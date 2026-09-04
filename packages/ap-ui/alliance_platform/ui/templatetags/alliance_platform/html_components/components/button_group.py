from __future__ import annotations

from typing import Any

from django.template import Context
from django.template import TemplateSyntaxError

from alliance_platform.frontend.bundler.frontend_resource import FrontendResource

from ..base import BaseHtmlUIComponentRenderer
from ..base import enum_prop_rule
from ..runtime import add_auto_attach_marker
from .button import BUTTON_PROP_RULES

VALID_ORIENTATIONS = ("horizontal", "vertical")
VALID_ALIGNS = ("start", "center", "end")
VALID_DENSITIES = ("compact", "xxs", "xs", "sm", "md", "lg", "xl", "xxl", "xxxl")

_BUTTON_GROUP_STYLE_PATH = "@alliancesoftware/ui/components/button/ButtonGroup.css.ts"
_SMART_ORIENTATION_STYLE_PATH = "@alliancesoftware/ui/components/layout/SmartOrientation.css.ts"
_RUNTIME_MODULE_PATH = "@alliancesoftware/ui/components/layout/SmartOrientation.auto.ts"

_BUTTON_GROUP_FORWARDED_PROPS = frozenset(
    {"id", "title", "role", "tabIndex", "dir", "lang", "hidden", "draggable"}
)


class UIButtonGroupRenderer(BaseHtmlUIComponentRenderer):
    apui_component_name = "button-group"
    slot_name = "buttonGroup"
    supported_props = frozenset(
        {
            "orientation",
            "align",
            "density",
            "isDisabled",
            "color",
            "variant",
            "size",
            "className",
            "style",
            "children",
            "slot",
        }
    )
    forwarded_props = _BUTTON_GROUP_FORWARDED_PROPS
    allow_data_props = True
    allow_aria_props = True
    prop_filter_context = "static button-group components"
    event_handler_prop_reason = "event handlers are not supported by static button-group components"
    prop_rules = {
        "orientation": enum_prop_rule(VALID_ORIENTATIONS, invalid_fallback="horizontal"),
        "align": enum_prop_rule(VALID_ALIGNS, invalid_fallback="start"),
        "density": enum_prop_rule(VALID_DENSITIES, invalid_fallback="md"),
        "variant": BUTTON_PROP_RULES["variant"],
        "color": BUTTON_PROP_RULES["color"],
        "size": BUTTON_PROP_RULES["size"],
    }

    def resolve_component_resources(self) -> list[FrontendResource]:
        return [
            self.resolve_frontend_resource(_BUTTON_GROUP_STYLE_PATH),
            self.resolve_frontend_resource(_SMART_ORIENTATION_STYLE_PATH),
            self._resolve_runtime_resource(),
        ]

    def render_children_for_component(self, context: Context, props: dict[str, Any]) -> str:
        group_styles = self.resolve_vanilla_extract_mapping(_BUTTON_GROUP_STYLE_PATH)
        slot_defaults = {
            key: props[key] for key in ("isDisabled", "color", "variant", "size") if key in props
        }
        button_slot_class_name = self.get_style_class(group_styles, "button")
        if button_slot_class_name:
            slot_defaults["className"] = button_slot_class_name
        return self.render_children(context, slot_overrides={"button": slot_defaults})

    def render_component(self, context: Context, props: dict[str, Any], children_html: str) -> str:
        if not children_html.strip():
            return ""

        orientation = str(props.get("orientation", "horizontal"))
        align_prop_present = "align" in props
        align = str(props.get("align", "start"))
        density_prop_present = "density" in props
        density = str(props.get("density", "md"))

        group_styles = self.resolve_vanilla_extract_mapping(_BUTTON_GROUP_STYLE_PATH)
        smart_orientation_styles = self.resolve_vanilla_extract_mapping(_SMART_ORIENTATION_STYLE_PATH)

        container_class_name = self.get_nested_style_class(smart_orientation_styles, "container", orientation)
        align_class_name = self.get_nested_style_class(smart_orientation_styles, "align", align)
        density_class_name = self.get_nested_style_class(smart_orientation_styles, "density", density)
        button_group_class_name = self.get_style_class(group_styles, "buttonGroup")
        class_name = self.join_classes(
            container_class_name,
            align_class_name,
            density_class_name,
            button_group_class_name,
            props.get("className"),
        )

        attrs: dict[str, Any] = {
            **self.collect_forwarded_props(props),
            "className": class_name,
            "data-apui": "button-group",
            "data-orientation": orientation,
            "data-density": density if density_prop_present else None,
            "data-align": align if align_prop_present else None,
            "style": props.get("style"),
        }

        add_auto_attach_marker(attrs, "smart-orientation")

        return self._render_tag("div", attrs, children_html)

    def _resolve_runtime_resource(self) -> FrontendResource:
        try:
            return self.resolve_frontend_resource(
                _RUNTIME_MODULE_PATH,
                resolve_extensions=[".ts", ".tsx", ".js", ".mjs"],
            )
        except TemplateSyntaxError as exc:
            raise TemplateSyntaxError(
                "Static button-group rendering requires "
                f"'{_RUNTIME_MODULE_PATH}'. Upgrade @alliancesoftware/ui to a compatible version."
            ) from exc
