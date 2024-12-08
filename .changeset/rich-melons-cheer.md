---
"alliance-platform-frontend": patch
---

Support defining frontend resources more explicitly to faciliate better bundling. For example, ES module usage is now supported such that Vite can bundle the exports you use, rather than all exports for a given file/module. In the template project this reduces bundle size by about 75%.
