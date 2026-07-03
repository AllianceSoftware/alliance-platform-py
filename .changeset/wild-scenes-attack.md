---
"alliance-platform-frontend": patch
"alliance-platform-ui": patch
---

Add `RenderableContent`, a backend-neutral representation for trusted renderable HTML fragments. `{% form_input %}` now stores `help_text` as `RenderableContent` in `extra_widget_props["description"]`: the React `{% component %}` path converts it to nested React elements (equivalent output to before), and static `{% ui %}` input widgets can now render HTML help text instead of dropping it. `convert_html_string()` is unchanged for existing callers.
