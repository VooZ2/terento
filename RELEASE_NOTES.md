# Terento v1.0.0-beta.9

Release date: 2026-09-02

Beta.9 fixes OpenTopoMap Lithuania installation and hardens the boundary
between Terento releases and the independently changing live map catalog.
It keeps the beta.8 provider and device scope unchanged.

This remains a pre-MVP beta for hardware validation. Model eligibility is not
a claim that every exact watch has been independently verified.

## Fixes and safeguards

- Accept the reviewed OpenTopoMap `LTU` and `LITHUANIA` identity pair at the
  provider boundary, fixing the Lithuania failure reported in Issue #74.
- Keep all other provider and region comparisons exact; the fix does not
  weaken source validation, device ownership, or destructive-operation rules.
- Correct fixed-width Freizeitkarte IMG header parsing so a full region field
  cannot be joined with the following release field.
- Reject an incompatible live catalog as a whole and use the bundled
  last-known-good snapshot instead of exposing only some broken maps.
- Validate the exact production catalog during release packaging, after API
  deployment, on release-tag/manual CI, and every day against the shipped
  client contract.

## Application updates

- About reports `1.0.0-beta.9` and distributed build `9`.
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
- Map statistics are independent from compatibility evidence, optional, queued
  locally and non-blocking. They exclude watch identifiers, serial numbers,
  Unit IDs, file paths, manifests, binaries and diagnostic logs.
- Maps download directly from the selected provider. Terento does not host,
  mirror, proxy or repackage provider binaries.

## Validation status

- All 42 native test scripts pass, including generated identity checks for all
  63 Freizeitkarte and 177 OpenTopoMap catalog rows.
- The exact current 219,494,190-byte OpenTopoMap Lithuania archive passes ZIP,
  artifact-size, production parser, release, and catalog identity validation.
- The catalog backend suite passes 167 tests and the exact live 240-package
  catalog passes the beta.9 client contract.
- The arm64 release build is Developer ID signed, notarized by Apple with no
  issues, stapled, Gatekeeper accepted, and launch-smoke verified from both the
  ZIP and DMG paths.
- Existing beta.8 fēnix 8 lifecycle evidence remains valid, but a beta.9
  Lithuania install/reconnect/Manage maps smoke on real hardware is still
  required before public release.

## Known limitations

- Map-capable means eligible for a guarded beta attempt, not independently
  verified compatibility.
- A single installation batch can contain maps from only one provider.
- OpenTopoMap contour-package selection is deferred to a later beta.
- macOS 13 or later on Apple Silicon is required. Intel Macs, App Store, PKG,
  Windows and Linux distributions are not included.

## Release artifacts

Apple notarization submission `cb3749cf-61f4-4131-a6b9-83e240a616d3` was
accepted with no issues.

```text
Terento-1.0.0-beta.9-macOS-arm64.dmg  e348885f8ef73f8358f29761f8dde5b4fb541b8d6a2d06bc95be78eb2c514bed
Terento-1.0.0-beta.9-macOS-arm64.zip  0615d8e7708d92a2bb434539c12c5f27cd4e78dfdf5076b612f320ef5354a660
```
