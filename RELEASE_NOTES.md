# Terento v1.0.0-beta.17 (build 39)

Terento is a free, open-source Public beta for installing community maps on map-capable Garmin smartwatches from Apple Silicon Macs running macOS 13 or later. Compatibility is evaluated model by model.

## App improvements

- Keeps temporarily unavailable maps visible and explains which provider is unavailable. Install and Update remain disabled until downloads are available; existing maps and Remove remain available.
- Checks current download availability before starting a provider download and refreshes status while the app is idle.
- Explains provider timeouts, rate limits and connection problems. If current availability cannot be checked, the app asks you to check your connection and try again.

## Admin improvements

- Adds automatic provider checks with 1, 6 or 24 hour intervals and shows the last check, next check and current download status.
- Allows administrators to pause downloads for individual maps with a reason while keeping those maps in the catalog.
- Shows the current detailed provider check separately from compact, bounded history.

## Known issues and beta limits

- Update and remove operations can remain at a high displayed percentage for a noticeable period before completion.
- Intermittent USB/MTP stalls are not claimed fixed. Reconnect and try again if the connection does not become ready.
- OpenTopoMap India remains under investigation in [issue #278](https://github.com/VooZ2/terento/issues/278).
- Real newer-release update validation remains pending for Freizeitkarte and OpenTopoMap.
- Garmin Edge devices remain outside the current supported scope. This release does not broaden device compatibility claims.

Existing protected-map, ownership, safe Update and explicit Remove safeguards remain in place.

<!-- DMG SHA-256: 3fd52d6c23177f7d20354f9ef298be8306f086f0e1e3f60ebdf5f22ded8cd745 -->
