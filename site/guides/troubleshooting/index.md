---
title: "Garmin Watch Not Showing Up on Mac? Troubleshooting — Terento"
canonical: https://terento.app/guides/troubleshooting/
---

Troubleshooting

# Fix Garmin watch and map problems on Mac

Find the problem you see, from a Garmin watch that doesn’t show up on your Mac to a map download that fails, and follow the short steps. If nothing helps, send a report so we can take a look.

Connection

## Garmin watch connection problems

### Garmin watch not showing up on Mac

Connect the watch directly to your Mac with a USB cable that supports data, unlock it and wait up to 2 minutes: Terento finds it automatically.

1. Use a USB data cable. Charge-only cables and some USB hubs don’t work.
2. Wait up to 2 minutes while Terento checks the connection.
3. If the watch still doesn’t appear, unplug it, wait a few seconds and connect it again.
4. If another app is open, see [Garmin Express or another app is using the watch](https://terento.app/guides/troubleshooting/#garmin-busy).

### Garmin Express or another app is using the watch

Quit Garmin Express and file-transfer apps such as Android File Transfer, OpenMTP or MacDroid: only one app at a time can use the watch connection.

1. Quit Garmin Express, Android File Transfer, OpenMTP, MacDroid and other MTP apps. If Terento names an app, quit that one first.
2. Also close Image Capture, Photos and Preview if they are open.
3. If the watch appears in Finder, eject it there.
4. Unplug the watch, connect it again, then choose “Refresh” in Terento.

### More than one Garmin device connected

Disconnect every Garmin device except the watch you want to use: Terento works with one Garmin at a time.

1. Unplug other Garmin watches, bike computers and handheld devices.
2. Keep the watch you want to use connected and wait for Terento to find it.

### Garmin watch not recognized: USB mode (MTP)

If Terento says the watch isn’t ready for file transfer, set the watch’s USB Mode to MTP, if your model has this setting.

1. On the watch, open USB Mode, usually under Settings › System. Not every model has it.
2. Choose MTP.
3. Disconnect the watch and connect it again.

### Garmin watch detected but not ready

If Terento finds the watch but the connection doesn’t become ready within 2 minutes, unplug the watch and connect it again. Occasional connection stalls are a known limit of the current version.

1. Quit other apps that may be using the watch. See [Garmin Express or another app is using the watch](https://terento.app/guides/troubleshooting/#garmin-busy).
2. Try another USB port or cable.
3. If it keeps happening, restart the watch and connect it again.

### Garmin watch stopped responding

Unplug the watch, wait a few seconds and connect it again: the connection was lost or the watch stopped answering Terento.

1. If Terento was installing, updating or removing a map, open “Manage maps” after reconnecting and check the result before you try again.
2. Restart the watch if it keeps happening.

Checks

## Watch and map checks

### Map installation not available for this Garmin model

Terento installs maps only on Garmin watches with map support that are enabled in Terento. You can still connect this watch and browse the maps.

1. Check that your watch model supports maps.
2. Terento checks its current list each time you connect. If your model is enabled later, connect the watch again.
3. Tell us your exact model so we can review it. See [How to report a problem](https://terento.app/guides/troubleshooting/#send-report).

### Terento couldn’t check your Garmin watch

Check that your Mac is online, then connect the watch again: Terento needs an internet connection to check whether this watch can install maps.

1. Open a website to confirm your Mac is online.
2. Unplug the watch and connect it again to repeat the check.
3. If it still fails, wait a few minutes and try again.

### Garmin map list won’t load or Terento needs an update

If Terento can’t load the current map list, check your internet connection and try again in a few minutes. Maps already on your watch are not affected.

1. If this version of Terento is too old for the current map list and Terento says a newer version is available, install the update.
2. While Terento shows an older saved map list, installing and updating catalog maps stays unavailable until the current list can be checked.

Downloads and space

## Map downloads and free space

### Garmin map download failed

Check your internet connection and try again later: Terento downloads each map directly from its provider, and providers are sometimes slow or temporarily unavailable.

1. Read the reason shown beside the map. If the provider is unavailable or downloads are paused, try again later.
2. Start the installation again.

### Not enough space on the Mac to download the map

Free up space on your Mac and try again: Terento needs temporary space to download and prepare a map.

1. Remove files you no longer need and empty the Trash.
2. Try again. Large regions need more space.

### Not enough space for Garmin maps on the watch

Choose a smaller region or remove a map you no longer need: Terento checks the watch’s free space before installing and doesn’t start if the maps won’t fit.

1. Choose a smaller region or fewer maps.
2. Open “Manage maps” and remove a map you no longer need.
3. An update needs extra space while the new map is checked. Free up space if an update can’t start.

Installing and updating

## Map installs, updates and removals

### Map installation failed: leftover map on the watch

Remove the leftover map in “Manage maps”, then install it again. If an installation stops after copying started, part of the map can stay on the watch, and Terento doesn’t remove it automatically.

1. Connect the watch again and wait until Terento is ready.
2. Open “Manage maps” and check the list.
3. If the map from the failed installation is listed, remove it, then install it again.
4. If it fails again, [send a report](https://terento.app/guides/troubleshooting/#send-report).

### Map update or removal takes a long time

This is expected in the current version: updating or removing a map can stay at a high percentage for a while before it finishes. Keep the watch connected and your Mac awake.

1. Don’t unplug the watch while Terento is working.
2. Wait until Terento says it is done.
3. If Terento reports a failure, connect the watch again and check “Manage maps” before you try again.

Still stuck?

## Getting help

### How to report a problem with Terento

Choose “Report issue” on the failure screen: Terento opens GitHub with the report it saved on your Mac already filled in.

1. Later, you can use “Report latest failure” in “Diagnostics”.
2. If the GitHub form is empty, click the report field, press ⌘A and then ⌘V.
3. Review the report before posting: GitHub issues are public.
4. No GitHub account? Email [hello@terento.app](mailto:hello@terento.app?subject=Terento%20installation%20issue) with your watch model, the map region and what happened.

New to Terento?

## Start with the three-step installation guide.

[Read the Mac installation guide](https://terento.app/guides/install-garmin-maps-mac/)
