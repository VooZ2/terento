# Third-party notices

Terento currently bundles the following web fonts for the public landing page. They remain under their upstream licenses; the Terento source code remains planned for GPL-3.0-or-later.

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

The production landing page loads the Umami tracker supplied by the project owner:

`https://stats.enduristas.lt/script.js`

Website ID: `d8097a98-ffe4-478e-b212-9f06b5bcccbe`

This is a runtime service reference, not a bundled dependency or secret. It is included on the production page only; test environments must use a no-tracking build. See the [Umami documentation](https://docs.umami.is/docs) for the service's privacy model and configuration details.

## Native connectivity PoC dependencies

The isolated native connectivity PoC under
`lab/native-connectivity-poc/` links to Homebrew-installed libraries during
development. The production Xcode target rebuilds these libraries from the
pinned upstream sources recorded below and bundles the resulting dynamic
libraries in `Terento.app/Contents/Frameworks`.

### libmtp

- Version: 1.1.23
- Upstream: <https://github.com/libmtp/libmtp>
- License: GNU Lesser General Public License 2.1 or later (LGPL-2.1-or-later)
- Copyright: libmtp contributors
- Use: read-only Garmin MTP detection, device information, and storage information
- Distribution: bundled in the production `Terento.app` under `Contents/Frameworks`; SwiftPM development builds may still use a local Homebrew prefix.
- Build: pinned upstream source archive and checksum are recorded in `Packaging/NativeDependencies/build.sh`.
- Compatibility: Terento code is GPL-3.0-or-later; the dynamically linked libmtp remains under LGPL-2.1-or-later. Terento does not relicense libmtp.

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

- Version: 3.2.9 (`psycopg[binary]`)
- Upstream: <https://www.psycopg.org/psycopg3/>
- License: GNU Lesser General Public License 3.0 or later
- Use: PostgreSQL connection and migration access for the metadata-only
  catalog service
- Distribution: installed in the catalog API Docker image; the dependency's
  own license and notice requirements remain applicable
