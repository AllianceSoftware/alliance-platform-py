---
"alliance-platform-ui": patch
---

The `{% ui %}` dispatcher now accepts a reserved `props` kwarg holding a dict of props to apply in bulk (e.g. `props=widget.attrs|merge_props:extra_widget_props` in form widget templates). HTML attribute names are adapted to the component prop contract automatically, and `merge_props` is now also available from the `alliance_platform.ui` template tag library.
