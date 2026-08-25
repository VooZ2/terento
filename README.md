# Terento

> A simple way to get maps onto your Garmin smartwatch from a Mac.

[![Swift CI](https://github.com/VooZ2/terento/actions/workflows/swift-ci.yml/badge.svg?branch=beta)](https://github.com/VooZ2/terento/actions/workflows/swift-ci.yml)
[![License: GPL-3.0-or-later](https://img.shields.io/badge/License-GPL--3.0--or--later-blue.svg)](LICENSE)

Terento is a free, open-source native macOS app for installing and managing
Freizeitkarte maps on Garmin smartwatches.

I started it because I got tired of looking for the right software every time
I wanted to put maps on my Garmin from a Mac. I wanted something simpler:

**Connect your watch → choose a map → install it.**

No extra transfer tools, no digging through folders, and no need to know how
Garmin stores its map files.

<p align="center">
  <img
    src=".github/assets/terento-ready-to-install.png"
    alt="Terento showing a selected map, available storage, and the Install maps action"
    width="100%"
  >
</p>

<p align="center">
  <em>Review your map, storage, and installation choice before installing.</em>
</p>

<p align="center">
  <a href="https://github.com/VooZ2/terento/releases/download/v1.0.0-beta.4/Terento-1.0.0-beta.4-macOS-arm64.dmg">Download the beta</a>
  ·
  <a href="https://terento.app/compatibility/">Check compatibility</a>
  ·
  <a href="https://github.com/VooZ2/terento/issues">Report an issue</a>
  ·
  <a href="https://terento.app/">Website</a>
</p>

> **Early beta:** Compatibility varies by Garmin smartwatch model. Terento's
> compatibility list is built from real installation evidence and community
> testing.

## What it does

Terento keeps the process intentionally small:

- detects your connected Garmin smartwatch;
- shows the Freizeitkarte regions available to install;
- downloads the map from its original source;
- checks available storage before making changes;
- installs and verifies the map;
- lets you back up or remove maps installed by Terento; and
- leaves Garmin's own maps and other unknown files alone.

<p align="center">
  <img
    src=".github/assets/terento-install-maps.png"
    alt="Choosing Freizeitkarte regions in Terento"
    width="49%"
  >
  <img
    src=".github/assets/terento-manage-maps.png"
    alt="Managing installed maps in Terento"
    width="49%"
  >
</p>

## Why Terento

Garmin watches are great outdoors. Moving third-party maps onto newer models
from macOS can be less straightforward.

Terento is my attempt to make that part feel like a normal Mac app instead of
a file-transfer exercise.

It is:

- **Native to macOS** — built for Apple Silicon.
- **Focused** — it does maps rather than trying to replace every Garmin tool.
- **Careful with your watch** — files Terento cannot identify as its own stay untouched.
- **Local-first** — no account or cloud profile is required.
- **Open source** — the code, issues, and development are public.

## Compatibility

Garmin support is based on real device evidence rather than assuming that
every watch behaves the same way.

You may see these statuses:

- **Tested** — real hardware evidence exists for that exact model.
- **Supported** — a real map installation completed successfully for that exact model.
- **Verified** — evidence exists across multiple physical devices and firmware versions.

See the current list:

**[terento.app/compatibility](https://terento.app/compatibility/)**

If you own a Garmin model that is not there yet, testing it and sharing the
result is genuinely useful.

## Requirements

- macOS 13 or later;
- an Apple Silicon Mac;
- a Garmin smartwatch with map support;
- a USB connection; and
- an internet connection for downloading maps.

Freizeitkarte is the only map source supported in the current beta.

## Download

The latest public beta is `v1.0.0-beta.4`.

- [Download DMG](https://github.com/VooZ2/terento/releases/download/v1.0.0-beta.4/Terento-1.0.0-beta.4-macOS-arm64.dmg) — recommended for installation
- [Download ZIP](https://github.com/VooZ2/terento/releases/download/v1.0.0-beta.4/Terento-1.0.0-beta.4-macOS-arm64.zip)
- [View release notes](https://github.com/VooZ2/terento/releases/tag/v1.0.0-beta.4)

The macOS app is notarized and does not require Homebrew. It is intended for
testing and real-device validation, not as a stable production release.

You can also browse all releases on the
[GitHub Releases](https://github.com/VooZ2/terento/releases) page.

## A note about beta software

Terento writes map files to your watch, so this is one of those projects where
being careful matters.

There are safeguards around installation, replacement, and removal, and
Terento avoids changing files it cannot confidently identify. Still, this is
early beta software and bugs are possible.

If you are not comfortable testing early software with your Garmin, it is
better to wait for a later release.

## Privacy

Terento works without an account.

For a new installation, the compatibility evidence-sharing choice is shown
before installation and selected by default. You can uncheck it before
installing, and declining does not affect installation or app functionality.

If enabled, Terento shares only privacy-minimised compatibility evidence to
help improve support for other Garmin users. Reports never include Garmin Unit
IDs, serial numbers, accounts, file paths, manifests, map files, or raw
diagnostic logs.

Your maps, device files, manifests, and diagnostic logs remain on your Mac.
Only the privacy-minimised compatibility evidence described above may be
shared when enabled.

See the full [Privacy Policy](https://terento.app/privacy/).

## Maps

Terento currently works with
[Freizeitkarte](https://www.freizeitkarte-osm.de/), which provides Garmin maps
based on OpenStreetMap data.

Maps are downloaded from the original Freizeitkarte infrastructure. Terento
does not host, mirror, or repackage them.

- [Freizeitkarte](https://www.freizeitkarte-osm.de/)
- [OpenStreetMap copyright](https://www.openstreetmap.org/copyright)

Terento is an independent open-source project and is not affiliated with,
endorsed by, or sponsored by Garmin.

## Feedback

This is still an early project, and feedback from real Garmin users is
especially valuable.

If you try Terento, I would love to know:

- which Garmin model you used;
- whether the watch was detected correctly;
- whether the map installed successfully; and
- whether it was still there after reconnecting.

If something does not work, open a
[GitHub issue](https://github.com/VooZ2/terento/issues) and attach the
`log.txt` generated by Terento.

Even a simple “worked on this model” report helps.

## Contributing

Bug reports, compatibility testing, documentation improvements, and focused
pull requests are welcome.

Start with:

- [`CONTRIBUTING.md`](CONTRIBUTING.md) — development setup and safe device testing
- [`SECURITY.md`](SECURITY.md) — reporting security issues
- [`Packaging/README.md`](Packaging/README.md) — build, signing, and release details

The production app is a native Xcode macOS project. Development and regression
tests live alongside it in the repository.

## License

Terento source code is licensed under
[GPL-3.0-or-later](LICENSE).
