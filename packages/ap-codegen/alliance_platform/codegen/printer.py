import contextlib
import dataclasses
from functools import wraps
import json
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Callable
from typing import Sequence

from django.conf import settings
from django.utils.html import escape

from .settings import ap_codegen_settings
from .typescript import ArrayLiteralExpression
from .typescript import ArrowFunction
from .typescript import AsExpression
from .typescript import AsyncKeyword
from .typescript import Block
from .typescript import BooleanLiteral
from .typescript import CallExpression
from .typescript import ElementAccessExpression
from .typescript import ExportKeyword
from .typescript import FunctionDeclaration
from .typescript import Identifier
from .typescript import ImportDeclaration
from .typescript import ImportDefaultSpecifier
from .typescript import ImportSpecifier
from .typescript import JsxAttribute
from .typescript import JsxElement
from .typescript import JsxExpression
from .typescript import JsxText
from .typescript import Modifier
from .typescript import MultiLineComment
from .typescript import NewExpression
from .typescript import Node
from .typescript import NodeLike
from .typescript import NullKeyword
from .typescript import NumericLiteral
from .typescript import ObjectLiteralExpression
from .typescript import ObjectProperty
from .typescript import Parameter
from .typescript import PropertyAccessExpression
from .typescript import ReturnStatement
from .typescript import SingleLineComment
from .typescript import SpreadAssignment
from .typescript import StringLiteral
from .typescript import TemplateExpression
from .typescript import TypeReference
from .typescript import VariableDeclaration
from .typescript import VariableDeclarator
from .typescript import convert_to_node

# Useful reference: https://babeljs.io/docs/en/babel-types


# TODO: Should add a base Printer and TypescriptSourceFileWriter class


def push_node_stack(method):
    """Pushes a node onto the node stack before calling the method and pops it after.

    This is done as a decorator to avoid needing to wrap and indent the entire ``print`` method which is already
    very large.
    """

    @wraps(method)
    def wrapper(self: "TypescriptPrinter", node: NodeLike, *args, **kwargs):
        self.node_stack.append(node)
        try:
            result = method(self, node, *args, **kwargs)
        finally:
            self.node_stack.pop()
        return result

    return wrapper


def print_comments(method):
    """For any node that has leading or trailing comments print them out before or after the node code.

    Intended to decorate the ``print`` method on ``TypescriptPrinter``. This is a decorator to avoid needing to
    concatenate strings within ``print`` which is already very large. Comments are a special case in that they
    apply generically to many nodes.
    """

    @wraps(method)
    def wrapper(self: "TypescriptPrinter", node: NodeLike, *args, **kwargs):
        result = method(self, node, *args, **kwargs)
        if isinstance(node, Node) and (not isinstance(node, JsxElement) or not self.jsx_transform):
            if node.leading_comments:
                result = self._print_comments(node.leading_comments) + "\n" + result
                if self.parent_node():
                    result = "\n" + result
            if node.trailing_comments:
                result = result + "\n" + self._print_comments(node.trailing_comments)
                if len(self.node_stack) > 1:
                    # Only do this if not the root node
                    result += "\n"
        return result

    return wrapper


default_jsx_transform = PropertyAccessExpression(
    Identifier("React"),
    Identifier("createElement"),
)


class TypescriptPrinter:
    """Print out code for the specified node

    NOTE: This does not generate nicely formatted code - it's expected the code will be passed through prettier.
    """

    #: Path any imports are relative to. Only used if a :class:`~pathlib.Path` is received - if a string is encountered it used directly
    relative_to_path: Path
    #: Function used to resolve the URL to use for an import. This can be used to do things like resolve it to a dev server URL or to a built file. If not provided import source is used as is.
    resolve_import_url: Callable[[Path | str], str] | None
    #: How to treat JSX elements. If specified, JSX elements will be transformed to the equivalent of ``React.createElement`` calls.
    #: The specific function called is identified by ``jsx_transform``, but the relevant import must be added manually.
    jsx_transform: Node | None
    #: Current node stack for printing. As each node is printed it is pushed onto this stack. This can be used to determine the parent node of the current node.
    node_stack: list[NodeLike]

    def __init__(
        self,
        relative_to_path: Path | None = None,
        resolve_import_url: Callable[[Path | str], str] | None = None,
        jsx_transform: Node | None = default_jsx_transform,
    ):
        if relative_to_path is None:
            relative_to_path = ap_codegen_settings.JS_ROOT_DIR
        self.relative_to_path = relative_to_path.parent if relative_to_path.is_file() else relative_to_path
        self.resolve_import_url = resolve_import_url
        self.jsx_transform = jsx_transform
        self.node_stack = []

    def _format_literal(self, value: str | int | float | bool):
        """Format a literal for printing

        For strings, this will escape them and wrap them in quotes. For booleans, this will convert them to 'true' or 'false'.
        Numeric values will be converted to strings.
        """
        if isinstance(value, str):
            # use json.dumps to escape strings & quote them
            return json.dumps(
                value,
                # don't escape non-ascii. I added this specifically for generating code for React, e.g. '“I'm in a lquo;“' should
                # not end up as \u201cI'm in a lquo;\u201c
                ensure_ascii=False,
            )
        if isinstance(value, bool):
            return "true" if value else "false"
        return str(value)

    def _print_comments(self, comments: Sequence[SingleLineComment | MultiLineComment]):
        """Print comments according to the current context

        If within a JSX element, comments will be wrapped in curly braces and SingleLineComment cannot be used.
        """
        within_jsx = self.is_within_jsx()
        comment_strs: list[str] = []
        for comment in comments:
            if within_jsx and isinstance(comment, SingleLineComment):
                comment = MultiLineComment(comment.comment_text)
            comment_str = self.print(comment)
            if within_jsx:
                comment_str = f"{{{comment_str}}}"
            comment_strs.append(comment_str)
        return "\n".join(comment_strs)

    def parent_node(self):
        """Return the parent node of the current node being processed by ``print``. This only makes sense when called from within ``print``.

        This can be used to determine what to do with a node conditionally based on its parent.
        """
        if len(self.node_stack) >= 2:
            return self.node_stack[-2]
        return None

    @contextlib.contextmanager
    def _push_node(self, node: NodeLike):
        """Like ``push_node_stack``, but as a context manager.

        This is useful when a node is being unwrapped within ``print``, as is the case with ``JSXAttribute``"""
        self.node_stack.append(node)
        try:
            yield
        finally:
            self.node_stack.pop()

    @push_node_stack
    @print_comments
    def print(self, node: NodeLike) -> str:  # noqa: T202
        """Recursively print the code for the specified ``node``"""
        if isinstance(node, JsxText) or isinstance(node, StringLiteral) and self.is_within_jsx():
            if self.jsx_transform:
                return self._format_literal(node.value)
            if node.value != escape(node.value):
                # If escaping is needed, use a JSX expression. For example, if the string is "Hello <World>" then
                # this will be printed as {"Hello <World>"}
                return f"{{{self._format_literal(node.value)}}}"
            return node.value
        if isinstance(node, JsxExpression):
            value = ""
            if node.expression is not None:
                value = self.print(node.expression)
            prefix = ""
            suffix = ""
            if node.leading_comments:
                prefix = self.print(node.leading_comments)
            if node.trailing_comments:
                suffix = self.print(node.trailing_comments)
            if self.jsx_transform:
                return f"{prefix}{value}{suffix}"
            return f"{{{prefix}{value}{suffix}}}"
        if isinstance(node, JsxElement):
            if self.jsx_transform:
                # Copy comments from the node to the tag name when using JSX transform
                tag_name = dataclasses.replace(
                    node.tag_name,
                    leading_comments=node.leading_comments,
                    trailing_comments=node.trailing_comments,
                )
                element_args: list[NodeLike] = [
                    tag_name,
                    ObjectLiteralExpression(
                        [
                            ObjectProperty(attr.name, attr.initializer)
                            if isinstance(attr, JsxAttribute)
                            else SpreadAssignment(attr.expression)
                            for attr in node.attributes
                        ]
                    ),
                    *node.children,
                ]
                return self.print(
                    CallExpression(
                        self.jsx_transform,
                        element_args,
                    )
                )
            attrs = []
            for attr in node.attributes:
                with self._push_node(attr):
                    if isinstance(attr, JsxAttribute):
                        # if attr is e.g. "aria-label" use that as is. Otherwise will be an Identifier.
                        name = (
                            attr.name.value if isinstance(attr.name, StringLiteral) else self.print(attr.name)
                        )
                        # if string use form 'name="value"', otherwise use form 'name={value}'
                        if isinstance(attr.initializer, StringLiteral):
                            attrs.append(f"{name}={self._format_literal(attr.initializer.value)}")
                        else:
                            attrs.append(f"{name}={{{self.print(attr.initializer)}}}")
                    else:
                        attrs.append(f"{{...{self.print(attr.expression)}}}")
            attrs_str = ""
            if attrs:
                attrs_str = " " + " ".join(attrs)
            tag_name_str = (
                node.tag_name.value if isinstance(node.tag_name, StringLiteral) else self.print(node.tag_name)
            )
            if node.children:
                return f"<{tag_name_str}{attrs_str}>{''.join(self.print(child) for child in node.children)}</{tag_name_str}>"
            return f"<{tag_name_str}{attrs_str} />"

        if isinstance(node, VariableDeclaration):
            return self.apply_modifiers(
                " ".join(
                    [node.kind, ", ".join(self.print(declaration) for declaration in node.declarations)]
                ),
                node.modifiers,
                node,
            )
        if isinstance(node, (VariableDeclarator, Parameter)):
            if node.init:
                return " ".join([self.print(node.name), "=", self.print(node.init)])
            return self.print(node.name)
        if isinstance(node, Identifier):
            return node.name
        if isinstance(node, (NumericLiteral, BooleanLiteral, StringLiteral)):
            return self._format_literal(node.value)
        if isinstance(node, ImportSpecifier):
            if node.imported == node.local:
                return self.print(node.imported)
            return f"{self.print(node.imported)} as {self.print(node.local)}"
        if isinstance(node, ImportDeclaration):
            default_specifier = node.get_default_specifier()
            named_specifiers = [
                self.print(specifier)
                for specifier in sorted(node.specifiers, key=lambda x: x.local.name)
                if specifier != default_specifier
            ]
            named_specifiers_code = f" {{ {', '.join(named_specifiers)} }}"
            if isinstance(node.source, Path):
                source = "./" + str(node.source.relative_to(self.relative_to_path))
            else:
                source = node.source
            if self.resolve_import_url:
                source = self.resolve_import_url(source)
            if default_specifier:
                return (
                    f"import {self.print(default_specifier.local)},{named_specifiers_code} from '{source}';"
                )
            return f"import{named_specifiers_code} from '{source}';"

        if isinstance(node, ObjectProperty):
            # If same name use shortcut, e.g. { Button } instead of { Button: Button }
            if node.name == node.init and isinstance(node.name, Identifier):
                return self.print(node.name)
            return f"{self.print(node.name)}: {self.print(node.init)}"

        if isinstance(node, SpreadAssignment):
            return f"...{self.print(node.expression)}"

        if isinstance(node, ObjectLiteralExpression):
            values = []
            for prop in node.properties:
                values.append(self.print(prop))
            return "{" + ", ".join(values) + "}"

        if isinstance(node, ArrayLiteralExpression):
            values = []
            for el in node.elements:
                values.append(self.print(el))
            return "[" + ", ".join(values) + "]"

        if isinstance(node, FunctionDeclaration):
            params = ", ".join(self.print(param) for param in node.parameters)
            statements = ";\n".join(self.print(statement) for statement in node.statements)
            return self.apply_modifiers(
                f"function {self.print(node.name)}({params}) {{\n  {statements};\n}}",
                node.modifiers,
                node,
            )
        if isinstance(node, ReturnStatement):
            return f"return {self.print(node.expression)}"

        if isinstance(node, CallExpression):
            args: list[str] = []
            for arg in node.arguments:
                code = self.print(arg)
                if isinstance(arg, SingleLineComment):
                    args.append(f"\n{code}\n")
                else:
                    args.append(code)
            args_str = ", ".join(args)
            return f"{self.print(node.expression)}({args_str})"

        if isinstance(node, AsExpression):
            return f"{self.print(node.expression)} as {self.print(node.type_annotation)}"

        if isinstance(node, TypeReference):
            # TODO: need to support type arguments - but this should be based on target. e.g. for code in browser we
            # wouldn't include this, but for codegen ViewModel classes we would.
            return self.print(node.name)

        if isinstance(node, PropertyAccessExpression):
            return f"{self.print(node.expression)}.{self.print(node.name)}"

        if isinstance(node, ElementAccessExpression):
            return f"{self.print(node.expression)}[{self.print(node.argument_expression)}]"

        if isinstance(node, TemplateExpression):
            pieces = []
            for child in node.children:
                if not isinstance(child, Node):
                    child = convert_to_node(child)
                if isinstance(child, StringLiteral):
                    pieces.append(child.value)
                else:
                    pieces.append(f"${{{self.print(child)}}}")
            return f"`{''.join(pieces)}`"

        if isinstance(node, SingleLineComment):
            lines = "\n// ".join(node.comment_text.split("\n"))
            return f"// {lines}"

        if isinstance(node, MultiLineComment):
            return f"/* {node.comment_text} */"

        if isinstance(node, NullKeyword):
            return "null"

        if isinstance(node, NewExpression):
            return (
                f"new {self.print(node.expression)}({', '.join(self.print(arg) for arg in node.arguments)})"
            )

        if isinstance(node, Block):
            statements = ";\n".join(self.print(statement) for statement in node.statements)
            return f"{{\n{statements}\n}}"

        if isinstance(node, ArrowFunction):
            params = ", ".join(self.print(param) for param in node.parameters)
            return f"({params}) => {self.print(node.body)}"

        if not isinstance(node, Node):
            # as a convenience allow converting native objects. This avoids tedium like wrapping
            # strings with StringLiteral() etc
            return self.print(convert_to_node(node))

        raise NotImplementedError(f"Don't know how to print {node.__class__.__name__}")

    def apply_modifiers(self, code: str, modifiers: list[Modifier], node: Node):
        """Apply some modifiers (e.g. export or async keywords)

        This can change e.g. `function myFunc()` to `export async myFunc()`
        """
        prefix = ""
        for modifier in modifiers:
            if isinstance(modifier, ExportKeyword):
                if prefix:
                    raise ValueError("ExportModifier must be the first modifier")
                prefix += "export "
                if modifier.is_default:
                    if not isinstance(node, (Identifier, FunctionDeclaration)):
                        # TODO: You can only default export an expression, function or class
                        # Expand this list as add more nodes
                        raise ValueError(f"Can't default export {node}")
                    prefix += "default "
            elif isinstance(modifier, AsyncKeyword):
                prefix += "async "
            else:
                raise NotImplementedError(f"Do not know how to handle {modifier}")

        return prefix + code

    def is_within_jsx(self):
        """Return True if the current node is within a JSX element. This can be used to determine how to print certain nodes.

        For example, a ``StringLiteral`` within a JSX element would be ``<Element>Text</Element>``, but outside would be ``"Text"``.
        """
        return isinstance(self.parent_node(), JsxElement)


class TypescriptSourceFileWriter:
    """Source file writer with some helpers

    Helps add imports to nodes without needing to manually track duplicates etc. Use ``resolve_import`` to get a valid
    ``Identifier`` to use.

    Usage::

        with TypescriptSourceFileWriter(path) as sfw:
            sfw.add_node(
                FunctionDeclaration(
                    Identifier("identity"),
                    [Parameter(Identifier("value"))],
                    [
                        ReturnStatement(
                           Identifier("value")
                        )
                    ],
                )
            )

        # Will write source to ``path``:
        #
        # function identity(value) {
        #     return value;
        # }

    If no ``path`` is supplied then nothing will be written automatically. In that case retrieve the code with ``get_code``:

    Usage::

        with SourceFileWrite() as sfw:
            sfw.add_node(...)
            print(sfw.get_code())

    The ``resolve_import_url`` argument can be used to resolve imports to the correct location based on usage::

        bundler = get_bundler()
        with TypescriptSourceFileWriter(resolve_import_url=bundler.get_url) as sfw:
            # any imports will be resolved by the bundler
    """

    #: Path any imports are relative to. Passed to :class:`~alliance_platform.frontend.codegen.printer.TypescriptPrinter`.
    path_base: Path | None
    #: Any imports that are required. This is based on calls to ``resolve_import``. This imports will be included in the generated code.
    required_imports: list[ImportDeclaration]
    #: The nodes that will be included in the generated code.
    nodes: list[Node]
    #: Function used to resolve the URL to use for an import. This can be used to do things like resolve it to a dev server URL or to a built file.
    resolve_import_url: Callable[[Path | str], str] | None
    #: Nodes that will be included at the start of the generated code. This is useful for adding header comments.
    leading_nodes: list[Node]

    used_identifiers: list[str]

    #: How to treat JSX elements. If specified, JSX elements will be transformed to the equivalent of ``React.createElement`` calls.
    #: The specific function called is identified by ``jsx_transform``, but the relevant import must be added manually.
    jsx_transform: Node | None

    def __init__(
        self,
        path: Path | None = None,
        path_base: Path | None = None,
        resolve_import_url: Callable[[Path | str], str] | None = None,
        jsx_transform: Node | None = default_jsx_transform,
    ):
        """

        Args:
            path: If specified, and ``SourceFileWrite`` used as a context then the generated code will be written to this file
            path_base: Path any imports are relative to
            resolve_import_url: Function used to resolve the URL to use for an import. This can be used to do things like resolve
                it to a dev server URL or to a built file. If not provided import source is used as is.
        """
        self.path = path
        self.resolve_import_url = resolve_import_url
        self.path_base = path_base or path or settings.PROJECT_DIR
        self.nodes = []
        self.leading_nodes = []
        self.required_imports = []
        self.used_identifiers = []
        self.jsx_transform = jsx_transform

    def resolve_import(
        self, source: str | Path, specifier: ImportSpecifier | ImportDefaultSpecifier, import_order_priority=0
    ) -> Identifier:
        """
        Resolve an import. This will make sure the import is included in the final source (while not conflicting with
        other imports) and will return the ``Identifier`` to use to reference it.

        Args:
            source: The source file to import from
            specifier: The specifier for what to import from ``source``

        Returns:
            The ``Identifier`` that can be used to reference the import.
        """
        existing_import = None
        for imp in self.required_imports:
            if imp.source == source:
                existing = imp.get_specifier(specifier)
                if existing:
                    return existing.local
                existing_import = imp
        if not existing_import:
            existing_import = ImportDeclaration(source, import_order_priority=import_order_priority)
            self.required_imports.append(existing_import)
            # Maintain sort order so code generated is consistent, makes easier for tests
            self.required_imports.sort(key=lambda imp: [-imp.import_order_priority, str(imp.source)])
        existing_import.add_specifier(specifier)
        local_name = specifier.local.name
        count = 0
        while specifier.local.name in self.used_identifiers:
            specifier.local = Identifier(f"{local_name}{count}")
            count += 1
        self.used_identifiers.append(specifier.local.name)
        return specifier.local

    def add_node(self, node: Node):
        """Add a node to be included in the code"""
        self.nodes.append(node)

    def add_leading_node(self, node: Node):
        self.leading_nodes.append(node)

    def __enter__(self):
        return self

    def get_code(self) -> str:
        """Returns the printed code"""
        printer = TypescriptPrinter(self.path_base, self.resolve_import_url, jsx_transform=self.jsx_transform)
        code = [printer.print(node) for node in self.leading_nodes]
        for imp in self.required_imports:
            code.append(printer.print(imp))
        if code:
            code.append("\n")
        for node in self.nodes:
            code.append(printer.print(node))
            code.append("\n")

        return "\n".join(code)

    def __exit__(self, exc_type, exc_val, exc_tb):
        # If a path has been specifier write the generated code to it
        if self.path:
            with NamedTemporaryFile("w", suffix=".tsx") as temp:
                temp_file_path = Path(temp.name)
                temp.write(self.get_code())
                temp.flush()
                # config = get_codegen_config()
                # config.post_process([CodeGenFile(temp_file_path, self.path)])
                contents = temp_file_path.read_text()
                if not self.path.exists() or self.path.read_text("utf8") != contents:
                    self.path.write_text(contents, "utf8")
