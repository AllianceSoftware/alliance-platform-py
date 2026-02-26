# Justfile for alliance-platform-py development tasks

# Install dependencies
install:
    uv sync --all-groups

# Run tests for specific package
# Usage: just test-package ap-pdf [python-version] [django-constraint]
# Examples:
#   just test-package ap-pdf              # default Python, no constraint
#   just test-package ap-pdf 3.12         # Python 3.12, no constraint
#   just test-package ap-pdf 3.12 django42  # Python 3.12 with Django 4.2
test-package package python="" constraint="":
    #!/usr/bin/env bash
    set -euo pipefail

    PKG="{{package}}"
    PY="{{python}}"
    CONSTRAINT="{{constraint}}"

    # Colors
    BOLD='\033[1m'
    GREEN='\033[32m'
    BLUE='\033[34m'
    RESET='\033[0m'

    # Set environment variables
    export UV_NO_SYNC=1
    if [[ -n "$PY" ]]; then
        export UV_PYTHON="$PY"
    fi
    if [[ -n "$CONSTRAINT" ]]; then
        export UV_CONSTRAINT="constraints/${CONSTRAINT}.txt"
        echo -e "${BLUE}Using constraint: $UV_CONSTRAINT${RESET}"
    fi

    echo -e "${BOLD}${GREEN}Testing $PKG${RESET}"

    PACKAGE_NAME="alliance-platform-${PKG#ap-}"

    # Recreate venv for correct Python version if needed
    if [[ ! -d .venv ]] || [[ -n "$PY" ]]; then
        echo "Creating virtual environment..."
        rm -rf .venv
        uv venv >/dev/null
    fi

    # Install package and dependencies (including dev group)
    echo "Installing dependencies..."
    if [[ -n "$CONSTRAINT" ]]; then
        # Use override to replace Django version while preserving dev dependencies
        uv export --no-hashes --package "$PACKAGE_NAME" | UV_OVERRIDE="constraints/${CONSTRAINT}.txt" uv pip install -r - >/dev/null 2>&1
    else
        uv export --no-hashes --package "$PACKAGE_NAME" | uv pip install -r - >/dev/null 2>&1
    fi

    # Run tests
    cd "packages/$PKG" && uv run ./manage.py test

# Run tests for all packages
# Usage: just test-all [python-version] [django-constraint]
# Examples:
#   just test-all              # default Python, no constraint
#   just test-all 3.12         # Python 3.12, no constraint
#   just test-all 3.12 django42  # Python 3.12 with Django 4.2
test-all python="" constraint="":
    #!/usr/bin/env bash
    set -e

    PY="{{python}}"
    CONSTRAINT="{{constraint}}"

    # Colors
    BOLD='\033[1m'
    GREEN='\033[32m'
    BLUE='\033[34m'
    RED='\033[31m'
    YELLOW='\033[33m'
    RESET='\033[0m'

    # Set environment variables
    export UV_NO_SYNC=1
    if [[ -n "$PY" ]]; then
        export UV_PYTHON="$PY"
        echo -e "${BLUE}Using Python: $PY${RESET}"
    fi
    if [[ -n "$CONSTRAINT" ]]; then
        export UV_CONSTRAINT="constraints/${CONSTRAINT}.txt"
        echo -e "${BLUE}Using constraint: $UV_CONSTRAINT${RESET}"
    fi

    echo ""

    # Recreate venv for correct Python version if needed
    if [[ ! -d .venv ]] || [[ -n "$PY" ]]; then
        echo -e "${YELLOW}Creating virtual environment...${RESET}"
        rm -rf .venv
        uv venv >/dev/null
        echo ""
    fi

    FAILED_PACKAGES=()
    PASSED_PACKAGES=()

    for pkg in ap-core ap-codegen ap-frontend ap-storage ap-audit ap-ui ap-pdf ap-server-choices ap-ordered-model; do
        echo -e "${BOLD}${GREEN}═══════════════════════════════════════════════════${RESET}"
        echo -e "${BOLD}${GREEN}Testing $pkg${RESET}"
        echo -e "${BOLD}${GREEN}═══════════════════════════════════════════════════${RESET}"

        PACKAGE_NAME="alliance-platform-${pkg#ap-}"

        # Install package and dependencies (including dev group)
        echo -e "${YELLOW}Installing dependencies...${RESET}"
        if [[ -n "$CONSTRAINT" ]]; then
            # Use override to replace Django version while preserving dev dependencies
            if ! uv export --no-hashes --package "$PACKAGE_NAME" | UV_OVERRIDE="constraints/${CONSTRAINT}.txt" uv pip install -r - >/dev/null 2>&1; then
                echo -e "${RED}✗ Failed to install $pkg${RESET}"
                FAILED_PACKAGES+=("$pkg")
                echo ""
                continue
            fi
        else
            if ! uv export --no-hashes --package "$PACKAGE_NAME" | uv pip install -r - >/dev/null 2>&1; then
                echo -e "${RED}✗ Failed to install $pkg${RESET}"
                FAILED_PACKAGES+=("$pkg")
                echo ""
                continue
            fi
        fi

        # Run tests
        if cd "packages/$pkg" && uv run ./manage.py test; then
            PASSED_PACKAGES+=("$pkg")
            echo -e "${GREEN}✓ $pkg tests passed${RESET}"
        else
            FAILED_PACKAGES+=("$pkg")
            echo -e "${RED}✗ $pkg tests failed${RESET}"
        fi
        cd ../..
        echo ""
    done

    # Summary
    echo -e "${BOLD}${GREEN}═══════════════════════════════════════════════════${RESET}"
    echo -e "${BOLD}Test Summary${RESET}"
    echo -e "${BOLD}${GREEN}═══════════════════════════════════════════════════${RESET}"
    echo -e "${GREEN}Passed: ${#PASSED_PACKAGES[@]}${RESET}"
    if [[ ${#PASSED_PACKAGES[@]} -gt 0 ]]; then
        for pkg in "${PASSED_PACKAGES[@]}"; do
            echo -e "  ${GREEN}✓${RESET} $pkg"
        done
    fi
    echo ""
    echo -e "${RED}Failed: ${#FAILED_PACKAGES[@]}${RESET}"
    if [[ ${#FAILED_PACKAGES[@]} -gt 0 ]]; then
        for pkg in "${FAILED_PACKAGES[@]}"; do
            echo -e "  ${RED}✗${RESET} $pkg"
        done
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

# Build docs as Markdown and sync into the Codex skill references directory
docs-build-skill:
    ./scripts/build-skill-docs.sh

# Clean build artifacts
clean:
    rm -rf build_artifacts/
    rm -rf .venv/
    find . -type d -name "__pycache__" -exec rm -rf {} +
    find . -type d -name "*.egg-info" -exec rm -rf {} +

# List all available recipes
list:
    @just --list
