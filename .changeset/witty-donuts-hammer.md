---
"alliance-platform-frontend": patch
---

Perform asset registry checks in `lock`, and only when `DEBUG` is `True`. These checks do not need to happen in production, and could break things if you remove the frontend source code from the deployed files.
