# Terento macOS release packaging

`Packaging/release.sh` is the repeatable Stage 6.5 release entry point. It
builds a fresh arm64 Release app, runs the SwiftPM regression suite, verifies
the bundled libmtp/libusb libraries, signs nested code inside-out with
Developer ID, submits a temporary ZIP to Apple, staples the accepted app, and
validates both final ZIP and DMG installers with Gatekeeper and launch smoke
tests.

## Preconditions

- macOS and Xcode with the `Terento.xcodeproj` toolchain available;
- the Developer ID Application identity for Team ID `VXALAZU3B5` in the local
  Keychain;
- the notarytool Keychain profile `TerentoNotary` configured outside the
  repository;
- `/opt/homebrew/opt/libmtp`, or an explicitly supplied `LIBMTP_PREFIX`, for
  the legacy SwiftPM regression tests only. This is not a production runtime
  dependency: the app build bundles source-built libmtp/libusb under
  `Terento.app/Contents/Frameworks`.

## Full release validation

Run from the repository root:

```sh
Packaging/release.sh --version 1.0.0 --build 8
```

For a beta release, keep the app's marketing version separate from the public
release label:

```sh
RELEASE_TAG=v1.0.0-beta.8 \
Packaging/release.sh \
  --version 1.0.0 \
  --build 8 \
  --release-version 1.0.0-beta.8 \
  --overwrite
```

The pipeline fails rather than silently replacing an existing artifact. Use
`--overwrite` only when the exact output is intentionally being regenerated.
The results are written to:

```text
dist/Terento-1.0.0-beta.8-macOS-arm64.zip
dist/Terento-1.0.0-beta.8-macOS-arm64.dmg
```

The command prints the final artifact size and SHA-256 checksum for both
packages. Packaging explicitly excludes macOS resource forks, extended
attributes, ACLs, and quarantine metadata so `._*`, `.DS_Store`, and
`__MACOSX` files cannot enter the distributed archives. The ZIP contains one
top-level item, `Terento.app`. The DMG contains
the same signed app and an `Applications` shortcut for drag-and-drop install.
Both packages are mounted or extracted and checked before the pipeline reports
success.

## Application icon and Help menu

The macOS application icon is generated from the immutable canonical symbol at
`brand/logo/logo.svg`. The generator changes only the symbol color and square
composition; it does not redraw or alter the approved path geometry.

Regenerate the checked-in AppIcon PNG sizes from the repository root with:

```sh
xcrun swift Packaging/generate-app-icon.swift
```

The Xcode asset catalog contains the 1x/2x macOS renditions from 16 pt through
512 pt. The native Help menu and the `About Terento` window are part of the
SwiftUI app shell. Documentation currently points to the public repository
README because the website does not yet have a dedicated documentation route.

The all-tests loop invokes every `Tests/run-*.sh` file directly. Preserve the
executable bit on newly added test runners before using the full release
entry point; a shell-invoked test can pass while the release loop still stops
on a file-mode error.

## Dry-run

To exercise the fresh build, tests, signing, Hardened Runtime, and runtime-path
checks without contacting Apple or creating release artifacts:

```sh
Packaging/release.sh --no-notarize --version 1.0.0 --build 8 \
  --release-version 1.0.0-beta.8
```

This mode explicitly reports `NOT NOTARIZED` and must not be treated as a
distribution-ready artifact.

Temporary build and notarization files are created under `/private/tmp` and
are removed after a successful run. A failed run preserves its unique run
directory for diagnostics. No certificate, private key, password, Apple ID,
or app-specific password is read from or written to the repository.

This pipeline does not publish to GitHub, upload release files, or modify Apple
Developer settings. The `dist/` artifacts are local release outputs until they
are explicitly attached to a GitHub prerelease.

## Update metadata release checklist

Before distributing a public build:

- increment `CFBundleVersion` monotonically and set the public release label;
- set the intended `TERENTO_RELEASE_CHANNEL` (`beta` or `stable`);
- update `site/updates/macos-arm64.json` with the matching version, build,
  minimum macOS, channel, and canonical DMG `downloadURL`;
- provide a concise plain-text `summary` and the canonical `releaseNotesURL`;
- regenerate the public JSON-LD from the release manifest and visible FAQ
  content with `python3 scripts/normalize-structured-data.py --write`, then
  run it again with `--check` before publishing;
- publish and notarize the DMG using this existing process;
- validate the manifest after publication and confirm its download and notes
  URLs remain official Terento destinations.

The app performs only a background metadata check and a user-confirmed
`NSWorkspace` hand-off. It does not download, mount, or replace the app in the
background. Do not add Sparkle, in-place replacement, rollback, forced update,
or periodic polling as part of this release flow.

Public structured data keeps `https://terento.app/#software` and
`https://terento.app/#organization` stable across locales. Home pages render
one graph containing the publisher, application, website, and the localized
visible FAQ; Download pages render only the application and reference the
publisher. The renderer reads release version, download, and notes URLs from
`site/updates/macos-arm64.json` and derives FAQ JSON-LD from each page's
visible `#faq` section.
