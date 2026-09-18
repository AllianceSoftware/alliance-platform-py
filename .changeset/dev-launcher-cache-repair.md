---
"alliance-platform-dev": patch
---

Store generated launcher environments in a durable user cache when writable, check cached entry
points offline, and rotate and rebuild incomplete bootstrap environments before running commands.
Add `alliance-dev update-launcher` so existing projects can adopt the fix without rerunning the
interactive installer:

```bash
uvx --upgrade --from alliance-platform-dev alliance-dev update-launcher
```
