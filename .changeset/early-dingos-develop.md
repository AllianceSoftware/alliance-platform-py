---
"alliance-platform-dev": patch
---

Add the Alliance Platform worktree-aware development runner, including an interactive installer
for adopting it in existing Django projects and a private machine-wide registry of worktree-owned
resources, with commands for listing and safely removing retained environments. Report timed
progress while cloning and preparing worktree databases. Template clones can opt into PostgreSQL's
``wal_log`` or ``file_copy`` strategy, and default clones link to the copy-on-write setup guide.
Existing-project installation now detects available verification commands and leaves unresolved
commands explicitly disabled instead of referencing assumed ``bin/`` scripts.
Generated database names reserve space for Django's parallel test database suffixes, preventing
PostgreSQL identifier truncation from collapsing worker clones onto the primary test database.
Generated launchers now retain uvx's isolated cache in a sandbox-writable, worktree-shared temporary
location, avoiding repeated dependency downloads and builds after the first successful bootstrap.
Mutable local tool sources now run as isolated editable dependencies so a shared cache cannot keep
running an older build from the same checkout path.
Python-backed verification commands automatically use a provisioned project virtualenv when the
caller has not explicitly activated one, allowing project wrappers to invoke installed tools
without requiring developers or agents to source ``activate`` first.
