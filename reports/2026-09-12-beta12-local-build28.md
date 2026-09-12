# beta.12-local build28 — local test artifact

Date: 2026-09-12. User requested a beta.12-local build of PR173 UI polish.
Runtime source: 9235296 on terento/catalog-ui-polish. Public beta.11/build27
release settings, release manifest and downloads remain unchanged.

## Build and package

Xcode Debug arm64 with bundled MTP, optimization -O, command-line overrides:
TERENTO_RELEASE_LABEL=1.0.0-beta.12-local and CURRENT_PROJECT_VERSION=28.
No tracked project/version setting was changed. The normal Debug local-label
guard passed. Bundle and both dylibs are ad-hoc signed for local testing;
this is not a notarized public distribution.

Artifact: dist/Terento-1.0.0-beta.12-local-build28-macOS-arm64.zip (about5.7MB).
SHA256: 13feaebde178864c3e94cd05d5fd954fb4edc9f3e442194ad46640da2696fdd7
Unpacked app: dist/beta.12-local-build28/Terento.app.
Artifacts are in the owner's main workspace, not published to GitHub Releases.

## Verification

- Xcode build PASS.
- Fresh ZIP extraction + deep strict codesign verification PASS.
- Extracted Info.plist label 1.0.0-beta.12-local/build28 PASS.
- Executable/libmtp/libusb arm64 and absence of Homebrew runtime linkage PASS.
- No running app was stopped, replaced or launched; /Applications and device
  maps were untouched. New UI visual acceptance remains pending owner testing.

PR CI had found a stale root About contract requiring the deleted sidebar page.
The contract was updated to require the consolidated app-menu About, retaining
privacy/link/diagnostics/update/brand checks. Focused contract PASS; the actual CI app entrypoint Tests/run-app-tests.sh
passes all24/24 runners in39.6s after correcting both root About/readiness
contracts. Install/remove execution code is
unchanged from the UI source and previously passed safety suites.
