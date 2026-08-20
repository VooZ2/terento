# Terento

> Your device, ready for where you're going.

Terento is an open-source project exploring a simpler way to install community
maps on modern Garmin smartwatches from a Mac.

## Current scope

- macOS and Apple Silicon
- modern Garmin smartwatches using MTP
- Freizeitkarte as the first and only provider
- Lithuania as the first real end-to-end proof path

The project is pre-MVP. The public v1 scope is limited to modern Garmin
smartwatches. Installation, downloads, and model support are not generally
available until the corresponding technical gates pass on real hardware.

## Repository guide

- [`site/`](site/) — the initial public landing page and its SEO assets
- [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) — bundled font and runtime
  notices

Operational VPS notes, brandbook material, live project state, local task
notes, previews, and credentials are intentionally kept outside the public
source set.

## Principles

- Prefer the simplest reliable path before adding native components.
- Keep map downloads on the user's Mac and use the original provider source.
- Keep device state and manifests local.
- Modify only files Terento can prove it owns.
- Prefer a safe failure over destructive guessing.

## License

The planned Terento source-code license is GPL-3.0-or-later. Provider map and
data licenses remain separate and must retain their own attribution and source
requirements.
