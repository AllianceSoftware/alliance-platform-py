import textwrap

from alliance_platform.codegen.printer import TypescriptPrinter
from alliance_platform.codegen.printer import TypescriptSourceFileWriter
from alliance_platform.codegen.typescript import ArrayLiteralExpression
from alliance_platform.codegen.typescript import ArrowFunction
from alliance_platform.codegen.typescript import AsExpression
from alliance_platform.codegen.typescript import AsyncKeyword
from alliance_platform.codegen.typescript import BooleanLiteral
from alliance_platform.codegen.typescript import CallExpression
from alliance_platform.codegen.typescript import ElementAccessExpression
from alliance_platform.codegen.typescript import ExportKeyword
from alliance_platform.codegen.typescript import FunctionDeclaration
from alliance_platform.codegen.typescript import Identifier
from alliance_platform.codegen.typescript import ImportDeclaration
from alliance_platform.codegen.typescript import ImportDefaultSpecifier
from alliance_platform.codegen.typescript import ImportSpecifier
from alliance_platform.codegen.typescript import JsxAttribute
from alliance_platform.codegen.typescript import JsxElement
from alliance_platform.codegen.typescript import JsxExpression
from alliance_platform.codegen.typescript import JsxSpreadAttribute
from alliance_platform.codegen.typescript import JsxText
from alliance_platform.codegen.typescript import MultiLineComment
from alliance_platform.codegen.typescript import NewExpression
from alliance_platform.codegen.typescript import NumericLiteral
from alliance_platform.codegen.typescript import ObjectLiteralExpression
from alliance_platform.codegen.typescript import ObjectProperty
from alliance_platform.codegen.typescript import Parameter
from alliance_platform.codegen.typescript import PropertyAccessExpression
from alliance_platform.codegen.typescript import ReturnStatement
from alliance_platform.codegen.typescript import SingleLineComment
from alliance_platform.codegen.typescript import SpreadAssignment
from alliance_platform.codegen.typescript import StringLiteral
from alliance_platform.codegen.typescript import TemplateExpression
from alliance_platform.codegen.typescript import TypeReference
from alliance_platform.codegen.typescript import VariableDeclaration
from alliance_platform.codegen.typescript import VariableDeclarator
from alliance_platform.codegen.typescript import convert_to_node
from alliance_platform.codegen.typescript import create_accessor
from django.conf import settings
from django.test import SimpleTestCase


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

    def test_jsx_simple(self):
        tests = [
            (None, "<Button isDisabled={true}>Click Me</Button>"),
            (Identifier("createElement"), 'createElement(Button, {isDisabled: true}, "Click Me")'),
        ]
        for jsx_transform, expected in tests:
            with self.subTest(jsx_transform=jsx_transform):
                p = TypescriptPrinter(jsx_transform=jsx_transform)
                self.assertEqual(
                    p.print(
                        JsxElement(
                            Identifier("Button"),
                            [JsxAttribute(Identifier("isDisabled"), BooleanLiteral(True))],
                            [JsxText("Click Me")],
                        )
                    ),
                    expected,
                )

    def test_jsx_unicode(self):
        tests = [
            (None, "<Button>“Testing and Stuff” 🥰</Button>"),
            (
                Identifier("createElement"),
                'createElement(Button, {}, "“Testing and Stuff” 🥰")',
            ),
        ]
        for jsx_transform, expected in tests:
            with self.subTest(jsx_transform=jsx_transform):
                p = TypescriptPrinter(jsx_transform=jsx_transform)
                self.assertEqual(
                    p.print(
                        JsxElement(
                            Identifier("Button"),
                            [],
                            [JsxText("“Testing and Stuff” 🥰")],
                        )
                    ),
                    expected,
                )

    def test_jsx_html_entities(self):
        tests = [
            # Rather than escaping in printer we output the string in a JSX expression.
            (None, '<Button>{"This & that"}</Button>'),
            (
                Identifier("createElement"),
                'createElement(Button, {}, "This & that")',
            ),
        ]
        for jsx_transform, expected in tests:
            with self.subTest(jsx_transform=jsx_transform):
                p = TypescriptPrinter(jsx_transform=jsx_transform)
                self.assertEqual(
                    p.print(
                        JsxElement(
                            Identifier("Button"),
                            [],
                            [JsxText("This & that")],
                        )
                    ),
                    expected,
                )

    def test_jsx_spread_attribute(self):
        tests = [
            (None, "<Button isDisabled={true} {...props}>Click Me</Button>"),
            (
                Identifier("createElement"),
                'createElement(Button, {isDisabled: true, ...props}, "Click Me")',
            ),
        ]
        for jsx_transform, expected in tests:
            with self.subTest(jsx_transform=jsx_transform):
                p = TypescriptPrinter(jsx_transform=jsx_transform)
                self.assertEqual(
                    p.print(
                        JsxElement(
                            Identifier("Button"),
                            [
                                JsxAttribute(Identifier("isDisabled"), BooleanLiteral(True)),
                                JsxSpreadAttribute(Identifier("props")),
                            ],
                            [JsxText("Click Me")],
                        )
                    ),
                    expected,
                )

    def test_jsx_dashed_attribute_keys(self):
        tests = [
            (None, '<Button aria-label="Click Me">X</Button>'),
            (Identifier("createElement"), 'createElement(Button, {"aria-label": "Click Me"}, "X")'),
        ]
        for jsx_transform, expected in tests:
            with self.subTest(jsx_transform=jsx_transform):
                p = TypescriptPrinter(jsx_transform=jsx_transform)
                self.assertEqual(
                    p.print(
                        JsxElement(
                            Identifier("Button"),
                            [JsxAttribute(StringLiteral("aria-label"), StringLiteral("Click Me"))],
                            [JsxText("X")],
                        )
                    ),
                    expected,
                )

    def test_jsx_comments(self):
        tests = [
            (
                None,
                "// Leading comment\n"
                "<Button>Click Me\n"
                "{/* Inner leading comment */}\n"
                "<strong>Nested</strong>\n"
                "{/* Inner trailing comment */}\n"
                "</Button>\n"
                "// Trailing comment",
            ),
            (
                Identifier("createElement"),
                "createElement(\n"
                "// Leading comment\n"
                "Button\n"
                "// Trailing comment\n"
                ', {}, "Click Me", createElement(\n'
                "/* Inner leading comment */\n"
                '"strong"\n'
                "/* Inner trailing comment */\n"
                ', {}, "Nested"))',
            ),
        ]
        for jsx_transform, expected in tests:
            with self.subTest(jsx_transform=jsx_transform):
                p = TypescriptPrinter(jsx_transform=jsx_transform)
                self.assertEqual(
                    p.print(
                        JsxElement(
                            Identifier("Button"),
                            [],
                            [
                                JsxText("Click Me"),
                                JsxElement(
                                    StringLiteral("strong"),
                                    [],
                                    [JsxText("Nested")],
                                    leading_comments=[MultiLineComment("Inner leading comment")],
                                    trailing_comments=[MultiLineComment("Inner trailing comment")],
                                ),
                            ],
                            leading_comments=[SingleLineComment("Leading comment")],
                            trailing_comments=[SingleLineComment("Trailing comment")],
                        )
                    ),
                    expected,
                )

    def test_jsx_function_children(self):
        tests = [
            (None, "<Provider>{() => <span>child</span>}</Provider>"),
            (
                Identifier("createElement"),
                'createElement(Provider, {}, () => createElement("span", {}, "child"))',
            ),
        ]
        for jsx_transform, expected in tests:
            with self.subTest(jsx_transform=jsx_transform):
                p = TypescriptPrinter(jsx_transform=jsx_transform)
                self.assertEqual(
                    p.print(
                        JsxElement(
                            Identifier("Provider"),
                            [],
                            [
                                JsxExpression(
                                    ArrowFunction(
                                        [], JsxElement(StringLiteral("span"), [], [JsxText("child")])
                                    )
                                )
                            ],
                        )
                    ),
                    expected,
                )

    def test_jsx_comments_attribute(self):
        tests = [
            (None, "<Wrapper element={\n/* Leading comment */\n<Inner />} />"),
            (
                Identifier("createElement"),
                'createElement(Wrapper, {"element": createElement(\n'
                "/* Leading comment */\n"
                "Inner, {})})",
            ),
        ]
        for jsx_transform, expected in tests:
            with self.subTest(jsx_transform=jsx_transform):
                p = TypescriptPrinter(jsx_transform=jsx_transform)
                self.assertEqual(
                    p.print(
                        JsxElement(
                            Identifier("Wrapper"),
                            [
                                JsxAttribute(
                                    StringLiteral(
                                        "element",
                                    ),
                                    JsxElement(
                                        Identifier("Inner"),
                                        [],
                                        [],
                                        leading_comments=[MultiLineComment("Leading comment")],
                                    ),
                                )
                            ],
                            [],
                        )
                    ),
                    expected,
                )


fixtures_dir = settings.BASE_DIR / "alliance_platform_frontend/bundler/tests/fixtures"


class TypescriptSourceFileWriterTestCase(SimpleTestCase):
    def test_resolve_import_dedupe(self):
        def get_url(path):
            return path

        p = TypescriptSourceFileWriter(resolve_import_url=get_url)
        (p.resolve_import("frontend/src/ssr.ts", ImportSpecifier("renderItems")),)
        self.assertEqual(
            p.resolve_import("frontend/src/renderComponent.tsx", ImportSpecifier("createElement", "$")),
            p.resolve_import("frontend/src/renderComponent.tsx", ImportSpecifier("createElement", "$")),
        )
