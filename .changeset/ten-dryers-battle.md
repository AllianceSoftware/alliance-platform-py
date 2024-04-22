---
"alliance-platform-frontend": patch
---

Add `DEV_CODE_FORMAT_LIMIT` to limit the size of code the dev server will attempt to format (default 1mb).
Add `DEV_CODE_FORMAT_TIMEOUT` to control the timeout applied to requests to the Vite dev server for formatting; defaults to 1 second.
