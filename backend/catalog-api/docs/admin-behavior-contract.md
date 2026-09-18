# Administration, statistics and diagnostic behavior contract

This is the canonical behavioral contract for the private Terento admin surface
and its diagnostic data dependencies. It complements `api.md` (routes and current
implementation) and the exact-model compatibility policy. Read it before changing
client diagnostic delivery, intake, aggregate queries, admin navigation or UI.

Requirements below are acceptance criteria, not a claim that every criterion is
implemented. Publication success and passing unit tests alone do not establish
that an operator workflow works. Known gaps are listed at the end.

## Operator outcome

Within 5–10 seconds, an operator opening a failure must understand what failed,
which model/variant is known, when it happened, the map/provider, whether action
is needed and what action is available. Technical identifiers and source checks
belong in expandable details. Progressive disclosure must preserve access to
information and actions; visual simplification must not silently remove them.

## Data and identity

- A map-use event describes a download or map operation. It is not device
  identity evidence and does not carry the watch model or native diagnostic log.
- A compatibility diagnostic describes a retained per-map result with reported
  device identity, stage/code and available bounded technical observations.
- A random operation ID links a session; it is not a user or unique-watch ID.
  One session can contain several maps and optional components. Map-result
  identity uses `operationId + mapResultIndex` when available, together with
  package/map, provider/region and component facts. `operationId` alone is not
  a map-result identity, and provider + region alone cannot distinguish two
  different custom IMG results.
- Correlation must include operation and provider/map-region identity. A failure
  for one map must not be consumed by another map's report in the same batch.
  Only validated provider-specific aliases may equate region names.
- Preserve received identity, reviewed identity and unknown values distinctly.
  Missing evidence is not false, success, or a guessed model. Catalog labels and
  images may enrich an established exact identity, not establish it by themselves.
- Do not rewrite original reports to make counters or identity look consistent.
  Administrator decisions must be scoped and auditable. Existing session-wide
  actions must show their affected results; an action must not silently expand
  its scope to other operations, models or maps.

## Diagnostic delivery contract

While compatibility sharing is enabled, each completed per-map result must be
recorded through the existing durable local outbox independently of screen
rendering, navigation or the lifetime of a SwiftUI view. Retain the operation's
identity/context until its diagnostic result is recorded. A disconnect or UI
reset must not erase an already available failure observation before recording.

Preserve failure, not-started and cancellation semantics; record only facts the
operation actually observed. Never manufacture a terminal result, writeStarted,
transfer completion, failure cause or identity to fill a telemetry gap. Preserve
per-map results in partial batches. Retries/replayed event IDs must not increase
counts or create duplicate review items. Sharing controls remain independent and
must be honored; delivery must never block or change installation/removal safety.

Intake must make stored, duplicate and rejected delivery distinguishable. Safe
correlation uses bounded validated random report/session IDs and reason codes.
Do not retain raw rejected payloads, credentials, Unit IDs, serial numbers, local
paths or binaries. Raw native logs remain local; an admin technical-details view
shows only received structured fields. Missing data must be labelled unavailable.

## Counting and lifecycle

| Concept | Required interpretation |
| --- | --- |
| Installation result | One retained per-map result, not a watch, tester, whole batch or component phase. Custom IMG results belong in compatibility accounting. |
| Acquisition result | One terminal provider acquisition identified by `acquisition_id` plus known operation, provider, package and component facts where available. Without that ID, lifecycle pairing uses operation + provider + package + component; sibling components never close another acquisition. Started/processing/cancelled/interrupted phases are history, not completed acquisition attempts. |
| Map update result | `MAP_UPDATE_SUCCEEDED` or `MAP_UPDATE_FAILED` is one replacement of an already installed Terento-owned provider map. It is not a new installation and is excluded from installation totals, coverage, and popularity counts. |
| Success | SUCCEEDED with VERIFIED finishing; no success inferred from download completion or missing errors. |
| Failed result | Recorded final failure; never a compatibility promotion. Preserve historical failed/attempt totals after resolution. |
| Not started / cancellation | Not a successful or failed completed install merely because a later map was skipped or the user cancelled. Preserve the recorded distinction. |
| Open error | Active actionable diagnostic; resolution removes it from open work, not historical failure totals. |
| Identity review | Device identity requires a decision; distinct from an installation failure and from publication approval. |
| Missing diagnostic | Map event lacks matching device diagnostic evidence. It cannot supply model-specific counts or public compatibility evidence by guessing. |
| Public compatibility | Exact approved model/variant, retained verified successes and existing promotion/publication rules. No family-wide inference or promotion from map statistics. |

The compatibility denominator includes only retained verified successes and
failures for which writing actually started, plus the explicitly documented
legacy fallback when the write fact is absent. A current `writeStarted=false`
result is a pre-install result, not a failed installation attempt; its stage and
reason remain visible in diagnostics, but it does not enter fresh-install
attempts, failures or success rates. A current missing write fact is unknown and
is not guessed. Overview's map-event fallback projects only a verified success
or a failure with writing started, so Recent map activity and the installations
chart do not turn a download/preflight failure into a fresh-install failure.

Counts use full retained history, not the currently loaded page, top-N list or
bounded detail query. Resolution, pagination and formatting changes must not
silently reset counts. Data retention is governed by the existing retention
policy; “history” does not mean indefinite retention. Local-test telemetry stays
outside production/public totals and has its own explicit admin scope.

Each metric must have a stable definition: source, unit, outcome eligibility,
time window, test exclusion and deduplication. Views using the same population
must agree. Different populations must be named so a difference is explainable.
The canonical formulas and population boundaries live in
[`contracts/STATISTICS_CONTRACT.md`](../../../contracts/STATISTICS_CONTRACT.md);
this document governs the admin workflow that presents them. Do not force
equality by inventing data. Missing/unavailable measurements use an em dash,
while a measured zero is 0.

## Page and navigation behavior

### Overview and Review queue

Period-filtered KPIs describe the selected period. Review queue covers unresolved
work across all dates. Keep that scope explicit. Show failures, linked issue work,
identity/publication review and provider/system problems as distinct work types.
Counts and list links must lead to the corresponding work, even when the preview
is truncated. Empty active work does not mean there have been no failures.

The section title is `Review queue`; its total counts pending review tasks. A failed
diagnostic and GitHub handling linked to the same operation are alternative
states of one task; linking an issue moves the task between categories and
does not increase the total. Identity review is an additional task and
publication review is counted per exact model. The queue groups operation work,
not unique GitHub incidents, and resolved work is excluded. If the query fails,
the queue is unavailable rather than zero. Actions opened from an operation
task retain that operation-level diagnostic scope; per-map installation history
remains separate in the statistics read model.

A received device failure must lead to its actionable diagnostic context with
model/variant, available watch image, provider/map, time, result and known reason.
It must not be redirected to aggregate Map statistics as a substitute.

When a provider acquisition fails before writing starts
(`write_started=false` with `failure_stage=download` or
`INSTALL_BLOCKED_DOWNLOAD_FAILED`), it is activity/history only. Show it as a
failed download and do not create an installation failure diagnostic, Review
queue task, open-error count, or identity-review task for it. Connection and
provider acquisition failures are not operator bugs by default. The original
diagnostic and map-event records remain available; an explicitly linked GitHub
issue remains its own operator-created workflow.

The same pre-install classification is used by all Admin read models:
`PRE-INSTALL` / `NOT_STARTED` is absent from Map installations, device/model
installation counts, fresh-install rates, and open errors. It remains in Map
statistics and Recent map activity. A stale `DOWNLOAD_STARTED` or
`DOWNLOAD_PROCESSING` phase without a correlated terminal event is shown as
missing/unresolved after four hours; it is not converted into `FAILED`,
`INTERRUPTED`, an acquisition failure, or an installation issue.

When only a map failure exists, keep the gap visible and clearly say the device
report is unavailable. A statistics link is supplementary, not diagnostic
resolution. A complete unknown-device workflow must expose only supported,
audited actions and reconcile later reports without duplicating history. Do not
present that workflow, watch assignment or GitHub actions as available before
implemented. Never borrow a model from another user or nearby timestamp.

### Installations, device history and Diagnostic detail

All/Failed/Open errors/Successful/Identity review filters have separate meanings.
Failed history includes resolved failures; Open errors excludes resolved work.
Known exact identities group consistently across list, card, detail and statistics.
Unknown identities remain discoverable rather than disappearing from the UI.

Detail must retain supported actions: inspect received technical evidence,
review/correct identity with an audit trail, create or link a GitHub issue, inspect
linked issue/workflow, and resolve/reopen under existing rules. Creating an issue
requires the existing explicit operator action; do not publish issues as a test.
Issue synchronization changes workflow status, not the historical install result.
A source-mapping review is not an automatic historical installation reassignment.

Use the canonical model name and a consistent variant order: case size, display,
then features such as Solar/inReach when known. No specifications may be inferred
merely to fill a visual gap. Cards and tables must use the same reviewed values.

Historical catalog provenance in device and installation tables uses a small
Font Awesome Free solid `box-archive` icon beside the model. Its “Historical catalog entry” text stays
in the accessible link name and appears on icon hover or model-link keyboard
focus. This marker does not change support, specifications or installation
authorization; the device detail retains the explicit provenance label.

### Map statistics and downloads

Distinguish download phases, download outcomes and installation outcomes. Missing
a terminal download event is unknown, not succeeded. Lifecycle phases must not
multiply completed-download or installation counts. A grouped statistics row is
not an individual diagnostic and must not be offered as its replacement.

A chart, total, filter and table that claim the same period/population must agree;
cumulative totals must be labelled separately. Apply the selected time zone
consistently. History remains accessible with compact, aligned rows and explicit
status text; icons/color supplement rather than replace meaning. Download history
uses original Font Awesome solid hourglass-start (Started), spinner (Processing)
and hourglass-end (Succeeded). These historical phase icons stay static, so past
processing does not imply an operation is still running. The activity title itself
expands the timeline; no separate Download history row is shown. The map/provider
link remains visible below the title. Started and the terminal result show their
recorded timestamps in the selected timezone; Processing shows total elapsed time
from start to terminal result, or an em dash if either is missing or inconsistent.
This duration includes the whole acquisition, not just unpacking/checking.

Map-statistics population filters are provider, map, region, and date. Event
type, outcome, and detail pagination affect only the Event detail disclosure;
they do not recalculate KPI totals, success rates, coverage, or popularity.
The initial HTML and asynchronous response must use the same server summary.
Per-map diagnostic coverage is reliably linked fresh-map attempts divided by
all selected fresh-map attempts. A linked message is not synonymous with a
successful message, and an absent message is an observation gap, not a failed
install. Session totals are separate.

The visible Map statistics KPI summary is one compact container. On wide
layouts it has equal Downloads, Fresh installs, and Updates groups, with
Successful and Success rate on the first row and Failed below in each group.
Diagnostic coverage is a compact secondary row in the same container with
Fresh attempts, Linked reports, Report gaps, and Coverage rate. A positive
Failed value uses the same semantic error token as Open errors; zero is neutral
and an unavailable value is shown as an em dash. These are presentation rules
only; the existing summary counts and formulas remain authoritative.

Popular maps uses only successful fresh main-map installs for known provider
catalog packages. Custom images, optional components, updates, and downloads
are excluded before grouping and sorting. Top 5 and Regions group by canonical
country/region across providers; Top 5 keeps five eligible rows and Regions
shows the full grouped list. All maps groups by canonical country/region and
provider. Each row keeps the last eligible fresh-install timestamp; All maps
also shows the provider. Search is applied to the complete All maps set before
pagination, and view navigation does not change the selected population. The
three views share compact list geometry and use bottom navigation buttons.

The Activity by provider table labels its final column Last install. It shows
the latest successful fresh-install timestamp in the selected scope and
timezone, or an em dash when none exists; updates, downloads, and provider
health checks do not advance it. Admin tables keep descriptive text and dates
left-aligned, counters and percentages centered, and status badges centered,
with column headers aligned to their values. Sort controls retain their
keyboard, focus, and `aria-sort` behavior. The Providers table shows the health
badge without an additional “Latest check state” helper when no error exists.

Activity by provider keeps acquisition and installation populations independent:
successful installs are not synthesized from downloads, downloads are not
synthesized from installs, and `Installs > Downloads` is valid when the two
telemetry streams are incomplete. Install success remains
`F_success / (F_success + F_failed)`, while download success is terminal
`DOWNLOAD_SUCCEEDED / (DOWNLOAD_SUCCEEDED + DOWNLOAD_FAILED)`; started,
processing, cancelled, interrupted, stale, and missing outcomes are excluded
from the latter denominator.

The GitHub chart says `Observed download increases between checks`. In the 24h
view each visual point uses the full-hour `hour_start` bucket while retaining
the exact observation timestamp for context. It starts
with a baseline and preserves valid zero increases. Historical counter deltas
whose observations lack the new population metadata remain visible as legacy
or unverified deltas; missing metadata alone is not a discontinuity. A counter
decrease or confirmed population change remains unknown/discontinuous. Missing
check gaps and period-boundary intervals retain the previous and actual
`observed_at` values, are marked uncertain, and are never filled with zero or
used to spread a delta across the gap. Daily/monthly buckets with known values
and unknown intervals are marked partial. Failed collection keeps the last
successful observation and timestamp.

The GitHub downloads bar chart keeps zero-valued intervals in its data and time
axis, but does not render `.dmg` or `.zip` zero values as extra circles or
repeated zero symbols. Zero information remains available through the interval
tooltip/accessibility label. Unknown, missing, partial, legacy, and
discontinuity semantics remain unchanged.

Admin scrollbars are visually hidden in existing scrollable regions while the
regions remain scrollable with wheel, trackpad, touch, keyboard, and horizontal
table interaction. Hiding the scrollbar must not clip content, disable focus,
change overflow behavior, or add scrolling to a view that was not already
scrollable.

Average download time, when exposed by an Admin provider statistic, uses only
eligible successful main acquisitions with one trustworthy Started →
Processing → Succeeded sequence for the same acquisition, operation, provider,
package, and component. It measures Processing minus Started, excludes failed,
cancelled, interrupted, contours, custom, local-test, missing, conflicting and
legacy-incomplete sequences, aggregates the full selected population rather
than paginated activity, and rounds only the final raw-seconds average.

## Identity Review operator-assisted assignment addendum (2026-09-17)

Identity Review is an operator-assisted model-selection workflow, not a
mandatory all-evidence form. Its 10–15 second outcome is: see the reported
device, see the available facts, confirm the suggested exact catalog model, or
choose another exact variant. Missing facts remain visible and do not by
themselves block an explicit manual catalog selection.

The compact review shows one `Reported device` value and six fact cards:
`Model`, `Case size`, `Display`, `Solar`, `inReach`, and `Device codes`.
Facts retain their provenance as `Reported`, `From mapping`, `From catalog`, or
`Not confirmed`; `No`, `Not confirmed`, and an unavailable value must not be
collapsed into one another. Catalog-derived facts are allowed only when the
independently reported model/variant and the catalog specifications identify a
consistent exact target. A selected catalog ID is never fed back as evidence
for its own assessment. The legacy `displayType=Solar` value is Solar evidence
only, not a screen technology; MIP/AMOLED/MicroLED are screen values and Solar
and inReach are separate feature values.

One non-conflicting candidate may be suggested and shown with the active
`Confirm`/`Edit` path. Multiple candidates show `Select variant`. The picker is
one exact-ID search/list mechanism that supports mouse, touch, arrow keys,
Enter, and Escape; typing after a selection clears the hidden ID. The server
must validate the selected Garmin catalog ID and preserve the previous result
scope. The canonical UI key is
`result:<operation UUID>:<mapResultIndex>` and index `0` is valid. It selects
only that result, including for Review queue, Installations and device history.
A raw operation UUID remains an explicit operation-level batch scope only when
the operator submits that scope intentionally. Legacy event keys match only
their exact legacy row. No scope may fall back from a missing result to the
whole operation.

An ordinary `Confirm` is blocked when selected and independently reported facts
conflict. The separate explicit `Confirm manual assignment` action is the only
way to override that conflict. It records an automatic audit containing the
administrator, time, exact scope, previous/new identities, decision type, safe
facts, missing facts and conflicts. Identity confirmation needs no reason or
review note. A missing selection, unknown catalog ID, missing diagnostic and
identity conflict are distinct errors; failures preserve the selection and do
not claim that a successful database write was not saved. Repeating an
identical decision is idempotent. Identity decisions never alter installation
outcomes, device files, map statistics, telemetry fields or publication state.
Late corrections update only the selected result(s) and retain the previous/new
identity audit trail. Existing source-correction and mapping-review controls
remain available in technical/admin workflows; they are not duplicated in the
compact confirmation form.

The shared implementation is in `identity_assessment.py` (safe observations,
catalog-derived facts and conflict checks), `db.py` (strict result scope,
validated persistence and audit), `admin.py` (compact review and diagnostic
detail dialog), and `http_api.py` (specific error responses and safe redirects).
The Diagnostic detail dialog keeps the date, result, map/region, app version,
failure or success state, issue/lifecycle actions and one collapsed Technical
details section, with a single Identity Review section and one secondary
technical disclosure. The daily review does not render a separate `Technical
identity details` or candidate table; safe raw diagnostic fields remain only
in that single diagnostic-level `Technical details` disclosure. A successful
result with pending identity is not a failure. On desktop, the `Resolve
diagnostic` lifecycle card and the selected/choose catalog-model card are
siblings in the diagnostic action grid, each using one half of the row; the
grid becomes one column at the mobile breakpoint.

### Providers and collection history

Separate provider health, collection outcome, available packages and broken
artifacts. A successful metadata collection is not proof of device compatibility
or a completed user download. Updates count newly discovered plus changed map
packages for that run, with the components explained; do not count every artifact
as a new map. Unknown historical counts remain unknown, not zero. Technical
source/review controls remain accessible behind clearly labelled disclosures.

Provider `Problems` has separate counts: unique current affected packages and
unique problematic source identities. Two broken artifacts in one package are
one affected package; one source used by two packages is one problematic source
and two packages. The latest provider health state/error is separate and does
not become a package/source problem. Counts use the complete current catalog,
not the first page or a preview, and retired/resolved historical entries are
excluded.

All admin statistics preserve the distinction between a measured zero,
unknown/unavailable, stale, and partial data. Do not use truthiness or
cross-unit fallbacks to turn missing values into zero; `false` remains `No`.
A successful empty map-statistics population is `0 recorded events` with
zero terminal attempts and an unavailable (`—`) success rate, not an error or
evidence that nobody used the app.

## Mandatory change and release gate

For changes affecting this contract:

1. State the affected populations, routes, actions and delivery stages. Compare
   behavior with the last working version; preserve existing supported workflows.
2. Test representative structured reports through intake, storage/read models,
   queue, exact-device history, statistics and detail actions. Validator-only or
   screenshot-only tests are insufficient for cross-layer changes.
3. Cover write/pre-write failures, verification failure, partial batches and
   not-started maps; active/resolved/reopened states; known/unknown identity;
   missing/late/out-of-order reports; retries; disabled sharing; local-test data;
   pagination/time-zone boundaries. UI-lifetime delivery changes also require
   tests for navigation, state reset and disconnect during diagnostic recording.
4. Verify privacy and existing action authorization/CSRF. Test issue actions with
   fixtures/mocks or an isolated environment, not unsolicited public issues.
5. Visually follow the affected queue link through to the actual detail and
   required actions. Check both an existing historical failure and a new fixture.
   Preserve navigation, keyboard access, clear labels and consistent spacing.
6. After deployment, verify the affected authenticated workflow and counters
   read-only. Public API health and a green deploy job are not this acceptance
   test. If access is unavailable, record this gate as pending, not passed.
7. Record source revision, test evidence, limitations and live verification in
   project state. Distinguish implemented, locally tested, deployed and live
   verified. Never describe a missing workflow as fixed because an extra row is
   visible. Any deferred criterion must be explicit in the completion report.

These gates are required review criteria; this document does not claim they are
all already enforced automatically by CI. No new collection of production user
logs, synthetic production reports or install/remove operations is authorized
by this documentation.

## Known gaps at adoption (2026-09-15)

- PR212 surfaces unmatched failed map events and eligible compatibility failures in
  Overview, but it does not provide the full unknown-device diagnostic/issue
  workflow for a map-only failure.
- Build31 source moves diagnostic creation from ConnectScreen to an operation
  observer with native-to-API regressions. Record publication/live validation in
  the release receipt. The historical France cause and watch remain unknown.
- Safe correlated intake logging is included with this contract change; its
  production deployment must be verified separately. It cannot reconstruct past
  missing/rejected reports.
- These are open implementation/acceptance gaps, not exceptions to the required
  operator outcome. Fixes must not change installation/removal or device-file
  behavior as a side effect of diagnostic work.

App/API sequencing and revision/test receipts follow
[the app–API release contract](../../../contracts/APP_API_RELEASE_CONTRACT.md).

Recent map activity uses original Font Awesome solid icons and semantic title colors: started/processing blue, succeeded green, failed red, cancelled/unknown neutral, interrupted amber. Text remains visible. Plain and collapsed download rows share spacing, icon width and context alignment; the trailing disclosure chevron adds no leading indent. Expanding retains start/finish timestamps and total duration. Historical spinners remain static.

## Admin visual consistency addendum (2026-09-17)

These rules extend the existing Admin behavior contract and apply to the
current visual unification work. They do not change API payloads, populations,
formulas, sorting, filtering, pagination, or device actions.

- Popularity uses one `mapRow` renderer and one compact `popular-map-row`
  geometry in Top 5, Regions, and All maps. The first line keeps the region
  name at left and the install count at right; the second line is the last
  eligible install time, or provider plus time for All maps. Only the numeric
  value uses the bold treatment; `install`/`installs` remains regular and is
  kept with the value. Long names may wrap, while the count remains on the
  first line. Regions and All maps retain their existing scroll/search/page
  behavior, and the map button keeps its full focus/click target.

- Admin tables use semantic `column-number`, `column-status`, and
  `column-date` classes on headers and cells. Text and dates are left aligned;
  numeric values and status badges are centered. Sort controls inside those
  headers inherit the same alignment, including both the Devices sticky header
  and the horizontally scrolled main table. Future table rows must use these
  classes instead of page-specific positional selectors.

- Error and failed counters use the shared `admin-error-counter` helper/class:
  a measured zero is graphite, a measured positive value is danger red, and an
  unavailable value is `—` in neutral graphite. The class applies to the value
  only; links and headings do not force a zero into an error state. Async
  refreshes must use explicit numeric checks and preserve the same 0 → positive
  → 0 → unknown semantics.

- Overview, Installations, and device detail KPI summaries use the same
  `map-statistics-kpi-panel`, `map-statistics-kpi-groups`,
  `map-statistics-kpi-group`, and `map-statistics-kpi-value` hierarchy as Map
  statistics. Overview retains six metrics with Installs and Downloads grouped
  in the same compact panel. Installations retains five metrics in one panel.
  Device detail groups Attempts, Successful,
  Failed, and Open errors together, while Last activity remains in that panel
  with smaller date typography. Attempts has no decorative information icon.

- System health uses compact disclosure cards in three columns on wide screens,
  two on tablet and one on mobile, with status badges and retained
  diagnostic evidence/actions. All rows start collapsed, with problems ordered
  before healthy checks. The count summary, status filter and name search support
  30–50 checks in a compact responsive grid.


## Approved Admin plan — local implementation (2026-09-18)

These rules extend the existing contract, including the preceding identity and
work-item boundaries. Implementation evidence is local until separately published.

- Every page, section, chart, table, dialog and disclosure uses a title without
  decorative eyebrows or kickers. Editorial titles contain at most three words
  (excluding connective “by”); real model/provider names are retained. Counts,
  dates and statuses are separate metadata. Functional warnings, eligibility
  conditions and form instructions remain visible.
- Reuse the Map statistics KPI hierarchy. Provider detail has one summary of
  affected packages, problematic sources and broken artifacts. Health and
  Collection share the next row on wide screens and stack on narrow screens.
  Their details retain HTTP/status/duration, checks, sources, package history,
  collection runs, catalog sync, licensing and attribution. Check now, Collect
  catalog, Pause/Activate, More and activation restrictions remain unchanged.
- Native disclosures share a 44px minimum summary target, 14px chevron, common
  padding/focus geometry and Enter/Space behavior. Existing anchors still open
  their target. Nested detail content is padded independently of the summary.
- Installations shares Devices sort-button/aria-sort and column alignment.
  Model/Variant use natural text order; counts numeric order; dates chronological
  order; statuses canonical order. Unknown values are last in both directions;
  identity breaks ties. Latest activity remains the default. Dropdown and header
  controls use one URL/session state and sort the entire filtered model list.
  Server summaries use the complete narrow diagnostic population, not the newest
  500 events. A selected identity history is scoped in SQL before retrieval;
  the browser does not receive all histories to calculate summary counts.
- Empty table rows span the actual columns and center their content. Mobile grid
  presentation retains a full-width cell without a generated column label.
- Recent map activity uses one label/state/tone dictionary: success green, failure
  red, interrupted warning, started/processing informational, cancelled/unknown
  neutral. Text and existing icons accompany color; historical phases do not
  animate as live work. Update success uses the same success color as install.
- Overview preserves distinct compatibility-only, custom, pre-install and unknown
  identity diagnostics under Device/model activity. Removing its duplicate evidence
  card does not merge streams, delete history, or equate their denominators.
- Review queue previews at most three tasks. Category counts use the full all-date
  unresolved work population and link to the corresponding existing work view;
  zero categories are omitted, unavailable counts remain unavailable. Each preview
  retains object, reason/action and available timestamp with one primary link.
  Publication-review previews open the Devices publication-review filter, matching
  the queue shortcut, rather than the ordinary unfiltered device detail view.
- System health answers which component needs attention. Collapsed rows show title,
  status and a concrete issue. Details retain result, actual last-check time and
  operational links. Missing observations are “—”; next-check time appears only
  when recorded as scheduled. No synthetic problem-start/Changed timestamps are
  inferred from a check time. Schedules and health thresholds remain unchanged.
- Freshness revisions hash explicit source-data sections, never rendered HTML.
  Ignore rendering timestamps, tokens, check clocks, successful heartbeat metadata,
  identical logical redelivery and irrelevant ordering. A download poll with zero
  delta alone does not notify; actual increases, gaps/discontinuities and derived
  stale/status transitions remain meaningful. Poll every 60 seconds only while
  visible, without overlapping requests. Discard responses for an obsolete URL,
  generation or replaced view. Async rendering acknowledges only its rendered
  section keys; other pending changes stay pending. Show one short message and
  Refresh, no dismiss. Keep connection/session failures distinct. Dirty POST forms
  require confirmation before a user-requested full refresh discards edits.
- Average download time uses the canonical statistics definition below and one
  backend calculation/shared formatter in both tables. Show tabular mm:ss (minutes
  may exceed 59), round only the final average, “—” for missing, and a plain-language “X downloads” label for measured
  sample size. The focusable compact explanation states formula, selected period
  (Providers: last 30 days), measured/population coverage and interpretation limits.
- Scale acceptance uses isolated fixtures: 120 identities, 3,000 diagnostics,
  40 pending tasks and 50 health checks. Browser evidence must include wide,
  tablet and mobile views, keyboard controls, long names and empty states.


### Owner visual corrections (2026-09-18)

Map statistics is the KPI presentation reference. All shared KPI primary values
use its 24px/1.15 scale, with 19px secondary result values and horizontal separators.
Overview, Installations and exact-model detail must not override that scale with
larger KPI tokens. Exact-model activity follows a horizontal divider; Attempts
has no generated information icon. Functional accessible descriptions remain.

The shared error counter owns semantic color only and inherits typography from
its context. Table Failed/Open errors values match Attempts/Successful; compact
chart totals use identical font/line height and badge geometry. Positive errors
stay red, zero and missing values stay neutral.

Admin display copy omits the word “Fresh”; install/update populations and API
keys remain unchanged. Country coverage names custom-source results “Custom maps”.
Provider records without drawable country metadata remain separately identified
as installs without country coverage, never relabelled custom. Duration sample
size uses “1 download” / “X downloads” rather than statistical “n=X”; the accessible
explanation retains measured-versus-successful coverage and the formula.

A started acquisition with no recorded matching terminal event remains explicitly
unresolved. Do not convert elapsed time, another acquisition's interruption, or
missing telemetry into success/failure. App acquisition lifecycle tests cover
completion, cancellation, disconnect, restart recovery, queue draining, retry
and opt-out. A server-side absence alone cannot establish which client-side
condition prevented delivery.
