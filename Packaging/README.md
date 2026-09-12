# Terento macOS release packaging

`Packaging/release.sh` is the repeatable release entry point. It
builds a fresh arm64 Release app, runs the SwiftPM regression suite, verifies
the bundled libmtp/libusb libraries, signs nested code inside-out with
Developer ID, submits a temporary ZIP to Apple, staples the accepted app, and
validates both final ZIP and DMG installers with Gatekeeper and launch smoke
tests.

## Preconditions

- a clean checkout of a GitHub-verified signed release commit already merged
  into beta, plus authenticated `gh` for the read-only source preflight;
- macOS and Xcode with the `Terento.xcodeproj` toolchain available;
- Node.js for the JavaScript-backed native/web regression contracts;
- Python 3.12 or 3.13 for backend and shared JSON contract checks; the backend
  runner prepares the ignored repository `.venv` and installs
  `backend/catalog-api[test]` when needed;
- the Developer ID Application identity for Team ID `VXALAZU3B5` in the local
  Keychain;
- the notarytool Keychain profile `TerentoNotary` configured outside the
  repository;
- `/opt/homebrew/opt/libmtp`, or an explicitly supplied `LIBMTP_PREFIX`, for
  the legacy SwiftPM regression tests only. This is not a production runtime
  dependency: the app build bundles source-built libmtp/libusb under
  `Terento.app/Contents/Frameworks`.

If Node.js is not on `PATH`, set `TERENTO_NODE_BIN` to its executable. The
same override is used by the web, native, backend, and release checks.

## Full release validation

The current published build is identified by `site/updates/macos-arm64.json`
and `RELEASE_NOTES.md`. Packaging a new artifact does not publish it. Public
labels never use `-local`; local device-test candidates do.

Run from the repository root with explicitly selected new release values:

```sh
RELEASE_TAG="v${release_label}-build${build_number}" Packaging/release.sh \
  --version "$marketing_version" --build "$build_number" \
  --release-version "$release_label"
```

Set these variables to the reviewed release plan; do not reuse a distributed
build number. The command fails if output already exists. `--overwrite` is
only for intentionally regenerating an undistributed local output. Results are
`dist/Terento-<release-label>-macOS-arm64.zip` and `.dmg`.

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
SwiftUI app shell. User documentation is available in the public
[installation guide](https://terento.app/guides/install-garmin-maps-mac/).

The release entry point invokes `Tests/run-all-tests.sh`. Its checked-in suite
manifest assigns every leaf runner to one functional area, and the inventory
gate rejects unassigned, duplicated, missing, or non-executable runners.

## Dry-run

To exercise the fresh build, tests, signing, Hardened Runtime, and runtime-path
checks without contacting Apple or creating release artifacts:

```sh
Packaging/release.sh --no-notarize --version "$marketing_version" \
  --build "$build_number" --release-version "$release_label"
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

## Mandatory local-test / public-release telemetry boundary

Every locally tested build, including a candidate for the next release, must
use a semantic `TerentoReleaseLabel` ending in `-local` (for example
`1.0.0-beta.10-local`). Use the Debug test-build path; its Xcode guard now
rejects a missing or public label even when build settings are overridden.
Do not use a public-labelled Release artifact for local installation tests.

Both privacy-minimised diagnostic streams carry this release label. The API
derives and stores `is_local_test=true`; the caller cannot override the
classification. Local events are shown only in authenticated `/admin/test-data`
and are excluded from Overview, Installations, Maps statistics, compatibility
counts and public compatibility evidence. This is a logical partition in the
existing API/database, not a separate telemetry host. Raw local diagnostic
logs remain local and are not uploaded by this mechanism.

A public beta must use its public semantic label with no `-local` suffix and
is stored with `is_local_test=false`. The Release guard and release-documentation
gate reject local public labels. Keep `CFBundleVersion` numeric and monotonically
increasing for public distribution; the `-local` marker belongs to the displayed
release label and diagnostic identity, not to the public build-order counter.

Before the next public release: run the release-documentation gate, the two
native diagnostic suites and backend isolation tests; verify the packaged
`TerentoReleaseLabel`; verify a local test appears only in Test data. Never
generate a synthetic public installation just to validate the public counters.
Historical events without trustworthy local labels must not be automatically
relabeled or deleted based on model, date, owner, or guessed build provenance.

## Local OpenTopoMap contour test build

The internal contour allowlist is available only in a Debug build. Build the
app with the Debug configuration and a `*-local` release label, then distribute
the app together with `Packaging/local-contour-test.command`. The launcher sets
the Debug-only environment values for `opentopomap-andorra` and
`opentopomap-ltu`; launching `Terento.app` directly intentionally leaves the
contour rollout off. Release builds ignore these Debug overrides and enable source-validated contours
through the public rollout policy.

The local package is ad-hoc signed, arm64-only, not notarized, and not a public
release. Its `TerentoReleaseLabel` must remain a strict local label so its
diagnostic and map-statistics events are classified as purgeable test data.

## Local Finishing diagnostic build

For an explicitly authorized Debug diagnostic package, use `local-finishing-diagnostics.command`
beside the Debug `Terento.app`. It enables the same contour allowlist plus
`TERENTO_FINISHING_TRACE=1`. This flag controls the extra Debug stderr mirror.
Normal builds now independently collect fixed-field Finishing events in
`~/Library/Logs/Terento/finishing.log` (512 KiB rotation, one previous file),
without a special launcher. A frozen, bounded failure summary is included in
`log.txt` and the user-reviewed Report issue draft; full files are not uploaded
automatically. No version/build metadata is changed for this diagnostic iteration.

The launcher creates a unique mode-0600 log under `~/Library/Logs/Terento/`
with prefix `finishing-r4-` and redirects stdout/stderr directly to that regular
append file. Workers inherit stderr, preserving evidence through worker timeout
without a pipe consumer. Fixed structured trace fields exclude filenames, map
bytes and hardware identifiers; ordinary native-library terminal output is also
captured locally and must be reviewed before public sharing. No trace upload is
implemented. Include the log and the existing `log.txt` when reviewing a failure.
This is diagnosis only; it does not fix the intermittent session failure.

## Update metadata release checklist

Before distributing a public build:

- run the complete release pipeline on the newest macOS version available to
  the project; its architecture, minimum-OS, runtime-path, code-signing,
  Gatekeeper and launch-smoke checks are the automated compatibility baseline;
- before a new major macOS release, record a separate preview/RC test when a
  suitable machine is available; until then, keep that future-OS result
  explicitly pending rather than inferring it from the current macOS run;
- increment `CFBundleVersion` monotonically and set the public release label;
- set the intended `TERENTO_RELEASE_CHANNEL` (`beta` or `stable`);
- update `site/updates/macos-arm64.json` with the matching version, build,
  minimum macOS, channel, release tag, and canonical DMG `downloadURL`;
- provide a concise plain-text `summary` and the canonical `releaseNotesURL`;
- run `Tests/run-all-tests.sh` and retain its per-suite summary in CI output;
- synchronize all six visible Download pages with
  `python3 scripts/normalize-release-pages.py --write`, then require
  `python3 scripts/normalize-release-pages.py --check` to pass;
- regenerate the public JSON-LD from the release manifest and visible FAQ
  content with `python3 scripts/normalize-structured-data.py --write`, then
  run it again with `--check` before publishing;
- publish and notarize the DMG using this existing process;
- validate the manifest after publication and confirm its download and notes
  URLs remain official Terento destinations.

Every distributed rebuild must receive a new monotonically increasing build
and a new build-specific tag, even if its semantic beta label is unchanged.
Never reuse an existing public tag or overwrite a distributed artifact.

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

## Sampled-read worker bounds

Sample verification uses a 120-second inactivity limit renewed only by strictly
increasing validated-byte progress from the private worker sidecar, with a
600-second absolute limit per sample worker. Missing, malformed, repeated,
regressing or inconsistent progress cannot extend the wait. Opening and final
release are covered by these limits; successful progress never substitutes for
the final verified result. Cancellation still kills and reaps the owned child
before the lifecycle lease is released.

Connection discovery retains its separate 120-second limit. Cleanup, inventory
and snapshot workers retain their 45-second limits. Sample coverage, native
USB calls, retry policy, map writes and ownership rules are unchanged.

## Release evidence and publication

Historical local candidate commands are retained in Git history, not active
instructions; see [historical evidence](../history/README.md). The public beta
includes all four reviewed providers. Never replace a packaged catalog or
change activation flags manually as a normal release step.

Merge the tested release source into beta, then package from the exact
GitHub-verified merge commit. Create a lightweight tag at that packaged SHA;
verify its remote target and signature before publishing the draft release.
See [the signature policy](../VERSIONING.md#verified-release-source).
The beta push is the single site deployment trigger; a tag records app provenance
and runs release CI, without redeploying an older site tree. Attach the verified
artifacts to the intended GitHub prerelease and verify the final live manifest,
download URLs and checksums. The published source-client catalog matrix must
retain prior route contracts and gain the new release source when appropriate.

A local PASS is not publication evidence. The release receipt must distinguish
compilation/tests, signing/notarization, exact-model owner hardware results,
GitHub asset publication and live website verification. A waived real newer-map
update remains untested and must remain in Known issues.
