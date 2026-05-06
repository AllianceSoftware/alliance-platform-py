---
"alliance-platform-codegen": patch
---

Fix `FileNotFoundError` when writing the codegen artifact cache if the `CACHE_DIR` (default `.alliance-platform/`) does not yet exist. The directory is now created on `CodegenRegistry` initialisation.
