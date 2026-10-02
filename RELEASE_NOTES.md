# Terento v1.0.0-beta.16 (build 38)

Terento is a free, open-source Public beta for installing community maps on map-capable Garmin smartwatches from Apple Silicon Macs running macOS 13 or later. Compatibility is evaluated model by model.

## App improvements

- Fixed BBBike map availability checks.
- Improved diagnostic reports for failed map updates, including the failure stage and whether the previous map was preserved.

## Admin and project improvements

- Added package rechecks with actionable validation results and check history.
- Added update failure details, with links from Activity and update statistics.
- Unified installation and update error views: a clear outcome, map and provider, failure reason, next action, known safety facts, and GitHub issue preparation, preview, copying and linking.
- Added separate update results and paginated history to exact model and variant details, including diagnostic review and linked-issue controls.
- Made Activity show the map, provider and known watch model together for installations and updates, without the extra blank row for custom maps.
- Separated successful and failed updates in charts. Update results do not count as installations or change public compatibility evidence.
- Corrected the initial model-picker selection and made historical catalog markers consistent while preserving model variants. Missing historical failure details remain unknown.
- Simplified the README and retained implementation details in technical documentation.

## Known issues and beta limits

- Update and remove operations can remain at a high displayed percentage for a noticeable period before completion; remove was observed around 87% before finishing.
- Intermittent USB/MTP stalls are not claimed fixed. Reconnect and try again if the connection does not become ready.
- OpenTopoMap India remains under investigation in [issue #278](https://github.com/VooZ2/terento/issues/278).
- Real newer-release update validation remains pending for Freizeitkarte and OpenTopoMap. These gates are not established by automated checks or successful updates from another provider.
- Garmin Edge devices remain outside the current supported scope. This release does not broaden device compatibility claims.

Existing protected-map, ownership, safe Update and explicit Remove safeguards remain in place.

<!-- DMG SHA-256: 7cd45a731d3cdfa589ac4fe7fa41aae4226a381ee447bf6b9247962152d9a794 -->
