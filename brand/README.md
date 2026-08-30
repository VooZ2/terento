# Terento Brand Assets

This directory is the implementation baseline for the Terento visual identity.

## Start here

- `BRAND_GUIDELINES.md` — visual and usage rules
- `DESIGN_TOKENS.json` — machine-readable design tokens
- `tokens.css` — CSS custom properties
- `typography.md` — typography roles and licensing notes
- `accessibility.md` — validated contrast baseline

## Logo

Canonical geometry:

`logo/logo.svg`

**Do not edit its paths.**

Derived variants:

- `logo/logo-black.svg`
- `logo/logo-white.svg`
- `logo/logo-currentcolor.svg`

PNG assets in `logo/` are derived exports only.

## Locked identity

Core palette:

- Sky `#7898A8`
- Lichen `#9AA58B`
- Warm Stone `#B39A78`
- Alpine Off-White `#F7F3EC`
- Graphite `#222A2B`

Interactive:

- Primary `#577787`
- Hover `#4F6E7E`

Typography:

- Instrument Sans — marketing / brand headings
- Inter — UI / body
- JetBrains Mono — diagnostics only

## Scope

Exploratory preview boards are intentionally kept outside the public
repository. This directory contains only the approved identity baseline and
derived logo exports. Public-facing claims must match functionality available
in the current release; beta pages must state relevant platform,
compatibility, and feature limits, and future-state mockups are not proof of
shipped functionality.

## Source hierarchy

Use these sources in order:

1. `logo/logo.svg` for immutable logo geometry
2. `DESIGN_TOKENS.json` for numeric token values
3. `BRAND_GUIDELINES.md` for usage and intent
4. generated or platform-specific implementation files
5. screenshots, mockups, boards, PDFs, and presentations as human-facing
   references only

The canonical SVG and machine-readable token file outrank visual examples.
PDFs, presentation files, and screenshots must not be used to extract or
redefine implementation values, and the Brandbook is not an implementation
dependency.

## Implementation defaults

Spacing and radius values in the token files are explicitly marked provisional. The core logo, color family, typography roles, and accessibility derivatives are the validated identity decisions. Final spacing/radius tuning should happen in the real web/product implementation.

## Generated non-app outputs

`DESIGN_TOKENS.json` is the source of truth for shared brand values, including
the native app token output. Regenerate derived outputs with:

```sh
python3 scripts/generate-brand-tokens.py
python3 scripts/generate-brand-tokens.py --check
```

The generator owns `tokens.css`, the native app
`Views/DesignSystem/TerentoTokens.generated.swift`, the generated token block
in `site/styles.css`, and `admin_brand_tokens_generated.py`. Do not edit these
generated outputs manually. The app output is deterministic and checked for
drift by the same `--check` command.
