---
"alliance-platform-ui": patch
---

Add static checkboxes, checkbox groups and radio groups. `{% ui "checkbox" %}`,
`{% ui "checkbox_group" %}`, `{% ui "radio_group" %}` and `{% ui "radio" %}` render Alliance UI's
Checkbox, CheckboxGroup, RadioGroup and Radio as HTML with no React on the page and no script: the
browser checks the inputs and the styles follow. The
[checkbox](https://alliance-platform.readthedocs.io/projects/ui/latest/templatetags.html#static-checkboxes),
[checkbox group](https://alliance-platform.readthedocs.io/projects/ui/latest/templatetags.html#static-checkbox-groups)
and [radio group](https://alliance-platform.readthedocs.io/projects/ui/latest/templatetags.html#static-radio-groups)
references document their props.

- Forms: the
  [`StaticFormRenderer`](https://alliance-platform.readthedocs.io/projects/ui/latest/installation.html#static-form-widgets)
  also renders Django's `CheckboxInput`, `RadioSelect` and `CheckboxSelectMultiple` widgets with
  them. A template of your own for the widget still renders it, as does your own version of a
  template Django's renders through: `input.html`, and for the radio and checkbox select
  `multiple_input.html`, `input_option.html` and the option templates. As in the React widget, the
  field's label sits beside a checkbox, with the field's help text, or its errors, below it.
- Read only: `is_read_only`, or `readonly` in a form widget's attrs, stops a checkbox or radio
  changing with no script. HTML has no read only state for them, so the input renders disabled with
  the look of an enabled one, and a hidden input submits each checked value: the form submits what
  the controls show.
- Requires `@alliancesoftware/ui@0.0.68`, the first release with version 2 of the static contract;
  the [system check](https://alliance-platform.readthedocs.io/projects/ui/latest/installation.html#system-checks)
  reports an earlier release.
- `ui_migration_check` suggests the static components for `Checkbox`, `CheckboxGroup`, `RadioGroup`
  and `Radio`.
