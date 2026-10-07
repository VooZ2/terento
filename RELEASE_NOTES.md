# Terento v1.0.0-rc.2 (build 42)

Terento 1.0.0-rc.2 is the second release candidate for Terento 1.0.0, the free, open-source app for installing community maps on map-capable Garmin smartwatches from Apple Silicon Macs running macOS 13 or later. Terento remains a Public beta until 1.0.0, release candidates only contain fixes, and compatibility is still evaluated model by model.

This candidate changes only what the Device page shows when a watch doesn't connect; map installation, Update, Remove and their safeguards are unchanged from rc.1. The new messages passed automated tests and have not yet been checked with a real watch.

## WHAT'S NEW?

- No new features in this release; release candidates only contain fixes.

## WHAT'S FIXED?

- When your watch doesn't connect, the Device page names the cause, shows what Terento found and lists what to do, with a link to the matching section of the troubleshooting guide.
- If another app such as Android File Transfer or OpenMTP may be using the watch, Terento names that app.
- The watch's USB Mode setting is named with its usual location (Settings › System).
- If no watch is plugged in for 2 minutes, the Device page shows more steps to try while Terento keeps looking.
- Each connection status in the sidebar has an icon as well as text.

## KNOWN ISSUES

- The new connection messages passed automated tests but have not yet been checked with a real watch.
- The faster Update checks from rc.1 have not yet been confirmed on a real watch.
- Updating or removing a map installed with an earlier version still uses the full check and can stay at a high displayed percentage for a while before it finishes.
- Real-watch Update validation for OpenTopoMap is still pending.
- Intermittent USB/MTP stalls are not claimed fixed. Reconnect and try again if the connection does not become ready.
- OpenTopoMap India remains under investigation in [issue #278](https://github.com/VooZ2/terento/issues/278).
- Garmin Edge devices remain outside the current supported scope. This release does not broaden device compatibility claims.

<!-- DMG SHA-256: 22e965f4d4ecdfe193ea12a662cb2140010c0f15c9514197149b11f56f0a99b7 -->

# Terento v1.0.0-rc.1 (build 41)

Terento 1.0.0-rc.1 is the first release candidate for Terento 1.0.0, the free, open-source app for installing community maps on map-capable Garmin smartwatches from Apple Silicon Macs running macOS 13 or later. Terento remains a Public beta until 1.0.0, later release candidates only contain fixes, and compatibility is still evaluated model by model.

Map Update was validated on real watches with BBBike, Freizeitkarte and MapRando maps during the beta. Fast removal was validated on a real watch with this release candidate. Protected-map, ownership, safe Update and explicit Remove safeguards and the installation authorization rules are unchanged.

## WHAT'S NEW?

- Removing a map installed with this version takes seconds instead of minutes. Terento checks the exact map object and a recorded fingerprint of the map it wrote and verified.
- Updating such a map is much faster: Terento no longer reads the installed map and the new map in full. The new map is checked the same way as a fresh installation, and the current map stays on the watch until the new one is verified.
- Maps installed with earlier versions and maps not installed by Terento keep the full check. After their first Update with this version, later Updates and removals use the fast check.
- The map list shows each map's download size and estimated download time. On a watch without Terento maps yet, it also recommends a map for your region.
- After an interrupted download, Try again continues where it stopped when the map server supports it, instead of starting over (BBBike downloads still start over). Every map is still fully checked.
- Download, write, read-back and Update/Remove checks show an estimated time left once enough progress has been measured. Terento never shows a guessed time. Update and Remove show measured progress throughout.
- Cancel is available while maps are downloaded and checked on the Mac.
- Your Mac stays awake during map transfers, and Terento asks before quitting while it writes to the watch.
- With no Garmin connected, the Device page shows a short checklist instead of a connection error. It also shows whether maps can be installed on this model; if Terento couldn't check, Try again checks again.
- Error dialogs link to the matching section of the new Troubleshooting guide on terento.app, and Help → Troubleshooting opens the guide.
- Send report to Terento sends a sanitised failure report without a GitHub account. You review exactly what is sent, and the report is sent only when you choose Send. Reporting on GitHub remains available.

## WHAT'S FIXED?

- Clear messages when another app is using the watch, when more than one Garmin is connected, or when the watch is not in file-transfer (USB) mode.
- After a timeout or an unexpected disconnect, plugging the watch back in starts a new connection automatically.
- An unexpected disconnect is shown as such. An interrupted Update or Remove explains what was kept: nothing is removed before the content check finishes, and the current map stays until the new one is verified.
- If an installation fails before anything is written, Try again keeps your selection and reuses the maps already downloaded and checked.
- The safety check before writing is faster on watches with a lot of music or other non-map content.
- When the map catalog or installation policy needs a newer app, Terento asks you to update Terento instead of showing a misleading connection error. One invalid catalog entry no longer hides the rest of the catalog.
- If Terento's record of the maps it installed on a watch can't be read, it is set aside, never deleted, before the next installation instead of the installation failing after the write.
- Optional compatibility and usage reports are delivered more reliably: a rejected report no longer blocks later ones, and results are kept when a long transfer finishes while the Mac is locked.

## KNOWN ISSUES

- The faster Update checks passed automated tests but have not yet been confirmed on a real watch.
- Updating or removing a map installed with an earlier version still uses the full check and can stay at a high displayed percentage for a while before it finishes.
- Real-watch Update validation for OpenTopoMap is still pending.
- Intermittent USB/MTP stalls are not claimed fixed. Reconnect and try again if the connection does not become ready.
- OpenTopoMap India remains under investigation in [issue #278](https://github.com/VooZ2/terento/issues/278).
- Garmin Edge devices remain outside the current supported scope. This release does not broaden device compatibility claims.

<!-- DMG SHA-256: f051c7a781c1180c5e673a7c1a0d09914faca9ec2e4ed7b9db544776cc33bbbb -->

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
