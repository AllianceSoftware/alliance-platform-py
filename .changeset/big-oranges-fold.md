---
"alliance-platform-frontend": patch
---

Add support to detect case mismatches in template-included assets during development. When an asset path matches only by case (for example `MyView.tsx` vs `Myview.tsx`), Alliance Platform can raise a `TemplateSyntaxError` with the actual filesystem path so the mismatch is fixed before CI fails on case-sensitive filesystems. This can be enabled with the `BUNDLER_CHECK_CASE_SENSITIVE` option. This introduces a noticeable overhead per file and so is disabled by default.
