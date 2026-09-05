# Privacy

This notice covers the Terento website and macOS app. No account is needed to use the app. Your maps and device records stay on your Mac; the limited diagnostics described below are shared separately.

## Who to contact

Data controller: private individual. Read [About Terento](/about/) or contact [privacy@terento.app](mailto:privacy@terento.app) about your data.

## App diagnostics

Two diagnostic streams are enabled by default to improve installation reliability and compatibility. There is no sharing choice during installation. Turn either stream off in **Terento → Diagnostics** without limiting the app. This stops future sharing and clears that stream’s unsent queue; uploaded reports cannot be deleted from the app. Privacy-rights requests can be sent to the contact above.

- **Compatibility:** watch model and firmware, app and macOS versions, selected provider/maps, installation result and limited technical error information.
- **Map usage:** provider, map/region, download or installation outcome, time, app build and random operation/event IDs. Custom `.img` imports are excluded from this stream.

Reports exclude Garmin Unit IDs, serial-number values, account details, local paths, map files and raw logs. Individual reports are private; only reviewed aggregate compatibility results are published. The basis is legitimate interests in improving reliability and device coverage, under GDPR Article 6(1)(f).

## Website and app connections

Website, API, catalog and app-update requests may expose your IP address and request metadata to hosting and security providers. Catalog maps download directly from Freizeitkarte or OpenTopoMap, whose privacy practices apply to those connections. The app’s launch update check retrieves release metadata, not an app download.

These connections serve content, provide requested app functions and protect against abuse. Security processing relies on legitimate interests under GDPR Article 6(1)(f).

## Help and public issues

If you email us, we receive your address, message and anything you attach, to answer your request and investigate the problem. Do not send map files, credentials or private device identifiers. Support handling relies on legitimate interests in responding to requests and maintaining the app.

A GitHub issue is separate from automatic diagnostics: you review and submit it, and its content and GitHub account name may be public. [GitHub’s privacy statement](https://docs.github.com/en/site-policy/privacy-policies/github-general-privacy-statement) applies. Optional donations take place on [Buy Me a Coffee](https://www.buymeacoffee.com/privacy-policy), which processes payment-related information under its own terms.

## Website statistics and browser storage

Umami loads for all visitors to measure page visits, link clicks and download events. It does not use tracking cookies. It may process page/referrer URLs, browser, operating system, device and approximate location information. UTM values in links describe campaign sources. Terento passes those values through URLs without storing campaigns in your browser. Statistics support site improvement and campaign measurement under legitimate interests, GDPR Article 6(1)(f). There is no analytics consent banner or on-site analytics switch; contact us to object. Website statistics are separate from the app’s diagnostic settings.

The site remembers a language you choose as `terento-language` in local storage. This requested preference is separate from analytics. Cloudflare may use security cookies depending on its protection settings.

## Recipients and storage

Website, API and database hosting use Hostinger; Cloudflare delivers and protects website/API traffic. Umami runs at `stats.enduristas.lt`. See [Cloudflare](https://www.cloudflare.com/privacypolicy/) and [Hostinger](https://www.hostinger.com/legal/privacy-policy) for their processing information. Provider configurations may involve processing outside the EEA; contact us for details of applicable arrangements.

The retention policy for uploaded app diagnostics is 24 months. Access is restricted to project administration. Support correspondence is kept while needed to resolve the request and related disputes or legal obligations. Contact us about other service-specific storage periods or a particular report.

## Your choices and rights

You may request access, correction, erasure or restriction and object to processing based on legitimate interests. Portability applies where its legal conditions are met.

Contact [privacy@terento.app](mailto:privacy@terento.app). We normally respond within one month; if a lawful extension is needed, we will explain it. Reports are not linked to an account or direct device identifier, so we may need information that helps locate yours. You may complain to the [Lithuanian State Data Protection Inspectorate (VDAI)](https://vdai.lrv.lt/) or another competent supervisory authority.

## Technical diagnostic fields

Compatibility reports may also include a sanitized MTP model label, USB VID/PID, transport, identity-source category (never the identifier value), map releases, timestamps, random event/operation IDs, failure stage, approved app/native error codes, write/cleanup status and coarse transfer progress. Custom imports use coarse custom-source labels. Neither stream sends manifests, MTP object IDs, map hashes or unfiltered error text.

Updated: 5 September 2026.
