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
Packaging/release.sh --version 1.0.0 --build 1
```

For a beta release, keep the app's marketing version separate from the public
release label:

```sh
RELEASE_TAG=v1.0.0-beta.2 \
Packaging/release.sh \
  --version 1.0.0 \
  --build 1 \
  --release-version 1.0.0-beta.2 \
  --overwrite
```

The pipeline fails rather than silently replacing an existing artifact. Use
`--overwrite` only when the exact output is intentionally being regenerated.
The results are written to:

```text
dist/Terento-1.0.0-beta.2-macOS-arm64.zip
dist/Terento-1.0.0-beta.2-macOS-arm64.dmg
```

The command prints the final artifact size and SHA-256 checksum for both
packages. The ZIP contains one top-level item, `Terento.app`. The DMG contains
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
Packaging/release.sh --no-notarize --version 1.0.0 --build 1
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
