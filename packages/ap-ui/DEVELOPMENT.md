# ap-ui Development Notes

This file contains maintainer-focused workflow notes for developing `alliance-platform-py/packages/ap-ui`.

## Adding a new HTML dispatcher component

1. Add a renderer class under:
   - `alliance_platform/ui/templatetags/alliance_platform/html_components/components/`
2. Register it in:
   - `alliance_platform/ui/templatetags/alliance_platform/html_components/registry.py`
3. Add parity cases in:
   - `scripts/parity_cases/`
   - include `class_prefixes` in each parity case module so fixture generation can keep relevant VE class tokens without hardcoding full class maps.
4. Regenerate fixtures:
   - `just sync-html-ui-parity-fixtures`
5. Add or extend parity tests in:
   - `tests/`

## Input components (`text_input`, `number_input`, `text_area`)

The input renderers live in
`alliance_platform/ui/templatetags/alliance_platform/html_components/components/input.py` and share the
`UILabeledInputRendererMixin` / `UITextInputBaseRenderer` rendering path, mirroring how the React
components all render through `LabeledInput` + `TextInputBase`. Future input-like components (search
input, select, date picker) should reuse the same base classes.

Generated element ids use a deterministic `apui-<component>-<n>` scheme where the counter is unique
within a template render (stored in `context.render_context`). The fixture generator remaps the
react-aria generated ids to the same scheme so fixtures stay deterministic.

Props that are not consumed by the renderer only reach the control element through an explicit
allowlist (`control_pass_through_props`, plus `data-*`/`aria-*` attributes); anything else warns
and is dropped. Event handler props (`on*`) are always rejected — a string value would otherwise
render as a live inline event handler, which React never does.

### Rich content props (`RenderableContent`)

`RenderableContent` (in `alliance_platform.frontend.renderable_content`) is the supported way to
pass rich (HTML) content into static HTML renderers — `{% form_input %}` produces it for
`help_text`, and the same value works for both React `{% component %}` widgets and static
`{% ui %}` widgets. Renderers declare which props accept it via `rich_content_props` (currently
only `description` on inputs; `errorMessage` and labels are deliberately plain escaped text) and
must render it through `html_components/content.py`'s `render_content()` helper — never `str()`
or `mark_safe()` on the raw value. `render_content()` escapes text and attribute values, refuses
event handler attributes (`on*`) with a warning, and statically renders legacy plain-HTML
`ComponentNode` values during migration (imported React components warn and render nothing — it
never calls `ComponentNode.render()`, which would enter the React/bundler path).

### Bulk props (`props=` kwarg)

Like the React `{% component %}` tag, `{% ui %}` accepts a reserved `props` kwarg holding a dict of
props to apply in bulk. This exists for dynamic attribute dicts that cannot be enumerated in the
template, e.g. Django form widget templates:

```django
{% load alliance_platform.ui %}

{% ui "text_input" props=widget.attrs|merge_props:extra_widget_props type=widget.type name=widget.name defaultValue=widget.value %}{% endui %}
```

Bulk prop keys are adapted to the component prop contract automatically: HTML attribute names are
converted to their React equivalents (`maxlength` → `maxLength`, `class` → `className` — no
`|html_attr_to_jsx` filter needed), and boolean state attributes to their react-aria props
(`disabled` → `isDisabled`, `required` → `isRequired`, `readonly` → `isReadOnly`) so widget attrs
do not trigger the inline-kwarg alias warnings. Matching `{% component %}`, bulk props take
precedence over individually passed props, except `className` values which are merged. The merged
props still pass through the same unsupported-prop filtering as inline kwargs, so non-scalar
values warn and are dropped unless the prop accepts rich content (see above).
`merge_props` is registered in both the `react` and `alliance_platform.ui` template tag libraries.

### Deliberate static-render differences from React

These are normalized away by the fixture generator (`generateHtmlUiParityFixtures.mjs`) and/or are
intentional extensions, so they will not show up as parity failures:

- **Label association**: react-aria wires labels with both `<label for>` and an
  `aria-labelledby`/label `id` pair. The static renderer relies on the native `<label for>`
  association only.
- **`aria-describedby`**: react-aria reserves description/error slot ids during SSR even when
  neither renders. The static renderer only generates ids for help text that actually renders.
  Caller supplied `aria-describedby` values are preserved with generated ids prepended (matching
  react-aria's ordering).
- **`rows`/`cols` on `text_area`**: the React component drops these in favour of runtime
  autosizing; the static renderer passes them through as normal textarea attributes since there is
  no autosize behaviour. They are covered by unit tests, not parity fixtures.
- **`minValue`/`maxValue`/`step` on `number_input`**: accepted but produce no DOM output, matching
  React (clamping/stepping is client-side behaviour). Step buttons are rendered statically with no
  increment/decrement behaviour and are not disabled at min/max boundaries.
- **Number formatting**: the static renderer renders numeric values with `str()` (integral floats
  collapse to integers). Locale-aware formatting (`formatOptions`, thousand separators, `locale`)
  is not supported; `formatOptions` and `locale` warn and are ignored. Keep fixture values below
  1000 so the en-US formatted React output matches.
- **Validation icons / step button chevrons**: rendered as static SVG markup copied from
  `@alliancesoftware/icons` (`AlertCircleOutlined`, `CheckOutlined`, `ChevronUpOutlined`,
  `ChevronDownOutlined`). If those icons change upstream the fixture drift check will catch it.
- **`font_*` classes**: excluded from fixture `class_prefixes`. In production the composed font
  classes come through automatically because the real vanilla-extract mappings store the full
  composite class strings; the test style mocks return single tokens.
- **Boolean attributes**: React SSR renders `disabled=""`/`readonly=""`; the Python renderer emits
  bare `disabled`/`readonly`. The parity normalizer treats these as equivalent (they are in HTML).

## Table components (`table`, `table_header`, `table_body`, `table_column`, `table_row`, `table_cell`)

The static table renderers live in
`alliance_platform/ui/templatetags/alliance_platform/html_components/components/table.py` and
mirror `@alliancesoftware/ui`'s `Table.tsx` for the read-only CRUD list case. Sorting is rendered
as plain `<a href>` links that update a backend query parameter, mirroring `ColumnHeaderLink.tsx` /
`useTableSorter.ts` (direction cycle: unsorted → ascending → descending → off).

### Cross-component render state

The components coordinate through a `TableRenderState` stack stored in `context.render_context`
(`_TABLE_STATE_KEY`), pushed by `table` around its children via the
`render_children_for_component()` hook on the base renderer (which, unlike `render_children()`,
receives the resolved props). `render_context` is shared across `{% include %}` — including
`only` — within one template render, and a stack supports tables nested inside cells:

1. `table` builds the state from its props (sort order/mode/behaviour, query param, empty state)
   and pushes it while children render.
2. Each `table_column` appends its `TableColumnState` (key, align, row-header flag, sort state)
   in render order.
3. Each `table_row` resets `current_row_cell_index` to 0 around its children and increments
   `row_count` (so `table_body` can render the default empty state only when no rows rendered).
4. Each `table_cell` consumes the column state at the current index to inherit alignment and
   row-header status, advancing the index by the cell's `colSpan` so later cells stay aligned.

Components rendered outside their expected parent warn and render fallback markup rather than
failing (CRUD pages should not 500 because of a conditional cell); rows with more cells than
registered columns warn once per table.

### Intentionally unsupported React Table features

Row selection (`selectionMode`, `selectedKeys`, checkboxes, `isSelected`), client-side sorting
(`onSortChange`, `sortFunction`, `defaultSortOrder`), collection render props (`items`,
`columns`), `columnHeaderElementType`, nested/grouped columns, and all keyboard grid/focus
behaviour (including `mode="edit"` semantics — only the `data-mode` attribute is rendered). These
warn and are dropped so templates never render interactive-looking state with no behaviour behind
it.

### Native semantics vs the React ARIA grid

The React table is an interactive ARIA grid (grid roles, tab indexes, focus management). The
static renderer intentionally keeps native table semantics instead: no grid roles or tab indexes,
`scope="col"` and `aria-sort` on `<th>` header cells (direction when sorted, `"none"` when
sortable-but-unsorted), and row-header cells as `<td role="rowheader">` rather than
`<th scope="row">` so browser default `<th>` styling cannot diverge visually from React. The
fixture generator's `normalizeTableComponentHtml()` reconciles these documented differences; see
the comments there for the full list (grid roles, `data-collection`/`data-key` bookkeeping,
absolute vs relative sort hrefs, CSS var hashes in `style`).

The Table stylesheet is deliberately "class-free" for consumers: all structural styling hangs off
the `tableWrapper` class on the root element, with rows/cells targeted through element and
data-attribute selectors (`tbody tr`, `td`, `[data-align]`, `[data-spans-multiple]`,
`[data-has-header]`/`[data-has-footer]`). Only the root and the header chrome
(`headerCellWrapper`, `headerCellContent`, `sortWrapper`, sort icon classes, `noResults`) carry
classes, so user `className` values render alone on `<th>`/`<tr>`/`<td>` and the data attributes
are load-bearing — don't drop them as informational.

Sortable-column fixtures record the URL the React SSR render happened at in `meta.current_url`
(the generator exposes it via `globalSsrContext.currentUrl`, which `ColumnHeaderLink` reads during
SSR); the Python parity test builds a `RequestFactory` request for the same URL. Regenerate the
table fixtures with `just sync-html-ui-parity-fixtures ../alliance-platform-js table`.

## Menubar components (`menubar`, `menubar_item`, `menubar_submenu`, `menubar_section`)

The static menubar renderers live in
`alliance_platform/ui/templatetags/alliance_platform/html_components/components/menubar.py` and
mirror `@alliancesoftware/ui`'s `Menubar.tsx` for server-rendered navigation menus. Interactivity
comes from a standalone runtime module in the JS repo —
`@alliancesoftware/ui/components/menu-bar/Menubar.attach.ts` — attached through
`attach_module_script()` exactly like the button group's `SmartOrientation.attach.ts` (per-root
`data-djid` + module script; the runtime is idempotent and holds cleanup state in a `WeakMap`).
The runtime never imports CSS mappings: the Python renderer exposes the state class names it must
toggle through `data-open-class` / `data-focused-class` / `data-popover-open-class` on the root.

### Cross-component render state

The components coordinate through a `MenubarRenderState` stack in the document-level base layer
of `context.render_context` (`_MENUBAR_STATE_KEY`), with one `MenubarRenderFrame` per menu grouping
(root menu, submenu popup, section). Django gives every included template a fresh top render-context
layer, so component state and generated-ID counters must use `get_document_render_context()` to
survive `{% include %}` (including `only`). `menubar`, `menubar_submenu` and `menubar_section`
render their children from inside `render_component()` (returning `""` from
`render_children_for_component()`) so the frame wraps the children and the child counts are
available when deciding what to render:

1. Items increment the current frame's `item_count` only when they actually render — a denied
   `url_with_perm` href raises `OmitComponentFromRendering`, which the static renderer base now
   catches (the whole component renders nothing, silently, matching the React tags).
2. A submenu/section whose child frame has `item_count == 0` renders nothing by default
   (`hide_when_empty=False` opts out); a menubar with an empty root frame renders nothing unless
   `render_when_empty=True`.
3. `is_current` items set `contains_current` on their frame, which propagates `data-current` to
   ancestor submenu triggers and sections.
4. The first enabled root-level item claims `tabindex="0"` (or the `default_focused_key` item);
   everything else renders `tabindex="-1"` and the runtime moves the roving tab stop.
5. Leading static icons receive the `itemIcon` slot class, adjacent plain text is wrapped like the
   React `Text` component, and `hasLeadingIcon` class/data state is propagated to the containing
   root or submenu `<ul>` for consistent indentation. The item wrapper and content span emit the
   shared `data-apui-menu-item-content-wrapper` and `data-apui-menu-item-content` markers used by
   `Menubar.css.ts` to space leading icons.

Section separators are decided *after* pruning (`is_first` = parent frame count at render time),
so a pruned first section never leaves a leading separator behind.

### Intentionally unsupported React Menubar features

`onAction`/`onSelectionChange`/`onExpandedChange` callbacks, selection (`selectionMode` etc.),
dynamic collections (`items`/`childItems`), `itemElementType`, controlled `expandedKeys`, and
width overflow into a "More" submenu (`overflowLabel`/`overflowTextLabel`). These warn and are
dropped. `default_expanded_keys` *is* supported statically (submenus render open; the runtime
initialises from `data-open="true"`). Known first-pass runtime gaps: flyout positioning is simple
DOM-relative placement without viewport-aware flipping, and typeahead searches within the current
menu only.

### Deliberate static-render differences from React

Reconciled by `normalizeMenubarComponentHtml()` in the fixture generator (React side) and
`strip_static_menubar_extensions()` in `tests/test_html_ui_menubar_parity.py` (static side):

- **Stable submenu popups**: React renders open flyouts in a portal and closed menus not at all;
  the static renderer always renders a `Popover.css`-styled wrapper
  (`data-apui-menu-popover`) in place. Inline layout uses the same wrapper with the CSS
  `display: contents` contract, so `MenubarController.setLayout()` can switch that DOM tree to a
  positioned flyout. Closed wrappers are stripped for parity; visible inline wrappers are
  unwrapped so the `defaultExpandedKeys` fixtures still compare their submenu content.
- **Submenu trigger element**: React defaults to `<div>` for triggers without `href`; the static
  renderer uses `<button type="button">` so menus work without React synthetic events. Fixture
  cases pass `elementType="button"` on the React side; the `type="button"` attribute is stripped
  for comparison.
- **`aria-controls`/popup ids, roving `tabindex`, `data-open="false"`, `data-current`,
  `data-key`**: static extensions (or explicit values React leaves implicit); stripped and unit
  tested instead.
- **`hasLeadingIcon` during SSR**: React initially emits this state optimistically before
  `useHasChild` inspects the DOM. The static renderer computes the actual value from rendered
  leading icon slots, so the React SSR value is stripped for fixture parity and focused unit tests
  cover the shared class/data contract.
- **Overflow measurement placeholders**: React SSRs an offscreen dummy "more items" node for
  measuring; removed from fixtures.
- **react-aria ids**: unlike the input components, `aria-labelledby` references (section heading
  ids) must survive normalization — the generator drops only unreferenced element ids, then remaps
  survivors to the static `apui-menubar-<n>` scheme.

Regenerate with `just sync-html-ui-parity-fixtures ../alliance-platform-js menubar`. The runtime
tests live in the JS repo: `packages/ui/components/menu-bar/tests/Menubar.attach.test.ts`
(`npx vitest --run components/menu-bar/tests/Menubar.attach.test.ts` from `packages/ui`).

### template-django primary nav migration

`nav_primary.html` can migrate from the React `PrimaryNav` to the static path following the
example in `docs/templatetags.rst` (the `Users` submenu's `component:omit_if_empty=True` becomes
automatic empty-pruning, logout stays a POST `<button form="logout-form">`). The standalone
runtime's `attach(root)` returns a controller with `setLayout(layout)`, so one rendered menubar can
switch between horizontal, vertical and inline layout without duplicating menu markup. Submenus
always keep the same popover/inner/menu subtree, including when the initial layout is inline, so a
later vertical or horizontal layout can position them as flyouts. A responsive mobile drawer still
requires its own static drawer/disclosure behaviour; layout switching alone does not supply that
container interaction.

## HTML parity fixture workflow

The fixture generator depends on `@alliancesoftware/ui` TypeScript sources, so it must run through the `alliance-platform-js` runtime context.

From `alliance-platform-py`:

```bash
just sync-html-ui-parity-fixtures
```

Use a non-default JS checkout path:

```bash
just sync-html-ui-parity-fixtures /path/to/alliance-platform-js
```

Generate a single component fixture:

```bash
just sync-html-ui-parity-fixtures ../alliance-platform-js button_group
```

Check fixture drift (for CI or pre-commit checks):

```bash
just check-html-ui-parity-fixtures /path/to/alliance-platform-js
```

## CI fixture drift check

The cross-repo fixture drift workflow is defined in:

- `.github/workflows/ap-ui-fixture-drift.yml`

It checks out both `alliance-platform-py` and `alliance-platform-js`, regenerates the fixtures, and fails if fixture files changed.

### Testing against an unmerged alliance-platform-js branch

By default the workflow regenerates fixtures against alliance-platform-js `main`. When a change
here depends on an unmerged alliance-platform-js branch (e.g. fixtures were regenerated against a
JS fix), pin the ref in:

- `.github/alliance-platform-js-ref` — single line containing the branch/tag/SHA to check out.

Commit the pin with your PR so CI tests the pair together, and reset the file to `main` once the
JS branch merges (until then, `main` runs of the drift check will use the pinned ref, so don't
leave stale pins behind). Manual runs can override the ref with the `js_ref` input on
`workflow_dispatch` without touching the file.

For private `alliance-platform-js` access in GitHub Actions, configure:

- `ALLIANCE_PLATFORM_JS_DEPLOY_KEY`: private SSH key matching a read-only deploy key on `AllianceSoftware/alliance-platform-js`.
