from __future__ import annotations

from typing import Any

from django.template import Context

from alliance_platform.frontend.bundler.frontend_resource import FrontendResource

from ..base import BaseHtmlUIComponentRenderer
from ..runtime import attach_module_script

VALID_ORIENTATIONS = ("horizontal", "vertical")
VALID_ALIGNS = ("start", "center", "end")
VALID_DENSITIES = ("compact", "xxs", "xs", "sm", "md", "lg", "xl", "xxl", "xxxl")

_BUTTON_GROUP_STYLE_PATH = "@alliancesoftware/ui/components/button/ButtonGroup.css.ts"
_SMART_ORIENTATION_STYLE_PATH = "@alliancesoftware/ui/components/layout/SmartOrientation.css.ts"
# The runtime module is optional for now; if unresolved at parse time we degrade gracefully to static HTML.
_RUNTIME_MODULE_PATH = "@alliancesoftware/ui/components/layout/SmartOrientation.attach.ts"


class UIButtonGroupRenderer(BaseHtmlUIComponentRenderer):
    def resolve_component_resources(self) -> list[FrontendResource]:
        resources: list[FrontendResource] = [
            self.resolve_frontend_resource(_BUTTON_GROUP_STYLE_PATH),
            self.resolve_frontend_resource(_SMART_ORIENTATION_STYLE_PATH),
        ]
        runtime_resource = self._resolve_runtime_resource()
        if runtime_resource:
            resources.append(runtime_resource)
        return resources

    def render_component(self, context: Context, props: dict[str, Any], children_html: str) -> str:
        if not children_html.strip():
            return ""

        orientation = self.validate_enum_prop(
            props,
            prop_name="orientation",
            valid_values=VALID_ORIENTATIONS,
            default_value="horizontal",
        )
        align = self.validate_enum_prop(
            props,
            prop_name="align",
            valid_values=VALID_ALIGNS,
            default_value="start",
        )

        density_prop_present = "density" in props and props.get("density") is not None
        density = self.validate_enum_prop(
            props,
            prop_name="density",
            valid_values=VALID_DENSITIES,
            default_value="md",
        )

        group_styles = self.resolve_vanilla_extract_mapping(_BUTTON_GROUP_STYLE_PATH)
        smart_orientation_styles = self.resolve_vanilla_extract_mapping(_SMART_ORIENTATION_STYLE_PATH)

        container_class_name = self.get_nested_style_class(smart_orientation_styles, "container", orientation)
        align_class_name = self.get_nested_style_class(smart_orientation_styles, "align", align)
        density_class_name = self.get_nested_style_class(smart_orientation_styles, "density", density)
        button_group_class_name = self.get_style_class(group_styles, "buttonGroup")
        button_slot_class_name = self.get_style_class(group_styles, "button")

        class_name = self.join_classes(
            container_class_name,
            align_class_name,
            density_class_name,
            button_group_class_name,
            props.get("className"),
        )

        slot_defaults: dict[str, Any] = {}
        for key in ("isDisabled", "color", "variant", "size"):
            if key in props and props[key] is not None:
                slot_defaults[key] = props[key]
        if button_slot_class_name:
            slot_defaults["className"] = button_slot_class_name

        children_html = self.render_children(context, slot_overrides={"button": slot_defaults})

        attrs: dict[str, Any] = {
            "className": class_name,
            "data-apui": "button-group",
            "data-orientation": orientation,
            "data-density": density if density_prop_present else None,
            "data-align": props.get("align") if props.get("align") is not None else None,
            "id": props.get("id"),
            "style": props.get("style"),
        }

        runtime_resource = self._resolve_runtime_resource()
        script_html = ""
        if runtime_resource is not None:
            script_html = attach_module_script(runtime_resource, attrs)

        return f"{self._render_tag('div', attrs, children_html)}{script_html}"

    def _resolve_runtime_resource(self) -> FrontendResource | None:
        runtime_path = self.resolve_optional_resource_path(
            _RUNTIME_MODULE_PATH,
            resolve_extensions=[".ts", ".tsx", ".js", ".mjs"],
        )
        if runtime_path is None:
            return None
        return FrontendResource.from_path(runtime_path)
