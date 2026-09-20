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
- Public device copy describes a Garmin smartwatch with map support rather than a
  finite supported-model list.
- Initial HTML must contain the current published snapshot; JavaScript may refresh
  it live. The generator/source is canonical; do not hand-edit divergent locale
  HTML, and preserve the same semantics in all six locales.
