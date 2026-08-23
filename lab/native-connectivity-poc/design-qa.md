# Connect screen design QA

## Source visual truth

User-provided Garmin render reference supplied during design review.

The approved Terento visual direction remains the previously provided Connect
screen reference. This iteration implements the next Device workflow state.

## Implementation

Native SwiftUI screen in:

`Sources/TerentoPoC/Views/ConnectScreen.swift`

The target window is configured for an initial size of 1120 × 820 points.

## State

Initial light-mode Device state, with Connect completed and Device active.
The screen presents the known fēnix 8 test-device identity, read-only storage,
third-party map detection, and collapsed technical details.

## Evidence

- SwiftPM build: PASS.
- Static UI/component check: PASS; the requested Device components and
  `Back`/`Continue` actions are present.
- Resource bundle check: PASS; the canonical logo, Connect illustration, and
  cropped fēnix 8 render are included in the SwiftPM bundle.
- Desktop screenshot capture: BLOCKED. The current runtime reported
  `could not create image from display`, so there is no implementation
  screenshot to compare against the source at the same viewport.

## Required fidelity surfaces

- Fonts and typography: token families are requested when installed, with a
  macOS system fallback to avoid runtime errors when the fonts are not bundled.
- Spacing and layout: implemented from the supplied desktop reference with a
  fixed-width sidebar, top progress indicator, Device card, storage/map
  cards, accordion, and bottom navigation actions.
- Colors and tokens: implemented from the Terento brand token values.
- Image quality and asset fidelity: the bundled logo SVG is byte-identical to
  the canonical `brand/logo/logo.svg`; the fēnix 8 render is derived from the
  user-provided transparent PNG without changing the source asset.
- Copy and content: Connect, Device, Maps, Install, Complete, compatibility,
  storage, map state, technical details, Back, and Continue are represented.

## Findings

- No P0/P1/P2 findings could be verified without a rendered screenshot.
- Visual comparison remains incomplete because this headless runtime cannot
  capture the native display.

## final result: blocked

Blocker: native display capture is unavailable in the current environment.
