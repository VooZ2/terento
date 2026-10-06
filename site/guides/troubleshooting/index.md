---
title: "Troubleshooting Garmin Maps on Mac — Terento"
canonical: https://terento.app/guides/troubleshooting/
---

Troubleshooting

# Fix common Terento problems

Find the problem you see in Terento and follow its short steps. If nothing helps, send a report so we can take a look.

Connection

## Connecting your watch

### Terento is waiting for your watch

Terento finds the watch automatically after you connect it. This can take up to 2 minutes.

1. Connect the watch directly to your Mac with a USB cable that supports data. Charge-only cables and some hubs do not work.
2. Unlock the watch.
3. Wait up to 2 minutes while Terento checks the connection.
4. If the watch still does not appear, unplug it, wait a few seconds and connect it again.

### Another app is using the watch

Only one app can use the watch connection at a time.

1. Quit Garmin Express and any other app that can open the watch, such as a file-transfer app.
2. If the watch appears in Finder, eject it there.
3. Reconnect the watch, then choose “Refresh” in Terento.

### More than one Garmin is connected

Terento works with one Garmin device at a time.

1. Disconnect every Garmin device except the watch you want to use.
2. Keep that watch connected and wait for Terento to find it.

### The watch is not ready for file transfer

Some Garmin watches have a USB Mode setting that controls how they connect to a computer.

1. On the watch, look for USB Mode, usually under Settings › System. Not every model has it.
2. If the setting is there, choose MTP.
3. Disconnect the watch and connect it again.

### The watch was found but did not become ready

Terento detected the watch, but the connection did not become ready within 2 minutes. Occasional connection stalls are a known limit of the current beta.

1. Unplug the watch and connect it again.
2. Close other apps that may be using the watch.
3. Try another USB port or cable.
4. If it keeps happening, restart the watch and connect it again.

### The watch stopped responding

The connection was lost or the watch stopped answering Terento.

1. Unplug the watch, wait a few seconds and connect it again.
2. If Terento was installing, updating or removing a map, open “Manage maps” after reconnecting and check the result before you try again.
3. Restart the watch if it keeps happening.

Checks

## Watch and map checks

### This watch model isn’t enabled for map installation

Terento installs maps only on Garmin watches with map support that are enabled in Terento. You can still connect the watch and browse the maps.

1. Check that your watch model supports maps.
2. Terento checks its current list each time you connect. If your model is enabled later, connect the watch again.
3. Tell us your exact model so we can review it. See [Send a report](https://terento.app/guides/troubleshooting/#send-report).

### Terento couldn’t check this watch

Terento needs an internet connection to check whether this watch can install maps.

1. Check that your Mac is connected to the internet.
2. Connect the watch again to repeat the check.
3. If it still fails, wait a few minutes and try again.

### Map availability couldn’t be checked

Terento could not load the current map list, or this version of Terento is too old for it. Maps already on your watch are not affected.

1. Check your internet connection and try again in a few minutes.
2. If Terento says a newer version is available, install the update.
3. While Terento shows an older saved map list, installing and updating catalog maps stays unavailable until the current list can be checked.

Downloads and space

## Downloads and free space

### The map download failed

Terento downloads each map directly from its provider. Providers are sometimes slow or temporarily unavailable.

1. Check your internet connection.
2. Read the reason shown beside the map. If the provider is unavailable or downloads are paused, try again later.
3. Start the installation again.

### Not enough free space on the Mac

Terento needs temporary space on your Mac to download and prepare a map.

1. Free up space on your Mac, for example by removing files you no longer need.
2. Try again. Large regions need more space.

### Not enough free space on the watch

Terento checks the free space on the watch before it installs and does not start if the maps will not fit.

1. Choose a smaller region or fewer maps.
2. Remove a map you no longer need in “Manage maps”.
3. An update needs extra space while the new map is checked. Free up space if an update cannot start.

Installing and updating

## Installs, updates and removals

### Installation failed after the map was written

If an installation stops after copying started, part of the map can remain on the watch. Terento does not remove it automatically.

1. Connect the watch again and wait until Terento is ready.
2. Open “Manage maps” and check the list.
3. If the map from the failed installation is listed, remove it, then install it again.
4. If it fails again, [send a report](https://terento.app/guides/troubleshooting/#send-report).

### Updates or removals take a long time

Updating or removing a map can stay at a high percentage for a while before it finishes. This is expected in the current beta.

1. Keep the watch connected and your Mac awake until Terento says it is done.
2. Don’t unplug the watch while Terento is working.
3. If Terento reports a failure, connect the watch again and check “Manage maps” before you try again.

Still stuck?

## Getting help

### Send a report

When an installation, update or removal fails, Terento saves a report on your Mac that helps us investigate.

1. On the failure screen, choose “Report issue”. Later, you can use “Report latest failure” in “Diagnostics”.
2. Terento opens GitHub with the report filled in. If the form is empty, click the report field, press ⌘A and then ⌘V.
3. Review the report before posting: GitHub issues are public.
4. No GitHub account? Email [hello@terento.app](mailto:hello@terento.app?subject=Terento%20installation%20issue) with your watch model, the map region and what happened.

New to Terento?

## Start with the three-step installation guide.

[Read the Mac installation guide](https://terento.app/guides/install-garmin-maps-mac/)
