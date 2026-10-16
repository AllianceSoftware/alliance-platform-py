from __future__ import annotations

from typing import Any

from alliance_platform.frontend.bundler.context import BundlerAsset
from alliance_platform.frontend.bundler.frontend_resource import FrontendResource
from allianceutils.template import is_static_expression
from allianceutils.template import parse_tag_arguments
from django import template
from django.template import Context
from django.template import Origin
from django.template import TemplateSyntaxError
from django.template.base import UNKNOWN_SOURCE
from django.template.base import FilterExpression
from django.template.base import NodeList

from .base import BaseHtmlUIComponentRenderer
from .constants import ALLOWED_COMPONENTS_KWARG
from .diagnostics import report
from .registry import HtmlUIComponentRegistry
from .registry import built_in_registry


class UIComponentDispatcherNode(template.Node, BundlerAsset):
    def __init__(
        self,
        *,
        selector: FilterExpression,
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
        self.allowed_components = allowed_components
        self.target_var = target_var
        self.registry = registry
        super().__init__(origin or Origin(UNKNOWN_SOURCE))

    def get_resources_for_bundling(self) -> list[FrontendResource]:
        resources: list[FrontendResource] = []
        seen_keys: set[tuple[type[FrontendResource], str]] = set()
        for component_name in self.allowed_components or []:
            renderer_cls = self.registry.get(component_name)
            if renderer_cls is None:
                continue
            renderer = renderer_cls(
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
            report(
                "Resolved ui component name was empty; rendering nothing.",
                kind="contract",
                origin=self.origin,
            )
            return ""

        if self.allowed_components is not None and component_name not in self.allowed_components:
            report(
                f"Resolved ui component '{component_name}' is not allowed by {ALLOWED_COMPONENTS_KWARG}.",
                kind="contract",
                component=component_name,
                origin=self.origin,
            )
            return ""

        renderer_cls = self.registry.get(component_name)
        if renderer_cls is None:
            report(
                f"Unknown ui component '{component_name}'",
                kind="contract",
                component=component_name,
                origin=self.origin,
            )
            return ""

        renderer = renderer_cls(
            props=self.props,
            nodelist=self.nodelist,
            origin=self.origin,
            target_var=self.target_var,
        )
        return renderer.render(context)

    def _resolve_component_name(self, context: Context) -> str:
        value = self.selector.resolve(context)
        return "" if value is None else str(value).strip()


def parse_ui_tag(
    parser,
    token,
    *,
    registry: HtmlUIComponentRegistry = built_in_registry,
):
    tag_name = token.split_contents()[0]
    args, kwargs, target_var = parse_tag_arguments(parser, token, supports_as=True)

    if len(args) == 0:
        raise TemplateSyntaxError(
            f"'{tag_name}' requires a component selector as the first positional argument"
        )
    if len(args) > 1:
        raise TemplateSyntaxError(
            f"'{tag_name}' accepts exactly one positional argument (component selector), received {len(args)}"
        )

    selector_expr = args[0]
    renderer_cls: type[BaseHtmlUIComponentRenderer] | None = None

    if is_static_expression(selector_expr):
        resolved_selector = selector_expr.resolve(Context())
        if not isinstance(resolved_selector, str):
            raise TemplateSyntaxError(
                f"'{tag_name}' static selector must resolve to a string, received {type(resolved_selector).__name__}"
            )
        renderer_cls = registry.get(resolved_selector)
        if renderer_cls is None:
            raise TemplateSyntaxError(f"Unknown ui component '{resolved_selector}'")

    allowed_components = _parse_allowed_components_literal(
        tag_name=tag_name,
        raw_allowed_components=kwargs.pop(ALLOWED_COMPONENTS_KWARG, None),
        registry=registry,
    )

    if renderer_cls is None and not allowed_components:
        raise TemplateSyntaxError(
            f"'{tag_name}' requires {ALLOWED_COMPONENTS_KWARG} when using a dynamic component selector"
        )

    has_children = (
        renderer_cls.has_children
        if renderer_cls is not None
        else _allowed_components_have_children(
            tag_name=tag_name,
            allowed_components=allowed_components,
            registry=registry,
        )
    )
    # A leaf tag has no end tag, so nothing after it is consumed: a following {% endui %} closes the
    # enclosing component, or is an invalid block tag at the top level.
    if has_children:
        nodelist = parser.parse((f"end{tag_name}",))
        parser.delete_first_token()
    else:
        nodelist = NodeList()

    if renderer_cls is not None:
        return renderer_cls(
            props=kwargs,
            nodelist=nodelist,
            target_var=target_var,
            origin=parser.origin,
        )

    return UIComponentDispatcherNode(
        selector=selector_expr,
        props=kwargs,
        nodelist=nodelist,
        allowed_components=allowed_components,
        target_var=target_var,
        origin=parser.origin,
        registry=registry,
    )


def _allowed_components_have_children(
    *,
    tag_name: str,
    allowed_components: list[str],
    registry: HtmlUIComponentRegistry,
) -> bool:
    """Return whether a dynamic tag has children, which every allowed component must agree on.

    The tag is parsed before the selector resolves, so whether it takes an end tag cannot depend on
    which component renders.
    """
    with_children: list[str] = []
    leaves: list[str] = []
    for component_name in allowed_components:
        renderer_cls = registry.get(component_name)
        if renderer_cls is None:
            # _parse_allowed_components_literal() rejected unknown names already
            continue
        (with_children if renderer_cls.has_children else leaves).append(component_name)
    if with_children and leaves:
        raise TemplateSyntaxError(
            f"'{tag_name}' {ALLOWED_COMPONENTS_KWARG} cannot mix components that take children "
            f"({', '.join(with_children)}) with leaf components that take no end tag ({', '.join(leaves)})"
        )
    return not leaves


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
