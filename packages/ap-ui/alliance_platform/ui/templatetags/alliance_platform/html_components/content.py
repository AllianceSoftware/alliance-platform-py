"""Static HTML rendering of renderable content values.

This is the static-HTML backend for :class:`~alliance_platform.frontend.renderable_content.RenderableContent`
values (e.g. form ``help_text`` produced by ``{% form_input %}``). It renders trusted developer
authored fragments directly to HTML, with the same guardrails as the rest of the HTML component
rendering: text and attribute values are escaped and event handler attributes are refused.

"""

from __future__ import annotations

import re
from typing import Any
import warnings

from django.template import Context
from django.template import Node
from django.template import NodeList
from django.template import Origin
from django.utils.functional import Promise
from django.utils.html import conditional_escape
from django.utils.safestring import SafeString
from django.utils.safestring import mark_safe

from alliance_platform.frontend.html_parser import void_elements
from alliance_platform.frontend.renderable_content import RenderableContent
from alliance_platform.frontend.renderable_content import RenderableElement
from alliance_platform.frontend.renderable_content import RenderableTemplateNode
from alliance_platform.frontend.renderable_content import RenderableText

from .base import build_attrs_string
from .base import is_event_handler_attr

_VALID_TAG_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9-]*$")


def is_rich_content_value(value: Any) -> bool:
    """Whether a prop value is renderable rich content (as opposed to a plain scalar)."""
    return isinstance(value, (RenderableContent, list, tuple))


def has_renderable_content(value: Any) -> bool:
    """Whether a content value would render anything.

    Used to decide e.g. whether a help text element should be rendered at all.
    """
    if value is None:
        return False
    if isinstance(value, RenderableContent):
        return not value.is_empty()
    if isinstance(value, (list, tuple)):
        return any(has_renderable_content(item) for item in value)
    if isinstance(value, (str, Promise)):
        return bool(str(value))
    return True


def render_content(
    value: Any,
    context: Context,
    *,
    prop_name: str,
    origin: Origin | None = None,
) -> SafeString:
    """Render a renderable-content prop value to static HTML.

    Accepts ``None``, plain/lazy strings (escaped; ``SafeString`` preserved),
    :class:`RenderableContent`, and lists/tuples of any of these. Anything unsupported warns and
    renders nothing.
    """
    if value is None:
        return mark_safe("")
    if isinstance(value, (str, Promise)):
        # str() evaluates lazy strings; SafeString.__str__ returns itself so safeness is preserved
        return conditional_escape(str(value))
    if isinstance(value, RenderableContent):
        return mark_safe("".join(_render_part(part, context, prop_name=prop_name) for part in value.parts))
    if isinstance(value, (list, tuple)):
        return mark_safe(
            "".join(render_content(item, context, prop_name=prop_name, origin=origin) for item in value)
        )
    warnings.warn(
        f"Renderable content prop '{prop_name}' contains a {type(value).__name__} value which "
        "cannot be rendered by static HTML ui components and will be ignored"
    )
    return mark_safe("")


def _render_part(part: Any, context: Context, *, prop_name: str) -> str:
    if isinstance(part, RenderableText):
        return conditional_escape(part.value)
    if isinstance(part, RenderableTemplateNode):
        # Template node output is composed like any other template content
        return part.node.render(context)
    if isinstance(part, RenderableElement):
        return _render_element(part, context, prop_name=prop_name)
    warnings.warn(
        f"Renderable content prop '{prop_name}' contains an unsupported part "
        f"({type(part).__name__}) which will be ignored"
    )
    return ""


def _clean_content_attrs(attrs: dict[str, Any], context: Context, *, prop_name: str) -> dict[str, Any]:
    """Resolve and filter attributes for static rendering.

    Event handler attributes are refused: a string value would become a live inline event handler,
    which the React backend never produces.
    """
    cleaned: dict[str, Any] = {}
    for key, value in attrs.items():
        if is_event_handler_attr(str(key)):
            warnings.warn(
                f"Renderable content prop '{prop_name}' contains event handler attribute "
                f"'{key}' which will not be rendered by static HTML ui components"
            )
            continue
        if isinstance(value, (NodeList, Node)):
            value = value.render(context)
        cleaned[key] = value
    return cleaned


def _render_element(element: RenderableElement, context: Context, *, prop_name: str) -> str:
    if not _VALID_TAG_RE.match(element.tag):
        warnings.warn(
            f"Renderable content prop '{prop_name}' contains invalid tag '{element.tag}' "
            "which will be ignored"
        )
        return ""
    attrs = dict(element.attrs)
    if element.attribute_template_nodes:
        # Attribute fragments that could not be parsed statically (bare boolean attributes and
        # template-node placeholders). Resolve them the same way the React backend does: render,
        # then re-parse in attribute position.
        from alliance_platform.frontend.html_parser import HtmlTreeParser
        from alliance_platform.frontend.html_parser import clean_html_attributes

        attr_str = " ".join(
            fragment.render(context) if isinstance(fragment, Node) else fragment
            for fragment in element.attribute_template_nodes
        )
        parser = HtmlTreeParser()
        parser.feed(f"<div {attr_str}></div>")
        if parser.root.children:
            parsed = parser.root.children[0]
            attrs.update(clean_html_attributes(parsed.attributes, attr_str, Origin("renderable content")))
    attrs_html = build_attrs_string(_clean_content_attrs(attrs, context, prop_name=prop_name))
    if element.tag in void_elements:
        return f"<{element.tag}{attrs_html}/>"
    children_html = "".join(
        _render_part(part, context, prop_name=prop_name) for part in element.children.parts
    )
    return f"<{element.tag}{attrs_html}>{children_html}</{element.tag}>"
