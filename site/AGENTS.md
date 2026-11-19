# Website instructions

These are future-change rules for `site/**`. Do not change current site files
as a side effect of unrelated work.

- Preserve the approved visual direction and current layout unless a task
  explicitly requests a redesign.
- Reuse existing semantic variables and components. Do not invent page-level
  brand colors.
- Use Instrument Sans for brand and marketing headings. Use Inter for
  navigation, controls, body copy, labels, and information.
- Keep one clear primary-action hierarchy. `Warm Stone` cannot become a
  second primary CTA.
- Preserve the existing light/dark hierarchy. Do not use light Sky, Lichen,
  or Warm Stone as normal-size text on Alpine Off-White.
- UI icons are original Lucide 0.460.0 outline SVGs (24 px grid, 1.75 px
  stroke, `currentColor`), inlined with `aria-hidden` and listed in
  `THIRD_PARTY_NOTICES.md`; never hand-draw or redraw an icon. Brand logos
  (GitHub, Apple, Garmin) are the only exception.
- Maintain visible keyboard focus and reduced-motion behavior.
- Localization must preserve meaning and hierarchy, not merely literal word
  length.
- Public copy must match the current release state. Future-state mockup text
  is not evidence that a feature has shipped.
- Change app screenshots only as part of a reviewed application release or an
  explicitly scoped screenshot task.
- Do not make broad CSS or generated-page refactors during unrelated content
  changes.

## Documentation impact

When user-visible app behavior, feature availability, requirements,
compatibility semantics, install/update/remove flow, or troubleshooting
changes, review the public copy and its canonical generator source in the same
change. Never hand-edit generated locale HTML. Regenerate all six locales and
preserve the same meaning in each locale.

## Public Compatibility

- Compatibility is a successful-installation directory, not a supported-device
  whitelist. A public exact model/variant requires `successfulInstallations >= 1`;
  failed-only or zero-success models stay out of the public list.
- A missing model is not unsupported. Internal `TESTING`/`TESTED`/`SUPPORTED`/
  `VERIFIED` values are not public support badges.
- Public device copy describes a Garmin smartwatch or a newer Garmin Edge bike
  computer with map support rather than a finite supported-model list. Write
  "Garmin Edge" or "Edge bike computer" for the device and "Microsoft Edge" for
  the browser. Never claim every Edge, handheld GPS or automotive device.
- `successfulInstallations` counts app and web-installer successes. Each card
  shows that total and its split (`appSuccessfulInstallations`,
  `webSuccessfulInstallations`; a snapshot or payload without them counts every
  success as app), with the Lucide `laptop` and `globe` outline icons; a part with
  zero is hidden. Card counts below 100 are exact; from 100 they are rounded down
  to the hundred with a plus (`1,200+`, plural form). The summary line, filters
  and sorting keep exact counts.
- Initial HTML must contain the current published snapshot; JavaScript may refresh
  it live. The generator/source is canonical; do not hand-edit divergent locale
  HTML, and preserve the same semantics in all six locales.

## Shared page components (site refresh, 2026-11)

- Indexed pages use one component layer in `styles.css`: `.grid`
  (12 columns, one on phones, `col-4|6|8|12`, `row-2`), `.card`
  (`--media`), `.page-hero`, `.section-head`, `.trust-strip`, `.steps`,
  `.callout` and `.cta-band`. Markup helpers live in
  `scripts/site_components.py`. Reuse them instead of page-specific variants.
- One hero on every page (round 4, 2026-11-19): `section.page-hero >
  .shell > .hero-copy` with the H1, one `.hero-lede` and optional
  `.hero-actions`, on the canvas, left-aligned in a 720px column, never in a
  card. Same top padding (`--hero-top`) and gap to the next section
  (`--hero-gap`) everywhere; H1 64px on Home, 52px elsewhere; lead 21/18px,
  max 65ch. Nothing goes under the hero buttons.
- Bento surfaces: the Off-White canvas carries the page; `.card` tiles use
  `--tile` (backgroundSecondary) without borders. Radii: controls
  `--control-radius` 10px, cards `--card-radius` 14px, large panels
  `--panel-radius` 18px. Card and step titles use `--type-item` (Instrument
  Sans 22px). Product photos sit on `--photo-tile` in both modes.
- Buttons: `primary_action()` (one primary button, "Download for Mac" with
  the Lucide download icon, 40px, 15/20 at 600) and `secondary_action()`
  (outlined, same size). `store_download()` adds Apple's badge and is used
  only on /download/: at most one App Store badge per page. Never change the
  badge.
- Every page except Download ends with `end_cta(locale, location)`: "Put a
  free map on your Garmin", "Download for Mac" and a "Use the web installer"
  text link (the Linux guide passes `web_first=True`).
- Header navigation marks the current item with `aria-current="page"`, 600
  in the link colour; every guide page (watch, Edge, Linux, Troubleshooting)
  marks "Guide".
- Links: one style everywhere (link colour, 600, no underline; underline on
  hover). Dates: one long format per locale (`dateStyle: "long"`).
- `.cta-band` titles are `<p class="cta-band__title">`, never headings, so
  the H2 list does not change.
- Run `python3 scripts/check-site-refresh.py` for any layout change (pass the
  intended changes with `--expect`, e.g. `scripts/site-refresh-step0-expect.json`): it
  compares title, H1, meta description, canonical, hreflang, robots, the H2
  list, JSON-LD types, Umami events and FAQPage questions against
  `origin/main` for every page and locale.
