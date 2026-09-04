# Terento repository instructions

These are the repository-wide instructions for Codex and contributors. Keep
changes narrow, evidence-based, and consistent with the canonical documents
under `internal/` and the current release state.

## Mandatory reading for user-facing work

Before changing user-facing UI, public copy, CSS, admin UI, icons,
illustrations, screenshots, marketing documentation, or visual assets, read:

- `brand/BRAND_GUIDELINES.md`
- `brand/DESIGN_TOKENS.json`
- the nearest scoped `AGENTS.md`

Also inspect the current implementation before editing. Preserve current
layout and runtime behavior unless the task explicitly requests a change.

## Source precedence

Use this order when sources disagree:

1. `brand/logo/logo.svg` — canonical, immutable logo geometry.
2. `brand/DESIGN_TOKENS.json` — canonical numeric token values.
3. `brand/BRAND_GUIDELINES.md` — canonical usage, accessibility, voice, and
   product-truth rules.
4. Generated or platform-specific implementation files — implementations of
   the canonical sources; they must not redefine the brand.
5. Screenshots, mockups, boards, PDFs, and presentations — editorial
   references only, never implementation sources.

## Locked brand and product rules

- Never modify the canonical logo geometry or reinterpret its paths.
- Do not introduce new brand colors, fonts, or visual directions inside a
  feature task. Use approved semantic tokens instead of inventing raw colors.
- `Interactive Primary` is the only primary action family. `Warm Stone` is
  never a primary CTA.
- Instrument Sans is for brand, marketing, hero, and expressive headings;
  Inter is for UI, body text, labels, buttons, and information; JetBrains
  Mono is for diagnostics and technical identifiers only.
- Normal product UI describes outcomes, not MTP, IMG, USB object handles, or
  filesystem mechanics.
- Every status has explicit text and an icon; color is supporting information,
  never the only status signal.
- Public claims must match functionality available in the current release.
  Beta limitations must remain truthful.
- `internal/DEVICE_COMPATIBILITY.md` is the single source for the official
  exact-model compatibility criteria: `TESTING` (0), `TESTED` (1–2),
  `SUPPORTED` (3–4), and `VERIFIED` (5+). The current administrator-approved
  public rows come from `/admin` through the compatibility API; public pages,
  app/API copy, release notes, and reviews must not introduce another list or
  threshold.
- Do not reduce accessibility or keyboard focus behavior.
- Do not alter unrelated working behavior during visual or documentation
  work.

## Change discipline

- Prefer small, focused diffs and avoid opportunistic cleanup.
- Update tests when user-facing behavior changes.
- Preserve repository safety, privacy, licensing, device-ownership, and
  provider boundaries documented by the applicable canonical documents.
- Report intentional exceptions and unresolved limitations explicitly.
- Keep local machine or operator-specific instructions in the ignored
  `AGENTS.override.md`; never copy private infrastructure, credentials,
  secrets, or personal working instructions into tracked files.
