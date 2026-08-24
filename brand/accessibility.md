# Terento Accessibility Baseline

Status: validated visual baseline, 2026-08-20.

Target: **WCAG AA** for normal interface text and appropriate non-text contrast for interactive components.

## Validated contrast checks

Against the validated brand system:

| Check | Ratio | Result |
|---|---:|---|
| Graphite body text on Alpine Off-White | 13.24:1 | PASS |
| Secondary text `#6D706F` on Alpine Off-White | 4.52:1 | PASS |
| White on Interactive Primary `#577787` | 4.78:1 | PASS |
| White on Interactive Hover `#4F6E7E` | 5.43:1 | PASS |
| Focus family `#577787` vs Alpine Off-White | 4.32:1 | PASS for non-text |
| Lichen Dark `#5F6D53` on Alpine Off-White | 5.00:1 | PASS |
| Stone Dark `#7B6246` on Alpine Off-White | 5.16:1 | PASS |
| Error Rust `#8A4F47` on Alpine Off-White | 5.77:1 | PASS |
| Alpine Off-White on Graphite | 13.24:1 | PASS |
| Terento Sky `#7898A8` on Graphite | 4.78:1 | PASS |

## Core palette limitation

The following core brand colors are visual identity colors and are **not approved as normal-size body text on Alpine Off-White**:

- Terento Sky `#7898A8`
- Lichen `#9AA58B`
- Warm Stone `#B39A78`

Use the accessible functional derivatives instead.

## Status behavior

Never rely on color alone.

Every status should include:

- icon
- clear text label
- color as supporting information

Examples:

- success: icon + “Ready”
- warning: icon + descriptive warning
- error: icon + explicit error message
- information: info icon + explanatory text

## Focus

Keyboard focus must remain clearly visible.

Recommended:

- 3 px focus ring
- 3 px offset where layout permits
- use `#577787` in light mode
- use the lighter dark-mode focus derivative in dark mode

## Dark mode

Dark mode is not a simple inversion.

Test actual UI screens for:

- body text
- secondary text
- buttons
- status labels
- selected borders
- focus rings
- disabled controls

The dark status tokens in `DESIGN_TOKENS.json` are implementation derivatives chosen to maintain readable natural colors. Validate them again if their backgrounds change.

## Production requirement

Run automated and manual accessibility checks against the actual rendered website/product before release.

A token passing contrast in isolation does not guarantee the final component passes when opacity, compositing, imagery, or different surfaces are introduced.
