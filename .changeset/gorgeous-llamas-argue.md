---
"alliance-platform-codegen": patch
---

Make codegen detection of when to abort more robust. This helps avoid cases where codegen runs mid server restart and the git head changes which can produce incorrect changes.
