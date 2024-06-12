---
"alliance-platform-frontend": patch
---

FrontendAssetRegistry.lock will now only warn rather than throw an error if invalid values are used. This only occurs when DEBUG is True. This is to better accomodate configurations where node_modules might not be available (e.g. having DEBUG on in CI, but node_modules not installed).
