# Terento v0.1.0-beta.1

Release date: 2026-08-23

This is a pre-MVP beta checkpoint for the Terento macOS proof of concept. It
is intended to make the current implementation reproducible for development
and hardware validation; it is not a stable production release and does not
include a notarized DMG or PKG.

## Included

- guarded Garmin smartwatch discovery, compatibility evaluation, map
  inventory, source acquisition, installation, backup, removal, and safe
  update foundations;
- local manifest-backed ownership and fail-closed protection for unknown and
  Garmin-owned device files;
- metadata-only Freizeitkarte catalog and Garmin device catalog services;
- serialized MTP lifecycle handling and disconnect-safe map lifecycle UI;
- the public Terento landing page with English, German, French, Polish, Czech,
  and Italian indexable versions, translated metadata, reciprocal `hreflang`,
  sitemap entries, and a local language preference; and
- production deployment of the multilingual public landing page at
  `https://terento.app`.

## Validation status

- Automated Stage 2–5 validation and Swift build are the release validation
  baseline.
- The harmless write/read/delete roundtrip has passed on the validated Garmin
  fēnix 8 profile, including after reconnect.
- Read-only backup and safe-delete hardware gates have passed for the tested
  device and exact Terento-owned map.
- Safe Update is implemented and covered by automated tests, but its physical
  real-device update gate remains pending a genuinely newer Freizeitkarte
  release.

## Known limitations

- This beta does not claim universal Garmin smartwatch support. Hardware
  evidence is specific to the tested fēnix 8 profile and connectivity path.
- The complete first real-product success condition is not declared passed
  until the end-to-end install/update flow is repeated and verified on real
  hardware without changing non-Terento files.
- Freizeitkarte remains the only supported map provider in this phase.
- The catalog contains metadata only; Terento does not host or mirror map
  binaries.
- The macOS app is a development proof of concept. Distribution, notarization,
  and App Store packaging are outside this checkpoint.

## Privacy and safety

No account, login, cloud device profile, server-side Garmin Unit ID storage, or
required email is introduced by this checkpoint. Device manifests remain local
to the Mac. Terento modifies only files it can prove it owns and prefers a
safe failure over destructive guessing.
