# Terento macOS app instructions

These instructions supplement the repository-level `AGENTS.md` and apply to
the SwiftPM app module, its tests, developer tools, and resources under this
`app/TerentoCore/` directory. The root instructions remain authoritative for product scope,
architecture, safety, documentation, and delivery.

## Current module and review boundary

- The production app is the root Xcode target; this directory remains the
  SwiftPM source module and native regression harness consumed by that target.
- The current beta release is maintained through the repository release
  manifest, release notes, and the public successful-install compatibility
  results. Do not use an old beta branch, draft PR, or local artifact as the
  current status source. A missing public result does not prove another Garmin
  model is unsupported.
- Active providers are Freizeitkarte, OpenTopoMap, MapRando and BBBike through
  the shared lifecycle. BBBike and BBBike (Ontrail) are two map types of one
  provider. Source-validated OpenTopoMap contours are an optional public add-on.
  Registration and successful tests do not grant broad device compatibility.
- Do not change app runtime code, resources, screenshots, Xcode packaging,
  release metadata, or version numbers as incidental cleanup. Functional
  changes require their own reviewed scope and test evidence.
- Release artifacts, public downloads, and website announcements are created
  only through the documented release workflow after all release gates pass.

## Current app baseline

The current native macOS experience is intentionally calm and outcome-first.
Preserve the existing SwiftUI structure and workflow:

- sidebar navigation: `Device`, `Install maps`, `Manage maps`;
- one complete About window via `Terento → About Terento`;
- the current connect, install, manage, update, troubleshooting, and About
  journeys;
- the established hierarchy, density, proportions, neutral surfaces,
  controls, and native macOS interaction model.

The user should see a finished Terento version of this product, not a new
product concept. Do not move the app to a new architecture or source layout
as part of visual work.

Provider selection, custom `.img` import, external single-map Remove,
ownership presentation, and safety confirmations are current functionality
and must retain their reviewed boundaries. A new information architecture or
runtime behavior still requires a separate reviewed decision.

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

The functional Map Manager scope is intentionally outside visual refinement.
Provider selection, custom `.img` import, external single-map Remove,
ownership presentation, and safety confirmations are reviewed functionality;
any change to their boundaries requires its own UI/UX and safety decision.

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
  during documentation-only work. Screenshot changes remain part of a
  reviewed application release.
- Do not change `CFBundleVersion`, version labels, distribution metadata, or
  update behavior during an intermediate task unless the task is explicitly a
  release preparation.
- Classify validation by risk: governance-only checks are sufficient for
  documentation changes; visual/refactor changes require an app build and
  affected tests; user-visible behavior changes require focused behavior
  validation; device/write-path changes require the relevant hardware gate.
- For every change, run `git diff --check`, review the changed-file list, and
  state explicitly whether runtime, resources, release, and deployment files
  were untouched. Do not run destructive hardware tests for visual work.

## Device content checks

Fast removal and fast Safe Update rely on a recorded `removalProof` (32
regions of 65,535 bytes plus SHA-256, format 1) bound to the manifest entry's
size and SHA-256. Keep these invariants; `app/TerentoCore/README.md` describes
the behavior:

- The check method is chosen from the local record before any device read and
  is never switched afterwards. A sampled mismatch blocks exactly like a full
  SHA-256 mismatch; never add a fallback to the other method.
- Entries without a valid bound proof, external maps and legacy entries keep
  the full read and SHA-256. Never synthesize a proof for a map Terento did not
  write and verify.
- The new map in an Update is verified with the fresh-install sampled
  read-back (`SampledReadBackPlan`) before the old map is touched.
- The residual limit (a same-name, same-size map that differs only outside the
  compared regions) is documented and accepted; do not widen it.
- Changes here need the native fake-libmtp runners
  (`run-native-removal-proof-tests.sh`, `run-native-fast-update-tests.sh`,
  `run-native-map-profile-contract-tests.sh`) and a real-watch check before
  release. Real-watch status is recorded in `RELEASE_NOTES.md` KNOWN ISSUES.

Local test builds use the `-local` release label (Debug
`TERENTO_RELEASE_LABEL`), so their telemetry is stored as test data and
excluded from statistics. Never distribute a `-local` build.

## Documentation impact

Any durable or user-visible app workflow or functionality change must review
`app/TerentoCore/README.md`, the root `README.md` when the public product
description changes, relevant website/help text when the user journey changes,
and `RELEASE_NOTES.md` when the change ships in a public release. Internal
refactors with no durable or user-visible effect do not require documentation
noise.
