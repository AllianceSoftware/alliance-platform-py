---
"alliance-platform-frontend": patch
---

Add `server_resolve_package_url` option to `ViteBundler`. This is used to resolve node_modules packages via the Vite dev server, rather than generating the URL ourselves. This behaves better with optimized deps and avoids a common case of "Outdated Optimized Deps" errors.
