from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import warnings

from allianceutils.template import is_static_expression
from allianceutils.template import parse_tag_arguments
from django import template
from django.conf import settings
from django.template import Context
from django.template import Origin
from django.template import TemplateSyntaxError
from django.template.base import UNKNOWN_SOURCE
from django.template.base import FilterExpression
from django.template.base import NodeList

from alliance_platform.frontend.bundler.context import BundlerAsset
from alliance_platform.frontend.bundler.frontend_resource import FrontendResource

from .constants import ALLOWED_COMPONENTS_KWARG
from .registry import HtmlUIComponentRegistry
from .registry import built_in_registry

_DISPATCHER_WARNING_KEYS: set[tuple[str, str]] = set()


@dataclass(frozen=True)
class ComponentSelector:
    expression: FilterExpression
    is_static: bool
    static_value: str | None


class UIComponentDispatcherNode(template.Node, BundlerAsset):
    def __init__(
        self,
        *,
        selector: ComponentSelector,
        props: dict[str, Any],
        nodelist: NodeList,
        allowed_components: list[str] | None,
        target_var: str | None,
        origin: Origin | None,
        registry: HtmlUIComponentRegistry,
    ):
        self.selector = selector
        self.props = props
        self.nodelist = nodelist
        self.allowed_components = allowed_components or []
        self.target_var = target_var
        self.registry = registry
        super().__init__(origin or Origin(UNKNOWN_SOURCE))

    def get_resources_for_bundling(self) -> list[FrontendResource]:
        if self.selector.is_static and self.selector.static_value is not None:
            spec = self.registry.get(self.selector.static_value)
            if spec is None:
                return []
            renderer = spec.renderer_cls(
                props=self.props,
                nodelist=self.nodelist,
                origin=self.origin,
                target_var=self.target_var,
                register_asset=False,
            )
            return renderer.get_resources_for_bundling()

        resources: list[FrontendResource] = []
        seen_keys: set[tuple[type[FrontendResource], str]] = set()
        for component_name in self.allowed_components:
            spec = self.registry.get(component_name)
            if spec is None:
                continue
            renderer = spec.renderer_cls(
                props=self.props,
                nodelist=self.nodelist,
                origin=self.origin,
                target_var=self.target_var,
                register_asset=False,
            )
            for resource in renderer.get_resources_for_bundling():
                key = (type(resource), str(resource.path))
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                resources.append(resource)
        return resources

    def render(self, context: Context) -> str:
        component_name = self._resolve_component_name(context)

        if not component_name:
            self._warn_dispatcher(
                warning_type="ui_dispatcher_empty_component",
                component_identifier="<empty>",
                message="Resolved ui component name was empty; rendering nothing.",
            )
            return ""

        if not self.selector.is_static:
            if component_name not in self.allowed_components:
                self._warn_dispatcher(
                    warning_type="ui_dispatcher_disallowed_dynamic_component",
                    component_identifier=component_name,
                    message=(
                        f"Resolved ui component '{component_name}' is not allowed by "
                        f"{ALLOWED_COMPONENTS_KWARG}."
                    ),
                )
                return ""

        spec = self.registry.get(component_name)
        if spec is None:
            if settings.DEBUG:
                raise TemplateSyntaxError(f"Unknown ui component '{component_name}'")
            self._warn_dispatcher(
                warning_type="ui_dispatcher_unknown_component",
                component_identifier=component_name,
                message=f"Unknown ui component '{component_name}'",
            )
            return ""

        renderer = spec.renderer_cls(
            props=self.props,
            nodelist=self.nodelist,
            origin=self.origin,
            target_var=self.target_var,
        )
        return renderer.render(context)

    def _resolve_component_name(self, context: Context) -> str:
        if self.selector.is_static:
            return self.selector.static_value or ""

        value = self.selector.expression.resolve(context)
        return "" if value is None else str(value).strip()

    def _warn_dispatcher(self, warning_type: str, component_identifier: str, message: str):
        key = (warning_type, component_identifier)
        if not settings.DEBUG and key in _DISPATCHER_WARNING_KEYS:
            return
        if not settings.DEBUG:
            _DISPATCHER_WARNING_KEYS.add(key)
        warnings.warn(message)


def parse_ui_tag(
    parser,
    token,
    *,
    registry: HtmlUIComponentRegistry = built_in_registry,
):
    tag_name = token.split_contents()[0]
    args, kwargs, target_var = parse_tag_arguments(parser, token, supports_as=True)

    if len(args) == 0:
        raise TemplateSyntaxError(f"'{tag_name}' requires a component selector as the first positional argument")
    if len(args) > 1:
        raise TemplateSyntaxError(
            f"'{tag_name}' accepts exactly one positional argument (component selector), received {len(args)}"
        )

    selector_expr = args[0]
    selector_is_static = is_static_expression(selector_expr)
    static_selector_value: str | None = None

    if selector_is_static:
        resolved_selector = selector_expr.resolve(Context())
        if not isinstance(resolved_selector, str):
            raise TemplateSyntaxError(
                f"'{tag_name}' static selector must resolve to a string, received {type(resolved_selector).__name__}"
            )
        static_selector_value = resolved_selector
        if settings.DEBUG and not registry.exists(static_selector_value):
            raise TemplateSyntaxError(f"Unknown ui component '{static_selector_value}'")

    allowed_components = _parse_allowed_components_literal(
        tag_name=tag_name,
        raw_allowed_components=kwargs.pop(ALLOWED_COMPONENTS_KWARG, None),
        registry=registry,
    )

    if not selector_is_static and not allowed_components:
        raise TemplateSyntaxError(
            f"'{tag_name}' requires {ALLOWED_COMPONENTS_KWARG} when using a dynamic component selector"
        )

    nodelist = parser.parse((f"end{tag_name}",))
    parser.delete_first_token()

    return UIComponentDispatcherNode(
        selector=ComponentSelector(
            expression=selector_expr,
            is_static=selector_is_static,
            static_value=static_selector_value,
        ),
        props=kwargs,
        nodelist=nodelist,
        allowed_components=allowed_components,
        target_var=target_var,
        origin=parser.origin,
        registry=registry,
    )


def _parse_allowed_components_literal(
    *,
    tag_name: str,
    raw_allowed_components: FilterExpression | None,
    registry: HtmlUIComponentRegistry,
) -> list[str]:
    if raw_allowed_components is None:
        return []

    if not is_static_expression(raw_allowed_components):
        raise TemplateSyntaxError(
            f"'{tag_name}' expects {ALLOWED_COMPONENTS_KWARG} as a static string literal list"
        )

    resolved_value = raw_allowed_components.resolve(Context())
    if not isinstance(resolved_value, str):
        raise TemplateSyntaxError(
            f"'{tag_name}' expects {ALLOWED_COMPONENTS_KWARG} as a string, received {type(resolved_value).__name__}"
        )

    normalized: list[str] = []
    seen: set[str] = set()
    for item in resolved_value.split(","):
        component_name = item.strip()
        if not component_name:
            raise TemplateSyntaxError(
                f"'{tag_name}' has malformed {ALLOWED_COMPONENTS_KWARG}; empty entries are not allowed"
            )
        if component_name in seen:
            continue
        seen.add(component_name)
        normalized.append(component_name)

    unknown = [component_name for component_name in normalized if not registry.exists(component_name)]
    if unknown:
        raise TemplateSyntaxError(
            f"'{tag_name}' has invalid {ALLOWED_COMPONENTS_KWARG} entries: {', '.join(unknown)}"
        )

    return normalized
