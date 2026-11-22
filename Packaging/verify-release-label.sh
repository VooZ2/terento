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

# AppStore (owner 2026-11-22): a build that can reach App Store Connect never
# carries an empty, "development" or -local label, because every -local build
# honours the bundled-catalog switch, TERENTO_DEBUG_UNPAUSE_PROVIDERS and
# ?preview=. Such a build is an archive (ACTION=install) or one signed with a
# real identity. The ad-hoc signed (CODE_SIGN_IDENTITY=-) local test build of
# this configuration keeps its -local label: App Store Connect refuses ad-hoc
# signed apps. An empty or "development" label is refused in every AppStore build.
if [ "${CONFIGURATION:-}" = "AppStore" ]; then
    release_label="${TERENTO_RELEASE_LABEL:-}"
    case "$release_label" in
        ""|development)
            echo "error: App Store builds require a public Terento release label" >&2
            exit 1
            ;;
        *-local*)
            if [ "${ACTION:-}" = "install" ] || [ "${CODE_SIGN_IDENTITY:-}" != "-" ]; then
                echo "error: an App Store archive or signed App Store build must not carry a -local release label" >&2
                exit 1
            fi
            ;;
    esac
fi
