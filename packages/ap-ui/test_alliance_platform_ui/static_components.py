"""A project-defined static component: the worked example in the static component authoring guide.

``{% ui "stat" %}`` renders a labelled figure. Its value is a ``{% ui "stat_value" %}`` part that
can sit anywhere inside it, and a child ``{% ui "icon" %}`` picks up the stat's icon styling.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from alliance_platform.frontend.bundler.frontend_resource import FrontendResource
from alliance_platform.ui.html_components.base import BaseHtmlUIComponentRenderer
from alliance_platform.ui.html_components.base import enum_prop_rule
from alliance_platform.ui.html_components.render_context import ChildReport
from alliance_platform.ui.html_components.render_context import RenderFrame
from alliance_platform.ui.html_components.render_context import collect_child_reports
from alliance_platform.ui.html_components.render_context import find_render_payload
from alliance_platform.ui.html_components.render_context import get_current_component_frame
from django.template import Context
from django.utils.html import conditional_escape

STAT_STYLES = "frontend/src/components/Stat.css.ts"

#: Icon size for each stat size; an icon's own ``size`` prop still wins
ICON_SIZES = {"md": "xs", "lg": "sm"}


@dataclass
class StatPayload:
    """State a stat shares with the parts rendered inside it."""

    size: str


class StatRenderer(BaseHtmlUIComponentRenderer):
    name = "stat"
    supported_props = frozenset({"label", "size", "className", "style"})
    prop_rules = {"size": enum_prop_rule(("md", "lg"), invalid_fallback="md")}
    forwarded_props = frozenset({"id", "title"})
    allow_data_props = True
    prop_filter_context = "static stat components"
    event_handler_prop_reason = "event handlers are not supported by static stat components"

    def resolve_component_resources(self) -> list[FrontendResource]:
        return [self.resolve_frontend_resource(STAT_STYLES)]

    def build_render_frame(self, context: Context, props: dict[str, Any]) -> RenderFrame:
        # Parts find the payload with find_render_payload() at any depth below the stat
        return RenderFrame(component=self.name, payload=StatPayload(size=props.get("size", "md")))

    def render_children_for_component(self, context: Context, props: dict[str, Any]) -> str:
        styles = self.resolve_vanilla_extract_mapping(STAT_STYLES)
        icon_defaults = {
            "size": ICON_SIZES[props.get("size", "md")],
            "className": self.get_style_class(styles, "icon"),
        }
        # Opt in to reports from direct children so render_component can see what rendered
        with collect_child_reports(context):
            return self.render_children(context, slot_overrides={"icon": icon_defaults})

    def render_component(self, context: Context, props: dict[str, Any], children_html: str) -> str:
        styles = self.resolve_vanilla_extract_mapping(STAT_STYLES)
        frame = get_current_component_frame(context)
        reports = frame.child_reports if frame is not None else []
        has_value = any(report.component == "stat_value" for report in reports)

        label_html = self.render_tag(
            "span",
            {"className": self.get_style_class(styles, "label")},
            conditional_escape(props.get("label", "")),
        )
        attrs = {
            **self.collect_forwarded_props(props),
            "data-apui": self.apui_name,
            "data-size": props.get("size", "md"),
            "data-empty": None if has_value else "true",
            "className": self.join_classes(self.get_style_class(styles, "stat"), props.get("className")),
            "style": props.get("style"),
        }
        return self.render_tag("div", attrs, f"{label_html}{children_html}")


class StatValueRenderer(BaseHtmlUIComponentRenderer):
    name = "stat_value"
    supported_props = frozenset({"className"})
    prop_filter_context = "static stat components"
    event_handler_prop_reason = "event handlers are not supported by static stat components"

    def resolve_component_resources(self) -> list[FrontendResource]:
        return [self.resolve_frontend_resource(STAT_STYLES)]

    def render_component(self, context: Context, props: dict[str, Any], children_html: str) -> str:
        payload = find_render_payload(context, StatPayload)
        if payload is None:
            self.report(
                "'stat_value' was rendered outside of a 'stat' component; rendering nothing", kind="contract"
            )
            return ""
        styles = self.resolve_vanilla_extract_mapping(STAT_STYLES)
        attrs = {
            "data-apui": self.apui_name,
            "className": self.join_classes(
                self.get_nested_style_class(styles, "value", payload.size),
                props.get("className"),
            ),
        }
        return self.render_tag("span", attrs, children_html)

    def build_child_report(self, context: Context, props: dict[str, Any], rendered: str) -> ChildReport:
        return ChildReport(component=self.name, html=rendered)
