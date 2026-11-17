---
"alliance-platform-ui": patch
---

Add static checkboxes, checkbox groups, and radio groups. `{% ui "checkbox" %}`,
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
