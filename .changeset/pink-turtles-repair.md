---
"alliance-platform-frontend": patch
---

Fix `{% component %}` handling of HTML help_text. Previously, a component coming through in help_text from `{% form_input %}` would be outputted as its escaped embed code rather than rendering it.
