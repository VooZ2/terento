# Legal notices

This page explains what Terento is and what it is not. These are public notices about the website and the project.

They are not an app user agreement, not an App Store EULA, not a Garmin document, and not a digital-content contract under Directive (EU) 2019/770.

The website, the macOS app in development, and map files are different things. The maps are not Terento’s work.

**Status.** No legal person, data controller, or contact address is designated yet. When they are, they will be added here. There is no email on this page — do not invent one.

## Garmin

Garmin belongs to Garmin Ltd. Terento is not affiliated with Garmin and is not endorsed, certified, or a partner of Garmin.

Garmin names (including product names) are used only to make clear which watches we work with: compatibility, testing, documentation, and search. Terento does not use Garmin logos.

## Apple and macOS

Apple, Mac, macOS, and Apple Silicon belong to Apple Inc. Terento is not affiliated with Apple. Those names are needed because the product is being built for Mac.

## Maps

Terento does not create, relicense, or call the maps “Terento maps.”

Freizeitkarte, OpenStreetMap, and other data providers keep their own licences. Terento only connects the path: download from the original provider → your Mac → the watch. Terento does not host or redistribute map files on its own servers.

See [Freizeitkarte](https://www.freizeitkarte-osm.de/) and [OpenStreetMap copyright](https://www.openstreetmap.org/copyright).

## Software licence

Terento source code is licensed under the GNU GPL 3.0 or later. Full text: [LICENSE](https://github.com/VooZ2/terento) in the repository.

The GPL grants freedoms in the code. It does not grant rights to use the name or mark “Terento” as a trademark, and it does not let anyone claim that a modified version is an official Terento release if it is not.

Website HTML, CSS, and JavaScript of Terento origin are also GPL unless a file says otherwise. Fonts and other third-party parts stay under their own licences — see [THIRD_PARTY_NOTICES.md](https://github.com/VooZ2/terento/blob/main/THIRD_PARTY_NOTICES.md).

## Other software

So the macOS app can talk to the watch over MTP, development builds link to Homebrew libraries. The production app rebuilds the dynamic libraries from pinned upstream sources and bundles them under \`Terento.app/Contents/Frameworks\`:

- **libmtp** — LGPL-2.1-or-later, [github.com/libmtp/libmtp](https://github.com/libmtp/libmtp)
- **libusb** — LGPL-2.1-or-later, [github.com/libusb/libusb](https://github.com/libusb/libusb)

Each library keeps its own licence. Terento does not relicense them.

## No warranty

The software is distributed in the hope that it will be useful, but **without any warranty**. Terento is not responsible if using the project, the website, or the software bricks a device, loses data, or if maps fail.

The product rule is to stop rather than guess and cause damage. That is not a promise that nothing will go wrong.

Nothing here waives rights that cannot be waived under applicable law, including EU and Lithuanian consumer protection.

## What runs on the website

The public site is delivered and protected by **Cloudflare**. Visit counts use **Umami** (no cookies, no personal profiling). A language choice may be stored in your browser.

Details: [Privacy](/privacy/).

## What is still missing

There is no registered legal person, company number, VAT number, or official contact. That is an open gap, not a hidden address. If optional donations are offered later, they will not unlock features or maps.

This text is a project notice, not legal advice.

## First-run acknowledgment (macOS app)

The public macOS app (GitHub + website, not App Store) shows a one-time English risk-and-ownership notice immediately before the first write to a Garmin device. It is not an EULA. Copy and UX: [FIRST-RUN-EN.md](FIRST-RUN-EN.md).
