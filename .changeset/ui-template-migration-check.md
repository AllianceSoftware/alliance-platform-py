---
"alliance-platform-ui": patch
---

Add the
[`ui_migration_check`](https://alliance-platform.readthedocs.io/projects/ui/latest/templatetags.html#finding-legacy-component-usages)
management command, which lists the React component tags in your templates and whether each can move
to a static `{% ui %}` component. `--strict` exits non-zero while any remain.
