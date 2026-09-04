"""Static HTML renderers for the generic Alliance UI layout primitives."""

from __future__ import annotations

from typing import Any

from django.template import Context

from ..base import BaseHtmlUIComponentRenderer
from ..base import enum_prop_rule
from ..slots import replace_slot_scope

_FORWARDED_PROPS = frozenset({"id", "title", "role", "tabIndex", "dir", "lang", "hidden", "draggable"})
_EVENT_HANDLER_REASON = "event handlers are not supported by static layout components"


class UILayoutPartRenderer(BaseHtmlUIComponentRenderer):
    slot_name: str
    tag_name: str
    supported_props = frozenset({"className", "style", "children", "slot"})
    forwarded_props = _FORWARDED_PROPS
    allow_data_props = True
    allow_aria_props = True
    prop_filter_context = "static layout components"
    event_handler_prop_reason = _EVENT_HANDLER_REASON

    def render_component(self, context: Context, props: dict[str, Any], children_html: str) -> str:
        attrs = {
            **self.collect_forwarded_props(props),
            "className": props.get("className"),
            "style": props.get("style"),
        }
        return self._render_tag(self.tag_name, attrs, children_html)


class UIContentRenderer(UILayoutPartRenderer):
    apui_component_name = "content"
    slot_name = "content"
    tag_name = "section"

    def render_children_for_component(self, context: Context, props: dict[str, Any]) -> str:
        # React Content renders an empty Slots provider around its children so nested layout
        # primitives do not inherit slots intended for Content's surrounding component.
        with replace_slot_scope(context, {}):
            return self.render_children(context)


class UIHeadingRenderer(UILayoutPartRenderer):
    apui_component_name = "heading"
    slot_name = "heading"
    tag_name = "h3"
    supported_props = UILayoutPartRenderer.supported_props | frozenset({"level"})
    prop_rules = {"level": enum_prop_rule((1, 2, 3, 4, 5, 6), invalid_fallback=3)}

    def render_component(self, context: Context, props: dict[str, Any], children_html: str) -> str:
        attrs = {
            **self.collect_forwarded_props(props),
            "className": props.get("className"),
            "style": props.get("style"),
        }
        return self._render_tag(f"h{props.get('level', 3)}", attrs, children_html)


class UIHeaderRenderer(UILayoutPartRenderer):
    apui_component_name = "header"
    slot_name = "header"
    tag_name = "header"


class UIFooterRenderer(UILayoutPartRenderer):
    apui_component_name = "footer"
    slot_name = "footer"
    tag_name = "footer"
