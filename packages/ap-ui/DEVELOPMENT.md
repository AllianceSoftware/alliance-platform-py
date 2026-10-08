# ap-ui Development Notes

This file contains maintainer-focused workflow notes for developing `alliance-platform-py/packages/ap-ui`.

## Adding a new HTML dispatcher component

Built-in components use the same renderer contract as project components. `docs/static_components.rst`
("Writing a static component") documents it. Its worked example is a real project component:
`test_alliance_platform_ui/static_components.py`, registered by `test_alliance_platform_ui/apps.py`
and tested in `tests/test_static_component_example.py`.

1. Add a renderer class under `alliance_platform/ui/html_components/components/`. Set `name` to the
   snake_case component name and export the class from `components/__init__.py`. The root
   `data-apui` marker and generated id prefixes come from `apui_name`, which defaults to the
   hyphenated `name`.
2. Register it with `register_component("<name>", Renderer)` at the end of
   `alliance_platform/ui/html_components/registry.py`. `register_component` rejects names that are
   not snake_case, names that differ from the renderer's `name`, and a second renderer for a taken
   name unless `replace=True`. Projects call it from `AppConfig.ready()` instead.
3. Add one parity case module, `scripts/parity_cases/<name>.mjs`, exporting the cases, the React
   components they build with (`loadComponents`), the React-side normalisation (`normalize`) and
   the stylesheets the renderer resolves (`stylesheets`). "HTML parity fixture workflow" below
   describes each export. A renderer that resolves a stylesheet no module lists fails its tests.
4. Regenerate with `just sync-html-ui-parity-fixtures ../alliance-platform-js <name>`, which writes
   `tests/fixtures/ui_html_<name>_parity.json` and refreshes `tests/fixtures/css-mappings.json`.
5. Add `tests/test_html_ui_<name>_parity.py`: an `HtmlUIParityTestCase` (`tests/parity/base.py`,
   built on the shipped `alliance_platform.ui.test_utils.StaticComponentTestCase`) that sets
   `fixture_component` and calls `assert_parity_case()` for each fixture case. Strip static-only
   extensions by extending `normalize_static_html()`, and `normalize_expected_html()` when the
   fixture markup needs the same treatment, then list each difference under the component's
   "Deliberate static-render differences from React" in this file. Unit tests for behaviour the
   fixtures cannot show use the same base, which renders with the real class mappings.

## Diagnostics

Renderers report template mistakes with `self.report(message, kind=...)`, or with `report()` from
`html_components/diagnostics.py` where there is no renderer, never with Python's `warnings`
module. Use `kind="contract"` when the fix is in template source or the environment and
`kind="data"` when the value can legitimately vary per request; when in doubt, use `contract`.
Reports log through the `alliance_platform.ui` logger with the message text unchanged: the parity
fixtures' `expected_warnings` hold React's `console.warn` strings and the parity tests compare them
with the logged messages. Contract reports raise `StaticComponentContractError` when the
`STATIC_COMPONENT_STRICT` setting is on (default `DEBUG`); ap-ui's test settings turn it off. Tests
capture diagnostics with `HtmlUIParityTestCase.capture_diagnostics()`, which yields the logged
messages and allows an empty list, or with `assertLogs`. `docs/static_components.rst` documents the
behaviour for projects.

## Input components (`text_input`, `number_input`, `text_area`)

The input renderers live in
`alliance_platform/ui/html_components/components/input.py` and share the
`UILabeledInputRendererMixin` / `UITextInputBaseRenderer` rendering path, mirroring how the React
components all render through `LabeledInput` + `TextInputBase`. Future input-like components (search
input, select, date picker) should reuse the same base classes.

Generated element ids use a deterministic `apui-<apui_name>-<n>` scheme (for example
`apui-text-input-1`) where the counter is unique within a template render (stored in
`context.render_context`). The fixture normalisation (`remapReactAriaIds()` in
`scripts/parity_cases/_helpers.mjs`) remaps the react-aria generated ids to the same scheme so
fixtures stay deterministic.

Props that are not consumed by the renderer only reach the control element through an explicit
allowlist (`control_pass_through_props`, plus `data-*`/`aria-*` attributes); anything else is
reported as a contract diagnostic and dropped. Event handler props (`on*`) are always rejected — a
string value would otherwise render as a live inline event handler, which React never does.

### Rich content props (`RenderableContent`)

`RenderableContent` (in `alliance_platform.frontend.renderable_content`) is the supported way to
pass rich (HTML) content into static HTML renderers — `{% form_input %}` produces it for
`help_text`, and the same value works for both React `{% component %}` widgets and static
`{% ui %}` widgets. Renderers declare which props accept it via `rich_content_props` (currently
only `description` on inputs; `errorMessage` and labels are deliberately plain escaped text) and
must render it through `html_components/content.py`'s `render_content()` helper — never `str()`
or `mark_safe()` on the raw value. `render_content()` escapes text and attribute values; event
handler attributes (`on*`) and values it cannot render (anything other than strings,
`RenderableContent` and lists of them) are reported as contract diagnostics and dropped.

### Bulk props (`props=` kwarg)

Like the React `{% component %}` tag, `{% ui %}` accepts a reserved `props` kwarg holding a dict of
props to apply in bulk. This exists for dynamic attribute dicts that cannot be enumerated in the
template, e.g. Django form widget templates:

```django
{% load alliance_platform.ui %}

{% ui "text_input" props=widget.attrs|merge_props:extra_widget_props type=widget.type name=widget.name defaultValue=widget.value %}
```

Bulk prop keys are adapted to the component prop contract automatically: HTML attribute names are
converted to their React equivalents (`maxlength` → `maxLength`, `class` → `className` — no
`|html_attr_to_jsx` filter needed), and boolean state attributes to their react-aria props
(`disabled` → `isDisabled`, `required` → `isRequired`, `readonly` → `isReadOnly`) so widget attrs
do not trigger the deprecated-alias diagnostics. Matching `{% component %}`, bulk props take
precedence over individually passed props, except `className` values which are merged. The merged
props still pass through the same unsupported-prop filtering as inline kwargs, so non-scalar
values are reported and dropped unless the prop accepts rich content (see above).
`merge_props` is registered in both the `react` and `alliance_platform.ui` template tag libraries.

### Deliberate static-render differences from React

These are normalized away by the input case modules' `normalize()` (which share
`normalizeInputComponent()` in `scripts/parity_cases/_helpers.mjs`) or by the parity tests, and/or
are intentional extensions, so they will not show up as parity failures:

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
- **`number_input` runtime configuration**: `minValue`, `maxValue`, `step`, `locale` and
  `formatOptions` are serialized as `data-apui-number-input-*` attributes for the standalone
  `NumberInput.attach.ts` runtime. These static-only attributes and the per-root attach script are
  removed by the NumberInput parity test before comparison with React SSR.
- **Number formatting and submission**: the server fallback renders the unformatted numeric value
  with `str()` (integral floats collapse to integers). The attach runtime applies `Intl.NumberFormat`
  display formatting, parses supported locale/currency/unit/percent input, and keeps the hidden
  named input it creates synchronized for native form submission. It also implements step-button and
  arrow-key increments with min/max clamping and dynamic boundary state.
- **`number_input` field name**: React renders `name` on a hidden input after the root and leaves
  the visible input unnamed. The static renderer keeps `name` on the visible input and renders no
  hidden input, so the field submits what the user typed when the attach runtime never runs; the
  runtime creates the hidden input on the client. `normalize()` in
  `scripts/parity_cases/number_input.mjs` drops React's hidden input and the NumberInput parity
  test drops `name` from the static visible input before comparison.
- **Validation icons / step button chevrons**: rendered as static SVG markup copied from
  `@alliancesoftware/icons` (`AlertCircleOutlined`, `CheckOutlined`, `ChevronUpOutlined`,
  `ChevronDownOutlined`). Matching NumberInput's documented React contract, validation state still
  colours the input while step controls are visible but the validation icon is only rendered when
  `hideStepButtons=True`. If those icons change upstream the fixture drift check will catch it.
- **Inline icon resources**: icon SVG files stay in frontend resource discovery for production
  builds, but are excluded from collected-asset embedding because the renderer already emits their
  markup inline. This prevents detached icon images from appearing at the document asset insertion
  point.
- **`font_*` classes**: excluded from fixture `class_prefixes`. Many styles compose the shared
  typography classes; React and the static renderers get the same composite strings from the
  class mappings, so the fixtures leave them out to stay readable.
- **Boolean attributes**: React SSR renders `disabled=""`/`readonly=""`; the Python renderer emits
  bare `disabled`/`readonly`. The parity normalizer treats these as equivalent (they are in HTML).

### Static NumberInput attach runtime

`number_input` attaches
`@alliancesoftware/ui/components/number-input/NumberInput.attach.ts` to its
`data-apui="number-input"` container with the same per-root `data-djid` + module-script pattern used
by Menubar and SmartOrientation. The server renders the field `name` on the visible input and no
hidden input, so without the runtime (JavaScript disabled, the script failed, or an
`@alliancesoftware/ui` without `NumberInput.auto.ts`) the field submits the unformatted number the
user typed. On attach, when the visible input has a `name`, the runtime creates a hidden input with
that name (copying any `form` attribute and mirroring `disabled`), appends it to the container and
removes `name` from the visible input, so the visible input can show locale formatting while the
hidden input carries the numeric value. It synchronizes on `input`, `change`, and form `submit` (the
last also covers a script assigning the visible value without dispatching an input event), formats
on attach/blur, handles the rendered step buttons and arrow keys, and keeps cleanup state in a
`WeakMap` so repeated attachment does not duplicate listeners or hidden inputs. `disconnect()`
writes the numeric value back into the visible input, moves `name` back to it and removes the hidden
input, so a later native submit sends a plain number. The runtime tests live in the JS repo:
`packages/ui/components/number-input/tests/NumberInput.attach.test.ts`.

## Table components (`table`, `table_header`, `table_body`, `table_column`, `table_row`, `table_cell`)

The static table renderers live in
`alliance_platform/ui/html_components/components/table.py` and
mirror `@alliancesoftware/ui`'s `Table.tsx` for the read-only CRUD list case. Sorting is rendered
as plain `<a href>` links that update a backend query parameter, mirroring `ColumnHeaderLink.tsx` /
`useTableSorter.ts` (direction cycle: unsorted → ascending → descending → off).

### Cross-component render state

The components coordinate through a typed `TableRenderState` payload on the shared document
render-frame stack. The frame stack is shared across `{% include %}` — including `only` — within
one template render, and nearest-payload lookup supports tables nested inside cells:

1. `table` builds the state from its props (sort order/mode/behaviour, query param, empty state)
   and pushes it while children render.
2. Each `table_column` appends its `TableColumnState` (key, align, row-header flag, sort state)
   in render order.
3. Each `table_row` resets `current_row_cell_index` to 0 around its children and increments
   `row_count` (so `table_body` can render the default empty state only when no rows rendered).
4. Each `table_cell` consumes the column state at the current index to inherit alignment and
   row-header status, advancing the index by the cell's `colSpan` so later cells stay aligned.

Components rendered outside their expected parent report a contract diagnostic and render
nothing; rows with more cells than registered columns report a data diagnostic once per table.

### Intentionally unsupported React Table features

Row selection (`selectionMode`, `selectedKeys`, checkboxes, `isSelected`), client-side sorting
(`onSortChange`, `sortFunction`, `defaultSortOrder`), collection render props (`items`,
`columns`), `columnHeaderElementType`, nested/grouped columns, and all keyboard grid/focus
behaviour (including `mode="edit"` semantics — only the `data-mode` attribute is rendered). These
are reported and dropped so templates never render interactive-looking state with no behaviour
behind it.

### Native semantics vs the React ARIA grid

The React table is an interactive ARIA grid (grid roles, tab indexes, focus management). The
static renderer intentionally keeps native table semantics instead: no grid roles or tab indexes,
`scope="col"` and `aria-sort` on `<th>` header cells (direction when sorted, `"none"` when
sortable-but-unsorted), and row-header cells as `<td role="rowheader">` rather than
`<th scope="row">` so browser default `<th>` styling cannot diverge visually from React.
`normalize()` in `scripts/parity_cases/table.mjs` reconciles these documented differences; see the
comments there for the full list (grid roles, `data-collection`/`data-key` bookkeeping, absolute vs
relative sort hrefs, CSS var hashes in `style`). The table parity test strips the same CSS var
hashes from the static output.

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

## Pagination component (`pagination`)

The static pagination renderer lives in
`alliance_platform/ui/html_components/components/pagination.py` and mirrors `@alliancesoftware/ui`'s
`Pagination.tsx` rendered with `renderPaginationItemAsLink`: every control is a link to the current
request's path and query string with the page parameter changed (removed for page 1) and any
page-size parameter removed. Page-size selection, callbacks, client-managed state, custom item
renderers and custom `breakpoints` are reported and dropped. "Static pagination" in
`docs/templatetags.rst` documents the behaviour for projects.

The parity cases render React with `renderPaginationItemAsLink` and record the URL its links are
built from in `meta.current_url`; the Python parity test builds a `RequestFactory` request for the
same URL. Regenerate with `just sync-html-ui-parity-fixtures ../alliance-platform-js pagination`.

### Deliberate static-render differences from React

Reconciled by `normalize()` in `scripts/parity_cases/pagination.mjs` (React side) and
`strip_static_pagination_extensions()` in `tests/test_html_ui_pagination_parity.py` (static side):

- **Responsive ranges**: React measures the nav with a resize observer and re-renders with fewer
  pages below its 620px and 450px breakpoints, so its SSR output holds only the configured
  `siblingCount`/`boundaryCount` range. The static renderer renders all three ranges up front, the
  configured one plus the two breakpoint ranges, each `<li>` marked with a
  `responsiveItemVisibility` class (`large`, `medium`, `small`) that the stylesheet shows through
  container queries at the matching width. The parity test drops the medium and small items and the large class.
- **Absolute link URLs**: `renderPaginationItemAsLink` builds absolute URLs from `currentUrl`; the
  static renderer writes the path and query only. The generator strips the origin.
- **`aria-current`**: React's `PaginationItem` passes a boolean, so every page link gets
  `aria-current="true"` or `"false"`. The static renderer marks only the current page, with the
  `page` token. The generator maps `"true"` to `"page"` and drops `"false"`.
- **Disabled controls**: React's Button keeps `href` on a disabled link and cancels navigation
  with a click handler; the generator applies the shared Button normalisation described under
  "Deliberate static Button differences from React". Beyond omitting `href` and rendering
  `aria-disabled="true"`, the static renderer renders `tabindex="-1"`, which the parity test
  strips.

## Icon component (`icon`)

The static icon renderer lives in `alliance_platform/ui/html_components/components/icon.py` and
renders through `render_static_icon()` in `html_components/static_icon.py`, which the other
renderers use for their built-in icons too. It mirrors `@alliancesoftware/icons`' `Icon.tsx`: the
same classes and defaults (`xs` size, `plain` variant, `secondary` colour for the circle variants),
`role="img"`, and `aria-hidden="true"` unless an `aria-label` or `aria-hidden` is given. The SVG is
inlined from the package's `static-svg` files.

The parity cases render the generated components in `packages/icons/outlined/`. In the Python tests
the test bundler serves the copies in `tests/fixtures/icons/static-svg/`, so when an icon changes
upstream the regenerated fixture shows the new SVG and the copy needs updating to match.
Regenerate with `just sync-html-ui-parity-fixtures ../alliance-platform-js icon`.

### Deliberate static icon differences from React

- **`data-apui-slot="icon"`**: the static icon always marks its root (the default `slot`), which
  static parents and the stylesheets rely on. React's Icon only gets the attribute from a
  parent's slot context, such as Button's. `normalize()` in `scripts/parity_cases/icon.mjs` adds
  it to React's icon root.
- **SVG serialisation**: React clones the SVG with `width`, `height` and `focusable="false"`, which
  the `static-svg` files carry as well, but the files keep their own whitespace and attribute
  order. The Python comparison sorts attributes and drops whitespace between tags
  (`normalize_html_fragment()`), so nothing is stripped.

## Menubar components (`menubar`, `menubar_item`, `menubar_submenu`, `menubar_section`)

The static menubar renderers live in
`alliance_platform/ui/html_components/components/menubar.py` and
mirror `@alliancesoftware/ui`'s `Menubar.tsx` for server-rendered navigation menus. Interactivity
comes from a standalone runtime module in the JS repo —
`@alliancesoftware/ui/components/menu-bar/Menubar.attach.ts` — attached through
`attach_module_script()` exactly like the button group's `SmartOrientation.attach.ts` (per-root
`data-djid` + module script; the runtime is idempotent and holds cleanup state in a `WeakMap`).
The runtime never imports CSS mappings: the Python renderer exposes the state class names it must
toggle through `data-open-class` / `data-focused-class` / `data-popover-open-class` on the root.

### Cross-component render state

All static components share one document-level render-frame stack. Frames carry inherited slot
defaults, typed Table/Menubar payloads, opt-in direct-child reports and the document ID allocator.
The stack survives `{% include %}` (including `only`), unlike ordinary template variables. A
`MenubarRenderState` remains the typed menu payload, with a `MenubarRenderFrame` for each grouping
(root menu, submenu popup, section). `menubar`, `menubar_submenu` and `menubar_section` render their
children while the appropriate grouping frame is active so child counts are available when
deciding what to render:

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
5. Static icons publish a structured report after successful uncaptured rendering. Menubar items
   use ordered reports anchored against their rendered children to identify a direct leading icon;
   adjacent plain text is wrapped like the React `Text` component, and `hasLeadingIcon` state is
   propagated to the containing
   root or submenu `<ul>` for consistent indentation. The item wrapper and content span emit the
   shared `data-apui-menu-item-content-wrapper` and `data-apui-menu-item-content` markers used by
   `Menubar.css.ts` to space leading icons. Each icon-bearing item also emits its own
   `data-has-leading-icon` marker. With `root_item_display="icon-only"`, icon-bearing level-zero
   items get an `aria-hidden` tooltip while iconless items retain their visible label.
6. Structural nodes expose the same stable runtime hooks as React: submenu owner/trigger/chevron,
   popover/menu container, section owner/heading/items, and separator. Sections and separators use
   the same zero-based `data-level` convention as menu items; heading icon and label content use
   `data-apui-slot="icon"` and `data-apui-slot="label"`.

Button uses the same direct-child reports for automatic icon-only detection. Explicit
`is_icon_only` and Menubar `text_value` remain the escape hatches for deliberately composed or
otherwise ambiguous arbitrary HTML. Reports are not published by components rendered with
`as variable`, or by components omitted during permission resolution.

Reports stop at the nearest component frame. They are dropped when that direct parent did not opt
into collection rather than travelling to a more distant collecting ancestor; an icon nested in
another component is not a direct child of Button or Menubar.

### Deliberate static Button differences from React

- **Raw slotted elements**: React can inspect the mounted DOM and treats any sole direct element
  carrying `data-apui-slot="icon"` as icon-only. Static rendering only auto-detects an icon emitted
  by the static `icon` component's structured child report. Arbitrary raw elements can opt in with
  `is_icon_only=True`; this avoids parsing consumer HTML and prevents wrapped or composite content
  from being misclassified.
- **Disabled links**: React's Button passes `href` after useButton's props, so a disabled link
  keeps its `href` (plus a button-only `disabled` attribute, because the inferred anchor element
  type is not passed to useButton) and relies on a click handler to cancel navigation. The static
  renderer omits `href` and renders `aria-disabled="true"`, so the link cannot navigate without
  JavaScript. Other element types except `button`/`input` get `aria-disabled` too, matching
  useButton. `normalizeButtons()` in `scripts/parity_cases/_helpers.mjs` applies the same change to
  the React output.

Static components rendered inside a React component's children continue to participate in the
surrounding static render frames. This preserves the existing composition behaviour; use a layout
component that replaces its slot scope when a deliberate inheritance boundary is required.

Section separators are decided *after* pruning (`is_first` = parent frame count at render time),
so a pruned first section never leaves a leading separator behind.

### Intentionally unsupported React Menubar features

`onAction`/`onSelectionChange`/`onExpandedChange` callbacks, selection (`selectionMode` etc.),
dynamic collections (`items`/`childItems`), `itemElementType`, controlled `expandedKeys`, and
width overflow into a "More" submenu (`overflowLabel`/`overflowTextLabel`). These are reported
and dropped. `default_expanded_keys` *is* supported statically (submenus render open; the runtime
initialises from `data-open="true"`). Known first-pass runtime gaps: flyout positioning is simple
DOM-relative placement without viewport-aware flipping, and typeahead searches within the current
menu only.

### Deliberate static-render differences from React

Reconciled by `normalize()` in `scripts/parity_cases/menubar.mjs` (React side) and
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
- **Selection indicator**: React-selected items expose `data-apui-menu-item-selected-icon` on the
  check icon. Static menubar selection is intentionally unsupported, so the renderer never emits a
  selected icon; consumers can rely on the hook when the React component owns selection.
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
container interaction. Root-item presentation is independent: render
`root_item_display="icon-only"` initially or call `controller.setRootItemDisplay(display)` after
attachment; neither operation creates another menu tree.

## HTML parity fixture workflow

Parity fixtures record what the React components render for a set of cases, so the Python tests
can check that the static renderers produce the same markup, class names and diagnostics. The
generator imports `@alliancesoftware/ui` TypeScript sources, so it runs inside an
`alliance-platform-js` checkout: `scripts/syncHtmlUiParityFixtures.sh` runs
`scripts/generateHtmlUiParityFixtures.mjs` under that checkout's vite-node from `packages/ui`.

### Case modules

The generator loads every module in `scripts/parity_cases/` (names starting with `_` are skipped)
and writes `tests/fixtures/ui_html_<component>_parity.json` for each. A module exports:

- `component`: the static component name, which names the fixture.
- `cases`: objects with a `name`, the Django `template`, `buildElement({ React, components })`
  returning the equivalent React element, and `meta`. `meta.current_url` is the URL React's link
  components see during SSR; the Python test builds a request for it. Other keys are flags the
  module's `normalize` reads, such as `preserve_icon_only`.
- `loadComponents({ uiPackageDir, importDefault, importBareModule })`: the components the cases
  build with, passed to `buildElement` as `components`.
- `normalize(root, testCase, helpers)`: React-side normalisation for the component family, applied
  to the parsed SSR markup. `helpers` is `scripts/parity_cases/_helpers.mjs`: id remapping, inline
  style and CSS var normalisation, the shared Button normalisation and the class-token normaliser.
- `stylesheets`: every `.css.ts` path the component's renderers resolve, written as the renderers
  request it (`@alliancesoftware/ui/components/button/Button.css.ts`).
- `class_prefixes` and `keep_class_tokens` (both default to empty): the vanilla-extract scopes the
  fixture compares and tokens exempt from the parent-collapse rules (see `normalizeClassTokens()`
  in `_helpers.mjs`). Both are written into the fixture.

For each case the generator renders the element with `renderToStaticMarkup`, records anything
logged with `console.warn` as `expected_warnings`, parses the markup, removes the React Aria
attributes every component carries (`data-react-aria-pressable`, `tabindex="0"`), applies the
module's `normalize`, reduces every class attribute with `normalizeClassTokens` and serialises it.

### Class mappings

The generator also writes `tests/fixtures/css-mappings.json`, keyed by the request paths in the
modules' `stylesheets`: each value is the mapping the Vite plugin's `extractMappingFromModule()`
produces, the JSON Django reads at runtime. The sync script points vite-node at
`scripts/vite.parity.config.mjs`, which loads the ui package's Vite config with vanilla-extract's
identifiers pinned to `debug`, so classes read `Button_baseButton__1xyn7kcv` whatever the mode.
That config also aliases `@alliancesoftware/vite-plugin-django` to its `src/` entry: the
vanilla-extract plugin's source imports it by name and the package's entry points are build
output, so a plain `yarn install` in the JS checkout is enough and no build step is needed.

`HtmlUIParityTestCase` renders with these mappings; there are no mocks. A stylesheet a renderer
resolves that the file lacks fails the test with the command to run, and a style missing from a
listed stylesheet is a contract diagnostic, which fails the comparison with `expected_warnings`.
`assert_parity_case()` reduces the raw static output with `normalize_class_tokens()`, the port in
`tests/parity/normalizers.py`, using the fixture's `class_prefixes` and `keep_class_tokens`, then
compares it with the fixture's markup with attributes sorted and whitespace between tags dropped.
`render_ui_template()` and `render_ui_document()` give unit tests readable names instead: class
attributes go through the same token rules with every scope allowed except the `font` typography
classes, and custom properties in `style` attributes lose their hashes.

### Commands

From `alliance-platform-py`:

```bash
# Regenerate every fixture against ../alliance-platform-js, or another checkout
just sync-html-ui-parity-fixtures
just sync-html-ui-parity-fixtures /path/to/alliance-platform-js

# Regenerate one fixture; css-mappings.json is still rewritten for every module
just sync-html-ui-parity-fixtures ../alliance-platform-js button_group

# Regenerate everything and fail if a fixture or css-mappings.json changed
just check-html-ui-parity-fixtures /path/to/alliance-platform-js
```

Fixtures and `css-mappings.json` are generated: never edit them by hand. When a comparison fails,
fix the renderer or the normalisation and regenerate.

## CI fixture drift check

The cross-repo fixture drift workflow is defined in:

- `.github/workflows/ap-ui-fixture-drift.yml`

It runs on pull requests that touch the fixtures, `css-mappings.json`, `scripts/`, the JS ref pin
or the workflow, and on manual dispatch. It checks out both `alliance-platform-py` and
`alliance-platform-js`, installs the JS dependencies, runs the sync script, and fails if any
`ui_html_*_parity.json` fixture or `css-mappings.json` changed.

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
