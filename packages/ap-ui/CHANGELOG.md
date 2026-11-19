# alliance-platform-ui

## 0.0.6

### Patch Changes

- 1b11e66: Add static checkboxes, checkbox groups, and radio groups. `{% ui "checkbox" %}`,
  `{% ui "checkbox_group" %}`, `{% ui "radio_group" %}`, and `{% ui "radio" %}`
  render the Alliance UI components as HTML that needs no React and no script. See
  the [checkbox](https://alliance-platform.readthedocs.io/projects/ui/latest/templatetags.html#static-checkboxes),
  [checkbox group](https://alliance-platform.readthedocs.io/projects/ui/latest/templatetags.html#static-checkbox-groups),
  and [radio group](https://alliance-platform.readthedocs.io/projects/ui/latest/templatetags.html#static-radio-groups)
  docs.

  - Requires `@alliancesoftware/ui@0.0.68`. Upgrade the two packages together.
    The [system check](https://alliance-platform.readthedocs.io/projects/ui/latest/installation.html#system-checks)
    reports a version mismatch.
  - If you use [`StaticFormRenderer`](https://alliance-platform.readthedocs.io/projects/ui/latest/installation.html#static-form-widgets),
    Django's `CheckboxInput`, `RadioSelect`, and `CheckboxSelectMultiple` widgets
    now render as these components. A widget that your project has its own
    template for keeps that template.
  - `is_read_only`, or `readonly` in a widget's `attrs`, makes a checkbox or radio
    [read-only](https://alliance-platform.readthedocs.io/projects/ui/latest/templatetags.html#static-read-only-checkboxes-and-radios)
    with no script. The form still submits the checked values.
  - `ui_migration_check` suggests these components for `Checkbox`,
    `CheckboxGroup`, `RadioGroup`, and `Radio`.

- 1efe0e9: Add the static [`select`](https://alliance-platform.readthedocs.io/projects/ui/latest/templatetags.html#static-selects)
  component. `{% ui "select" %}` renders a native `<select>` styled like the
  static text input, with your `<option>` and `<optgroup>` elements as its
  children. `value` selects options, and `is_multiple=True` makes a multiple
  select.

  - Requires `@alliancesoftware/ui@0.0.68`. Upgrade the two packages together.
    The [system check](https://alliance-platform.readthedocs.io/projects/ui/latest/installation.html#system-checks)
    reports a version mismatch.
  - If you use [`StaticFormRenderer`](https://alliance-platform.readthedocs.io/projects/ui/latest/installation.html#static-form-widgets),
    Django's `Select`, `SelectMultiple`, and `NullBooleanSelect` widgets now
    render as `select`, unless your project has its own `select.html` or
    `select_option.html` widget template.
  - `ui_migration_check` suggests `select` in place of the React `Select` and
    `MultipleSelect`.

## 0.0.5

### Patch Changes

- 6c2042b: Add the `{% ui %}` template tag, which renders Alliance UI components as static HTML with no React on
  the page: icons, buttons and button groups, text, number and text area inputs, labeled inputs, inline
  alerts, menubars, pagination, tables, and the content, heading, header and footer layout parts.
  Components take snake_case props, the leaf components take no end tag, and the React tags remain for
  everything the static components do not cover. The
  [`{% ui %}` reference](https://alliance-platform.readthedocs.io/projects/ui/latest/templatetags.html#ui)
  documents every component and its props, and
  [Writing a static component](https://alliance-platform.readthedocs.io/projects/ui/latest/static_components.html)
  covers adding your own.

  - Forms: the opt-in
    [`StaticFormRenderer`](https://alliance-platform.readthedocs.io/projects/ui/latest/installation.html#static-form-widgets)
    renders Django's text, number and text area widgets with the static components, and
    `{% ui "labeled_input" %}` wraps any other control in the inputs' label, help text and error
    message. Form help text and errors marked safe keep their HTML in both the React and static
    widgets.
  - The `alliance_platform.ui` template library now provides the `merge_props` and `none_as_nan`
    filters.
  - Template mistakes are logged to the `alliance_platform.ui` logger; the
    [`STATIC_COMPONENT_STRICT`](https://alliance-platform.readthedocs.io/projects/ui/latest/installation.html#settings)
    setting, which defaults to `DEBUG`, raises them instead.
  - Requires `alliance-platform-frontend>=0.0.24`, `@alliancesoftware/ui@0.0.67` and
    `@alliancesoftware/icons@0.0.14`, the first releases that ship a `static-contract.json`. A
    [system check](https://alliance-platform.readthedocs.io/projects/ui/latest/installation.html#system-checks)
    reports an installed version the renderers do not support, and `extract_frontend_resources` now
    runs the system checks tagged `alliance_platform_frontend_build` and fails the build on an error.

- 8a1df99: Add the
  [`ui_migration_check`](https://alliance-platform.readthedocs.io/projects/ui/latest/templatetags.html#finding-legacy-component-usages)
  management command, which lists the React component tags in your templates and whether each can move
  to a static `{% ui %}` component. `--strict` exits non-zero while any remain.

## 0.0.4

### Patch Changes

- 0ee15e0: Fix two latent bundling issues where components referenced dynamically at render time were not statically discoverable, so could be omitted from the production frontend bundle:

  - `InlineAlert` wraps plain-string children in a `Content` component.
  - `form_input` wraps the widget in a `LabeledInput` component when `non_standard_widget=True`.

  Both dependencies are now registered for bundling at parse time.

## 0.0.3

### Patch Changes

- 8f82c94: Support defining frontend resources more explicitly to facilitate better bundling. For example, ES module usage is now supported such that Vite can bundle the exports you use, rather than all exports for a given file/module. In the template project this reduces bundle size by about 75%.

  `FrontendAssetRegistry` has been deprecated in favour of [FrontendResourceRegistry](https://alliance-platform.readthedocs.io/projects/frontend/latest/api.htmlapi.html#alliance_platform.frontend.bundler.resource_registry.FrontendResourceRegistry). In addition, the `FRONTEND_ASSET_REGISTRY` setting
  has been renamed to [FRONTEND_RESOURCE_REGISTRY](https://alliance-platform.readthedocs.io/projects/frontend/latest/settings.html#alliance_platform.frontend.settings.AlliancePlatformFrontendSettingsType.FRONTEND_RESOURCE_REGISTRY) but will continue to work with a deprecation warning. Migration is straightforward -
  use the new class and call `add_resource` rather than `add_asset`. You can still pass a `Path` to `add_resource`, but
  can be more specific and pass resource instances instead like [ESModuleResource](https://alliance-platform.readthedocs.io/projects/frontend/latest/api.html#alliance_platform.frontend.bundler.frontend_resource.ESModuleResource)

## 0.0.2

### Patch Changes

- d0a4643: Add [create_dict](https://alliance-platform.readthedocs.io/projects/ui/latest/templatetags.html#create-dict) templatetag and [with_params](https://alliance-platform.readthedocs.io/projects/ui/latest/templatetags.html#with-params) filter

## 0.0.1

### Patch Changes

- 8262e04: Split ap frontend into separate packages: alliance_platform_frontend and alliance_platform_ui
