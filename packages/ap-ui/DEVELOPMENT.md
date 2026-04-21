# ap-ui Development Notes

This file contains maintainer-focused workflow notes for developing `alliance-platform-py/packages/ap-ui`.

## Adding a new HTML dispatcher component

1. Add a renderer class under:
   - `alliance_platform/ui/templatetags/alliance_platform/html_components/components/`
2. Register it in:
   - `alliance_platform/ui/templatetags/alliance_platform/html_components/registry.py`
3. Add parity cases in:
   - `scripts/parity_cases/`
   - include `class_prefixes` in each parity case module so fixture generation can keep relevant VE class tokens without hardcoding full class maps.
4. Regenerate fixtures:
   - `just sync-html-ui-parity-fixtures`
5. Add or extend parity tests in:
   - `tests/`

## HTML parity fixture workflow

The fixture generator depends on `@alliancesoftware/ui` TypeScript sources, so it must run through the `alliance-platform-js` runtime context.

From `alliance-platform-py`:

```bash
just sync-html-ui-parity-fixtures
```

Use a non-default JS checkout path:

```bash
just sync-html-ui-parity-fixtures /path/to/alliance-platform-js
```

Generate a single component fixture:

```bash
just sync-html-ui-parity-fixtures ../alliance-platform-js button_group
```

Check fixture drift (for CI or pre-commit checks):

```bash
just check-html-ui-parity-fixtures /path/to/alliance-platform-js
```

## CI fixture drift check

The cross-repo fixture drift workflow is defined in:

- `.github/workflows/ap-ui-fixture-drift.yml`

It checks out both `alliance-platform-py` and `alliance-platform-js`, regenerates the fixtures, and fails if fixture files changed.
