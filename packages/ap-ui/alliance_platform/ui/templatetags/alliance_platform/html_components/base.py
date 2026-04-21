from __future__ import annotations

from pathlib import Path
import re
from typing import Any
import warnings

from allianceutils.util import underscore_to_camel
from django import template
from django.template import Context
from django.template import Origin
from django.template.base import UNKNOWN_SOURCE
from django.template.base import FilterExpression
from django.template.base import NodeList
from django.utils.html import conditional_escape
from django.utils.safestring import mark_safe

from alliance_platform.frontend.bundler import get_bundler
from alliance_platform.frontend.bundler.base import ResolveContext
from alliance_platform.frontend.bundler.context import BundlerAsset
from alliance_platform.frontend.bundler.frontend_resource import FrontendResource
from alliance_platform.frontend.bundler.vanilla_extract import resolve_vanilla_extract_class_mapping
from alliance_platform.frontend.templatetags.react import DeferredProp

from .slots import get_slot_context
from .slots import merge_slot_props
from .slots import push_slot_scope

_REACT_ATTR_TO_HTML_ATTR = {
    "className": "class",
    "htmlFor": "for",
    "formAction": "formaction",
    "formMethod": "formmethod",
    "formEncType": "formenctype",
    "formNoValidate": "formnovalidate",
    "formTarget": "formtarget",
    "tabIndex": "tabindex",
}

_CAMEL_CASE_SPLIT_RE = re.compile(r"([a-z0-9])([A-Z])")


class BaseHtmlUIComponentRenderer(template.Node, BundlerAsset):
    """Base node for HTML-only UI components dispatched by ``{% ui %}``."""

    slot_name: str | None = None

    def __init__(
        self,
        *,
        props: dict[str, Any],
        nodelist: NodeList,
        origin: Origin | None,
        target_var: str | None,
        register_asset: bool = True,
    ):
        self.props = props
        self.nodelist = nodelist
        self.target_var = target_var
        self._register_asset = register_asset
        resolved_origin = origin or Origin(UNKNOWN_SOURCE)
        if register_asset:
            super().__init__(resolved_origin)
        else:
            self.origin = resolved_origin
            self.bundler = get_bundler()

    def resolve_component_resources(self) -> list[FrontendResource]:
        return []

    def get_resources_for_bundling(self) -> list[FrontendResource]:
        return self.resolve_component_resources()

    def get_slot_name(self) -> str | None:
        return self.slot_name

    def render(self, context: Context) -> str:
        if not self._register_asset:
            raise RuntimeError(
                "Cannot render a renderer initialised with register_asset=False. "
                "This mode is for resource introspection only."
            )
        self._queue_resources()
        props = self.resolve_props(context)
        props = self._merge_slot_props(context, props)
        children_html = self.render_children(context)
        rendered = self.render_component(context, props, children_html)
        if self.target_var:
            context[self.target_var] = rendered
            return ""
        return rendered

    def resolve_props(self, context: Context) -> dict[str, Any]:
        resolved_props: dict[str, Any] = {}
        for key, value in self.props.items():
            normalized_key = self._normalize_prop_key(key)
            resolved_value = self.resolve_prop_value(context, value)
            if normalized_key == "className" and normalized_key in resolved_props:
                existing = resolved_props.get(normalized_key)
                resolved_props[normalized_key] = self.join_classes(
                    str(existing) if existing else None,
                    str(resolved_value) if resolved_value else None,
                )
                continue
            resolved_props[normalized_key] = resolved_value
        return resolved_props

    def resolve_prop_value(self, context: Context, value: Any) -> Any:
        if isinstance(value, FilterExpression):
            return self.resolve_prop_value(context, value.resolve(context))
        if isinstance(value, DeferredProp):
            return value.resolve(context)
        if isinstance(value, NodeList):
            return value.render(context)
        return value

    def render_children(
        self,
        context: Context,
        slot_overrides: dict[str, dict[str, Any]] | None = None,
    ) -> str:
        if slot_overrides:
            with push_slot_scope(context, slot_overrides):
                return self.nodelist.render(context)
        return self.nodelist.render(context)

    def render_component(self, context: Context, props: dict[str, Any], children_html: str) -> str:
        raise NotImplementedError

    def resolve_resource_path(self, path: str, resolve_extensions: list[str] | None = None) -> Path:
        resolver_context = ResolveContext(self.bundler.root_dir, self.origin.name if self.origin else None)
        return self.bundler.resolve_path(path, resolver_context, resolve_extensions=resolve_extensions)

    def resolve_optional_resource_path(
        self,
        path: str,
        resolve_extensions: list[str] | None = None,
    ) -> Path | None:
        try:
            return self.resolve_resource_path(path, resolve_extensions=resolve_extensions)
        except template.TemplateSyntaxError:
            return None

    def resolve_frontend_resource(
        self,
        path: str,
        resolve_extensions: list[str] | None = None,
    ) -> FrontendResource:
        return FrontendResource.from_path(
            self.resolve_resource_path(path, resolve_extensions=resolve_extensions)
        )

    def resolve_vanilla_extract_mapping(
        self,
        path: str,
        resolve_extensions: list[str] | None = None,
    ):
        style_path = self.resolve_resource_path(path, resolve_extensions=resolve_extensions)
        return resolve_vanilla_extract_class_mapping(self.bundler, style_path)

    def get_style_class(self, mapping: Any, key: str) -> str:
        value = getattr(mapping, key, "")
        return value if isinstance(value, str) else ""

    def get_nested_style_class(self, mapping: Any, key: str, nested_key: str) -> str:
        mapping_value = getattr(mapping, key, {})
        if isinstance(mapping_value, dict) or hasattr(mapping_value, "get"):
            nested_value = mapping_value.get(nested_key, "")
            return nested_value if isinstance(nested_value, str) else ""
        return ""

    def validate_enum_prop(
        self,
        props: dict[str, Any],
        *,
        prop_name: str,
        valid_values: tuple[str, ...],
        default_value: str,
    ) -> str:
        value = props.get(prop_name, default_value)
        if value in valid_values:
            return str(value)
        warnings.warn(f"Invalid '{prop_name}' prop passed: {value}")
        return default_value

    def build_attrs_string(self, attrs: dict[str, Any]) -> str:
        rendered_attrs: list[str] = []
        for name, value in attrs.items():
            if value is None or value is False:
                continue
            attr_name = self._to_html_attr_name(name)
            if name == "style" and isinstance(value, dict):
                value = self._style_dict_to_string(value)
            if value is True:
                rendered_attrs.append(f" {conditional_escape(attr_name)}")
            else:
                rendered_attrs.append(f' {conditional_escape(attr_name)}="{conditional_escape(value)}"')
        return "".join(rendered_attrs)

    def join_classes(self, *class_names: str | None) -> str:
        return " ".join(class_name for class_name in class_names if class_name)

    def _normalize_prop_key(self, key: str) -> str:
        if key in {"class", "class_name"}:
            return "className"
        if key.startswith("data_"):
            return f"data-{key[5:].replace('_', '-')}"
        if key.startswith("aria_"):
            return f"aria-{key[5:].replace('_', '-')}"
        return underscore_to_camel(key)

    def _to_html_attr_name(self, key: str) -> str:
        if key in _REACT_ATTR_TO_HTML_ATTR:
            return _REACT_ATTR_TO_HTML_ATTR[key]
        if "-" in key:
            return key
        if key.startswith("aria") and len(key) > 4 and key[4].isupper():
            return "aria-" + self._camel_to_kebab(key[4:])
        if key.startswith("data") and len(key) > 4 and key[4].isupper():
            return "data-" + self._camel_to_kebab(key[4:])
        return key.lower()

    def _camel_to_kebab(self, value: str) -> str:
        return _CAMEL_CASE_SPLIT_RE.sub(r"\1-\2", value).replace("_", "-").lower()

    def _style_dict_to_string(self, style: dict[str, Any]) -> str:
        declarations = []
        for key, value in style.items():
            css_key = key if key.startswith("--") else self._camel_to_kebab(str(key))
            declarations.append(f"{css_key}: {value}")
        return "; ".join(declarations)

    def _merge_slot_props(self, context: Context, child_props: dict[str, Any]) -> dict[str, Any]:
        slot_name = self.get_slot_name()
        if not slot_name:
            return child_props
        slot_context = get_slot_context(context)
        return merge_slot_props(slot_context.get(slot_name), child_props)

    def _queue_resources(self):
        for item in self.bundler.get_embed_items(self.get_resources_for_bundling()):
            self.bundler_asset_context.queue_embed_file(item)

    def _render_tag(self, tag_name: str, attrs: dict[str, Any], children_html: str = "") -> str:
        attrs_html = self.build_attrs_string(attrs)
        return mark_safe(f"<{tag_name}{attrs_html}>{children_html}</{tag_name}>")
