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

For private `alliance-platform-js` access in GitHub Actions, configure:

- `ALLIANCE_PLATFORM_JS_DEPLOY_KEY`: private SSH key matching a read-only deploy key on `AllianceSoftware/alliance-platform-js`.
