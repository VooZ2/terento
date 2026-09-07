#!/bin/sh
set -eu

# Local test launchers and ordinary Debug builds must remain segregated even
# when an operator overrides Xcode settings at the command line.
if [ "${CONFIGURATION:-}" = "Debug" ]; then
    case "${TERENTO_RELEASE_LABEL:-}" in
        *-local) ;;
        *)
            echo "error: Debug test builds require a Terento release label ending in -local" >&2
            exit 1
            ;;
    esac
fi

# Debug builds intentionally carry a purgeable local label. A public Xcode
# Release build must never be able to emit that identity, because the backend
# classifies the exact -local family as purgeable test telemetry.
if [ "${CONFIGURATION:-}" = "Release" ]; then
    release_label="${TERENTO_RELEASE_LABEL:-}"
    case "$release_label" in
        ""|development|*-local*)
            echo "error: public Release builds require a non-local Terento release label" >&2
            exit 1
            ;;
    esac
fi
