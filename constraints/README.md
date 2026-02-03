# Django Version Constraints

This directory contains override files used in CI to test against specific Django versions.

## Files

- `django42.txt` - Constrains Django to 4.2.x (>=4.2,<5.0)
- `django52.txt` - Constrains Django to 5.2.x (>=5.2,<6.0)

## Usage

These files are used as overrides via the `UV_OVERRIDE` environment variable in the CI workflow:

```yaml
env:
  UV_OVERRIDE: constraints/${{ matrix.django-version }}.txt
```

The workflow uses `uv export` to generate requirements (including dev dependencies from dependency groups), then `UV_OVERRIDE` replaces the Django version:

```bash
uv export --no-hashes --package alliance-platform-core | uv pip install -r -
# With UV_OVERRIDE set, Django version is replaced according to the override file
```

This ensures:
- Python 3.11-3.13 with `django42` → Django 4.2.x
- Python 3.11-3.13 with `django52` → Django 5.2.x
- All dev dependencies from `[dependency-groups]` are included

## Background

Without overrides, Python 3.12+ would resolve to Django 6.0+ (due to `Django>=4.2.11` in package dependencies), which could introduce breaking changes before we're ready to support them.

Using `uv export` with `UV_OVERRIDE` allows us to:
1. Use the proper `[dependency-groups]` from pyproject.toml (no manual dependency lists)
2. Override only the Django version while preserving all other dependencies
3. Match CI behavior exactly in local testing

## Local Testing

### Using Justfile (Recommended)

The easiest way to test with overrides locally:

```bash
# Test single package with Django 4.2
just test-package ap-pdf 3.12 django42

# Test single package with Django 5.2
just test-package ap-pdf 3.12 django52

# Test all packages with Django 4.2
just test-all 3.12 django42
```

### Using uv Directly

You can also use overrides directly (matches CI exactly):

```bash
# Test with Django 4.2
UV_PYTHON=3.12 bash -c '
  uv venv &&
  uv export --no-hashes --package alliance-platform-pdf | UV_OVERRIDE=constraints/django42.txt uv pip install -r - &&
  cd packages/ap-pdf &&
  UV_NO_SYNC=1 uv run ./manage.py test
'

# Test with Django 5.2
UV_PYTHON=3.12 bash -c '
  uv venv &&
  uv export --no-hashes --package alliance-platform-pdf | UV_OVERRIDE=constraints/django52.txt uv pip install -r - &&
  cd packages/ap-pdf &&
  UV_NO_SYNC=1 uv run ./manage.py test
'
```
