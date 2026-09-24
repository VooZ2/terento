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

## Structured failure detail

Version-4 reports may supply top-level `failureContext` and
`originalFailureContext` using the same nonrecursive closed contract, with
`protection` nested inside each context. See the
[shared event contract](../../../contracts/README.md#structured-installation-failure-context)
for accepted fields. Server-first acceptance and presentation do not mean the
app emits these fields, comparator version 2 is implemented, or deployment has
occurred. Omitted and explicitly null contexts both display `unavailable` in
Admin detail and generated GitHub reports, including historical missing fields;
neither creates an empty or inferred context. Non-null original context requires
a terminal cleanup context object. Never reconstruct
boundary, presence or reason from a code, neighboring report or issue text.

Keep Overview concise. Diagnostic detail presents stage, exact boundary,
protection reason, native category, retry count and classification source.
Remaining bounded observations belong in Technical details. The generated
GitHub issue report includes exact boundary, classification source, device
presence, protection reason and explicit custom-import wording. Generating a
report does not authorize posting it or changing an issue's status.

Pre-write protection belongs to preflight; post-write protection belongs to
verify. Successful cleanup leaves that stage and reason intact. Cleanup failure
uses terminal stage/boundary cleanup while retaining the complete originating
context and protection reason separately. Read failure alone is not evidence
of device absence. Show only received facts; absent observations are not false.

A manually imported IMG remains a custom import even when its content originated
from OpenTopoMap. A catalog OpenTopoMap operation remains a provider operation.
Do not infer source from a private filename or map content. If a main map
succeeded, context is allowed only with `componentKind=contours`,
`optionalComponentSelected=true` and `optionalComponentOutcome=FAILED`; its
boundary matches the optional component's failure stage. Show that component's
context, including its separately retained original context on cleanup failure.
An aggregate successful-cleanup flag may describe another component and must
not erase this failure. Never pick context by dictionary order or
rewrite the main-map outcome. These diagnostics do not alter counting,
compatibility status, identity assignment, sharing or device safety.

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

Primary Admin section links are grouped by Daily (`Dashboard`, `Health`,
`Installations`), Catalog (`Devices`, `Providers`), and Analytics
(`Maps`). Tools remain a utility menu. A single `Review` count links to Dashboard
Needs attention. Grouping is visual only; destinations stay the same.

### Dashboard and Needs attention

Dashboard headline KPIs describe all retained history and link to the same all-time
Map statistics population. The two charts and unified activity list describe the
selected period. Period chart totals keep that selected period when they open
Map statistics. Needs attention covers unresolved work across all dates. Keep each
scope explicit. Show failures, linked issue work, identity/publication review and
provider/system problems as distinct work types.
Counts and list links must lead to the corresponding work, even when the preview
is truncated. Empty active work does not mean there have been no failures.

Needs attention is labelled and counted as `Pending review tasks`. A failed
diagnostic and GitHub handling linked to the same operation are alternative
states of one task; linking an issue moves the task between categories and
does not increase the total. Identity review is an additional task and
publication review is counted per exact model. The queue groups operation work,
not unique GitHub incidents, and resolved work is excluded. If the query fails,
the queue is unavailable rather than zero. Actions opened from an operation
task retain that operation-level diagnostic scope; per-map installation history
remains separate in the statistics read model.

An install failure without a matching device diagnostic is an additional
per-map review task keyed by the immutable map event ID. Overview exposes a
visible, keyboard-accessible `×` action to dismiss that task without a reason,
device selection, or diagnostic mutation. Dismiss/reopen is server-side,
idempotent, CSRF/authenticated, and audited with the administrator, timestamp,
transition, and exact event target; a failed mutation leaves the item visible.
The post-action Overview offers Undo. Queue counts, list rows, revisions, and
freshness use the same active task population. A later matching diagnostic
removes the gap independently. The activity link includes exact `eventId` and
opens the corresponding Map statistics Event detail without changing aggregate
statistics or install/coverage/publication/GitHub data.

A received device failure must lead to its actionable diagnostic context with
model/variant, available watch image, provider/map, time, result and known reason.
It must not be redirected to aggregate Map statistics as a substitute.

Admin presentation follows the pre-install classification in
[`contracts/STATISTICS_CONTRACT.md`](../../../contracts/STATISTICS_CONTRACT.md):
show provider acquisition failure as activity/history, not as an installation
failure, Review queue task, open error, or identity-review task. The original
diagnostic and map-event records remain available, and an explicitly linked
GitHub issue remains its own operator-created workflow.

When only a map failure exists, keep the gap visible and clearly say the device
report is unavailable. A statistics link is supplementary, not diagnostic
resolution. A complete unknown-device workflow must expose only supported,
audited actions and reconcile later reports without duplicating history. Do not
present that workflow, watch assignment or GitHub actions as available before
implemented. Never borrow a model from another user or nearby timestamp.

### Installations, device history and Diagnostic detail

Installations is all-time model evidence. The page label is `All time`. It is
not the selected Dashboard period.

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

The `Installation authorization` field reports the derived write decision,
not a compatibility result. The per-row policy values come from that catalog
row's `active` and `map_capable` fields: active Maps=Yes is Approved, Maps=No
is Blocked, and unknown capability is Pending. The native resolver applies
the exact normalized base-model match and evaluates Maps across every
remaining plausible active variant; conflicting variant attributes broaden
that candidate set rather than denying authorization. `support_status` remains
a separate operator metadata field and is never translated into write
permission. This decision is separate from
`TESTING`/`TESTED`/`SUPPORTED`/`VERIFIED`, success counts, and public
publication. A model with zero successful installations may still be
Approved, while evidence or support metadata cannot authorize it.
Admin payload `mapCapable` and the device list's `Catalog Maps` show only the
stored nullable `device_model.map_capable` value. The separate
`observedMapCapability` field holds classifier or successful-install evidence
and is shown on device detail and in the list cell's secondary description.
For example, stored NULL with observed Yes displays Catalog Maps Unknown and
authorization Pending. Identity Review and public compatibility retain their
own evidence semantics; neither derived value changes write permission.

Only an exact catalog row with inactive or stored Maps=No state may receive
server-side `OUT_OF_SCOPE_PREWRITE` classification; neither `support_status`
nor an Edge name is a classification shortcut. Events so classified remain visible in
diagnostic history with their reason and audit row, but are excluded from
ordinary open-error, identity-review, publication, overview, model-card,
fresh-install, update, and public statistics. A reported write boundary or
remote object is retained as a separate `OUT_OF_SCOPE_WRITE` security review
issue. Provider acquisition events remain a separate population.

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
layouts it has equal Downloads, Installs, and Updates groups, with
Successful and Success rate on the first row and Failed below in each group.
Diagnostic coverage is a secondary disclosure, not a primary KPI row, and
still shows Fresh attempts, Linked reports, Report gaps, and Coverage rate. A positive
Failed value uses the same semantic error token as Open errors; zero is neutral
and an unavailable value is shown as an em dash. These are presentation rules
only; the existing summary counts and formulas remain authoritative.

Popular maps uses the population and grouping defined in
[`contracts/STATISTICS_CONTRACT.md`](../../../contracts/STATISTICS_CONTRACT.md).
It is a secondary disclosure beside Installations by country. Admin provides
Top 5, Regions, and All maps views; All maps searches the complete eligible
set before pagination, and view navigation does not change the selected
population. The canonical row geometry is defined once in the
Admin visual consistency addendum below.

Dashboard has three KPI groups: `Downloads`, `Installs`, and `Model coverage`;
it has no `Current status` group. Installs and Downloads show all-time successful,
failed, and success-rate values. The Downloads group is map-acquisition telemetry, not
the GitHub `.dmg`/`.zip` panel: it uses the canonical acquisition populations
and formulas in [`contracts/STATISTICS_CONTRACT.md`](../../../contracts/STATISTICS_CONTRACT.md).
The model group shows active exact catalog rows with stored Maps=Yes that have at
least one verified successful installation, divided by all active exact catalog
rows with stored Maps=Yes. It is evidence coverage, not support, public
compatibility, or installation authorization.

Activity by provider has a two-row header: `Provider`; `Downloads`, `Installs`,
and `Updates`, each with `Successful`, `Failed`, and `Rate`; then `Last install`.
Admin installation and statistics UI uses `Installs` for the fresh main-map
installation population and must not render `Fresh install`, `Fresh installs`,
or `Fresh install success` as visible labels or copy. This vocabulary rule does
not rename internal identifiers (for example `freshMapAttemptCount`) or the
canonical population terminology in `contracts/STATISTICS_CONTRACT.md`.
Provider-health `Freshness` describes catalog recency and is unrelated to
installation vocabulary.
The visible `Installs` group is the canonical fresh main-map install population;
updates remain separate. Each provider rate divides its successful terminal
count by successful plus failed terminal counts in that same group. A zero
denominator displays `—`. Download failures include only terminal
`DOWNLOAD_FAILED`, not interrupted, cancelled, stale, or missing outcomes.
`Last install` shows the latest successful fresh-install timestamp in the
selected scope and timezone, or `—` when none exists; updates, downloads, and
provider health checks do not advance it. Average download time remains a
separate provider metric and is not a column in this table. Admin
tables keep descriptive text and dates left-aligned, counters and percentages
centered, and status badges centered, with column headers aligned to their
values. Sort controls retain their keyboard, focus, and `aria-sort` behavior.
The Providers table shows the health badge without an additional “Latest check
state” helper when no error exists.

Activity by provider keeps acquisition and installation populations independent:
successful installs are not synthesized from downloads, downloads are not
synthesized from installs, and `Installs > Downloads` is valid when the two
telemetry streams are incomplete. Install success, update success, and download
success use the canonical populations and formulas in
[`contracts/STATISTICS_CONTRACT.md`](../../../contracts/STATISTICS_CONTRACT.md).
Overview keeps the same three-metric layout in its outcome groups and separates
each Failed row with the shared Map statistics KPI divider.

The GitHub chart says `Observed download increases between checks`. In the 24h
view it is a discrete hourly chart: each canonical hour has one equal-width
x-axis slot, the label is `HH:00`, and adjacent bar footprints have visible
separation. The `.dmg` and `.zip` segments are stacked in the same hourly slot;
observation minutes never affect x-position. The exact observation timestamp
remains tooltip/accessibility and factual interval metadata. It starts
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
discontinuity semantics remain unchanged. A trusted positive delta, including
`+1` in the final slot, is rendered as a normal bar. A genuine unknown or
discontinuity interval has a visible `Unknown` text marker and accessible
description, not a color-only or dashed-zero interpretation.

Admin scrollbars are visually hidden in existing scrollable regions while the
regions remain scrollable with wheel, trackpad, touch, keyboard, and horizontal
table interaction. Hiding the scrollbar must not clip content, disable focus,
change overflow behavior, or add scrolling to a view that was not already
scrollable.

Average download time uses the canonical population and measurement definition
in [`contracts/STATISTICS_CONTRACT.md`](../../../contracts/STATISTICS_CONTRACT.md).
Admin renders the available value as `mm:ss` and an unavailable value as `—`,
never `0`; the selected population is not reduced by pagination or recent
activity limits.

- Overview has one `Activity` list for the selected period. It groups provider
  acquisition phases and shows install outcomes in the same chronological list.
  A device model appears only when operation plus provider and exact or
  unambiguous package-region facts reliably link the map and compatibility
  streams. Missing or ambiguous linkage is explicit and never filled from time,
  nearby activity, or another result. Full diagnostics elsewhere in Admin remain
  unaffected.

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

The `identity_conflict_manual_required` response keeps the stable error code and
adds a bounded `details.conflicts` array. Each item identifies the diagnostic
result, conflicting field, reported value, source, selected catalog model and
selected field value; approved identifier conflicts also list the catalog models
mapped to that exact code. All conflicting results in the selected operation are
included. Missing or unconfirmed facts remain `MISSING`/unknown and do not
create a conflict. The browser renders these fields as text and falls back to
the generic message when details are absent; exception, SQL and stack-trace
text are never exposed.

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
  geometry in Top 5, Regions, and All maps. The primary row keeps the
  country/region at left and the numeric count at right. Only the number is
  bold; `install`/`installs` remains regular and stays with the number. The
  secondary row is a timestamp for Top 5 and Regions, and `Provider ·
  timestamp` for All maps; it is placed below the left primary content, never
  beside the country or below the count. Each entry has a divider and compact
  spacing analogous to Device/model activity. Long names wrap on the left,
  the count remains top-right, the secondary line remains below the left
  content, and the separator cannot become an orphan. Regions and All maps
  retain their existing scroll/search/page behavior, and the map button keeps
  its full focus/click target. The visible summary heading is `Top 5`; each
  primary row and its optional secondary metadata line form one compact flow
  without a reserved empty row. Missing dates omit only their text, not the
  row or its divider.

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

- Dashboard, Installations, and device detail KPI summaries use the same
  `map-statistics-kpi-panel`, `map-statistics-kpi-groups`,
  `map-statistics-kpi-group`, and `map-statistics-kpi-value` hierarchy as Map
  statistics. Dashboard retains eight all-time metrics in three groups:
  Downloads, Installs, and Model coverage. Installations retains five
  metrics in one panel.
  Device detail groups Attempts, Successful,
  Failed, and Open errors together, while Last activity remains in that panel
  with smaller date typography and the Attempts explanation control.

- System health uses compact rows: name, badge, and relative time. Healthy
  checks stay collapsed with no description. Problems expand to Why, Next
  action, and Technical details. There is no explanatory summary paragraph
  about healthy checks staying collapsed.

- System health includes exactly one **IndexNow submissions** card. It reuses
  the common health badge, status sorting/filtering, disclosure behavior, and
  authenticated workflow link. Its collapsed summary contains only the
  disclosure affordance, the title, and the common health badge. The expanded
  view shows the safe result, last real submission or `No submissions yet`,
  pending URL count when the sender knows it, and distinguishes Last check, Last
  submission, Last successful submission (HTTP 200), execution URL/HTTP
  counts, pending/oldest-pending values, safe error/action text, and a maximum
  ten-URL public preview. It includes the exact explanation `Submission status
  only. This does not confirm search indexing.` and never offers submit/retry
  or key/configuration controls.

- IndexNow health is independent from API, database, site, and catalog health.
  HTTP 200 with no pending URLs is `HEALTHY`; HTTP 202 is validation-pending
  `WARNING`; temporary failures with retained pending URLs are `WARNING`; key,
  domain, request, or live-verification errors are `FAILED`; bootstrap or
  absent evidence is `UNKNOWN`. Unknown counts remain `—`, never zero. A
  missing-report warning is evaluated only when the latest retained site
  deployment has `indexnow_expected: true` and its 30-minute grace period has
  elapsed. Old or superseded deployments, PR/fork/dry-run runs, and historical
  deployments before this contract are not missing reports.
