from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
import re
from typing import Any
from typing import Callable
from typing import Mapping
from typing import cast
import warnings

from allianceutils.util import underscore_to_camel
from django import template
from django.template import Context
from django.template import Origin
from django.template.base import UNKNOWN_SOURCE
from django.template.base import FilterExpression
from django.template.base import NodeList
from django.utils.functional import Promise
from django.utils.html import conditional_escape
from django.utils.safestring import mark_safe

from alliance_platform.frontend.bundler import get_bundler
from alliance_platform.frontend.bundler.base import ResolveContext
from alliance_platform.frontend.bundler.context import BundlerAsset
from alliance_platform.frontend.bundler.frontend_resource import FrontendResource
from alliance_platform.frontend.bundler.vanilla_extract import resolve_vanilla_extract_class_mapping
from alliance_platform.frontend.templatetags.react import DeferredProp
from alliance_platform.frontend.templatetags.react import OmitComponentFromRendering
from alliance_platform.frontend.util import transform_attribute_names

from .constants import BULK_PROPS_KWARG
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
    "readOnly": "readonly",
    "autoComplete": "autocomplete",
    "autoCapitalize": "autocapitalize",
    "autoCorrect": "autocorrect",
    "autoFocus": "autofocus",
    "spellCheck": "spellcheck",
    "inputMode": "inputmode",
    "maxLength": "maxlength",
    "minLength": "minlength",
}

_CAMEL_CASE_SPLIT_RE = re.compile(r"([a-z0-9])([A-Z])")
_OMIT_INVALID_PROP = object()

# Extra key adaptations applied to bulk ``props`` dicts (after the standard HTML -> React attribute
# name conversion). Bulk props typically come from HTML attribute dicts such as Django's
# ``widget.attrs``, where boolean state is expressed with the plain HTML attribute names rather
# than the react-aria style props the components accept.
_BULK_PROP_STATE_ALIASES = {
    "disabled": "isDisabled",
    "required": "isRequired",
    "readOnly": "isReadOnly",
}


def normalize_html_ui_prop_name(key: str) -> str:
    """Normalize Django-template spelling to the static renderer prop convention."""
    if key in {"class", "class_name"}:
        return "className"
    if key.startswith("data_"):
        return f"data-{key[5:].replace('_', '-')}"
    if key.startswith("aria_"):
        return f"aria-{key[5:].replace('_', '-')}"
    return underscore_to_camel(key)


@dataclass(frozen=True)
class PropRule:
    """Declarative validation for a supplied component prop.

    Rules validate values that were actually supplied; they deliberately do not add a prop when
    it is absent. This keeps default rendering separate from explicit-prop detection used by slot
    inheritance and data attributes.
    """

    accepted_types: tuple[type, ...] | None = None
    choices: tuple[Any, ...] | None = None
    validator: Callable[[Any], bool] | None = None
    invalid_fallback: Any = _OMIT_INVALID_PROP
    allow_none: bool = False

    def accepts(self, value: Any) -> bool:
        if self.accepted_types is not None and not isinstance(value, self.accepted_types):
            return False
        if self.choices is not None and value not in self.choices:
            return False
        return self.validator(value) if self.validator is not None else True


def enum_prop_rule(
    valid_values: tuple[Any, ...],
    *,
    invalid_fallback: Any = _OMIT_INVALID_PROP,
) -> PropRule:
    """Return a rule for an enum-like prop, optionally normalising invalid values."""
    return PropRule(choices=valid_values, invalid_fallback=invalid_fallback)


def typed_prop_rule(
    *accepted_types: type,
    validator: Callable[[Any], bool] | None = None,
    invalid_fallback: Any = _OMIT_INVALID_PROP,
    allow_none: bool = False,
) -> PropRule:
    """Return a rule for a typed prop with an optional additional validator."""
    return PropRule(
        accepted_types=accepted_types,
        validator=validator,
        invalid_fallback=invalid_fallback,
        allow_none=allow_none,
    )


def camel_to_kebab(value: str) -> str:
    return _CAMEL_CASE_SPLIT_RE.sub(r"\1-\2", value).replace("_", "-").lower()


def to_html_attr_name(key: str) -> str:
    """Convert a React style prop name to the HTML attribute name (``className`` -> ``class``)."""
    if key in _REACT_ATTR_TO_HTML_ATTR:
        return _REACT_ATTR_TO_HTML_ATTR[key]
    if "-" in key:
        return key
    if key.startswith("aria") and len(key) > 4 and key[4].isupper():
        return "aria-" + camel_to_kebab(key[4:])
    if key.startswith("data") and len(key) > 4 and key[4].isupper():
        return "data-" + camel_to_kebab(key[4:])
    return key.lower()


def is_event_handler_attr(name: str) -> bool:
    """Return whether an attribute/prop name could create an inline event handler."""
    return to_html_attr_name(str(name)).lower().startswith("on")


def is_scalar_prop_value(value: Any) -> bool:
    """Return whether a prop can be safely serialized as an HTML attribute value."""
    # Promise covers lazy translation proxies; Decimal covers Django DecimalField values.
    return isinstance(value, (str, int, float, bool, Decimal, Promise)) or value is None


def style_dict_to_string(style: dict[str, Any]) -> str:
    declarations = []
    for key, value in style.items():
        css_key = key if key.startswith("--") else camel_to_kebab(str(key))
        declarations.append(f"{css_key}: {value}")
    return "; ".join(declarations)


def build_attrs_string(attrs: dict[str, Any]) -> str:
    """Render a dict of props/attributes to an escaped HTML attribute string.

    ``None``/``False`` values are omitted, ``True`` renders a bare boolean attribute and React
    style names are converted to their HTML equivalents.
    """
    rendered_attrs: list[str] = []
    for name, value in attrs.items():
        if value is None or value is False:
            continue
        attr_name = to_html_attr_name(name)
        if name == "style" and isinstance(value, dict):
            value = style_dict_to_string(value)
        if value is True:
            rendered_attrs.append(f" {conditional_escape(attr_name)}")
        else:
            rendered_attrs.append(f' {conditional_escape(attr_name)}="{conditional_escape(value)}"')
    return "".join(rendered_attrs)


def get_document_render_context(context: Context) -> dict[str, Any]:
    """Return render state shared by the root template and all included templates.

    Django intentionally isolates the top layer of ``context.render_context`` for every template
    render, including ``{% include %}``. Its base layer lives for the whole document render and is
    the same layer Django itself uses for include-template caching, making it the appropriate home
    for cross-template component composition state and document-unique counters.
    """
    return cast(dict[str, Any], context.render_context.dicts[0])


class BaseHtmlUIComponentRenderer(template.Node, BundlerAsset):
    """Base node for HTML-only UI components dispatched by ``{% ui %}``."""

    slot_name: str | None = None
    #: Props accepted by :meth:`filter_component_props`. ``None`` defers the final prop-name
    #: allowlist to the component (useful for inputs, which split props across several elements).
    supported_props: frozenset[str] | None = None
    unsupported_prop_reasons: Mapping[str, str] = {}
    prop_aliases: Mapping[str, str] = {}
    deprecated_prop_aliases: Mapping[str, str] = {}
    prop_rules: Mapping[str, PropRule] = {}
    #: Ordinary element props copied by :meth:`collect_forwarded_props`. Data/aria props use the
    #: separate allow flags because their names are open-ended.
    forwarded_props: frozenset[str] = frozenset()
    allow_data_props = False
    allow_aria_props = False
    extra_allowed_aria_props: frozenset[str] = frozenset()
    non_scalar_props: frozenset[str] = frozenset()
    none_meaningful_props: frozenset[str] = frozenset()
    prop_filter_context = "static HTML ui components"
    event_handler_prop_reason = "event handlers are not supported by static HTML ui components"

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

    def get_resources_to_embed(self) -> list[FrontendResource]:
        """Return resources that should be embedded into the rendered document.

        Resource discovery and document embedding usually use the same resources, so the default
        preserves that behaviour. Renderers with build-only dependencies can override this hook
        without removing those dependencies from :meth:`get_resources_for_bundling`.
        """
        return self.get_resources_for_bundling()

    def get_slot_name(self) -> str | None:
        return self.slot_name

    def render(self, context: Context) -> str:
        if not self._register_asset:
            raise RuntimeError(
                "Cannot render a renderer initialised with register_asset=False. "
                "This mode is for resource introspection only."
            )
        self._queue_resources()
        try:
            props = self.resolve_props(context)
            props = self._merge_slot_props(context, props)
            props = self.filter_component_props(props)
            children_html = self.render_children_for_component(context, props)
            rendered = self.render_component(context, props, children_html)
        except OmitComponentFromRendering:
            # Matches the React component tags: a prop can raise this to indicate the whole
            # component should not render (e.g. a denied ``url_with_perm`` href). This is expected
            # behaviour so no warning is emitted.
            rendered = ""
        if self.target_var:
            context[self.target_var] = rendered
            return ""
        return rendered

    def resolve_props(self, context: Context) -> dict[str, Any]:
        resolved_props: dict[str, Any] = {}
        bulk_props: Any = None
        for key, value in self.props.items():
            if key == BULK_PROPS_KWARG:
                bulk_props = self.resolve_prop_value(context, value)
                continue
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
        return self._merge_bulk_props(resolved_props, bulk_props)

    def filter_component_props(self, props: dict[str, Any]) -> dict[str, Any]:
        """Apply the shared static-component prop policy.

        Component families configure the policy through the class attributes above. The common
        implementation keeps event-handler refusal, data/aria handling, style validation and
        scalar-value checks consistent while leaving component-specific allowlists declarative.
        """
        filtered: dict[str, Any] = {}
        component_name = self.get_component_prop_name()
        aliased_props: dict[str, Any] = {}
        for original_key, value in props.items():
            key = self.deprecated_prop_aliases.get(
                original_key,
                self.prop_aliases.get(original_key, original_key),
            )
            if original_key in self.deprecated_prop_aliases:
                warnings.warn(f"You passed '{original_key}' - use '{key}' instead")
            if key != original_key and key in props:
                # The canonical spelling always wins when both forms are supplied.
                continue
            aliased_props[key] = value

        for key, value in aliased_props.items():
            rule = self.prop_rules.get(key)
            if value is None:
                if (rule is not None and rule.allow_none) or key in self.none_meaningful_props:
                    if self.is_supported_prop(key):
                        filtered[key] = value
                continue
            reason = self.unsupported_prop_reasons.get(key)
            if reason:
                warnings.warn(f"Prop '{key}' will be ignored: {reason}")
                continue
            if is_event_handler_attr(key):
                warnings.warn(f"Prop '{key}' will be ignored: {self.event_handler_prop_reason}")
                continue
            attr_name = to_html_attr_name(key)
            if attr_name.startswith("data-") or attr_name.startswith("aria-"):
                allowed = (
                    self.allow_data_props
                    if attr_name.startswith("data-")
                    else (self.allow_aria_props or attr_name in self.extra_allowed_aria_props)
                )
                if not allowed:
                    warnings.warn(f"Prop '{key}' is not supported on '{component_name}' and will be ignored")
                    continue
                if not is_scalar_prop_value(value):
                    warnings.warn(
                        f"Prop '{key}' with non-scalar value is not supported by "
                        f"{self.prop_filter_context} and will be ignored"
                    )
                    continue
                filtered[attr_name] = value
                continue
            if not self.is_supported_prop(key):
                warnings.warn(f"Prop '{key}' is not a supported '{component_name}' prop and will be ignored")
                continue
            if rule is not None and not rule.accepts(value):
                warnings.warn(f"Invalid '{key}' prop passed: {value}")
                if rule.invalid_fallback is _OMIT_INVALID_PROP:
                    continue
                value = rule.invalid_fallback
            if key == "style":
                if not isinstance(value, (str, dict)):
                    warnings.warn("Prop 'style' must be a string or dict; it will be ignored")
                    continue
            elif (
                not is_scalar_prop_value(value)
                and rule is None
                and not self.allow_non_scalar_prop(key, value)
            ):
                warnings.warn(
                    f"Prop '{key}' with non-scalar value is not supported by "
                    f"{self.prop_filter_context} and will be ignored"
                )
                continue
            filtered[key] = value
        return filtered

    def is_supported_prop(self, key: str) -> bool:
        return (
            self.supported_props is None
            or key in self.supported_props
            or key in self.prop_rules
            or key in self.forwarded_props
        )

    @classmethod
    def canonical_prop_name(cls, key: str) -> str:
        """Return the prop name after template normalization and renderer aliases."""
        normalized = normalize_html_ui_prop_name(key)
        return cls.deprecated_prop_aliases.get(
            normalized,
            cls.prop_aliases.get(normalized, normalized),
        )

    @classmethod
    def supports_prop_name(cls, key: str) -> bool:
        """Whether a statically known prop is accepted by this renderer's contract."""
        canonical = cls.canonical_prop_name(key)
        if canonical in cls.unsupported_prop_reasons or is_event_handler_attr(canonical):
            return False
        if canonical.startswith("data-"):
            return cls.allow_data_props
        if canonical.startswith("aria-"):
            return cls.allow_aria_props or canonical in cls.extra_allowed_aria_props
        return (
            cls.supported_props is None
            or canonical in cls.supported_props
            or canonical in cls.prop_rules
            or canonical in cls.forwarded_props
        )

    def collect_forwarded_props(self, props: Mapping[str, Any]) -> dict[str, Any]:
        """Collect validated props that a renderer forwards to its root/control element."""
        forwarded: dict[str, Any] = {}
        for key, value in props.items():
            if key in self.forwarded_props:
                forwarded[key] = value
                continue
            if key.startswith("data-") and self.allow_data_props:
                forwarded[key] = value
                continue
            if key.startswith("aria-") and (self.allow_aria_props or key in self.extra_allowed_aria_props):
                forwarded[key] = value
        return forwarded

    def get_component_prop_name(self) -> str:
        name = getattr(self, "component_name", None) or getattr(self, "apui_component_name", None)
        return str(name or self.__class__.__name__)

    def allow_non_scalar_prop(self, key: str, value: Any) -> bool:
        return key in self.non_scalar_props

    def _merge_bulk_props(self, resolved_props: dict[str, Any], bulk_props: Any) -> dict[str, Any]:
        """Merge a dict passed via the ``props`` kwarg into the individually passed props.

        This supports passing dynamic attribute dicts, e.g. Django's ``widget.attrs`` in form widget
        templates. Keys are adapted to the component prop contract: HTML attribute names are
        converted to their React equivalents (``maxlength`` -> ``maxLength``, ``class`` ->
        ``className``), boolean state attributes to their react-aria props (``disabled`` ->
        ``isDisabled``), and the usual template prop normalization is applied.

        Matching the ``{% component %}`` tag, bulk props take precedence over individually passed
        props, except ``className`` values which are merged.
        """
        if bulk_props is None:
            return resolved_props
        if not isinstance(bulk_props, dict):
            warnings.warn(
                f"'{BULK_PROPS_KWARG}' must be a dict of props; "
                f"received {type(bulk_props).__name__} which will be ignored"
            )
            return resolved_props
        merged = dict(resolved_props)
        for key, value in transform_attribute_names(bulk_props).items():
            if not isinstance(key, str):
                warnings.warn(f"Ignoring non-string key in '{BULK_PROPS_KWARG}': {key!r}")
                continue
            normalized_key = self._normalize_prop_key(key)
            normalized_key = _BULK_PROP_STATE_ALIASES.get(normalized_key, normalized_key)
            if normalized_key == "className" and merged.get(normalized_key):
                merged[normalized_key] = self.join_classes(
                    str(merged[normalized_key]),
                    str(value) if value else None,
                )
                continue
            merged[normalized_key] = value
        return merged

    def resolve_prop_value(self, context: Context, value: Any) -> Any:
        if isinstance(value, FilterExpression):
            return self.resolve_prop_value(context, value.resolve(context))
        if isinstance(value, DeferredProp):
            return value.resolve(context)
        if isinstance(value, NodeList):
            return value.render(context)
        return value

    def render_children_for_component(self, context: Context, props: dict[str, Any]) -> str:
        """Render children during the main :meth:`render` flow.

        Unlike :meth:`render_children` this receives the resolved props, so renderers that need to
        share state with their children (e.g. the table components) can push that state around the
        children render based on the props.
        """
        return self.render_children(context)

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

    def get_recipe_classes(self, mapping: Any, key: str, selections: dict[str, str]) -> list[str]:
        """Resolve classes for a vanilla-extract recipe export.

        Recipes are serialized by ``@alliancesoftware/vite-plugin-django-vanilla-extract`` as
        ``{"base": <class>, "variants": {<group>: {<value>: <class>}}}``. Returns the base class
        followed by the class for each selected variant, skipping anything unresolved.
        """
        recipe = getattr(mapping, key, None)
        if recipe is None or not (isinstance(recipe, dict) or hasattr(recipe, "get")):
            return []
        classes: list[str] = []
        base_class = recipe.get("base", "")
        if isinstance(base_class, str) and base_class:
            classes.append(base_class)
        variants = recipe.get("variants", {})
        for group, value in selections.items():
            group_mapping = variants.get(group, {}) if isinstance(variants, dict) else {}
            variant_class = group_mapping.get(value, "") if isinstance(group_mapping, dict) else ""
            if isinstance(variant_class, str) and variant_class:
                classes.append(variant_class)
        return classes

    def render_icon(
        self,
        name: str,
        size: str,
        extra_class_names: list[str] | None = None,
        *,
        slot: str | None | bool = "icon",
        attrs: dict[str, Any] | None = None,
    ) -> str:
        """Render a named static icon using the shared static icon renderer."""
        from .static_icon import render_static_icon

        return render_static_icon(
            self,
            name=name,
            size=size,
            extra_class_names=extra_class_names,
            slot=slot,
            attrs=attrs,
        )

    def build_attrs_string(self, attrs: dict[str, Any]) -> str:
        return build_attrs_string(attrs)

    def join_classes(self, *class_names: str | None) -> str:
        return " ".join(class_name for class_name in class_names if class_name)

    def _normalize_prop_key(self, key: str) -> str:
        return normalize_html_ui_prop_name(key)

    def _merge_slot_props(self, context: Context, child_props: dict[str, Any]) -> dict[str, Any]:
        slot_name = self.get_slot_name()
        if not slot_name:
            return child_props
        slot_context = get_slot_context(context)
        return merge_slot_props(slot_context.get(slot_name), child_props)

    def _queue_resources(self):
        for item in self.bundler.get_embed_items(self.get_resources_to_embed()):
            self.bundler_asset_context.queue_embed_file(item)

    def _render_tag(self, tag_name: str, attrs: dict[str, Any], children_html: str = "") -> str:
        attrs_html = self.build_attrs_string(attrs)
        return mark_safe(f"<{tag_name}{attrs_html}>{children_html}</{tag_name}>")
