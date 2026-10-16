---
"alliance-platform-ui": patch
---

Document when application code must call the static number input controller's `sync()` before direct form serialization, including programmatic value and disabled changes, immediate resets, and changes made after the runtime's submit listener.
