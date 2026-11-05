---
title: "Install Free Maps on a Garmin Watch from a Mac — Terento"
canonical: https://terento.app/guides/install-garmin-maps-mac/
---

# Install free maps on your Garmin watch from a Mac

Terento puts free OpenStreetMap maps, or your own map file, on a Garmin watch with map support. You don’t copy any files yourself, and your Garmin maps stay as they are.

[Download](https://terento.app/download/)

Using Linux? [Install maps from your browser](https://terento.app/guides/install-garmin-maps-linux/).

## What you need

- Apple Silicon Mac with macOS 13 or later
- Garmin watch with map support
- USB cable that supports data transfer

After you connect, Terento checks the watch and tells you whether it can install maps. [Compatibility](https://terento.app/compatibility/) lists the models with successful installations; a missing model isn’t necessarily unsupported.

## Install a map

1. Download and open Terento

[Download Terento](https://terento.app/download/), drag it from the disk image to Applications and open it there. The first time, macOS asks whether to open an app downloaded from the internet: choose Open.

2. Connect your watch

Quit Garmin Express if it’s open. Unlock the watch and connect it to your Mac with a USB data cable, not a charge-only cable. If macOS asks whether to allow the accessory to connect, choose Allow. Terento finds the watch within 1–2 minutes and checks whether it can install maps.

[Garmin watch not showing up on Mac](https://terento.app/guides/troubleshooting/#connect-watch)

Terento showing a connected Garmin watch and device detection status
Terento recognizes the connected Garmin watch before installation.

3. Choose a map

Pick a map from the catalog or add your own compatible .img file. [Compare map styles](https://terento.app/map-styles/) to see how each map draws roads and trails.

1. Choose from the catalog

Choose a provider and a region from the catalog.

2. Add your own map

Add a compatible .img map from your Mac.

Terento showing third-party map providers, regions and available Garmin storage
Choose a map from the catalog or add your own compatible file.

4. Install

Start the installation and keep the watch connected until Terento says the map is ready. Then disconnect the watch.

Terento showing a completed map installation on a Garmin watch
Keep the watch connected until transfer and verification are complete.

## Show the map on your watch

Disconnect the watch, open its map settings and turn the new map on. If it isn’t listed, restart the watch. If several maps cover the same area, turn off the ones you don’t want to see.

Still can’t see it? Email [hello@terento.app](mailto:hello@terento.app?subject=Terento%20installation%20issue) with your exact watch model, map region and what happened.

## If something doesn’t work

### Terento does not detect the watch

Wait up to 1–2 minutes after connecting. If the watch still does not appear, reconnect it, check that the cable supports data and close other apps that may be using it. More help: [Garmin watch not showing up on Mac](https://terento.app/guides/troubleshooting/#connect-watch), [Garmin Express or another app is using the watch](https://terento.app/guides/troubleshooting/#garmin-busy), [Garmin watch not recognized: USB mode (MTP)](https://terento.app/guides/troubleshooting/#usb-mode).

### Install or Update is unavailable

Temporarily unavailable maps stay visible. Read the reason shown beside the map. If its provider is unavailable or downloads are paused, try later. If Terento cannot check current availability, check your internet connection and try again. Your installed maps remain available. More help: [Garmin map list won’t load or Terento needs an update](https://terento.app/guides/troubleshooting/#catalog-unavailable), [Garmin map download failed](https://terento.app/guides/troubleshooting/#download-failed).

### Installation failed

On the failed installation screen, choose “Report issue”. Terento opens GitHub with the report already filled in. Review it before posting: GitHub issues are public. For help by email, include your watch model, map region and what happened. More help: [Map installation failed: leftover map on the watch](https://terento.app/guides/troubleshooting/#leftover-map), [How to report a problem with Terento](https://terento.app/guides/troubleshooting/#send-report).

[See all troubleshooting steps](https://terento.app/guides/troubleshooting/)

## Uninstall Terento

Quit Terento and move it from Applications to the Trash. Maps already on your watch stay there. Terento keeps its records of the maps it installed in ~/Library/Application Support/Terento: keep that folder if you may install Terento again, so it can still update and remove those maps. To remove everything, also delete that folder, ~/Library/Caches/Terento, ~/Library/Logs/Terento and ~/Library/Preferences/app.terento.mac.plist.
