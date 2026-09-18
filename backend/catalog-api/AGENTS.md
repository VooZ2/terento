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

Before changing Terento Admin UI or statistics, search the canonical Admin and
statistics contracts for every touched concept. If a newer explicit owner rule
supersedes older prose, update or remove the older rule in the same change
rather than appending a conflicting definition; keep one canonical definition
per behavior and update any regression tests that encode superseded behavior
with the rule. Do not keep contradictory legacy guidance for compatibility.
Explicit current Admin UI invariants in `docs/admin-behavior-contract.md` take
precedence over older generic presentation wording.
Statistical populations and formulas remain canonical in
`contracts/STATISTICS_CONTRACT.md`; this contract owns Admin presentation only.

The admin interface may remain denser and more operational than the public
website; it is not a public marketing surface.
