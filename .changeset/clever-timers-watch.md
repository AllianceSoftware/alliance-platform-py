---
"alliance-platform-frontend": patch
---

Add classmethod `get_paths_for_bundling` to `ComponentProp`. This allows a handler to specify what dependencies they have that need to be included by the bundler. Previously this was done manually using `FrontendAssetRegistry"
