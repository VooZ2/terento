# Terento

> Your device, ready for where you're going.

Terento is a free, open-source macOS application for installing and managing
community maps on supported Garmin smartwatches. It is in active beta
development and is designed around an outcome rather than a transfer process:

```text
Connect Garmin → detect device → choose map → install/manage → ready
```

Normal users should not need to understand MTP, IMG files, object IDs, or
Garmin filesystem details.

## Current scope

- macOS, with Apple Silicon as the primary development target
- modern Garmin smartwatches using the supported connectivity path
- direct community-map installation and management
- Freizeitkarte as the first and only map provider
- all catalog-listed Freizeitkarte regions are available in the local beta
  install flow; Latvia is the currently hardware-validated region and
  Lithuania is the next validation target

Physical development and testing has been performed with a Garmin fēnix 8.
That evidence is specific to the tested device and connectivity path; it is
not a claim of universal Garmin support.

## Current implementation

The current pre-MVP implementation includes:

- automatic device detection, device identity, and compatibility status;
- a metadata-only Freizeitkarte catalog;
- installed-map discovery and version comparison;
- a guarded map-installation workflow;
- verified backups and conservative removal of Terento-managed maps;
- storage checks, transfer verification, and local ownership state;
- device disconnect/reconnect handling and lifecycle UI; and
- device presentation assets with a neutral fallback when no asset is
  available.

Terento is conservative around device contents. Unknown or unrelated files are
not silently replaced or removed. Destructive lifecycle actions are limited to
maps Terento can prove it owns. Manual Remove uses live exact-object and
integrity checks without creating a local backup; Safe Update remains
backup-protected. Installation and update verification are part of the guarded
workflow.

Safe Update is implemented and covered by automated validation. The final
real-device update gate is pending a genuinely newer Freizeitkarte release.
The project has not marked Stage 5.3 hardware validation as passed.

## Development status

Terento is not a stable production release. The repository currently contains
the macOS application source, public web surfaces, and the metadata catalog
service. Stage 6 packaging validation has been performed locally, but no DMG
or PKG is committed or distributed by this repository. Generated release
outputs remain local under the ignored `dist/` directory.

The production app target and bundled native runtime are ready for local beta
validation. The local install flow supports one or several catalog-listed
Freizeitkarte maps sequentially on the tested fēnix 8 profile. Latvia is the
current hardware evidence; other regions are not yet public compatibility
claims. OpenTopoMap remains read-only and is not part of installation.

## Repository guide

- [`site/`](site/) — the public landing page and legal/SEO assets
- [`app/`](app/) — the macOS application shell, metadata, entitlements, and
  resources
- [`lab/native-connectivity-poc/`](lab/native-connectivity-poc/) — the current
  SwiftPM source module and tests consumed by the macOS application target;
  the historical `lab` name is retained for compatibility
- [`Packaging/`](Packaging/) — local release-build and signing/notarization
  preparation scripts; it does not contain release artifacts
- [`backend/catalog-api/`](backend/catalog-api/) — the metadata-only catalog
  service
- [`legal/`](legal/) — public legal web content and publication inputs
- [`PROJECT_STRUCTURE.md`](PROJECT_STRUCTURE.md) — what belongs in each
  project area and what stays local
- [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) — dependency and runtime
  notices
- [`VERSIONING.md`](VERSIONING.md) — public beta versioning policy
- [`RELEASE_NOTES.md`](RELEASE_NOTES.md) — current beta checkpoint scope and
  validation limitations

## Principles

- Prefer the simplest reliable path before adding native components.
- Keep map downloads on the user's Mac and use the original provider source.
- Keep device state and manifests local.
- Modify only files Terento can prove it owns.
- Prefer a safe failure over destructive guessing.
- Keep Garmin independent: Terento is not affiliated with, endorsed by, or
  sponsored by Garmin.

## License

Terento source code is licensed under GPL-3.0-or-later. See [LICENSE](LICENSE) and [NOTICE](NOTICE). Provider map and
data licenses remain separate and must retain their own attribution and source
requirements.
