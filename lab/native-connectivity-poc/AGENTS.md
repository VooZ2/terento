# Terento macOS app instructions

These instructions supplement the repository-level `AGENTS.md` and apply to
the SwiftPM app module, its tests, developer tools, and resources under this
directory. The root instructions remain authoritative for product scope,
architecture, safety, documentation, and delivery.

## Stage 2 branch and review boundary

- All Stage 2 app work belongs on `release/beta.8` and its single draft PR
  into `beta`.
- Keep the draft PR current: commit narrowly, push the branch, and update the
  existing draft PR. Do not open an overlapping app PR or merge this branch.
- Stage 2A is governance only. Do not change app runtime code, resources,
  screenshots, Xcode packaging, release metadata, or version numbers here.
- Intermediate Stage 2 work is not a release. Do not create tags, GitHub
  Releases, DMG/ZIP/notarized artifacts, update manifests, public downloads,
  or website announcements.

## Current app baseline

The current native macOS experience is intentionally calm and outcome-first.
Preserve the existing SwiftUI structure and workflow:

- sidebar navigation: `Device`, `Install maps`, `Manage maps`, `About`;
- the current connect, install, manage, update, troubleshooting, and About
  journeys;
- the established hierarchy, density, proportions, neutral surfaces,
  controls, and native macOS interaction model.

The user should see a finished Terento version of this product, not a new
product concept. Do not move the app to a new architecture or source layout
as part of visual work.

## Refinement boundary

Small, evidence-based refinements are allowed when they preserve the baseline:
alignment, spacing, padding, wrapping, typography application, icon sizing,
badges, button hierarchy, status presentation, corner radii, separators,
selected/hover/focus states, empty states, and accessibility polish.

Stop and report the problem, proposed change, user impact, functional risk,
and why a smaller refinement is insufficient before making any change that
would:

- replace the sidebar or information architecture;
- change primary actions, onboarding, the dashboard/home concept, or the
  Install maps workflow;
- introduce a new card-heavy density or visual language;
- add brand colors, fonts, logo variants, gradients, glassmorphism, heavy
  blur, prominent outdoor decoration, or SaaS-dashboard styling;
- add dark mode or remove the forced light presentation; or
- change confirmation, destructive-action, ownership, or safety behavior.

Major redesign approval is a separate decision gate. Default to a small
refinement when the goal can be met without crossing this boundary.

## Brand, typography, and accessibility

- Reuse existing `TerentoColors`, typography helpers, and components. Do not
  invent local color or font systems.
- Keep the locked brand palette: Sky `#7898A8`, Lichen `#9AA58B`, Warm Stone
  `#B39A78`, Off-White `#F7F3EC`, and Graphite `#222A2B`. Warm Stone is not a
  primary CTA color; surfaces should remain neutral.
- Keep the current Instrument Sans / Inter / JetBrains Mono roles. Changing
  app font loading or replacing the established font system needs a separate
  reviewed task.
- Preserve `.preferredColorScheme(.light)`. Do not add partial dark-mode
  support, isolated system-appearance overrides, or appearance-dependent
  styling.
- Status must not rely on color alone; retain icon + text + color. Preserve
  VoiceOver labels, keyboard navigation and focus, reduced-motion behavior,
  and clear enabled/disabled states.
- Keep normal UI outcome-oriented. MTP, IMG, filesystem, and transport terms
  belong in diagnostics/developer context, not primary user flows.

## Functional freeze and SwiftUI safety

Visual or structural polish must not change `DeviceEngine`, `MapEngine`, map
lifecycle, compatibility, MTP transport, ownership rules, safe install/update
sequencing, backup/remove behavior, telemetry/privacy consent, networking, or
API contracts. Do not use a visual task to repair or refactor those systems.

Preserve state ownership and behavior while editing SwiftUI: property
wrappers, bindings, focus state, environment values, tasks, `onAppear`,
`onChange`, actions, disabled conditions, accessibility modifiers, navigation,
and lifecycle timing. Do not relocate state merely for cleanup. Reuse an
existing component before introducing a new abstraction, and do not replace a
native control without an explicit reviewed reason.

## Resources, versions, and validation

- Do not update app screenshots, AppIcon, logo assets, or other app resources
  during Stage 2A. Later screenshot changes remain review-only until release
  freeze.
- Do not change `CFBundleVersion`, version labels, distribution metadata, or
  update behavior during intermediate Stage 2 work.
- Classify validation by risk: governance-only checks are sufficient for
  documentation changes; visual/refactor changes require an app build and
  affected tests; user-visible behavior changes require focused behavior
  validation; device/write-path changes require the relevant hardware gate.
- For every change, run `git diff --check`, review the changed-file list, and
  state explicitly whether runtime, resources, release, and deployment files
  were untouched. Do not run destructive hardware tests for visual work.
