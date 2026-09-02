from __future__ import annotations

from typing import Any
import warnings

from allianceutils.template import is_static_expression
from django.template import Context
from django.template import TemplateSyntaxError
from django.template.base import FilterExpression

from alliance_platform.frontend.bundler.frontend_resource import FrontendResource
from alliance_platform.frontend.bundler.frontend_resource import ImageResource
from alliance_platform.ui.icons import get_static_icon_resource
from alliance_platform.ui.icons import validate_icon_name

from ..base import BaseHtmlUIComponentRenderer
from ..static_icon import ICON_STYLE_PATH
from ..static_icon import render_static_icon


class UIIconRenderer(BaseHtmlUIComponentRenderer):
    apui_component_name = "icon"
    slot_name = "icon"
    supported_props = frozenset({"name", "size", "variant", "color", "slot", "className"})
    forwarded_props = frozenset({"id", "title", "style"})
    allow_data_props = True
    allow_aria_props = True
    prop_filter_context = "static icon components"
    event_handler_prop_reason = "event handlers are not supported by static icon components"

    def resolve_component_resources(self) -> list[FrontendResource]:
        name = self._resolve_static_icon_name()
        return [
            self.resolve_frontend_resource(ICON_STYLE_PATH),
            get_static_icon_resource(name, origin=self.origin),
        ]

    def get_resources_to_embed(self) -> list[FrontendResource]:
        # The SVG remains a bundling dependency, but render_static_icon reads it and emits its
        # markup inline. Passing it to the bundler's embed pipeline would emit a second <img>.
        return [
            resource
            for resource in self.get_resources_for_bundling()
            if not isinstance(resource, ImageResource)
        ]

    def render_component(self, context: Context, props: dict[str, Any], children_html: str) -> str:
        if children_html.strip():
            warnings.warn("'icon' does not support children; the content will be ignored")

        props = dict(props)
        name = props.pop("name", None)
        if not isinstance(name, str):
            warnings.warn("'icon' requires a string 'name' prop and will not render")
            return ""

        size = props.pop("size", "xs")
        variant = props.pop("variant", "plain")
        color = props.pop("color", None)
        slot = props.pop("slot", "icon")
        class_name = props.pop("className", None)
        aria_label = props.pop("aria-label", None)
        aria_hidden = props.pop("aria-hidden", None)
        attrs = self.collect_forwarded_props(props)

        try:
            return render_static_icon(
                self,
                name=name,
                size=str(size),
                variant=str(variant),
                color=str(color) if color is not None else None,
                aria_label=str(aria_label) if aria_label else None,
                aria_hidden=aria_hidden,
                slot=slot,
                class_name=str(class_name) if class_name else None,
                attrs=attrs,
            )
        except (FileNotFoundError, TemplateSyntaxError, ValueError) as exc:
            warnings.warn(f"Could not render static icon '{name}': {exc}")
            return ""

    def _resolve_static_icon_name(self) -> str:
        raw_name = self.props.get("name")
        if raw_name is None:
            raise TemplateSyntaxError("'icon' requires a static 'name' prop")
        if isinstance(raw_name, FilterExpression):
            if not is_static_expression(raw_name):
                raise TemplateSyntaxError("'icon' requires 'name' to be a static string literal")
            raw_name = raw_name.resolve(Context())
        if not isinstance(raw_name, str):
            raise TemplateSyntaxError(
                f"'icon' static 'name' prop must resolve to a string, received {type(raw_name).__name__}"
            )
        if raw_name != raw_name.strip():
            raise TemplateSyntaxError("'icon' name cannot contain leading or trailing whitespace")
        try:
            validate_icon_name(raw_name)
        except ValueError as exc:
            raise TemplateSyntaxError(str(exc)) from exc
        return raw_name
