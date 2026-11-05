---
title: "Install Garmin Maps on Linux from Chrome — Terento"
canonical: https://terento.app/guides/install-garmin-maps-linux/
---

Linux guide

# Install Garmin maps on Linux

On Linux, the Terento web installer puts free maps on Garmin watches with map support, straight from your browser. Linux needs one permission rule first, so the browser can use the watch over USB.

## What you need

- Chrome, Microsoft Edge, Opera or Brave on a Linux computer. Firefox can’t connect to USB devices.
- A USB data cable, not a charge-only cable.
- A Garmin watch that supports maps, unlocked.

Three steps

## Install a map from your browser

1. Give the browser USB access

Open Terminal and paste this command. It adds a udev rule for Garmin devices and asks for your administrator password once. Then unplug the watch and plug it back in.

```
echo 'SUBSYSTEM=="usb", ATTR{idVendor}=="091e", MODE="0660", GROUP="plugdev", TAG+="uaccess"' | sudo tee /etc/udev/rules.d/70-garmin.rules >/dev/null && sudo udevadm control --reload-rules && sudo udevadm trigger
```

2. Open the web installer and connect

Open the web installer, choose Connect your watch and pick the entry with “Garmin” in its name. The list may stay empty for a minute or two while the watch gets ready.

3. Choose maps and install

Pick a country or region and choose Install maps. Keep the tab open and the watch connected until it finishes.

Troubleshooting

## If it doesn’t work

### The browser can’t open the watch

Your file manager may be using the watch. Eject it there without unplugging it, then reload the page. If you added the rule while the watch was connected, unplug it and plug it back in.

### The browser’s list stays empty

Leave the list open for up to two minutes. If no entry with “Garmin” in its name appears, try another USB data cable and check that the watch is unlocked.

### The browser has no USB access

A browser installed as a Snap package may not get USB access. Use the browser from its official .deb or .rpm package.

Ready?

## Open the web installer and connect your watch.

[Open the web installer](https://terento.app/install/)
