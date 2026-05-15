---
"alliance-platform-ui": patch
---

Fix `InlineAlert` template tag so the `Content` component it wraps plain-string children in is always included in the final frontend bundle. Previously the `Content` import was not statically discoverable and could be omitted from the build, causing the component to fail to render at runtime.
