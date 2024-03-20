import textwrap

from django.conf import settings
from django.test import SimpleTestCase

from common_frontend.bundler.vite import ViteBundler
from common_frontend.codegen.printer import TypescriptPrinter
from common_frontend.codegen.printer import TypescriptSourceFileWriter
from common_frontend.codegen.typescript import ArrayLiteralExpression
from common_frontend.codegen.typescript import AsExpression
from common_frontend.codegen.typescript import AsyncKeyword
from common_frontend.codegen.typescript import BooleanLiteral
from common_frontend.codegen.typescript import CallExpression
from common_frontend.codegen.typescript import convert_to_node
from common_frontend.codegen.typescript import create_accessor
from common_frontend.codegen.typescript import ElementAccessExpression
from common_frontend.codegen.typescript import ExportKeyword
from common_frontend.codegen.typescript import FunctionDeclaration
from common_frontend.codegen.typescript import Identifier
from common_frontend.codegen.typescript import ImportDeclaration
from common_frontend.codegen.typescript import ImportDefaultSpecifier
from common_frontend.codegen.typescript import ImportSpecifier
from common_frontend.codegen.typescript import NewExpression
from common_frontend.codegen.typescript import NumericLiteral
from common_frontend.codegen.typescript import ObjectLiteralExpression
from common_frontend.codegen.typescript import ObjectProperty
from common_frontend.codegen.typescript import Parameter
from common_frontend.codegen.typescript import PropertyAccessExpression
from common_frontend.codegen.typescript import ReturnStatement
from common_frontend.codegen.typescript import SpreadAssignment
from common_frontend.codegen.typescript import StringLiteral
from common_frontend.codegen.typescript import TemplateExpression
from common_frontend.codegen.typescript import TypeReference
from common_frontend.codegen.typescript import VariableDeclaration
from common_frontend.codegen.typescript import VariableDeclarator


class TypescriptPrinterTestCase(SimpleTestCase):
    def test_convert_to_node(self):
        self.assertEqual(
            convert_to_node({"color": "#ccc"}),
            ObjectLiteralExpression([ObjectProperty(Identifier("color"), StringLiteral("#ccc"))]),
        )
        self.assertEqual(
            convert_to_node(
                {"level1": {"level2_1": "One", "level2_2": 2, "level2_3": 1.3, "level2 4": False}}
            ),
            ObjectLiteralExpression(
                [
                    ObjectProperty(
                        Identifier("level1"),
                        ObjectLiteralExpression(
                            [
                                ObjectProperty(Identifier("level2_1"), StringLiteral("One")),
                                ObjectProperty(Identifier("level2_2"), NumericLiteral(2)),
                                ObjectProperty(Identifier("level2_3"), NumericLiteral(1.3)),
                                ObjectProperty(StringLiteral("level2 4"), BooleanLiteral(False)),
                            ]
                        ),
                    )
                ]
            ),
        )

    def test_variable_declaration(self):
        p = TypescriptPrinter()
        self.assertEqual(
            p.print(VariableDeclaration([VariableDeclarator(Identifier("name"), "Gandalf")], "const")),
            'const name = "Gandalf"',
        )
        self.assertEqual(
            p.print(VariableDeclaration([VariableDeclarator(Identifier("name"), 'Some "quotes"')], "const")),
            'const name = "Some \\"quotes\\""',
        )
        self.assertEqual(
            p.print(
                VariableDeclaration(
                    [
                        VariableDeclarator(Identifier("name"), "Frodo"),
                        VariableDeclarator(Identifier("companion"), "Samwise"),
                    ],
                    "const",
                )
            ),
            'const name = "Frodo", companion = "Samwise"',
        )
        self.assertEqual(
            p.print(
                VariableDeclaration(
                    [VariableDeclarator(Identifier("name"), "Gandalf")], "const", modifiers=[ExportKeyword()]
                )
            ),
            'export const name = "Gandalf"',
        )

    def test_import(self):
        p = TypescriptPrinter()
        self.assertEqual(
            p.print(
                ImportDeclaration(
                    "antd",
                    [
                        ImportDefaultSpecifier("antd"),
                        ImportSpecifier("Button"),
                        ImportSpecifier("Alert", "DefaultAlert"),
                    ],
                )
            ),
            "import antd, { Button, Alert as DefaultAlert } from 'antd';",
        )
        self.assertEqual(
            p.print(
                ImportDeclaration(
                    "antd",
                    [
                        ImportDefaultSpecifier("Antd"),
                    ],
                )
            ),
            "import Antd, {  } from 'antd';",
        )
        self.assertEqual(
            p.print(
                ImportDeclaration(
                    "antd",
                    [
                        ImportSpecifier("Button"),
                    ],
                )
            ),
            "import { Button } from 'antd';",
        )

    def test_object_expression(self):
        p = TypescriptPrinter()
        self.assertEqual(
            p.print(ObjectLiteralExpression([ObjectProperty(Identifier("color"), "#ccc")])),
            '{color: "#ccc"}',
        )
        self.assertEqual(
            p.print(
                ObjectLiteralExpression(
                    [
                        ObjectProperty(
                            Identifier("level1"),
                            ObjectLiteralExpression(
                                [
                                    ObjectProperty(Identifier("level2_1"), "One"),
                                    ObjectProperty(Identifier("level2_2"), "Two"),
                                ]
                            ),
                        ),
                        ObjectProperty("contains space", True),
                    ]
                )
            ),
            '{level1: {level2_1: "One", level2_2: "Two"}, "contains space": true}',
        )

    def test_object_expression_with_spread(self):
        p = TypescriptPrinter()
        self.assertEqual(
            p.print(
                ObjectLiteralExpression(
                    [
                        SpreadAssignment(
                            Identifier("base"),
                        ),
                        ObjectProperty(
                            Identifier("level1"),
                            ObjectLiteralExpression(
                                [
                                    ObjectProperty(Identifier("level2_1"), "One"),
                                    ObjectProperty(Identifier("level2_2"), "Two"),
                                    SpreadAssignment(Identifier("rest")),
                                ]
                            ),
                        ),
                        ObjectProperty("contains space", True),
                    ]
                )
            ),
            '{...base, level1: {level2_1: "One", level2_2: "Two", ...rest}, "contains space": true}',
        )

    def test_array_expression(self):
        p = TypescriptPrinter()
        self.assertEqual(
            p.print(
                ArrayLiteralExpression(
                    [
                        1,
                        ObjectLiteralExpression([ObjectProperty(Identifier("color"), "#ccc")]),
                        True,
                        "test",
                        9.8,
                        {"level1": "Test"},
                    ]
                )
            ),
            '[1, {color: "#ccc"}, true, "test", 9.8, {level1: "Test"}]',
        )

    def test_function_declaration(self):
        p = TypescriptPrinter()
        self.assertEqual(
            textwrap.dedent(
                p.print(
                    FunctionDeclaration(
                        Identifier("renderButton"),
                        [Parameter(Identifier("container")), Parameter(Identifier("props"))],
                        [VariableDeclaration([VariableDeclarator(Identifier("name"), "Gandalf")], "const")],
                    )
                )
            ).strip(),
            textwrap.dedent(
                """
                    function renderButton(container, props) {
                      const name = "Gandalf";
                    }
                """
            ).strip(),
        )

        self.assertEqual(
            textwrap.dedent(
                p.print(
                    FunctionDeclaration(
                        Identifier("renderButton"),
                        [Parameter(Identifier("container")), Parameter(Identifier("props"))],
                        [VariableDeclaration([VariableDeclarator(Identifier("name"), "Gandalf")], "const")],
                        [ExportKeyword(is_default=True), AsyncKeyword()],
                    )
                )
            ).strip(),
            textwrap.dedent(
                """
                    export default async function renderButton(container, props) {
                      const name = "Gandalf";
                    }
                """
            ).strip(),
        )

        self.assertEqual(
            textwrap.dedent(
                p.print(
                    FunctionDeclaration(
                        Identifier("identity"),
                        [Parameter(Identifier("a"))],
                        [ReturnStatement(Identifier("a"))],
                    )
                )
            ).strip(),
            textwrap.dedent(
                """
                    function identity(a) {
                      return a;
                    }
                """
            ).strip(),
        )

    def test_call_expression(self):
        p = TypescriptPrinter()
        self.assertEqual(
            p.print(
                CallExpression(
                    Identifier("renderButton"),
                )
            ),
            "renderButton()",
        )
        self.assertEqual(
            p.print(
                CallExpression(
                    Identifier("renderButton"),
                    [Identifier("container"), Identifier("props")],
                )
            ),
            "renderButton(container, props)",
        )
        self.assertEqual(
            p.print(
                CallExpression(
                    PropertyAccessExpression(
                        Identifier("document"),
                        Identifier("querySelector"),
                    ),
                    ["my-container"],
                )
            ),
            'document.querySelector("my-container")',
        )

    def test_as_expression(self):
        p = TypescriptPrinter()
        self.assertEqual(
            p.print(
                AsExpression(
                    ObjectLiteralExpression([ObjectProperty("example", True)]),
                    TypeReference(Identifier("const")),
                )
            ),
            '{"example": true} as const',
        )

    def test_property_access_expression(self):
        p = TypescriptPrinter()
        self.assertEqual(
            p.print(
                PropertyAccessExpression(
                    PropertyAccessExpression(
                        Identifier("my_obj"),
                        Identifier("property"),
                    ),
                    Identifier("nested"),
                )
            ),
            "my_obj.property.nested",
        )

    def test_element_access_expression(self):
        p = TypescriptPrinter()
        self.assertEqual(
            p.print(ElementAccessExpression(ElementAccessExpression(Identifier("my_obj"), "my key"), 5)),
            'my_obj["my key"][5]',
        )

    def test_template_expression(self):
        p = TypescriptPrinter()
        self.assertEqual(
            p.print(
                TemplateExpression(
                    [StringLiteral("Hello my name is "), Identifier("name"), ". What's yours?"]
                )
            ),
            "`Hello my name is ${name}. What's yours?`",
        )

    def test_new_expression(self):
        p = TypescriptPrinter()

        self.assertEqual(
            p.print(NewExpression(Identifier("Date"))),
            "new Date()",
        )

        date_str = "2020-01-01T00:00:00"
        self.assertEqual(
            p.print(NewExpression(Identifier("Date"), [StringLiteral(date_str)])),
            f'new Date("{date_str}")',
        )

    def test_create_accessor(self):
        p = TypescriptPrinter()

        self.assertEqual(
            p.print(create_accessor([Identifier("a"), "b", 500])),
            "a.b[500]",
        )
        self.assertEqual(
            p.print(create_accessor([Identifier("a"), Identifier("b"), NumericLiteral(500)])),
            "a.b[500]",
        )
        self.assertEqual(
            p.print(
                create_accessor(
                    [PropertyAccessExpression(Identifier("palette"), Identifier("primary")), "border", "sm"]
                )
            ),
            "palette.primary.border.sm",
        )


fixtures_dir = settings.BASE_DIR / "common_frontend/bundler/tests/fixtures"

bundler_kwargs = dict(
    root_dir=settings.PROJECT_DIR,
    path_resolvers=[],
    build_dir=fixtures_dir / "build_test",
    server_build_dir=fixtures_dir / "server_build_test",
    server_host="localhost",
    server_port="5173",
    server_protocol="http",
)


class TypescriptSourceFileWriterTestCase(SimpleTestCase):
    def test_resolve_import_dedupe(self):
        bundler = ViteBundler(
            **bundler_kwargs,  # type: ignore[arg-type]
            mode="development",
        )
        p = TypescriptSourceFileWriter(resolve_import_url=bundler.get_url)
        p.resolve_import("frontend/src/ssr.ts", ImportSpecifier("renderItems")),
        self.assertEqual(
            p.resolve_import("frontend/src/renderComponent.tsx", ImportSpecifier("createElement", "$")),
            p.resolve_import("frontend/src/renderComponent.tsx", ImportSpecifier("createElement", "$")),
        )
