"""Read a static ``{% ui %}`` component's contract from its renderer for the ``ui-component`` directive.

:func:`describe_component` collects what a renderer declares into a :class:`ComponentReference`
and :func:`component_reference_rst` writes it as reStructuredText. Neither renders a component, and
this module imports neither Sphinx nor docutils, so ap-ui's tests run it without the docs
dependencies. ``ap_ui_components`` is the Sphinx extension that uses it.
"""

from __future__ import annotations

from dataclasses import dataclass
import importlib
import json
import re
import sys
from typing import TYPE_CHECKING
from typing import Any
from typing import Iterable

if TYPE_CHECKING:
    from alliance_platform.ui.html_components.base import BaseHtmlUIComponentRenderer
    from alliance_platform.ui.html_components.base import PropRule
    from alliance_platform.ui.html_components.registry import HtmlUIComponentRegistry

#: The React components' documentation, by Storybook docs id
STORYBOOK_DOCS_URL = "https://ui.alliance.software/?path=/docs/{docs_id}--docs"

#: The Storybook docs id of the React component each built-in renders, from the story titles in
#: alliance-platform-js ``apps/stories/src/stories/*.stories.tsx`` (``title: 'ui/Button'`` is
#: ``ui-button``). The layout parts have no stories.
BUILT_IN_STORYBOOK_DOCS_IDS = {
    "button": "ui-button",
    "button_group": "ui-buttongroup",
    "icon": "icons-icons",
    "inline_alert": "ui-inlinealert",
    "labeled_input": "form-labeledinput",
    "menubar": "ui-menubar",
    "menubar_item": "ui-menubar",
    "menubar_section": "ui-menubar",
    "menubar_submenu": "ui-menubar",
    "number_input": "ui-numberinput",
    "pagination": "ui-pagination",
    "table": "ui-table",
    "table_body": "ui-table",
    "table_cell": "ui-table",
    "table_column": "ui-table",
    "table_header": "ui-table",
    "table_row": "ui-table",
    "text_area": "ui-textarea",
    "text_input": "ui-textinput",
    "checkbox": "ui-checkbox",
    "checkbox_group": "ui-checkboxgroup",
    "radio_group": "ui-radiogroup",
    "radio": "ui-radiogroup",
    "native_select": "form-nativeselect",
}

#: The parent each built-in part requires, by the class attribute that declares the requirement
_PARENT_REQUIREMENTS = (
    ("requires_table", "table"),
    ("requires_menubar", "menubar"),
    ("requires_radio_group", "radio_group"),
)

_CAMEL_CASE_BOUNDARY_RE = re.compile(r"([a-z0-9])([A-Z])")


def template_prop_name(name: str) -> str:
    """Return how a template writes the prop ``name``: ``isDisabled`` is ``is_disabled``.

    ``{% ui %}`` turns the result back into ``name``, as it does any prop a template passes.
    """
    if name == "className":
        return "class"
    if name.startswith(("data-", "aria-")):
        return name.replace("-", "_")
    return _CAMEL_CASE_BOUNDARY_RE.sub(r"\1_\2", name).lower()


@dataclass(frozen=True)
class PropReference:
    """A prop as the reference lists it."""

    #: The canonical prop name, as the renderer and the React component spell it
    name: str
    #: How templates write it
    template_name: str
    #: The values its ``PropRule`` allows, as reStructuredText literals: the choices or the types
    values: tuple[str, ...]
    #: What an invalid value is replaced by, as a literal; ``"omitted"`` when the rule drops it and
    #: ``None`` for a prop without a rule
    invalid_fallback: str | None
    #: The template spellings of other names for the prop
    aliases: tuple[str, ...]
    #: The template spellings of names that still work for the prop but are reported
    deprecated_aliases: tuple[str, ...]
    rich_content: bool
    non_scalar: bool
    #: The renderer's ``prop_docs`` entry
    doc: str | None


@dataclass(frozen=True)
class UnsupportedProps:
    """Props a renderer refuses for one reason."""

    #: How templates write them
    template_names: tuple[str, ...]
    #: The reason, which a report of one of them follows with ``use {% <react_tag> %} instead``
    reason: str


@dataclass(frozen=True)
class ComponentReference:
    """What a static component's renderer declares, for its reference documentation."""

    name: str
    has_children: bool
    #: The ``data-apui`` value the component marks its element with, if it marks one
    apui_marker: str | None
    slot_name: str | None
    #: The component the component renders only inside, if any
    parent: str | None
    runtime_token: str | None
    react_tag: str | None
    #: The React component's Storybook documentation, if it has any
    react_docs_url: str | None
    #: The props, in template spelling order, without the forwarded attributes
    props: tuple[PropReference, ...]
    #: The template spellings of the plain attributes copied to the component's element
    forwarded_attributes: tuple[str, ...]
    allows_data_attributes: bool
    allows_aria_attributes: bool
    #: The template spellings of the ``aria-*`` attributes accepted when others are not
    extra_aria_attributes: tuple[str, ...]
    #: The ``prop_docs`` entries for the open-ended attributes
    data_attributes_doc: str | None
    aria_attributes_doc: str | None
    #: Why event handler props are refused
    event_handler_reason: str
    unsupported_props: tuple[UnsupportedProps, ...]
    #: The source files of the renderer's classes, which the reference is read from
    source_files: tuple[str, ...]

    @property
    def usage(self) -> str:
        """The tag as a template writes it, with its end tag when it has children."""
        tag = f'{{% ui "{self.name}" %}}'
        return f"{tag}...{{% endui %}}" if self.has_children else tag


def load_registry(dotted_path: str) -> HtmlUIComponentRegistry:
    """Import the :class:`HtmlUIComponentRegistry` named by ``module.path.attribute``."""
    from alliance_platform.ui.html_components.registry import HtmlUIComponentRegistry

    module_path, _, attribute = dotted_path.rpartition(".")
    if not module_path:
        raise ValueError(f"'{dotted_path}' is not a dotted path to a registry")
    registry = getattr(importlib.import_module(module_path), attribute, None)
    if not isinstance(registry, HtmlUIComponentRegistry):
        raise ValueError(f"'{dotted_path}' is not an HtmlUIComponentRegistry")
    return registry


def describe_component(
    name: str,
    registry: HtmlUIComponentRegistry | None = None,
) -> ComponentReference:
    """Describe the component registered as ``name``, by default in ``built_in_registry``.

    Raises ``LookupError`` when no component has that name.
    """
    if registry is None:
        from alliance_platform.ui.html_components import built_in_registry

        registry = built_in_registry
    renderer = registry.get(name)
    if renderer is None:
        raise LookupError(f"No static ui component is registered as '{name}'")

    docs_id = BUILT_IN_STORYBOOK_DOCS_IDS.get(name)
    accepted = renderer.documented_props()
    # children is the tag's content, which templates write between the tags, not a prop
    props = accepted - renderer.forwarded_props - {"children"}
    return ComponentReference(
        name=name,
        has_children=renderer.has_children,
        apui_marker=renderer.apui_name if renderer.has_apui_marker else None,
        slot_name=renderer.slot_name,
        parent=next(
            (parent for attribute, parent in _PARENT_REQUIREMENTS if getattr(renderer, attribute, False)),
            None,
        ),
        runtime_token=renderer.runtime_token,
        react_tag=renderer.react_tag,
        react_docs_url=STORYBOOK_DOCS_URL.format(docs_id=docs_id) if docs_id else None,
        props=tuple(
            sorted(
                (_describe_prop(renderer, prop) for prop in props),
                key=lambda prop: prop.template_name,
            )
        ),
        forwarded_attributes=_template_names(renderer.forwarded_props & accepted),
        allows_data_attributes=renderer.allow_data_props,
        allows_aria_attributes=renderer.allow_aria_props,
        extra_aria_attributes=(
            () if renderer.allow_aria_props else _template_names(renderer.extra_allowed_aria_props)
        ),
        data_attributes_doc=renderer.prop_docs.get("data-*"),
        aria_attributes_doc=renderer.prop_docs.get("aria-*"),
        event_handler_reason=renderer.event_handler_prop_reason,
        unsupported_props=_describe_unsupported_props(renderer),
        source_files=_source_files(renderer),
    )


def _source_files(renderer: type[BaseHtmlUIComponentRenderer]) -> tuple[str, ...]:
    files = (getattr(sys.modules.get(cls.__module__), "__file__", None) for cls in renderer.__mro__)
    return tuple(dict.fromkeys(file for file in files if file))


def _describe_prop(renderer: type[BaseHtmlUIComponentRenderer], name: str) -> PropReference:
    rule = renderer.prop_rules.get(name)
    return PropReference(
        name=name,
        template_name=template_prop_name(name),
        values=_rule_values(rule) if rule is not None else (),
        invalid_fallback=_rule_fallback(rule) if rule is not None else None,
        aliases=_template_names(alias for alias, target in renderer.prop_aliases.items() if target == name),
        deprecated_aliases=_template_names(
            alias for alias, target in renderer.deprecated_prop_aliases.items() if target == name
        ),
        rich_content=name in getattr(renderer, "rich_content_props", ()),
        non_scalar=name in renderer.non_scalar_props,
        doc=renderer.prop_docs.get(name),
    )


def _rule_values(rule: PropRule) -> tuple[str, ...]:
    if rule.choices is not None:
        values = tuple(_literal(choice) for choice in rule.choices)
    elif rule.accepted_types is not None:
        values = tuple(f"``{accepted_type.__name__}``" for accepted_type in rule.accepted_types)
    else:
        values = ()
    return (*values, "``None``") if rule.allow_none else values


def _rule_fallback(rule: PropRule) -> str:
    from alliance_platform.ui.html_components.base import _OMIT_INVALID_PROP

    if rule.invalid_fallback is _OMIT_INVALID_PROP:
        return "omitted"
    return _literal(rule.invalid_fallback)


def _literal(value: Any) -> str:
    # Strings as a template writes them, in double quotes
    return f"``{json.dumps(value) if isinstance(value, str) else repr(value)}``"


def _template_names(names: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted(template_prop_name(name) for name in names))


def _describe_unsupported_props(renderer: type[BaseHtmlUIComponentRenderer]) -> tuple[UnsupportedProps, ...]:
    by_reason: dict[str, list[str]] = {}
    for prop, reason in renderer.unsupported_prop_reasons.items():
        by_reason.setdefault(reason, []).append(prop)
    groups = [
        UnsupportedProps(template_names=_template_names(props), reason=reason)
        for reason, props in by_reason.items()
    ]
    return tuple(sorted(groups, key=lambda group: group.template_names))


def component_reference_rst(reference: ComponentReference, *, link_react_tag: bool = False) -> list[str]:
    """Write ``reference`` as reStructuredText lines: a field list, the props and the attributes.

    The output is standard markup only (field and bullet lists, a ``list-table``, literals and
    links), which the HTML and Markdown builders both render. With ``link_react_tag`` a named React
    tag is written with the ``ttag`` role, so it links to the tag's section where one documents it.
    """
    usage = f"``{reference.usage}``"
    if not reference.has_children:
        usage += " (a leaf: no children and no ``{% endui %}``)"
    lines = [f":Usage: {usage}"]
    if reference.parent:
        lines.append(f':Parent: renders only inside ``{{% ui "{reference.parent}" %}}``')
    if reference.apui_marker:
        lines.append(f':Marker: ``data-apui="{reference.apui_marker}"``')
    if reference.slot_name:
        lines.append(f":Slot: ``{reference.slot_name}``")
    if reference.runtime_token:
        lines.append(f':Runtime: ``data-apui-attach="{reference.runtime_token}"``')
    react = _react_field(reference, link_react_tag=link_react_tag)
    if react:
        lines.append(f":React: {react}")
    lines.append("")

    if reference.props:
        lines += _props_table(reference)
    else:
        lines += ["Props: none.", ""]

    attributes = _attribute_items(reference)
    if attributes:
        lines += ["Forwarded attributes:", ""]
        lines += [f"* {attribute}" for attribute in attributes]
    else:
        lines.append("Forwarded attributes: none.")
    lines.append("")

    lines += ["Unsupported props:", ""]
    lines.append(f"* ``on_*`` props: {_refusal(reference, reference.event_handler_reason)}")
    for group in reference.unsupported_props:
        lines.append(f"* {_literal_list(group.template_names)}: {_refusal(reference, group.reason)}")
    lines.append("")
    return lines


def _refusal(reference: ComponentReference, reason: str) -> str:
    # With the suffix BaseHtmlUIComponentRenderer._report_ignored_prop adds to a report of the prop
    text = _escape_rst(_one_line(reason))
    return f"{text}; use ``{{% {reference.react_tag} %}}`` instead" if reference.react_tag else text


_RST_SPECIAL_RE = re.compile(r"([\\`*|_])")


def _escape_rst(text: str) -> str:
    """Escape plain text, such as a diagnostic, for reStructuredText."""
    return _RST_SPECIAL_RE.sub(r"\\\1", text)


def _react_field(reference: ComponentReference, *, link_react_tag: bool) -> str:
    parts = []
    if reference.react_tag:
        tag = f"{{% {reference.react_tag} %}}"
        # A named tag is one word: component "@alliancesoftware/ui" "Content" is not
        if link_react_tag and " " not in reference.react_tag:
            parts.append(f":ttag:`{tag} <{reference.react_tag}>`")
        else:
            parts.append(f"``{tag}``")
    if reference.react_docs_url:
        parts.append(f"`React docs <{reference.react_docs_url}>`__")
    return ", ".join(parts)


def _props_table(reference: ComponentReference) -> list[str]:
    lines = [
        ".. list-table::",
        "    :header-rows: 1",
        "    :widths: 22 26 14 38",
        "    :class: apui-component-props",
        "",
        "    * - Prop",
        "      - Values",
        "      - Default on invalid",
        "      - Notes",
    ]
    for prop in reference.props:
        lines.append(f"    * - ``{prop.template_name}``")
        if prop.template_name != prop.name:
            lines += ["", f"        ``{prop.name}``"]
        lines.append(_cell(", ".join(prop.values)))
        lines.append(_cell(prop.invalid_fallback or ""))
        lines.append(_cell("; ".join(_prop_notes(reference, prop))))
    lines.append("")
    return lines


def _cell(text: str) -> str:
    # A cell's text must stay on its line
    return f"      - {_one_line(text)}".rstrip()


def _one_line(text: str) -> str:
    return " ".join(text.split())


def _prop_notes(reference: ComponentReference, prop: PropReference) -> list[str]:
    notes = []
    if prop.aliases:
        notes.append(f"{'aliases' if len(prop.aliases) > 1 else 'alias'} {_literal_list(prop.aliases)}")
    if prop.deprecated_aliases:
        notes.append(
            f"deprecated {'aliases' if len(prop.deprecated_aliases) > 1 else 'alias'} "
            f"{_literal_list(prop.deprecated_aliases)}"
        )
    if prop.rich_content:
        notes.append("rich content")
    if prop.non_scalar:
        notes.append("non-scalar")
    if prop.doc:
        # Every prop of a component without a React counterpart is the component's own
        notes.append(f"static only: {prop.doc}" if reference.react_tag else prop.doc)
    elif reference.react_docs_url:
        notes.append("see React docs")
    elif reference.react_tag:
        notes.append("as in React")
    return notes


def _attribute_items(reference: ComponentReference) -> list[str]:
    items = []
    if reference.forwarded_attributes:
        items.append(_literal_list(reference.forwarded_attributes))
    if reference.allows_data_attributes:
        items.append(_with_doc(reference, "``data-*`` attributes", reference.data_attributes_doc))
    if reference.allows_aria_attributes:
        items.append(_with_doc(reference, "``aria-*`` attributes", reference.aria_attributes_doc))
    elif reference.extra_aria_attributes:
        items.append(f"{_literal_list(reference.extra_aria_attributes)}; no other ``aria-*`` attributes")
    return items


def _with_doc(reference: ComponentReference, item: str, doc: str | None) -> str:
    if not doc:
        return item
    doc = _one_line(doc)
    return f"{item}; static only: {doc}" if reference.react_tag else f"{item}: {doc}"


def _literal_list(names: Iterable[str]) -> str:
    return ", ".join(f"``{name}``" for name in names)
