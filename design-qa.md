# Terento final Home simplification QA

## Source visual truth

- `/Users/gediminas/Downloads/terento-public-screenshots-no-titlebar/your-garmin.png`
- `/Users/gediminas/Downloads/terento-public-screenshots-no-titlebar/install-maps.png`
- `/Users/gediminas/Downloads/terento-public-screenshots-no-titlebar/ready-to-install.png`
- `/Users/gediminas/Downloads/terento-public-screenshots-no-titlebar/installing-maps.png`
- `/Users/gediminas/Downloads/terento-public-screenshots-no-titlebar/manage-maps.png`

The supplied no-titlebar masters were compared at asset level with the
rendered home-page showcase. They contain only the Terento app surface; the
page adds one restrained Terento frame, spacing, and responsive presentation.

## Rendered implementation evidence

- Desktop: `/private/tmp/terento-home-no-built-with-care-desktop-1440.png` (1440×900 viewport,
  device scale 1)
- Mobile: `/private/tmp/terento-home-no-built-with-care-mobile-390.png` (390×844 viewport,
  device scale 1)
- Local URL: `http://localhost:4174/`

## Verification state

- Theme: light Terento public site
- Desktop viewport: 1440×900 CSS px
- Mobile viewports checked: 320×844, 360×844, 375×844, 390×844, 430×844
- Images: hero plus two Home feature screenshots are rendered from the
  no-titlebar masters; Ready to install and Installing maps derivatives remain
  available but are intentionally not referenced by Home. All derivatives use
  AVIF/WebP sources and a 1600px PNG fallback; hero eager, feature screenshots
  lazy
- Interactions: mobile Menu opens with `aria-expanded="true"`; canonical
  Compatibility and Download links resolve in the local preview; FAQ contains
  six product-focused disclosure items
- Console: no browser errors observed during the local checks
- Layout: no horizontal overflow at any checked viewport

## Full-view comparison evidence

The desktop and mobile captures show the unchanged hero hierarchy, concise
Connect → Install → Go workflow, only the Install maps and Manage maps proof,
Beta scope, FAQ, final download CTA, and footer. The Built with care section
and its compatibility card are absent; the source app surfaces remain legible
at desktop and fit inside the content frame on mobile without cropping or
stretching.

## Focused region comparison evidence

Focused checks were made for the supplied `your-garmin`, `install-maps`, and
`manage-maps` assets, including their clean app-only crop, sharpness, source
selection, alt text, and responsive dimensions. The two feature screenshot
frames measured 671px wide at the 1440px desktop viewport and 337px wide at
390px mobile; the hero remained intentionally larger at 649px desktop. No
focused-region mismatch remained.

## Findings

No actionable P0, P1, or P2 findings remain.

### Required fidelity surfaces

- Fonts and typography: existing Terento display/body font stack and hierarchy
  remain intact; screenshot text stays inside the supplied raster assets.
- Spacing and layout rhythm: showcase grids become one column below 1099px;
  mobile frames use the full available content width without overflow.
- Colors and visual tokens: existing Terento off-white, graphite, muted
  surface, border, and blue/green accents are reused.
- Image quality and asset fidelity: only the five final supplied masters are
  used; optimized AVIF/WebP/PNG variants retain the source content.
- Copy and content: hero, scope, trust, FAQ, and CTA copy is factual and keeps
  compatibility model-specific; internal transport terms are not exposed.

## Comparison history

1. Initial local integration: verified that all five final masters render in
   the requested workflow and that the hero has an eager source.
2. Optimization pass: removed intermediate PNG fallbacks, keeping AVIF/WebP
   at four responsive widths and a 1600px PNG fallback; rechecked source
   selection and visual sharpness.
3. Home simplification pass: removed the Ready to install and Installing maps
   Home sections without deleting their assets, kept only Install maps and
   Manage maps, and replaced the scope card wording with `Free and
   open-source`.
4. Home trust-section removal: removed the full Built with care section and
   normalized the Beta scope → FAQ transition without duplicating its content.
5. Responsive pass: checked 320–430px widths, opened mobile navigation, and
   confirmed no horizontal overflow. No P0/P1/P2 fix was outstanding after
   this pass.

## Implementation checklist

- [x] Final no-titlebar screenshot masters copied to local asset directory
- [x] Responsive AVIF/WebP/PNG variants generated without upscaling
- [x] Hero screenshot eager-loaded with explicit dimensions
- [x] Below-fold screenshots lazy-loaded with meaningful alt text
- [x] Social card generated at 1200×630 and metadata updated
- [x] Desktop and mobile browser checks completed
- [x] No VPS publication, commit, or push performed

## Final polish notes

- [x] A single `.app-shot` system now controls border, 16px radius, subtle
  shadow, shared max-width modifiers, and image sizing for hero and features.
- [x] Home keeps only Install maps and Manage maps as the two feature sections;
  both retain the same feature column and visual weight.
- [x] The Home flow is Hero → Connect → Install → Go → Install maps → Manage
  maps → Beta scope → FAQ → Final CTA → Footer; the Built with care section
  and all of its content are removed and not duplicated elsewhere.
- [x] The final CTA uses the existing `.download-action` primary button style,
  is a single left-aligned column directly below its copy, and stacks naturally
  on mobile with exact text `Download the beta`.
- [x] Home is noticeably shorter and has no leftover walkthrough spacing.
- [x] No fake title bars, traffic lights, browser chrome, or background art
  were added.
- [x] `README.md` was updated locally after this QA; no GitHub publication was performed.

final result: passed
