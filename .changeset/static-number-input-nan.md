---
"alliance-platform-ui": patch
---

Treat Python float and Decimal NaN values as empty in static NumberInput markup, including its
visible field and attach-runtime initial value, so NaN is never submitted with the form.
