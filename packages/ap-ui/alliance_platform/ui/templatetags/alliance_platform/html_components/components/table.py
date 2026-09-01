"""Static HTML renderers for the Alliance UI table components.

These mirror ``@alliancesoftware/ui``'s ``Table`` (see ``components/table/Table.tsx``) for the
read-only CRUD list case: the same markup structure, classes and state data attributes, but no
JavaScript runtime. Structural styling hangs off the ``tableWrapper`` class on the root element —
rows/cells are styled through element and data-attribute selectors (``[data-align]``,
``[data-has-header]`` etc.) so only the root and the header chrome (sort indicator, header
content) carry classes. Sorting is expressed as plain links that update a backend query parameter
(mirroring ``ColumnHeaderLink.tsx`` / ``useTableSorter.ts``); row selection, client-side sorting
and the React Aria keyboard grid behaviour are intentionally unsupported.

Because the React table is an interactive ARIA grid and the static table is not, native table
semantics are preferred: no grid roles or tab indexes are rendered, ``aria-sort``/``scope="col"``
are set on header cells, and row-header cells render as ``<td role="rowheader">`` (rather than
``<th scope="row">``) so browser default ``<th>`` styling cannot diverge from the React output.

Cross-component coordination (column metadata inherited by body cells, row/cell counting for the
empty state) is done through a :class:`TableRenderState` stack stored in
``context.render_context``, which survives ``{% include %}`` (including ``only``) within a single
template render.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from dataclasses import field
from decimal import Decimal
import re
from typing import Any
from typing import Iterator
from typing import Literal
from typing import Mapping
import warnings

from django.template import Context
from django.utils.functional import Promise
from django.utils.html import conditional_escape
from django.utils.safestring import mark_safe

from alliance_platform.frontend.bundler.frontend_resource import FrontendResource
from alliance_platform.frontend.templatetags.react import OmitComponentFromRendering
from alliance_platform.ui.icons import get_static_icon_resource

from ..base import BaseHtmlUIComponentRenderer
from ..base import style_dict_to_string
from ..base import to_html_attr_name
from ..content import render_content
from ..static_icon import ICON_STYLE_PATH

_TABLE_STYLE_PATH = "@alliancesoftware/ui/components/table/Table.css.ts"

# Key used in ``context.render_context`` for the stack of in-progress table renders.
_TABLE_STATE_KEY = "alliance_platform_ui_table_state"

VALID_SORT_MODES = ("single", "multiple")
VALID_SORT_BEHAVIORS = ("toggle", "replace")
VALID_TABLE_MODES = ("default", "edit")
VALID_ALIGNMENTS = ("start", "center", "end")
VALID_SORT_DIRECTIONS = ("ascending", "descending")

DEFAULT_SORT_QUERY_PARAM = "ordering"

_ARROW_UP_ICON = "ArrowUpOutlined"
_ARROW_DOWN_ICON = "ArrowDownOutlined"

# Inline styles rendered by react-aria's VisuallyHidden, used for hideHeader content. There is no
# shared visually-hidden class in the design system so the same inline convention is used here.
_VISUALLY_HIDDEN_STYLE = (
    "border: 0; clip: rect(0 0 0 0); clip-path: inset(50%); height: 1px; margin: -1px; "
    "overflow: hidden; padding: 0; position: absolute; width: 1px; white-space: nowrap"
)

# Matches event handler props in any of the forms they can reach us in after prop normalization
# (onClick, onclick, on_click -> onClick). These must never be rendered: a string value would
# become a live inline event handler attribute, which React never renders.
_EVENT_HANDLER_PROP_RE = re.compile(r"^on[A-Za-z]")

_EVENT_HANDLER_REASON = "event handlers are not supported by static table components"
_SELECTION_REASON = "row selection is not supported by static table components yet"
_SORT_CALLBACK_REASON = "client-side sort callbacks are not supported by static table components"
_COLLECTION_REASON = "collection render props are not supported by static table components"
_NESTED_COLUMNS_REASON = "nested/grouped columns are not supported by static table components"

_TABLE_UNSUPPORTED_PROPS: Mapping[str, str] = {
    "selectionMode": _SELECTION_REASON,
    "selectionBehavior": _SELECTION_REASON,
    "selectedKeys": _SELECTION_REASON,
    "defaultSelectedKeys": _SELECTION_REASON,
    "onSelectionChange": _SELECTION_REASON,
    "showSelectionCheckboxes": _SELECTION_REASON,
    "disabledKeys": _SELECTION_REASON,
    "disabledBehavior": _SELECTION_REASON,
    "onSortChange": _SORT_CALLBACK_REASON,
    "sortFunction": _SORT_CALLBACK_REASON,
    "defaultSortOrder": "uncontrolled sort state is not supported by static table components; pass sortOrder",
    "items": _COLLECTION_REASON,
    "columns": _COLLECTION_REASON,
    "columnHeaderElementType": (
        "custom column header element types are not supported by static table components"
    ),
}


def _is_scalar_prop_value(value: Any) -> bool:
    return isinstance(value, (str, int, float, bool, Decimal, Promise)) or value is None


def _pixelify(value: Any) -> str:
    """Append ``px`` to bare numbers, matching the React ``pixelify('width', value)`` helper."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if value == 0:
            return "0"
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        return f"{value}px"
    return str(value)


def _coerce_int(value: Any) -> int | None:
    try:
        if isinstance(value, bool):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


@dataclass
class TableSortDescriptor:
    column: str
    direction: Literal["ascending", "descending"]


@dataclass
class TableColumnState:
    key: str | None
    align: Literal["start", "center", "end"] | None
    is_row_header: bool
    allows_sorting: bool
    sort_direction: Literal["ascending", "descending"] | None
    sort_position: int | None
    show_sort_position: bool


@dataclass
class TableRenderState:
    sort_order: list[TableSortDescriptor]
    sort_mode: Literal["single", "multiple"]
    sort_behavior: Literal["toggle", "replace"]
    sort_query_param: str
    #: rendered empty state content, or None when the empty state is disabled
    empty_state_html: str | None
    columns: list[TableColumnState] = field(default_factory=list)
    row_count: int = 0
    #: index of the next cell within the current row, or None outside a row
    current_row_cell_index: int | None = None
    #: True once any column explicitly passed isRowHeader=True; when False the first column is
    #: the row header by default (matching the React Table)
    has_explicit_row_header: bool = False
    #: used to warn once per table when rows contain more cells than registered columns
    warned_extra_cells: bool = False
    #: row_count snapshots pushed when a table_body starts rendering and popped when it finishes,
    #: so it can tell whether any of its own rows rendered. Kept here (rather than on the renderer)
    #: because renderer instances are template nodes and must not carry per-render state.
    body_start_row_counts: list[int] = field(default_factory=list)


def get_current_table_state(context: Context) -> TableRenderState | None:
    stack = context.render_context.get(_TABLE_STATE_KEY)
    if not stack:
        return None
    return stack[-1]


@contextmanager
def _push_table_state(context: Context, state: TableRenderState) -> Iterator[None]:
    stack = context.render_context.get(_TABLE_STATE_KEY)
    if stack is None:
        stack = []
        context.render_context[_TABLE_STATE_KEY] = stack
    stack.append(state)
    try:
        yield
    finally:
        stack.pop()


class UITableComponentRendererBase(BaseHtmlUIComponentRenderer):
    """Shared prop validation for the static table component renderers.

    Mirrors the input renderer policy: event handler props and React-only props warn and are
    dropped, unknown props warn rather than rendering arbitrary attributes, and ``data-*``/
    ``aria-*`` attributes pass through only where the spec allows it.
    """

    #: registered dispatcher name, used in warning messages
    component_name: str
    #: props (after normalization) the component understands
    supported_props: frozenset[str] = frozenset()
    #: props rejected with a specific reason instead of the generic unknown-prop warning
    unsupported_prop_reasons: Mapping[str, str] = {}
    #: whether arbitrary data-*/aria-* attributes pass through to the rendered element
    allow_data_aria_props = False
    #: aria-* attribute names allowed even when allow_data_aria_props is False
    extra_allowed_aria_props: frozenset[str] = frozenset()
    #: supported props that may hold non-scalar values
    non_scalar_props: frozenset[str] = frozenset()
    #: supported props where an explicit None is meaningful (kept) rather than treated as unset
    none_meaningful_props: frozenset[str] = frozenset()
    requires_table = True

    def resolve_props(self, context: Context) -> dict[str, Any]:
        if self.requires_table and get_current_table_state(context) is None:
            self.warn_outside_table()
            raise OmitComponentFromRendering()
        return self.filter_component_props(super().resolve_props(context))

    def filter_component_props(self, props: dict[str, Any]) -> dict[str, Any]:
        filtered: dict[str, Any] = {}
        for key, value in props.items():
            if value is None:
                # Treat None the same as an unset prop, mirroring undefined in JSX. Props in
                # none_meaningful_props mirror React props where null overrides a default.
                if key in self.none_meaningful_props and key in self.supported_props:
                    filtered[key] = value
                continue
            reason = self.unsupported_prop_reasons.get(key)
            if reason:
                warnings.warn(f"Prop '{key}' will be ignored: {reason}")
                continue
            if _EVENT_HANDLER_PROP_RE.match(key):
                warnings.warn(f"Prop '{key}' will be ignored: {_EVENT_HANDLER_REASON}")
                continue
            attr_name = to_html_attr_name(key)
            if attr_name.startswith("data-") or attr_name.startswith("aria-"):
                if not self.allow_data_aria_props and attr_name not in self.extra_allowed_aria_props:
                    warnings.warn(
                        f"Prop '{key}' is not supported on '{self.component_name}' and will be ignored"
                    )
                    continue
                if not _is_scalar_prop_value(value):
                    warnings.warn(
                        f"Prop '{key}' with non-scalar value is not supported by static table "
                        "components and will be ignored"
                    )
                    continue
                filtered[attr_name] = value
                continue
            if key not in self.supported_props:
                warnings.warn(
                    f"Prop '{key}' is not a supported '{self.component_name}' prop and will be ignored"
                )
                continue
            if key == "style":
                if not isinstance(value, (str, dict)):
                    warnings.warn("Prop 'style' must be a string or dict; it will be ignored")
                    continue
            elif not _is_scalar_prop_value(value) and key not in self.non_scalar_props:
                warnings.warn(
                    f"Prop '{key}' with non-scalar value is not supported by static table "
                    "components and will be ignored"
                )
                continue
            filtered[key] = value
        return filtered

    def resolve_table_styles(self) -> Any:
        return self.resolve_vanilla_extract_mapping(_TABLE_STYLE_PATH)

    def warn_outside_table(self):
        warnings.warn(
            f"'{self.component_name}' was rendered outside of a '{{% ui \"table\" %}}' component; "
            "rendering nothing"
        )

    def collect_data_aria_attrs(self, props: dict[str, Any]) -> dict[str, Any]:
        return {
            key: value for key, value in props.items() if key.startswith("data-") or key.startswith("aria-")
        }


class UITableRenderer(UITableComponentRendererBase):
    component_name = "table"
    requires_table = False
    supported_props = frozenset(
        {
            "id",
            "className",
            "style",
            "header",
            "footer",
            "mode",
            "sortOrder",
            "sortMode",
            "sortBehavior",
            "sortQueryParam",
            "renderEmptyState",
            "emptyState",
        }
    )
    unsupported_prop_reasons = _TABLE_UNSUPPORTED_PROPS
    extra_allowed_aria_props = frozenset({"aria-label", "aria-labelledby", "aria-describedby"})
    non_scalar_props = frozenset({"sortOrder", "header", "footer", "renderEmptyState", "emptyState"})
    none_meaningful_props = frozenset({"renderEmptyState", "emptyState"})

    def resolve_component_resources(self) -> list[FrontendResource]:
        # Icon.css is included unconditionally (sortable columns may render sort icons) to keep
        # resource discovery deterministic.
        return [
            self.resolve_frontend_resource(_TABLE_STYLE_PATH),
            self.resolve_frontend_resource(ICON_STYLE_PATH),
            get_static_icon_resource(_ARROW_UP_ICON, origin=self.origin),
            get_static_icon_resource(_ARROW_DOWN_ICON, origin=self.origin),
        ]

    def render_children_for_component(self, context: Context, props: dict[str, Any]) -> str:
        with _push_table_state(context, self.build_table_state(context, props)):
            return self.render_children(context)

    def build_table_state(self, context: Context, props: dict[str, Any]) -> TableRenderState:
        sort_mode = self.validate_enum_prop(
            props,
            prop_name="sortMode",
            valid_values=VALID_SORT_MODES,
            default_value="single",
        )
        sort_behavior = self.validate_enum_prop(
            props,
            prop_name="sortBehavior",
            valid_values=VALID_SORT_BEHAVIORS,
            default_value="toggle",
        )
        sort_query_param = str(props.get("sortQueryParam") or DEFAULT_SORT_QUERY_PARAM)
        return TableRenderState(
            sort_order=self.resolve_sort_order(props),
            sort_mode=sort_mode,  # type: ignore[arg-type] # validated above
            sort_behavior=sort_behavior,  # type: ignore[arg-type] # validated above
            sort_query_param=sort_query_param,
            empty_state_html=self.resolve_empty_state_html(context, props),
        )

    def resolve_sort_order(self, props: dict[str, Any]) -> list[TableSortDescriptor]:
        raw_sort_order = props.get("sortOrder")
        if raw_sort_order is None:
            return []
        if not isinstance(raw_sort_order, (list, tuple)):
            warnings.warn(
                "Prop 'sortOrder' must be a list of sort descriptors "
                '({"column": ..., "direction": ...}); it will be ignored'
            )
            return []
        descriptors: list[TableSortDescriptor] = []
        for entry in raw_sort_order:
            column = entry.get("column") if isinstance(entry, dict) else None
            direction = entry.get("direction") if isinstance(entry, dict) else None
            if not column or direction not in VALID_SORT_DIRECTIONS:
                warnings.warn(f"Ignoring invalid 'sortOrder' descriptor: {entry!r}")
                continue
            descriptors.append(TableSortDescriptor(column=str(column), direction=direction))
        return descriptors

    def resolve_empty_state_html(self, context: Context, props: dict[str, Any]) -> str | None:
        # renderEmptyState matches the React prop name; emptyState is accepted as a friendlier
        # alias. Explicit None or False disables the empty state (mirroring
        # renderEmptyState={null} in React); True or an absent prop uses the React default.
        if "renderEmptyState" in props:
            value = props["renderEmptyState"]
        elif "emptyState" in props:
            value = props["emptyState"]
        else:
            value = True
        if value is None or value is False:
            return None
        if value is True:
            return "<em>No results</em>"
        return render_content(value, context, prop_name="renderEmptyState", origin=self.origin)

    def render_component(self, context: Context, props: dict[str, Any], children_html: str) -> str:
        mode = self.validate_enum_prop(
            props,
            prop_name="mode",
            valid_values=VALID_TABLE_MODES,
            default_value="default",
        )
        table_styles = self.resolve_table_styles()

        header_html = render_content(props.get("header"), context, prop_name="header", origin=self.origin)
        footer_html = render_content(props.get("footer"), context, prop_name="footer", origin=self.origin)
        has_header = bool(header_html)
        has_footer = bool(footer_html)

        wrapper_attrs: dict[str, Any] = {
            "data-apui": "table",
            "data-mode": mode,
            # These are load-bearing for styling: the stylesheet keys header/footer chrome off
            # [data-has-header]/[data-has-footer] on the tableWrapper class.
            "data-has-header": "true" if has_header else None,
            "data-has-footer": "true" if has_footer else None,
            "className": self.join_classes(
                self.get_style_class(table_styles, "tableWrapper"),
                props.get("className"),
            ),
            "style": props.get("style"),
        }

        table_attrs: dict[str, Any] = {
            "id": props.get("id"),
            "aria-label": props.get("aria-label"),
            "aria-labelledby": props.get("aria-labelledby"),
            "aria-describedby": props.get("aria-describedby"),
        }
        table_html = self._render_tag("table", table_attrs, children_html)
        # The horizontal scroll container is a plain div; the stylesheet targets it with
        # `${tableWrapper} > div:has(> table)`.
        scroll_html = f"<div>{table_html}</div>"

        return self._render_tag("div", wrapper_attrs, f"{header_html}{scroll_html}{footer_html}")


class UITableHeaderRenderer(UITableComponentRendererBase):
    component_name = "table_header"
    # The React TableHeader accepts no styling props; nested/grouped columns are a non-goal.
    supported_props = frozenset()
    unsupported_prop_reasons = {"columns": _COLLECTION_REASON}

    def render_component(self, context: Context, props: dict[str, Any], children_html: str) -> str:
        # Header rows carry no class; the stylesheet targets `thead tr` under the tableWrapper.
        return mark_safe(f"<thead><tr>{children_html}</tr></thead>")


class UITableColumnRenderer(UITableComponentRendererBase):
    component_name = "table_column"
    supported_props = frozenset(
        {
            "id",
            "className",
            "style",
            "key",
            "align",
            "width",
            "colSpan",
            "isRowHeader",
            "hideHeader",
            "allowsSorting",
            "sortHref",
            "sortDirection",
            "sortPosition",
            "showSortPosition",
        }
    )
    unsupported_prop_reasons = {"childColumns": _NESTED_COLUMNS_REASON}

    def render_component(self, context: Context, props: dict[str, Any], children_html: str) -> str:
        state = get_current_table_state(context)
        assert state is not None

        align = self.validate_optional_enum_prop(props, prop_name="align", valid_values=VALID_ALIGNMENTS)
        explicit_direction = self.validate_optional_enum_prop(
            props, prop_name="sortDirection", valid_values=VALID_SORT_DIRECTIONS
        )
        key = props.get("key")
        key = str(key) if key is not None else None
        allows_sorting = bool(props.get("allowsSorting"))
        is_row_header = bool(props.get("isRowHeader"))
        col_span = _coerce_int(props.get("colSpan"))
        spans_multiple = col_span is not None and col_span > 1

        descriptor: TableSortDescriptor | None = None
        if key is not None:
            descriptor = next((entry for entry in state.sort_order if entry.column == key), None)

        sort_direction = explicit_direction or (descriptor.direction if descriptor else None)
        sort_position = _coerce_int(props.get("sortPosition"))
        if sort_position is None and descriptor is not None:
            sort_position = state.sort_order.index(descriptor) + 1
        if "showSortPosition" in props:
            show_sort_position = bool(props["showSortPosition"])
        else:
            show_sort_position = state.sort_mode == "multiple" and len(state.sort_order) > 1

        column_state = TableColumnState(
            key=key,
            align=align,  # type: ignore[arg-type] # validated above
            is_row_header=is_row_header,
            allows_sorting=allows_sorting,
            sort_direction=sort_direction,  # type: ignore[arg-type] # validated above
            sort_position=sort_position,
            show_sort_position=show_sort_position,
        )
        state.columns.append(column_state)
        if is_row_header:
            state.has_explicit_row_header = True

        table_styles = self.resolve_table_styles()

        href: str | None = None
        if allows_sorting:
            sort_href = props.get("sortHref")
            if sort_href is not None:
                href = str(sort_href)
            elif key is not None:
                href = self.build_sort_url(context, state, key)
            if href is None:
                warnings.warn(
                    f"Could not build a sort URL for column '{key or '<no key>'}': pass 'sortHref', or "
                    "pass 'key' and ensure 'request' is available in the template context. The header "
                    "will render without a link."
                )

        content_html = self.render_header_content(props, children_html, table_styles, href)
        sort_wrapper_html = ""
        if allows_sorting:
            sort_wrapper_html = self.render_sort_wrapper(column_state, table_styles)
        header_cell_wrapper_class = self.get_style_class(table_styles, "headerCellWrapper")
        cell_children = (
            f'<div class="{conditional_escape(header_cell_wrapper_class)}">'
            f"{content_html}{sort_wrapper_html}</div>"
        )

        # aria-sort: 'ascending'/'descending' when sorted, 'none' when sortable but unsorted,
        # otherwise unset. See the comment in Table.tsx around aria-sort for background.
        aria_sort = None
        if allows_sorting:
            aria_sort = sort_direction or "none"

        attrs: dict[str, Any] = {
            # Header cells carry no default classes; alignment and multi-span styling are driven
            # by the data attributes ([data-align], [data-spans-multiple]) under the tableWrapper.
            "className": props.get("className"),
            "id": props.get("id"),
            "style": self.resolve_column_style(props, table_styles),
            "data-align": align,
            "data-sort-direction": sort_direction,
            "data-spans-multiple": "true" if spans_multiple else None,
            "colspan": col_span,
            "scope": "col",
            "aria-sort": aria_sort,
        }
        return self._render_tag("th", attrs, cell_children)

    def render_header_content(
        self,
        props: dict[str, Any],
        children_html: str,
        table_styles: Any,
        href: str | None,
    ) -> str:
        content_class = conditional_escape(self.get_style_class(table_styles, "headerCellContent"))
        if href is not None:
            content = f'<a class="{content_class}" href="{conditional_escape(href)}">{children_html}</a>'
        else:
            content = f'<div class="{content_class}">{children_html}</div>'
        if props.get("hideHeader"):
            # React wraps the content in react-aria's VisuallyHidden (plus a focus tooltip the
            # static renderer cannot provide). The text must stay available to screen readers.
            content = f'<div style="{_VISUALLY_HIDDEN_STYLE}">{content}</div>'
        return content

    def render_sort_wrapper(self, column_state: TableColumnState, table_styles: Any) -> str:
        if column_state.sort_direction == "descending":
            icon_html = self.render_icon(
                _ARROW_DOWN_ICON, "xs", [self.get_style_class(table_styles, "sortIcon")]
            )
        elif column_state.sort_direction == "ascending":
            icon_html = self.render_icon(
                _ARROW_UP_ICON, "xs", [self.get_style_class(table_styles, "sortIcon")]
            )
        else:
            icon_html = self.render_icon(
                _ARROW_UP_ICON, "xs", [self.get_style_class(table_styles, "sortIconUnsorted")]
            )
        position_html = ""
        if column_state.show_sort_position:
            position = column_state.sort_position
            position_html = f"<span>{position if position is not None else ''}</span>"
        sort_wrapper_class = self.get_style_class(table_styles, "sortWrapper")
        return f'<span class="{conditional_escape(sort_wrapper_class)}">{icon_html}{position_html}</span>'

    def resolve_column_style(self, props: dict[str, Any], table_styles: Any) -> Any:
        style = props.get("style")
        width = props.get("width")
        if width is None:
            return style
        width_var = self.resolve_column_width_var(table_styles)
        if width_var is None:
            warnings.warn(
                "Could not resolve the table columnWidth CSS variable; the 'width' prop will be ignored"
            )
            return style
        width_style = {width_var: _pixelify(width)}
        if isinstance(style, dict):
            return {**style, **width_style}
        if isinstance(style, str) and style.strip():
            return f"{style.rstrip().rstrip(';')}; {style_dict_to_string(width_style)}"
        return width_style

    def resolve_column_width_var(self, table_styles: Any) -> str | None:
        """Resolve the CSS custom property name for the table columnWidth theme var.

        The vanilla-extract mapping serializes theme vars as ``var(--name)`` references (the same
        values ``assignInlineVars`` accepts in the React implementation).
        """
        var_reference = self.get_nested_style_class(table_styles, "vars", "columnWidth")
        if not var_reference:
            return None
        match = re.fullmatch(r"var\((--[^,)]+)(?:,.*)?\)", var_reference.strip())
        if match:
            return match.group(1)
        if var_reference.startswith("--"):
            return var_reference
        return None

    def build_sort_url(self, context: Context, state: TableRenderState, key: str) -> str | None:
        request = context.get("request")
        if request is None or not hasattr(request, "GET") or not hasattr(request, "path"):
            return None
        params = request.GET.copy()
        next_order = self.get_next_sort_order(state, key)
        if next_order:
            params[state.sort_query_param] = ",".join(
                f"{'-' if entry.direction == 'descending' else ''}{entry.column}" for entry in next_order
            )
        else:
            params.pop(state.sort_query_param, None)
        query_string = params.urlencode()
        return f"{request.path}?{query_string}" if query_string else request.path

    def get_next_sort_order(self, state: TableRenderState, key: str) -> list[TableSortDescriptor]:
        """The sort order the column's link should apply, mirroring ``useTableSorter.getSortOrder``.

        The direction cycle is unsorted -> ascending -> descending -> off. ``replace`` mode matches
        the React behaviour without the meta/ctrl force-toggle (which requires JavaScript).
        """
        current = next((entry for entry in state.sort_order if entry.column == key), None)
        current_direction = current.direction if current else None
        if state.sort_mode == "single" or state.sort_behavior == "replace":
            if current_direction == "descending":
                return []
            direction: Literal["ascending", "descending"] = (
                "descending" if current_direction == "ascending" else "ascending"
            )
            return [TableSortDescriptor(column=key, direction=direction)]
        if current_direction == "descending":
            return [entry for entry in state.sort_order if entry.column != key]
        if current_direction == "ascending":
            return [
                TableSortDescriptor(column=key, direction="descending") if entry.column == key else entry
                for entry in state.sort_order
            ]
        return [*state.sort_order, TableSortDescriptor(column=key, direction="ascending")]


class UITableBodyRenderer(UITableComponentRendererBase):
    component_name = "table_body"
    supported_props = frozenset({"id", "className", "style"})
    unsupported_prop_reasons = {"items": _COLLECTION_REASON}
    allow_data_aria_props = True

    def render_children_for_component(self, context: Context, props: dict[str, Any]) -> str:
        # The row-count snapshot lives on the render state (in context.render_context), not on
        # self: this renderer is a template node, and per-render state on the instance would leak
        # between concurrent renders of a shared compiled template.
        state = get_current_table_state(context)
        assert state is not None
        state.body_start_row_counts.append(state.row_count)
        return self.render_children(context)

    def render_component(self, context: Context, props: dict[str, Any], children_html: str) -> str:
        state = get_current_table_state(context)
        assert state is not None
        if state.body_start_row_counts:
            rows_before = state.body_start_row_counts.pop()
            if state.row_count == rows_before and state.empty_state_html is not None:
                children_html += self.render_empty_state(state)
        attrs: dict[str, Any] = {
            "className": props.get("className"),
            "id": props.get("id"),
            "style": props.get("style"),
            **self.collect_data_aria_attrs(props),
        }
        return self._render_tag("tbody", attrs, children_html)

    def render_empty_state(self, state: TableRenderState) -> str:
        table_styles = self.resolve_table_styles()
        no_results_class = self.get_style_class(table_styles, "noResults")
        column_count = len(state.columns) or 1
        return (
            f'<tr><td colspan="{column_count}">'
            f'<div class="{conditional_escape(no_results_class)}">{state.empty_state_html}</div>'
            "</td></tr>"
        )


class UITableRowRenderer(UITableComponentRendererBase):
    component_name = "table_row"
    supported_props = frozenset({"id", "key", "className", "style"})
    unsupported_prop_reasons = {"isSelected": _SELECTION_REASON, "isDisabled": _SELECTION_REASON}
    allow_data_aria_props = True

    def render_children_for_component(self, context: Context, props: dict[str, Any]) -> str:
        state = get_current_table_state(context)
        assert state is not None
        previous_cell_index = state.current_row_cell_index
        state.current_row_cell_index = 0
        try:
            return self.render_children(context)
        finally:
            state.current_row_cell_index = previous_cell_index
            state.row_count += 1

    def render_component(self, context: Context, props: dict[str, Any], children_html: str) -> str:
        key = props.get("key")
        attrs: dict[str, Any] = {
            # Rows carry no default classes; the stylesheet targets `tbody tr` under the
            # tableWrapper.
            "className": props.get("className"),
            "id": props.get("id"),
            "style": props.get("style"),
            "data-key": str(key) if key is not None else None,
            **self.collect_data_aria_attrs(props),
        }
        return self._render_tag("tr", attrs, children_html)


class UITableCellRenderer(UITableComponentRendererBase):
    component_name = "table_cell"
    supported_props = frozenset({"id", "className", "style", "colSpan", "rowSpan"})
    allow_data_aria_props = True

    def render_component(self, context: Context, props: dict[str, Any], children_html: str) -> str:
        state = get_current_table_state(context)
        assert state is not None
        col_span = _coerce_int(props.get("colSpan"))
        row_span = _coerce_int(props.get("rowSpan"))

        column: TableColumnState | None = None
        cell_index: int | None = None
        if state.current_row_cell_index is None:
            warnings.warn(
                "'table_cell' was rendered outside of a '{% ui \"table_row\" %}' component; "
                "column metadata (alignment, row header) will not be applied"
            )
        else:
            cell_index = state.current_row_cell_index
            state.current_row_cell_index = cell_index + max(col_span or 1, 1)
            if cell_index < len(state.columns):
                column = state.columns[cell_index]
            elif not state.warned_extra_cells:
                state.warned_extra_cells = True
                warnings.warn(
                    "A 'table_row' rendered more 'table_cell' components than there are registered "
                    "'table_column' components; extra cells render without column metadata. "
                    "(warning shown once per table)"
                )

        align = column.align if column else None
        is_row_header = False
        if column is not None and cell_index is not None:
            is_row_header = column.is_row_header if state.has_explicit_row_header else cell_index == 0

        attrs: dict[str, Any] = {
            # Cells carry no default classes; cell typography and alignment are driven by the
            # `td` element and [data-align] selectors under the tableWrapper.
            "className": props.get("className"),
            "id": props.get("id"),
            "style": props.get("style"),
            "data-align": align,
            "colspan": col_span,
            "rowspan": row_span,
            # Rendered as <td role="rowheader"> rather than <th scope="row"> so browser default
            # <th> styling (bold, centered) cannot diverge from the React table's appearance.
            "role": "rowheader" if is_row_header else None,
            **self.collect_data_aria_attrs(props),
        }
        return self._render_tag("td", attrs, children_html)
