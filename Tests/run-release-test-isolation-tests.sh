#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
PYTHONDONTWRITEBYTECODE=1 python3 Tests/release-test-isolation-tests.py
# The bundled-catalog checks import the backend catalog policy, which needs the
# backend's Python 3.12/3.13, not the system python3 (3.9 on macOS).
. Tests/backend-python-runtime.sh
PYTHONDONTWRITEBYTECODE=1 "$TERENTO_PYTHON_BIN" Tests/bundled-map-catalog-tests.py
