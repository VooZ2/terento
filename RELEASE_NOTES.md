# Terento v1.0.0-beta.6

Release date: 2026-08-26

Beta.6 broadens the Garmin smartwatch beta from one tested USB identity to
reviewed Garmin Map Manager model families, while strengthening the checks
that protect the connected watch and Terento-managed maps. It also adds
privacy-minimised failure diagnostics so unsuccessful beta installations can
be investigated without asking users to send raw logs.

This remains a pre-MVP beta for hardware validation. A model being listed by
Garmin as map-capable allows a guarded beta installation attempt; it is not a
claim that Terento has already verified that exact model. Freizeitkarte
remains the only map provider.

## Highlights

- Map installation is no longer limited to the fēnix 8 USB PID used by the
  original hardware test. Reviewed map-capable smartwatch families, including
  fēnix, epix, Forerunner, Enduro, tactix, quatix, MARQ, Descent, D2 Mach and
  Venu X1 families, may enter the guarded beta installation flow.
- Every production write is bound to the live MTP session. The native layer
  verifies the connected Garmin VID/PID, manufacturer, raw MTP model and one
  unambiguous `/GARMIN` target before writing. The laboratory Write Test and
  Interruption Test remain restricted to their validated `0x51b8` identity.
- fēnix 8 and fēnix 8 Pro are now separate identities in the app, private
  diagnostics and compatibility data. Case size alone never guesses AMOLED,
  Solar or MicroLED.
- Watches without a stable MTP serial can use the Garmin Unit ID from one
  bounded `/GARMIN/GarminDevice.xml` read for local ownership. The serial and
  Unit ID values are never uploaded, logged or stored in the manifest.
- Terento-managed maps can be recovered after moving the same watch to a new
  Mac or losing the previous local manifest. Recovery verifies the complete
  map before adopting it and cannot transfer ownership to a different watch.
- Remove refreshes the live device inventory and resolves current-session MTP
  handles before deletion. It still removes only a verified Terento-managed
  map. Backup remains an explicit user choice and is not run automatically.

## Installation diagnostics and compatibility evidence

- The visible compatibility-sharing choice remains selected by default and
  can be turned off without limiting installation or removal.
- Opted-in reports now include one random operation ID per Install action,
  exact Terento beta/build, a controlled failure stage and code, whether a
  write or cleanup started, and a coarse transfer-progress range.
- Download, extraction, validation and preflight failures can be diagnosed but
  do not reduce a watch model's installation compatibility rate when device
  writing never started.
- Multiple selected maps share one operation ID while retaining individual map
  results. Reports for the same exact model/variant aggregate into one evidence
  row instead of creating duplicate model rows.
- Private admin diagnostics show only the sanitized raw MTP model label and
  whether local identity came from an MTP serial, Garmin Unit ID or was
  unavailable. They never receive the identifier value, local path, MTP object
  ID, manifest, map hash, raw error text or log file.
- The three legacy Swiss-map failures from issue #32 were retained for private
  investigation but quarantined from the incorrect base fēnix 8 identity.

## Catalog, UI and offline behavior

- The app consumes the canonical API compatibility status instead of deriving
  Testing, Tested, Supported or Verified locally.
- The bundled Freizeitkarte fallback contains the complete 63-package
  metadata set, including measured final IMG installation sizes. It is used
  only when the live catalog is unavailable and is presented as potentially
  stale; it does not limit the remote catalog.
- Verification wording now distinguishes sampled transfer verification from a
  complete file proof.
- App metadata and compatibility reports carry the exact
  `1.0.0-beta.6` / build `5` identity.

## Safety and privacy

- Garmin-owned, unknown and manually managed files remain read-only.
- New installs never overwrite an existing target. Update still follows
  write-new → verify → remove-old and never deletes the working map first.
- Safe Update behavior is unchanged in beta.6. Its automated suite passes, but
  the real-device update gate remains pending a genuinely newer Freizeitkarte
  release.
- Device manifests and physical-watch ownership keys remain local. There is no
  account, login, cloud device profile, required email or server-side Garmin
  identifier storage.

## Validation status

- Backend validation: 95 tests passed; backward-compatible migrations 017 and
  018 are deployed before the beta.6 client.
- Full automated native Stage 2–7, Install, Recover, Remove, manifest,
  compatibility, privacy and unchanged Safe Update suites pass.
- Swift/Xcode arm64 Release build, bundled libmtp/libusb checks, Developer ID
  signing verification and GitHub CI pass.
- The owner hardware smoke gate passed on the available fēnix 8 watch using
  the final notarized build: exact model presentation, map installation,
  opted-in beta.6 report delivery and Remove all passed.
- The fēnix 8 Pro issue #32 correction is based on the reported pre-write
  failure and automated regression coverage. Public beta evidence is still
  needed for that exact model.

## Known limitations

- Map-capable means eligible for a guarded beta attempt, not independently
  verified compatibility. Exact model status continues to be based on opted-in
  successful installations.
- A watch that exposes neither a stable MTP serial nor a valid Garmin Unit ID
  remains read-only because Terento cannot safely separate two identical
  physical watches for ownership and later removal.
- Safe Update has not yet passed its real-device newer-map gate.
- Freizeitkarte is the only supported map provider. Terento does not host or
  mirror map binaries.
- macOS 13 or later on Apple Silicon is required. Intel Macs, App Store, PKG,
  Windows and Linux distributions are not included.

## Release checksums

```text
Terento-1.0.0-beta.6-macOS-arm64.dmg  f206816fbee38fe2092cdfc91d58eb68e88c2b0f7ee0c909c327b4b1d455ccb5
Terento-1.0.0-beta.6-macOS-arm64.zip  b779086c1bad975b7275db34e44c6033eeaf04118881feca20b383fa82b960c7
```
