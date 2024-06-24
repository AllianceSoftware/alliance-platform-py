---
"alliance-platform-frontend": patch
"alliance-platform-codegen": patch
---

Fix code generated for embedding with <script> tags to properly escape code and avoid XSS vulnerabilities. This affected the `{% component %}` tag.
