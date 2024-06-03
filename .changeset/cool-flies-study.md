---
"alliance-platform-codegen": patch
---

Fix type on `AlliancePlatformCodegenSettingsType.POST_PROCESSORS`; it should be either a string (the module import path) or a list of `ArtifactPostProcessor` instances.
