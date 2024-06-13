---
"alliance-platform-frontend": patch
---

`{% component %}` tag will now only convert prop names from `this_case` to `thisCase`. Previously this was converting nested dicts as well - so things like `{ MY_CONSTANT: 5}` became `{ MYCONSTANT: 5}`.
