# Administration, statistics and diagnostic behavior contract

## Provider recovery and update diagnostics — local 2026-10-02

The local implementation adds provider-scoped recheck jobs, per-artifact check
results and an update-only diagnostic view. This section describes the working
tree; production deployment and a new native release are separate gates.

Provider actions have distinct meanings: **Check provider health** samples
provider infrastructure; **Refresh catalog** collects its catalog; **Recheck
affected packages** validates currently failed/unavailable artifacts. A package
row can request a targeted recheck. Rechecks use original catalog URLs and the
existing provider validators, obey acquisition restrictions and stop after HTTP
429. The operator sees a reason, next action, time and stored job results;
missing historical reasons remain explicitly unknown. Failed optional contours
do not make a validated required main map unavailable. A check never asserts
that a full download or a Garmin installation has passed.

Activity failures link to `/admin/update-diagnostics?eventId=...`. The detail
requires one exact operation/provider/region match with the same outcome. Region
casing is normalized to lowercase in both streams; names and aliases are not
guessed. Missing,
ambiguous or conflicting evidence is shown explicitly. The list is titled
`Update reports`, is reached from Tools → Update reports (the Tools menu and
that item are marked active on it; Maps carries no Update reports link) and has
no link to itself. It follows the Installations layout (owner decision
2026-10-06): one summary card with plain Reports, Successful, Failed, Blocked
and Open numbers and no scope chips (the heading carries `All time` as page
meta), counted as raw update report rows of the diagnostic stream and
independent of the outcome filter and pagination, so it is never presented as
the Maps update total. Failed and Open are red only when positive; a positive
Open links to the open failed reports. Below the card, with no wrapping card or
title, the quick-filter bar (All, Failed, Blocked, Successful; server-side links
styled exactly like the Installations quick filters, `aria-current` on the
active one, Clear only while a filter is active) sits directly above the table
at the shared filter-to-table gap. The table (Date, Map, Result, GitHub issue,
App version, Action) sorts through the shared sorter, shows the GitHub issue
column only when a listed report has a linked issue, uses the device Update
history's compact secondary `Inspect` action, has no `N records` line, and pages
50 reports with Previous/Next links in the shared pagination row (same height as
its buttons, never underlined). A report detail (`?diagnosticId=`/`?eventId=`,
including the event-only and not-found states) starts with a `← Update reports`
back link and the result (for example `Map update failed`) as the page heading,
and uses the full content width; its facts grid has two columns on wide screens
and one on narrow screens. Detail reports show a closed failure-code explanation,
stage, next action, app version/build and known write/old-map-preservation facts.
An unconfirmed preservation result is not proof of absence; failed updates say
“Not confirmed — inspect device.” Acquisition/source-validation failures link
to the known provider package view. Raw payloads, device paths and logs are not
exposed. A historical statistic alone
cannot establish the France failure's cause.

Install successes/failures and update successes/failures have distinct chart
series and labels. Chart colours follow the single rule in the statistics
contract (owner decision 2026-10-05): provider fresh install successful uses
Interactive Primary (slate), custom `.img` fresh install successful its own
Lichen-dark series and legend entry, install failed solid red (destructive
text), update successful solid Stone Dark with no outline (Warm Stone alone is
2.69:1 on white), and update failed red diagonal stripes in bars and legends.
Stacked segments touch with no separator line, so each bar reads as one solid
column; every series has a legend
entry (counts follow the Dashboard legend rule), and each bucket is one keyboard
stop whose label lists every series. Fresh-install KPI denominators exclude every update.
Not-started updates are diagnostics, not failed device-write attempts. Charts
and legends must preserve these distinctions at supported widths.

### Shared component kit

Every Admin page renders numbers, statuses, cards, tables, empty states and
legends through one kit: a metric tile (label of one or two words, value,
visible scope chip, at most one secondary line, measured/unknown/unavailable/
partial states, danger tone only for a positive failure count; the label and
secondary text carry the meaning, so a tile value never carries an icon), a
section card
(one- or two-word title, optional scope chip, at most one action link, no
explanatory paragraph), a status pill (icon plus sentence-case text; colour
supports but never replaces the text), table conventions (identity first,
numbers and dates trailing, `—` for unknown; every data table sorts by any
labelled column through its header button with a Font Awesome sort icon and
`aria-sort`, `—` always last; server-paginated tables sort the loaded page and
ranking lists with a visually hidden header keep their ranking order), empty states (empty, filtered,
unavailable with Retry) and chart legends. Labels and card titles carry no
inline `?` help links, and Admin has no separate term-definition page (owner
decision 2026-10-06); term definitions are owned by
`contracts/STATISTICS_CONTRACT.md`, `contracts/APP_FUNNEL_CONTRACT.md` and this
contract.
Colours, radii and focus rings come only from the generated brand tokens; the
focus ring is Interactive Primary (≥3:1). Every icon, including chevrons,
arrows and placeholders, is an unchanged Font Awesome Free solid icon from the
pinned revision in `THIRD_PARTY_NOTICES.md`, inlined (no external origin);
Admin never uses hand-drawn SVG, CSS-drawn shapes or text glyphs as icons.

Filter bar (owner decision 2026-10-06): every Admin filter bar uses the
Installations design — one muted rounded bar holding, in order, a quick-filter
group, the search field, More filters or other selects, the result count and
Clear; Clear appears only when a filter differs from its default. A
single-choice filter is a quick-filter group, not a dropdown: Devices Maps
capability, Health status, the Maps time range, provider package and source
status, support report status, and the device, diagnostics and update history
filters. Such a group drives a hidden native select that stays the source of
truth for page scripts and GET forms. The bar sits 12px above its table. The
Dashboard period stays a dropdown because the Dashboard replaces its content in
place; its lone-dropdown bar keeps equal padding on every side of the field.
At 760 px and narrower, where Installations and Devices move their sort and
remaining selects behind a `Filters and sorting` button, More filters and
`Filters and sorting` share one row at equal widths with the normal 8px gap;
either panel opens full width below that row without moving the buttons. The
result count is one tight line below them with Clear beside it when shown, never
a control-height block; a More filters button without a partner (Maps) keeps
the full width. At 760 px and narrower a quick-filter group wraps its buttons
onto as many rows as it needs with the normal gap and keeps the 44 px touch
height; it never scrolls horizontally or clips a button at the edge.

Filter persistence (owner decision 2026-10-06): a page may keep its search,
sort, More filters selects and page size in the tab's session storage and in
the URL, but it never restores a single-choice quick filter from a previous
visit. A plain visit to Installations opens at `All` and a plain visit to
Devices opens at `Maps: Yes`; only an explicit link (`?state=identity-pending`,
`?state=open`, `?maps=unknown`, `?new=1` and the like) or the current URL on
reload preselects another quick filter or the Devices `new` view.

Filter dropdown (owner decision 2026-10-06): every remaining filter-type
`<select>` — More filters panels (Installations, Devices, Maps), the Maps
provider, the Dashboard period, rows-per-page and the mobile sort selects —
carries `data-admin-dropdown` and is enhanced by one shared,
nonce-delivered Admin script. A combobox button shows the selected option and
a Font Awesome chevron; its listbox popover opens directly below the field,
left-aligned and at least the field's width, flips above only when there is no
room below, and never covers the field. It uses the white surface, a 1px
border, the control radius, the existing card shadow, Inter at the field's
size, a check icon plus selected tint on the chosen option, and the Admin focus
ring. The button's horizontal padding is `--admin-control-padding-x` on both
sides, owned by the stylesheet and never copied from the hidden native select,
so the selected text never touches the field edge and the chevron sits on the
right after an 8px gap; the popover is used at every width and never causes page overflow. The
native select stays in the DOM, labelled and visually hidden, as the source of
truth: a choice sets its value and dispatches bubbling `input` and `change`
events, and programmatic value or option changes and `disabled` are mirrored.
Keyboard follows the ARIA select-only combobox (Enter, Space, Alt+Down or the
arrows open; arrows, Home, End and type-ahead move; Enter selects; Escape closes
and keeps focus; an outside click closes). Selects in forms that post data
(device Administration, diagnostic issue workflow), selects inside dialogs, the
provider health-check interval and the top-bar time zone stay native.

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
| Open problem | One install operation with an active, nonlocal, non-excluded failed diagnostic that is not a provider download/pre-install failure and has no linked GitHub issue. This is the single Needs attention installation-task predicate and unit; resolution or linking an issue removes it from open problems, never from historical failure totals. |
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

The primary sequence is `Dashboard`, `Installations`, `First run`, `Devices`,
`Maps`, `Providers`, and `Health`, followed by Tools and account controls. Dashboard
Needs attention is the entry point for actionable review work; there is no
duplicate Review navigation item.

### Dashboard and Needs attention

Dashboard must answer whether anything is wrong, what happened in the selected
period, whether activity is changing, and what to inspect next. It has no
summary tile row: the Downloads and Installs chart cards share the first row.
Each chart card holds exactly three things (owner decision 2026-10-06): a
header with the period scope chip and, top right, the period totals as compact
value chips (Successful, Failed — danger only when positive — and Success rate;
Installs counts fresh installs only); the chart; and a legend naming each
series by colour without counts. No All time line, purpose breakdown or other
explanatory text is shown in these cards; all-time totals live on Maps. Header totals and charts use the same period
population, so they agree. A legend elsewhere shows a count only where it adds
information no total shows (the Maps Custom .img install split and the App
downloads period increases). The Needs attention header shows its `Now` total
as one chip (`—` when any row is unavailable). Below the
charts, Needs attention and Activity share a row, then First run and App
downloads share the next row; when one of those cards is omitted the remaining
one spans the row, so no Dashboard row leaves an empty grid cell at ≥1024 px.
The narrow order is Downloads, Installs, Needs attention, Activity, First
run, then App downloads.

Every number shows its scope as visible text (`Today`, `Last 24 hours`,
`Last 7 days`, `Last 30 days`, `All time` or `Now`); hover-only scope is not
used. Every Admin period picker (the Dashboard period dropdown and the Maps time
range) offers, in this order, Today, Last 24 hours, Last 7 days, Last 30 days and
All time (owner request 2026-10-07); Today covers the current day from midnight
in the selected Admin time zone up to now. The Dashboard default stays Last 24
hours and the Maps default stays All time; an unknown Dashboard period falls
back to Last 24 hours. Card titles
are one or two words. App downloads means Terento application downloads (GitHub
`.dmg` and `.zip`, never map downloads), shows its
period increases in the legend and its all-time totals and last update in one
`All time` line, and is omitted when no usable counter or trend data exists.
The Dashboard First run card is a short review (owner decision 2026-10-10): the
journey below with its `Lost on the way` line, then `Waiting models` (only when
any model waits: at most three models across the Pending, Unknown model and
Ambiguous outcomes, most sessions first, each linking to Devices filtered by
that name with its catalog status and session count, then `+N more on First
run`), and a `View all` action to `/admin/first-run` for the same period. It
shows no Sessions over time and no outcome groups.

The First run page (`/admin/first-run`, primary navigation after
Installations) has the Dashboard period picker (default Last 24 hours; an
unknown period falls back to it) and one First run card that shows the separate
app first-run funnel population for the period (owner redesign 2026-10-10;
moved off the Dashboard the same day). It opens with the
journey: three steps on one row of three equal columns at every width, label
above number with the numbers on one baseline: `Opened app` (the period's
distinct sessions), `Watch connected` (sessions with `DEVICE_CONNECT`
`CONNECTED`, with its share `N% of opened`) and `Install allowed` (connected
sessions with `AUTHORIZATION` `APPROVED`, with `N% of connected`; `—` when the
read model does not report it). Each step has a bar scaled to its share of the
period's sessions and, when the read model reports the previous window, its
change as text with an arrow (`▲ +4 vs previous 24 h`, `▼ -2 vs yesterday`,
`= Same as previous 7 days`); colour is never the only signal. A `Lost on the
way` line names `N never connected` (`neverConnectedSessionCount`) and `N
connected but not allowed` when above zero. With at least two buckets,
`Sessions over time` shows one small stacked bar per hour (Today, Last 24
hours), day (Last 7 days), week (Last 30 days) or month (All time):
connected sessions in the interactive colour, never-connected sessions in the
danger colour, each bucket focusable with its values as text, the first and
last bucket labels below and a two-entry legend. Below, in this order, `Why
not connected` (only when sessions never connected: the `DEVICE_CONNECT`
signals of those sessions alone, plus `Closed before any watch signal` for
never-connected sessions with no connection signal, scaled to the
never-connected count, with the muted note `Sessions that never connected;
one can show several signals.`), Connection problems (every non-connected
`DEVICE_CONNECT` outcome across all sessions, with the muted note `Every
session, including those that connected later.`), Authorization, Catalog and
Install blocked list one row per outcome with its label, a small horizontal bar
scaled to its share of the period's sessions and its count as text, largest
first; zero rows are omitted and an empty group shows `—`. Non-obvious outcome
rows carry one short muted meaning under the label (for example Pending
`Model not in the catalog, or its Maps value is unknown or mixed`, Catalog
unavailable `The policy check failed (network or server); nothing was
written`, Built-in copy `The server catalog did not load; the app used its
bundled list`). On this page the models waiting for review are listed under their
Pending, Unknown model or Ambiguous row (there is no separate Waiting models
group): each model links to Devices filtered by that name and shows what the
current installation policy says about it (`Not in catalog`, `Maps unknown`,
`Variants differ`, `No maps`, `Withdrawn`, `Approved now`); this status is
diagnostic and never grants or revokes write authority. Labels keep their
full width and the bar track shrinks first. Above 900 px, when the card is
wide enough for label, bar and count in half columns
(card content at least 620 px), the groups flow into two balanced columns and a
group is never split; otherwise they stay in one column with one aligned label
column. Rows count sessions
per outcome and are not exclusive: one session can appear in several rows, and
most connection problems are signals seen while the app keeps waiting, so their
sum is not a failure count. Outcome labels use outcome wording: Connection
problems `No watch plugged in`, `Didn't get ready`, `Not in file-transfer
mode`, `Watch in use by another app`, `Several Garmins`, `Disconnected after
connecting`, `Stopped responding`; Catalog `Loaded`, `Partly loaded`,
`Built-in copy`, `App update required`; Install blocked `Not allowed for this
watch`, `Watch storage full`, `Mac storage problem`, `Map not verified`, `Watch
not identified`, `Other`. The Dashboard and First run page freshness revisions
for First run cover exactly these displayed values, without zero trend buckets that only move with the rolling window. One-card KPI rows follow the two-row rule in Responsive and
layout invariants. It never
mixes into install counts. A failed sub-query renders that card as `Unavailable` with a Retry link
inside the admin chrome instead of failing the page.
Activity is internally scrollable and must not force page height. A generic
activity row has no Maps link unless an exact useful destination exists.
Installation and update activity use two text rows: status, then map/region,
provider and exact assessed model/variant separated by middle dots. The catalog
placeholder `Historical` is omitted from this label; real variants remain visible. Custom .img
omits provider. The model link is inline in that same context row, never a
separate row with a blank gap. Unassigned or ambiguous models are omitted rather
than shown as a reported guess. Long context may wrap naturally on narrow screens.

Dashboard chart series use one stacked bar for each bucket: downloads are
successful/failed, while map operations distinguish install successful, custom
`.img` install successful, install failed, update successful and update failed,
each with its own legend entry; optional components and pre-write failures remain
excluded by the statistics contract. Each bucket is one keyboard stop with a
label listing every series; segments are presentational. Tapping, clicking or
keyboard-focusing a bucket (Enter/Space also select it) fills a small value
strip under the chart (hidden, with no hint text, until a bucket is chosen) with the bucket date, every series value (`—` when not
recorded) and the total, announced through `aria-live`; values never require
hover. The strip uses the shared inline nonce script, no chart library, and the
charts stay server-rendered SVG.

Chart geometry is truthful with two legibility rules shared by every Admin bar
chart. Minimum segment: a non-zero stacked segment is drawn at least about
3 CSS px tall (5 chart units on the desktop chart, 4 on the compact chart); the
added height is taken proportionally from the larger segments of the same bar,
so each bar keeps its true total height on the axis scale. Only a bar whose
true height is below that floor for each of its non-zero segments grows to
exactly the floor, and exact values always remain in the bucket label and value
strip. X axis: every bucket is labelled when the labels fit, otherwise every
second bucket (or the smallest regular step that fits on the compact chart),
always including the most recent bucket and never overlapping.

Needs attention covers unresolved work across all dates in six review queues
(owner decision 2026-10-06), in this order, each row with an icon, label, count
and arrow: Open problems, GitHub issues, Identity review, Publication review,
Missing reports and Support reports, followed by one System checks row (owner
decision 2026-10-06). System checks appears only when Health has Failed or
Degraded checks; its count is those checks (the same states Health lists under
Issues) excluding the Catalogs check, because provider problems stay on
Providers. It links to `/admin/system-health?status=FAILED`, or
`?status=WARNING` when no counted check failed, which preselects that Health
quick filter, and it is counted in the header total. A Health list filtered this
way can also show a failed or degraded Catalogs row that the Dashboard count
leaves out. An unavailable Health snapshot adds no row. Maps unknown models and
provider problems are not Needs attention rows; they stay on Devices
(`/admin/devices?maps=unknown&active=1`) and Providers. Only rows with a positive or unavailable
count are listed (owner decision 2026-10-06); a measured zero renders no row,
and when every count is zero the card shows `Nothing to review.` instead. Review
counts come only from the canonical review read model and the support-report
count, and System checks only from the Health check states; there is no
fallback from another definition.
A failed query shows `—` with an explicit `Unavailable` message, never `0` or
"No pending work". Each row links to its work list, and that list shows the same
total even when it paginates; Identity review links to the Identity review queue
(`/admin/review/identity`). Failures, linked issue work, identity/publication
review, and provider/system problems remain distinct work types. Empty active
work does not mean there have been no failures.

A provider problem is an active provider (not paused or retired) whose source
health is Degraded or Failed, whose catalog collection failed or is overdue, or
which has current package problems. Dashboard, Providers and Health use this one
definition; System checks excludes the provider catalog checks so a provider is
never counted twice.

A failed installation diagnostic and GitHub handling linked to one operation are alternative
states of one task; linking an issue moves the task between categories and does
not increase the total. Identity review is a separate task and publication review
is counted per exact model. The GitHub queue and its badge also include each active,
nonlocal linked update diagnostic by exact report UUID. Unlinked update failures
remain in update diagnostics and do not enter installation issues. Resolved work
is excluded.

A map install failure without matching device diagnostic evidence is a per-map
review task keyed by the immutable map event ID. `/admin/review/missing-reports`
lists every such task (50 per page, total shown) with its Inspect link and
Dismiss. Dismiss/reopen is authenticated, CSRF-protected, idempotent, and audited
without changing telemetry, statistics, compatibility, publication, or GitHub
state. The list offers Undo after dismiss (the Dashboard keeps accepting the same
notice). A later matching diagnostic removes the gap independently. A retained
statistics-excluded diagnostic is present evidence, and an
`OUT_OF_SCOPE_PREWRITE` diagnostic for the same result suppresses the task. An exact event action
may open the matching collapsed Maps Event detail; aggregate statistics remain
unchanged. A received device failure instead opens its actionable diagnostic
context and is not redirected to aggregate Maps as a substitute.

Support reports counts open reports from public (non-local) builds, read from
its own query; a failed query shows that row as `Unavailable` (`—`) and the
Needs attention header total as `—`, never `0`. `/admin/support-reports` shows Open
(`Now`), Handled and Reports (`All time`, i.e. the 12-month retention window)
tiles, Open/Handled filter chips with their counts, and a table (Reference,
Category, Report, Model, App version, Received, Status pill) with 50 rows per
page, newest receipt first. The detail (`/admin/support-reports/TR-XXXXXX`)
shows Summary, Problem, Description and a collapsed Technical details section
(IDs, verification, failure context, lifecycle facts, finishing diagnostics),
with Actions (Mark handled / Reopen with an optional note, GitHub issue link),
Diagnostics (links to the public installation report model view and update
report with the same operation ID, or an explicit "not received" state) and
History. Every action is authenticated, CSRF-protected, idempotent and audited
and never changes the received report or any count. Local test reports are
listed only on Tools → Test data, open from there with a `Local test` pill, link
no diagnostics and are deleted by the Test data purge. Support reports are never
statistics ([`SUPPORT_REPORT_CONTRACT.md`](../../../contracts/SUPPORT_REPORT_CONTRACT.md)).

Provider acquisition failure remains activity/history, not an installation
failure, open problem, identity task, or publication task. Never borrow a model from
another report or nearby timestamp.

### Installations

Installations is all-time model evidence and is visibly labelled `All time ·
Model evidence`. Its summary tiles, in order, are Attempts, Successful, Failed,
Success rate (all time) and Open problems (now), shown without scope chips under
the numbers (owner decision 2026-10-06; the page is the all-time evidence view). A positive
Failed value uses the danger color; a measured zero stays neutral. The status
column is named Evidence.
Open problems, the per-identity Open problems column and model detail Open
problems use the operation-level Needs attention installation predicate, so
Dashboard `Installation problems` equals Installations `Open problems`. Each
operation is attributed to exactly one identity; the KPI is the sum of the rendered
rows and an identity with an open problem stays listed even with zero attempts.
Model history rows marked open are the per-map results of those operations.
Maps applies the same fresh main-map write-boundary contract. A current
map-side failure with no reliable write evidence, a pre-write failure, and an
optional-component result stay in raw Event detail but do not enter the Maps
install denominator. Maps and Installations can still differ because their
independently delivered telemetry populations are attributed differently;
neither view invents the missing stream or a model identity.

All, Failed, Open problems, Identity review and Successful quick filters retain
their separate meanings; Identity review shows identities with a pending
identity decision. When a listed identity is pending, a `Review identities`
link beside the quick filters opens the Identity review queue, and a row's
`Identity review` badge links to the queue at that reported identity
(`/admin/review/identity#identity-…`); the model link keeps its destination.
Failed includes resolved historical failures; Open problems does not. A true no-evidence state omits metrics, filters, table, and pagination. A
filtered-empty state keeps the active filters and a clear action. Pagination
appears only when multiple pages exist.

Known exact identities group consistently across list, record, detail, and
statistics views. Unknown identities remain discoverable. Identity text is
leading aligned; numbers and dates are trailing aligned where practical.

### Identity review

`/admin/review/identity` is the one Identity review queue (owner decision
2026-10-06) and the Dashboard Identity review destination. It lists every
active install operation with at least one identity-pending result, across all
reported identities, newest first, grouped by reported identity (one card per
identity with its reported model and variant, its count and an `All
installations` link to that identity's page). The unit is the Needs attention
one, an install operation; a multi-map operation is one item. Each item is one
compact row: date, map, result pill, a short reason taken from the received
identity assessment (for example `2 possible models`, `One match · size not
confirmed`, `No catalog match`), a `Details` link that opens that result's
diagnostic dialog on the reported-identity page, and the Device identity
controls inline. The inline controls are the dialog's Device identity form
(same fields, same `/admin/diagnostics/identity` action, one exact result per
form, so a multi-map item shows one form per pending result): the suggested
model when the assessment has exactly one, Edit or Pick model to open the
picker (candidates only, or the page's catalog template), and Confirm. The
picker stays closed until Edit or Pick model. Confirm saves through the shared
async action and keeps the queue open: the form becomes `Confirmed` with a link
to the model and the remaining counts drop; a conflict keeps the separate
Confirm manual assignment path. The endpoint assigns one result or one explicit
operation scope, so the queue never offers a group-wide confirm. With nothing
pending the page says `No installations wait for identity review.`; a failed
read renders an `Unavailable` card with Retry.

Discovery reuses the Installations source (identities whose active results are
identity pending) and the existing per-identity detail read; the Needs
attention count is the SQL operation count. Both use the same row predicate
(active, nonlocal, not statistics-excluded, no catalog model, not resolved or
not identifiable, not a provider download failure) and the same operation
unit, so they agree except when one operation reports results under two
different reported identities, which then appears under each identity.

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
never grant write permission. Evidence is computed only from the stored catalog
Maps fact and verified successes; a model-name classifier never sets it.

The Devices list uses the Installations layout: the last sync line sits in the
page heading meta, and the tiles (Models, Maps: Yes, Verified, Covered, Pending
policy) carry no scope chips. Covered reads `covered/eligible (rate)`, for
example `12/40 (30.0%)`. Pending policy counts active Pending models and uses the
danger tone when the count is above zero, like other failure tiles; zero stays
neutral (owner decision 2026-10-06). The filter bar matches Installations: a Maps quick
filter group (All, Maps: Yes, Maps: No, Maps: Unknown; Maps: Yes by default),
search, More filters and the result count, separated from the table by the
filter-to-table gap and still sticky above it; Clear appears only when a filter
or sort differs from the default. The narrow-width sticky column header is a
visual copy hidden from assistive technology; the table's own header keeps the
caption and sortable controls.

Empty installation history omits unusable filters, table, and pagination. Above
900px, the Installs card (Attempts, Successful, Failed, Open problems, Last
report), Updates, Administration, Device information, and Technical
details form the left column while Installation history and, below it, Update
history use the right column.
Update history uses the Installation history layout: its `Update history` title
sits outside the card in the same section heading, with no scope chip, followed
by the same quick-filter bar in the Installation history order (All, Failed,
Blocked, Successful; Clear when a filter is active) and the same diagnostic
list table (Date, Map, Result, GitHub issue, App
version, Inspect). Its filters and pages stay server-side (`updateOutcome`,
`updateOffset`), so the filters are links; the active one carries
`aria-current` and the quick-filter active style. At ≥1024 px the table fits
the history column without horizontal scrolling and shows the GitHub issue
column only when a listed row has a linked issue; narrower layouts use the same
labelled record cards as Installation history. An empty Update history shows
the same compact empty state as Installation history and omits filters, table
and pagination; a filter with no matches keeps the filter bar and says so.
A pre-write result (`writeStarted=false`) shows a `Blocked` status pill (its title
says `Blocked before writing`; quick filters also read `Blocked`, counts keep
the full term), is not in the Failed filter, has its own Blocked filter, and
stays an
open problem when the canonical predicate says so.
Narrow layouts stack that same reading order. Historical catalog provenance
remains accessible and does not change Maps, Install policy, support, or public
compatibility.

Historical provenance is determined by `record_source=HISTORICAL_REVIEWED`
(`recordSource` in the admin payload), independently of variant text. Display its
marker on Devices, Installations and model detail while preserving real variant
labels such as 47 mm or Solar (no Wi-Fi). The legacy variant placeholder
`Historical` displays as an empty variant, not a hardware feature. The marker
describes catalog provenance, not product age or Garmin's discontinued status.
Model detail's catalog lifecycle reads `Historical` for that provenance,
`Retired from retail` for a collector row Garmin's category has omitted for
three complete collections (`retailRetired` in the admin payload; the row stays
active and keeps its Maps and Install policy), `Inactive` for a withdrawn
inactive row, and otherwise `Current retail`.

The historical fēnix 7 Pro and Solar (no Wi-Fi) identities remain separate, as do
their 7X Pro equivalents: Garmin lists them separately in its
[Connect IQ device catalog](https://developer.garmin.com/connect-iq/compatible-devices/).
Migration051 uses shared representative model photographs for these pairs;
identical images do not establish identical variants or justify merging evidence.

### Maps and downloads

Map acquisition, fresh installation, and update populations remain separate.
Missing terminal activity is unknown, not success. Lifecycle phases must not
multiply attempts. Provider, map, region, and date filters define the summary
population; event type, outcome, exact event, and detail pagination scope only
the collapsed Events disclosure. Initial HTML and asynchronous JSON use the same
server summary.

Maps reads top to bottom: the filter bar; Downloads, Installs and Updates tiles
for the selected period (each with failed count and rate); then Countries (world
map) and Top countries; then Providers; then Top maps; then the collapsed Events
disclosure; and last, at the very bottom, the Downloads and Installs trend cards,
laid out like the Dashboard charts (period Successful, Failed and Success rate
totals at the top right, a legend without numbers, nothing under the legend)
(owner decision 2026-10-06). The Countries
card carries no visible country/install count line; the world map's accessible
name states when coverage is empty or partially unavailable. Top maps names are
plain text with the provider and last-install date below, not links; Top
countries names stay buttons that highlight their country on the world map.
The filter bar names the selected period, so Maps cards carry no scope chips and
no separate All time line (owner decision 2026-10-06). The Providers stream
control and the Top maps search sit in the shared filter bar inside their
cards. These analytics are not placed in disclosures on wider
screens. At ≤600 px the three tiles form one compact three-column row, and Top
countries, Providers and Top maps start collapsed behind a Show/Hide button
(`aria-expanded`, card title in its accessible name) so the page stays short;
a link to an element inside a collapsed card opens it, and without script or
above 600 px every card stays open. Top countries and Top maps are compact
ranking lists at every width and never turn into labelled mobile record cards
(`data-own-mobile-layout`): each row puts the name on the left (Top maps adds
its provider · date line below) and the install count on the right on the
name's baseline, with no per-row field labels. At 760 px and narrower Top maps
hides its column header and its counts name their unit for screen readers;
wider screens keep the sortable Map and Installs header. The world map remains visible and Top
countries shows at least 10 rows from the existing country ranking; beside the
Countries card it adds further rows while they fit its height (up to 30). A period without rows shows measured zero tiles and an empty-scope note;
it never shows populated all-time numbers as if they were the period. Diagnostic
linkage coverage may remain in the private API contract but is not shown as an
Admin block. Events uses human labels (event type, provider, map name) with the
raw code in the title, and shows Results (counted) and Events (raw records)
separately. The Maps page carries the selected time zone in its form so chart
buckets and period boundaries use it; changing the zone reloads them. The Maps
heading carries no Update reports link; the update report list is reached from
Tools → Update reports.

Maps trends use hourly buckets for Today (from local 00:00 to the current hour)
and 24 hours, daily buckets for seven days,
weekly buckets for 30 days, and adaptive all-time buckets: daily through 14
observed days, weekly through 60, then monthly. Missing buckets keep the
statistics contract's existing zero-fill and timezone rules.

Providers shows one stream at a time through a segmented control (Installs,
Updates, Downloads); each stream keeps its own Successful, Failed and Rate, and
Installs and Updates show their own Last install / Last update date, drawn from
the same rows as that provider's Successful count: a positive operation count
for a main map (or a historical row without a component), including custom maps
that have no catalog package. Zero-count rows and optional components such as
contours cannot advance them. Downloads shows Last download:
the latest successful download with a positive operation count, across the same
all-purpose population as the Downloads totals. Download failures include only
terminal `DOWNLOAD_FAILED`. A zero denominator displays `—`. Downloads totals
and trends explicitly include all purposes, including updates and components.
The download purpose breakdown (For installs, For updates, Not recorded) stays in
the statistics payload but is not rendered in Admin (owner decision 2026-10-06).
Unknown historical purpose is never inferred from the absence
of an update report. The interface does not synthesize one telemetry stream
from another.

Top countries, the world map, and Top maps share the eligible positive
fresh-install population: known provider, identified catalog package, and main
component (or historical absent component). Optional contour components do not
rank; an independently selectable contours package whose component is main does.
Unknown or zero counts cannot create ranking entries or advance their dates.

When retained update diagnostics establish a terminal prewrite outcome, Activity
shows “Update blocked before writing”, its reason and a link to the report. This
is separate from failed writes and never increments Update failed. A completed
acquisition remains a completed acquisition even if the later update stops.

The App downloads chart shows observed public GitHub `.dmg` and `.zip` counter
increases. Its baseline, zero, legacy, partial, gap, counter-reset, and population
comparability semantics are owned by the statistics contract. A counter reset or
confirmed population change is labelled `Data boundary`, with the reason in
accessible text; independently retained authoritative release markers may add
`New release` or `New releases · N` in the same bucket. It uses the available
card width with only axis and clipping margins.

History remains compact and explicit. Icons and color supplement status text.
Download phase icons remain static. Timestamps use the selected time zone.

### Diagnostics

Primary actions precede raw technical evidence. Prepare GitHub issue is visible
without opening a disclosure in both installation and update failure views.
Resolve marks a diagnostic reviewed; it is secondary to investigating the
failure.

The installation detail dialog (opened from Inspect) reads, below the record
summary, in one section rhythm with one heading style (owner decision
2026-10-06): What happened, with its Next action sentence as a labelled line in
the same section; Safety facts as a compact fact list; GitHub issue (status
line, one help line, one action row with Prepare GitHub issue and Copy issue
report, then the Preview issue report and Link or manage an existing issue
disclosures); Review administration; Technical details; and Device identity
last. Every `<details>` in the dialog, including the per-result Technical
details, uses the one `admin-disclosure diagnostic-disclosure` presentation
(white surface, border, card radius, Font Awesome chevron, same summary font).
Review administration holds the resolve/reopen and workflow forms in one
collapsed disclosure, each form a compact row with its button aligned to its
fields; it is omitted when no lifecycle or workflow action applies. There is no
separate "Identity incomplete" notice; the Review state badge and Next action
point to Device identity. The update report page uses the same sections in
the same order, disclosure presentation and review-form layout, and also ends
with Device identity; there it is read-only (Catalog model from the server
assessment or `Not assigned`, Reported model, Reported variant) because update
reports have no identity assignment action. Its top Device fact is the catalog
model link or the plain reported model, as in the installation dialog. When an
event has no matching diagnostic, the Report status explanation follows the
summary facts.

Device identity is an operator-assisted exact-catalog selection: Selected model
is shown as a label with a bold value, and Edit, Confirm and (only on conflict)
Confirm manual assignment share one action row. When a model is already
selected the search picker stays hidden until Edit. Initial candidate
buttons are immediately usable by pointer and keyboard without
typing into the search field. When a dialog would list the whole catalog, the
page renders the catalog once in a template and each dialog clones it when it
first opens; candidate-restricted pickers keep their own options. Confirm stays disabled until a specific catalog
model is selected; changing the search clears a stale selection. Reported facts and
missing facts stay distinct; catalog facts may enrich only a consistent exact
target. A conflicting normal assignment requires the separate explicit manual
action and an audit record. Scope remains one exact result unless the operator
explicitly submits an operation-level scope. The newest identity audit record
per result is its administrator decision; repeating that identical decision
(double submit, second tab) succeeds without another audit record. Identity
decisions never alter installation outcomes, device files, telemetry,
statistics, or publication.

The reported-identity page (`/admin/diagnostics?identity=…` for an identity
without a catalog model) follows the device page: an Installs card with the
same classes and tiles (Attempts, Successful, Failed, Open problems and
Evidence as a normal status pill) without scope chips, an Installation history
with a quick-filter bar (All, Failed, Open problems, Identity review, Resolved,
With issue, Successful; no select and no `N records` line) above the shared
diagnostic table (labelled record cards when narrow), and a `Review all pending
identities` link at the top. A link ending in `#diagnostic-detail-…` opens that
result's dialog on load.

Diagnostic detail retains the result, time, map/provider, device identity,
available image, reason, lifecycle actions, issue actions, and one collapsed
Technical details section. When an installation report carries
`inventoryMetrics`, Technical details lists its scope, pre-write objects and
check time, and post-write objects and check time; they are diagnostics, never
counts. A successful result with pending identity is not a
failure.

### Shared installation and update review

Installation and update failures use the same reading order and control patterns:
operation, model/variant, date, provider/map, result and app version; What happened
with Next action; known safety facts; GitHub issue with visible Prepare GitHub
issue and expandable preview/link management; then review administration and
Technical details as disclosures (see Diagnostics), then Device identity. Both
use the same typography, spacing and button hierarchy; the installation dialog
keeps a bounded width while the update report page uses the full content width
like other Admin detail pages. A generic
installation failure explicitly says the specific reason was not received and
points to the local report; it does not merely repeat “Installation error.”
An update also shows whether the previous map was confirmed preserved. A failed
check names the observed boundary; it does not invent the underlying cause.

Both views prepare a sanitised issue title/body for the Terento repository, offer
preview and copy, accept an optional bounded admin note, and link or unlink an
existing issue. Preparing opens the GitHub composer; the administrator reviews
and submits it there. Oversized reports use the same copy fallback. No report is
posted automatically. Update issue links and lifecycle actions target one exact
diagnostic UUID, require authentication/CSRF and record an audit. Every issue
link, relink or unlink that changes a result is audited, including on resolved
results; an identical link is a no-op. Reopening an active result or resolving
a resolved one is a no-op success that keeps its workflow, resolution and
resolver; a workflow change on resolved results is rejected. Resolving,
reopening or linking never changes the received outcome, write fact or counts.
The bounded issue synchronizer reads GitHub before locking any diagnostic,
resolves active linked diagnostics when GitHub confirms closure and audits each
one's actual previous workflow state; reopening remains an explicit
administrator action.

An update report links to the model detail only through a server-assessed exact
catalog identity. Reported model text and unresolved/conflicting identity remain
visible as such. A client-provided catalog ID alone is insufficient. Historical
rows without an assessment remain unassigned; no adjacent installation or time
match supplies identity. The cards describe model-and-variant history; no unique
physical-watch identifier is collected.

The model detail adds a separate Updates card and Update history, scoped to all
retained nonlocal reports for that exact identity. The Installs and Updates
cards share one design (same classes, label and value sizes), carry no `All
time` chip, and show plain Successful, Failed and Blocked before writing counts
without links (owner decision 2026-10-06); the Update history outcome filters
open the matching records. The Administration card has two separated sections,
Install policy (Install policy and Public compatibility as label/value rows) and
Support metadata (Support status and Save), with no optional note fields.
Blocked results stay in
history and outside the attempt denominator. Summary totals are independent of
history pagination and diagnostic resolution. Conflicting logical reports remain
visible with an ambiguity notice and are excluded from completed counts.
Updates never change installation metrics or public compatibility evidence.
The Installs card labels its timestamp `Last report` (the last installation
report); it is not a combined installation/update activity timestamp.
On the model detail page the Installation history sits in the right-hand
column (two-fifths summary, three-fifths history at ≥1024 px) and renders as
compact table rows there: Date, Map, Result pill, Error, App version and the
Inspect action, plus the GitHub issue column whenever a listed row has a linked
issue. Below 1024 px it keeps the record-card layout. Filters, pagination and
Inspect dialogs are unchanged.
The broad Devices listing keeps its existing compact columns.

### Model sources

`/admin/device-identification` is visibly named `Model sources` (Tools menu).
It is a rarely used tool kept aligned with the rest of Admin (owner decision
2026-10-06). The list opens with one summary card of plain Needs review,
Approved, Rejected and No source numbers (no scope chips, no icons; Needs review
stays neutral because a source decision changes no installation, permission or
public compatibility). Below it the Installations filter bar holds the state
quick filters (All, Needs review, Approved, Rejected, No source; Needs review is
preselected when any listed model needs review), the server-side model or code
search (`?q=`), the result count and Clear, which shows only when the state
differs from its default or a search is active and then returns to the
unfiltered list. The table (Model, Garmin code, Source, State) sorts through the
shared sorter, State in queue order; the model name opens its review. It has no
records line and uses the shared 25-row pagination. The detail keeps the human
workflow `Source says` ⇄ `Catalog model` (side by side) → `Same code` →
`Confirm` → `Technical details`: a `Model sources` back link with `Next in
queue` (the next model that needs review) sits above the heading, each source is
one Admin card, Technical details is its own collapsed card, and the cards are
spaced by `--admin-card-gap`. Approve match is the only Interactive Primary
control; Same code states and the current decision are status pills (text plus
icon). Raw codes, mapping/catalog IDs, source revision, policy internals,
missing-source inventory, and decision history remain secondary in Technical
details. Mapping review does not reassign historical installations
automatically.

### Providers and collection history

Provider health, collection outcome, available packages, and broken artifacts
remain separate. Updates count newly discovered plus changed packages for that
run; they do not count every artifact. Unknown historical counts remain unknown.
Technical source/review controls remain available behind disclosure.

The Providers list says "Issues", not "Problems", in its visible copy and
accessible labels. Its heading meta shows `Last sync` with the latest catalog
sync on the right, like Devices; Last sync is not a tile. One summary card
(the Installations `installation-kpis` card with one metric row and no scope
chips) holds Active and Healthy (each with `of N`), Package issues and Provider
issues, using the shared provider-problem definition. The Issues column counts
affected packages with problematic sources in the same line ("2 packages · 2
sources", with "with issues" as screen-reader text). It is a plain right-aligned
number like the other numeric cells, rendered with the shared error counter:
danger text for a positive count, plain text for `0`, never a pill or icon. Its
numeric `data-sort-value` is the affected-package count. An unknown count shows
`—` with `Unknown` accessible text, never `0`, and sorts last. Retired or
resolved historical entries do not enter current counts. Measured zero,
unknown/unavailable, stale, and partial remain distinct.

Provider detail (owner decision 2026-10-06: shorter, nothing removed) reads top
to bottom: the action bar, one summary card, Issues, Packages, Checks and Syncs,
then Technical details. The action bar holds Check provider health (the only
Interactive Primary action), then secondary Refresh catalog, Pause or Activate,
Turn previews on/off and More (Retire provider). The previews switch keeps its
authenticated, CSRF-protected provider action; there is no separate Map style
previews card. The summary is one card of tiles (`_metric_row`, no scope chips,
like Installations): Health, Catalog, Package issues, Downloads and Previews
(On/Off plus only the layer states that occur, for example `6 published · 3
failed`). On this page the word is **Issues**: the Issues card groups package
issues by recorded reason; other pages keep Open problems and Package problems.
Each group shows its package count, one Recheck (a single-package group
rechecks that package; a larger group's `Recheck affected` and the card's
`Recheck affected packages` recheck every affected package) and at most five
rows with Recheck, Open source and Copy details, plus `Show all N in Packages`.
Packages is the one package list: search, Issues/Available filter (Issues is
preselected when issues exist), pagination, and a per-row `⋯` menu with
Recheck, Disable or Enable downloads, Open source and artifact details. An open
row menu floats above the table (fixed position below its button, or above it
when there is no room below), so the table's scroll box never clips it; one
menu is open at a time and Escape, an outside click, scroll or resize closes
it. A column whose header is only screen-reader text (Actions) is not sortable.

Checks shows the latest result, the Automatic health checks row (label, native
interval select styled as an Admin control, and Save interval, all one control
height), View check details, and a link to its history. Syncs shows the latest
run, the catalog sync time, the latest run's updates (and error, if any) and a
link to Collection history. The two share a row at one height only when both
fit (wider than 1180 px) and stack otherwise or while check details are open.
Tabular content is never placed in a half-width card.

Technical details is one full-width card, collapsed by default, holding the
rarely needed lists behind one tab switcher (one panel at a time): History
(admin audit), Health checks, Syncs (collection runs plus Releases), Preview
layers (with what previews do), Download links (when the provider has any; its
search, Broken filter and 25/50 pagination stay) and Attribution (attribution
facts plus Original links). The Checks and Syncs history links open the card on
their panel. Long lists start short and reveal the rest in place with `Show N
more` — History and Syncs five rows, Health checks five, Preview layers and
Original links ten — so no list paginates or scrolls inside the card. Table
cells wrap inside the full-width card; at 760 px and narrower the tables become
labelled records. A History release-change reason lists three changes and keeps
the rest behind `+N more` in the same cell; the full audit record stays behind
Raw record. Provider names come from the catalog provider name, never from the
provider ID.

Provider **View check details** shows only the latest observation as labelled
check/status pairs, its reason, observation time, next scheduled check and stale
warning. It must fit the card width without a horizontally scrolling history
row. The source of evidence is the Terento server; do not imply every user's
network has the same result or that a complete map install was verified.
Download-server availability is separate from website and catalog health.

Automatic checks offer 1, 6 or 24 hours per provider (default one hour). Saving
uses the authenticated, CSRF-protected provider action. Health check history is
at most ten previous checks within 30 days, each a compact timestamp, result,
counts and observed reason, five visible before `Show N more`. It has no
pagination or growing scroll container; the latest observation remains available
even when stale. Collection and admin audit previews likewise show at most ten
rows; limiting the preview never deletes administrative audit evidence.

Current, nonretired map rows expose **Disable downloads** / **Enable downloads**
separately from artifact validation. Disabling requires a nonempty internal
reason, which is escaped in Admin and is not public user copy. Administrator
choices survive catalog refresh and automated checks. Enabling removes only the
manual block and cannot override provider availability or artifact validation.
Retired maps/providers have no usable download control.

### Health

Health (owner decision 2026-10-06) has, top to bottom: one summary card with
plain Failed, Degraded, No data and Healthy tiles like Installations (no icons,
no scope chips, not buttons; Failed is red only when positive); the shared filter
bar with an All/Failed/Degraded/No data/Healthy quick-filter group (the pill
labels) and search, which is the only filter; one Issues card; and one Technical
details card.

Issues lists every Failed or Degraded check as one compact table row: Check,
Status pill, Reason with the next action under it, Last checked and a small
Details control. The action is a link when a real target exists (Providers for
Catalogs, the retained GitHub Actions run for workflow-backed checks) and muted
help text otherwise. Details opens the check's technical evidence inline under
its row; there is no separate disclosure per check. With no Failed or Degraded
check the card shows `No issues.`

Technical details is one full-width card, collapsed by default, with ARIA tabs
(arrow keys, Home and End) in the provider-detail pattern: Service (API,
Database, Scheduler, Issue sync), Releases (Website deploy, API deploy, Release
match, Weekly tests, Email report), Catalogs, Search and Weekly results (the
weekly suite table and run link). Each group tab shows its `N/M healthy` summary
and every check of the group not already listed under Issues (Healthy and No
data), each with Status, Last checked and Details; a No data row keeps its
reason under the name and its next action in Details. Quick filters and search
hide non-matching rows everywhere; when a match exists only inside a group tab
the card opens on that tab. `?status=FAILED` (or another status value)
preselects the quick filter, and changing it keeps the query in sync.

Every check shows a real Last checked time when one exists: the retained
observation time for workflow-backed checks, the page's snapshot time for the
live API and Database probes, the scheduler heartbeat's last write, the latest
issue-sync check, and the latest provider health check or catalog collection for
Catalogs (each provider's own time is in Details). Only a check with no recorded
time shows `—` with `Not recorded` accessible text.

Provider catalogs are one Catalogs check (worst provider state, each provider
linked) that links to Providers instead of one card per provider. Vendor and
pipeline names (SMTP2GO, IndexNow, manifest) stay in Details. Search indexing
reports IndexNow submission state as one independent check and does not imply
that a submitted URL was indexed.

### Campaign links

Tools → Campaign links (owner decision 2026-10-06) is one local, client-side
builder card: no persistence, no API and no analytics storage. Its vocabulary is
owned by `src/terento_catalog/campaign_links.py`; the page renders and the
script embeds those constants, so the browser cannot drift from the tested
contract. A short `When to use campaign links` note opens the card (use one for
every terento.app link posted outside the site; pick the channel where it is
posted; reuse one campaign name per effort). Every control has one muted help
line saying when to use it; there are no information popovers.

Choices are quick-filter groups in the filter-bar design (buttons with
`aria-pressed` driving a hidden select), never dropdowns:

| Where will you share this link? | `utm_source` | `utm_medium` |
|---|---|---|
| Reddit post (default) | `reddit` | `community` |
| Garmin forum | `garmin_forum` | `community` |
| GitHub | `github` | `referral` |
| Discord | `discord` | `community` |
| Facebook group | `facebook` | `social` |
| X post | `x` | `social` |
| Email | `email` | `email` |
| Other | typed source | Social, Community, Email, Referral (default), Paid social or a typed medium |

The free-text source and medium fields appear only for Other. Destination is
Home (default), Download, Compatibility or `Other page…`, which reveals a
terento.app-only path or URL field. Campaign is one of `early_beta` (default),
`launch`, `compatibility`, `community` or `Custom…`, whose name is normalized
live (shown as `Used as …`) and stored canonically when the field loses focus.
`Where exactly (optional)` fills `utm_content` with a channel-specific example
hint; `utm_term` sits behind a `More options` disclosure. Every value is
normalized with `normalize_value` and limited to 80 characters, the longest
value the public site forwards to Umami (`site/privacy-consent.js`).

The result is always visible: a read-only, wrapping JetBrains Mono link field,
a `Copy link` Interactive Primary button (Clipboard API, falling back to
selecting the field), and one inline line `Umami will show: source … · medium …
· campaign …` (plus content and term when set). Incomplete input disables Copy
and shows a status line with an icon and text naming the missing value; copy
success and failure are status lines with their own icons.

### Resilience

A failing sub-query renders only its card as `Unavailable` with a Retry link
inside the admin chrome; the rest of the page keeps working. HTML routes never
answer with raw JSON: an invalid link, a missing page and an unavailable page
are HTML error pages with the navigation. The review summary query runs only for
the Dashboard.

### Freshness notice

Every page with `#main-content` renders `data-admin-revisions`: one hash per
section of data that the page itself displays. While the tab is visible the page
re-reads its own URL every two minutes, and once when the tab becomes visible
again, and compares the fresh revisions with the rendered ones. A notice appears
only when a revision differs, so a refresh with no new data never brings it back
on the next poll; a client-side section render acknowledges its own sections.

Revisions hash displayed data only (owner report 2026-10-07). They exclude
request-time values (for example the First run `since`/`until` window, render
time, CSRF and nonce values), observation and schedule clocks (health check,
heartbeat, download poll and next-check times), payloads a page does not render
(the Dashboard hashes no compatibility evidence, provider rows or Maps unknown,
and no in-progress download rows; Maps hashes provider names only), zero chart
buckets that only move with the rolling window, and list order. A new or
changed installation, report, count, status or displayed row still changes the
revision, as does an event leaving a rolling period.

The notice is one compact info status inside the content width (floating near
the bottom, centred on wide screens and spanning the 16 px gutters on phones):
the info icon and `New data is available for this page.`, a secondary `Refresh`
button directly beside the text and an icon-only Dismiss button. It uses the
Admin surface, the info status border, the control radius and a 44 px touch
target on phones; it is `role="status"` with `aria-live="polite"` and never
takes focus. A failed check (`Live check unavailable. Refresh to try again.`)
or an expired session uses the warning icon and border. Refresh reloads the page
and asks before discarding unsaved edits in a POST form. Dismiss hides the
current state until a different change or state arrives.

### Responsive and layout invariants

Admin preserves consistent left edges and the existing spacing scale, with no
block overlap or page-level horizontal overflow. It remains usable at effective
200% zoom, uses one compact menu column, keeps charts visible rather than
collapsed, and trailing-aligns numbers and dates where practical. Cards that
share a grid row (Dashboard and Maps) stretch to one height; charts in a row use
one chart height, the shorter card's spare space sits below its content and an
`All time` line aligns to the card bottom. Controls retain keyboard focus,
readable labels, and existing `aria-sort` semantics.

Separate cards, tables and sections stacked anywhere in Admin keep one clear
gap from the spacing scale: 24 px, and 16 px at 700 px and narrower. Grid rows
and columns of cards use the same gap, so consecutive cards in one column (for
example Installs, Updates and Administration on a device page) are equally
spaced. The only tighter case is a filter bar directly above its own table,
which keeps 12 px (a filter bar drawn as the table's attached header keeps no
gap). Rows inside one table or list are not separate cards; labelled mobile
record rows keep their 12 px row gap. The spacing belongs to the containing
layout (`--admin-card-gap`), never to both the layout and the card.

One-card KPI rows (owner decision 2026-10-07): a summary card holding one
metric row (`installation-kpis` on Installations, Devices, Providers, provider
detail, Health, Model sources and Update reports, and the `admin-kpi-panel`
Installs and Updates cards on device and diagnostics pages) fits two rows at
760 px and narrower: five or three tiles use three columns (3 + 2, or one row),
four or two tiles use two (2 + 2, or one row). Columns share the width equally
and widen only as far as a pill or number needs. Within each row of tiles the
labels share one top line and the values one line below the tallest label, so
a wrapped label never moves a number off the shared baseline. A long value
wraps instead of overflowing. On Devices, Covered spans two columns so Pending
policy sits under Verified, and its rate is a separate half-size part on the
count's line (owner decision 2026-10-07). Desktop layouts are unchanged.

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

Provider recovery respects HTTP 429 Retry-After cooldown across package rechecks, catalog collection and health checks. A matching active request reuses its job; a different scope waits for the active provider job. Sources display artifact validation state, separately from provider enablement.

Activity keeps the failure status as plain text and provides `View failure` as
an inline text link without a button border or padding. The Maps Updates failed
count uses the shared failure counter without a link; the update report list is
reached from Tools → Update reports.
