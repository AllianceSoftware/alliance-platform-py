export const component = 'table';
export const class_prefixes = ['Table', 'Icon'];

// Shared helpers to keep the case definitions readable. The React Table renders sortable header
// links through ColumnHeaderLink (the same component the React-backed Django tags use); the
// static renderer always renders sortable headers as links when a URL can be resolved.
function buildTable({ React, components }, tableProps, columns, rows) {
    const { Table, TableHeader, TableBody, Column, Row, Cell } = components;
    return React.createElement(
        Table,
        tableProps,
        React.createElement(
            TableHeader,
            null,
            columns.map(([key, props, label]) =>
                React.createElement(Column, { key, ...props }, label)
            )
        ),
        React.createElement(
            TableBody,
            null,
            rows.map((cells, rowIndex) =>
                React.createElement(
                    Row,
                    { key: `row-${rowIndex}` },
                    cells.map((cell, cellIndex) => {
                        const [props, content] = Array.isArray(cell) ? cell : [null, cell];
                        return React.createElement(Cell, { key: `cell-${cellIndex}`, ...props }, content);
                    })
                )
            )
        )
    );
}

function sortableTableProps({ React, components }, extraProps = {}) {
    const { ColumnHeaderLink } = components;
    return {
        'aria-label': 'User list',
        columnHeaderElementType: React.createElement(ColumnHeaderLink, { sortQueryParam: 'ordering' }),
        ...extraProps,
    };
}

export const cases = [
    {
        name: 'basic',
        template:
            '{% ui "table" aria_label="User list" %}' +
            '{% ui "table_header" %}' +
            '{% ui "table_column" key="name" %}Name{% endui %}' +
            '{% ui "table_column" key="email" %}Email{% endui %}' +
            '{% endui %}' +
            '{% ui "table_body" %}' +
            '{% ui "table_row" %}{% ui "table_cell" %}Jane{% endui %}{% ui "table_cell" %}jane@example.com{% endui %}{% endui %}' +
            '{% ui "table_row" %}{% ui "table_cell" %}John{% endui %}{% ui "table_cell" %}john@example.com{% endui %}{% endui %}' +
            '{% endui %}' +
            '{% endui %}',
        buildElement(runtime) {
            return buildTable(
                runtime,
                { 'aria-label': 'User list' },
                [
                    ['name', null, 'Name'],
                    ['email', null, 'Email'],
                ],
                [
                    ['Jane', 'jane@example.com'],
                    ['John', 'john@example.com'],
                ]
            );
        },
        meta: {},
    },
    {
        name: 'class_style_merging',
        template:
            '{% ui "table" aria_label="User list" class="custom-table" style="max-width: 400px" %}' +
            '{% ui "table_header" %}' +
            '{% ui "table_column" key="name" class="custom-column" %}Name{% endui %}' +
            '{% endui %}' +
            '{% ui "table_body" class="custom-body" %}' +
            '{% ui "table_row" class="custom-row" %}' +
            '{% ui "table_cell" class="custom-cell" style="font-style: italic" %}Jane{% endui %}' +
            '{% endui %}' +
            '{% endui %}' +
            '{% endui %}',
        buildElement(runtime) {
            const { React, components } = runtime;
            const { Table, TableHeader, TableBody, Column, Row, Cell } = components;
            return React.createElement(
                Table,
                { 'aria-label': 'User list', className: 'custom-table', style: { maxWidth: '400px' } },
                React.createElement(
                    TableHeader,
                    null,
                    React.createElement(Column, { key: 'name', className: 'custom-column' }, 'Name')
                ),
                React.createElement(
                    TableBody,
                    { className: 'custom-body' },
                    React.createElement(
                        Row,
                        { key: 'row-0', className: 'custom-row' },
                        React.createElement(
                            Cell,
                            { className: 'custom-cell', style: { fontStyle: 'italic' } },
                            'Jane'
                        )
                    )
                )
            );
        },
        meta: {},
    },
    {
        name: 'column_alignment',
        template:
            '{% ui "table" aria_label="User list" %}' +
            '{% ui "table_header" %}' +
            '{% ui "table_column" key="name" %}Name{% endui %}' +
            '{% ui "table_column" key="active" align="center" %}Active{% endui %}' +
            '{% ui "table_column" key="total" align="end" %}Total{% endui %}' +
            '{% ui "table_column" key="notes" align="start" %}Notes{% endui %}' +
            '{% endui %}' +
            '{% ui "table_body" %}' +
            '{% ui "table_row" %}' +
            '{% ui "table_cell" %}Jane{% endui %}' +
            '{% ui "table_cell" %}Yes{% endui %}' +
            '{% ui "table_cell" %}10{% endui %}' +
            '{% ui "table_cell" %}-{% endui %}' +
            '{% endui %}' +
            '{% endui %}' +
            '{% endui %}',
        buildElement(runtime) {
            return buildTable(
                runtime,
                { 'aria-label': 'User list' },
                [
                    ['name', null, 'Name'],
                    ['active', { align: 'center' }, 'Active'],
                    ['total', { align: 'end' }, 'Total'],
                    ['notes', { align: 'start' }, 'Notes'],
                ],
                [['Jane', 'Yes', '10', '-']]
            );
        },
        meta: {},
    },
    {
        name: 'column_width',
        template:
            '{% ui "table" aria_label="User list" %}' +
            '{% ui "table_header" %}' +
            '{% ui "table_column" key="name" width=96 %}Name{% endui %}' +
            '{% endui %}' +
            '{% ui "table_body" %}' +
            '{% ui "table_row" %}{% ui "table_cell" %}Jane{% endui %}{% endui %}' +
            '{% endui %}' +
            '{% endui %}',
        buildElement(runtime) {
            return buildTable(
                runtime,
                { 'aria-label': 'User list' },
                [['name', { width: 96 }, 'Name']],
                [['Jane']]
            );
        },
        meta: {},
    },
    {
        name: 'sortable_unsorted',
        template:
            '{% ui "table" aria_label="User list" sort_order=request|table_sort_order %}' +
            '{% ui "table_header" %}' +
            '{% ui "table_column" key="name" allows_sorting=True %}Name{% endui %}' +
            '{% ui "table_column" key="email" %}Email{% endui %}' +
            '{% endui %}' +
            '{% ui "table_body" %}' +
            '{% ui "table_row" %}{% ui "table_cell" %}Jane{% endui %}{% ui "table_cell" %}jane@example.com{% endui %}{% endui %}' +
            '{% endui %}' +
            '{% endui %}',
        buildElement(runtime) {
            return buildTable(
                runtime,
                sortableTableProps(runtime, { sortOrder: [] }),
                [
                    ['name', { allowsSorting: true }, 'Name'],
                    ['email', null, 'Email'],
                ],
                [['Jane', 'jane@example.com']]
            );
        },
        meta: { current_url: '/users/' },
    },
    {
        name: 'sortable_ascending',
        template:
            '{% ui "table" aria_label="User list" sort_order=request|table_sort_order %}' +
            '{% ui "table_header" %}' +
            '{% ui "table_column" key="name" allows_sorting=True %}Name{% endui %}' +
            '{% endui %}' +
            '{% ui "table_body" %}' +
            '{% ui "table_row" %}{% ui "table_cell" %}Jane{% endui %}{% endui %}' +
            '{% endui %}' +
            '{% endui %}',
        buildElement(runtime) {
            return buildTable(
                runtime,
                sortableTableProps(runtime, {
                    sortOrder: [{ column: 'name', direction: 'ascending' }],
                }),
                [['name', { allowsSorting: true }, 'Name']],
                [['Jane']]
            );
        },
        meta: { current_url: '/users/?ordering=name' },
    },
    {
        name: 'sortable_descending',
        template:
            '{% ui "table" aria_label="User list" sort_order=request|table_sort_order %}' +
            '{% ui "table_header" %}' +
            '{% ui "table_column" key="name" allows_sorting=True %}Name{% endui %}' +
            '{% endui %}' +
            '{% ui "table_body" %}' +
            '{% ui "table_row" %}{% ui "table_cell" %}Jane{% endui %}{% endui %}' +
            '{% endui %}' +
            '{% endui %}',
        buildElement(runtime) {
            return buildTable(
                runtime,
                sortableTableProps(runtime, {
                    sortOrder: [{ column: 'name', direction: 'descending' }],
                }),
                [['name', { allowsSorting: true }, 'Name']],
                [['Jane']]
            );
        },
        meta: { current_url: '/users/?ordering=-name' },
    },
    {
        name: 'multiple_sort_with_position',
        template:
            '{% ui "table" aria_label="User list" sort_order=request|table_sort_order sort_mode="multiple" sort_behavior="toggle" %}' +
            '{% ui "table_header" %}' +
            '{% ui "table_column" key="name" allows_sorting=True %}Name{% endui %}' +
            '{% ui "table_column" key="created" allows_sorting=True %}Created{% endui %}' +
            '{% ui "table_column" key="email" allows_sorting=True %}Email{% endui %}' +
            '{% endui %}' +
            '{% ui "table_body" %}' +
            '{% ui "table_row" %}{% ui "table_cell" %}Jane{% endui %}{% ui "table_cell" %}2026-01-01{% endui %}{% ui "table_cell" %}jane@example.com{% endui %}{% endui %}' +
            '{% endui %}' +
            '{% endui %}',
        buildElement(runtime) {
            return buildTable(
                runtime,
                sortableTableProps(runtime, {
                    sortOrder: [
                        { column: 'name', direction: 'ascending' },
                        { column: 'created', direction: 'descending' },
                    ],
                    sortMode: 'multiple',
                    sortBehavior: 'toggle',
                }),
                [
                    ['name', { allowsSorting: true }, 'Name'],
                    ['created', { allowsSorting: true }, 'Created'],
                    ['email', { allowsSorting: true }, 'Email'],
                ],
                [['Jane', '2026-01-01', 'jane@example.com']]
            );
        },
        meta: { current_url: '/users/?page=2&ordering=name,-created' },
    },
    {
        name: 'hidden_header',
        template:
            '{% ui "table" aria_label="User list" %}' +
            '{% ui "table_header" %}' +
            '{% ui "table_column" key="name" %}Name{% endui %}' +
            '{% ui "table_column" key="actions" hide_header=True %}Actions{% endui %}' +
            '{% endui %}' +
            '{% ui "table_body" %}' +
            '{% ui "table_row" %}{% ui "table_cell" %}Jane{% endui %}{% ui "table_cell" %}Edit{% endui %}{% endui %}' +
            '{% endui %}' +
            '{% endui %}',
        buildElement(runtime) {
            return buildTable(
                runtime,
                { 'aria-label': 'User list' },
                [
                    ['name', null, 'Name'],
                    ['actions', { hideHeader: true }, 'Actions'],
                ],
                [['Jane', 'Edit']]
            );
        },
        meta: {},
    },
    {
        name: 'empty_body_default_empty_state',
        template:
            '{% ui "table" aria_label="User list" %}' +
            '{% ui "table_header" %}' +
            '{% ui "table_column" key="name" %}Name{% endui %}' +
            '{% ui "table_column" key="email" %}Email{% endui %}' +
            '{% endui %}' +
            '{% ui "table_body" %}{% endui %}' +
            '{% endui %}',
        buildElement(runtime) {
            return buildTable(
                runtime,
                { 'aria-label': 'User list' },
                [
                    ['name', null, 'Name'],
                    ['email', null, 'Email'],
                ],
                []
            );
        },
        meta: {},
    },
    {
        name: 'empty_body_empty_state_disabled',
        template:
            '{% ui "table" aria_label="User list" render_empty_state=None %}' +
            '{% ui "table_header" %}' +
            '{% ui "table_column" key="name" %}Name{% endui %}' +
            '{% endui %}' +
            '{% ui "table_body" %}{% endui %}' +
            '{% endui %}',
        buildElement(runtime) {
            return buildTable(
                runtime,
                { 'aria-label': 'User list', renderEmptyState: null },
                [['name', null, 'Name']],
                []
            );
        },
        meta: {},
    },
    {
        name: 'header_footer_content',
        template:
            '{% ui "table" aria_label="User list" header="Showing 1 user" footer="Page 1 of 1" %}' +
            '{% ui "table_header" %}' +
            '{% ui "table_column" key="name" %}Name{% endui %}' +
            '{% endui %}' +
            '{% ui "table_body" %}' +
            '{% ui "table_row" %}{% ui "table_cell" %}Jane{% endui %}{% endui %}' +
            '{% endui %}' +
            '{% endui %}',
        buildElement(runtime) {
            return buildTable(
                runtime,
                { 'aria-label': 'User list', header: 'Showing 1 user', footer: 'Page 1 of 1' },
                [['name', null, 'Name']],
                [['Jane']]
            );
        },
        meta: {},
    },
];
