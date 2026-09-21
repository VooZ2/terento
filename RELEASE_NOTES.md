# Terento v1.0.0-beta.13 (build 33)

Terento offers Freizeitkarte, OpenTopoMap, MapRando, BBBike and BBBike (Ontrail) maps for map-capable Garmin smartwatches on Apple Silicon Macs.

## Improvements

- Stronger protection of existing maps during an Update.
- More reliable Update and Remove results after reconnecting your Garmin.
- Safer reading of installed-map information across device sessions.
- Removal stays available for valid external maps after an app reinstall or on another Mac, with confirmation and a fresh check of the selected map. Garmin-protected map files remain read-only.
- Uncertain failed-install cleanup leaves recovery information instead of guessing which file to remove.

## Known issues

Compatibility remains specific to the tested model and variant. Existing fresh-install hardware evidence and the local safety simulations do not certify every Garmin device or provider.

Real newer-provider Update and external Remove hardware validation remain pending. The owner-reported BBBike Lithuania update remains separate evidence; Freizeitkarte and OpenTopoMap still need their real newer-release update gates before beta exit.

Some watches may need to be disconnected and reconnected if detection or map listing stalls. The physical causes of the historical incidents in #222 and #249 remain unconfirmed; these safety changes do not establish those causes.

Missing or shared model identifiers may still require administrator review. Unknown screen or Solar properties remain unconfirmed. Updating the app cannot reconstruct diagnostic reports or watch identities that were never recorded; abrupt app termination before a result reaches the local queue can still leave an unrecorded result.

The release pipeline passed all 80 regression runners, live map-catalog validation, Release test isolation, Developer ID signing, Apple notarization, stapling, DMG verification, and ZIP/DMG launch smoke checks.

<!-- DMG SHA-256: bac6817398c0b134f36d34334ff496e3a05034f128be55a1e2ed2c452722ff37 -->
