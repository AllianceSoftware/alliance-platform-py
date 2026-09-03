from __future__ import annotations

import re
from typing import Any

from django.template import Context
from django.utils.html import conditional_escape
from django.utils.safestring import mark_safe

from alliance_platform.frontend.bundler.frontend_resource import FrontendResource

from ..base import BaseHtmlUIComponentRenderer
from ..base import enum_prop_rule
from ..base import typed_prop_rule

VALID_VARIANTS = ("solid", "outlined", "plain", "light", "link")
VALID_COLORS = ("primary", "secondary", "destructive", "gray")
VALID_SIZES = ("sm", "md", "lg", "xl", "2xl")
VALID_SHAPES = ("default", "circle")

DEFAULT_ICON_SIZE_MAPPING = {
    "sm": "xxs",
    "md": "xxs",
    "lg": "xs",
    "xl": "xs",
    "2xl": "xs",
}

BUTTON_PROP_RULES = {
    "variant": enum_prop_rule(VALID_VARIANTS, invalid_fallback="solid"),
    "color": enum_prop_rule(VALID_COLORS, invalid_fallback="primary"),
    "size": enum_prop_rule(VALID_SIZES, invalid_fallback="md"),
    "shape": enum_prop_rule(VALID_SHAPES, invalid_fallback="default"),
}

_BUTTON_STYLE_PATH = "@alliancesoftware/ui/components/button/Button.css.ts"
_FOCUS_RING_STYLE_PATH = "@alliancesoftware/ui/styles/base/focusRing.css.ts"

_ICON_ONLY_RE = re.compile(r"^\s*<[^>]+data-apui-slot=([\"'])icon\1[^>]*>.*</[^>]+>\s*$", re.DOTALL)
_HTML_TAG_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9-]*$")

_BUTTON_FORWARDED_PROPS = frozenset(
    {
        "id",
        "name",
        "type",
        "value",
        "title",
        "role",
        "target",
        "rel",
        "download",
        "tabIndex",
        "form",
        "formAction",
        "formMethod",
        "formEncType",
        "formNoValidate",
        "formTarget",
        "autoFocus",
    }
)


class UIButtonRenderer(BaseHtmlUIComponentRenderer):
    apui_component_name = "button"
    slot_name = "button"
    supported_props = frozenset(
        {
            "variant",
            "color",
            "size",
            "shape",
            "className",
            "style",
            "isDisabled",
            "href",
            "elementType",
            "children",
            "slot",
            "isIconOnly",
        }
    )
    forwarded_props = _BUTTON_FORWARDED_PROPS
    allow_data_props = True
    allow_aria_props = True
    prop_filter_context = "static button components"
    event_handler_prop_reason = "event handlers are not supported by static button components"
    deprecated_prop_aliases = {"disabled": "isDisabled"}
    prop_rules = {
        **BUTTON_PROP_RULES,
        "elementType": typed_prop_rule(str, validator=lambda value: bool(_HTML_TAG_NAME_RE.fullmatch(value))),
    }

    def resolve_component_resources(self) -> list[FrontendResource]:
        return [
            self.resolve_frontend_resource(_BUTTON_STYLE_PATH),
            self.resolve_frontend_resource(_FOCUS_RING_STYLE_PATH),
        ]

    def render_children_for_component(self, context: Context, props: dict[str, Any]) -> str:
        size = str(props.get("size", "md"))
        return self.render_children(
            context,
            slot_overrides={"icon": {"size": DEFAULT_ICON_SIZE_MAPPING[size]}},
        )

    def render_component(self, context: Context, props: dict[str, Any], children_html: str) -> str:
        variant = str(props.get("variant", "solid"))
        color = str(props.get("color", "primary"))
        size = str(props.get("size", "md"))
        shape = str(props.get("shape", "default"))
        is_disabled = bool(props.get("isDisabled"))

        button_styles = self.resolve_vanilla_extract_mapping(_BUTTON_STYLE_PATH)
        focus_ring_styles = self.resolve_vanilla_extract_mapping(_FOCUS_RING_STYLE_PATH)

        size_class_name = self.get_nested_style_class(button_styles, "sizes", size)
        class_name = self.join_classes(
            self.get_style_class(focus_ring_styles, "base"),
            self.get_style_class(button_styles, "baseButton"),
            size_class_name,
            props.get("className"),
        )

        attrs: dict[str, Any] = {
            **self.collect_forwarded_props(props),
            "className": class_name,
            "data-apui": "button",
            "data-variant": variant,
            "data-color": color,
            "data-size": size,
            "data-shape": shape,
            "data-disabled": "true" if is_disabled else None,
            "style": props.get("style"),
        }

        href = props.get("href")
        tag_name = str(props.get("elementType") or ("a" if href else "button"))

        if href is not None:
            attrs["href"] = href
        if is_disabled and tag_name == "button":
            attrs["disabled"] = True

        normalized_children = self._normalize_children(children_html)
        explicit_icon_only = props.get("isIconOnly")
        if explicit_icon_only is True or (
            explicit_icon_only is None and self._is_icon_only(normalized_children)
        ):
            attrs["data-icon-only"] = "true"

        return self._render_tag(tag_name, attrs, normalized_children)

    def _normalize_children(self, children_html: str) -> str:
        stripped = children_html.strip()
        if not stripped:
            return ""
        if "<" not in stripped and ">" not in stripped:
            return str(mark_safe(f"<span>{conditional_escape(stripped)}</span>"))
        return children_html

    def _is_icon_only(self, children_html: str) -> bool:
        return bool(_ICON_ONLY_RE.match(children_html.strip()))
