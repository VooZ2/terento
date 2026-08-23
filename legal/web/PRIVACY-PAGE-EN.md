# Privacy

A short notice about the public website **terento.app**. It is separate from the [legal notices](/legal/).

This is not a privacy policy for the macOS app, and not Freizeitkarte’s or OpenStreetMap’s policy. You download maps from the original provider; those files are not a Terento personal-data product.

**Status.** No controller identity or contact is designated yet. The project is published by Terento contributors. When a legal person is designated, it will be stated here. There is no email on this page — do not invent one.

## What this site does not do

There is no account, login, or required email. Device state and Terento manifests stay on your Mac under project rules and are not uploaded to a Terento server as a cloud watch profile during MVP.

libmtp and libusb are used only by the native macOS app, not by this website. Development builds use Homebrew; the production app uses the pinned bundled dynamic libraries described in the legal notices.

## What runs on the website

### Cloudflare

DNS and HTTPS at the edge are provided by Cloudflare. That typically means content delivery, TLS, and protection against abusive traffic. Project documentation names only this edge — not Workers, R2, or Turnstile.

IP addresses and request metadata may be processed so the site can be delivered and protected. [Cloudflare’s privacy policy](https://www.cloudflare.com/privacypolicy/) applies. Data may be processed outside Lithuania or the EU, depending on Cloudflare’s setup.

Cloudflare **may** set security cookies (for example `__cf_bm`, `cf_clearance`) if bot protection or challenges are enabled in the dashboard. That depends on Cloudflare settings. A normal response observed at the time of writing did not set those cookies — this page does not claim they exist if they do not.

### Umami analytics

The production site loads an Umami script from `stats.enduristas.lt` to count visits. Umami states, and the script confirms: it **does not use tracking cookies**. There is no account, email, or personal profile across visits.

It typically records path, referrer, browser and device type, and country-level context. Terento does not enable Umami `identify()`. The script may read a `localStorage` key `umami.disabled` if you set it yourself as an opt-out.

See the [Umami FAQ](https://umami.is/docs/faq).

### Language preference

If you choose a site language, your browser may store `terento-language` (`localStorage`). That is a preference you asked for, so the same language can open next time — not advertising tracking.

## Cookies — what applies

**No consent banner is needed.**

This site does not use advertising or profiling cookies. Visit statistics (Umami) are cookieless and do not build a personal profile. Language `localStorage` is written only when you choose a language. Cloudflare security cookies, if they ever appear, would be for infrastructure, not marketing.

If that changes (for example non-essential cookies or profiling analytics), this page must be updated and only then should consent be asked.

Do not put an absolute “no cookies are used” line in the footer if Cloudflare settings can change. A more accurate line: visit statistics do not use cookies; details on this page.

## Your rights

Under the GDPR you may have rights to access, rectify, erase, restrict processing, object, and lodge a complaint with a supervisory authority. In Lithuania that is the State Data Protection Inspectorate (VDAI).

Until a controller contact exists, exercising those rights through a Terento channel is limited. That is stated openly. Nothing here limits those rights.

The purpose is to serve a static site, protect it, and see aggregated visit counts. A full GDPR Article 6 legal-basis statement can be given only by a designated controller; it will be added together with the identity.

This notice is a transparency text, not legal advice.
