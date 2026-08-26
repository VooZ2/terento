# Privacy

This notice covers the public website **terento.app** and the Terento macOS beta. It is separate from the [legal notices](/legal/).

It does not cover the privacy practices of Freizeitkarte or OpenStreetMap. Map files are provided by their respective providers and are not personal data collected by Terento.

**Data controller:** Private individual. **Contact:** [privacy@terento.app](mailto:privacy@terento.app).

## Local app data

The website and app do not provide an account or login and do not require an email address. Device state, maps, Terento manifests and local installation records stay on your Mac. Local installation records are not sent to Terento unless you choose to share compatibility reports.

The app may contact `terento.app` when it starts to check whether a newer
version is available. This automatic update request is not used for analytics
or user tracking; it only fetches release metadata. Terento does not download,
mount or install the DMG in the background.

## Compatibility reports

For a new installation, the macOS beta shows a visible compatibility-sharing
choice before installation and selects it by default. If you leave it enabled
and continue with the installation, the app sends privacy-minimised
installation reports to `api.terento.app` to measure installation reliability
and compatibility evidence by watch model and firmware. You can uncheck the
choice before installing; declining does not limit the app or map installation.

A report may contain random event and per-installation operation IDs, timestamp, watch model and family, sanitized raw MTP model label, firmware version, USB vendor and product identifiers, MTP transport, a category stating only whether local identity came from an MTP serial, Garmin Unit ID, or was unavailable, map provider, selected regions and releases, exact Terento release/build, macOS version, per-map outcome, failure stage, allowlisted Terento/native failure codes, whether device writing or cleanup started, and a coarse transfer-progress range. Pre-write provider and validation failures are kept separate from watch compatibility rates. It does not contain the Garmin Unit ID or serial value, local watch identifier, account information, email address, local file paths, MTP object IDs, Terento manifests, map files, map hashes, raw error text or diagnostic logs.

These reports are processed with your consent under Article 6(1)(a) GDPR. You can stop future sharing or delete uploaded reports in the app under **About Terento → Privacy**. Withdrawal does not affect processing that took place before it.

## Storage and public statistics

Compatibility reports are stored in Terento's PostgreSQL database on its hosting infrastructure for no longer than 24 months and are then deleted. Access to individual reports is restricted to the private administration service.

Terento may publish only reviewed aggregate compatibility statistics. Raw reports, operation or event IDs, firmware lists, error details and request metadata are not published.

## Cloudflare and hosting

Cloudflare provides services used to deliver and secure the website and API, including DNS, HTTPS/TLS, content delivery and protection against abusive traffic. The website, API and database run on Hostinger infrastructure. Terento and these providers may process IP addresses, request metadata and security-related information to operate and protect these services. [Cloudflare's privacy policy](https://www.cloudflare.com/privacypolicy/) and [Hostinger's privacy policy](https://www.hostinger.com/legal/privacy-policy) apply.

## Umami analytics

The site loads the Umami analytics script from `stats.enduristas.lt` only after you consent, to measure visits. Umami does not use tracking cookies or create personal profiles. Visit statistics are processed with your consent under Article 6(1)(a) GDPR.

It may record the page path, referrer, browser and device type, and country-level context to produce aggregated statistics. It is not used for advertising or personal profiling. See the [Umami FAQ](https://umami.is/docs/faq).

## Language preference and cookies

When you choose a site language, the site stores `terento-language` in your browser's local storage. The site does not use advertising or profiling cookies. Cloudflare security cookies, if used, serve infrastructure and security purposes.

If you do not consent to analytics, Umami is not loaded. You can change or withdraw analytics consent at any time using the website privacy settings.

## Your rights

Under the GDPR you may have rights to access, rectify, erase, restrict processing, object, data portability, withdraw consent and lodge a complaint with a supervisory authority. In Lithuania that is the State Data Protection Inspectorate (VDAI).

Use the app to stop sharing or delete uploaded compatibility reports. For other requests, contact [privacy@terento.app](mailto:privacy@terento.app).

The controller relies on legitimate interests under Article 6(1)(f) GDPR to deliver and secure the website and API, prevent abuse, and maintain network and information security. Website analytics and optional compatibility reports are processed only with consent under Article 6(1)(a) GDPR.
