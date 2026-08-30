# Terento Brand Guidelines

Status: **Approved visual direction / implementation baseline**
Date: **2026-08-20**

Governance/editorial revision: **2026-08-30**. This revision clarifies source
precedence and release-neutral product-truth rules. The approved visual
identity values remain unchanged.

These guidelines capture the visual system validated in the four final Terento boards. They are intended to be used by Codex, designers, maintainers, and future contributors.

The visual identity is now implementation work, not an exploration round.

## Source of truth

Use the following precedence order:

1. `brand/logo/logo.svg` — canonical and immutable logo geometry.
2. `brand/DESIGN_TOKENS.json` — canonical numeric token values.
3. This document — canonical usage, accessibility, voice, and product-truth
   rules.
4. Generated or platform-specific implementation files — implementations of
   the canonical sources.
5. Screenshots, mockups, boards, PDFs, and presentations — editorial
   references only, never implementation sources.

The Brandbook PDF and presentation files are not implementation dependencies.

---

## 1. Brand foundation

**Brand:** Terento

**Core promise:**

> Your device, ready for where you're going.

**Product character:**

- effortless
- calm
- precise
- natural
- outdoor-aware
- premium
- contemporary
- light
- optimistic
- non-technical to normal users

**Visual direction:**

> Alpine / Nordic natural minimalism + macOS precision

Terento must not feel like generic SaaS, enterprise IT, an AI startup, health-tech, an eco startup, an outdoor clothing brand, or a developer utility.

---

## 2. Logo

### Canonical geometry

The canonical symbol is:

`brand/logo/logo.svg`

This file is the immutable geometry source.

Do not:

- redraw
- retrace
- smooth
- simplify
- reinterpret
- change path data
- change proportions
- alter the opening
- rotate
- stretch
- split-color the two masses
- add gradients
- add shadows, outlines, glows, or effects

Derived assets:

- `brand/logo/logo-black.svg`
- `brand/logo/logo-white.svg`
- `brand/logo/logo-currentcolor.svg`

PNG files are preview/export assets only and are not geometry sources.

### Wordmark

The current approved lockup uses the symbol with **Terento** typeset in Instrument Sans.

The symbol remains the canonical identity asset. A dedicated outlined wordmark SVG may be created later if required, but it must not alter the symbol.

### Clear space

Use generous neutral space around the symbol. As a practical minimum, reserve approximately **½ of the symbol width on all sides**.

### Minimum size

- hard minimum: **24 px** symbol height
- preferred UI minimum: **40 px**

Below 24 px, use only when technically necessary and validate the opening remains legible.

### macOS application icon

The macOS application icon uses only the canonical symbol above, without the
Terento wordmark or any additional map, GPS, Garmin, compass, landscape, or
decorative graphics. Its square background is Terento Sky (`#7898A8`) and the
symbol is Alpine Off-White (`#F7F3EC`). The symbol is optically centered with
generous breathing room; macOS supplies the native rounded-square presentation.

The checked-in renditions live in
`app/Terento/Assets.xcassets/AppIcon.appiconset/` and are reproducibly generated
by `Packaging/generate-app-icon.swift` from `brand/logo/logo.svg`. The generator
must not change the canonical path data, proportions, opening, or curves.

### Monochrome

The symbol must always work as:

- solid black on light backgrounds
- solid white on dark backgrounds

---

## 3. Core color system

### Terento Sky — `#7898A8`

Primary brand color.

Use for:

- primary logo color
- navigation accents
- selected informational accents
- diagrams
- large non-text brand areas

Avoid:

- normal-sized text on light backgrounds
- using Sky as the only color across the whole interface
- placing small white text directly on Sky when AA contrast is required

### Lichen — `#9AA58B`

Natural supporting color.

Use for:

- secondary accents
- supporting surfaces
- natural state cues
- subtle diagrams and illustrations

Avoid:

- primary CTA
- normal body text on light backgrounds
- making Terento look like an eco/wellness product

### Warm Stone — `#B39A78`

Restrained warm supporting accent.

Use for:

- secondary warmth
- dividers
- metadata
- diagrams
- photography relationships
- provider accents where appropriate

Avoid:

- primary CTA
- large dominant areas
- normal body text on light backgrounds

**Warm Stone is never a second primary CTA color.**

### Alpine Off-White — `#F7F3EC`

Primary light-mode canvas.

Use for:

- page background
- breathing room
- large neutral surfaces

Avoid:

- text on light surfaces
- replacing every elevated surface with the same tone

### Graphite — `#222A2B`

Primary text and dark-mode anchor.

Use for:

- primary body text
- headings
- dark-mode background
- high-contrast monochrome branding

Avoid:

- turning the entire light experience dark
- using pure black as a substitute without reason

### Interactive Primary — `#577787`

Functional action color.

Use for:

- primary CTA
- links that need stronger contrast
- focus
- progress
- selected borders
- important interactive UI

White text on this token is approximately **4.78:1** and meets WCAG AA for normal text.

### Interactive Hover — `#4F6E7E`

Hover / active interaction token.

White text contrast is approximately **5.43:1**.

---

## 4. Accessibility derivatives

The light core brand colors are not automatically suitable for normal text.

Approved functional derivatives:

| Role | Token | Purpose |
|---|---|---|
| Secondary text | `#6D706F` | normal-size secondary text |
| Lichen Dark | `#5F6D53` | accessible natural success / lichen text |
| Stone Dark | `#7B6246` | accessible warning / warm text |
| Error Rust | `#8A4F47` | accessible error text / destructive UI |
| Selected Tint | `#E7EEF1` | subtle selected background |

Validated contrast on Alpine Off-White:

- Graphite: **13.24:1**
- Secondary text: **4.52:1**
- Interactive Primary / focus family: **4.32–4.78:1**, depending on background/text pairing
- Interactive Hover with white: **5.43:1**
- Lichen Dark: **5.00:1**
- Stone Dark: **5.16:1**
- Error Rust: **5.77:1**

Color must never be the only carrier of success, warning, error, or information. Pair status color with icon and text.

---

## 5. Light mode

Light mode is the primary Terento experience.

Principles:

- Alpine Off-White is the main canvas.
- Elevated surfaces may be white or near-white.
- Graphite carries primary text.
- Sky, Lichen, and Warm Stone are supporting accents, not a colored-card system.
- Use space and hierarchy before using borders or fills.
- Do not create grey-on-grey enterprise UI.

Light mode should feel airy, natural, bright, and calm.

---

## 6. Dark mode

Dark mode is an independent natural extension of the same identity, not a simple inversion.

Use Graphite as the anchor.

The intended feeling is:

- forest shade
- wet stone
- evening mountain air

Avoid:

- navy SaaS
- purple-black AI aesthetics
- pure-black developer/terminal styling

Use the same interaction hierarchy. Functional dark-mode status colors may use lighter derivatives when required for text contrast.

---

## 7. Typography

### Instrument Sans — brand / marketing

Use for:

- hero
- H1–H3
- marketing statements
- brand-led editorial headings

Recommended scale:

| Role | Size / line | Weight |
|---|---:|---:|
| Hero | 64 / 70 px | 600 |
| H1 | 52 / 60 px | 600 |
| H2 | 40 / 48 px | 600 |
| H3 | 30 / 38 px | 500–600 |

Character: precise, open, human, contemporary, restrained.

### Inter — UI / body

Use for:

| Role | Size / line | Weight |
|---|---:|---:|
| UI heading | 22 / 28 px | 600 |
| Body | 17 / 26 px | 400 |
| Body small | 15 / 22 px | 400 |
| Label | 14 / 20 px | 500 |
| Button | 15 / 20 px | 600 |
| Caption | 13 / 18 px | 400 |

Inter should disappear into the product and prioritize clarity.

### JetBrains Mono — diagnostics only

Use for:

- logs
- diagnostics
- technical identifiers
- file names
- code-like content

Recommended:

- 13 / 20 px
- 400–500

Do not use monospace as a general visual-brand device.

---

## 8. UI behavior and component style

### Primary CTA

Use `Interactive Primary #577787` with white text.

Hover:

`Interactive Hover #4F6E7E`

Warm Stone is never used as an alternate primary CTA.

### Cards

Cards should be calm, generous, and neutral.

Use brand colors as small state or category accents rather than large saturated fills.

Suggested semantic accents:

- connected / success → Lichen family
- selected / information → Sky / Interactive family
- provider / natural metadata → Warm Stone where appropriate
- errors → Error Rust family

### Progress

Use:

- neutral pale track
- Interactive Primary fill

Progress should remain readable without animation or color alone.

### Focus

Keyboard focus must be visible. Use Interactive Primary or an accessible derivative with at least 3:1 non-text contrast against its adjacent surface.

---

## 9. Iconography

Direction:

- outline-first
- 24 px base
- approximately 1.75–2 px stroke
- soft but controlled corners
- filled variants only for compact status emphasis or selected states

Do not derive every icon from the Terento symbol.

Icons should feel precise, calm, and friendly.

---

## 10. Photography

Preferred subjects:

- alpine / glacier
- forest
- stone / stream
- highland terrain
- real outdoor environments in natural light

Photography is atmospheric support. Product UI remains the hero.

Avoid:

- AI fantasy mountains
- heavy color grading
- dramatic adventure clichés
- generic lifestyle hiking stock
- glowing futuristic maps

The palette should sit naturally beside real landscape colors without recoloring the photography to match the UI.

---

## 11. Product voice

Writing is:

- simple
- calm
- short
- outcome-first
- non-technical

Good:

> Connect your device.

> Choose where you're going.

> Ready.

Avoid surfacing implementation concepts such as MTP, IMG, `/GARMIN`, USB object handles, or provider internals in normal UI.

Technical detail belongs in diagnostics.

---

## 12. Website and product-truth claims

The final validation boards demonstrate the future product state. They are not proof that those features already exist.

Until the functionality is real and releasable, production `terento.app` must not imply that users can already download or use a working installer.

Examples such as:

- `Get Terento`
- “Terento keeps this map up to date automatically”

are approved design-copy examples for a future state, not automatic permission to publish those claims now.

Public-facing claims must match functionality available in the current
release. Beta pages must state relevant platform, compatibility, and feature
limits. Future-state mockups and validation copy are not proof of shipped
functionality.

Do not imply unsupported automatic updating, broad device support, or
availability. Do not understate functionality that is already publicly
released. Link to the project or repository when appropriate, and keep every
release-specific claim aligned with the current release metadata.

---

## 13. Brand discipline

Do:

- keep most surfaces neutral
- use Sky as the technological brand anchor
- let Lichen and Warm Stone provide natural context
- use Instrument Sans for expression
- use Inter for information density
- preserve strong light/dark equivalence
- keep the canonical SVG untouched

Do not:

- introduce vivid cyan, lime, neon, or purple
- use gradients as identity
- fill the marketing site with colored cards
- use light Sky/Lichen/Stone as small text on Off-White
- use Warm Stone as a second CTA
- redraw the logo for individual contexts
- add new fonts without a deliberate brand-system decision

---

## 14. Canonical asset structure

```text
brand/
├── BRAND_GUIDELINES.md
├── DESIGN_TOKENS.json
├── tokens.css
├── typography.md
├── accessibility.md
├── README.md
├── logo/
│   ├── logo.svg
│   ├── logo-black.svg
│   ├── logo-white.svg
│   ├── logo-currentcolor.svg
│   ├── logo-black-on-white.png
│   └── logo-white-on-black.png
```

The logo SVG is the only source of truth for symbol geometry.
