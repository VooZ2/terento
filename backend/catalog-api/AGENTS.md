# Catalog API and admin instructions

These are future-change rules for `backend/catalog-api/**`. Do not change
backend runtime files as a side effect of brand work.

- API, database, authentication, evidence collection, and admin behavior must
  not change as a side effect of brand work.
- Keep admin UI consistent with the Terento palette and typography. Reuse
  existing semantic colors and components instead of creating an independent
  admin brand.
- Diagnostics may use technical terminology. Normal admin navigation and
  action labels should remain clear and outcome-oriented.
- Destructive, warning, success, and information states must remain explicit;
  never rely on color alone.
- Do not add external font or asset origins without reviewing CSP,
  deployment, privacy, and third-party notices.
- Isolate visual refactors from API or data-model refactors.
- Preserve current responsive behavior and action semantics.

The admin interface may remain denser and more operational than the public
website; it is not a public marketing surface.
