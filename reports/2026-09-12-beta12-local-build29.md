# beta.12-local build29 — owner UI feedback

Owner reviewed build28 and supplied a Ready screenshot. The requested follow-up
keeps the accepted visual direction and changes only these presentation details:

- Ready Storage is anchored immediately above Back/Install, using the same
  summary component and32pt summary/action gap as Install maps. Repeated safety
  and diagnostics paragraphs are removed from Ready; privacy remains in About
  and Diagnostics. Insufficient-space and other blocking reasons remain visible.
- About and Diagnostics center on their active display at opening/reopening.
  Refocusing an already-visible window retains its manually chosen position.
- Manage maps adds pinned search/provider controls and actual result count.
  Existing provider/imported/external grouping and exact lifecycle items remain.
  Filters project a cached inventory and never request a device scan or preflight.
  Unknown/imported maps remain in All; geography is not inferred for those files,
  so Manage intentionally has search/provider without a continent menu.

The existing installed map display labels and recognized geographic codes are
searchable; custom maps retain their user-chosen display-name search. Provider,
version, style and file-extension metadata are excluded from geographic search.

## Verification

- Xcode Release and optimized Debug beta.12-local/build29 PASS.
- Full CI app entrypoint:24/24 runners PASS (31.4s).
- Lifecycle presentation:80 assertions PASS, including new inventory-filter cases.
- Navigation/window:18 assertions PASS, including multi-display centering.
- Map selection:39 behavior tests and static read-only guards PASS.
- Independent diff review: install/remove callbacks, exact confirmation targets,
  ownership and capability/availability guards unchanged. No device/MapEngine/
  lifecycle/controller behavior changes. Project file adds only source references.
- Git diff --check PASS.

## Local artifact

ZIP:dist/Terento-1.0.0-beta.12-local-build29-macOS-arm64.zip.
App:dist/beta.12-local-build29/Terento.app.
SHA256:f534a188c160f0f3cef5724dcb4a462d2d746315137c82a20ee328bcb5585dd3.
Built from this PR's follow-up working tree with CLI-only label/build overrides.
Ad-hoc signed for local testing, not notarized or publicly released. Fresh ZIP
extraction, deep strict signature, build29/local label, arm64 and bundled runtime
paths verified. Public beta.11/build27 metadata remains unchanged.

No app was stopped/launched and no device operation was performed. Owner testing
of build29 should check Storage position at minimum/default sizes, initial/open-
close/reopen Diagnostics positioning, and Manage filtering/clear behavior. Runtime
visual and VoiceOver acceptance of these follow-up changes remains unverified;
geometry/model tests are not a substitute for that check. PR173 remains draft.
