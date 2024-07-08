from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import math
from pathlib import Path
from typing import Any
from typing import cast
import warnings

from alliance_platform.codegen.printer import TypescriptPrinter
from alliance_platform.codegen.printer import TypescriptSourceFileWriter
from alliance_platform.codegen.typescript import CallExpression
from alliance_platform.codegen.typescript import FunctionDeclaration
from alliance_platform.codegen.typescript import Identifier
from alliance_platform.codegen.typescript import ImportDefaultSpecifier
from alliance_platform.codegen.typescript import ImportSpecifier
from alliance_platform.codegen.typescript import InvalidIdentifier
from alliance_platform.codegen.typescript import JsxAttribute
from alliance_platform.codegen.typescript import JsxElement
from alliance_platform.codegen.typescript import MultiLineComment
from alliance_platform.codegen.typescript import Node as TypescriptNode
from alliance_platform.codegen.typescript import PropertyAccessExpression
from alliance_platform.codegen.typescript import RawNode
from alliance_platform.codegen.typescript import ReturnStatement
from alliance_platform.codegen.typescript import StringLiteral
from alliance_platform.codegen.typescript import UnconvertibleValueException
from alliance_platform.codegen.typescript import convert_to_node
from allianceutils.template import build_html_attrs
from allianceutils.template import is_static_expression
from allianceutils.template import parse_tag_arguments
from allianceutils.template import resolve
from allianceutils.util import camelize as camelize_util
from allianceutils.util import underscore_to_camel
from django import template
from django.core.exceptions import ImproperlyConfigured
from django.forms.models import ModelChoiceIteratorValue
from django.template import Context
from django.template import Node
from django.template import NodeList
from django.template import Origin
from django.template import TemplateSyntaxError
from django.template.base import UNKNOWN_SOURCE
from django.template.base import FilterExpression
from django.template.base import TextNode
from django.utils.functional import LazyObject
from django.utils.html import format_html
from django.utils.safestring import SafeString
from django.utils.safestring import mark_safe

from ..bundler import get_bundler
from ..bundler.base import BaseBundler
from ..bundler.base import ResolveContext
from ..bundler.context import BundlerAsset
from ..bundler.context import BundlerAssetContext
from ..bundler.ssr import ImportDefinition
from ..bundler.ssr import SSRItem
from ..bundler.ssr import SSRSerializable
from ..bundler.ssr import SSRSerializerContext
from ..bundler.vite import ViteBundler
from ..forms.renderers import form_input_context_key
from ..html_parser import HtmlAttributeTemplateNodeList
from ..html_parser import convert_html_string
from ..html_parser import html_replacement_placeholder_template
from ..prop_handlers import CodeGeneratorNode
from ..prop_handlers import ComponentProp
from ..settings import ap_frontend_settings
from ..util import transform_attribute_names

register = template.Library()

# Used to ensure that the import for renderComponent comes first in the generated code. This is so
# any config related items get loaded first.
HIGHEST_PRIORITY_IMPORT = 100


def resolve_prop(value: Any, node: ComponentNode, context: Context) -> ComponentProp | Any:
    """Resolve the prop class to use for the specified ``value``

    To add new handlers, add class to the list set in  ``settings.REACT_PROP_HANDLERS``
    """
    if isinstance(value, dict):
        return {k: resolve_prop(v, node, context) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return list(resolve_prop(v, node, context) for v in value)
    if isinstance(value, ModelChoiceIteratorValue):
        return resolve_prop(value.value, node, context)  # type: ignore[attr-defined] # It has this value but no type info
    if isinstance(value, LazyObject):
        # unwrap lazy objects
        return value.__reduce__()[1][0]
    for handler in ap_frontend_settings.REACT_PROP_HANDLERS:
        if handler.should_apply(value, node, context):
            return handler(value, node, context)
    return value


@register.tag("component")
def component(parser: template.base.Parser, token: template.base.Token):
    """Render a React component with the specified props

    See the templatetags.rst docs for more details.
    """
    return parse_component_tag(parser, token)


class NestedComponentProp(ComponentProp):
    """
    This is used to describe a nested component rendered within the ``component`` tag::

        {% component "div" %}
            {% component "button" disabled %}
                Click Me
            {% endcomponent %}
        {% endcomponent %}

    See ``revivers.Component`` in ``ssrJsonRevivers.tsx`` for how this is handled in SSR.
    """

    def __init__(self, value: ComponentNode, node: ComponentNode, context: Context):
        super().__init__(value, node, context)
        self.component = value
        self.props = value.resolve_props(context)

    def __repr__(self):
        return f"NestedComponentProp({self.component.source}, {self.props})"

    def get_tag(self):
        return "Component"

    def get_representation(self, ssr_cache):
        return {
            # This value will be resolved by revivers.ComponentImport
            "component": self.component.source,
            "props": self.props,
        }

    def generate_code(self, generator: ComponentSourceCodeGenerator):
        return generator.create_jsx_element_node(self.component, self.props)


PropType = str | float | int | list["PropType"] | tuple["PropType"] | dict[str, "PropType"] | ComponentProp
PropsType = dict[str, PropType]


class ComponentProps(SSRSerializable):
    """Stores the props for a given component and handles serialization"""

    props: PropsType

    def __init__(self, props: PropsType):
        # Copy as ``add_prop`` modifies
        self.props = props.copy()
        # Remove form input context key if present - this can't be used beyond this point and exists only as
        # a workaround to pass extra context to widgets, see FormInputContextRenderer
        if form_input_context_key in self.props:  # type: ignore[comparison-overlap]
            self.props.pop(form_input_context_key)  # type: ignore[call-overload]

    def __repr__(self):
        return f"ComponentProps({self.props})"

    def _serialize_prop(self, value: PropType, ssr_context: SSRSerializerContext):
        if isinstance(value, dict):
            return {k: self._serialize_prop(v, ssr_context) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [self._serialize_prop(v, ssr_context) for v in value]
        if isinstance(value, ComponentProp):
            return value.serialize(ssr_context)
        if isinstance(value, ComponentProps):
            return value.serialize(ssr_context)
        return value

    def serialize(self, ssr_context: SSRSerializerContext):
        """Serialize props to Dict that can then be JSON encoded

        Handles conversion of :class:`~alliance_platform.frontend.prop_handlers.ComponentProp` instances.

        Args:
            options: The options to use when serializing. In particular the options tell serialization how to handle
                resolving imports when dealing with nested components.
        """
        return self._serialize_prop(self.props, ssr_context)

    def has_prop(self, prop_name: str):
        return prop_name in self.props

    def add_prop(self, prop_name: str, value: PropType):
        """Add a new prop"""
        self.props[prop_name] = value

    def update(self, props: dict):
        self.props.update(props)

    def pop(self, prop_name: str, default_value):
        return self.props.pop(prop_name, default_value)


class ComponentSourceBase:
    """Base class used to identify what the source of a component is

    This is used to differentiate between components that need to be imported vs common
    components (e.g. div, button etc).
    """

    def as_tag(self):
        """Used in debugging. Should return the name of the component as it would be used in JSX"""
        raise NotImplementedError


@dataclass(frozen=True)
class CommonComponentSource(ComponentSourceBase, SSRSerializable):
    """Used for things that require no imports, e.g. standard DOM components

    See https://beta.reactjs.org/reference/react-dom/components/common for origin of
    terminology 'common component'.
    """

    name: str

    def serialize(self, ssr_context: SSRSerializerContext):
        return self.name

    def as_tag(self):
        return self.name


@dataclass(frozen=True)
class ImportComponentSource(ImportDefinition, ComponentSourceBase):
    """
    Used to identify a Component that needs to be imported from a module

    This differs from :class:`~alliance_platform.frontend.templatetags.react.CommonComponentSource` which is just
    a string (e.g. 'div' or 'button') and requires no import to work.
    """

    #: If specified, this is the name of the property to use from the import. e.g. "Table.Cell" would use the Cell property from Table.
    property_name: str | None = None

    def get_relative_path(self):
        return self.path.relative_to(get_bundler().root_dir)

    def get_tag(self):
        return "ComponentImport"

    def get_representation(self, context: SSRSerializerContext):
        return {
            "import": context.add_import(self),
            "propertyName": self.property_name,
        }

    def as_tag(self):
        if self.property_name:
            return f"{self.import_name}.{self.property_name}"
        return self.import_name


class NestedComponentPropAccumulator:
    """
    Used to accumulate nested components during render, and then applying the accumulated components to
    a final rendered value to return the children to use in a component props. This is easier to understand through an
    example (the redundant ``if`` is just to demonstrate a nested non-component tag)::

        {% component "div" %}
            {% if True %}{% component "strong" %}Test{% endcomponent %}{% endif %} Example
        {% endcomponent %}

    As a React element this would be::

        <div><strong>Test Component</strong></div>

    As django template nodes::

        ComponentNode(
            "div",
            [IfNode((Condition(True), ComponentNode("strong", [TextNode("Test")]), TextNode("Example")]
        )

    All the children of a node will be (by default) rendered to a string. We can handle direct ``ComponentNode``
    children by inspecting the type (we do exactly this in ``resolve_prop`` as an optimisation). For the general
    case where the ``ComponentNode`` could be anywhere down the tree we render as normal. ``ComponentNode.render``
    checks if it's within another component by calling ``NestedComponentPropAccumulator.get_current(context)``. If
    it is it calls ``add`` and returns the string. This will end up rendering something like::

        __NestedComponentPropAccumulator__prop__0 Example

    Internally ``NestedComponentPropAccumulator`` will store the actual prop::

        props = {
            "__NestedComponentPropAccumulator__prop__0": NestedComponentProp(
                ComponentNode("strong", ...),
                ComponentProps({"children": ["Test"]})
            )
        }

    Then when ``apply`` is called it will be passed the rendered string::

        "__NestedComponentPropAccumulator__prop__0 Example"

    And process that, returning a list that can be used as children for the component props::

        [
            NestedComponentProp(
                ComponentNode("strong", ...),
                ComponentProps({"children": ["Test"]})
            ),
            " Example"
        ]
    """

    #: Used internally to track where the current registry is stored in ``Context``
    context_key = "__NestedComponentPropAccumulator"
    #: The stored props as a mapping from the rendered placeholder string, to the ``NestedComponentProp``.
    props: dict[str, NestedComponentProp]
    #: The origin component node
    origin_node: ComponentNode

    @classmethod
    def get_current(cls, context: Context) -> NestedComponentPropAccumulator | None:
        """Get the current accumulator, if any

        This extracts the current accumulator instance from the template context. Returns ``None``
        if there is no active accumulator.
        """
        return context.get(cls.context_key, None)

    def __init__(self, context: Context, origin_node: ComponentNode):
        self.origin_node = origin_node
        self.context = context
        self.props = {}

    def __enter__(self):
        # push current context; matching pop is in ``__exit__``
        self.context.push()
        # store this instance in context
        self.context[self.context_key] = self
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.context.pop()

        # make sure apply was called
        if self.props:
            warnings.warn("NestedComponentPropAccumulator context exited without calling 'apply'")

    def add(self, prop: NestedComponentProp):
        """Add a prop to the accumulator

        This returns a string that should be rendered in the components place. It will then be
        handled in ``apply``.
        """
        if not isinstance(prop, NestedComponentProp):
            raise ValueError(
                "must be a NestedComponentProp; if you are passing ComponentNode wrap it in ComponentProp first"
            )

        key = f"{self.context_key}__prop__{len(self.props)}"
        self.props[key] = prop
        return key

    def apply(self, value: str):
        """Apply the accumulator props to ``value``.

        ``value`` will have placeholders for each prop that was accumulated. This method will
        return a list with each of those props in its correct position, surrounded by strings
        for all non-placeholder parts of ``value``.

        For example, given this value::

            "__NestedComponentPropAccumulator__prop__0 Example __NestedComponentPropAccumulator__prop__1 "

        This would be returned (details omitted)::

            [
                NestedComponentProp(...),
                " Example"
                NestedComponentProp(...),
            ]
        """

        # TODO: Not 100% sure about the behaviour below of stripping & excluding empty string - see how it goes.
        # There were definitely issues in _not_ doing this, but it's not clear if this is the right solution.
        children: list[NestedComponentProp | str] = []
        if self.props:
            prev_index = 0
            for placeholder, prop in self.props.items():
                index = value.find(placeholder)
                if index == -1:
                    warnings.warn(f"Unexpected: didn't find {placeholder} in string {value}")
                    continue
                if index > prev_index:
                    part = value[prev_index:index]
                    if part:
                        children.append(part)
                children.append(prop)
                prev_index = index + len(placeholder)
            value = value[prev_index:]
        if value:
            children += self.transform_string(value)
        self.props = {}

        return children

    def transform_string(self, child: str | NestedComponentProp):
        """Given a string, handle any necessary HTML conversions for React compatibility."""
        if isinstance(child, SafeString):
            nodes = convert_html_string(
                child,
                self.origin_node.origin,
            )
            processed = []
            for node in nodes:
                processed += self.apply(node.render(self.context) if isinstance(node, Node) else node)
            return processed
        return [child]


class ComponentSourceCodeGenerator:
    """Helper class to assist in generating source for a component tag

    This uses a ``TypescriptSourceFileWriter`` to generate the source code for a component tag but
    provides some additional helpers to make it easier to generate the source.

    The generated source code has two potential shapes depending on if ``requires_wrapper_component`` has been called.
    Without a wrapper component (in production the URLs would refer to built files)::

        import { TestComponent } from "http://localhost:5173/assets/frontend/src/components/TestComponent.tsx";
        import { renderComponent } from "http://localhost:5173/assets/frontend/src/renderComponent.tsx";

        renderComponent(
          document.querySelector("[data-djid='6126825472__1_3']"),
          TestComponent,
          {},
          "6126825472__1_3",
          true
        );

    With a wrapper component::

        import { TestComponent } from "http://localhost:5173/assets/frontend/src/components/TestComponent.tsx";
        import {
          createElement,
          renderComponent,
        } from "http://localhost:5173/assets/frontend/src/renderComponent.tsx";

        function Wrapper() {
          return createElement(TestComponent, {});
        }

        renderComponent(
          document.querySelector("[data-djid='6144913408__1_3']"),
          Wrapper,
          {},
          "6144913408__1_3",
          true
        );

    The second form is only required if one of the props needs to use a React hook (e.g. ``useViewModelCache``).
    """

    bundler: BaseBundler
    node: ComponentNode

    #: If a wrapper component is required. This is set by ``requires_wrapper_component``.
    _requires_wrapper_component: bool
    #: Tracks the name of all identifiers generated so far. This is used to ensure uniqueness.
    _used_identifiers: list[str]
    #: Used by ``create_jsx_element`` to detect when the template name changes so it can output a comment.
    _last_template_origin_name: str | None
    #: Used by ``create_jsx_element`` to track the specified value for the ``include_template_origin`` kwarg in the root node
    _last_include_template_origin: bool

    def __init__(self, node: ComponentNode):
        self.node = node
        self.bundler = node.bundler
        self._writer = TypescriptSourceFileWriter(
            resolve_import_url=self._resolve_import_url,
        )
        self._requires_wrapper_component = False
        self._used_identifiers = []
        self._last_template_origin_name = None
        self._last_include_template_origin = False

        # Resolve the import for createElement and use the returned Identifier for the jsx_transform
        self._writer.jsx_transform = self._writer.resolve_import(
            ap_frontend_settings.REACT_RENDER_COMPONENT_FILE,
            ImportSpecifier("createElement"),
            import_order_priority=HIGHEST_PRIORITY_IMPORT,
        )

    def _resolve_import_url(self, path: Path | str):
        path = self.bundler.validate_path(path, resolve_extensions=[".ts", ".tsx"])
        return self.bundler.get_url(path)

    def resolve_component_import(self, component: ComponentNode):
        """Resolve import to use for a component."""
        if isinstance(component.source, ImportComponentSource):
            # If we are dealing with an import resolve it using TypescriptSourceFileWriter - it will
            # return the Identifier that can safely be used. The actual URL used is set above to
            # resolve using self.blunder.get_url
            identifier = self._writer.resolve_import(
                str(component.source.get_relative_path()),
                (
                    ImportDefaultSpecifier(component.source.import_name)
                    if component.source.is_default_import
                    else ImportSpecifier(component.source.import_name)
                ),
            )
            if component.source.property_name:
                return PropertyAccessExpression(identifier, Identifier(component.source.property_name))
            return identifier
        if isinstance(component.source, CommonComponentSource):
            # Nothing to import - just reference the component as a string
            # e.g. "div"
            return StringLiteral(component.source.name)
        raise NotImplementedError(f"No support for {component.source}")

    def resolve_prop_import(
        self, path: str | Path, specifier: ImportSpecifier | ImportDefaultSpecifier, import_order_priority=0
    ):
        """This is a separate method so that we can track prop imports separately.

        Any custom prop that needs and import should call this method

        This is necessary as the imports for props depend on usage and can't be statically determined. As such, these
        are tracked separated and added to the dynamic dependencies of the component. This allows the ``BundlerContext``
        to check this assets will be available in production and raise an error if not.
        """
        self.node.add_dynamic_dependency(self.bundler.validate_path(path, resolve_extensions=[".ts", ".tsx"]))
        return self._writer.resolve_import(path, specifier, import_order_priority=import_order_priority)

    def requires_wrapper_component(self):
        """Indicate that a wrapper component is required to render this component. This is required when using hooks.

        ``ComponentProp`` instances can call this method to indicate that a wrapper component is required.
        """
        self._requires_wrapper_component = True

    def _codegen_prop(self, value: PropType):
        if isinstance(value, dict):
            return {k: self._codegen_prop(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [self._codegen_prop(v) for v in value]
        if isinstance(value, CodeGeneratorNode):
            return value.generate_code(self)
        if isinstance(value, ImportComponentSource):
            # This lets us pass through imports as props, for example to pass a component class itself as a prop to
            # another component
            return self.resolve_prop_import(
                value.path,
                (
                    ImportDefaultSpecifier(value.import_name)
                    if value.is_default_import
                    else ImportSpecifier(value.import_name)
                ),
            )
        return convert_to_node(value)

    def _create_jsx_key(self, key: str):
        """Not strictly accurate, but for our purposes it's better to not crash than generate strictly accurate JSX

        JSX is never used directly; it's always converted to React.createElement calls, so we can be a bit more
        flexible here as anything can technically be passed to `createElement`.
        """
        try:
            return StringLiteral(key.lower()) if "-" in key else Identifier(key)
        except InvalidIdentifier:
            return StringLiteral(key)

    def create_jsx_element_node(
        self, component: ComponentNode, resolved_props: ComponentProps, include_template_origin=None
    ):
        """
        Create a JSX element node for the specified component and props

        Note that this creates the representation of the component as a JSX element. The TypescriptPrinter will
        then convert it to code, either as JSX directly for debugging, or as React.createElement calls for code
        outputted to the browser (JSX can't be interpreted directly in the browser, but is very useful for debugging
        or test cases).

        Args:
            component: The component node to create the JSX element for
            resolved_props: The fully resolved props for the component
            include_template_origin: Whether to include a comment for each component indicating the template it was
                created from. Useful for debugging.

        Returns:
            A ``JsxElement`` that can be printed to code.
        """

        # If not specified, use the last value. This is useful for nested elements to use the value specified on the
        # root node.
        if include_template_origin is None:
            include_template_origin = self._last_include_template_origin
        last_include_template_origin = self._last_include_template_origin
        self._last_include_template_origin = include_template_origin

        # Track the template name so we know when it changes. This way we only output the template name when it changes.
        last_template_name = self._last_template_origin_name
        template_name = (
            component.origin.template_name.decode()
            if isinstance(component.origin.template_name, bytes)
            else component.origin.template_name
        )
        self._last_template_origin_name = template_name

        try:
            children = cast(
                list[NestedComponentProp | str] | str | NestedComponentProp,
                resolved_props.props.get("children", []),
            )
            attributes = [
                JsxAttribute(
                    self._create_jsx_key(key),
                    self._codegen_prop(prop),
                )
                for key, prop in resolved_props.props.items()
                if key != "children"
            ]
            jsx_children = [
                self._codegen_prop(child)
                for child in ([children] if not isinstance(children, list) else children)
            ]
            leading_comments = None
            if include_template_origin and template_name and template_name != last_template_name:
                leading_comments = [MultiLineComment(template_name)]
            return JsxElement(
                self.resolve_component_import(component),
                attributes,
                jsx_children,
                leading_comments=leading_comments,
            )
        except UnconvertibleValueException as e:
            raise ValueError(
                f"Do not know how to handle prop of type {type(e.value)}: {e.value}\n\n "
                "Either add a handler to ALLIANCE_PLATEFORM['FRONTEND']['REACT_PROP_HANDLERS'] or check the correct value is being passed in."
            )
        finally:
            self._last_template_origin_name = last_template_name
            self._include_template_origin = last_include_template_origin

    def generate_code(self, props: ComponentProps, container_id: str):
        jsx_element = self.create_jsx_element_node(self.node, props)

        # In some cases a wrapper component is needed, e.g. when using props that require hooks. This just wraps
        # the element in a wrapper function and returns the element. The props themselves may be a hook call, so we
        # don't have to specifically check for hooks here.
        if self._requires_wrapper_component:
            wrapper_id = Identifier("Wrapper")
            self._writer.add_node(
                FunctionDeclaration(
                    wrapper_id,
                    [],
                    [ReturnStatement(jsx_element)],
                )
            )
            component_id = wrapper_id
            jsx_element = JsxElement(component_id, [], [])
        self._writer.add_node(
            CallExpression(
                self._writer.resolve_import(
                    ap_frontend_settings.REACT_RENDER_COMPONENT_FILE,
                    ImportSpecifier("renderComponent"),
                    import_order_priority=HIGHEST_PRIORITY_IMPORT,
                ),
                [
                    CallExpression(
                        PropertyAccessExpression(
                            Identifier("document"),
                            Identifier("querySelector"),
                        ),
                        [RawNode(f"\"[data-djid='{container_id}']\"")],
                    ),
                    jsx_element,
                    container_id,
                    not self.node.ssr_disabled,
                ],
            )
        )
        return self._writer.get_code()

    def generate_identifier(self, name: str):
        """Generate a unique identifier for use in the generated code"""
        counter = 2
        original_name = name
        while name in self._used_identifiers:
            name = f"{original_name}{counter}"
            counter += 1
        self._used_identifiers.append(name)
        return Identifier(name)

    def add_leading_node(self, node: TypescriptNode):
        """Add a node that should be added to the top of the generated code."""
        self._writer.add_leading_node(node)


class OmitComponentFromRendering(Exception):
    """Raise this exception to indicate that the component should not be rendered.

    This can be used to indicate the component should not be rendered in certain circumstances, for example
    if a permission check is done to determine whether user can see certain content.
    """

    pass


class DeferredProp:
    """Represents a prop that should be deferred until the component is rendered.

    This is useful for cases where the prop is rendered outside the component, for example:

    .. code-block:: html

        {% url_with_perm "some-url" as url %}

        {% component "SomeComponent" url=url %}{% endcomponent %}

    In this case, the ``url`` prop is rendered outside the component and so needs to be deferred until the component
    is rendered so that things that need to happen in context work (e.g. raising ``OmitComponentFromRendering`` are caught).
    """

    def resolve(self, context: Context):
        raise NotImplementedError()


def _merge_strings(children: list[str | NestedComponentProp]) -> list[str | NestedComponentProp]:
    new_children: list[str | NestedComponentProp] = []
    current_str = ""
    for child in children:
        if isinstance(child, str):
            current_str += child
        else:
            if current_str:
                new_children += current_str.splitlines()
                current_str = ""
            new_children.append(child)
    if current_str:
        new_children += current_str.splitlines()
    return new_children


def process_component_children(children: list[str | NestedComponentProp]) -> list[str | NestedComponentProp]:
    """Process component children, reducing strings to match JSX behaviour

    This applies the following (from `React JSX docs <https://legacy.reactjs.org/docs/jsx-in-depth.html#string-literals-1>`_):

    * JSX removes whitespace at the beginning and ending of a line.
    * It also removes blank lines.
    * New lines adjacent to tags are removed;
    * New lines that occur in the middle of string literals are condensed into a single space.

    For our purposes the list contains either strings, or ``NestedComponentProp`` which indicates a 'tag' in the rules
    above.
    """
    processed_children: list[str | NestedComponentProp] = []
    current_str = ""

    # First combine adjacent strings
    children = _merge_strings(children)
    for i, item in enumerate(children):
        prev_is_str = isinstance(children[i - 1], str) if i - 1 >= 0 else None
        next_is_str = isinstance(children[i + 1], str) if i + 1 < len(children) else None
        if isinstance(item, str):
            if prev_is_str:
                item = item.lstrip()
            if next_is_str:
                item = item.rstrip()
            # Remove entirely blank lines
            if not item.strip():
                continue

            # Concatenate adjacent strings
            # This handled the condition: new lines that occur in the middle of string literals are condensed into a single space
            current_str += " " + item if current_str else item
        else:
            if current_str:
                processed_children.append(current_str)
                current_str = ""

            processed_children.append(item)
    if current_str:
        processed_children.append(current_str)
    return processed_children


# Used to identify children when processing them in resolve_props
class ChildrenList(list):
    pass


class ComponentNode(template.Node, BundlerAsset):
    """A template node used by :func:`~alliance_platform.frontend.templatetags.react.component`"""

    #: Any extra dependencies for this component. This comes from props used that may require imports, for example
    #: DateProp may require the date library be included.
    dynamic_dependencies: list[Path]

    container_tag: str | FilterExpression
    container_props: dict[str, Any]
    #: For tags that are parsed from raw HTML we can have instances where the attributes can't be resolved until
    #: the component is rendered. This is used to store those nodes and resolve them to props later.
    html_attribute_template_nodes: HtmlAttributeTemplateNodeList | None

    def __init__(
        self,
        origin: Origin,
        source: ComponentSourceBase,
        props: dict[str, Any],
        target_var=None,
        ssr_disabled: bool | FilterExpression = False,
        omit_if_empty: bool | FilterExpression = False,
        container_tag: str | FilterExpression = "dj-component",
        container_props: dict[str, Any] | None = None,
        html_attribute_template_nodes: HtmlAttributeTemplateNodeList | None = None,
    ):
        if not ap_frontend_settings.REACT_RENDER_COMPONENT_FILE:
            raise ImproperlyConfigured(
                "When using the `react` tag you must have `REACT_RENDER_COMPONENT_FILE` set in ALLIANCE_PLATFORM['FRONTEND'] settings"
            )
        if "children" in props:
            props["children"] = ChildrenList(props["children"])
        self.html_attribute_template_nodes = html_attribute_template_nodes
        self.container_tag = container_tag
        self.container_props = container_props or {}
        self.ssr_disabled = ssr_disabled or not get_bundler().is_ssr_enabled()
        self.source = source
        self.props = props
        self.target_var = target_var
        self.omit_if_empty = omit_if_empty
        # For the case where props=my_dict is passed
        self.extra_props = props.pop("props", None)
        self.dynamic_dependencies = []
        super().__init__(origin)

    def __repr__(self):
        return f"ComponentNode({self.source}, {self.props})"

    def add_dynamic_dependency(self, path: Path):
        """Track when a dynamic dependency is used.

        A dynamic dependency is JS file that can't be statically analyzed. For example, if a ``ComponentProp`` required
        an import (e.g. ``useViewModelCache`` for ``ViewModelProp``) then that would be a dynamic dependency. This lets
        us identify during dev imports that need to be explicitly included in the created bundle.
        """

        # If path is explicitly included in ``get_paths_for_bundling`` we don't have to worry about it as it
        # will always be included
        if path not in self.get_paths_for_bundling():
            self.dynamic_dependencies.append(path)

    def get_dynamic_paths_for_bundling(self) -> list[Path]:
        return self.dynamic_dependencies

    def get_paths_for_bundling(self) -> list[Path]:
        paths = [ap_frontend_settings.REACT_RENDER_COMPONENT_FILE]
        if isinstance(self.source, ImportComponentSource):
            paths.append(self.source.path)
        return paths

    def resolve_prop(self, value, context: Context):
        """Handles resolving values to a type that can be serialized

        If you add new :class:`~alliance_platform.frontend.prop_handlers.ComponentProp` there must a case here
        to convert values to the new type.
        """

        # Always handle this first, as ``ComponentNode`` is also a ``Node`` but shouldn't be rendered directly here
        if isinstance(value, ComponentNode):
            return NestedComponentProp(value, self, context)
        # In the case of raw HTML that is transformed with the ``convert_html_string`` function we need to handle
        # the case of a template node being used as a prop, e.g. ``<a href="{% url 'some-url' %}">``.
        if isinstance(value, Node):
            value = value.render(context)
        if isinstance(value, DeferredProp):
            value = value.resolve(context)
        if isinstance(value, (ChildrenList, NodeList)):
            children: list[str | NestedComponentProp] = []
            for child in value:
                if isinstance(child, ComponentNode):
                    # We could remove this branch - it's an optimisation of the below. We know the node type here
                    # directly so can avoid the extra work + string replacement that happens below.

                    # css has to be queued here as we won't be rendering the component directly
                    child._queue_css()
                    try:
                        children.append(NestedComponentProp(child, self, context))
                    except OmitComponentFromRendering:
                        pass
                else:
                    with NestedComponentPropAccumulator(context, self) as accumulator:
                        # This will be a string but there may have been components that render (e.g. within
                        # other django tags like {% if %}, or from template inheritance and rendering into a
                        # block contained within a component).
                        child_value: str = child if isinstance(child, str) else child.render(context)
                        if child_value:
                            children += accumulator.apply(child_value)

            children = process_component_children(children)

            if self.omit_if_empty and not children:
                raise OmitComponentFromRendering()

            # Many things only expect a single child so handle that as a default. This isn't necessary as we handle
            # it in our calls to createElement, but makes for slightly more readable code so leaving it in.
            if len(children) == 1:
                return children[0]

            # NOTE: I removed this as we can handle it on the frontend by passing `children` through as a spread to
            # `React.createElement` which tells it the children are static. See ``ComponentSourceCodeGenerator.create_jsx_element_node``
            # for where this occurs. Adding keys here did cause some problems - namely with the `Cell` component in
            # `Table`; navigation with keyboard across rows broke.
            # for i, child in enumerate(children):
            #     if isinstance(child, required_imports) and not child.props.has_prop("key"):
            #         child.props.add_prop("key", i)

            return children
        # This won't be true for props that come from ``extra_props`` as it's already a dict before passed to the template
        # tag (the ``extra_props`` var itself is resolved in ``resolve_props``)
        if isinstance(value, FilterExpression):
            value = value.resolve(context)
            return self.resolve_prop(value, context)
        return resolve_prop(value, self, context)

    def resolve_props(self, context: Context) -> ComponentProps:
        """Resolve the props for this component to values that can be serialized

        To add special handling override the :meth:`~alliance_platform.frontend.templatetags.react.ComponentNode.resolve_prop`
        method.
        """
        props = self.props.copy()
        if self.extra_props:
            extra_props = self.extra_props.resolve(context)
            if extra_props:
                props.update(extra_props)
        if self.html_attribute_template_nodes:
            props.update(self.html_attribute_template_nodes.resolve(context))
        return ComponentProps(
            {underscore_to_camel(key): self.resolve_prop(value, context) for key, value in props.items()}
        )

    def _queue_css(self):
        css_items = self.bundler.get_embed_items(self.get_paths_for_bundling(), "text/css")
        for item in css_items:
            self.bundler_asset_context.queue_embed_file(item)

    def render_component(self, context: Context):
        self._queue_css()
        # This means this component is nested under another and needs to be handled by the parent
        # Add to the accumulator and return a string that will be handled by NestedComponentPropAccumulator.apply()
        accumulator = NestedComponentPropAccumulator.get_current(context)
        if accumulator:
            try:
                return accumulator.add(NestedComponentProp(self, self, context))
            except OmitComponentFromRendering:
                return ""

        if self.target_var:
            context[self.target_var] = NestedComponentProp(self, self, context)
            return ""

        props = self.resolve_props(context)
        asset_context = BundlerAssetContext.get_current()
        container_id = asset_context.generate_id()

        generator = ComponentSourceCodeGenerator(self)
        # Generate this first before queuing SSR so if it fails we don't queue the SSR item
        code = self.bundler.format_code(generator.generate_code(props, container_id).strip())
        if not self.ssr_disabled:
            ssr_placeholder = asset_context.queue_ssr(ComponentSSRItem(self.source, props, container_id))
        else:
            # Include a comment we can see in HTML output to assist with debugging
            ssr_placeholder = "<!-- SSR OPT OUT -->"
        if not asset_context.html_target.include_scripts:
            return ssr_placeholder

        html_attrs = build_html_attrs(
            {
                **{key: resolve(value, context) for key, value in self.container_props.items()},
                "data-djid": container_id,
            }
        )
        container_tag = resolve(self.container_tag, context)
        parts = [
            format_html(
                f"<{container_tag} {{}}>{{}}</{container_tag}>",
                html_attrs,
                mark_safe(ssr_placeholder),
            ),
            f'<script type="module">\n{code}\n</script>',
        ]
        if ap_frontend_settings.DEBUG_COMPONENT_OUTPUT:
            parts.append(f"<!--\n{self.print_debug_tree(props)}\n-->")
        return "\n".join(parts)

    def render(self, context: Context):
        try:
            return self.render_component(context)
        except OmitComponentFromRendering:
            return ""

    def print_debug_tree(self, props: ComponentProps, include_template_origin=True):
        """Print a debug tree of the component and its children.

        This renders to look like JSX with comments indicating which templates are used to render the component::

            { /* django/forms/widgets/select.html */ }
            <DjangoWidgetWrapper name="is_active">
              <Select >
                {/* django/forms/widgets/select_option.html */ }
                <Item key="unknown">
                  --------
                </Item>
              </Select>
            </DjangoWidgetWrapper>
        """
        # Disable jsx_transform so raw JSX is outputted rather than React.createElement calls
        printer = TypescriptPrinter(jsx_transform=None)
        generator = ComponentSourceCodeGenerator(self)
        jsx_element = generator.create_jsx_element_node(self, props, include_template_origin)

        return self.bundler.format_code(printer.print(jsx_element))


@register.simple_tag()
def react_refresh_preamble():
    """Add `react-refresh <https://www.npmjs.com/package/react-refresh>`_ support

    Currently only works with :class:`~alliance_platform.frontend.bundler.vite.ViteBundler`.

    This must appear after :meth:`~alliance_platform.frontend.templatetags.bundler.bundler_preamble`.

    See https://vitejs.dev/guide/backend-integration.html

    Usage:

    .. code-block:: html+django

        {% bundler_preamble %}
        {% react_refresh_preamble %}
    """
    bundler = get_bundler()
    if not isinstance(bundler, ViteBundler):
        raise ValueError("Current only ViteBundler is supported")
    if bundler.mode != "development":
        return ""
    return mark_safe(
        # Indentation level here chose to generate prettier HTML source ;)
        f"""
    <script type="module">
      import RefreshRuntime from '{bundler.get_url('@react-refresh')}';

      RefreshRuntime.injectIntoGlobalHook(window)
      window.$RefreshReg$ = () => {{}}
      window.$RefreshSig$ = () => (type) => type
      window.__vite_plugin_react_preamble_installed__ = true
    </script>
        """
    )


@dataclass
class ComponentSSRItem(SSRItem):
    """Represents a component that will be rendered on the server

    Provides payload containing necessary import & the props for rendering the component.

    See the ``ComponentSSRItem`` type in ``ssr.ts`` for where this is handled.

    NOTE: Keep in sync with ``ssr.ts``
    """

    #: Tells the renderer how to resolve the component source - either ``CommonComponentSource`` or ``ESMAssetSource``
    source: ComponentSourceBase
    #: Props for the component
    props: ComponentProps
    #: Used by React to prefix id's to guarantee uniqueness when multiple roots rendered on one page
    identifier_prefix: str

    def get_ssr_type(self):
        return "Component"

    def get_ssr_payload(self, ssr_context: SSRSerializerContext):
        """Matches ``ComponentSSRItem`` type in ``ssr.ts``


        For a common component this looks like::

            // {% component "div" %}Hello{% component %}
            {
              "component": "div",
              "props": {
                "children": ["Hello"]
              },
              "identifierPrefix": "abc123"
            }

        For an imported component source gets serialized as a custom format handled in ssrJsonRevivers.tsx ::

            // {% component "components/Input" value=5 %}{% endcomponent %}
            {
              "component": ["@@CUSTOM", "ComponentImport", {"import": "<generated string>", "propertyName": null}],
              "props": {
                "value": 5
              },
              "identifierPrefix": "6169587712__1_1"
            }

        After going through the reviver this becomes::

            {
                "component": [Function: Input],
                "props: { "value": 5 },
                "identifierPrefix": "6169587712__1_1"
            }
        """
        return {
            "component": self.source,
            "props": self.props,
            "identifierPrefix": self.identifier_prefix,
        }


@register.filter
def html_attr_to_jsx(attrs: dict):
    """Convert html attributes to casing expected by JSX

    Calls :meth:`~alliance_platform.frontend.util.transform_attribute_names`
    """
    return transform_attribute_names(attrs)


@register.filter
def merge_props(attrs1: dict, attrs2: dict | None):
    """Merge props from two dicts together

    Usage::

        {% component "MyComponent" props=widget.attrs|merge_props:some_more_props|html_attr_to_jsx %}{% endcomponent %}
    """
    if attrs2 is None:
        return attrs1
    new_props = {**attrs1, **attrs2}
    # TODO: merge class names. need to work out normalization
    # ie. class vs class_name vs className
    return new_props


@register.filter
def none_as_nan(value):
    """Convert None to NaN

    This is useful for props that should be passed as NaN to the component. The NumberInput component uses `NaN`
    instead of `null` for no value.
    """
    if value is None:
        return math.nan
    return value


@register.filter
def camelize(attrs: dict):
    """Recursively camelizes keys in a dictionary for passing to the frontend as props

    Usage::

        {% component "MyComponent" props=widget.attrs|camelize %}{% endcomponent %}
    """
    return camelize_util(attrs)


def get_component_source_from_tag_args(args: list[Any], tag_name: str, origin: Origin) -> ComponentSourceBase:
    if len(args) == 2:
        # This is the form
        #   {% component "@ant-design/icons" "MenuOutlined" %}
        # We treat this as a named import, e.g.
        #   import MenuOutlined from "@ant-design/icons"
        source = args[0]
        component_name = args[1]
        is_default_import = False
    else:
        # This is the form
        #   {% component "components/Button" %}
        # We treat this as a default import, e.g.
        #   import Button from "components/Button";
        # We could have a parameter to customise the name (Button here) but there's
        # no reason to as it's an internal detail of the codegen at that point.
        source = args[0]
        component_name = None
        is_default_import = True

    if not isinstance(source, str):
        raise TemplateSyntaxError(
            f"{tag_name} must be passed a string, received a {type(source)} witih value '{source}'"
        )
        # This is for react-dom HTML elements, e.g. "div" etc. This is identified by the tag
        # being alphabetic or one of the heading tags (these are the only html tags with numbers)
        # This doesn't support custom elements - if we need this we can extend this check to
        # consider a 'dash' as well.
        # Note that this means you can't import components from a lowercase file in the root,
        # e.g. {% component "mycomponent" %} won't work - it will consider that a common component.
        # Our conventions would disallow this anyway, and it will work so long as it's in a
        # subdirectory (e.g. "components/div" would work).
    if len(args) == 1 and (
        source.isalpha() and source.islower() or source in ["h1", "h2", "h3", "h4", "h5", "h6"]
    ):
        return CommonComponentSource(source)
    if not component_name:
        component_name = source.split("/")[-1].split(".")[0]
    bundler = get_bundler()
    resolver_context = ResolveContext(bundler.root_dir, origin.name)
    source_path = bundler.resolve_path(source, resolver_context, resolve_extensions=[".ts", ".tsx", ".js"])
    property_name = None
    if "." in component_name:
        parts = component_name.split(".")
        if len(parts) > 2:
            raise TemplateSyntaxError(f"Invalid component name {component_name}")
        component_name = parts[0]
        property_name = parts[1]
    return ImportComponentSource(source_path, component_name, is_default_import, property_name=property_name)


def parse_component_tag(
    parser: template.base.Parser,
    token: template.base.Token,
    *,
    node_class: type[ComponentNode] = ComponentNode,
    asset_source: ComponentSourceBase | None = None,
    container_tag: str = "dj-component",
    container_props: dict[str, Any] | None = None,
    props: dict[str, Any] | None = None,
    ssr_disabled: bool = False,
    omit_if_empty: bool = False,
    no_end_tag: bool = False,
):
    """Parse a component tag. Allows custom component tags to be created.

    Example usage::

        @register.tag("MyComponent")
        def my_custom_component(parser: template.base.Parser, token: template.base.Token):
            bundler = get_bundler()
            resolver_context = ResolveContext(bundler.root_dir, parser.origin.name if parser.origin else None)
            source_path = get_bundler().resolve_path(
                "path/to-component", resolver_context, resolve_extensions=[".ts", ".tsx", ".js"]
            )
            asset_source = ImportComponentSource(source_path, "MyComponentName", False)
            return parse_component_tag(parser, token, asset_source=asset_source)

    Args:
        parser: Parser as provided when using `@register.tag`
        token: Token as provided when using `@register.tag`
        node_class: The class to use for the node. This can be used to create custom nodes, should extend ``ComponentNode``
        asset_source: The source for the component. If not provided this will be determined from the tag arguments.
        container_tag: The tag to use for the container element. This defaults to ``dj-component``. This can also be
            specified when using the tag itself, e.g. ``{% MyComponent container:tag="div" %}``
        container_props: Any additional props to pass through to the container element
        props: Any default props to pass through to the component. These are combined with any props passed to the tag,
            with the tag props taking precedence.
        ssr_disabled: Whether to disable SSR for this tag. Can also be specified when using the tag, e.g. ``ssr:disabled=True``
        omit_if_empty: Whether to omit this tag if it has no children. Can also be specified when using the tag, e.g. ``component:omit_if_empty=True``

    Returns:
        The constructed ``ComponentNode``
    """
    tag_name = token.split_contents()[0]
    args, kwargs, target_var = parse_tag_arguments(
        parser,
        token,
        supports_as=True,
    )

    processed_args: list[str] = []
    context = Context()
    for arg in args:
        if not is_static_expression(arg):
            raise TemplateSyntaxError(
                f"{tag_name} must be passed static strings for its arguments (encountered variable '{arg.var}')"
            )
        else:
            processed_args.append(arg.resolve(context))
    args = processed_args
    if asset_source and args:
        raise TemplateSyntaxError(f"{tag_name} accepts no non-keyword arguments")
    elif not asset_source and len(args) not in [1, 2]:
        raise TemplateSyntaxError(f"{tag_name} tag requires either 1 or 2 arguments, received {len(args)}")
    if not no_end_tag:
        nodelist = parser.parse((f"end{tag_name}",))
        parser.delete_first_token()
    else:
        nodelist = None
    if "children" in kwargs:
        raise TemplateSyntaxError("Pass children as the tag contents rather than under the 'children' prop")
    namespaced_options: dict[str, dict[str, Any]] = defaultdict(dict)
    exclude_keys = []
    valid_keys = {
        "component": {"omit_if_empty"},
        "ssr": {"disabled"},
    }
    for k, v in kwargs.items():
        for namespace in ["container", "ssr", "component"]:
            prefix = namespace + ":"
            if k.startswith(prefix):
                key = k[len(prefix) :]
                if namespace in valid_keys and key not in valid_keys[namespace]:
                    raise TemplateSyntaxError(
                        f"Invalid option {k} passed to {tag_name}. Valid options are {' ,'.join(valid_keys[namespace])}"
                    )
                exclude_keys.append(k)
                namespaced_options[namespace][key] = v
    container_props = {**(container_props or {}), **namespaced_options["container"]}
    ssr_options = namespaced_options["ssr"]
    component_options = namespaced_options["component"]
    container_tag = container_props.pop("tag", container_tag)
    props = props.copy() if props else {}
    props.update({key: value for key, value in kwargs.items() if key not in exclude_keys})
    origin = parser.origin or Origin(UNKNOWN_SOURCE)
    if nodelist:
        # Convert the nodelist to a string with placeholders for the template nodes. This is then processed for HTML
        # contained within ``TextNode``s, before converting back to a list of nodes with any placeholders replaced with
        # the original template nodes. This allows us to handle HTML being passed to component children directly without
        # having to use __dangerouslySetInnerHTML.
        i = 0
        html = ""
        replacements: dict[str, Node] = {}
        for node in nodelist:
            if isinstance(node, TextNode):
                html += node.s
            else:
                placeholder = html_replacement_placeholder_template.format(i)
                html += placeholder
                replacements[str(i)] = node
                i += 1
        props["children"] = convert_html_string(html, origin, replacements=replacements)
    if asset_source is None:
        asset_source = get_component_source_from_tag_args(args, tag_name, origin)

    return node_class(
        origin,
        asset_source,
        props,
        target_var=target_var,
        container_tag=container_tag,
        container_props=container_props,
        ssr_disabled=ssr_options.get("disabled", ssr_disabled),
        omit_if_empty=component_options.get("omit_if_empty", omit_if_empty),
    )
