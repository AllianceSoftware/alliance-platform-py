# Justfile for alliance-platform-py development tasks

# Install dependencies
install:
    uv sync

# Run tests for specific package
test-package package:
    cd packages/{{package}} && uv run ./manage.py test

# Run tests for all packages
test-all:
    #!/usr/bin/env bash
    set -e
    for pkg in ap-core ap-codegen ap-frontend ap-storage ap-audit ap-ui ap-pdf ap-server-choices ap-ordered-model; do
        echo "Testing $pkg..."
        cd packages/$pkg && uv run ./manage.py test
        cd ../..
    done

# Run mypy for specific package
mypy-package package:
    cd packages/{{package}} && uv run mypy .

# Run mypy for all packages
mypy-all:
    #!/usr/bin/env bash
    set -e
    for pkg in ap-core ap-codegen ap-frontend ap-storage ap-audit ap-ui ap-pdf ap-server-choices ap-ordered-model; do
        echo "Type checking $pkg..."
        cd packages/$pkg && uv run mypy .
        cd ../..
    done

# Run ruff linter
lint:
    uv run ruff check

# Run ruff formatter
format:
    uv run ruff format

# Check ruff formatting without making changes
format-check:
    uv run ruff format --check

# Run specific package's manage.py command
manage package *args:
    cd packages/{{package}} && uv run ./manage.py {{args}}

# Build docs and watch for changes
docs-watch:
    ./scripts/build-docs.sh

# Clean build artifacts
clean:
    rm -rf build_artifacts/
    rm -rf .venv/
    find . -type d -name "__pycache__" -exec rm -rf {} +
    find . -type d -name "*.egg-info" -exec rm -rf {} +

# Run full test suite with tox
tox *args:
    uvx --with tox-uv tox {{args}}

# List all available recipes
list:
    @just --list
