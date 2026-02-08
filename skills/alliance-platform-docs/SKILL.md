---
name: alliance-platform-docs
description: Answer questions about Alliance Platform package APIs, settings, installation, usage, template tags, and migrations by consulting generated Markdown references. Use for requests involving alliance_platform core, frontend, codegen, storage, audit, ui, pdf, server-choices, or ordered-model docs.
compatibility: Designed for filesystem-based coding agents (Codex/Claude Code style). Useful when one or more alliance-platform-* Python libraries are installed or being integrated.
---

# Alliance Platform Docs

Prioritize helping app developers consume Alliance Platform packages: installation, settings, usage patterns, template tags, API behavior, and migrations.

## Package Map

- [Core](references/generated/core/index.md): shared foundation, package-level configuration patterns, core auth/settings APIs.
- [Frontend](references/generated/frontend/index.md): Vite/bundler integration, React component embedding, template tags and SSR behavior.
- [Codegen](references/generated/codegen/index.md): code generation framework and artifact generation workflows.
- [Storage](references/generated/storage/index.md): async uploads, storage backends, upload/download flows, management commands.
- [Audit](references/generated/audit/index.md): model auditing, history/event tracking, audit views, integration patterns.
- [UI](references/generated/ui/index.md): Alliance UI Django template tags and form rendering helpers.
- [PDF](references/generated/pdf/index.md): HTML-to-PDF rendering setup, deployment, runtime options, and usage details.
- [Server Choices](references/generated/server-choices/index.md): server-driven field choices endpoints and serializer/form integrations.
- [Ordered Model](references/generated/ordered-model/index.md): trigger-backed ordered model behavior and migration guidance.

## Consumer-Focused Routing

- For setup questions, open each package `installation.md` then `settings.md`.
- For “how do I use X?” questions, open `usage.md`/`overview.md`/`templatetags.md` first.
- For exact APIs, open `api.md` after behavior is understood.
- For upgrade concerns, check `legacy-migration.md` where available.

## Answering Rules

1. Prefer package-local docs first, then follow cross-package links only when required.
2. Explain behavior in consumer terms (what to configure, what to call, expected output).
3. Include concrete setting names, template tags, class/function names, and file paths from docs.
4. If docs and implementation differ, trust code and explicitly note the discrepancy.
