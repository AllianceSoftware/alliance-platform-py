from __future__ import annotations

from typing import TYPE_CHECKING
from typing import Any
import warnings

from django.utils.safestring import mark_safe

from alliance_platform.ui.icons import get_static_icon_definition

if TYPE_CHECKING:
    from .base import BaseHtmlUIComponentRenderer

ICON_STYLE_PATH = "@alliancesoftware/icons/Icon.css.ts"

ICON_SIZES = ("xxs", "xs", "sm", "md", "lg", "xl")
ICON_VARIANTS = ("plain", "circle", "circle-outlined")
ICON_COLORS = ("primary", "secondary", "warning", "destructive", "success")


def is_event_handler_attr(name: str) -> bool:
    return name.lower().startswith("on")


def render_static_icon(
    renderer: "BaseHtmlUIComponentRenderer",
    *,
    name: str,
    size: str = "xs",
    variant: str = "plain",
    color: str | None = None,
    aria_label: str | None = None,
    aria_hidden: Any = None,
    slot: str | None | bool = "icon",
    class_name: str | None = None,
    extra_class_names: list[str] | None = None,
    attrs: dict[str, Any] | None = None,
) -> str:
    if size not in ICON_SIZES:
        warnings.warn(f"Invalid 'size' prop passed: {size}")
        size = "xs"
    if variant not in ICON_VARIANTS:
        warnings.warn(f"Invalid 'variant' prop passed: {variant}")
        variant = "plain"
    if color is not None and color not in ICON_COLORS:
        warnings.warn(f"Invalid 'color' prop passed: {color}")
        color = None
    if color is None and variant != "plain":
        color = "secondary"

    icon_styles = renderer.resolve_vanilla_extract_mapping(ICON_STYLE_PATH)
    wrapper_class_name = renderer.join_classes(
        renderer.get_style_class(icon_styles, "icon"),
        renderer.get_nested_style_class(icon_styles, "variants", variant),
        renderer.get_nested_style_class(icon_styles, "colors", color) if color else None,
        renderer.get_nested_style_class(icon_styles, "sizes", size),
        *(extra_class_names or []),
        class_name,
    )
    wrapper_attrs: dict[str, Any] = {"role": "img"}
    if aria_label:
        wrapper_attrs["aria-label"] = aria_label
    if aria_hidden is not None:
        if isinstance(aria_hidden, bool):
            aria_hidden = "true" if aria_hidden else "false"
        wrapper_attrs["aria-hidden"] = aria_hidden
    elif not aria_label and "aria-hidden" not in (attrs or {}):
        wrapper_attrs["aria-hidden"] = "true"
    if slot is not None and slot is not False:
        wrapper_attrs["data-apui-slot"] = slot
    wrapper_attrs["class"] = wrapper_class_name
    wrapper_attrs.update(attrs or {})

    for attr_name in list(wrapper_attrs.keys()):
        if is_event_handler_attr(attr_name):
            warnings.warn(
                f"Event handler prop '{attr_name}' is not supported by static icon components and will be ignored"
            )
            del wrapper_attrs[attr_name]

    svg_markup = get_static_icon_definition(name, origin=renderer.origin).svg_markup
    return mark_safe(f"<span{renderer.build_attrs_string(wrapper_attrs)}>{svg_markup}</span>")
