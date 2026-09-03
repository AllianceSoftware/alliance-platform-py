"""Static HTML renderer for Alliance UI pagination.

The React component normally manages page state through callbacks. This renderer targets Django's
request/response flow instead: every pagination control is an ordinary link that preserves the
current query string while changing the configured page parameter.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from typing import Literal
import warnings

from django.http import QueryDict
from django.template import Context
from django.utils.safestring import mark_safe

from alliance_platform.frontend.bundler.frontend_resource import FrontendResource
from alliance_platform.frontend.bundler.frontend_resource import ImageResource
from alliance_platform.ui.icons import get_static_icon_resource

from ..base import BaseHtmlUIComponentRenderer
from ..base import enum_prop_rule
from ..base import typed_prop_rule
from ..static_icon import ICON_STYLE_PATH

_PAGINATION_STYLE_PATH = "@alliancesoftware/ui/components/pagination/Pagination.css.ts"
_BUTTON_STYLE_PATH = "@alliancesoftware/ui/components/button/Button.css.ts"
_FOCUS_RING_STYLE_PATH = "@alliancesoftware/ui/styles/base/focusRing.css.ts"

_ARROW_LEFT_ICON = "ArrowLeftOutlined"
_ARROW_RIGHT_ICON = "ArrowRightOutlined"

VALID_VARIANTS = ("default", "compact")
VALID_SIZES = ("sm", "md")

_PAGE_SIZE_REASON = (
    "page-size selection requires an interactive form or JavaScript and is not supported by static pagination"
)
_CALLBACK_REASON = "callback pagination is not supported; static pagination uses ordinary links"
_STATE_REASON = "client-managed pagination state is not supported; pass page, pageSize, and total"
_RENDER_REASON = "custom item render functions are not supported by static pagination"

_UNSUPPORTED_PROPS = {
    "defaultPage": _STATE_REASON,
    "defaultPageSize": _STATE_REASON,
    "state": _STATE_REASON,
    "onPageChange": _CALLBACK_REASON,
    "onPageSizeChange": _PAGE_SIZE_REASON,
    "isPageSizeSelectable": _PAGE_SIZE_REASON,
    "pageSizes": _PAGE_SIZE_REASON,
    "renderItem": _RENDER_REASON,
    "renderItemProps": _RENDER_REASON,
    "breakpoints": (
        "JavaScript breakpoint configuration is not supported; static pagination uses the "
        "Pagination.css.ts container-query baseline"
    ),
}


def _is_int_at_least(minimum: int):
    return lambda value: not isinstance(value, bool) and value >= minimum


@dataclass(frozen=True)
class PaginationItem:
    type: Literal["previous", "page", "ellipsis", "next"]
    page: int | None = None
    is_current: bool = False
    is_disabled: bool = False


class UIPaginationRenderer(BaseHtmlUIComponentRenderer):
    apui_component_name = "pagination"
    slot_name = "pagination"
    supported_props = frozenset(
        {
            "total",
            "page",
            "pageSize",
            "boundaryCount",
            "siblingCount",
            "pageQueryParam",
            "pageSizeQueryParam",
            "variant",
            "size",
            "className",
            "style",
            "isDisabled",
            "slot",
            "children",
        }
    )
    forwarded_props = frozenset({"id"})
    allow_data_props = True
    allow_aria_props = True
    unsupported_prop_reasons = _UNSUPPORTED_PROPS
    prop_filter_context = "static pagination components"
    event_handler_prop_reason = _CALLBACK_REASON
    prop_rules = {
        "total": typed_prop_rule(int, validator=_is_int_at_least(0), invalid_fallback=0),
        "page": typed_prop_rule(int, validator=_is_int_at_least(1), invalid_fallback=1),
        "pageSize": typed_prop_rule(int, validator=_is_int_at_least(1), invalid_fallback=10),
        "boundaryCount": typed_prop_rule(int, validator=_is_int_at_least(0), invalid_fallback=1),
        "siblingCount": typed_prop_rule(int, validator=_is_int_at_least(0), invalid_fallback=2),
        "pageQueryParam": typed_prop_rule(str, validator=lambda value: bool(value), invalid_fallback="page"),
        "pageSizeQueryParam": typed_prop_rule(
            str, validator=lambda value: bool(value), invalid_fallback="pageSize"
        ),
        "variant": enum_prop_rule(VALID_VARIANTS, invalid_fallback="default"),
        "size": enum_prop_rule(VALID_SIZES, invalid_fallback="sm"),
        "isDisabled": typed_prop_rule(bool, invalid_fallback=False),
    }

    def resolve_component_resources(self) -> list[FrontendResource]:
        return [
            self.resolve_frontend_resource(_PAGINATION_STYLE_PATH),
            self.resolve_frontend_resource(_BUTTON_STYLE_PATH),
            self.resolve_frontend_resource(_FOCUS_RING_STYLE_PATH),
            self.resolve_frontend_resource(ICON_STYLE_PATH),
            get_static_icon_resource(_ARROW_LEFT_ICON, origin=self.origin),
            get_static_icon_resource(_ARROW_RIGHT_ICON, origin=self.origin),
        ]

    def get_resources_to_embed(self) -> list[FrontendResource]:
        return [
            resource
            for resource in self.get_resources_for_bundling()
            if not isinstance(resource, ImageResource)
        ]

    def render_component(self, context: Context, props: dict[str, Any], children_html: str) -> str:
        if children_html.strip():
            warnings.warn("'pagination' does not support children; the content will be ignored")
        if "total" not in props:
            warnings.warn("'pagination' requires a 'total' prop and will not render")
            return ""

        total = int(props["total"])
        page_size = int(props.get("pageSize", 10))
        total_pages = (max(1, total) + page_size - 1) // page_size
        page = int(props.get("page", 1))
        if page > total_pages:
            warnings.warn(
                f"Prop 'page' ({page}) exceeds the total page count ({total_pages}); "
                f"page {total_pages} will be rendered"
            )
            page = total_pages

        boundary_count = int(props.get("boundaryCount", 1))
        sibling_count = int(props.get("siblingCount", 2))
        is_disabled = bool(props.get("isDisabled", False))
        variant = str(props.get("variant", "default"))
        size = str(props.get("size", "sm"))

        pagination_styles = self.resolve_vanilla_extract_mapping(_PAGINATION_STYLE_PATH)
        root_attrs: dict[str, Any] = {
            **self.collect_forwarded_props(props),
            "className": self.join_classes(
                self.get_nested_style_class(pagination_styles, "pagination", variant),
                props.get("className"),
            ),
            "style": props.get("style"),
        }
        items = self.generate_items(
            page=page,
            total_pages=total_pages,
            sibling_count=sibling_count,
            boundary_count=boundary_count,
            is_disabled=is_disabled,
        )
        list_html = self.render_items(
            context,
            props,
            items,
            pagination_styles=pagination_styles,
            size=size,
        )
        wrapper_attrs = {"className": self.get_style_class(pagination_styles, "wrapper")}
        return self._render_tag("nav", root_attrs, self._render_tag("ul", wrapper_attrs, list_html))

    def generate_items(
        self,
        *,
        page: int,
        total_pages: int,
        sibling_count: int,
        boundary_count: int,
        is_disabled: bool,
    ) -> list[PaginationItem]:
        total_link_count = boundary_count * 2 + sibling_count * 2 + 1
        start_pages = self.inclusive_range(1, min(boundary_count, total_pages))
        end_pages = self.inclusive_range(
            max(total_pages - boundary_count + 1, boundary_count + 1),
            total_pages,
        )
        total_link_count -= len(start_pages) + len(end_pages)

        siblings, start_gap, end_gap = self.generate_siblings(
            start_pages=start_pages,
            end_pages=end_pages,
            page=page,
            sibling_count=sibling_count,
            total_link_count=total_link_count,
            total_pages=total_pages,
        )

        items = [
            PaginationItem(
                type="previous",
                page=max(page - 1, 1),
                is_disabled=is_disabled or page == 1,
            )
        ]
        items.extend(self.page_item(value, page, is_disabled) for value in start_pages)
        if start_gap == "ellipsis":
            items.append(PaginationItem(type="ellipsis"))
        elif start_gap == "fill" and siblings:
            items.append(self.page_item(siblings[0] - 1, page, is_disabled))
        items.extend(self.page_item(value, page, is_disabled) for value in siblings)
        if end_gap == "ellipsis":
            items.append(PaginationItem(type="ellipsis"))
        elif end_gap == "fill" and siblings:
            items.append(self.page_item(siblings[-1] + 1, page, is_disabled))
        items.extend(self.page_item(value, page, is_disabled) for value in end_pages)
        items.append(
            PaginationItem(
                type="next",
                page=min(total_pages, page + 1),
                is_disabled=is_disabled or page == total_pages,
            )
        )
        return items

    def generate_siblings(
        self,
        *,
        start_pages: list[int],
        end_pages: list[int],
        page: int,
        sibling_count: int,
        total_link_count: int,
        total_pages: int,
    ) -> tuple[list[int], Literal["none", "fill", "ellipsis"], Literal["none", "fill", "ellipsis"]]:
        start_gap: Literal["none", "fill", "ellipsis"] = "none"
        end_gap: Literal["none", "fill", "ellipsis"] = "none"
        if start_pages and end_pages:
            sibling_start = max(
                start_pages[-1] + 1,
                min(page - sibling_count, end_pages[0] - total_link_count),
            )
            sibling_end = min(sibling_start + total_link_count - 1, end_pages[0] - 1)
            start_gap_size = sibling_start - start_pages[-1] - 1
            end_gap_size = end_pages[0] - sibling_end - 1
            if start_gap_size:
                start_gap = "fill" if start_gap_size == 1 else "ellipsis"
            if end_gap_size:
                end_gap = "fill" if end_gap_size == 1 else "ellipsis"
            siblings = self.inclusive_range(sibling_start, sibling_end)
        else:
            sibling_start = max(
                start_pages[-1] + 1 if start_pages else 1,
                min(page - sibling_count, total_pages - total_link_count + 1),
            )
            sibling_end = min(sibling_start + total_link_count - 1, total_pages)
            siblings = self.inclusive_range(sibling_start, sibling_end)
        return siblings, start_gap, end_gap

    def render_items(
        self,
        context: Context,
        props: dict[str, Any],
        items: list[PaginationItem],
        *,
        pagination_styles: Any,
        size: str,
    ) -> str:
        rendered: list[str] = []
        for index, item in enumerate(items):
            wrapper_classes = []
            if item.type in {"page", "ellipsis"}:
                wrapper_classes.append(self.get_style_class(pagination_styles, "pageNumberWrapper"))
            elif item.type == "previous":
                wrapper_classes.append(self.get_style_class(pagination_styles, "prevButtonWrapper"))
            elif item.type == "next":
                wrapper_classes.append(self.get_style_class(pagination_styles, "nextButtonWrapper"))
            if item.type == "page" and items[index + 1].type not in {"page", "ellipsis"}:
                wrapper_classes.append(self.get_style_class(pagination_styles, "lastPageNumberWrapper"))

            content = self.render_item(
                context,
                props,
                item,
                pagination_styles=pagination_styles,
                size=size,
            )
            rendered.append(
                self._render_tag("li", {"className": self.join_classes(*wrapper_classes)}, content)
            )
        return mark_safe("".join(rendered))

    def render_item(
        self,
        context: Context,
        props: dict[str, Any],
        item: PaginationItem,
        *,
        pagination_styles: Any,
        size: str,
    ) -> str:
        if item.type == "ellipsis":
            return self._render_tag(
                "div",
                {"className": self.get_style_class(pagination_styles, "ellipsisButton")},
                "&#8230;",
            )
        if item.page is None:
            raise ValueError(f"Pagination item '{item.type}' requires a page")

        if item.type == "previous":
            item_class = self.get_style_class(pagination_styles, "prevButton")
            label = "Previous Page"
            children = self.render_icon(_ARROW_LEFT_ICON, "xxs") + self._render_tag(
                "span",
                {"className": self.get_style_class(pagination_styles, "buttonText")},
                "Previous",
            )
        elif item.type == "next":
            item_class = self.get_style_class(pagination_styles, "nextButton")
            label = "Next Page"
            children = self._render_tag(
                "span",
                {"className": self.get_style_class(pagination_styles, "buttonText")},
                "Next",
            ) + self.render_icon(_ARROW_RIGHT_ICON, "xxs")
        else:
            item_class = self.join_classes(
                self.get_style_class(pagination_styles, "pageButton"),
                self.get_style_class(pagination_styles, "currentPage") if item.is_current else None,
            )
            label = f"Current Page, Page {item.page}" if item.is_current else f"Go to page {item.page}"
            children = self._render_tag("span", {}, str(item.page))

        button_styles = self.resolve_vanilla_extract_mapping(_BUTTON_STYLE_PATH)
        focus_ring_styles = self.resolve_vanilla_extract_mapping(_FOCUS_RING_STYLE_PATH)
        class_name = self.join_classes(
            self.get_style_class(focus_ring_styles, "base"),
            self.get_style_class(button_styles, "baseButton"),
            self.get_nested_style_class(button_styles, "sizes", size),
            item_class,
        )
        attrs: dict[str, Any] = {
            "href": None if item.is_disabled else self.build_page_url(context, props, item.page),
            "aria-label": label,
            "aria-current": "page" if item.is_current else None,
            "aria-disabled": "true" if item.is_disabled else None,
            "tabIndex": "-1" if item.is_disabled else None,
            "className": class_name,
            "data-apui": "button",
            "data-variant": "outlined",
            "data-color": "gray",
            "data-size": size,
            "data-shape": "default",
            "data-disabled": "true" if item.is_disabled else None,
        }
        return self._render_tag("a", attrs, children)

    def build_page_url(self, context: Context, props: dict[str, Any], page: int) -> str:
        request = context.get("request")
        if request is not None and hasattr(request, "GET") and hasattr(request, "path"):
            path = request.path
            params = request.GET.copy()
        else:
            path = "/"
            params = QueryDict(mutable=True)

        page_query_param = str(props.get("pageQueryParam", "page"))
        page_size_query_param = str(props.get("pageSizeQueryParam", "pageSize"))
        # Page-size selection is intentionally unsupported, matching renderPaginationItemAsLink's
        # non-selectable mode by removing any stale page-size parameter.
        params.pop(page_size_query_param, None)
        if page == 1:
            params.pop(page_query_param, None)
        else:
            params[page_query_param] = str(page)
        query_string = params.urlencode()
        return f"{path}?{query_string}" if query_string else path

    @staticmethod
    def inclusive_range(start: int, end: int) -> list[int]:
        if start > end:
            return []
        return list(range(start, end + 1))

    @staticmethod
    def page_item(page: int, current_page: int, is_disabled: bool) -> PaginationItem:
        return PaginationItem(
            type="page",
            page=page,
            is_current=page == current_page,
            is_disabled=is_disabled,
        )
