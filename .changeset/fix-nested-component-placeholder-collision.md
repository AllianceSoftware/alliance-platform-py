---
"alliance-platform-frontend": patch
---

Fix components with more than 10 nested child components rendering incorrectly. Previously, large component trees (for example a table with many rows, each containing conditional nested components) could render with missing, duplicated, or out-of-order elements, and sometimes leaked raw internal placeholder text into the output. Affected components now render all of their children correctly and in the right order.
