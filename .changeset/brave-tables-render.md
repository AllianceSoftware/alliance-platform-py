---
"alliance-platform-ui": patch
---

Add static HTML dispatcher renderers for the Alliance UI table components, available through `{% ui "table" %}`, `{% ui "table_header" %}`, `{% ui "table_body" %}`, `{% ui "table_column" %}`, `{% ui "table_row" %}` and `{% ui "table_cell" %}`. These mirror the `@alliancesoftware/ui` `Table` markup (visual classes, state data attributes, sort icons, empty state, header/footer) without any JavaScript runtime, and support backend-driven sorting through plain links that update a query parameter (matching the `useTableSorter`/`ColumnHeaderLink` toggle semantics, including `sort_mode`/`sort_behavior`). Row selection, client-side sorting and the interactive ARIA grid behaviour are intentionally unsupported; the React-backed `{% Table %}` tags remain for those cases.
