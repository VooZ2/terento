# Terento v1.0.0-beta.18 (build 40)

Terento is a free, open-source Public beta for installing community maps on map-capable Garmin smartwatches from Apple Silicon Macs running macOS 13 or later. Compatibility is evaluated model by model.

## App improvements

- Fixed a map-folder detection inconsistency that could block installation before the transfer started on supported Garmin watches.
- Applied consistent target checks to map installation, custom map import and managed map updates, while preserving existing map and device safety checks.
- Improved preparation failure messages and local diagnostics when Terento cannot verify a safe installation target.

## Please test again

If an earlier version stopped before transferring your map, update to beta.18, reconnect your watch and retry the installation. If it still fails, report the new result with the app version and diagnostic report.

The fix passes automated regression tests, including installation and update simulations. Confirmation on the affected watches is still needed; this release does not claim that every previously reported failure is resolved.

## Known issues and beta limits

- Update and remove operations can remain at a high displayed percentage for a noticeable period before completion.
- Intermittent USB/MTP stalls are not claimed fixed. Reconnect and try again if the connection does not become ready.
- OpenTopoMap India remains under investigation in [issue #278](https://github.com/VooZ2/terento/issues/278).
- Real newer-release update validation remains pending for Freizeitkarte and OpenTopoMap.
- Garmin Edge devices remain outside the current supported scope. This release does not broaden device compatibility claims.

Existing protected-map, ownership, safe Update and explicit Remove safeguards remain in place.

<!-- DMG SHA-256: 17dc52b1c213add8217ad6f2bee4e392e1264fb1ecccc62477c52ca5c9270755 -->
