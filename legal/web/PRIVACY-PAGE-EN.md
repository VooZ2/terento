# Privacy

This notice covers the public website **terento.app** and the Terento macOS beta. It is separate from the [legal notices](/legal/).

It does not cover the privacy practices of Freizeitkarte, OpenTopoMap, or OpenStreetMap. Map files are provided by their respective providers and are not personal data collected by Terento.

**Data controller:** Private individual. **Contact:** [privacy@terento.app](mailto:privacy@terento.app).

## Local app data

The website and app do not provide an account or login and do not require an email address. Device state, maps, Terento manifests and local installation records stay on your Mac. The app sends only the privacy-minimised diagnostic fields described below and never sends those local records.

The app may contact `terento.app` when it starts to check whether a newer
version is available. This automatic update request is not used for analytics
or user tracking; it only fetches release metadata. Terento does not download,
mount or install the DMG in the background.

## Privacy-minimised compatibility diagnostics

The macOS beta sends privacy-minimised compatibility diagnostics that are not
linked to an account or direct device identifier by default to
`api.terento.app` to improve installation reliability and
compatibility coverage by watch model and firmware. There is no sharing choice
in the installation flow. You can turn this stream off at any time under
**Terento → Diagnostics**; doing so does not limit the app or map installation.

A report may contain random event and per-installation operation IDs, timestamp, watch model and family, sanitized raw MTP model label, firmware version, USB vendor and product identifiers, MTP transport, a category stating only whether local identity came from an MTP serial, Garmin Unit ID, or was unavailable, map provider, selected regions and releases, exact Terento release/build, macOS version, per-map outcome, failure stage, allowlisted Terento/native failure codes, whether device writing or cleanup started, and a coarse transfer-progress range. Pre-write provider and validation failures are kept separate from watch compatibility rates. It does not contain the Garmin Unit ID or serial value, local watch identifier, account information, email address, local file paths, MTP object IDs, Terento manifests, map files, map hashes, raw error text or diagnostic logs.

These diagnostics are used to improve Terento's app quality, installation
reliability and supported-device coverage. You can stop future sharing under
**Terento → Diagnostics**. The app does not provide a delete action for
uploaded diagnostics; contact [privacy@terento.app](mailto:privacy@terento.app)
for privacy-rights requests.

## Privacy-minimised map-usage diagnostics

The app sends a separate stream of privacy-minimised map-usage
diagnostics by default to measure map download and installation outcomes. Each
event may contain only random event and operation IDs, timestamp, provider,
map, region, event type, outcome and app build. It does not contain a watch
model or identifier, serial or Garmin Unit ID value, account, local file path,
manifest, map file or diagnostic log. You can turn this stream off under
**Terento → Diagnostics**; doing so does not limit installation. Custom IMG
installations are reported only through compatibility diagnostics and never
through this map-usage stream.

## Storage and public statistics

Compatibility diagnostics and map-usage diagnostics are stored in Terento's
PostgreSQL database on its hosting infrastructure for no longer than 24 months
and are then deleted. Access to individual events is restricted to the private
administration service. The app does not provide a user-facing delete action
for uploaded diagnostics.

Terento may publish only reviewed aggregate compatibility statistics. Raw reports, operation or event IDs, firmware lists, error details and request metadata are not published.

## Cloudflare and hosting

Cloudflare provides services used to deliver and secure the website and API, including DNS, HTTPS/TLS, content delivery and protection against abusive traffic. The website, API and database run on Hostinger infrastructure. Terento and these providers may process IP addresses, request metadata and security-related information to operate and protect these services. [Cloudflare's privacy policy](https://www.cloudflare.com/privacypolicy/) and [Hostinger's privacy policy](https://www.hostinger.com/legal/privacy-policy) apply.

## Umami analytics

The site loads the Umami analytics script from `stats.enduristas.lt` for all visitors to measure visits and download events. Umami does not use tracking cookies or create personal profiles. Visit statistics are processed on the basis of Terento’s legitimate interests under Article 6(1)(f) GDPR: understanding site reach and campaign performance, improving the public site, and supporting a free open-source project.

It may record the page path, referrer, browser, operating system, device type, and country-level context to produce aggregated statistics. Download events may include non-personal UTM campaign values to distinguish campaign sources and creative variants. It is not used for advertising or personal profiling. See the [Umami FAQ](https://umami.is/docs/faq).

## Language preference and cookies

When you choose a site language, the site stores `terento-language` in your browser's local storage. The site does not use advertising or profiling cookies. Cloudflare security cookies, if used, serve infrastructure and security purposes.

There is no analytics consent popup or analytics settings control. You may object to this processing by contacting [privacy@terento.app](mailto:privacy@terento.app).

## Your rights

Under the GDPR you may have rights to access, rectify, erase, restrict processing, object, data portability, withdraw consent and lodge a complaint with a supervisory authority. In Lithuania that is the State Data Protection Inspectorate (VDAI).

Use **Terento → Diagnostics** to stop future diagnostic sharing. The app does
not provide a delete action for uploaded diagnostics. For privacy-rights
requests, contact [privacy@terento.app](mailto:privacy@terento.app).

The controller relies on legitimate interests under Article 6(1)(f) GDPR to
deliver and secure the website and API, prevent abuse, maintain network and
information security, understand site reach, measure campaigns and improve
Terento through privacy-minimised diagnostics that are not linked to an account
or direct device identifier.
