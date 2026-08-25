# Legal notices

These legal notices describe the Terento website, the Terento project, the public beta macOS app, and the third-party software and map data associated with them.

Map data and map files remain subject to the terms and licences of their respective providers.

## Garmin

Garmin belongs to Garmin Ltd. Terento is not affiliated with Garmin and is not endorsed, certified, or a partner of Garmin.

Garmin names, including product names, are used only to describe compatibility, testing, documentation, and search. Terento does not use Garmin logos.

## Apple and macOS

Apple, Mac, macOS, and Apple Silicon belong to Apple Inc. Terento is not affiliated with Apple. Those names are used descriptively because the beta is available for Apple Silicon Mac.

## Maps

Terento does not create, relicense, or call the maps “Terento maps.”

Freizeitkarte, OpenStreetMap, and other data providers keep their own licences. Terento connects the path from the original provider to your Mac and watch. Terento does not host or redistribute map files on its own servers.

See [Freizeitkarte](https://www.freizeitkarte-osm.de/) and [OpenStreetMap copyright](https://www.openstreetmap.org/copyright).

## Software licence

Terento source code is licensed under the GNU GPL 3.0 or later. The full text is available in the repository [LICENSE](https://github.com/VooZ2/terento/blob/beta/LICENSE).

The GPL grants freedoms in the code. It does not grant rights to use the name or mark “Terento” as a trademark or to claim that an unofficial modified version is an official Terento release.

Website HTML, CSS, and JavaScript of Terento origin are also GPL unless a file says otherwise. Fonts and other third-party parts stay under their own licences. See [THIRD_PARTY_NOTICES.md](https://github.com/VooZ2/terento/blob/beta/THIRD_PARTY_NOTICES.md).

## Other software

The production build of the macOS beta uses **libmtp** to communicate with compatible devices over MTP. It includes the dynamically linked **libmtp** and **libusb** libraries, built from pinned upstream source releases and bundled in `Terento.app/Contents/Frameworks`:

- **libmtp** 1.1.23 — LGPL-2.1-or-later, [github.com/libmtp/libmtp](https://github.com/libmtp/libmtp)
- **libusb** 1.0.30 — LGPL-2.1-or-later, [github.com/libusb/libusb](https://github.com/libusb/libusb)

`libusb` is a runtime dependency of `libmtp`. Each library remains under its own licence. Terento does not relicense these libraries.

## No warranty

The software is distributed in the hope that it will be useful, but **without any warranty**. Terento is not responsible if using the project, website, or software makes a device unusable, loses data, or if maps fail.

The product rule is to stop rather than guess and cause damage. That is not a promise that nothing will go wrong.

Nothing here waives rights that cannot be waived under applicable law, including EU and Lithuanian consumer protection.

## Online services

The public site and API are delivered and protected through online
infrastructure described in the Privacy notice. Visit statistics use Umami
only after consent. For a new installation, the macOS beta shows a visible
compatibility-sharing choice before installation and selects it by default.
Reports are sent only when the user continues with that choice; the user can
uncheck it before installing.

Details: [Privacy](/privacy/).
