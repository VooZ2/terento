# Third-party notices

Terento currently bundles the following web fonts for the public landing page. They remain under their upstream licenses; the Terento source code is licensed under GPL-3.0-or-later.

## Instrument Sans

- Version/source: upstream commit `7fa22308a3d0c94ee2b3cd537a1196b65db34a3e`, downloaded on 2026-08-20
- File: `site/assets/fonts/instrument-sans.woff2`
- Upstream: <https://github.com/Instrument/instrument-sans>
- Source file: `fonts/webfonts/InstrumentSans[wdth,wght].woff2`
- License: SIL Open Font License 1.1
- License notice: `site/assets/fonts/Instrument-Sans-OFL.txt`
- Use: Terento brand and marketing headings

## Inter

- Version: 4.1
- File: `site/assets/fonts/inter-variable.woff2`
- Upstream: <https://github.com/rsms/inter>
- Source distribution: <https://rsms.me/inter/inter.css>
- License: SIL Open Font License 1.1
- License notice: the upstream SIL Open Font License 1.1 applies; no separate
  copied license file is present in `site/assets/fonts/`
- Use: body copy and UI text

## Umami analytics

The production site loads the Umami tracker supplied by the project owner for
all public-site visitors:

`https://stats.enduristas.lt/script.js`

Website ID: `d8097a98-ffe4-478e-b212-9f06b5bcccbe`

This is a runtime service reference, not a bundled dependency or secret. It is
included on production pages for all visitors; test and lab environments must
use a no-tracking build. See the [Umami documentation](https://docs.umami.is/docs)
for the service's privacy model and configuration details.

## Simple Icons

- Version: 13.x, downloaded on 2026-09-05
- Upstream: <https://github.com/simple-icons/simple-icons>
- License: CC0 1.0
- Files: `site/assets/social/linkedin.svg`, `site/assets/social/reddit.svg`,
  and `site/assets/social/buymeacoffee.svg`
- Use: small, recognizable profile and donation link marks on the About page
- Trademark note: LinkedIn, Reddit, and Buy Me a Coffee names and marks remain
  the property of their respective owners.

## Native core dependencies

The production SwiftPM native core under
`app/TerentoCore/` links to Homebrew-installed libraries during
development. The production Xcode target rebuilds these libraries from the
pinned upstream sources recorded below and bundles the resulting dynamic
libraries in `Terento.app/Contents/Frameworks`.

### libmtp

- Version: 1.1.23
- Upstream: <https://github.com/libmtp/libmtp>
- License: GNU Lesser General Public License 2.1 or later (LGPL-2.1-or-later)
- Copyright: libmtp contributors
- Use: Garmin MTP detection, device/storage information and guarded map transfers
- Distribution: bundled in the production `Terento.app` under `Contents/Frameworks`; SwiftPM development builds may still use a local Homebrew prefix.
- Build: pinned upstream source archive and checksum are recorded in `Packaging/NativeDependencies/build.sh`.
- Compatibility: Terento code is GPL-3.0-or-later; the dynamically linked libmtp remains under LGPL-2.1-or-later. Terento does not relicense libmtp.
- Local modification: `Packaging/NativeDependencies/patch-partial-read-diagnostics.pl` adds the otherwise discarded partial-read PTP response to libmtp's existing error stack. The patch changes diagnostics only, retains LGPL-2.1-or-later for the modified library, and is distributed as source alongside the pinned upstream source reference.
- Local modification (local candidate): `Packaging/NativeDependencies/patch-usb-session-lifecycle.pl` closes USB handles on failed initialization/session paths and suppresses the inherited reset-on-close quirk on macOS only for Garmin VID/PID `091e:51b8`. Explicit failed-session recovery resets remain. The modified library retains LGPL-2.1-or-later; this patch is supplied as source alongside the pinned upstream reference. Hardware acceptance remains pending.

- Local build23 candidate: `Packaging/NativeDependencies/patch-usb-recovery.py` adds explicit shutdown of libmtp's own idle libusb context under Terento's operation gate, host-only abort of a failed read session, and suppresses automatic failed-OpenSession reset only on macOS Garmin `091e:51b8`. The two additional library entry points are used only by bundled app builds. LGPL-2.1-or-later and the upstream notices remain; patch source is included with this test package. Hardware acceptance is pending. This supersedes the preceding candidate's retained explicit reset for that exact device.

- Local build24 correction: `Packaging/NativeDependencies/patch-usb-device-references.py` balances enumeration, retained MTP-list and open-handle references before context shutdown. It also releases lists on specific-device and allocation-failure exits. This fixes build23-local's reproducible library reinitialization failure. LGPL-2.1-or-later remains; patch source accompanies the local package. Read-only connection/inventory evidence does not establish installation acceptance.

### libusb

- Version: 1.0.30
- Upstream: <https://github.com/libusb/libusb>
- License: GNU Lesser General Public License 2.1 or later (LGPL-2.1-or-later)
- Copyright: libusb contributors
- Use: transitive runtime dependency of libmtp
- Distribution: bundled in the production `Terento.app` under `Contents/Frameworks`; SwiftPM development builds may still use a local Homebrew prefix.
- Build: pinned upstream source archive and checksum are recorded in `Packaging/NativeDependencies/build.sh`.
- Compatibility: the dynamically linked libusb remains under LGPL-2.1-or-later and is not relicensed by Terento.

## Caddy static web server

- Image: `caddy:2.10-alpine`
- Image digest used for the Hostinger deployment: `sha256:4c6e91c6ed0e2fa03efd5b44747b625fec79bc9cd06ac5235a779726618e530d`
- Upstream: <https://github.com/caddyserver/caddy>
- License: Apache License 2.0
- Use: serve the static landing page inside the private Docker network behind the existing Traefik reverse proxy
- The image is pulled at deployment time and is not redistributed in the Terento repository.

## psycopg

- Version: 3.3.5 (`psycopg[binary]`, as pinned by the backend package)
- Upstream: <https://www.psycopg.org/psycopg3/>
- License: GNU Lesser General Public License 3.0 or later
- Use: PostgreSQL connection and migration access for the metadata-only
  catalog service
- Distribution: installed in the catalog API Docker image; the dependency's
  own license and notice requirements remain applicable

## Simple World Map

- Version/source: `flekschas/simple-world-map`, commit
  `d3c4ebb2d0b7fc90a89d2c1e8da0d579fea3871c`
- Upstream: <https://github.com/flekschas/simple-world-map>
- File: `backend/catalog-api/src/terento_catalog/admin_world_map.py`
- License: Creative Commons Attribution-ShareAlike 3.0 Unported
- Use: local country geometry for the private Umami-style Admin map-statistics
  coverage view
- Attribution: the upstream SVG retains its author/editor/license metadata;
  the map is not used as a public marketing asset

## JSON Schema test validation

- Dependency: jsonschema 4.26.0, pinned in the backend `test` optional group
- Upstream: <https://github.com/python-jsonschema/jsonschema>
- License: MIT
- Use: offline Draft 2020-12 public contract and fixture checks only
- Distribution: installed in CI/developer test environments, not added to the
  production API image, macOS bundle or website
- Redistribution: permitted by MIT with copyright and license notice retained;
  no copyleft linking or source-disclosure obligation is introduced
- Keep upstream license files if redistributing the test environment. Test
  installation also resolves jsonschema's MIT-licensed dependencies: attrs
  (<https://github.com/python-attrs/attrs>), jsonschema-specifications
  (<https://github.com/python-jsonschema/jsonschema-specifications>), referencing
  (<https://github.com/python-jsonschema/referencing>) and rpds-py
  (<https://github.com/crate-py/rpds>). Their own notices remain applicable.

## Natural Earth country geometry

- Source: https://github.com/nvkelso/natural-earth-vector/blob/master/geojson/ne_50m_admin_0_countries.geojson (50m Admin 0 countries; exact input SHA-256 recorded in generated module).
- License: public domain, https://www.naturalearthdata.com/about/terms-of-use/. Redistribution and modification permitted; no required attribution.
- Use: local SVG country boundaries in private admin statistics, replacing the stylized map. No runtime dependency or tile service. Reproduction: backend/catalog-api/tools/build_admin_world_map.py.

## Leaflet 1.9.4

- Upstream: https://github.com/Leaflet/Leaflet/tree/v1.9.4
- License: BSD-2-Clause; redistribution and modification permitted with copyright, conditions and disclaimer retained.
- Use: admin country-statistics navigation (pan, zoom, keyboard and SVG overlay), with a reusable presentation component for a future separately approved public statistics page.
- Bundled files: original minified JS and CSS in `backend/catalog-api/src/terento_catalog/static/map/`; full notice in `LEAFLET-LICENSE.txt` alongside them.
- No runtime npm dependencies, remote tiles or CDN calls. No native application linking or source-disclosure requirement is introduced by Leaflet.
