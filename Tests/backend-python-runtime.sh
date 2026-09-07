#!/bin/sh
set -eu

# Resolve the Python runtime used by the backend regression suite.  Backend
# tests require the package's declared test extra; do not silently fall back
# to Apple's/Xcode's often older system Python.

repo_root="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
backend_dir="$repo_root/backend/catalog-api"
local_venv="$repo_root/.venv"

python_is_supported() {
    candidate="$1"
    "$candidate" - <<'PY' >/dev/null 2>&1
import sys

raise SystemExit(0 if (3, 12) <= sys.version_info[:2] < (3, 14) else 1)
PY
}

resolve_command() {
    candidate="$1"
    case "$candidate" in
        /*|./*|../*)
            [ -x "$candidate" ] || return 1
            printf '%s\n' "$candidate"
            ;;
        *)
            command -v "$candidate" 2>/dev/null || return 1
            ;;
    esac
}

python_bin=""
if [ -n "${TERENTO_PYTHON_BIN:-}" ]; then
    python_bin="$(resolve_command "$TERENTO_PYTHON_BIN" || true)"
    if [ -z "$python_bin" ] || ! python_is_supported "$python_bin"; then
        echo "TERENTO_PYTHON_BIN must point to a usable Python 3.12 or 3.13 executable." >&2
        exit 1
    fi
elif [ -x "$local_venv/bin/python" ] && python_is_supported "$local_venv/bin/python"; then
    python_bin="$local_venv/bin/python"
else
    for candidate in python3.13 python3.12 python3; do
        resolved="$(resolve_command "$candidate" || true)"
        if [ -n "$resolved" ] && python_is_supported "$resolved"; then
            python_bin="$resolved"
            break
        fi
    done
fi

if [ -z "$python_bin" ]; then
    echo "Terento backend tests require Python 3.12 or 3.13." >&2
    echo "Install a supported Python or set TERENTO_PYTHON_BIN to its executable." >&2
    exit 1
fi

if ! "$python_bin" - <<'PY' >/dev/null 2>&1
import importlib.metadata

assert importlib.metadata.version("jsonschema") == "4.26.0"
PY
then
    if [ -n "${TERENTO_PYTHON_BIN:-}" ]; then
        echo "The selected Python is missing jsonschema==4.26.0." >&2
        echo "Install the backend test extra: python -m pip install -e 'backend/catalog-api[test]'" >&2
        exit 1
    fi

    # Keep automatic setup isolated from the system interpreter.  CI already
    # installs the extra globally; local runs use this ignored project venv
    # only when the selected interpreter does not have the test dependency.
    if [ ! -x "$local_venv/bin/python" ]; then
        "$python_bin" -m venv "$local_venv"
        python_bin="$local_venv/bin/python"
    fi
    "$python_bin" -m pip install --disable-pip-version-check -e "$backend_dir[test]"
fi

export TERENTO_PYTHON_BIN="$python_bin"
