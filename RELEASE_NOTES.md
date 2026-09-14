# Terento v1.0.0-beta.12 (build 30)

Terento continues to offer Freizeitkarte, OpenTopoMap, MapRando, BBBike and BBBike (Ontrail) maps.

## Improvements

- Map activity now distinguishes processing, cancellation and interruption after a download starts. Unfinished downloads are reconciled when Terento next opens.
- Main maps and contour downloads keep separate outcomes and activity history.
- Device review shows received XML and USB identifiers independently of catalog confirmation, prioritizes the reported model, and reduces repeated model choices to the remaining screen and Solar differences.
- Preserves the provider identity of catalog maps, including OpenTopoMap and Freizeitkarte. Custom imports remain separate.

## Known issues

- The map update feature has not been tested yet.
- Occasional device connection issues may interrupt reading installed maps or finishing an installation. If prompted, disconnect and reconnect your Garmin, then try again.
- Missing or shared model identifiers may still require administrator review. Unknown screen or Solar properties remain unconfirmed.
- Download recovery and component reporting passed automated tests; a complete build30 installation and interruption check on a real watch is still pending. Existing build29 records cannot always recover outcomes that were never recorded.

<!-- DMG SHA-256: c758b71e6cc5f92e6d8078f8c331b14ab0d850e7c8fe63313b169e0f644b08e6 -->
