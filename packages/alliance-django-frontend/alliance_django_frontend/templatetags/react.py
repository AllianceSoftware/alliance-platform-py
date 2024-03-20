from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any
from typing import cast
from typing import Type
import warnings

from allianceutils.util import underscore_to_camel
from django import template
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.forms.models import ModelChoiceIteratorValue
from django.template import Context
from django.template import NodeList
from django.template import Origin
from django.template import TemplateSyntaxError
from django.template.base import FilterExpression
from django.template.base import UNKNOWN_SOURCE
from django.utils.html import format_html
from django.utils.module_loading import import_string
from django.utils.safestring import mark_safe

from common_frontend.bundler import get_bundler
from common_frontend.bundler.base import BaseBundler
from common_frontend.bundler.base import ResolveContext
from common_frontend.bundler.context import BundlerAsset
from common_frontend.bundler.context import BundlerAssetContext
from common_frontend.bundler.ssr import ImportDefinition
from common_frontend.bundler.ssr import SSRItem
from common_frontend.bundler.ssr import SSRSerializable
from common_frontend.bundler.ssr import SSRSerializerContext
from common_frontend.bundler.vite import ViteBundler
from common_frontend.codegen.printer import TypescriptSourceFileWriter
from common_frontend.codegen.typescript import CallExpression
from common_frontend.codegen.typescript import FunctionDeclaration
from common_frontend.codegen.typescript import Identifier
from common_frontend.codegen.typescript import ImportDefaultSpecifier
from common_frontend.codegen.typescript import ImportSpecifier
from common_frontend.codegen.typescript import Node
from common_frontend.codegen.typescript import PropertyAccessExpression
from common_frontend.codegen.typescript import ReturnStatement
from common_frontend.codegen.typescript import StringLiteral
from common_frontend.codegen.typescript import UnconvertibleValueException
from common_frontend.forms.renderers import form_input_context_key
from common_frontend.prop_handlers import CodeGeneratorNode
from common_frontend.prop_handlers import ComponentProp
from common_frontend.util import transform_attribute_names
from common_lib.templatetags.common import build_html_attrs
from common_lib.templatetags.common import is_static_expression
from common_lib.templatetags.common import parse_tag_arguments
from common_lib.templatetags.common import resolve

register = template.Library()


@lru_cache
def get_prop_handlers() -> tuple[Type[ComponentProp]]:
    """Get the prop handlers to use for this project. Reads the ``FRONTEND_REACT_PROP_HANDLERS`` setting and caches result."""
    try:
        prop_handlers = settings.FRONTEND_REACT_PROP_HANDLERS
    except AttributeError:
        raise ImproperlyConfigured("settings.FRONTEND_REACT_PROP_HANDLERS must be defined. ")
    else:
        if isinstance(prop_handlers, str):
            prop_handlers = import_string(prop_handlers)
        prop_handlers = tuple(prop_handlers)  # type: ignore[assignment]
    return cast(tuple[Type[ComponentProp]], prop_handlers)


def resolve_prop(value: Any, node: ComponentNode, context: Context) -> ComponentProp | Any:
    """Resolve the prop class to use for the specified ``value``

    To add new handlers, add class to the list set in  ``settings.FRONTEND_REACT_PROP_HANDLERS``
    """
    if isinstance(value, dict):
        return {k: resolve_prop(v, node, context) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return list(resolve_prop(v, node, context) for v in value)
    if isinstance(value, ModelChoiceIteratorValue):
        return resolve_prop(value.value, node, context)  # type: ignore[attr-defined] # It has this value but no type info
    handlers = get_prop_handlers()
    for handler in handlers:
        if handler.should_apply(value, node, context):
            return handler(value, node, context)
    return value


@register.tag("component")
def component(parser: template.base.Parser, token: template.base.Token):
    """Render a React component with the specified props

    There are three ways to specify which component to render. The first is for a `"common component" <https://react.dev/reference/react-dom/components/common>`_
    which is to say a built-in browser component (e.g. ``div``)::

        {% component "h2" %}Heading{% endcomponent %}

    The other two are for using a component defined in an external file. These will be loaded via
    the specified bundler class (currently :class:`~common_frontend.bundler.vite.ViteBundler`). With
    a single argument it specifies that the default export from the file is the component to use::

        {% component "components/Button" %}Click Me{% endcomponent %}

    With two arguments the first is the file path and the second is the named export from that file::

        {% component "components/Table" "Column" %}Name{% endcomponent %}

    The last option has a variation for using a property of the export. This is useful for components
    where related components are added as properties, e.g. ``Table`` and ``Table.Column``::

        {% component "components" "Table.Column" %}Name{% endcomponent %}

    Note that this is only available when using named exports; default exports don't support it due to
    ambiguity around whether the ``.`` indicates file extension or property access.

    You can omit the file extension - the above could resolve to ``components/Table.tsx`` (``.js`` and ``.ts`` are also
    supported). See :ref:`resolving_paths` for details on how the file path is resolved.

    Props are specified as keyword arguments to the tag::

        {% component "components/Button" variant="primary" %}Click Me{% endcomponent %}

    Additionally, a dict of props can be passed under the ``props`` kwarg::

        {% component "components/Button" variant="primary" props=button_props %}Click Me{% endcomponent %}

    Children can be passed between the opening ``{% component %}`` and closing ``{% endcomponent %}``. Whitespace
    is handled the same as in JSX:

    * Whitespace at the beginning and ending of lines is removed
    * Blank lines are removed
    * New lines adjacent to other components are removed
    * New lines in the middle of a string literal is replaced with a single space

    So the following are all equivalent::

        {% component "div" %}Hello World{% endcomponent %}

        {% component %}
            Hello world
        {% endcomponent %}


        {% component %}
            Hello
            world
        {% endcomponent %}


        {% component %}

            Hello world
        {% endcomponent %}

    Components can be nested::

        {% component "components/Button" type="primary" %}
            {% components "icons" "Menu" %}{% endcomponent %}
            Open Menu
        {% end_component %}

    You can use ``as <variable name>`` to store in a variable in context that can then be passed to another tag::

        {% component "icons" "Menu" as icon %}{% end_component %}
        {% component "components/Button" type="primary" icon=icon %}Open Menu{% end_component %}

    All props must be JSON serializable. :class:`~common_frontend.prop_handlers.ComponentProp` can be used to define
    how to serialize data, with a matching implementation in ``propTransformers.tsx`` to de-serialize it.

    For example :class:`~common_frontend.prop_handlers.DateProp` handles serializing a python ``datetime`` and
    un-serializing it as a native JS ``Date`` on the frontend. See :class:`~common_frontend.prop_handlers.ComponentProp`
    for documentation about adding your own complex props.

    Components are rendered using the ``renderComponent`` function in ``renderComponent.tsx``. This can be modified as needed,
    for example if a new provider is required.

    .. note:: All props passed through are converted to camel case automatically (i.e. ``my_prop`` will become ``myProp``)

    Server Side Rendering (SSR)
    ---------------------------

    Components will automatically be rendered on the server. See :ref:`ssr` for details about how this works.

    To opt out of SSR pass ``ssr:disabled=True`` to the component after the component name::

        {% component 'components/Button.tsx' ssr:disabled=True %}...{% endcomponent %}

    Options
    -------

    Various options can be passed to the component tag. To differentiate from actual props to the component they are
    prefixed with `ssr:` for server side rendering options, `component:` for general component options, or `container:`
    for options relating to the container the component is rendered into.

    - ``ssr:disabled=True`` - if specified, no server side rendering will occur for this component
    - ``component:omit_if_empty=True`` - if specified, the component will not be rendered if it has no children. This is
      useful for when components may not be rendered based on permission checks
    - ``container:tag`` - the HTML tag to use for the container. Defaults to the custom element ``dj-component``.
    - ``container:<any other prop>`` - any other props will be passed to the container element. For example, to add
      a class to the container you can use ``container:class="my-class"``.

    For example::

        {% component 'core-ui' 'Button' ssr:disabled=True variant="Outlined"%}
            ...
        {% endcomponent %}
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
        component = generator.resolve_component_import(self.component)
        create_element = generator.resolve_prop_import(
            "frontend/src/renderComponent.tsx", ImportSpecifier("createElementWithProps")
        )
        return CallExpression(create_element, [component, self.props.generate_code(generator)])

    def as_debug_string(self):
        """Returns a string representation of this prop for debugging purposes

        This is only used if you pass a component as a prop to another component. It's not used when
        just nesting components - that's handled by `print_debug_tree` itself.
        """
        return self.component.print_debug_tree(self.props, suppress_origin=True)


PropType = str | float | int | list["PropType"] | tuple["PropType"] | dict[str, "PropType"] | ComponentProp
PropsType = dict[str, PropType]


class ComponentProps(SSRSerializable, CodeGeneratorNode):
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

    def get_tag(self):
        return "json"

    def _serialize_prop(self, value: PropType, ssr_context: SSRSerializerContext):
        if isinstance(value, dict):
            return {underscore_to_camel(k): self._serialize_prop(v, ssr_context) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [self._serialize_prop(v, ssr_context) for v in value]
        if isinstance(value, ComponentProp):
            return value.serialize(ssr_context)
        if isinstance(value, ComponentProps):
            return value.serialize(ssr_context)
        return value

    def serialize(self, ssr_context: SSRSerializerContext):
        """Serialize props to Dict that can then be JSON encoded

        Handles conversion of :class:`~common_frontend.prop_handlers.ComponentProp` instances.

        Args:
            options: The options to use when serializing. In particular the options tell serialization how to handle
                resolving imports when dealing with nested components.
        """
        return self._serialize_prop(self.props, ssr_context)

    def _codegen_prop(self, value: PropType, generator: ComponentSourceCodeGenerator):
        if isinstance(value, dict):
            return {underscore_to_camel(k): self._codegen_prop(v, generator) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [self._codegen_prop(v, generator) for v in value]
        if isinstance(value, CodeGeneratorNode):
            return value.generate_code(generator)
        if isinstance(value, ImportComponentSource):
            # This lets us pass through imports as props, for example to pass a component class itself as a prop to
            # another component
            return generator.resolve_prop_import(
                value.path,
                (
                    ImportDefaultSpecifier(value.import_name)
                    if value.is_default_import
                    else ImportSpecifier(value.import_name)
                ),
            )
        return value

    def generate_code(self, generator: ComponentSourceCodeGenerator):
        try:
            return self.convert_to_node(self._codegen_prop(self.props, generator), generator)
        except UnconvertibleValueException as e:
            raise ValueError(
                f"Do not know how to handle prop of type {type(e.value)}: {e.value}\n\n "
                f"Either add handling to {settings.FRONTEND_REACT_PROP_HANDLERS} or check the correct value is being passed in."
            )

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

    This differs from :class:`~common_frontend.templatetags.react.CommonComponentSource` which is just
    a string (e.g. 'div' or 'button') and requires no import to work.
    """

    #: If specified, this is the name of the property to use from the import. e.g. "Table.Cell" would use the Cell property from Table.
    property_name: str | None = None

    def get_relative_path(self):
        return self.path.relative_to(settings.PROJECT_DIR)

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

    @classmethod
    def get_current(cls, context: Context) -> NestedComponentPropAccumulator | None:
        """Get the current accumulator, if any

        This extracts the current accumulator instance from the template context. Returns ``None``
        if there is no active accumulator.
        """
        return context.get(cls.context_key, None)

    def __init__(self, context: Context):
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
            sub_value = value[prev_index:]
            if sub_value:
                children.append(sub_value)
        elif value:
            children.append(value)
        self.props = {}

        return children


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
          createElementWithProps,
          renderComponent,
        } from "http://localhost:5173/assets/frontend/src/renderComponent.tsx";

        function Wrapper() {
          return createElementWithProps(TestComponent, {});
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

    _requires_wrapper_component: bool
    _used_identifiers: list[str]
    _leading_nodes: list[Node]

    def __init__(self, node: ComponentNode):
        self.node = node
        self.bundler = node.bundler
        self._writer = TypescriptSourceFileWriter(resolve_import_url=self._resolve_import_url)
        self._requires_wrapper_component = False
        self._used_identifiers = []
        self._leading_nodes = []

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

    def resolve_prop_import(self, path: str | Path, specifier: ImportSpecifier | ImportDefaultSpecifier):
        """This is a separate method so that we can track prop imports separately.

        Any custom prop that needs and import should call this method

        This is necessary as the imports for props depend on usage and can't be statically determined. As such, these
        are tracked separated and added to the dynamic dependencies of the component. This allows the ``BundlerContext``
        to check this assets will be available in production and raise an error if not.
        """
        self.node.add_dynamic_dependency(self.bundler.validate_path(path, resolve_extensions=[".ts", ".tsx"]))
        return self._writer.resolve_import(path, specifier)

    def requires_wrapper_component(self):
        """Indicate that a wrapper component is required to render this component. This is required when using hooks."""
        self._requires_wrapper_component = True

    def generate_code(self, props: ComponentProps, container_id: str):
        props_node = props.generate_code(self)
        component_id = self.resolve_component_import(self.node)
        for node in self._leading_nodes:
            self._writer.add_node(node)
        if self._requires_wrapper_component:
            wrapper_id = Identifier("Wrapper")
            self._writer.add_node(
                FunctionDeclaration(
                    wrapper_id,
                    [],
                    [
                        ReturnStatement(
                            CallExpression(
                                self._writer.resolve_import(
                                    "frontend/src/renderComponent.tsx",
                                    ImportSpecifier("createElementWithProps"),
                                ),
                                [
                                    component_id,
                                    props_node,
                                ],
                            )
                        )
                    ],
                )
            )
            component_id = wrapper_id
            props_node = {}
        self._writer.add_node(
            CallExpression(
                self._writer.resolve_import(
                    "frontend/src/renderComponent.tsx", ImportSpecifier("renderComponent")
                ),
                [
                    CallExpression(
                        PropertyAccessExpression(
                            Identifier("document"),
                            Identifier("querySelector"),
                        ),
                        [f"[data-djid='{container_id}']"],
                    ),
                    component_id,
                    props_node,
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

    def add_leading_node(self, node: Node):
        """Add a node that should be added to the top of the generated code."""
        self._leading_nodes.append(node)


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


class ComponentNode(template.Node, BundlerAsset):
    """A template node used by :func:`~common_frontend.templatetags.react.component`"""

    #: Any extra dependencies for this component. This comes from props used that may require imports, for example
    #: DateProp may require the date library be included.
    dynamic_dependencies: list[Path]

    container_tag: str | FilterExpression
    container_props: dict[str, Any]

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
    ):
        self.container_tag = container_tag
        self.container_props = container_props or {}
        self.ssr_disabled = ssr_disabled
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
        paths = [settings.PROJECT_DIR / "frontend/src/renderComponent.tsx"]
        if isinstance(self.source, ImportComponentSource):
            paths.append(self.source.path)
        return paths

    def resolve_prop(self, value, context: Context):
        """Handles resolving values to a type that can be serialized

        If you add new :class:`~common_frontend.prop_handlers.ComponentProp` there must a case here
        to convert values to the new type.
        """
        if isinstance(value, DeferredProp):
            value = value.resolve(context)
        if isinstance(value, NodeList):
            # If it's a NodeList it must be tag children
            children: list[str | NestedComponentProp] = []
            for child in value:
                if isinstance(child, ComponentNode):
                    # We could remove this branch - it's an optimisation of the below. We know the node type here
                    # directly so can avoid the extra work + string replacement that happens below.
                    try:
                        children.append(NestedComponentProp(child, self, context))
                    except OmitComponentFromRendering:
                        pass
                else:
                    with NestedComponentPropAccumulator(context) as accumulator:
                        # This will be a string but there may have been components that render (e.g. within
                        # other django tags like {% if %}, or from template inheritance and rendering into a
                        # block contained within a component).
                        child_value: str = child.render(context)
                        if child_value:
                            children += accumulator.apply(child_value)

            children = process_component_children(children)

            if self.omit_if_empty and not children:
                raise OmitComponentFromRendering()

            # Many things only expect a single child so handle that as a default. This isn't necessary as we handle
            # it in createElementWithProps but makes for slightly more readable code so leaving it in.
            if len(children) == 1:
                return children[0]

            # NOTE: I removed this as we can handle it on the frontend by passing `children` through as a spread to
            # `React.createElement` which tells it the children are static. See `createElementWithProps` for where this
            # occurs. Adding keys here did cause some problems - namely with the `Cell` component in `Table`; navigation
            # with keyboard across rows broke.
            # for i, child in enumerate(children):
            #     if isinstance(child, required_imports) and not child.props.has_prop("key"):
            #         child.props.add_prop("key", i)

            return children
        # This won't be true for props that come from ``extra_props`` as it's already a dict before passed to the template
        # tag (the ``extra_props`` var itself is resolved in ``resolve_props``)
        if isinstance(value, FilterExpression):
            value = value.resolve(context)
            return self.resolve_prop(value, context)
        # Always handle this first as many things rely on NestedComponentProp being here
        if isinstance(value, ComponentNode):
            return NestedComponentProp(value, self, context)
        return resolve_prop(value, self, context)

    def resolve_props(self, context: Context) -> ComponentProps:
        """Resolve the props for this component to values that can be serialized

        To add special handling override the :meth:`~common_frontend.templatetags.react.ComponentNode.resolve_prop`
        method.
        """
        props = self.props.copy()
        if self.extra_props:
            props.update(self.extra_props.resolve(context))
        return ComponentProps({key: self.resolve_prop(value, context) for key, value in props.items()})

    def render_component(self, context: Context):
        css_items = self.bundler.get_embed_items(self.get_paths_for_bundling(), "text/css")
        for item in css_items:
            self.bundler_asset_context.queue_embed_file(item)

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
        if settings.FRONTEND_DEBUG_COMPONENT_OUTPUT:
            parts.append(f"<!--\n{self.print_debug_tree(props)}\n-->")
        return "\n".join(parts)

    def render(self, context: Context):
        try:
            return self.render_component(context)
        except OmitComponentFromRendering:
            return ""

    def print_debug_tree(
        self, props: ComponentProps, level=0, last_template_name=None, suppress_origin=False
    ):
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
        attrs = {}
        children = []
        for name, value in props.props.items():
            if name == "children":
                _raw_prop = value
                raw_prop: list[PropType]
                if not isinstance(_raw_prop, (list, tuple)):
                    raw_prop = [cast(PropType, _raw_prop)]
                else:
                    raw_prop = cast(list[PropType], _raw_prop)
                for i, child in enumerate(raw_prop):
                    if isinstance(child, NestedComponentProp):
                        children.append(
                            child.component.print_debug_tree(
                                child.props, level + 1, self.origin.template_name, suppress_origin=i > 0
                            )
                        )
                    else:
                        if isinstance(child, str):
                            child = child.strip()
                        if child:
                            children.append(child)
            else:
                if isinstance(value, ComponentProp):
                    value = f"{{{value.as_debug_string()}}}"
                elif isinstance(value, str):
                    value = f'"{value}"'
                else:
                    value = f"{{{value}}}"
                attrs[name] = value
        indent = "  " * level
        child_indent = "  " * (level + 1)
        children_str = child_indent + f"\n{child_indent}".join(children)
        attr_str = " ".join(f"{name}={value}" for name, value in attrs.items())
        template_name = self.origin.template_name
        if isinstance(template_name, bytes):
            template_name = template_name.decode("utf8")
        if not suppress_origin and template_name and template_name != last_template_name:
            origin = f"{{/* {template_name} */ }}\n{indent}"
        else:
            origin = ""
        open_tag = f"{origin}<{self.source.as_tag()} {attr_str}>"
        if not children:
            return f"{open_tag[:-1]} />"
        return f"""{open_tag}\n{children_str}\n{indent}</{self.source.as_tag()}>"""


@register.simple_tag()
def react_refresh_preamble():
    """Add `react-refresh <https://www.npmjs.com/package/react-refresh>`_ support

    Currently only works with :class:`~common_frontend.bundler.vite.ViteBundler`.

    This must appear after :meth:`~common_frontend.templatetags.bundler.bundler_preamble`.

    See https://vitejs.dev/guide/backend-integration.html

    Usage::

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

    Calls :meth:`~common_frontend.util.transform_attribute_names`
    """
    return transform_attribute_names(attrs)


@register.filter
def merge_props(attrs1: dict, attrs2: dict):
    """Merge props from two dicts together

    Usage::

        {% component "MyComponent" props=widget.attrs|merge_props:some_more_props|html_attr_to_jsx %}{% endcomponent %}
    """
    new_props = {**attrs1, **attrs2}
    # TODO: merge class names. need to work out nomralization
    # ie. class vs class_name vs className
    return new_props


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
    if nodelist:
        props["children"] = nodelist
    origin = parser.origin or Origin(UNKNOWN_SOURCE)
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
