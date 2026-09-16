# Terento v1.0.0-beta.12 (build 31)

Terento continues to offer Freizeitkarte, OpenTopoMap, MapRando, BBBike and BBBike (Ontrail) maps.

## Improvements

- Better recognition of BBBike maps previously installed through Terento.
- Remove is available for valid external maps, including maps installed outside Terento. Garmin maps remain protected, and removal still requires confirmation.
- Failed-install diagnostics retain the selected maps and watch context when the screen closes or resets, and use the existing retry queue and sharing settings.
- Installation diagnostics and map statistics keep their shared operation reference and separate outcomes for each selected map.
- Fixed a startup crash introduced by the newer macOS build tools. Added checks to catch this before publication.

## Known issues

- The map update feature has not been tested yet.
- Occasional device connection issues may interrupt reading installed maps or finishing an installation. If prompted, disconnect and reconnect your Garmin, then try again.
- Missing or shared model identifiers may still require administrator review. Unknown screen or Solar properties remain unconfirmed.
- Build31 fixes passed automated tests; their complete real-watch installation, interruption and external-removal checks remain pending.
- Updating the app cannot reconstruct diagnostic reports or watch identities that were never recorded. Abrupt app termination before a result reaches the local queue can still leave an unrecorded result.

<!-- DMG SHA-256: 295d5b37124d67d584526462d8ebab8ddf219cac491d937038ccc332b14b06c4 -->
