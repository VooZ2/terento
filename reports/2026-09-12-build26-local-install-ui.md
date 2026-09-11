# Build26-local — Install maps UI responsiveness

Date:2026-09-12. Follow-up to build25-local commitd750e1e on
terento/usb-recovery-build23-local. Owner explicitly required install/remove
logic unchanged and prohibited restarting the active France installation.

## Diagnosis

Read-only5-second process sample of running build25, PID7763:
/private/tmp/terento-install-ui-sample.txt.362 of420 sampled main-thread stacks
were under ConnectScreen.body line258 -> mapSelectionItems -> full catalog row
construction. Each body evaluation supplied a freshly computed array to onChange;
MapEngine.mapSelectionItems reevaluated preflight for every comparison and rebuilt
normalized presentation rows. Provider filtering, search and row selection checks
also repeatedly requested that computed array. Search/menu/scroll share the main
thread, explaining the owner-visible interaction stalls. These sample counts
are profiling evidence, not an end-to-end latency benchmark.

## UI-only correction

ConnectScreen stores its presentation rows and filtered lists in View State.
Initial appearance and changed MapEngine.result rebuild catalog rows. Provider
changes rebuild provider/available lists; search changes filter the existing rows.
Rendering and per-row display checks no longer rebuild all preflight statuses.
The existing selection validation still runs when the presentation items change.
Storage/Continue enabled-state displays refresh their plan on inventory, selection,
optional-artifact and custom-import readiness changes. Continue's action still
calls the original currentInstallationPlan getter for a fresh authoritative plan.

Only ConnectScreen.swift runtime source changes relative to build25. MapEngine,
selection policy/planner, install/remove coordinators, USB/C bridge, native patches,
verification, safety boundaries, resources and public release metadata unchanged.
No architecture ADR is needed for this UI-only projection lifetime correction.

## Evidence / gate

PASS: Xcode Debug arm64 build26;36 existing map-selection tests; provider/search
control contract; git diff --check. No claim of a measured post-fix interaction
latency or live GUI acceptance. Initially prepared separately without restarting
the ongoing build25 France test; see the subsequent status below.
Public22 and /Applications unchanged.

Owner-reported build25 MapRando Andorra installation PASS was received before
this task. Owner subsequently reported France installation PASS on build25.

## Local artifact

ZIP:dist/Terento-1.0.0-beta.11-local-build26-macOS-arm64.zip
SHA256:5578a5e4172902b7e5bb98a7065b1da58e3886a27c1a5869ab8e6713158ca94f
Extracted bundle signature, local label/build26, arm64 and no Homebrew runtime
paths verified. Prepared only; active build25 was neither stopped nor replaced.

## Follow-up after France PASS — 2026-09-12

Owner reported France install PASS. Build26 was then launched and the old build25
process was closed. Build26 currently shows Waiting for your Garmin, with Install
and Manage maps disabled during discovery. Live search/provider/scroll validation
remains pending a ready device/catalog. No install/remove action was performed.
