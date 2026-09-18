# Terento v1.0.0-beta.12 (build 32)

Terento continues to offer Freizeitkarte, OpenTopoMap, MapRando, BBBike and BBBike (Ontrail) maps.

## Improvements

- Better recognition of BBBike maps previously installed through Terento.
- Remove is available for valid external maps, including maps installed outside Terento. Garmin maps remain protected, and removal still requires confirmation.
- Failed-install diagnostics retain the selected maps and watch context when the screen closes or resets, and use the existing retry queue and sharing settings.
- Installation diagnostics and map statistics keep their shared operation reference and separate outcomes for each selected map.
- Fixed a startup crash introduced by the newer macOS build tools. Added checks to catch this before publication.
- Safe map Update is included for supported map-capable Garmin watches. The flow downloads and validates the replacement, installs and verifies the new map, removes the previous Terento-owned version only after verification, and then updates the local manifest.
- Map updates are recorded separately from new installations in map activity, statistics, and administrator views. Updates do not increase new-installation totals, coverage, or popularity counts.
- Pre-write inventory failures are now reported as device-check failures with the measured wait time, rather than as finishing or post-transfer failures. Inventory waiting remains bounded to the native USB operation limit, while cancellation and cleanup stay bounded.
- Added privacy-minimised local diagnostics for session opening, file-list reading, session closing, and native cleanup. These details are not uploaded as raw logs or local paths.

## Known issues

- Release status remains **Public beta — RC evaluation**. The owner-reported BBBike Lithuania safe update is PASS; the Freizeitkarte and OpenTopoMap real-update gates remain open. This is not a general hardware or provider certification.
- Compatibility remains model and variant specific. Automated tests do not establish real-device compatibility for every Garmin model.
- The isolated `Installing 0%` hardware cause from issue #222 has not been confirmed on the affected watch because no test watch is currently available. This build improves phase classification and diagnostics; it does not claim a confirmed hardware transport fix.
- Occasional device connection issues may interrupt reading installed maps or finishing an installation. If prompted, disconnect and reconnect your Garmin, then try again.
- Missing or shared model identifiers may still require administrator review. Unknown screen or Solar properties remain unconfirmed.
- Updating the app cannot reconstruct diagnostic reports or watch identities that were never recorded. Abrupt app termination before a result reaches the local queue can still leave an unrecorded result.

The release pipeline passed the full regression suite, live map-catalog validation, Developer ID signing, Apple notarization, stapling, DMG verification, and launch smoke checks.

<!-- DMG SHA-256: d8c84f4d152afee978405793283aedb3868217b965b7ed6dde46284a923c6756 -->
