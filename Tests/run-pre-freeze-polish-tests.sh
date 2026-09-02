#!/bin/zsh
set -euo pipefail

repo_root="${0:A:h:h}"
connect_screen="$repo_root/lab/native-connectivity-poc/Sources/TerentoPoC/Views/ConnectScreen.swift"
evidence="$repo_root/lab/native-connectivity-poc/Sources/TerentoPoC/Compatibility/InstallationEvidence.swift"
diagnostics="$repo_root/lab/native-connectivity-poc/Sources/TerentoPoC/Diagnostics/TerentoDiagnosticLog.swift"
about="$repo_root/lab/native-connectivity-poc/Sources/TerentoPoC/Views/AboutTerentoView.swift"
download="$repo_root/lab/native-connectivity-poc/Sources/TerentoPoC/MapCatalog/MapPackageAcquisition.swift"
engine="$repo_root/lab/native-connectivity-poc/Sources/TerentoPoC/MapCatalog/MapEngine.swift"

if grep -Fq 'Enough space remains after installation.' "$connect_screen"; then
    print -u2 "FAIL: allowed storage still shows a success warning"
    exit 1
fi

if ! grep -Fq 'return "Not enough space available. Remove a map or select fewer maps."' "$connect_screen"; then
    print -u2 "FAIL: insufficient-storage warning is missing"
    exit 1
fi

if grep -Fq 'shareCompatibilityEvidence' "$connect_screen" \
    || ! grep -Fq 'get: { evidenceController.compatibilitySharingEnabled }' "$connect_screen" \
    || ! grep -Fq 'evidenceController.commitCurrentSharingChoice()' "$connect_screen"; then
    print -u2 "FAIL: Ready/About/reporting do not share one persisted preference"
    exit 1
fi

if ! grep -Fq 'Text("Help improve Garmin compatibility")' "$connect_screen" \
    || ! grep -Fq 'Share anonymous installation results to help improve Garmin compatibility.' "$connect_screen" \
    || grep -Fq 'Selected by default;' "$connect_screen"; then
    print -u2 "FAIL: Ready compatibility-sharing copy is not concise"
    exit 1
fi

if ! grep -Fq 'Compatibility reports are up to date.' "$connect_screen" \
    || ! grep -Fq 'Terento will retry automatically.' "$connect_screen" \
    || grep -Fq 'Compatibility report was not sent because sharing was turned off.' "$connect_screen" \
    || grep -Fq 'Reason: \(reason\)' "$connect_screen" \
    || grep -Fq 'Last upload response:' "$connect_screen"; then
    print -u2 "FAIL: completion delivery messages expose the wrong state or raw details"
    exit 1
fi

if ! grep -Fq 'Open-source macOS app for installing and managing third-party maps on compatible Garmin smartwatches.' "$about"; then
    print -u2 "FAIL: About description still exposes internal map-origin wording"
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
