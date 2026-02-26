# AGENTS.md

## Scope

This file applies to the whole repository (`alliance-platform-py-codex`).

## Repository Overview

- Monorepo with Python packages in `packages/`.
- Package directories are named `ap-<name>`.
- Importable modules live under namespaced package `alliance_platform` inside each package.

Current packages:

- `ap-core`
- `ap-codegen`
- `ap-frontend`
- `ap-storage`
- `ap-audit`
- `ap-ui`
- `ap-pdf`
- `ap-server-choices`
- `ap-ordered-model`

## Tooling and Setup

- Python/package management: `uv`
- JS tooling: `yarn` (Node.js 20+)
- Task runner: `just` (optional but preferred)

Initial setup:

```bash
uv sync --all-groups
yarn
```

## Preferred Development Workflow

1. Keep changes scoped to the relevant package(s).
2. Run targeted checks first.
3. Run package-level tests for touched packages.
4. Add/update docs and changeset when release behavior changes.

## Commands

Lint and format:

```bash
just lint
just format
just format-check
```

Type checking:

```bash
just mypy-package ap-frontend
just mypy-all
```

Test one package:

```bash
just test-package ap-frontend
```

Test one package with Python/constraint (CI-like):

```bash
just test-package ap-frontend 3.12 django42
just test-package ap-frontend 3.12 django52
```

Run a focused Django test in a package:

```bash
cd packages/ap-frontend
uv run ./manage.py test tests.test_bundler.TestViteBundlerTestCase.test_resolve
```

## Test Environment Notes

- Package test settings use PostgreSQL (`django.db.backends.postgresql`) across packages.
- Ensure local DB access is configured (`DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`) or defaults are valid.
- Some frontend tests rely on Node tooling (for example Prettier via `node_modules`). Keep `yarn` dependencies installed.

## Dependency Changes

- Edit the relevant package `pyproject.toml` (`[project.dependencies]` and/or `[dependency-groups].dev`).
- Run `uv sync` to update workspace lockfile (`uv.lock`).

## Releases and Changesets

- For user-visible behavior changes, add a changeset:

```bash
yarn changeset
```

- Commit the generated file in `.changeset/` with the code change.
- Currently every release is a patch version

## Docs

- Package docs live under each package `docs/` directory.
- Top-level docs live under `docs/`.
- Use `just docs-watch` when working on documentation.

## Agent Guardrails

- Do not make unrelated cross-package changes.
- Do not change lockfiles unless dependency changes require it.
- Prefer small, reviewable patches with tests close to the changed behavior.
- If a command fails due to missing local services (DB/Node), report exactly what is missing and continue with static checks where possible.
