---
"alliance-platform-frontend": patch
"alliance-platform-ui": patch
---

Load interactive static UI component runtimes through deduplicated external auto-attachment modules instead of emitting one inline module script per component instance. Static Menubar labels now expose the same stable slot marker as React, and generated NumberInput form-control IDs no longer depend on runtime selectors.

Collected JavaScript resources from packages now use the development package resolver so TypeScript entrypoints are transformed by Vite before they reach the browser.
