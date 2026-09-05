#!/bin/zsh
set -euo pipefail

repo_root="${0:A:h:h}"
connect_screen="$repo_root/app/TerentoCore/Sources/TerentoPoC/Views/ConnectScreen.swift"
evidence="$repo_root/app/TerentoCore/Sources/TerentoPoC/Compatibility/InstallationEvidence.swift"
diagnostics="$repo_root/app/TerentoCore/Sources/TerentoPoC/Diagnostics/TerentoDiagnosticLog.swift"
about="$repo_root/app/TerentoCore/Sources/TerentoPoC/Views/AboutTerentoView.swift"
download="$repo_root/app/TerentoCore/Sources/TerentoPoC/MapCatalog/MapPackageAcquisition.swift"
engine="$repo_root/app/TerentoCore/Sources/TerentoPoC/MapCatalog/MapEngine.swift"

if grep -Fq 'Enough space remains after installation.' "$connect_screen"; then
    print -u2 "FAIL: allowed storage still shows a success warning"
    exit 1
fi

if ! grep -Fq 'return "Not enough space available. Remove a map or select fewer maps."' "$connect_screen"; then
    print -u2 "FAIL: insufficient-storage warning is missing"
    exit 1
fi

if grep -Fq 'compatibilitySharingBinding' "$connect_screen" \
    || grep -Fq 'mapStatisticsSharingBinding' "$connect_screen" \
    || grep -Fq 'commitCurrentSharingChoice' "$connect_screen"; then
    print -u2 "FAIL: Ready still owns a diagnostics preference or consent commit"
    exit 1
fi

if ! grep -Fq 'Terento sends privacy-minimised diagnostics by default to help improve the app and its services. You can turn this off anytime in Terento → Diagnostics.' "$connect_screen" \
    || grep -Fq 'Help improve Garmin compatibility' "$connect_screen" \
    || grep -Fq 'Share anonymous map statistics' "$connect_screen"; then
    print -u2 "FAIL: Ready diagnostics disclosure is missing or still exposes old copy"
    exit 1
fi

if grep -Fq 'Compatibility reports are up to date.' "$connect_screen" \
    || grep -Fq 'Terento will retry automatically.' "$connect_screen" \
    || grep -Fq 'Compatibility report was not sent because sharing was turned off.' "$connect_screen" \
    || grep -Fq 'Reason: \(reason\)' "$connect_screen" \
    || grep -Fq 'Last upload response:' "$connect_screen"; then
    print -u2 "FAIL: completion delivery messages expose the wrong state or raw details"
    exit 1
fi

if ! grep -Fq 'Install maps on Garmin watches, simply.' "$connect_screen" \
    || grep -Fq 'TerentoAppMetadata.description' "$connect_screen" \
    || grep -Fq 'TerentoAppMetadata.description' "$about"; then
    print -u2 "FAIL: About does not use the concise installation tagline"
    exit 1
fi

for field in 'Failure category:' 'HTTP status:' 'Backend payload:' 'Schema version:' 'Local report IDs:'; do
    if ! grep -Fq "$field" "$diagnostics"; then
        print -u2 "FAIL: diagnostics do not record $field"
        exit 1
    fi
done

if ! grep -Fq 'var compatibilitySharingEnabled: Bool' "$evidence" \
    || ! grep -Fq 'currentConsentChoice != .declined' "$evidence" \
    || ! grep -Fq 'TerentoDiagnosticLog.recordCompatibilityReportDeliveryFailure' "$evidence"; then
    print -u2 "FAIL: evidence controller does not own persisted consent and diagnostics"
    exit 1
fi

if grep -Fq 'let startedAt = Date()' "$download" \
    || grep -Fq 'lastInstallationProgressAt' "$engine" \
    || ! grep -Fq 'TransferSpeedEstimator' "$download" \
    || ! grep -Fq 'TransferSpeedEstimator' "$engine"; then
    print -u2 "FAIL: transfer speed still uses burst-prone wall-clock calculation"
    exit 1
fi

print "PASS: pre-freeze storage, consent, reporting, diagnostics, About, and speed checks"
