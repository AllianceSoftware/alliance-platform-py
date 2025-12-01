---
"alliance-platform-codegen": patch
---

Add support for eslint 9. This is a BREAKING change - for existing projects using eslint < 9 change the class used from `EslintFixPostProcessor` to `LegacyEslintFixPostProcessor`.
