---
title: "Install Free Maps on Garmin Edge from a Mac — Terento"
canonical: https://terento.app/guides/install-garmin-maps-edge-mac/
---

# Install free maps on your Garmin Edge from a Mac

Newer Garmin Edge bike computers don’t show up on a Mac as a drive, so you can’t simply copy a map file to them. Terento installs free OpenStreetMap maps, or your own compatible map file, on Garmin Edge bike computers with map support, such as Edge 540, 840 and 1050.

[Download](https://terento.app/download/)

## What you need

- Apple Silicon Mac with macOS 13 or later
- Newer Garmin Edge with map support
- USB cable that supports data transfer

After you connect, Terento checks the Edge and tells you whether it can install maps. [Compatibility](https://terento.app/compatibility/) lists the models with successful installations; a missing model isn’t necessarily unsupported.

## Install a map on your Edge

1. Download and open Terento

[Download Terento](https://terento.app/download/), drag it from the disk image to Applications and open it there. The first time, macOS asks whether to open an app downloaded from the internet: choose Open.

2. Connect the Edge

Quit Garmin Express if it’s open. Connect the Edge directly to your Mac with a USB data cable, not through a hub. If macOS asks whether to allow the accessory to connect, choose Allow. Terento finds the Edge within 2 minutes and checks whether it can install maps.

3. Choose a map

Choose a provider and a region from the catalog, or add your own compatible .img map file from your Mac. [Compare map styles](https://terento.app/map-styles/) to see how each map draws roads and trails.

Terento showing third-party map providers, regions and available Garmin storage
Choose a map from the catalog or add your own compatible file.

4. Install

Start the installation and keep the Edge connected until Terento says the installation is complete. Then disconnect the Edge.

Terento showing a completed map installation
Keep the Edge connected until Terento says the map is ready.

## Show the map on your Edge

Disconnect the Edge, open its map settings and make sure the new map is enabled. If it isn’t listed, restart the Edge. If several maps cover the same area, turn off the ones you don’t want to see.

## If something doesn’t work

### Garmin Edge not showing up in Terento

Use a USB data cable, connect the Edge directly instead of through a hub, quit Garmin Express and file-transfer apps, and wait up to 2 minutes. More help: [Garmin watch not showing up on Mac](https://terento.app/guides/troubleshooting/#connect-watch), [Garmin Express or another app is using the watch](https://terento.app/guides/troubleshooting/#garmin-busy).

### Install or Update is unavailable

Temporarily unavailable maps stay visible. Read the reason shown beside the map. If its provider is unavailable or downloads are paused, try later. If Terento cannot check current availability, check your internet connection and try again. Your installed maps remain available. More help: [Garmin map list won’t load or Terento needs an update](https://terento.app/guides/troubleshooting/#catalog-unavailable), [Garmin map download failed](https://terento.app/guides/troubleshooting/#download-failed).

### Installation failed

On the failed installation screen, choose “Report issue”. Terento opens GitHub with the report already filled in. Review it before posting: GitHub issues are public. For help by email, include your Edge model, map region and what happened. More help: [Map installation failed: leftover map on the watch](https://terento.app/guides/troubleshooting/#leftover-map), [How to report a problem with Terento](https://terento.app/guides/troubleshooting/#send-report).

[See all troubleshooting steps](https://terento.app/guides/troubleshooting/)

## Why your Garmin Edge doesn’t show up on your Mac

Newer Edge models, such as the Edge 540, 840 and 1050, share files over USB the way Android phones do. macOS has no built-in support for that, so the Edge doesn’t appear in Finder as a drive, and guides that tell you to copy a map file into the Garmin folder don’t work for these models. Terento talks to the Edge directly, so you don’t need Android File Transfer or OpenMTP.

## Older Edge models

Older models, such as the Edge 1030 Plus and earlier, usually show up on a Mac as a USB drive. On those, you can copy a compatible .img map file into the Garmin folder on the drive yourself, without Terento. Terento is not designed for these models.
