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
| Acquisition result | One terminal provider acquisition identified by `acquisition_id` and `component_kind` where available. Started/processing/cancelled/interrupted phases are history, not completed acquisition attempts. |
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

The Review queue is labelled and counted as `Pending review tasks`. A failed
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

The GitHub chart says `Observed download increases between checks`. It starts
with a baseline, preserves valid zero increases, leaves missing checks and
counter/population discontinuities unknown, and keeps the previous and actual
`observed_at` values for each observed interval. Failed collection keeps the
last successful observation and timestamp.

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
