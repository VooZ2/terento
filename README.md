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
- Lithuania as the first real end-to-end proof path

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
maps Terento can prove it owns, and backup and integrity checks are required
before removal. Installation and update verification are part of the guarded
workflow.

Safe Update is implemented and covered by automated validation. The final
real-device update gate is pending a genuinely newer Freizeitkarte release.
The project has not marked Stage 5.3 hardware validation as passed.

## Development status

Terento is not a stable production release. The repository currently contains
source and development builds for the macOS PoC, public web surfaces, and the
metadata catalog service. Stage 6 production packaging has not started: no
notarized DMG or PKG is provided by this release.

## Repository guide

- [`site/`](site/) — the public landing page and legal/SEO assets
- [`lab/`](lab/) — the macOS proof of concept and isolated connectivity labs
- [`backend/catalog-api/`](backend/catalog-api/) — the metadata-only catalog
  service
- [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) — dependency and runtime
  notices
- [`VERSIONING.md`](VERSIONING.md) — public beta versioning policy

## Principles

- Prefer the simplest reliable path before adding native components.
- Keep map downloads on the user's Mac and use the original provider source.
- Keep device state and manifests local.
- Modify only files Terento can prove it owns.
- Prefer a safe failure over destructive guessing.
- Keep Garmin independent: Terento is not affiliated with, endorsed by, or
  sponsored by Garmin.

## License

The planned Terento source-code license is GPL-3.0-or-later. Provider map and
data licenses remain separate and must retain their own attribution and source
requirements.
