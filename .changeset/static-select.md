---
"alliance-platform-ui": patch
---

Add the static [`select`](https://alliance-platform.readthedocs.io/projects/ui/latest/templatetags.html#static-selects)
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
