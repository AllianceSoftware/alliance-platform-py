import argparse
import json
from pathlib import Path
import re
from typing import cast

from django.conf import settings
from django.core.management import BaseCommand

from ...codegen.printer import TypescriptSourceFileWriter
from ...codegen.typescript import AsExpression
from ...codegen.typescript import construct_object_property_key
from ...codegen.typescript import convert_to_node
from ...codegen.typescript import create_accessor
from ...codegen.typescript import ExportKeyword
from ...codegen.typescript import Identifier
from ...codegen.typescript import ImportDefaultSpecifier
from ...codegen.typescript import ImportSpecifier
from ...codegen.typescript import Node
from ...codegen.typescript import NodeLike
from ...codegen.typescript import ObjectLiteralExpression
from ...codegen.typescript import ObjectProperty
from ...codegen.typescript import PropertyAccessExpression
from ...codegen.typescript import SingleLineComment
from ...codegen.typescript import SpreadAssignment
from ...codegen.typescript import StringLiteral
from ...codegen.typescript import TemplateExpression
from ...codegen.typescript import TypeReference
from ...codegen.typescript import VariableDeclaration
from ...codegen.typescript import VariableDeclarator


def arg_json_path(value):
    """For use with argparser to validate that a path exists and is a JSON file"""
    p = Path(value)
    if not p.exists():
        raise argparse.ArgumentTypeError(f"{value} is not a valid path")
    if not p.suffix == ".json":
        raise argparse.ArgumentTypeError(f"{value} must be a JSON file")
    return p


palette_path = settings.PROJECT_DIR / "styles/palette.ts"
contract_path = settings.PROJECT_DIR / "styles/contract.css.ts"
tokens_path = settings.PROJECT_DIR / "styles/tokens.css.ts"
base_tokens_path = settings.PROJECT_DIR / "styles/baseTokens.css.ts"


def generate_palette(main_colors) -> None:
    palette: dict[str, dict[str, str]] = {}
    for color in ["gray", "primary", "secondary", "error", "warning", "success", "base"]:
        palette[color] = {}
        for key, value in main_colors["baseColours"][color].items():
            if value["type"] == "color":
                palette[color][key] = value["value"]

    with TypescriptSourceFileWriter(palette_path) as sfw:
        sfw.add_leading_node(SingleLineComment("!! DO NOT MAKE CHANGES TO THIS FILE, THEY WILL BE LOST !!!"))
        sfw.add_leading_node(SingleLineComment("Code generated by ``import_figma_tokens``."))
        node = VariableDeclaration(
            [
                VariableDeclarator(
                    Identifier("palette"),
                    AsExpression(
                        convert_to_node(cast(NodeLike, palette)), TypeReference(Identifier("const"))
                    ),
                )
            ],
            "const",
            modifiers=[ExportKeyword()],
        )
        sfw.add_node(node)


def resolve_import_url_no_ext(path: Path | str) -> str:
    """Don't include typescript extensions for code generated for tokens.

    Without this will trigger lint warnings about unnecessary extensions.
    """
    path = str(path)
    for ext in [".ts", ".tsx"]:
        if path.endswith(ext):
            path = path[: -len(ext)]
            break
    return path


class FigmaTokenTransformer(TypescriptSourceFileWriter):
    def __init__(self, path: Path, raw_tokens_data: dict):
        super().__init__(path, resolve_import_url=resolve_import_url_no_ext)
        self.raw_tokens_data = raw_tokens_data
        self.add_leading_node(SingleLineComment("!! DO NOT MAKE CHANGES TO THIS FILE, THEY WILL BE LOST !!!"))
        self.add_leading_node(
            SingleLineComment(
                "Code generated by ``import_figma_tokens``. To add additional tokens see ``baseTokens.ts``"
            )
        )

    def resolve_var_ref(self, name):
        if name == "baseColours":
            if self.path == tokens_path:
                return self.resolve_import(palette_path, ImportSpecifier("palette"))
            return PropertyAccessExpression(
                self.resolve_import(contract_path, ImportSpecifier("vars")), Identifier("palette")
            )
        if name in [
            "spacing",
            "borderRadius",
            "borderWidth",
            "fontFamilies",
            "fontSize",
            "letterSpacing",
            "lineHeight",
        ]:
            name_mapping = {"fontFamilies": "fontFamily"}
            return PropertyAccessExpression(
                self.resolve_import(contract_path, ImportSpecifier("vars")),
                Identifier(name_mapping.get(name, name)),
            )
        raise ValueError(f"Unknown ref '{name}'")

    def _get_replacement_vars(self, value: str):
        return list(re.finditer(r"{([^}]*)}", value))

    def convert_string(self, value):
        matches = self._get_replacement_vars(value)
        if matches:
            pieces = []
            prev_end = None
            for match in matches:
                ref_name, *accessor_path = match.groups()[0].split(".")
                if ref_name == "borderColour":
                    # TODO: Special case. This referred to borderColor but seemed redundant - why not just resolve them
                    # all under the `border` key? I do that here. We should probably just do this direct in Figma.
                    datum = self.raw_tokens_data["main/components"]["borderColour"]
                    for piece in accessor_path:
                        datum = datum[piece]
                    accessor = self.convert_token(datum)
                else:
                    try:
                        var_identifier = self.resolve_var_ref(ref_name)
                        accessor = create_accessor([var_identifier, *accessor_path])
                    except ValueError:
                        if ref_name in ["padding"]:
                            ref_values = self.raw_tokens_data["main/components"][ref_name]
                            accessor = ref_values
                            for p in accessor_path:
                                accessor = accessor[p]
                        else:
                            raise
                joiner = value[prev_end : match.start()]
                if joiner:
                    pieces.append(StringLiteral(joiner))
                pieces.append(accessor)
                prev_end = match.end()
            if len(pieces) == 1:
                return pieces[0]
            return TemplateExpression(pieces)
        return StringLiteral(value)

    def convert_token(self, token):
        if isinstance(token, Node):
            return token
        if "value" not in token or "type" not in token:
            return {key: self.convert_token(n) for key, n in token.items()}
        value = token["value"]
        value_type = token["type"]
        if value_type == "boxShadow":
            return self.convert_string(self.convert_box_shadow(token))
        if value_type == "border":
            return self.convert_border(token)
        if value_type == "typography":
            return self.convert_typography(token)
        if value_type in ["spacing", "lineHeights", "fontSizes"]:
            try:
                # check if has no units
                int(value)
                value = StringLiteral(f"{value}px")
            except ValueError:
                pass
        if isinstance(value, str):
            return self.convert_string(value)
        return value

    def convert_border(self, token):
        """
        e.g.
         {
            "value": {
              "color": "{borderColour.button.primary.default}",
              "width": "{borderWidth.base.xs}",
              "style": "Solid"
            },
            "type": "border"
         }
        """
        return {
            "borderColor": self.convert_string(token["value"]["color"]),
            "borderWidth": self.convert_string(token["value"]["width"]),
            "borderStyle": self.convert_string(token["value"]["style"].lower()),
        }

    def convert_color(self, value: str):
        if value.startswith("#"):
            parts = [int(value[i : i + 2], 16) for i in range(1, len(value), 2)]
            if len(parts) == 4:
                return f"rgba({parts[0]}, {parts[1]}, {parts[2]}, {parts[3] / 255:.2f})"
            if len(parts) == 3:
                return f"rgb({parts[0]}, {parts[1]}, {parts[2]})"
        matches = self._get_replacement_vars(value)
        if matches:
            # If has replacement var leave it for replacement by convert_string
            return value
        raise ValueError(f"Unknown color format: {value}")

    def convert_drop_shadow(self, value: dict):
        spread = ""
        if value["spread"] != "0":
            spread = f"{value['spread']}px "
        return f"{value['x']}px {value['y']}px {value['blur']}px {spread}{self.convert_color(value['color'])}"

    def convert_box_shadow(self, token: dict):
        if isinstance(token["value"], list):
            return ", ".join([self.convert_drop_shadow(v) for v in token["value"]])
        return self.convert_drop_shadow(token["value"])

    def convert_typography(self, token):
        """
        e.g.
        {
            "value": {
                fontFamily: '{fontFamilies.body}',
                fontWeight: '{fontWeights.semibold}',
                lineHeight: '{lineHeight.xl}',
                fontSize: '{fontSize.xl}',
                letterSpacing: '{letterSpacing.normal}',
                paragraphSpacing: '{paragraphSpacing.none}',
                paragraphIndent: '{paragraphIndent.none}',
                textCase: '{textCase.none}',
                textDecoration: '{textDecoration.none}',
            },
            "type": "typography"
        }
        """
        return {
            "fontFamily": self.convert_string(token["value"]["fontFamily"]),
            "fontSize": self.convert_string(token["value"]["fontSize"]),
            "letterSpacing": self.convert_string(token["value"]["letterSpacing"]),
            "lineHeight": self.convert_string(token["value"]["lineHeight"]),
        }


def generate_tokens(raw_token_data):
    text_colors = {}
    for key, value in raw_token_data["main/colours"]["textColour"].items():
        text_colors[key] = value

    shadow = {}
    for key, token in raw_token_data["main/base"]["shadow"].items():
        shadow[key] = token

    focus_ring = {}
    for key, token in raw_token_data["main/base"]["focusRing"].items():
        focus_ring[key] = token

    with FigmaTokenTransformer(tokens_path, raw_token_data) as sfw:
        converted_token = sfw.convert_token(
            {
                "borderRadius": {
                    key: token for key, token in raw_token_data["main/base"]["borderRadius"].items()
                },
                "borderWidth": {
                    key: token for key, token in raw_token_data["main/base"]["borderWidth"].items()
                },
                "colors": {"text": text_colors},
                "focusRing": focus_ring,
                "fontFamily": {
                    "headings": raw_token_data["main/fonts"]["fontFamilies"]["headings"],
                    "body": raw_token_data["main/fonts"]["fontFamilies"]["body"],
                },
                "fontSize": raw_token_data["main/fonts"]["fontSize"],
                "letterSpacing": raw_token_data["main/fonts"]["letterSpacing"],
                "lineHeight": raw_token_data["main/fonts"]["lineHeight"],
                "palette": sfw.resolve_import(palette_path, ImportSpecifier("palette")),
                "shadow": shadow,
                "spacing": {
                    "gap": {
                        key: token for key, token in raw_token_data["main/base"]["spacing"]["gap"].items()
                    },
                    "padding": {
                        key: token for key, token in raw_token_data["main/base"]["spacing"]["padding"].items()
                    },
                },
            }
        )
        node = ObjectLiteralExpression(
            [
                SpreadAssignment(sfw.resolve_import(base_tokens_path, ImportDefaultSpecifier("baseTokens"))),
                *(
                    ObjectProperty(construct_object_property_key(key), convert_to_node(v))
                    for key, v in converted_token.items()
                ),
            ]
        )
        sfw.add_node(
            VariableDeclaration([VariableDeclarator(Identifier("tokens"), node)], "const", [ExportKeyword()])
        )

        node = sfw.convert_token(
            {
                "button": {
                    "padding": raw_token_data["main/components"]["padding"]["button"],
                    "borderRadius": raw_token_data["main/components"]["borderRadius"]["button"],
                    "gap": raw_token_data["main/components"]["gap"]["button"],
                    "backgroundColor": raw_token_data["main/components"]["backgroundColour"]["button"],
                    "textColor": raw_token_data["main/components"]["textColour"]["button"],
                    "border": raw_token_data["main/components"]["border"]["button"],
                    "typography": raw_token_data["main/fonts"]["global"]["button"],
                },
                "input": {
                    "padding": raw_token_data["main/components"]["padding"]["input"],
                    "gap": raw_token_data["main/components"]["gap"]["input"],
                    "backgroundColor": raw_token_data["main/components"]["backgroundColour"]["input"],
                    "border": raw_token_data["main/components"]["border"]["input"],
                },
                "label": raw_token_data["main/fonts"]["global"]["label"],
                "fonts": {
                    "desktop": raw_token_data["main/fonts"]["desktop"],
                    "mobile": raw_token_data["main/fonts"]["mobile"],
                },
                "alert": {
                    "borderRadius": raw_token_data["main/components"]["borderRadius"]["alert"],
                    "backgroundColor": raw_token_data["main/components"]["backgroundColour"]["alert"],
                    "border": raw_token_data["main/components"]["border"]["alert"],
                },
                "tooltip": {
                    "borderRadius": raw_token_data["main/components"]["borderRadius"]["tooltip"],
                    "backgroundColor": raw_token_data["main/components"]["backgroundColour"]["tooltip"],
                },
                "dropdownListItem": {
                    "backgroundColor": raw_token_data["main/components"]["backgroundColour"][
                        "dropdownListItem"
                    ],
                },
                "checkbox": {
                    "backgroundColor": raw_token_data["main/components"]["backgroundColour"]["checkbox"],
                    "borderColor": raw_token_data["main/components"]["borderColour"]["checkbox"],
                    "borderRadius": raw_token_data["main/components"]["borderRadius"]["checkbox"],
                },
                "pagination": {
                    "backgroundColor": raw_token_data["main/components"]["backgroundColour"]["pagination"],
                    "borderColor": raw_token_data["main/components"]["borderColour"]["pagination"],
                    "borderRadius": raw_token_data["main/components"]["borderRadius"]["pagination"],
                },
                "modal": {
                    "backgroundColor": raw_token_data["main/components"]["backgroundColour"]["modal"],
                    "borderRadius": raw_token_data["main/components"]["borderRadius"]["modal"],
                },
                "calendarCell": {
                    "backgroundColor": raw_token_data["main/components"]["backgroundColour"]["calendarCell"],
                },
            }
        )
        sfw.add_node(
            VariableDeclaration(
                [
                    VariableDeclarator(
                        Identifier("componentVars"), AsExpression(node, TypeReference(Identifier("const")))
                    )
                ],
                "const",
                [ExportKeyword()],
            )
        )


class Command(BaseCommand):
    help = "Import from a Figma Token Studio export and create the necessary .css.ts files"

    def add_arguments(self, parser):
        parser.add_argument(
            "token_file", type=arg_json_path, help="The JSON export from Figma to import from"
        )

    def handle(self, token_file, **kwargs):
        raw_token_data = json.loads(token_file.read_text())
        self.patch_data(raw_token_data)
        generate_palette(raw_token_data["main/colours"])
        generate_tokens(raw_token_data)

    def patch_data(self, raw_token_data: dict):
        """This modifies the token data to fix issues we haven't yet resolved in Figma

        This function should eventually go away
        """
        # Example:
        # raw_token_data["main/components"]["textColour"]["button"]["primary"]["plain"]["default"][
        #     "value"
        # ] = "{baseColours.base.White}"
