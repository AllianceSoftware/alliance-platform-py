---
"alliance-platform-ui": patch
---

Add the static [`native_select`](https://alliance-platform.readthedocs.io/projects/ui/latest/templatetags.html#static-native-selects)
component: a native `<select>` with the label, help text, error message, sizes and states of the
static text input. Its children are the `<option>` and `<optgroup>` elements, `value` selects
options and `is_multiple=True` makes a multiple select. The opt-in
[`StaticFormRenderer`](https://alliance-platform.readthedocs.io/projects/ui/latest/installation.html#static-form-widgets)
now renders Django's `Select`, `SelectMultiple` and `NullBooleanSelect` widgets with it, unless your
project has its own `select.html` or `select_option.html` widget template, and `ui_migration_check`
suggests it in place of the React `Select` and `MultipleSelect`.

Requires `@alliancesoftware/ui@0.0.68`, which ships static contract version 2: upgrade the two
together, as the [system check](https://alliance-platform.readthedocs.io/projects/ui/latest/installation.html#system-checks)
reports the mismatch otherwise.
