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
- License notice: `site/assets/fonts/Inter-OFL.txt`
- Use: body copy and UI text

## Umami analytics

The production landing page loads the Umami tracker supplied by the project owner:

`https://stats.enduristas.lt/script.js`

Website ID: `d8097a98-ffe4-478e-b212-9f06b5bcccbe`

This is a runtime service reference, not a bundled dependency or secret. It is included on the production page only; test environments must use a no-tracking build. See the [Umami documentation](https://docs.umami.is/docs) for the service's privacy model and configuration details.

## Caddy static web server

- Image: `caddy:2.10-alpine`
- Image digest used for the Hostinger deployment: `sha256:4c6e91c6ed0e2fa03efd5b44747b625fec79bc9cd06ac5235a779726618e530d`
- Upstream: <https://github.com/caddyserver/caddy>
- License: Apache License 2.0
- Use: serve the static landing page inside the private Docker network behind the existing Traefik reverse proxy
- The image is pulled at deployment time and is not redistributed in the Terento repository.
