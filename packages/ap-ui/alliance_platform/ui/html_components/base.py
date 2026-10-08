"""Base class for static ``{% ui %}`` component renderers.

A renderer is a template node. :meth:`BaseHtmlUIComponentRenderer.render` resolves the tag's props,
merges inherited slot defaults, applies the prop contract, pushes the frame from
``build_render_frame``, renders children, renders the component and publishes its child report.
Renderer instances are shared by every render of a compiled template, so per-render state belongs
in frame payloads, never on ``self``.

Contract attributes (class level): ``name``, ``apui_name``, ``slot_name``, ``has_children``,
``supported_props``, ``prop_rules``, ``prop_aliases``, ``deprecated_prop_aliases``,
``unsupported_prop_reasons``, ``forwarded_props``, ``allow_data_props``, ``allow_aria_props``,
``extra_allowed_aria_props``, ``non_scalar_props``, ``none_meaningful_props``, ``react_tag``, and
the diagnostic wording in ``prop_filter_context`` and ``event_handler_prop_reason``.

Hooks to override: ``render_component`` (required), ``render_children_for_component``,
``build_render_frame``, ``build_child_report``, ``resolve_component_resources`` and
``get_resources_to_embed``. Renderers may also override ``resolve_props`` (for example to require a
parent component), ``allow_non_scalar_prop`` and the ``supports_prop_name`` classmethod.

Helpers to call: ``report``, ``render_children``, ``render_tag``, ``render_icon``,
``resolve_frontend_resource``, ``resolve_optional_resource_path``, ``resolve_vanilla_extract_mapping``,
the style getters (``get_style_class``, ``get_nested_style_class``, ``get_recipe_classes``),
``collect_forwarded_props``, ``join_classes``, ``build_attrs_string`` and the
``canonical_prop_name`` classmethod. Module level: :class:`PropRule`, :func:`enum_prop_rule`,
:func:`typed_prop_rule`, :func:`build_attrs_string`, :func:`is_event_handler_attr` and
:func:`style_dict_to_string`.

Names starting with an underscore are internal.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
import re
from typing import Any
from typing import Callable
from typing import ClassVar
from typing import Mapping

from alliance_platform.frontend.bundler import get_bundler
from alliance_platform.frontend.bundler.base import ResolveContext
from alliance_platform.frontend.bundler.context import BundlerAsset
from alliance_platform.frontend.bundler.frontend_resource import FrontendResource
from alliance_platform.frontend.bundler.vanilla_extract import resolve_vanilla_extract_class_mapping
from alliance_platform.frontend.templatetags.react import DeferredProp
from alliance_platform.frontend.templatetags.react import OmitComponentFromRendering
from alliance_platform.frontend.util import transform_attribute_names
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

from . import diagnostics
from .constants import BULK_PROPS_KWARG
from .diagnostics import DiagnosticKind
from .render_context import ChildReport
from .render_context import RenderFrame
from .render_context import push_render_frame
from .render_context import report_child
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


def _normalize_html_ui_prop_name(key: str) -> str:
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


def _camel_to_kebab(value: str) -> str:
    return _CAMEL_CASE_SPLIT_RE.sub(r"\1-\2", value).replace("_", "-").lower()


def _to_html_attr_name(key: str) -> str:
    """Convert a React style prop name to the HTML attribute name (``className`` -> ``class``)."""
    if key in _REACT_ATTR_TO_HTML_ATTR:
        return _REACT_ATTR_TO_HTML_ATTR[key]
    if "-" in key:
        return key
    if key.startswith("aria") and len(key) > 4 and key[4].isupper():
        return "aria-" + _camel_to_kebab(key[4:])
    if key.startswith("data") and len(key) > 4 and key[4].isupper():
        return "data-" + _camel_to_kebab(key[4:])
    return key.lower()


def is_event_handler_attr(name: str) -> bool:
    """Return whether an attribute/prop name could create an inline event handler."""
    return _to_html_attr_name(str(name)).lower().startswith("on")


def _is_scalar_prop_value(value: Any) -> bool:
    """Return whether a prop can be safely serialized as an HTML attribute value."""
    # Promise covers lazy translation proxies; Decimal covers Django DecimalField values.
    return isinstance(value, (str, int, float, bool, Decimal, Promise)) or value is None


def style_dict_to_string(style: dict[str, Any]) -> str:
    declarations = []
    for key, value in style.items():
        css_key = key if key.startswith("--") else _camel_to_kebab(str(key))
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
        attr_name = _to_html_attr_name(name)
        if name == "style" and isinstance(value, dict):
            value = style_dict_to_string(value)
        if value is True:
            rendered_attrs.append(f" {conditional_escape(attr_name)}")
        else:
            rendered_attrs.append(f' {conditional_escape(attr_name)}="{conditional_escape(value)}"')
    return "".join(rendered_attrs)


class BaseHtmlUIComponentRenderer(template.Node, BundlerAsset):
    """Base node for HTML-only UI components dispatched by ``{% ui %}``."""

    #: The snake_case name the component is registered under (``{% ui "<name>" %}``). Diagnostics
    #: and render frames use it, and :func:`~alliance_platform.ui.html_components.register_component`
    #: requires it to match the registered name.
    name: ClassVar[str]
    #: Value for the root ``data-apui`` marker and generated id prefixes (``apui-<apui_name>-1``).
    #: Defaults to ``name`` with underscores replaced by hyphens whenever a class sets ``name``
    #: without also setting ``apui_name``.
    apui_name: ClassVar[str]
    slot_name: str | None = None
    #: Whether the tag has children and a closing ``{% endui %}``. A leaf (``False``) is written
    #: without an end tag, ``{% ui "icon" name="Pencil01Outlined" %}``, and always renders with an
    #: empty ``nodelist``. Every component in a dynamic tag's ``allowed_components`` must agree.
    has_children: ClassVar[bool] = True
    #: Props the component accepts. ``None`` defers the final prop-name allowlist to the
    #: component (useful for inputs, which split props across several elements).
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
    #: The React template tag to use instead when a prop this renderer refuses is needed, written as
    #: in a template without the braces: ``Table``, or ``component "@alliancesoftware/ui" "TextInput"``
    #: for a component with no tag of its own. Reports of props refused through
    #: ``unsupported_prop_reasons`` and of event handlers end with ``use {% <react_tag> %} instead``.
    react_tag: ClassVar[str | None] = None
    prop_filter_context = "static HTML ui components"
    event_handler_prop_reason = "event handlers are not supported by static HTML ui components"

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if "name" in cls.__dict__ and "apui_name" not in cls.__dict__:
            cls.apui_name = cls.name.replace("_", "-")

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

    def render(self, context: Context) -> str:
        if not self._register_asset:
            raise RuntimeError(
                "Cannot render a renderer initialised with register_asset=False. "
                "This mode is for resource introspection only."
            )
        self._queue_resources()
        report: ChildReport | None = None
        try:
            props = self.resolve_props(context)
            props = self._merge_slot_props(context, props)
            props = self._filter_component_props(props)
            frame = self.build_render_frame(context, props)
            with push_render_frame(context, frame):
                children_html = self.render_children_for_component(context, props)
                rendered = self.render_component(context, props, children_html)
                report = self.build_child_report(context, props, rendered)
        except OmitComponentFromRendering:
            # Matches the React component tags: a prop can raise this to indicate the whole
            # component should not render (e.g. a denied ``url_with_perm`` href). This is expected
            # behaviour so nothing is reported.
            rendered = ""
        if self.target_var:
            context[self.target_var] = rendered
            return ""
        if rendered and report is not None:
            report_child(context, report)
        return rendered

    def build_child_report(
        self,
        context: Context,
        props: dict[str, Any],
        rendered: str,
    ) -> ChildReport | None:
        """Return facts this component should publish to a collecting direct parent."""

        return None

    def build_render_frame(self, context: Context, props: dict[str, Any]) -> RenderFrame:
        """Build this component's frame; composite roots may attach a typed payload."""

        return RenderFrame(component=self.name)

    def resolve_props(self, context: Context) -> dict[str, Any]:
        resolved_props: dict[str, Any] = {}
        bulk_props: Any = None
        for key, value in self.props.items():
            if key == BULK_PROPS_KWARG:
                bulk_props = self._resolve_prop_value(context, value)
                continue
            normalized_key = self._normalize_prop_key(key)
            resolved_value = self._resolve_prop_value(context, value)
            if normalized_key == "className" and normalized_key in resolved_props:
                existing = resolved_props.get(normalized_key)
                resolved_props[normalized_key] = self.join_classes(
                    str(existing) if existing else None,
                    str(resolved_value) if resolved_value else None,
                )
                continue
            resolved_props[normalized_key] = resolved_value
        return self._merge_bulk_props(resolved_props, bulk_props)

    def _filter_component_props(self, props: dict[str, Any]) -> dict[str, Any]:
        """Apply the shared static-component prop policy.

        Component families configure the policy through the class attributes above. The common
        implementation keeps event-handler refusal, data/aria handling, style validation and
        scalar-value checks consistent while leaving component-specific allowlists declarative.
        """
        filtered: dict[str, Any] = {}
        aliased_props: dict[str, Any] = {}
        for original_key, value in props.items():
            key = self.deprecated_prop_aliases.get(
                original_key,
                self.prop_aliases.get(original_key, original_key),
            )
            if original_key in self.deprecated_prop_aliases:
                self.report(f"You passed '{original_key}' - use '{key}' instead", kind="contract")
            if key != original_key and key in props:
                # The canonical spelling always wins when both forms are supplied.
                continue
            aliased_props[key] = value

        for key, value in aliased_props.items():
            rule = self.prop_rules.get(key)
            if value is None:
                if (rule is not None and rule.allow_none) or key in self.none_meaningful_props:
                    if self._is_supported_prop(key):
                        filtered[key] = value
                continue
            reason = self.unsupported_prop_reasons.get(key)
            if reason:
                self._report_ignored_prop(key, reason)
                continue
            if is_event_handler_attr(key):
                self._report_ignored_prop(key, self.event_handler_prop_reason)
                continue
            attr_name = _to_html_attr_name(key)
            if attr_name.startswith("data-") or attr_name.startswith("aria-"):
                allowed = (
                    self.allow_data_props
                    if attr_name.startswith("data-")
                    else (self.allow_aria_props or attr_name in self.extra_allowed_aria_props)
                )
                if not allowed:
                    self.report(
                        f"Prop '{key}' is not supported on '{self.name}' and will be ignored", kind="contract"
                    )
                    continue
                if not _is_scalar_prop_value(value):
                    self.report(
                        f"Prop '{key}' with non-scalar value is not supported by "
                        f"{self.prop_filter_context} and will be ignored",
                        kind="contract",
                    )
                    continue
                filtered[attr_name] = value
                continue
            if not self._is_supported_prop(key):
                self.report(
                    f"Prop '{key}' is not a supported '{self.name}' prop and will be ignored", kind="contract"
                )
                continue
            if rule is not None and not rule.accepts(value):
                self.report(f"Invalid '{key}' prop passed: {value}", kind="contract")
                if rule.invalid_fallback is _OMIT_INVALID_PROP:
                    continue
                value = rule.invalid_fallback
            if key == "style":
                if not isinstance(value, (str, dict)):
                    self.report("Prop 'style' must be a string or dict; it will be ignored", kind="contract")
                    continue
            elif (
                not _is_scalar_prop_value(value)
                and rule is None
                and not self.allow_non_scalar_prop(key, value)
            ):
                self.report(
                    f"Prop '{key}' with non-scalar value is not supported by "
                    f"{self.prop_filter_context} and will be ignored",
                    kind="contract",
                )
                continue
            filtered[key] = value
        return filtered

    def _report_ignored_prop(self, key: str, reason: str) -> None:
        # Name the React tag that supports the prop, when there is one
        message = f"Prop '{key}' will be ignored: {reason}"
        if self.react_tag:
            message += f"; use {{% {self.react_tag} %}} instead"
        self.report(message, kind="contract")

    def _is_supported_prop(self, key: str) -> bool:
        return (
            self.supported_props is None
            or key in self.supported_props
            or key in self.prop_rules
            or key in self.forwarded_props
        )

    @classmethod
    def canonical_prop_name(cls, key: str) -> str:
        """Return the prop name after template normalization and renderer aliases."""
        normalized = _normalize_html_ui_prop_name(key)
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
            self.report(
                f"'{BULK_PROPS_KWARG}' must be a dict of props; "
                f"received {type(bulk_props).__name__} which will be ignored",
                kind="contract",
            )
            return resolved_props
        merged = dict(resolved_props)
        for key, value in transform_attribute_names(bulk_props).items():
            if not isinstance(key, str):
                self.report(f"Ignoring non-string key in '{BULK_PROPS_KWARG}': {key!r}", kind="contract")
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

    def _resolve_prop_value(self, context: Context, value: Any) -> Any:
        if isinstance(value, FilterExpression):
            return self._resolve_prop_value(context, value.resolve(context))
        if isinstance(value, DeferredProp):
            return value.resolve(context)
        if isinstance(value, NodeList):
            return value.render(context)
        return value

    def report(self, message: str, *, kind: DiagnosticKind) -> None:
        """Report a problem with this component, filling in its name and template origin.

        See :func:`~alliance_platform.ui.html_components.diagnostics.report`. A ``contract`` report
        raises :class:`~alliance_platform.ui.html_components.diagnostics.StaticComponentContractError`
        while the ``STATIC_COMPONENT_STRICT`` setting is on.
        """
        diagnostics.report(message, kind=kind, component=self.name, origin=self.origin)

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

    def _resolve_resource_path(self, path: str, resolve_extensions: list[str] | None = None) -> Path:
        resolver_context = ResolveContext(self.bundler.root_dir, self.origin.name if self.origin else None)
        return self.bundler.resolve_path(path, resolver_context, resolve_extensions=resolve_extensions)

    def resolve_optional_resource_path(
        self,
        path: str,
        resolve_extensions: list[str] | None = None,
    ) -> Path | None:
        try:
            return self._resolve_resource_path(path, resolve_extensions=resolve_extensions)
        except template.TemplateSyntaxError:
            return None

    def resolve_frontend_resource(
        self,
        path: str,
        resolve_extensions: list[str] | None = None,
    ) -> FrontendResource:
        return FrontendResource.from_path(
            self._resolve_resource_path(path, resolve_extensions=resolve_extensions)
        )

    def resolve_vanilla_extract_mapping(
        self,
        path: str,
        resolve_extensions: list[str] | None = None,
    ):
        style_path = self._resolve_resource_path(path, resolve_extensions=resolve_extensions)
        return resolve_vanilla_extract_class_mapping(self.bundler, style_path)

    # Style getters. ``mapping`` is what resolve_vanilla_extract_mapping() returns: a
    # ``VanillaExtractClassMapping`` at runtime, or the dict-backed stand-in from
    # ``alliance_platform.ui.test_utils`` in tests. Both return the class data from
    # ``mapping.get_mapping()`` (``None`` while the mapping file is unavailable) and name the
    # stylesheet in ``mapping.filename``.

    def get_style_class(self, mapping: Any, key: str) -> str:
        """Return the class string of the style ``key``.

        A style missing from a loaded mapping is reported as a contract problem and resolves to
        ``""``. While the mapping file is unavailable (``get_mapping()`` returns ``None``, as before
        the dev server has written it) nothing can be checked, so the style resolves through the
        mapping object as it would at runtime.
        """
        value = self._get_style(mapping, key, "")
        return value if isinstance(value, str) else ""

    def get_nested_style_class(self, mapping: Any, key: str, nested_key: str) -> str:
        """Return the class string at ``key`` -> ``nested_key``, such as a ``styleVariants`` entry.

        Missing entries are reported and resolve to ``""``, as for :meth:`get_style_class`.
        """
        group = self._get_style(mapping, key, None)
        if isinstance(group, Mapping) and isinstance(group.get(nested_key), str):
            return group[nested_key]
        if group is not None and self._mapping_loaded(mapping):
            self._report_missing_style(mapping, f"'{key}.{nested_key}'")
        return ""

    def get_recipe_classes(self, mapping: Any, key: str, selections: dict[str, str]) -> list[str]:
        """Resolve classes for a vanilla-extract recipe export.

        Recipes are serialized by ``@alliancesoftware/vite-plugin-django-vanilla-extract`` as
        ``{"base": <class>, "variants": {<group>: {<value>: <class>}}}``. Returns the base class
        followed by the class for each selected variant. A missing recipe or variant is reported,
        as for :meth:`get_style_class`, and skipped.
        """
        recipe = self._get_style(mapping, key, None)
        if not isinstance(recipe, Mapping):
            if recipe is not None and self._mapping_loaded(mapping):
                self._report_missing_style(mapping, f"'{key}'", problem="is not a recipe")
            return []
        classes: list[str] = []
        base_class = recipe.get("base", "")
        if isinstance(base_class, str) and base_class:
            classes.append(base_class)
        variants = recipe.get("variants", {})
        for group, value in selections.items():
            group_mapping = variants.get(group, {}) if isinstance(variants, Mapping) else {}
            variant_class = group_mapping.get(value, "") if isinstance(group_mapping, Mapping) else ""
            if isinstance(variant_class, str) and variant_class:
                classes.append(variant_class)
            elif self._mapping_loaded(mapping):
                self._report_missing_style(mapping, f"'{key}' variant {group}={value!r}")
        return classes

    @staticmethod
    def _loaded_styles(mapping: Any) -> Mapping[str, Any] | None:
        # get_mapping() reloads data the dev server rewrote since an earlier request, as reading a
        # class does, so a style added since is not reported missing. Mapping objects without it
        # expose the data as ``mapping``.
        get_mapping = getattr(mapping, "get_mapping", None)
        styles = get_mapping() if callable(get_mapping) else getattr(mapping, "mapping", None)
        return styles if isinstance(styles, Mapping) else None

    @classmethod
    def _mapping_loaded(cls, mapping: Any) -> bool:
        return cls._loaded_styles(mapping) is not None

    def _get_style(self, mapping: Any, key: str, default: Any) -> Any:
        # Check membership before reading the attribute so that VanillaExtractClassMapping does not
        # warn about the missing attribute as well as the report.
        styles = self._loaded_styles(mapping)
        if styles is not None and key not in styles:
            self._report_missing_style(mapping, f"'{key}'")
            return default
        return getattr(mapping, key, default)

    def _report_missing_style(self, mapping: Any, description: str, problem: str = "does not exist") -> None:
        stylesheet = getattr(mapping, "filename", None) or "its stylesheet"
        self.report(f"Style {description} {problem} in '{stylesheet}'", kind="contract")

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
        return _normalize_html_ui_prop_name(key)

    def _merge_slot_props(self, context: Context, child_props: dict[str, Any]) -> dict[str, Any]:
        # Match useSlotProps: an explicit slot selects that parent-provided slot; otherwise the
        # renderer's default slot is used. The slot selector itself is consumed by renderers and
        # is not forwarded as an HTML attribute.
        slot_name = child_props.get("slot") or self.slot_name
        if not slot_name:
            return child_props
        slot_context = get_slot_context(context)
        return merge_slot_props(slot_context.get(slot_name), child_props)

    def _queue_resources(self):
        for item in self.bundler.get_embed_items(self.get_resources_to_embed()):
            self.bundler_asset_context.queue_embed_file(item)

    def render_tag(self, tag_name: str, attrs: dict[str, Any], children_html: str = "") -> str:
        """Render ``<tag_name ...>children_html</tag_name>`` as safe HTML.

        ``attrs`` are rendered by :func:`build_attrs_string`; ``children_html`` is inserted as is,
        so it must already be escaped.
        """
        attrs_html = self.build_attrs_string(attrs)
        return mark_safe(f"<{tag_name}{attrs_html}>{children_html}</{tag_name}>")
