---
"alliance-platform-frontend": patch
---

alliance_ui tag `{% Fragment %}` no longer imports from re-exports and instead uses "react" directly. This removes the need for the frontend/src/re-exports file in projects and can be removed.
