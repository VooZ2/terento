# Catalog UI polish — local implementation

Branch: `terento/catalog-ui-polish`, based on `origin/beta` at `e092cb2`.
This is a local UI change, not a new public release or provider activation.

## Changes

- Stable 1180×820 pt default content size, 920×600 pt minimum; one-time growth
  preserves larger restored frames and clamps the title bar/frame to the screen.
- Country/region search, geography and provider menus, actual filtered count,
  stable provider/name ordering, preserved selections and contextual hidden-selection
  disclosure. Small windows wrap the toolbar; expanded import content can scroll.
- One immutable geography index per catalog snapshot. Keystrokes and filters do
  not rebuild device preflight or the installation plan. Continue still requests
  its authoritative current plan. Installed matches retain search-only visibility.
- Custom import stays separate. Ready uses actual component-row height up to three
  rows; progress stages size to their content. Confirmation metadata comes from
  the exact pending inventory ID. Failed-install rows have an explicit warning icon.
- About is consolidated under Terento → About Terento; all support, privacy/legal,
  diagnostics and update-state content remains available in a compact scrollable
  window. Sidebar has Device, Install maps, Manage maps.
- Existing colors, typography, logo, native controls and three-step flow retained.

## Boundaries

No DeviceEngine, MapEngine, lifecycle ViewModel, ownership, transport, provider
identity/acquisition policy, update controller, resources, release metadata or
backend changes. No device write/remove/update operations were run for this task.
BBBike remains unenabled; four-provider datasets are synthetic test fixtures.
Provider release labels preserve their original meanings; no guessed conversion
between a provider edition and a calendar release date was introduced.

Search covers official catalog countries/regions and geographic aliases. There
is no city/POI database or city expansion. Provider-defined administrative regions
(e.g. municipalities that are official region packages) remain searchable as
regions; valid catalog packages are not discarded by a city-name blacklist.

## Verification

- Release app build: PASS (bundled native runtime, signing disabled for local check).
- Optimized Debug local-label app build: PASS.
- Navigation/window: 15 behavioral cases + static checks PASS, including restored
  frame growth, screen clamping, negative-origin monitor and larger-frame retention.
- Full CI app entrypoint `Tests/run-app-tests.sh`: 24/24 runners PASS after
  updating the root About/readiness contracts for the consolidated window.
- Map selection: 39 behavioral cases PASS, including all 240 distinct bundled packages having
  a geography group, aliases, Crimea, overseas/transcontinental regions, installed
  matches, stable ties, and negative provider/style/raw-ID searches.
- Four-provider optimized filtering, 500/1000/2000 rows: final p95 0.693/1.311/2.617 ms
  (target ≤16 ms). These are filter measurements, not end-to-end UI latency.
- Lifecycle ViewModel 3, installation safety 39, safe-delete 19 and safe-update 10
  behavior cases PASS. Forbidden-operation guards PASS.
- Independent diff review found no changes to install/remove callbacks or their
  disabled/authorization conditions. Exact pending item ID still determines removal.

## Visual acceptance still pending

The prior build26 live audit informed the change; its successful small-map cycle
is baseline evidence only, not evidence for this modified UI. Switching the
owner's currently running app awaits confirmation that no operation is active.
Do not mark this work ready to merge until the new build is visually compared:

- default, minimum and larger windows; all three main destinations and About;
- search/provider/geography intersections, duplicate region names and empty states;
- selection retained across filters, Show selected scroll, review and Back;
- custom import collapsed/expanded and reachable file controls at minimum height;
- actual end-to-visible latency target p95≤100 ms, keyboard and full VoiceOver;
- progress, partial/error and success presentation using safe fixtures or an
  independently authorized operation (never start a device write solely for polish).

Canonical local docs reviewed: ARCHITECTURE.md, PLAN.md and PROJECT_STATE.md.
They are intentionally excluded from the public repository; this tracked receipt
and the module README carry the public implementation/validation description.
No ADR is needed: transport, ownership and installation boundaries are unchanged.
