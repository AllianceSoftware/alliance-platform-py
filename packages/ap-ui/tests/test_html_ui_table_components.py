from __future__ import annotations

import warnings

from django.template import Context
from django.template import Template
from django.test import RequestFactory

from tests.parity.base import HtmlUIParityTestCase

BASIC_TABLE_TEMPLATE = (
    '{% ui "table" aria_label="User list" %}'
    '{% ui "table_header" %}'
    '{% ui "table_column" key="name" %}Name{% endui %}'
    '{% ui "table_column" key="email" %}Email{% endui %}'
    "{% endui %}"
    '{% ui "table_body" %}'
    '{% ui "table_row" key=1 %}'
    '{% ui "table_cell" %}Jane{% endui %}'
    '{% ui "table_cell" %}jane@example.com{% endui %}'
    "{% endui %}"
    "{% endui %}"
    "{% endui %}"
)


def make_sortable_table_template(
    table_props: str = "", columns: str | None = None, cells: str | None = None
) -> str:
    if columns is None:
        columns = (
            '{% ui "table_column" key="name" allows_sorting=True %}Name{% endui %}'
            '{% ui "table_column" key="email" allows_sorting=True %}Email{% endui %}'
        )
    if cells is None:
        cells = '{% ui "table_cell" %}Jane{% endui %}' * columns.count("table_column")
    return (
        '{% ui "table" aria_label="User list" ' + table_props + " %}"
        '{% ui "table_header" %}' + columns + "{% endui %}"
        '{% ui "table_body" %}{% ui "table_row" %}' + cells + "{% endui %}{% endui %}"
        "{% endui %}"
    )


class UITableComponentsTestCase(HtmlUIParityTestCase):
    """Unit tests for the static table components not covered by the parity fixtures."""

    request_factory = RequestFactory()

    def render_with_warnings(self, template_body: str, context_kwargs=None):
        with self.setup_render_context():
            with warnings.catch_warnings(record=True) as caught_warnings:
                warnings.simplefilter("always")
                output = self.render_ui_template(template_body, context_kwargs)
        return output, [str(item.message) for item in caught_warnings]

    def test_table_renders_full_structure(self):
        output, caught = self.render_with_warnings(BASIC_TABLE_TEMPLATE)
        self.assertEqual(caught, [])
        # Structural styling hangs off the tableWrapper class; rows/cells are styled through
        # element/data-attribute selectors and carry no classes of their own.
        self.assertIn(
            '<div data-apui="table" class="Table_tableWrapper">',
            output,
        )
        self.assertIn('<div><table aria-label="User list">', output)
        self.assertIn("<thead><tr>", output)
        self.assertIn(
            '<th scope="col">'
            '<div class="Table_headerCellWrapper"><div class="Table_headerCellContent">Name</div></div>'
            "</th>",
            output,
        )
        self.assertIn("<tbody>", output)
        self.assertIn('<tr data-key="1">', output)
        self.assertIn('<td role="rowheader">Jane</td>', output)
        self.assertIn("<td>jane@example.com</td>", output)
        # No ARIA grid behaviour is rendered by the static implementation
        self.assertNotIn('role="grid"', output)
        self.assertNotIn("tabindex", output)

    def test_class_kwargs_merge_with_default_classes(self):
        template = (
            '{% ui "table" aria_label="Users" class="my-table" %}'
            '{% ui "table_header" %}'
            '{% ui "table_column" class="my-column" %}Name{% endui %}'
            "{% endui %}"
            '{% ui "table_body" class="my-body" %}'
            '{% ui "table_row" class="my-row" %}'
            '{% ui "table_cell" class="my-cell" %}Jane{% endui %}'
            "{% endui %}"
            "{% endui %}"
            "{% endui %}"
        )
        output, caught = self.render_with_warnings(template)
        self.assertEqual(caught, [])
        # The wrapper merges the user class with tableWrapper; other elements have no default
        # classes so the user class renders alone.
        self.assertIn('class="Table_tableWrapper my-table"', output)
        self.assertIn('<th class="my-column" scope="col">', output)
        self.assertIn('<tbody class="my-body">', output)
        self.assertIn('<tr class="my-row">', output)
        self.assertIn('<td class="my-cell" role="rowheader">', output)

    def test_column_align_applies_to_header_and_body_cells(self):
        template = (
            '{% ui "table" aria_label="Users" %}'
            '{% ui "table_header" %}'
            '{% ui "table_column" %}Name{% endui %}'
            '{% ui "table_column" align="center" %}Active{% endui %}'
            '{% ui "table_column" align="end" %}Total{% endui %}'
            '{% ui "table_column" align="start" %}Notes{% endui %}'
            "{% endui %}"
            '{% ui "table_body" %}'
            '{% ui "table_row" %}'
            '{% ui "table_cell" %}Jane{% endui %}'
            '{% ui "table_cell" %}Yes{% endui %}'
            '{% ui "table_cell" %}10{% endui %}'
            '{% ui "table_cell" %}-{% endui %}'
            "{% endui %}"
            "{% endui %}"
            "{% endui %}"
        )
        output, caught = self.render_with_warnings(template)
        self.assertEqual(caught, [])
        # Alignment is styled entirely through the data-align attribute selectors, applied to the
        # header cell and inherited by body cells through the column metadata.
        self.assertIn('<th data-align="center" scope="col">', output)
        self.assertIn('<td data-align="center">Yes</td>', output)
        self.assertIn('<th data-align="end" scope="col">', output)
        self.assertIn('<td data-align="end">10</td>', output)
        self.assertIn('<th data-align="start" scope="col">', output)
        self.assertIn('<td data-align="start">-</td>', output)

    def test_invalid_align_warns_and_is_ignored(self):
        template = make_sortable_table_template(
            columns='{% ui "table_column" align="middle" %}Name{% endui %}'
        )
        output, caught = self.render_with_warnings(template)
        self.assertIn("Invalid 'align' prop passed: middle", caught)
        self.assertNotIn("data-align", output)

    def test_first_column_is_row_header_by_default(self):
        output, _ = self.render_with_warnings(BASIC_TABLE_TEMPLATE)
        self.assertIn('<td role="rowheader">Jane</td>', output)
        self.assertNotIn('role="rowheader">jane@example.com', output)

    def test_explicit_is_row_header_overrides_first_column_default(self):
        template = (
            '{% ui "table" aria_label="Users" %}'
            '{% ui "table_header" %}'
            '{% ui "table_column" %}Name{% endui %}'
            '{% ui "table_column" is_row_header=True %}Email{% endui %}'
            "{% endui %}"
            '{% ui "table_body" %}'
            '{% ui "table_row" %}'
            '{% ui "table_cell" %}Jane{% endui %}'
            '{% ui "table_cell" %}jane@example.com{% endui %}'
            "{% endui %}"
            "{% endui %}"
            "{% endui %}"
        )
        output, caught = self.render_with_warnings(template)
        self.assertEqual(caught, [])
        self.assertIn("<td>Jane</td>", output)
        self.assertIn('<td role="rowheader">jane@example.com</td>', output)

    def test_column_width_renders_css_variable(self):
        template = make_sortable_table_template(columns='{% ui "table_column" width=96 %}Name{% endui %}')
        output, caught = self.render_with_warnings(template)
        self.assertEqual(caught, [])
        self.assertIn('style="--components-table-columnWidth: 96px"', output)

    def test_column_width_string_value_used_verbatim(self):
        template = make_sortable_table_template(columns='{% ui "table_column" width="20%" %}Name{% endui %}')
        output, _ = self.render_with_warnings(template)
        self.assertIn('style="--components-table-columnWidth: 20%"', output)

    def test_hide_header_renders_visually_hidden_content(self):
        template = make_sortable_table_template(
            columns='{% ui "table_column" hide_header=True %}Actions{% endui %}'
        )
        output, caught = self.render_with_warnings(template)
        self.assertEqual(caught, [])
        self.assertIn(
            '<div style="border: 0; clip: rect(0 0 0 0); clip-path: inset(50%); height: 1px; '
            "margin: -1px; overflow: hidden; padding: 0; position: absolute; width: 1px; "
            'white-space: nowrap"><div class="Table_headerCellContent">Actions</div></div>',
            output,
        )

    # --- Sorting ---

    def test_sort_links_preserve_unrelated_query_params(self):
        request = self.request_factory.get("/users/?page=2&search=jane")
        template = make_sortable_table_template()
        output, caught = self.render_with_warnings(template, {"request": request})
        self.assertEqual(caught, [])
        self.assertIn('href="/users/?page=2&amp;search=jane&amp;ordering=name"', output)

    def test_sort_cycle_ascending_to_descending_to_off(self):
        template = make_sortable_table_template('sort_order=request|table_sort_order sort_mode="single"')
        # Unsorted -> ascending
        request = self.request_factory.get("/users/")
        output, _ = self.render_with_warnings(template, {"request": request})
        self.assertIn('href="/users/?ordering=name"', output)
        # Ascending -> descending
        request = self.request_factory.get("/users/?ordering=name")
        output, _ = self.render_with_warnings(template, {"request": request})
        self.assertIn('href="/users/?ordering=-name"', output)
        self.assertIn('aria-sort="ascending"', output)
        self.assertIn('data-sort-direction="ascending"', output)
        # Descending -> off
        request = self.request_factory.get("/users/?ordering=-name")
        output, _ = self.render_with_warnings(template, {"request": request})
        self.assertIn('href="/users/"', output)
        self.assertIn('aria-sort="descending"', output)
        self.assertIn('data-sort-direction="descending"', output)

    def test_sort_mode_single_replaces_other_descriptors(self):
        request = self.request_factory.get("/users/?ordering=-email")
        template = make_sortable_table_template('sort_order=request|table_sort_order sort_mode="single"')
        output, _ = self.render_with_warnings(template, {"request": request})
        # Clicking name only sorts by name; email descriptor is dropped
        self.assertIn('href="/users/?ordering=name"', output)

    def test_sort_mode_multiple_toggle_preserves_other_descriptors(self):
        request = self.request_factory.get("/users/?page=2&order=-name")
        template = make_sortable_table_template(
            'sort_order=request|table_sort_order:"order" sort_query_param="order" '
            'sort_mode="multiple" sort_behavior="toggle"'
        )
        output, caught = self.render_with_warnings(template, {"request": request})
        self.assertEqual(caught, [])
        # name is descending -> clicking it cycles off, keeping other params
        self.assertIn('href="/users/?page=2"', output)
        # email is unsorted -> clicking it appends to the existing order
        self.assertIn('href="/users/?page=2&amp;order=-name%2Cemail"', output)

    def test_sort_mode_multiple_replace_replaces_other_descriptors(self):
        request = self.request_factory.get("/users/?page=2&order=-name")
        template = make_sortable_table_template(
            'sort_order=request|table_sort_order:"order" sort_query_param="order" '
            'sort_mode="multiple" sort_behavior="replace"'
        )
        output, caught = self.render_with_warnings(template, {"request": request})
        self.assertEqual(caught, [])
        # email is unsorted -> clicking it replaces the whole order (no meta/ctrl toggle statically)
        self.assertIn('href="/users/?page=2&amp;order=email"', output)
        # name is descending -> clicking it cycles off
        self.assertIn('href="/users/?page=2"', output)

    def test_explicit_sort_href_bypasses_url_generation(self):
        template = make_sortable_table_template(
            columns=(
                '{% ui "table_column" allows_sorting=True sort_href="?order=-created_at" '
                'sort_direction="ascending" %}Created{% endui %}'
            )
        )
        output, caught = self.render_with_warnings(template)
        self.assertEqual(caught, [])
        self.assertIn('<a class="Table_headerCellContent" href="?order=-created_at">Created</a>', output)
        self.assertIn('aria-sort="ascending"', output)
        self.assertIn('data-sort-direction="ascending"', output)

    def test_sortable_column_without_url_warns_and_renders_non_link(self):
        template = make_sortable_table_template()
        output, caught = self.render_with_warnings(template)
        self.assertTrue(any("Could not build a sort URL for column 'name'" in item for item in caught))
        self.assertNotIn("<a ", output)
        # Sort styling/state still renders
        self.assertIn('aria-sort="none"', output)
        self.assertIn('<div class="Table_headerCellContent">Name</div>', output)
        self.assertIn("Table_sortIconUnsorted", output)

    def test_sort_icons_match_sort_state(self):
        request = self.request_factory.get("/users/?ordering=name,-email")
        template = make_sortable_table_template(
            'sort_order=request|table_sort_order sort_mode="multiple"',
            columns=(
                '{% ui "table_column" key="name" allows_sorting=True %}Name{% endui %}'
                '{% ui "table_column" key="email" allows_sorting=True %}Email{% endui %}'
                '{% ui "table_column" key="active" allows_sorting=True %}Active{% endui %}'
            ),
        )
        output, caught = self.render_with_warnings(template, {"request": request})
        self.assertEqual(caught, [])
        up_icon = 'd="M12 19V5M12 5L5 12M12 5L19 12"'
        down_icon = 'd="M12 5V19M12 19L19 12M12 19L5 12"'
        self.assertIn(up_icon, output)
        self.assertIn(down_icon, output)
        self.assertIn("Icon_icon Icon_variants_plain Icon_sizes_xs Table_sortIcon", output)
        self.assertIn("Icon_icon Icon_variants_plain Icon_sizes_xs Table_sortIconUnsorted", output)
        # Multi-sort with more than one descriptor shows sort positions
        self.assertIn('<span class="Table_sortWrapper">', output)
        self.assertIn('data-apui-slot="icon"', output)
        self.assertIn(f"<path {up_icon}", output)
        self.assertIn("<span>1</span>", output)
        self.assertIn("<span>2</span>", output)
        # Sortable but unsorted column renders an empty position placeholder
        self.assertIn("<span></span>", output)

    def test_non_sortable_column_renders_no_sort_markup(self):
        output, caught = self.render_with_warnings(BASIC_TABLE_TEMPLATE)
        self.assertEqual(caught, [])
        self.assertNotIn("aria-sort", output)
        self.assertNotIn("Table_sortWrapper", output)
        self.assertNotIn("<a ", output)

    # --- Empty state ---

    def test_empty_body_renders_default_empty_state_with_column_count(self):
        template = (
            '{% ui "table" aria_label="Users" %}'
            '{% ui "table_header" %}'
            '{% ui "table_column" %}Name{% endui %}'
            '{% ui "table_column" %}Email{% endui %}'
            '{% ui "table_column" %}Active{% endui %}'
            "{% endui %}"
            '{% ui "table_body" %}{% endui %}'
            "{% endui %}"
        )
        output, caught = self.render_with_warnings(template)
        self.assertEqual(caught, [])
        self.assertIn(
            '<tr><td colspan="3"><div class="Table_noResults"><em>No results</em></div></td></tr>',
            output,
        )

    def test_empty_state_custom_content(self):
        template = (
            '{% ui "table" aria_label="Users" empty_state="Nothing to see" %}'
            '{% ui "table_body" %}{% endui %}'
            "{% endui %}"
        )
        output, _ = self.render_with_warnings(template)
        self.assertIn(
            '<tr><td colspan="1"><div class="Table_noResults">Nothing to see</div></td></tr>', output
        )

    def test_empty_state_can_be_disabled(self):
        for disable_props in ("empty_state=False", "render_empty_state=None", "empty_state=None"):
            with self.subTest(disable_props=disable_props):
                template = (
                    '{% ui "table" aria_label="Users" ' + disable_props + " %}"
                    '{% ui "table_body" %}{% endui %}'
                    "{% endui %}"
                )
                output, caught = self.render_with_warnings(template)
                self.assertEqual(caught, [])
                self.assertNotIn("Table_noResults", output)
                self.assertNotIn("No results", output)

    def test_user_rendered_rows_prevent_empty_state(self):
        output, _ = self.render_with_warnings(BASIC_TABLE_TEMPLATE)
        self.assertNotIn("Table_noResults", output)

    # --- Header/footer ---

    def test_header_and_footer_content_affect_wrapper_state(self):
        template = (
            '{% ui "table" aria_label="Users" header="<h2>People</h2>"|safe footer="Footer text" %}'
            '{% ui "table_body" %}{% endui %}'
            "{% endui %}"
        )
        output, caught = self.render_with_warnings(template)
        self.assertEqual(caught, [])
        # data-has-header/footer are load-bearing: the stylesheet keys the header/footer chrome
        # off these attributes on the tableWrapper element.
        self.assertIn('data-has-header="true"', output)
        self.assertIn('data-has-footer="true"', output)
        self.assertIn("<h2>People</h2>", output)
        self.assertIn("Footer text</div>", output)

    def test_header_from_variable_is_escaped(self):
        # Note template string literals are marked safe by Django itself (the template author
        # wrote them); escaping applies to variable content.
        template = (
            '{% ui "table" aria_label="Users" header=header_content %}'
            '{% ui "table_body" %}{% endui %}'
            "{% endui %}"
        )
        output, _ = self.render_with_warnings(template, {"header_content": "<b>unsafe</b>"})
        self.assertIn("&lt;b&gt;unsafe&lt;/b&gt;", output)
        self.assertNotIn("<b>unsafe</b>", output)

    def test_react_edit_mode_warns_and_is_ignored(self):
        template = (
            '{% ui "table" aria_label="Users" mode="edit" %}{% ui "table_body" %}{% endui %}{% endui %}'
        )
        output, caught = self.render_with_warnings(template)
        self.assertEqual(
            caught,
            [
                "Prop 'mode' will be ignored: React Aria edit-mode keyboard handling is not used "
                "by static table components"
            ],
        )
        self.assertNotIn("data-mode", output)

    # --- Prop validation ---

    def test_event_handler_props_warn_and_are_never_rendered(self):
        template = (
            '{% ui "table" aria_label="Users" onClick="alert(1)" %}'
            '{% ui "table_header" %}'
            '{% ui "table_column" on_click="alert(2)" %}Name{% endui %}'
            "{% endui %}"
            '{% ui "table_body" %}'
            '{% ui "table_row" onclick="alert(3)" %}'
            '{% ui "table_cell" onDoubleClick="alert(4)" %}Jane{% endui %}'
            "{% endui %}"
            "{% endui %}"
            "{% endui %}"
        )
        output, caught = self.render_with_warnings(template)
        for prop_name in ("onClick", "onclick", "onDoubleClick"):
            self.assertIn(
                f"Prop '{prop_name}' will be ignored: event handlers are not supported by "
                "static table components",
                caught,
            )
        self.assertNotIn("alert", output)
        self.assertNotIn("onclick", output.lower())

    def test_sort_callback_props_warn_with_specific_message(self):
        template = (
            '{% ui "table" aria_label="Users" onSortChange="handleSort" %}'
            '{% ui "table_body" %}{% endui %}'
            "{% endui %}"
        )
        output, caught = self.render_with_warnings(template)
        self.assertIn(
            "Prop 'onSortChange' will be ignored: client-side sort callbacks are not supported "
            "by static table components",
            caught,
        )
        self.assertNotIn("onsortchange", output.lower())

    def test_selection_props_warn_and_are_ignored(self):
        template = (
            '{% ui "table" aria_label="Users" selection_mode="multiple" selected_keys=selected %}'
            '{% ui "table_body" %}'
            '{% ui "table_row" is_selected=True %}{% ui "table_cell" %}Jane{% endui %}{% endui %}'
            "{% endui %}"
            "{% endui %}"
        )
        output, caught = self.render_with_warnings(template, {"selected": [1, 2]})
        for prop_name in ("selectionMode", "selectedKeys", "isSelected"):
            self.assertIn(
                f"Prop '{prop_name}' will be ignored: row selection is not supported by static "
                "table components yet",
                caught,
            )
        self.assertNotIn("data-selected", output)
        self.assertNotIn("selectionmode", output.lower())

    def test_collection_props_warn_and_are_ignored(self):
        template = (
            '{% ui "table" aria_label="Users" items=items columns=columns %}'
            '{% ui "table_body" %}{% endui %}'
            "{% endui %}"
        )
        output, caught = self.render_with_warnings(template, {"items": [1], "columns": ["a"]})
        for prop_name in ("items", "columns"):
            self.assertIn(
                f"Prop '{prop_name}' will be ignored: collection render props are not supported "
                "by static table components",
                caught,
            )

    def test_data_and_aria_passthrough_only_on_supported_elements(self):
        template = (
            '{% ui "table" aria_label="Users" data_testid="user-table" %}'
            '{% ui "table_header" %}'
            '{% ui "table_column" data_testid="name-column" %}Name{% endui %}'
            "{% endui %}"
            '{% ui "table_body" data_testid="body" %}'
            '{% ui "table_row" data_testid="row" aria_live="polite" %}'
            '{% ui "table_cell" data_testid="cell" aria_current="true" %}Jane{% endui %}'
            "{% endui %}"
            "{% endui %}"
            "{% endui %}"
        )
        output, caught = self.render_with_warnings(template)
        # Supported on body/row/cell
        self.assertIn('<tbody data-testid="body">', output)
        self.assertIn('data-testid="row"', output)
        self.assertIn('aria-live="polite"', output)
        self.assertIn('data-testid="cell"', output)
        self.assertIn('aria-current="true"', output)
        # Not supported on table (other than labelling props) or column
        self.assertNotIn('data-testid="user-table"', output)
        self.assertNotIn('data-testid="name-column"', output)
        self.assertIn(
            "Prop 'data-testid' is not supported on 'table' and will be ignored",
            caught,
        )
        self.assertIn(
            "Prop 'data-testid' is not supported on 'table_column' and will be ignored",
            caught,
        )

    def test_table_aria_labelling_props_are_supported(self):
        template = (
            '{% ui "table" aria_labelledby="heading-id" aria_describedby="desc-id" %}'
            '{% ui "table_body" %}{% endui %}'
            "{% endui %}"
        )
        output, caught = self.render_with_warnings(template)
        self.assertEqual(caught, [])
        self.assertIn('<table aria-labelledby="heading-id" aria-describedby="desc-id">', output)

    def test_unknown_props_warn_and_are_dropped(self):
        template = (
            '{% ui "table" aria_label="Users" unknownProp="nope" %}'
            '{% ui "table_header" unknown_header="x" %}'
            '{% ui "table_column" unknown_column="x" %}Name{% endui %}'
            "{% endui %}"
            '{% ui "table_body" %}'
            '{% ui "table_row" unknown_row="x" %}'
            '{% ui "table_cell" unknown_cell="x" %}Jane{% endui %}'
            "{% endui %}"
            "{% endui %}"
            "{% endui %}"
        )
        output, caught = self.render_with_warnings(template)
        for prop_name, component_name in (
            ("unknownProp", "table"),
            ("unknownHeader", "table_header"),
            ("unknownColumn", "table_column"),
            ("unknownRow", "table_row"),
            ("unknownCell", "table_cell"),
        ):
            self.assertIn(
                f"Prop '{prop_name}' is not a supported '{component_name}' prop and will be ignored",
                caught,
            )
        self.assertNotIn("nope", output)
        self.assertNotIn("unknown", output.lower())

    def test_non_scalar_prop_values_warn_and_are_ignored(self):
        template = (
            '{% ui "table" aria_label="Users" %}'
            '{% ui "table_body" %}'
            '{% ui "table_row" key=bad_value %}{% ui "table_cell" %}Jane{% endui %}{% endui %}'
            "{% endui %}"
            "{% endui %}"
        )
        output, caught = self.render_with_warnings(template, {"bad_value": {"nested": "dict"}})
        self.assertIn(
            "Prop 'key' with non-scalar value is not supported by static table components "
            "and will be ignored",
            caught,
        )
        self.assertNotIn("data-key", output)

    # --- Orphan child behaviour ---

    def test_cell_outside_table_warns_and_renders_nothing(self):
        output, caught = self.render_with_warnings('{% ui "table_cell" %}Orphan{% endui %}')
        self.assertTrue(
            any("'table_cell' was rendered outside" in item for item in caught),
            caught,
        )
        self.assertEqual(output, "")

    def test_child_components_outside_table_warn_and_render_nothing(self):
        for template in (
            '{% ui "table_header" %}{% endui %}',
            '{% ui "table_body" %}{% endui %}',
            '{% ui "table_row" %}{% endui %}',
        ):
            with self.subTest(template=template):
                output, caught = self.render_with_warnings(template)
                self.assertTrue(
                    any("was rendered outside of a" in item for item in caught),
                    caught,
                )
                self.assertEqual(output, "")

    def test_extra_cells_warn_once_per_table_and_render(self):
        template = (
            '{% ui "table" aria_label="Users" %}'
            '{% ui "table_header" %}{% ui "table_column" %}Name{% endui %}{% endui %}'
            '{% ui "table_body" %}'
            '{% ui "table_row" %}'
            '{% ui "table_cell" %}Jane{% endui %}'
            '{% ui "table_cell" %}extra-1{% endui %}'
            '{% ui "table_cell" %}extra-2{% endui %}'
            "{% endui %}"
            "{% endui %}"
            "{% endui %}"
        )
        output, caught = self.render_with_warnings(template)
        extra_cell_warnings = [item for item in caught if "more 'table_cell' components" in item]
        self.assertEqual(len(extra_cell_warnings), 1)
        self.assertIn("<td>extra-1</td>", output)
        self.assertIn("<td>extra-2</td>", output)

    def test_cell_colspan_consumes_multiple_columns(self):
        template = (
            '{% ui "table" aria_label="Users" %}'
            '{% ui "table_header" %}'
            '{% ui "table_column" %}Name{% endui %}'
            '{% ui "table_column" %}Email{% endui %}'
            '{% ui "table_column" align="end" %}Total{% endui %}'
            "{% endui %}"
            '{% ui "table_body" %}'
            '{% ui "table_row" %}'
            '{% ui "table_cell" col_span=2 %}Jane{% endui %}'
            '{% ui "table_cell" %}10{% endui %}'
            "{% endui %}"
            "{% endui %}"
            "{% endui %}"
        )
        output, caught = self.render_with_warnings(template)
        self.assertEqual(caught, [])
        self.assertIn('<td colspan="2" role="rowheader">Jane</td>', output)
        # The cell after a colspan=2 cell inherits metadata from the third column
        self.assertIn('<td data-align="end">10</td>', output)

    def test_nested_table_in_cell_uses_its_own_state(self):
        inner_table = (
            '{% ui "table" aria_label="Inner" %}'
            '{% ui "table_header" %}{% ui "table_column" align="end" %}Inner col{% endui %}{% endui %}'
            '{% ui "table_body" %}'
            '{% ui "table_row" %}{% ui "table_cell" %}inner-cell{% endui %}{% endui %}'
            "{% endui %}"
            "{% endui %}"
        )
        template = (
            '{% ui "table" aria_label="Outer" %}'
            '{% ui "table_header" %}'
            '{% ui "table_column" %}Name{% endui %}'
            '{% ui "table_column" %}Details{% endui %}'
            "{% endui %}"
            '{% ui "table_body" %}'
            '{% ui "table_row" %}'
            '{% ui "table_cell" %}Jane{% endui %}'
            '{% ui "table_cell" %}' + inner_table + "{% endui %}"
            "{% endui %}"
            "{% endui %}"
            "{% endui %}"
        )
        output, caught = self.render_with_warnings(template)
        self.assertEqual(caught, [])
        # Inner cell is the inner table's first column: row header with alignment from inner column
        self.assertIn('<td data-align="end" role="rowheader">inner-cell</td>', output)
        # The outer table's empty state/row counting is unaffected
        self.assertNotIn("Table_noResults", output)

    def test_colspan_on_column_renders_spans_multiple(self):
        template = make_sortable_table_template(columns='{% ui "table_column" col_span=2 %}Name{% endui %}')
        output, caught = self.render_with_warnings(template)
        self.assertEqual(caught, [])
        self.assertIn('<th data-spans-multiple="true" colspan="2" scope="col">', output)

    def test_compiled_template_is_reusable_across_renders(self):
        # Template nodes are shared between renders (and threads); the components must not carry
        # per-render state on the node instances. Render one compiled Template repeatedly and
        # check render-dependent output (empty state, sort links) is correct every time.
        outputs = []
        with self.setup_render_context():
            template_obj = Template(
                "{% load alliance_platform.ui %}"
                + make_sortable_table_template('sort_order=request|table_sort_order sort_mode="single"')
                + '{% ui "table" aria_label="Empty" %}'
                '{% ui "table_header" %}{% ui "table_column" %}Name{% endui %}{% endui %}'
                '{% ui "table_body" %}{% endui %}'
                "{% endui %}"
            )
            for url in ("/users/", "/users/?ordering=name", "/users/"):
                context_obj = Context({"request": self.request_factory.get(url)})
                context_obj.template = template_obj
                outputs.append(template_obj.render(context_obj))
        first_render, second_render, third_render = outputs
        self.assertIn('href="/users/?ordering=name"', first_render)
        self.assertIn('href="/users/?ordering=-name"', second_render)
        # Repeating the first request must reproduce the first output exactly (no leaked state)
        self.assertEqual(third_render, first_render)
        for output in outputs:
            self.assertIn("<em>No results</em>", output)

    def test_resources_are_registered(self):
        with self.setup_render_context() as asset_context:
            self.render_ui_template(BASIC_TABLE_TEMPLATE)
            resource_paths = [str(resource.path) for resource in asset_context.get_resources_for_bundling()]
        self.assertTrue(
            any(
                path.endswith("@alliancesoftware/ui/components/table/Table.css.ts") for path in resource_paths
            )
        )
        self.assertTrue(any(path.endswith("@alliancesoftware/icons/Icon.css.ts") for path in resource_paths))
