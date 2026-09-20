from __future__ import annotations

import re
from typing import Any
import warnings

from django.template import Context
from django.utils.html import conditional_escape
from django.utils.safestring import mark_safe

from alliance_platform.frontend.bundler.frontend_resource import FrontendResource

from ..base import BaseHtmlUIComponentRenderer

VALID_VARIANTS = ("solid", "outlined", "plain", "light", "link")
VALID_COLORS = ("primary", "secondary", "destructive", "gray")
VALID_SIZES = ("sm", "md", "lg", "xl", "2xl")
VALID_SHAPES = ("default", "circle")

_BUTTON_STYLE_PATH = "@alliancesoftware/ui/components/button/Button.css.ts"
_FOCUS_RING_STYLE_PATH = "@alliancesoftware/ui/styles/base/focusRing.css.ts"

_ICON_ONLY_RE = re.compile(r"^\s*<[^>]+data-apui-slot=([\"'])icon\1[^>]*>.*</[^>]+>\s*$", re.DOTALL)


class UIButtonRenderer(BaseHtmlUIComponentRenderer):
    slot_name = "button"

    def resolve_component_resources(self) -> list[FrontendResource]:
        return [
            self.resolve_frontend_resource(_BUTTON_STYLE_PATH),
            self.resolve_frontend_resource(_FOCUS_RING_STYLE_PATH),
        ]

    def render_component(self, context: Context, props: dict[str, Any], children_html: str) -> str:
        variant = self.validate_enum_prop(
            props,
            prop_name="variant",
            valid_values=VALID_VARIANTS,
            default_value="solid",
        )
        color = self.validate_enum_prop(
            props,
            prop_name="color",
            valid_values=VALID_COLORS,
            default_value="primary",
        )
        size = self.validate_enum_prop(
            props,
            prop_name="size",
            valid_values=VALID_SIZES,
            default_value="md",
        )
        shape = self.validate_enum_prop(
            props,
            prop_name="shape",
            valid_values=VALID_SHAPES,
            default_value="default",
        )

        if "disabled" in props and "isDisabled" not in props:
            warnings.warn("You passed 'disabled' - use 'isDisabled' instead")

        is_disabled = bool(props.get("isDisabled") or props.get("disabled"))

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
        element_type = props.get("elementType")
        if not isinstance(element_type, str):
            element_type = "a" if href else "button"
        tag_name = element_type

        if href is not None:
            attrs["href"] = href
        if is_disabled and tag_name == "button":
            attrs["disabled"] = True

        pass_through_keys = {
            "id",
            "name",
            "type",
            "value",
            "title",
            "role",
            "target",
            "rel",
            "tabIndex",
            "form",
            "formAction",
            "formMethod",
            "formEncType",
            "formNoValidate",
            "formTarget",
            "aria-label",
            "aria-describedby",
            "aria-controls",
            "aria-expanded",
            "aria-current",
            "data-testid",
        }
        handled_props = {
            "variant",
            "color",
            "size",
            "shape",
            "className",
            "style",
            "isDisabled",
            "disabled",
            "href",
            "elementType",
            "children",
            "slot",
            "autoFocus",
        }

        for key, value in props.items():
            if key in handled_props:
                continue
            if key in pass_through_keys or key.startswith("data-") or key.startswith("aria-"):
                attrs[key] = value

        normalized_children = self._normalize_children(children_html)
        if self._is_icon_only(normalized_children):
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
