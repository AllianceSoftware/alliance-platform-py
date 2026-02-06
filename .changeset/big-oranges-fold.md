---
"alliance-platform-frontend": patch
---

Improve frontend asset path validation to detect case mismatches in template-included assets during development. When an asset path matches only by case (for example `MyView.tsx` vs `Myview.tsx`), Alliance Platform now raises a `TemplateSyntaxError` with the actual filesystem path so the mismatch is fixed before CI fails on case-sensitive filesystems.
