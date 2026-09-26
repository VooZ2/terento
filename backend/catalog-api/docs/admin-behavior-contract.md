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

Keep Dashboard concise. Diagnostic detail presents stage, exact boundary,
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
is not guessed. Dashboard's map-event fallback projects only a verified success
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

The primary sequence is `Dashboard`, `Installations`, `Devices`, `Maps`,
`Providers`, and `Health`, followed by Tools and account controls. Dashboard
Needs attention is the entry point for actionable review work; there is no
duplicate Review navigation item.

### Dashboard and Needs attention

Dashboard must answer whether anything is wrong, what happened in the selected
period, whether activity is changing, and what to inspect next. On desktop its
first row is `Map downloads | Map installs`. Below it, Needs attention and App
downloads form the leading column while Activity spans the trailing column. The
narrow order is Map downloads, Map installs, Needs attention, Activity, then App
downloads.

The Map downloads and Map installs charts are always visible. Their Successful,
Failed, and Success rate badges are all-time values; the period selector changes
the chart series, not those badges. Hover/title and accessible text may expose
the all-time scope without permanent visible copy. App downloads means Terento
application downloads and is omitted when no usable counter or trend data exists.
Activity is internally scrollable and must not force page height. A generic
activity row has no Maps link unless an exact useful destination exists.

Needs attention covers unresolved work across all dates. Counts and Inspect links
must lead to the corresponding work even when the preview is truncated. Failures,
linked issue work, identity/publication review, and provider/system problems remain
distinct work types. Empty active work does not mean there have been no failures.
A failed query is unavailable rather than zero.

A failed diagnostic and GitHub handling linked to one operation are alternative
states of one task; linking an issue moves the task between categories and does
not increase the total. Identity review is a separate task and publication review
is counted per exact model. Resolved work is excluded.

A map install failure without matching device diagnostic evidence is a per-map
review task keyed by the immutable map event ID. Dismiss/reopen is authenticated,
CSRF-protected, idempotent, and audited without changing telemetry, statistics,
compatibility, publication, or GitHub state. Dashboard offers Undo after dismiss.
A later matching diagnostic removes the gap independently. An exact event action
may open the matching collapsed Maps Event detail; aggregate statistics remain
unchanged. A received device failure instead opens its actionable diagnostic
context and is not redirected to aggregate Maps as a substitute.

Provider acquisition failure remains activity/history, not an installation
failure, open error, identity task, or publication task. Never borrow a model from
another report or nearby timestamp.

### Installations

Installations is all-time model evidence and is visibly labelled `All time ·
Model evidence`. Its primary summary order is Attempts, Successful, Failed,
Success rate, and Open errors. A positive Failed value uses the danger color.
Maps applies the same fresh main-map write-boundary contract. A current
map-side failure with no reliable write evidence, a pre-write failure, and an
optional-component result stay in raw Event detail but do not enter the Maps
install denominator. Maps and Installations can still differ because their
independently delivered telemetry populations are attributed differently;
neither view invents the missing stream or a model identity.

All, Failed, Open errors, Successful, and Identity review filters retain their
separate meanings. Failed includes resolved historical failures; Open errors does
not. A true no-evidence state omits metrics, filters, table, and pagination. A
filtered-empty state keeps the active filters and a clear action. Pagination
appears only when multiple pages exist.

Known exact identities group consistently across list, record, detail, and
statistics views. Unknown identities remain discoverable. Identity text is
leading aligned; numbers and dates are trailing aligned where practical.

### Devices and device detail

`Maps`, `Install policy`, and `Evidence` are separate concepts. Maps reports the
stored nullable catalog fact. Install policy reports the derived native write
decision; it is not public compatibility or support status. Evidence reports
observed history. Administration starts collapsed. Technical identifiers and
provenance remain secondary.

The policy values are Pending, Approved, and Blocked. Active stored Maps=Yes is
Approved, Maps=No is Blocked, and unknown capability is Pending. The native
resolver still evaluates every plausible active variant. Support metadata,
observed capability, success counts, identity review, and public compatibility
never grant write permission.

Empty installation history omits unusable filters, table, and pagination. Above
900px, installation summary, Administration, Device information, and Technical
details form the left column while Installation history uses the right column.
Narrow layouts stack that same reading order. Historical catalog provenance
remains accessible and does not change Maps, Install policy, support, or public
compatibility.

### Maps and downloads

Map acquisition, fresh installation, and update populations remain separate.
Missing terminal activity is unknown, not success. Lifecycle phases must not
multiply attempts. Provider, map, region, and date filters define the summary
population; event type, outcome, exact event, and detail pagination scope only
the collapsed Event detail. Initial HTML and asynchronous JSON use the same
server summary.

The world map remains visible. Top countries shows up to 10 rows from the
existing country ranking. Primary visible analytics are Top countries,
Provider comparison, Maps by provider, Map downloads trend, Map installs trend,
and Updates. They are not placed in disclosures. Diagnostic linkage coverage
may remain in the private API contract but is not shown as an Admin block. Raw
Event detail is secondary and collapsed.

Maps trends use hourly buckets for 24 hours, daily buckets for seven days,
weekly buckets for 30 days, and adaptive all-time buckets: daily through 14
observed days, weekly through 60, then monthly. Missing buckets keep the
statistics contract's existing zero-fill and timezone rules.

Provider comparison keeps Downloads, Installs, and Updates independent, each
with Successful, Failed, and Rate, plus Last install. A zero denominator displays
`—`. Download failures include only terminal `DOWNLOAD_FAILED`. Last install is
the latest successful fresh main-map install in scope. The interface does not
synthesize one telemetry stream from another.

The App downloads chart shows observed public GitHub `.dmg` and `.zip` counter
increases. Its baseline, zero, legacy, partial, gap, counter-reset, and population
comparability semantics are owned by the statistics contract. It uses the
available card width with only axis and clipping margins.

History remains compact and explicit. Icons and color supplement status text.
Download phase icons remain static. Timestamps use the selected time zone.

### Diagnostics

Primary actions precede raw technical evidence. GitHub issue and Technical
details use the same disclosure presentation, with no duplicate heading inside
its own disclosure. Resolve and Assign model align naturally with content-driven
heights and stack when space requires it.

Assign model is an operator-assisted exact-catalog selection. Reported facts and
missing facts stay distinct; catalog facts may enrich only a consistent exact
target. A conflicting normal assignment requires the separate explicit manual
action and an audit record. Scope remains one exact result unless the operator
explicitly submits an operation-level scope. Identity decisions never alter
installation outcomes, device files, telemetry, statistics, or publication.

Diagnostic detail retains the result, time, map/provider, device identity,
available image, reason, lifecycle actions, issue actions, and one collapsed
Technical details section. A successful result with pending identity is not a
failure.

### Model source review

`/admin/device-identification` is visibly named `Model source review`. Its human
workflow is `Source reported` → `Match to` → `Other models using this code` →
`Confirm match` → `Technical details`. Raw codes, mapping/catalog IDs, source
revision, policy internals, missing-source inventory, and decision history remain
secondary in Technical details. Mapping review does not reassign historical
installations automatically.

### Providers and collection history

Provider health, collection outcome, available packages, and broken artifacts
remain separate. Updates count newly discovered plus changed packages for that
run; they do not count every artifact. Unknown historical counts remain unknown.
Technical source/review controls remain available behind disclosure.

Provider Problems distinguishes unique current affected packages, unique
problematic source identities, and the latest health state/error. Retired or
resolved historical entries do not enter current counts. Measured zero,
unknown/unavailable, stale, and partial remain distinct.

### Health

Health uses compact rows with the check name, status, and relative time.
Healthy checks stay collapsed. Problems expose the cause and next action before
Technical details. IndexNow submission state is one independent check and does
not imply that a submitted URL was indexed.

### Responsive and layout invariants

Admin preserves consistent left edges and the existing spacing scale, with no
block overlap or page-level horizontal overflow. It remains usable at effective
200% zoom, uses one compact menu column, keeps charts visible rather than
collapsed, trailing-aligns numbers and dates where practical, and uses
content-driven heights instead of artificial equal-height whitespace. Controls
retain keyboard focus, readable labels, and existing `aria-sort` semantics.

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

App/API sequencing and revision/test receipts follow
[the app–API release contract](../../../contracts/APP_API_RELEASE_CONTRACT.md).

Recent map activity uses semantic icons and color while retaining visible
status text. Expanded download history retains its start, finish, and duration
facts; historical in-progress icons remain static.
