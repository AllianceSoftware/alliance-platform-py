#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

SKILL_SOURCE_DIR="${SKILL_SOURCE_DIR:-$REPO_ROOT/skills/alliance-platform-docs}"
SKILL_SLUG="${SKILL_SLUG:-alliance-platform-py-docs}"
SITE_ROOT_DEFAULT="${READTHEDOCS_OUTPUT:-$REPO_ROOT/_docs-build/site}/html"
SITE_ROOT="${SITE_ROOT:-$SITE_ROOT_DEFAULT}"
PUBLISH_DIR="$SITE_ROOT/.well-known/skills/$SKILL_SLUG"

"$REPO_ROOT/scripts/build-skill-docs.sh"

echo "Publishing skill to $PUBLISH_DIR"
rm -rf "$PUBLISH_DIR"
mkdir -p "$PUBLISH_DIR"

cp "$SKILL_SOURCE_DIR/SKILL.md" "$PUBLISH_DIR/SKILL.md"
cp -R "$SKILL_SOURCE_DIR/references" "$PUBLISH_DIR/references"

echo "Done."
