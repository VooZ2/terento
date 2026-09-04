# Terento v1.0.0-beta.9

Release date: 2026-09-02
Maintenance build: 2026-09-04

Beta.9 build 11 addresses stalled installation finishing and diagnostics delivery.
Freizeitkarte and OpenTopoMap main-map packages remain the enabled providers.
The display version stays 1.0.0-beta.9; the distributed build is 11.

Because the original beta.9 GitHub release is immutable, this maintenance
build is published under `v1.0.0-beta.9-build11`. Terento still displays
`Version 1.0.0-beta.9 (11)`.

This is a public beta for hardware validation. The MVP first-install baseline
is established, but the beta remains open until one real safe update has passed
for each currently enabled provider. Model eligibility is not a claim that
every exact watch has been independently verified.

## Build 11 fixes

- Bound native sampled verification and exact cleanup with an isolated worker
  deadline. Stop the worker before continuing; never retry the map write.
- Read the same verification regions in smaller chunks and revalidate the
  exact target whenever a read-only session is reopened.
- Preserve failed-install recovery when cleanup cannot be confirmed. A partial
  or unverified map is never recorded as successfully installed.
- Restore schema-v4 compatibility event storage without deleting queued or
  uploaded reports, changing idempotency, or reopening the immutable API.
- Keep transfer progress tied to the validated source size, separately from
  sampled verification progress, in the UI and diagnostic reports.
- Make health/readiness fail when diagnostic storage migrations or the schema
  are incompatible, using read-only checks for both diagnostic streams.

## Fixes and safeguards

- Accept the reviewed OpenTopoMap `LTU` and `LITHUANIA` identity pair at the
  provider boundary, fixing the Lithuania failure reported in Issue #74.
- Keep all other provider and region comparisons exact; the fix does not
  weaken source validation, device ownership, or destructive-operation rules.
- Correct fixed-width Freizeitkarte IMG header parsing so a full region field
  cannot be joined with the following release field.
- Accept catalog health timestamps with or without fractional seconds across
  every supported macOS version instead of rejecting the complete live catalog.
- Reject an incompatible live catalog as a whole and use the bundled
  last-known-good snapshot instead of exposing only some broken maps.
- Validate the exact production catalog during release packaging, after API
  deployment, on release-tag/manual CI, and every day against the shipped
  client contract.
- Record the connected watch model for a successful custom `.img`
  installation in the default-on privacy-minimised compatibility report, using only
  the coarse `custom` source labels and never a hash-derived local identity.
- Keep custom `.img` installations out of map statistics; they appear in the
  dashboard as Custom installation activity through compatibility evidence.
- Send compatibility reports and map statistics by default, without an
  opt-in/opt-out choice in the installation flow. The only opt-out is in
  `Terento → Diagnostics`.
- Add one `Send diagnostics` action for queued reports. It is enabled only
  when reports are waiting, and uploaded reports cannot be deleted from the
  app.
- Refresh About with the direct `Update` and `Manage diagnostics` actions,
  Donate plus Privacy/Legal links, and add `Terento → Check updates`.

## Application updates

- About reports `1.0.0-beta.9` and distributed build `11`.
- Release and public Download metadata are generated from one manifest and
  checked for version, URL, date, and checksum drift.

## Safety and privacy

- Garmin-owned and unknown files remain read-only.
- External-map removal targets one exact recognized `.img` object and requires
  filename, path, size and hash checks plus a post-delete rescan.
- New installs never overwrite an existing target. Safe Update still follows
  write-new → verify → remove-old and never deletes the working map first.
- Device manifests and physical-watch ownership keys remain local. There is no
  account, login, cloud device profile or server-side Garmin identifier storage.
- Map statistics are independent from compatibility evidence, default-on,
  queued locally and non-blocking. They exclude watch identifiers, serial
  numbers, Unit IDs, file paths, manifests, binaries and diagnostic logs.
- Both diagnostics streams can be disabled later in `Terento → Diagnostics`;
  queued reports remain local until sent and there is no delete action for
  reports already uploaded.
- Custom `.img` imports use compatibility evidence only; they do not create
  map-statistics events.
- Maps download directly from the selected provider. Terento does not host,
  mirror, proxy or repackage provider binaries.

## Validation status

- All native safety and app regression suites pass, including generated
  identity checks for all 63 Freizeitkarte and 177 OpenTopoMap catalog rows.
- The exact current 219,494,190-byte OpenTopoMap Lithuania archive passes ZIP,
  artifact-size, production parser, release, and catalog identity validation.
- The complete catalog backend regression suite passes, and the exact live
  240-package catalog passes the beta.9 client contract. The test runner
  reports its current count automatically so release notes do not carry a
  number that can drift.
- The arm64 release build is Developer ID signed, notarized by Apple with no
  issues, stapled, Gatekeeper accepted, and launch-smoke verified from both the
  ZIP and DMG paths.
- Owner hardware verification on the beta.9 release candidate
  confirms OpenTopoMap Lithuania installation, map visibility on the fēnix 8,
  persistence after disconnect/reconnect, and discovery in Manage maps. The
  final rebuild changes only catalog timestamp decoding and diagnostics; its
  unchanged installation path passed the complete automated regression suite.

## Known limitations

- Map-capable means eligible for a guarded beta attempt, not independently
  verified compatibility.
- A single installation batch can contain maps from only one provider.
- OpenTopoMap contour-package selection is deferred to a later beta.
- macOS 13 or later on Apple Silicon is required. Intel Macs, PKG, Windows and
  Linux distributions are not included in this beta. App Store distribution is
  a long-term stable-release target, not a current beta or MVP dependency.

## Release artifacts

Build 10 was signed, notarized, stapled, and validated by the release
pipeline. Apple submission `be22894f-9a7a-44b5-bfff-55fe0ec3cece` was
accepted with no issues.

```text
Terento-1.0.0-beta.9-macOS-arm64.dmg  2f14858f494d1faa5fb27f24e833d714fe3eeb9e13a4664ab7eec3319aa5dd51
Terento-1.0.0-beta.9-macOS-arm64.zip  4a161c67997b6dbdca783bd6a8b9803ce4b0d2b8a8c3340a155ae78c2365d990
```
