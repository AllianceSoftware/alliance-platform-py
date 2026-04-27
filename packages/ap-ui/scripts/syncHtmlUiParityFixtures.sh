#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
AP_UI_DIR="$(cd -- "${SCRIPT_DIR}/.." >/dev/null 2>&1 && pwd)"
PY_REPO_ROOT="$(cd -- "${AP_UI_DIR}/../.." >/dev/null 2>&1 && pwd)"

DEFAULT_JS_REPO="${PY_REPO_ROOT}/../alliance-platform-js"
JS_REPO="${ALLIANCE_PLATFORM_JS_DIR:-${DEFAULT_JS_REPO}}"
COMPONENT=""

usage() {
    cat <<'EOF'
Usage: syncHtmlUiParityFixtures.sh [--js-repo <path>] [--component <name>]

Regenerates ap-ui HTML parity fixtures using the JS workspace runtime.

Options:
  --js-repo <path>   Path to alliance-platform-js (default: ../alliance-platform-js)
  --component <name> Generate only one component fixture (for example "button")
  -h, --help         Show this help
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
    --js-repo)
        if [[ $# -lt 2 ]]; then
            echo "Missing value for --js-repo" >&2
            usage >&2
            exit 1
        fi
        JS_REPO="$2"
        shift 2
        ;;
    --component)
        if [[ $# -lt 2 ]]; then
            echo "Missing value for --component" >&2
            usage >&2
            exit 1
        fi
        COMPONENT="$2"
        shift 2
        ;;
    -h | --help)
        usage
        exit 0
        ;;
    *)
        echo "Unknown argument: $1" >&2
        usage >&2
        exit 1
        ;;
    esac
done

if [[ ! -d "${JS_REPO}" ]]; then
    echo "alliance-platform-js directory not found: ${JS_REPO}" >&2
    exit 1
fi
JS_REPO="$(cd -- "${JS_REPO}" >/dev/null 2>&1 && pwd)"

UI_PACKAGE_DIR="${JS_REPO}/packages/ui"
if [[ ! -d "${UI_PACKAGE_DIR}" ]]; then
    echo "Expected UI package directory not found: ${UI_PACKAGE_DIR}" >&2
    exit 1
fi

VITE_NODE_BIN="${JS_REPO}/node_modules/.bin/vite-node"
if [[ ! -x "${VITE_NODE_BIN}" ]]; then
    cat >&2 <<EOF
Missing vite-node at ${VITE_NODE_BIN}.
Install JS dependencies first:
  cd ${JS_REPO}
  yarn install
EOF
    exit 1
fi

GENERATOR_SCRIPT="${SCRIPT_DIR}/generateHtmlUiParityFixtures.mjs"
VITE_CONFIG="${UI_PACKAGE_DIR}/vite.config.mjs"

COMMAND=("${VITE_NODE_BIN}" --config "${VITE_CONFIG}" "${GENERATOR_SCRIPT}")
if [[ -n "${COMPONENT}" ]]; then
    COMMAND+=("${COMPONENT}")
fi

(
    cd "${UI_PACKAGE_DIR}"
    AP_UI_JS_REPO="${JS_REPO}" \
        AP_UI_UI_PACKAGE_DIR="${UI_PACKAGE_DIR}" \
        "${COMMAND[@]}"
)
