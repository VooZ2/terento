# Terento v1.0.0-rc.1 (build 41)

<!-- DRAFT: unpublished release candidate. Publish only after the owner approves these notes, the API with migrations 067–072 and the site are deployed, and the signed, notarized artifacts exist. When publishing, remove this marker and every TODO line, add the real DMG SHA-256 comment, and update the manifest in the same change. -->

Terento 1.0.0-rc.1 is the first release candidate for Terento 1.0.0, the free, open-source app for installing community maps on map-capable Garmin smartwatches from Apple Silicon Macs running macOS 13 or later. Terento remains a Public beta until 1.0.0. This candidate is feature-complete for 1.0.0; later release candidates only contain fixes. Compatibility is still evaluated model by model.

## Connecting your watch

- Terento waits for your watch. With no Garmin connected, the Device page shows a short checklist instead of a connection error.
- Clear messages when another app is using the watch, when more than one Garmin is connected, or when the watch is not in file-transfer (USB) mode.
- After a timeout or an unexpected disconnect, plugging the watch back in starts a new connection automatically.
- An unexpected disconnect is shown as such. An interrupted Update or Remove explains what was kept: nothing is removed before the content check finishes, and the current map stays until the new one is verified.
- The Device page shows whether maps can be installed on this model. If Terento couldn't check, Try again checks again.

## Installing, updating and removing maps

- Cancel is available while maps are downloaded and checked on the Mac. If an installation fails before anything is written, Try again keeps your selection and reuses the maps already downloaded and checked.
- After an interrupted download, Try again continues where it stopped when the map server supports it, instead of starting over (BBBike downloads still start over). Every map is still fully checked.
- Download, write, read-back and Update/Remove checks show an estimated time left once enough progress has been measured. Terento never shows a guessed time.
- Update and Remove show measured progress throughout.
- Your Mac stays awake during map transfers, and Terento asks before quitting while it writes to the watch.
- The safety check before writing is faster on watches with a lot of music or other non-map content.
- On a watch without Terento maps yet, the map list recommends a map for your region and shows each map's download size and estimated download time.

<!-- TODO(fast removal, variant A): add the user-facing fast-removal note after terento/app-sampled-removal is merged. -->

## Help and reports

- Errors and hints link to the matching section of the new Troubleshooting guide on terento.app.
- Send report to Terento sends a sanitised failure report without a GitHub account. You review exactly what is sent, and the report is sent only when you choose Send. Reporting on GitHub remains available.

<!-- TODO(Help links): update this section after the Help-link cleanup on terento/app-sampled-removal is merged. -->

## Safer catalog and reporting

- When the map catalog or installation policy needs a newer app, Terento asks you to update Terento instead of showing a misleading connection error. One invalid catalog entry no longer hides the rest of the catalog.
- If Terento's record of the maps it installed on a watch can't be read, it is set aside, never deleted, before the next installation instead of the installation failing after the write.
- Optional compatibility and usage reports are delivered more reliably: a rejected report no longer blocks later ones, and results are kept when a long transfer finishes while the Mac is locked.

## Validation

Map Update was validated on a real watch with BBBike, Freizeitkarte and MapRando maps.

## Known issues and limits

- Real-watch Update validation for OpenTopoMap is still pending.
- Intermittent USB/MTP stalls are not claimed fixed. Reconnect and try again if the connection does not become ready.
- OpenTopoMap India remains under investigation in [issue #278](https://github.com/VooZ2/terento/issues/278).
- Garmin Edge devices remain outside the current supported scope. This release does not broaden device compatibility claims.
- Update and remove operations can remain at a high displayed percentage for a noticeable period before completion.

<!-- TODO(owner validation): remove the high displayed percentage item above only after the owner validates fast removal on a real watch. -->

Existing protected-map, ownership, safe Update and explicit Remove safeguards remain in place. Installation authorization rules are unchanged.

<!-- TODO(publish): add the DMG SHA-256 comment of the signed 1.0.0-rc.1 DMG. -->

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
