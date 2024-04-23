# alliance-platform-frontend

## 0.0.4

### Patch Changes

- 0dbe111: Add `server_resolve_package_url` option to `ViteBundler`. This is used to resolve node_modules packages via the Vite dev server, rather than generating the URL ourselves. This behaves better with optimized deps and avoids a common case of "Outdated Optimized Deps" errors.

## 0.0.3

### Patch Changes

- e6fcaea: Add FRONTEND_ASSET_REGISTRY setting, remove default `frontend_asset_registry`

## 0.0.2

### Patch Changes

- 58839dc: Fix alliance_platform.frontend AppConfig to have a unique label
