# beta.11 website provider update

The website presents Freizeitkarte, OpenTopoMap and MapRando in English,
German, French, Polish, Czech and Italian. General descriptions on Home,
About, Download, Guide and Compatibility use three-provider wording.
Provider cards, contour-specific guidance, Legal attribution and Privacy
connection recipients retain the relevant provider names.

MapRando benefits follow its official homepage:
https://ravenfeld.gitlab.io/open-garmin-map/
The copy describes hiking-oriented styling, small paths and trails, and regular
OpenStreetMap data updates without guaranteeing an update schedule.

The existing catalog-v3 projection supplies live counts. An explicit empty
provider list displays zero available packages; MapRando has no invented
static package count. Three compact cards fit on wide screens; the existing
keyboard-accessible scrolling row handles narrower screens. Changed assets
use version 20260911-three-providers-v2.

Home FAQ and Guide troubleshooting now describe beta.11's prefilled GitHub
report. Users still review reports before posting; email guidance asks for
watch model, map region and the observed problem.

Validation before publication:
- Site suite: 11/11 runners pass, including all six locale generators,
  structured data, Guide content, layout, API and accessibility contracts.
- Release documentation, Legal/Privacy and shared-brand checks pass.
- Browser checks: all six Home locales at 320px have three reachable provider
  cards, no page-width overflow, and no clipped card text. English/German
  desktop and French contour keyboard open/close were also checked.
- The initial empty MapRando API response was followed by 160 catalog entries,
  158 available. Counts are runtime data rather than a compatibility claim.

No native runtime, acquisition, device ownership or compatibility thresholds
change. This document records tested source, not publication evidence.
Publication acceptance additionally requires working release downloads,
production source parity and a live Rich Results Test. VoiceOver, native
200% zoom, forced-colors and a full performance audit are not claimed here.

Production cache follow-up: the first live check found the prior CSS/JS cached
under the v1 query. All changed asset references and deterministic contracts
now use v2, which must first be requested after the deployment completes.
