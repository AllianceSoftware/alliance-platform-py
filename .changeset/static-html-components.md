---
"alliance-platform-frontend": patch
"alliance-platform-ui": patch
---

Add the server-rendered `{% ui %}` component system with parity renderers for icons, buttons, button
groups, text and number inputs, text areas, Menubars, and tables. The components support Django-native
links and form submission, permission-aware menu pruning, backend-driven table sorting, unique input
associations, and deduplicated external runtimes for interactive Menubars and NumberInputs. Inline
Menubars can optionally persist expanded submenu paths in a server-readable cookie so the initial HTML
renders without a state flash. Static table sort icons remain inline while their SVG files are tracked
as build dependencies, avoiding duplicate document images.

The dispatcher accepts bulk props through the reserved `props` argument and exports `merge_props` from
the UI template library. New backend-neutral `RenderableContent` preserves trusted HTML form help text
for both React and static renderers, while frontend resource resolution now supports reading source and
production assets required by static icons and component runtimes.
