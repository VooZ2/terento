# Terento v1.0.0-beta.8

Release date: 2026-09-01

Beta.8 expands Terento into a provider-neutral Garmin map manager. It adds
OpenTopoMap main maps alongside Freizeitkarte, imports compatible local Garmin
`.img` maps from the Mac, and lets users remove one recognized third-party map
at a time after explicit confirmation.

This remains a pre-MVP beta for hardware validation. Model eligibility is not
a claim that every exact watch has been independently verified.

## Highlights

- Choose Freizeitkarte or OpenTopoMap from one provider-neutral catalog.
- Install one or several maps from the same provider in one operation.
- Import a compatible raw Garmin `.img` map from the Mac through the same
  validation, storage, transfer and verification lifecycle.
- Manage Terento-installed maps and remove one recognized external map at a
  time with an explicit safety confirmation.
- View provider health-aware errors when a map source is temporarily down.
- Optionally share anonymous map download and installation outcomes through a
  separate, off-by-default statistics control.

## Application updates

- Provider, package and local-import maps now use one common lifecycle:
  prepare, validate, storage check, transfer, verify, manifest and rescan.
- OpenTopoMap package identity and release headers are normalized without
  weakening provider, region or release validation.
- Sequential multi-map transfers include a bounded device-settle boundary for
  Garmin firmware that needs time to commit its MTP object database.
- Install, success, failure, confirmation and Manage maps screens received a
  consistent beta.8 visual and accessibility pass.
- About reports `1.0.0-beta.8` and distributed build `8`.

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

- The full native shell regression matrix and Swift CI pass on the final beta.8
  source, including provider-neutral acquisition, destructive-operation safety,
  privacy boundaries, bundled libraries and runtime paths.
- Owner hardware evidence on a Garmin fēnix 8 (47 mm AMOLED) confirms two-map
  Freizeitkarte and two-map OpenTopoMap operations, watch visibility, Manage
  maps discovery, persistence after reconnect and isolated one-map removal.
- Custom `.img` installation and subsequent managed removal were also confirmed
  on the same test watch.

## Known limitations

- Map-capable means eligible for a guarded beta attempt, not independently
  verified compatibility.
- A single installation batch can contain maps from only one provider.
- OpenTopoMap contour-package selection is deferred to a later beta.
- macOS 13 or later on Apple Silicon is required. Intel Macs, App Store, PKG,
  Windows and Linux distributions are not included.

## Release artifacts

The release pipeline must complete Apple notarization, stapling, Gatekeeper
assessment and launch verification before artifact hashes are recorded here.
