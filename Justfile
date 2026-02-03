# Justfile for alliance-platform-py development tasks

# Install dependencies
install:
    uv sync

# Run tests for specific package
test-package package python="":
    #!/usr/bin/env bash
    set -euo pipefail

    PKG="{{package}}"
    PY="{{python}}"

    PACKAGE_NAME="alliance-platform-${PKG#ap-}"

    if [[ -n "$PY" ]]; then
        PY_ARG=(--python "$PY")
    else
        PY_ARG=()
    fi

    if ! uv sync --frozen --package "$PACKAGE_NAME" "${PY_ARG[@]}" >/dev/null 2>&1; then
        echo "uv sync failed (initial)" >&2
        exit 1
    fi

    cd "packages/{{package}}" && uv run "${PY_ARG[@]}" ./manage.py test
    # reset back to default venv setup
    if uv sync "${PY_ARG[@]}" >/dev/null 2>&1; then
        echo "venv reset"
    else
        echo "venv reset failed" >&2
        exit 1
    fi

# Run tests for all packages
test-all python="":
    #!/usr/bin/env bash
    set -e
    for pkg in ap-core ap-codegen ap-frontend ap-storage ap-audit ap-ui ap-pdf ap-server-choices ap-ordered-model; do
        echo "Testing $pkg..."

        PY="{{python}}"                                                                      
        PACKAGE_NAME="alliance-platform-${pkg#ap-}"                                          
                                                                                            
        if [[ -n "$PY" ]]; then                                                              
            PY_ARG=(--python "$PY")                                                          
        else                                                                                 
            PY_ARG=()                                                                        
        fi                                                                                   
                                                                                            
        if ! uv sync --frozen --package "$PACKAGE_NAME" "${PY_ARG[@]}" >/dev/null 2>&1; then 
            echo "uv sync failed (initial)" >&2                                              
        else                                                                                   
          cd packages/$pkg && uv run "${PY_ARG[@]}" ./manage.py test
        fi
        cd ../..
    done
    # reset back to default venv setup
    if uv sync "${PY_ARG[@]}" >/dev/null 2>&1; then
        echo "venv reset"
    else
        echo "venv reset failed" >&2
        exit 1
    fi


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

# List all available recipes
list:
    @just --list
