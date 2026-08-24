# Terento v1.0.0-beta.2

Release date: 2026-08-24

This is a pre-MVP beta release for the Terento macOS application. It is
intended for development and hardware validation; it is not a stable
production release. Apple Silicon users can download the notarized ZIP or DMG
from the GitHub release assets.

## Included

- guarded Garmin smartwatch discovery, compatibility evaluation, map
  inventory, source acquisition, installation, backup, removal, and safe
  update foundations;
- local manifest-backed ownership and fail-closed protection for unknown and
  Garmin-owned device files;
- metadata-only Freizeitkarte catalog and Garmin device catalog services;
- serialized MTP lifecycle handling and disconnect-safe map lifecycle UI;
- a native macOS application target with bundled arm64 libmtp/libusb runtime;
- catalog-driven Freizeitkarte installation for one or several selected maps,
  including split-header composite-region identity handling, fresh
  device-backed inventory on Install/Manage navigation, and bounded Finishing
  progress;
- beta installation failures now save local operation diagnostics to
  `~/Library/Logs/Terento/log.txt`, including the selected preflight map and
  latest scanned Freizeitkarte objects, with a `Show log.txt` action on the
  failure screen;
- an About page with app version, update placeholder, support links, and local
  privacy statement;
- the public Terento landing page with English, German, French, Polish, Czech,
  and Italian indexable versions, translated metadata, reciprocal `hreflang`,
  sitemap entries, and a local language preference; and
- production deployment of the multilingual public landing page at
  `https://terento.app`.

## Validation status

- Full automated Stage 2–7 validation and Swift/Xcode Release builds pass.
- The application is Developer ID signed, notarized, stapled, Gatekeeper
  validated, and distributed as arm64 ZIP and DMG assets containing one
  `Terento.app`.
- The harmless write/read/delete roundtrip has passed on one validated Garmin
  smartwatch profile, including after reconnect.
- Read-only backup and safe-delete hardware gates have passed for the tested
  device and exact Terento-owned map.
- Safe Update is implemented and covered by automated tests, but its physical
  real-device update gate remains pending a genuinely newer Freizeitkarte
  release.

## Known limitations

- This beta does not claim universal Garmin smartwatch support. Hardware
  evidence is specific to one tested Garmin smartwatch profile and
  connectivity path.
- The complete first real-product success condition is not declared passed
  until the end-to-end install/update flow is repeated and verified on real
  hardware without changing non-Terento files.
- Freizeitkarte remains the only supported map provider in this phase.
- The catalog contains metadata only; Terento does not host or mirror map
  binaries.
- No PKG, App Store package, or universal Intel/Apple Silicon binary is
  included in this beta.

## Privacy and safety

No account, login, cloud device profile, server-side Garmin Unit ID storage, or
required email is introduced by this checkpoint. Device manifests remain local
to the Mac. Terento modifies only files it can prove it owns and prefers a
safe failure over destructive guessing.
