# Terento v1.0.0-beta.15 (build 37)

Terento offers Freizeitkarte, OpenTopoMap, MapRando, BBBike and BBBike (Ontrail) community maps for map-capable Garmin smartwatches on Apple Silicon Macs running macOS 13 or later.

## Improvements

- Further hardened the **Install** flow so transient preparation states cannot expose an action the engine cannot accept.
- Simplified obsolete internal installation and update code while preserving current authorization, ownership, verification, rollback, and cleanup safeguards.
- Owner-tested on a Garmin fēnix 8 AMOLED 47 mm with BBBike install, update, and remove; MapRando multi-map installation; and disconnect/reconnect inventory verification.

Existing protected-map, ownership, safe Update and explicit Remove safeguards remain in place.

## Known issues

Update and remove operations can remain at a high displayed percentage for a noticeable period before completion; remove was observed around 87% before finishing. Intermittent USB/MTP stalls are not claimed fixed; reconnect and try again if the connection does not become ready. Garmin Edge devices are outside the current supported scope.

OpenTopoMap India remains under investigation in issue #278.

<!-- DMG SHA-256: 35fe79dab413843300e1cac4d0bfa07af1641ded5083e580318697566ea75ec3 -->
