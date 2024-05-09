from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
import re
from typing import Callable
from typing import Sequence
from typing import Union

from django.utils.functional import Promise

# To work out what to name things enter code at https://astexplorer.net/ and see what AST it generates
# We don't need to be strict so exclude things where it makes it easier to use


@dataclass(kw_only=True)
class Node:
    """Root node everything else should extend from"""

    leading_comments: Sequence[Union["SingleLineComment", "MultiLineComment"]] | None = None
    trailing_comments: Sequence[Union["SingleLineComment", "MultiLineComment"]] | None = None


class Modifier:
    """Base class for modifiers"""

    pass


@dataclass
class ExportKeyword(Modifier):
    """
    Makes it so the identifier this is attached to is exported

    Usage::

        VariableDeclaration(
            [VariableDeclarator(Identifier("name"), "Gandalf")], "const", modifiers=[ExportKeyword()]
        )

        > export const name = "Gandalf"
    """

    is_default: bool = False


@dataclass
class AsyncKeyword(Modifier):
    """
    Makes it so the function this is attached to is marked as async

    Usage::

        FunctionDeclaration(
            Identifier("renderButton"),
            [Parameter(Identifier("container")), Parameter(Identifier("props"))],
            [VariableDeclaration([VariableDeclarator(Identifier("name"), "Gandalf")], "const")],
            [ExportKeyword(is_default=True), AsyncKeyword()],
        )

        > export default async function renderButton(container, props) {
        >  const name = "Gandalf";
        > }
    """

    pass


@dataclass
class NumericLiteral(Node):
    """A numeric literal"""

    value: int | float


@dataclass
class BooleanLiteral(Node):
    """A boolean literal"""

    value: bool


@dataclass
class StringLiteral(Node):
    """A string literal"""

    value: str


@dataclass
class NullKeyword(Node):
    pass


Literal = int | str | float | bool | NumericLiteral | BooleanLiteral | StringLiteral

reserved_words_js = [
    "await",
    "break",
    "case",
    "catch",
    "class",
    "const",
    "continue",
    "debugger",
    "default",
    "delete",
    "do",
    "else",
    "export",
    "extends",
    "false",
    "finally",
    "for",
    "function",
    "if",
    "import",
    "in",
    "instanceof",
    "let",
    "new",
    "null",
    "return",
    "static",
    "super",
    "switch",
    "this",
    "throw",
    "true",
    "try",
    "typeof",
    "var",
    "void",
    "while",
    "with",
    "yield",
]


class InvalidIdentifier(ValueError):
    pass


@dataclass
class Identifier(Node):
    """An identifier

    Will enforce naming is valid (i.e. cannot start with a digit, only contains alphanumeric characters, $ & _)

    Optionally can enforce not a reserved word.
    """

    name: str
    # TODO: not used yet, but this would support eg. const name: string = "Blah"
    type: Node | None = None

    def __post_init__(self):
        if self.name[0].isnumeric():
            raise InvalidIdentifier(f"Identifier '{self.name}' cannot start with a digit")
        if not re.match(r"^[$_0-9a-zA-Z]*$", self.name):
            raise InvalidIdentifier(
                f"Identifier '{self.name}' must be only contain letters, $, _, and digits"
            )

    def validate_reserved_words(self):
        """Validate can be used as an identifier

        This isn't done automatically as it doesn't apply universally

        .. code-block:: text

            e.g. const a = { test: true } as const;
                                 const a = { const: 5 }
                                           a.const
                                                ^ these three are all Identifier's and are valid
                 const const = { test: true };
                        ^ this is an Identifier but is not valid in this context
        """
        if self.name in reserved_words_js:
            raise ValueError(f"'{self.name}' is a reserved word in javascript")


AcceptedPropertyKeyType = int | float | str | Identifier | NumericLiteral | StringLiteral
#: A type that can be converted to a node
NodeLike = (
    Node
    | str
    | int
    | float
    | bool
    | None
    | list["NodeLike"]
    | tuple["NodeLike"]
    # making this more specific caused more problems than it was worth
    | dict
)


@dataclass
class TypeReference(Node):
    """TODO: Unclear what this should look like yet; need typeArguments as well for generics"""

    name: Identifier


@dataclass
class AsExpression(Node):
    """Typescript as expression, e.g.

    const a = { "example": true } as const;

    Usage::

        AsExpression(
            ObjectLiteralExpression([ObjectProperty("example", True)]),
            TypeReference(Identifier("const")),
        )

        > {"example": true} as const
    """

    expression: Node
    type_annotation: TypeReference


@dataclass
class VariableDeclarator(Node):
    """This is the ``myVar = 5`` part of a declaration"""

    name: Identifier
    init: Node | Literal

    def __post_init__(self):
        self.name.validate_reserved_words()


@dataclass
class VariableDeclaration(Node):
    """
    Usage::

        VariableDeclaration([VariableDeclarator(Identifier("name"), "Gandalf")], "const")

        > const name = "Gandalf"
    """

    declarations: list[VariableDeclarator | AsExpression]
    # let or const
    kind: str
    # This can be used e.g. to export the declaration
    modifiers: list[Modifier] = field(default_factory=list)


class ImportSpecifier(Node):
    """Represents the named import portion of an import declaration

    .. code-block:: javascript

        import { path as defaultPath } from 'pathlib';

    would be represented as

    .. code-block:: python

        ImportSpecifier("path", "defaultPath")

    Should be used in conjunction with ``ImportDeclaration``
    """

    #: The name of the import from the module
    imported: Identifier
    #: The local name of the import - defaults to same as imported
    local: Identifier

    def __init__(self, imported: str | Identifier, local: str | Identifier | None = None):
        if local is None:
            local = imported

        if isinstance(local, str):
            local = Identifier(local)
        if isinstance(imported, str):
            imported = Identifier(imported)
        self.imported = imported
        self.local = local

    def __str__(self):
        return f"ImportSpecifier({self.imported.name}, {self.local.name})"


class ImportDefaultSpecifier(Node):
    """Represents the default portion of an import declaration

    .. code-block:: javascript

        import Button from 'antd/es/button';

    would be represented with

    .. code-block:: python

        ImportDefaultSpecifier("Button")

    Should be used in conjunction with ``ImportDeclaration``
    """

    local: Identifier

    def __init__(self, local: str | Identifier):
        if isinstance(local, str):
            local = Identifier(local)
        self.local = local

    def __str__(self):
        return f"ImportDefaultSpecifier('{self.local.name}')"


@dataclass
class ImportDeclaration(Node):
    """Represents a javascript import declaration.

    A declaration is made up of ``source`` which is the module to import from and a numer of specifiers,
    one of which can be ``ImportDefaultSpecifier``.

    .. code-block:: javascript

        import antd, { Button, Alert as DefaultAlert } from 'antd';

    would be represented with

    .. code-block:: python

        ImportDeclaration('antd', [
            ImportDefaultSpecifier("antd"),
            ImportSpecifier("Button"),
            ImportSpecifier("Alert", "DefaultAlert"),
        ])
    """

    source: str | Path
    specifiers: list[ImportDefaultSpecifier | ImportSpecifier] = field(default_factory=list)
    # Priority to use when sorting imports. Higher numbers will be imported first.
    import_order_priority: int = 0

    def get_specifier(
        self, specifier: ImportDefaultSpecifier | ImportSpecifier
    ) -> ImportDefaultSpecifier | ImportSpecifier | None:
        """Get matching specifier if it exists, otherwise return ``None``"""
        for existing_specifier in self.specifiers:
            if type(existing_specifier) is type(specifier):
                # second isinstance technically redundant because of above check but included for mypy
                if isinstance(existing_specifier, ImportSpecifier) and isinstance(specifier, ImportSpecifier):
                    if existing_specifier.imported == specifier.imported:
                        return existing_specifier
                else:
                    # for ImportDefaultSpecifier if it exists then it matches as you can only have one
                    return existing_specifier
        return None

    def add_specifier(self, specifier: ImportDefaultSpecifier | ImportSpecifier):
        """Add the specifier. If it already exists an error will be thrown."""
        existing = self.get_specifier(specifier)
        if existing:
            raise ValueError("Specifier already exists.")
        self.specifiers.append(specifier)
        return specifier

    def get_default_specifier(self):
        for specifier in self.specifiers:
            if isinstance(specifier, ImportDefaultSpecifier):
                return specifier
        return None


@dataclass
class ObjectProperty(Node):
    """The property (key / value pair) on an object"""

    name: Identifier | Literal  # TODO: Could also be computed property name
    init: Node | Literal


@dataclass
class SpreadAssignment(Node):
    """A spread assignment within an object

    Usage::

        ObjectLiteralExpression(
            [
                SpreadAssignment(Identifier("base")),
                ObjectProperty(Identifier("key1", "One")),
            ]
        )

        > { ...base, key1: 'One' }
    """

    expression: Node


@dataclass
class ObjectLiteralExpression(Node):
    """e.g. { key1: "One", key2: "Two" }

    Usage::

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

        > {level1: {level2_1: "One", level2_2: "Two"}, "contains space": true}
    """

    properties: list[SpreadAssignment | ObjectProperty]


class ArrayLiteralExpression(Node):
    """e.g. [1,2,3]

    Usage::

        ArrayLiteralExpression(
            [
                1,
                ObjectLiteralExpression([ObjectProperty(Identifier("color"), "#ccc")]),
                True,
                "test",
                9.8,
            ]
        )

        > [1, {color: "#ccc"}, true, "test", 9.8]
    """

    elements: list[Node]

    def __init__(self, elements: list[NodeLike]):
        self.elements = [convert_to_node(value) for value in elements]


@dataclass
class Parameter(Node):
    """Parameter to function"""

    name: Identifier
    init: Node | None = None

    def __post_init__(self):
        self.name.validate_reserved_words()


@dataclass
class FunctionDeclaration(Node):
    """
    Usage::

        FunctionDeclaration(
            Identifier("renderButton"),
            [Parameter(Identifier("container")), Parameter(Identifier("props"))],
            [VariableDeclaration([VariableDeclarator(Identifier("name"), "Gandalf")], "const")],
        )

        > function renderButton(container, props) {
        >     const name = "Gandalf";
        > }
    """

    #: The name of the function
    name: Identifier
    #: Any parameters to the function
    parameters: list[Parameter]
    #: List of body statements
    statements: list[Node]
    #: Can be used to export the function and/or make it async
    modifiers: list[Modifier] = field(default_factory=list)

    def __post_init__(self):
        self.name.validate_reserved_words()


@dataclass
class ReturnStatement(Node):
    """A return statement in a function

    Usage::

       FunctionDeclaration(
           Identifier("identity"),
           [Parameter(Identifier("a"))],
           [ReturnStatement(Identifier("a"))],
       )

       > function identity(a) {
       >   return a;
       > }
    """

    expression: Node


@dataclass
class CallExpression(Node):
    """Function call eg. ``identifier(arg1, arg2)`` or ``obj[key](arg1, arg2)``

    Usage::

        CallExpression(
            Identifier("renderButton"),
            [Identifier("container"), Identifier("props")],
        )

        > renderButton(container, props)
    """

    expression: Node
    arguments: list[Node] = field(default_factory=list)

    def __init__(self, expression: Node, arguments: list[NodeLike] | None = None):
        self.expression = expression
        if arguments is None:
            arguments = []
        self.arguments = [convert_to_node(arg) for arg in arguments]


@dataclass
class PropertyAccessExpression(Node):
    """e.g. my_obj.primary

    Usage::

        PropertyAccessExpression(
            PropertyAccessExpression(
                Identifier("my_obj"),
                Identifier("property"),
            ),
            Identifier("nested"),
        )

        > my_obj.property.nested
    """

    expression: Node
    name: Node


@dataclass
class ElementAccessExpression(Node):
    """e.g. my_obj["key"], my_array[5] etc

    Usage::

        ElementAccessExpression(ElementAccessExpression(Identifier("my_obj"), "my key"), 5)

        > my_obj["my key"][5]
    """

    expression: Node
    argument_expression: Node | Literal


@dataclass
class TemplateExpression(Node):
    """e.g. ``${my_var} ${another_var}``

    Usage::

        TemplateExpression(
            [StringLiteral("Hello my name is "), Identifier("name"), ". What's yours?"]
        )

        > `Hello my name is ${name}. What's yours?`
    """

    children: Sequence[Node | str]


@dataclass
class SingleLineComment(Node):
    comment_text: str


@dataclass
class MultiLineComment(Node):
    comment_text: str


@dataclass
class NewExpression(Node):
    expression: Node
    arguments: Sequence[NodeLike] = field(default_factory=list)


@dataclass
class Block(Node):
    """Useful for ArrowFunction if not returning a single expression"""

    statements: list[Node]


@dataclass
class ArrowFunction(Node):
    #: Any parameters to the function
    parameters: list[Parameter]
    #: The body as either a single expression valid for Arrow functions or a ``Block`` node
    body: Node


@dataclass
class JsxAttribute(Node):
    name: Identifier | StringLiteral
    initializer: Node


@dataclass
class JsxSpreadAttribute(Node):
    expression: Identifier


@dataclass
class JsxText(Node):
    value: str


@dataclass
class JsxExpression(Node):
    expression: Node | None


@dataclass
class JsxElement(Node):
    tag_name: Identifier | StringLiteral
    attributes: Sequence[JsxAttribute | JsxSpreadAttribute]
    children: list[Union[JsxText, JsxExpression, "JsxElement"]]


def construct_object_property_key(
    value: AcceptedPropertyKeyType,
) -> Identifier | NumericLiteral | StringLiteral:
    """Construct node to use for a property key

    If ``value`` is numeric will return ``NumericLiteral``
        e.g. ``{ 5: "five" }``
    If ``value`` is a string will return ``Identifier`` if it's a valid identifier otherwise ``StringLiteral``
        e.g. ``{ test: "test" }`` vs ``{ "contains space": true }``

    Otherwise, returns ``Identifier``
    """
    if isinstance(value, (Identifier, NumericLiteral, StringLiteral)):
        return value
    if isinstance(value, (int, float)):
        return NumericLiteral(value)
    if isinstance(value, str):
        try:
            return Identifier(value)
        except ValueError:
            return StringLiteral(value)
    raise ValueError(f"Unknown property key type {type(value)}, value {value}")


def convert_literal(value: str | int | bool | float | None):
    """Helper to convert a native python value into a node"""
    if value is None:
        return NullKeyword()
    if isinstance(value, bool):
        return BooleanLiteral(value)
    if isinstance(value, (int, float)):
        return NumericLiteral(value)
    if issubclass(type(value), str) or isinstance(value, Promise):
        # ^ Promise is to handle lazy strings
        return StringLiteral(str(value))
    raise ValueError(f"Unknown literal type {type(value)}")


class UnconvertibleValueException(Exception):
    def __init__(self, value):
        super().__init__(f"Do not know how to convert {value} (type {type(value)}")
        self.value = value


def convert_to_node(value: NodeLike, convert_unknown: Callable[[NodeLike], Node] | None = None) -> Node:
    """Helper to convert a native python value into a node"""
    if isinstance(value, Node):
        return value
    if isinstance(value, dict):
        return ObjectLiteralExpression(
            [
                ObjectProperty(construct_object_property_key(key), convert_to_node(v, convert_unknown))
                for key, v in value.items()
            ]
        )
    if isinstance(value, (list, tuple)):
        return ArrayLiteralExpression([convert_to_node(v, convert_unknown) for v in value])
    try:
        return convert_literal(value)
    except ValueError:
        pass
    if convert_unknown:
        node = convert_unknown(value)
        if node:
            return node
    raise UnconvertibleValueException(value)


def create_accessor(path: list[str | int | PropertyAccessExpression | Identifier | NumericLiteral]):
    """Helper to create an accessor based on a path

    Will use PropertyAccessExpression or ElementAccessExpression based on whether the value is
    valid Identifier or not.

    e.g. passing ``["palette", "primary", 500]`` generates::

        ElementAccessExpression(
            PropertyAccessExpression(Identifier('palette'), Identifier('primary')),
            500
        )
    """
    if len(path) < 2:
        raise ValueError("path must have at least 2 elements")
    el = path[0]
    if not isinstance(el, (PropertyAccessExpression, Identifier, ElementAccessExpression)):
        raise ValueError(
            "first element of path must be PropertyAccessExpression, Identifier or ElementAccessExpression"
        )
    accessor: PropertyAccessExpression | Identifier | ElementAccessExpression = el
    for part in path[1:]:
        try:
            if isinstance(part, NumericLiteral):
                accessor = ElementAccessExpression(accessor, part)
            elif isinstance(part, int):
                accessor = ElementAccessExpression(accessor, NumericLiteral(int(part)))
            else:
                if not isinstance(part, Node):
                    identifier: Node = Identifier(part)
                else:
                    identifier = part
                accessor = PropertyAccessExpression(accessor, identifier)
        except InvalidIdentifier:
            accessor = ElementAccessExpression(accessor, part)
    return accessor
