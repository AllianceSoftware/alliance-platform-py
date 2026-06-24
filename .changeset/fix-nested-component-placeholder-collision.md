---
"alliance-platform-frontend": patch
---

Fix placeholder collisions in `NestedComponentPropAccumulator` that could corrupt the generated React children when a component contained more than 10 nested components. Placeholder tokens like `__NestedComponentPropAccumulator__prop__1` were a prefix of `__NestedComponentPropAccumulator__prop__10`, so `apply()` could match the wrong placeholder and emit children in the wrong order, leaving raw placeholder strings and dropped/duplicated elements in the output. Placeholders now use a delimited, monotonically-increasing token and `apply()` orders children by their position in the rendered value.
