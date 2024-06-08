---
"alliance-platform-frontend": patch
---

Default `extra_widget_props` to empty dict if not set. This avoids need for widget templates to check for existence; it can rely on it being set so long as `FORM_RENDERED` is set. This allows widget templates to work when used with or without the `form_input` tag.
