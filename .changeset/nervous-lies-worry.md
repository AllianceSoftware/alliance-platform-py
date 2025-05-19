---
"alliance-platform-frontend": patch
---

Correctly handle context modifying child nodes of a {% component %} tag. Previously, if context was modified by a tag within a {% component %} tag it would not be available in subsequent nodes. For example using `create_dict`.
