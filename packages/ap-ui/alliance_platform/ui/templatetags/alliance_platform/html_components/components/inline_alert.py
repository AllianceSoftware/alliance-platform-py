"""Static HTML renderers for Alliance UI inline alerts.

Loose children are wrapped in the same ``Content`` section used by the legacy Django tag. Generic
layout primitives participate in the component's slot styling without requiring a React root.
Dismiss buttons are deliberately unsupported because their state transition requires client-side
behaviour.
"""

from __future__ import annotations

import re
from typing import Any
from typing import Mapping

from django.template import Context

from alliance_platform.frontend.bundler.frontend_resource import FrontendResource
from alliance_platform.frontend.bundler.frontend_resource import ImageResource
from alliance_platform.ui.icons import get_static_icon_resource

from ..base import BaseHtmlUIComponentRenderer
from ..base import enum_prop_rule
from ..static_icon import ICON_STYLE_PATH
from ..static_icon import render_static_icon

_INLINE_ALERT_STYLE_PATH = "@alliancesoftware/ui/components/inline-alert/InlineAlert.css.ts"

VALID_INTENTS = ("danger", "warning", "info", "success", "default")
_INTENT_ICONS = {
    "danger": "AlertCircleOutlined",
    "warning": "AlertTriangleOutlined",
    "info": "InfoCircleOutlined",
    "success": "CheckCircleOutlined",
    "default": "InfoCircleOutlined",
}

_EVENT_HANDLER_REASON = "event handlers are not supported by static inline-alert components"
_DISMISS_REASON = "dismissible alerts require client-side state and are not supported statically"
_ROOT_FORWARDED_PROPS = frozenset({"id", "title", "role", "tabIndex", "dir", "lang", "hidden", "draggable"})


class UIInlineAlertRenderer(BaseHtmlUIComponentRenderer):
    apui_component_name = "inline-alert"
    supported_props = frozenset(
        {
            "intent",
            "hideIcon",
            "isDismissed",
            "className",
            "style",
            "children",
        }
    )
    forwarded_props = _ROOT_FORWARDED_PROPS
    allow_data_props = True
    allow_aria_props = True
    prop_filter_context = "static inline-alert components"
    event_handler_prop_reason = _EVENT_HANDLER_REASON
    unsupported_prop_reasons: Mapping[str, str] = {
        "isDismissable": _DISMISS_REASON,
        "onDismiss": _DISMISS_REASON,
    }
    prop_rules = {"intent": enum_prop_rule(VALID_INTENTS, invalid_fallback="default")}

    def resolve_component_resources(self) -> list[FrontendResource]:
        resources = [
            self.resolve_frontend_resource(_INLINE_ALERT_STYLE_PATH),
            self.resolve_frontend_resource(ICON_STYLE_PATH),
        ]
        resources.extend(
            get_static_icon_resource(icon_name, origin=self.origin)
            for icon_name in dict.fromkeys(_INTENT_ICONS.values())
        )
        return resources

    def get_resources_to_embed(self) -> list[FrontendResource]:
        return [
            resource
            for resource in self.get_resources_for_bundling()
            if not isinstance(resource, ImageResource)
        ]

    def render_children_for_component(self, context: Context, props: dict[str, Any]) -> str:
        styles = self.resolve_vanilla_extract_mapping(_INLINE_ALERT_STYLE_PATH)
        return self.render_children(
            context,
            slot_overrides={
                "buttonGroup": {"className": self.get_style_class(styles, "buttonGroup")},
                "content": {"className": self.get_style_class(styles, "content")},
                "footer": {"className": self.get_style_class(styles, "footer")},
                "header": {"className": self.get_style_class(styles, "header")},
                "heading": {"className": self.get_style_class(styles, "heading"), "level": 3},
                "icon": {
                    "className": self.get_style_class(styles, "icon"),
                    "data-alerticon": 1,
                },
            },
        )

    def render_component(self, context: Context, props: dict[str, Any], children_html: str) -> str:
        if props.get("isDismissed"):
            return ""

        intent = str(props.get("intent", "default"))
        styles = self.resolve_vanilla_extract_mapping(_INLINE_ALERT_STYLE_PATH)

        part_classes = {
            name: self.get_style_class(styles, name)
            for name in ("buttonGroup", "content", "footer", "header", "heading")
        }
        has_structured_child = any(
            self._has_class(children_html, class_name) for class_name in part_classes.values() if class_name
        )
        if has_structured_child:
            content_html = children_html
            only_content = self._contains_only_content(children_html, part_classes)
        else:
            content_html = self._render_tag(
                "section",
                {"className": part_classes["content"]},
                children_html,
            )
            only_content = True

        has_icon = 'data-alerticon="1"' in content_html
        if not props.get("hideIcon") and not has_icon:
            icon_html = render_static_icon(
                self,
                name=_INTENT_ICONS[intent],
                size="xs",
                slot=None,
                class_name=self.get_style_class(styles, "icon"),
                attrs={"data-alerticon": 1},
            )
            content_html = f"{icon_html}{content_html}"

        inner_class_name = self.join_classes(
            self.get_nested_style_class(styles, "alert", intent)
            or self.get_nested_style_class(styles, "alert", "default"),
            self.get_style_class(styles, "onlyContent") if only_content else None,
        )
        inner_html = self._render_tag("div", {"className": inner_class_name}, content_html)

        attrs: dict[str, Any] = {
            **self.collect_forwarded_props(props),
            "data-apui": "inline-alert",
            "data-intent": intent,
            "data-only-content": "true" if only_content else None,
            "className": self.join_classes(
                self.get_style_class(styles, "wrapper"),
                props.get("className"),
            ),
            "style": props.get("style"),
            # InlineAlert always exposes alert semantics, even if a different role is supplied.
            "role": "alert",
        }
        return self._render_tag("div", attrs, inner_html)

    @staticmethod
    def _has_class(html: str, class_name: str) -> bool:
        return any(class_name in value.split() for value in re.findall(r'class=["\']([^"\']*)["\']', html))

    def _contains_only_content(self, html: str, part_classes: dict[str, str]) -> bool:
        if not self._has_class(html, part_classes["content"]):
            return False
        return not any(
            self._has_class(html, class_name)
            for name, class_name in part_classes.items()
            if name != "content" and class_name
        )
