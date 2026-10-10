# Terento statistics contract

## Update diagnostic continuation — local 2026-10-02

The local producer records the actual safe-update write boundary. A failed
operation before that boundary reports `NOT_STARTED` through diagnostics and
creates no `MAP_UPDATE_FAILED` result. A terminal write failure reports `FAILED`;
success reports `SUCCEEDED`. The operation ID is shared with the local report
and any emitted update statistic. Missing remote objects do not imply that no
write was attempted.

Update acquisition events come from the real provider acquisition observer:
`DOWNLOAD_STARTED` begins at the downloader boundary, `DOWNLOAD_PROCESSING`
begins when returned bytes are being validated, and a single terminal result
records success, failure or cancellation. A failure while validating or
extracting downloaded bytes is a failed acquisition, matching installation
acquisition semantics; it is not a failed device write. Policy, identity or
workspace failures before the downloader boundary create no download attempt.
All phases share one acquisition ID, the main component and the update's
operation ID. They use the independent map-usage sharing preference.
Unmeasured update progress is omitted from diagnostics; cleanup attempt and
result fields describe the cleanup actually performed by the transaction.

Schema-v4 `operationKind=update` evidence is retained in the separate
`map_update_diagnostic` store. It never contributes to fresh-install counts,
success-rate denominators, provider install popularity or compatibility gates.
Map-statistics events remain authoritative for global/provider update totals;
diagnostic arrival, duplicates or opt-out cannot create another map-event result. Historical update events are
not reclassified without evidence about their write boundary.

Status: active
Semantics version: 2
Effective date: 2026-09-17

This document is the canonical meaning of Terento's retained statistics. It
describes read-model classification, not a promise that every installation or
download is reported. The statistics are privacy-minimised, aggregate evidence
and may be incomplete because users can disable either telemetry stream,
reports can be lost, and old releases emitted less information.

## Populations

Terento keeps four related but separate populations. App first-run funnel
sessions ([`APP_FUNNEL_CONTRACT.md`](APP_FUNNEL_CONTRACT.md)) are a fifth,
independent population: they are never mixed into acquisition, fresh-install,
update, download, compatibility or Needs attention counts. Web installer page
loads and relay jobs ([`WEB_INSTALLER_STATISTICS_CONTRACT.md`](WEB_INSTALLER_STATISTICS_CONTRACT.md))
are another independent population with the same rule: every count below
(installs, updates, downloads, failures, watch and model statistics) is app-only,
and web records appear only on the Admin Web installer page and behind the
Dashboard charts' Web switch. User-sent support
reports ([`SUPPORT_REPORT_CONTRACT.md`](SUPPORT_REPORT_CONTRACT.md)) are not a
statistical population at all: they are review work only and never change any
count, rate or chart. Optional installation-report `inventoryMetrics`
(pre-/post-write inventory object counts and durations) are diagnostics only:
they never add, remove or reclassify any acquisition, install, update, download
or compatibility count.

- **Acquisitions** are provider-download attempts. Only terminal
  `DOWNLOAD_SUCCEEDED` and `DOWNLOAD_FAILED` events count. `STARTED`,
  `PROCESSING`, `CANCELLED`, `INTERRUPTED`, missing, and unknown terminal
  states are excluded. A custom `.img` import is not an external provider
  acquisition. `acquisitionPurpose` records `install` or `update` independently
  of the eventual device outcome. Missing historical purpose stays unknown.
  Downloads totals and charts include all purposes; their breakdown explicitly
  separates install, update and unknown acquisitions. A download is not an install.
- **Fresh main-map installs** are independent main-map results. One result is
  identified by `operationId + mapResultIndex` and retains provider, region,
  package/map, and component/acquisition correlations where available. An
  `operationId` alone is a batch identity, and provider + region alone is not a
  map identity. Legacy events use their event ID because their stronger
  identity was not available; a missing historical `mapResultIndex` is never
  backfilled by inference.
- **Optional components** (for example OpenTopoMap contours) belong to the
  selected main map. They are never another fresh install. Their selected,
  verified, failed, not-started, and unknown state remains visible as an
  addon/component warning or diagnostic fact. An independently selectable catalog
  package with a main artifact (including MapRando France IGN contours) is its
  own main-map result; a provider/name heuristic must not exclude it.
- **Updates** are a separate population. Only confirmed terminal
  `MAP_UPDATE_SUCCEEDED` and `MAP_UPDATE_FAILED` results count, and only an
  update that reached its write boundary can be a failed update. An update
  acquisition failure before writing is a failed acquisition with update
  installation not started.

## Fresh-install classification

An independent fresh main-map result is a success only when the main map and
all required components are verified and the device installation result is
real. A failed fresh install requires reliable evidence that installation or
verification was attempted; `writeStarted=false` is not a failure. A write can
fail at zero bytes, so a byte count is not the write-boundary test.

The server may classify an event as `OUT_OF_SCOPE_PREWRITE` only when its
canonical catalog row has `active=false` or stored `map_capable=false`, and
the event explicitly reports
`writeStarted=false` and no remote object. This is a policy block, not an
installation failure: it contributes no fresh attempt, failure, success rate,
update result, provider/custom statistic, model-card count, review task or
public statistic. The raw diagnostic, reason and exclusion audit remain
retained. An out-of-scope event that reports a write boundary or remote object
is instead retained as a separate `OUT_OF_SCOPE_WRITE` security-review issue;
it is not silently removed from statistics. Missing/NULL write facts,
historical unknown devices, and unrelated models are preserved and are never
mass-excluded from name heuristics. `support_status` and model-name heuristics
do not classify a new event as out of scope.

Pre-install download, extraction, source validation, device-check, storage,
identity, cancellation, or unknown failures do not create a fresh attempt or a
fresh failure. They remain available in diagnostics and acquisition/activity
history. An unambiguous legacy record with no write field may retain its
historical attempted-write interpretation; current missing or conflicting
facts are excluded from the fresh denominator. A record is an unambiguous legacy
record when it has no write fact and its stored evidence schema version is 1 or 2;
rows received before the schema version was stored (NULL) qualify only when they
also carry no app build and no release label. One SQL function,
`terento_fresh_result_classification`, implements this for every read model.

For every read model:

```text
F_success  = verified main-map fresh results
F_failed   = confirmed started fresh failures
F_completed = F_success + F_failed
F_success_rate = F_success / F_completed, when F_completed > 0
```

When `F_completed = 0`, the UI displays an em dash rather than zero percent.
The pure reference classifier (`statistics_semantics.py`) and the SQL read models
(`compatibility_model_statistics`, `map_statistics`)
run the same fixture cases in a PostgreSQL parity test; when they disagree, this
contract decides which side is corrected. Conflicts are detected per logical
result over classification, provider, region and assessed device, and legacy
acquisitions without an acquisition ID keep their event identity in both.
The identities are stable across views: two selected provider maps produce two
fresh results; a provider map plus contours produces one; a provider map plus a
custom `.img` produces two; a fresh install plus an update produces one fresh
result and one update result; two updates produce no fresh result.

Administrative Resolve/Reopen changes review work, never historical verified
successes, started failures or model coverage. Classify conflicts at the logical
result level before aggregating by exact model, so a conflicting identity cannot
create two attempts.

Replay of the same event ID is zero additional work. A real retry must carry a
new operation/result identity and counts as a new result. The read model never
guesses a missing identity, provider, region, country, or device identifier,
and does not persist a user ID or watch ID for correlation.

## Telemetry streams and linkage

The map-statistics stream records provider acquisitions and explicit provider
fresh-install or update results. Its `mapId`/package, provider, region,
`acquisitionId`, and `componentKind` fields describe the map-side fact. The
compatibility-evidence stream records device-model evidence for each main-map
result, including `operationId` and `mapResultIndex`, plus optional-component
outcomes and write-boundary facts. The two streams may describe the same result
but are independently consented, delivered, stored, and deduplicated.

Producer rule for fresh map results (app candidate after beta.18): the map stream
emits `INSTALL_SUCCEEDED` when the selected map's main component is verified, even
if an optional component failed; that warning remains a diagnostic fact.
`INSTALL_FAILED` is emitted only when the main component reached its device write
boundary and failed. Identity, preflight, acquisition and other pre-write failures
emit no `INSTALL_*` map event; a provider download keeps its own acquisition
terminal. Maps completed earlier in a batch keep their result when a later
boundary read fails. Older clients' events are not reclassified, and the read
model's write-boundary filters above still apply to them.

When both streams contain a trustworthy shared operation identity, linkage also
requires an unambiguous provider/region and map/package match. An operation ID
alone is not enough; provider + region alone is not enough when sibling maps or
custom images are possible. A legacy map terminal with multiple possible diagnostic results remains ambiguous;
it does not add another completed result on top of those retained diagnostics.
A missing or delayed stream preserves the received
map-only or device-only fact and does not synthesize the missing side. A custom
import can contribute a common fresh result without becoming an external
provider acquisition or receiving guessed catalog geography.

Linkage is evaluated per independent map result, never once for an entire
session. The read model must not use `min(provider)`, timestamps, model, or
region as a session identity. A success for map A and a failure or missing
diagnostic for map B remain independent. A reliably linked diagnostic message
counts as linked whether its outcome is success, failure, incomplete, or
unknown; an absent message is an observation gap, not a failed installation.
A current map-side terminal failure without reliable write-boundary evidence
remains a raw diagnostic/activity fact and is excluded from fresh attempts. A
linked failure before the device write boundary is excluded for the same
reason. The legacy allowance applies only to unambiguous records from before
the write fact existed; it is never inferred for current missing evidence.
The private coverage metric is:

```text
fresh map diagnostic coverage = reliably linked fresh map attempts /
                                all selected fresh map attempts * 100
```

Devices has a separate catalog-evidence coverage metric:

```text
map-capable model evidence coverage =
    active exact catalog models with stored Maps=Yes and at least one
    retained verified successful installation /
    all active exact catalog models with stored Maps=Yes * 100
```

The numerator is a distinct exact-model count, not a count of installations.
Resolved diagnostics retain their historical verified result. Stored Maps=NULL
or Maps=No, inactive rows, unresolved text identities and inferred capability
are excluded from both sides. A model retired from Garmin retail stays active
(`contracts/INSTALLATION_AUTHORIZATION.md`) and is counted like a reviewed
historical row. This metric is not support status, public
compatibility, diagnostic linkage coverage, or native write authorization. It
belongs to the device catalog evidence view and is not presented on Dashboard
or Maps.

The linkage object keeps its historical operation/session compatibility fields
(`mapOperationCount`, `linkedOperationCount`, `mapInstallationCount`, and the
related `*InstallationCount`/`linkageRate` values) at operation-key scope.
`mapSessionCount` is the distinct non-null operation UUID count. The explicit
`freshMap*` fields are the per-map-result fields used by the coverage formula:
`freshMapAttemptCount`, `freshMapLinkedDiagnosticCount`,
`freshMapMissingDiagnosticCount`, and
`freshMapDiagnosticCoverageRate`. A compatibility field is not silently
reinterpreted as a per-map count.

Session counts are reported separately. Custom activity without a map-usage
stream is not a missing map-telemetry observation, and a provider event plus a
custom result does not invalidate a reliable provider link. A diagnostic that
arrives late can change linkage for that map result. For a map-side success it
never changes the selected fresh-attempt (coverage) denominator. A map-side
`INSTALL_FAILED` needs write-boundary evidence, so it enters fresh attempts —
`F_failed` and the coverage denominator — only once its linked started-failure
diagnostic has arrived; until then it remains a raw activity fact.

## Update and acquisition formulas

```text
A_success = terminal provider DOWNLOAD_SUCCEEDED attempts
A_failed  = terminal provider DOWNLOAD_FAILED attempts
A_completed = A_success + A_failed
A_success_rate = A_success / A_completed, when A_completed > 0

U_success = confirmed started MAP_UPDATE_SUCCEEDED results
U_failed  = confirmed started MAP_UPDATE_FAILED results
U_completed = U_success + U_failed
U_success_rate = U_success / U_completed, when U_completed > 0
```

The update acquisition result does not change `F_success`, `F_failed`,
`F_completed`, compatibility thresholds, compatibility status, map coverage,
or fresh-map popularity. An update may update last-update/version information
in map history, but it is not a fresh install.

Provider acquisition failures before the device write boundary are acquisition
facts only. A `write_started=false` diagnostic with download stage or
`INSTALL_BLOCKED_DOWNLOAD_FAILED` is classified as `PRE-INSTALL` /
`NOT_STARTED`: it is excluded from fresh-install attempts, failures, model
compatibility statistics, open installation problems, and installation review tasks. Raw
diagnostic and map-event facts remain retained and visible in acquisition
activity. `STARTED`, `PROCESSING`, `CANCELLED`, `INTERRUPTED`, stale and
missing terminal outcomes do not enter the acquisition failure denominator.

## Exact-model reported update results

Private model detail has a separate diagnostic population: all retained nonlocal
update reports with a server-assessed exact catalog identity. It describes the
model and variant, not an individual physical watch. Client ID hints, neighboring
installations, names alone and timestamps cannot establish that identity.
Historical unassessed rows remain unassigned.

A logical update is grouped by operation ID, provider and normalized region.
Repeated event IDs are idempotent. Different reports for that logical result
count once only when assessed identity, outcome, write-start and finishing facts
agree; a conflicting group remains in history and is excluded from completed
counts. No latest-report rule chooses a winning model or outcome.

- Successful: explicit write started, SUCCEEDED and VERIFIED finishing.
- Failed: explicit write started and FAILED.
- Not started: retained history, excluded from attempts and failure counts.
- Attempts: Successful + Failed. Zero attempts give an unavailable rate, not 0%.

These counts use the complete retained history, not the loaded page. Resolution,
issue linking and reopen actions change review state only. The summary identifies
its scope as reported results/all time. It may differ from the independent global
map-statistics stream because sharing and delivery differ. It is never added to
fresh-install totals, compatibility promotion, provider popularity or map coverage.

## Charts, cards, and activity

The Dashboard installation trend is an installation-outcome chart. It must never
include download or pre-install acquisition events. Its App view (the default)
and every rule in this section are app-only; the Web view of both Dashboard
charts is defined by the web installer statistics contract.

Fresh-install outcomes and map-update outcomes are separate statistical
populations. Updates must never change fresh-install counts or success rates.

Its fresh series are provider fresh successes, custom fresh successes, and
confirmed fresh-install failures (including custom). Successful updates and
failed updates are separate series. Colours (owner decision 2026-10-05; existing
brand tokens only, and every series also has a text label and legend entry):
provider fresh install successful uses the existing slate/sky series; custom
`.img` fresh install successful is its own green (Lichen family) series and
legend entry; install failed is solid red; update successful is solid Stone
Dark (the warm stone family's 5.16:1 shade, with no outline; Warm Stone itself
is below 3:1);
update failed uses red diagonal stripes in bars and legends. This supersedes
every earlier chart colour rule. Fresh attempt totals are
`F_success + F_failed`; download, pre-install, device-check, not-started,
cancelled, and unknown events are not chart series.

The map-statistics read model keeps fresh-install outcomes, acquisition
outcomes, and update outcomes separate. Period views use the selected period;
all-time views say so explicitly. The Admin period set is `today`, `24h`, `7d`,
`30d` and `all` (owner request 2026-10-07 added `today`). `today` is the
current calendar day in the request's time zone: it starts at local midnight
(where a DST change skips midnight, at the day's first existing local instant)
and runs until now. The other periods are rolling windows ending now; `all` has
no start. Period boundaries use the server/read-model timezone supplied by the
request (an absent or unknown zone is UTC), and timestamps remain immutable
source facts.
Client clocks can run ahead: when a reported time is more than 10 minutes after
the server receipt time, the map-statistics read model uses the receipt time for
that event (map events and diagnostics alike) in period filters, KPIs, canonical
result time and chart buckets, so a KPI never counts an event that no chart bucket
shows. Smaller skew keeps the reported time, and the stored fact is unchanged.
The read model selects one representative terminal result before bucketing:
acquisitions use their acquisition ID, current installs operation/result index,
and legacy records without that identity retain their event identity. Contradictory
terminal facts stay inspectable but do not enter completed totals. Repeated
identical reports use the earliest terminal time. For a reliably matched fresh
map/diagnostic pair the earliest of their terminal times is the canonical result
time, so a later matching map report cannot move a diagnostic result out of its
original period. Ambiguous matches cannot supply another result's timestamp.
An explicit dateTo bounds both bucket selection and display filling. Repeated
local hours at DST rollback retain distinct real-hour bucket identities.
The Today and 24-hour trends are hourly (Today from local 00:00 to the current
hour), seven-day trends are daily, and 30-day trends are weekly. All-time trends use the observed span: up to 14 days is daily, 15–60
days is weekly, and longer spans are monthly. Missing display buckets keep the
existing zero-fill rule; bucketing never interpolates or invents events.
Admin labels and grouping are owned by
[`admin-behavior-contract.md`](../backend/catalog-api/docs/admin-behavior-contract.md).

Popular maps uses only known provider-catalog packages and successful fresh
main-map installs. Custom `.img` rows, optional components, updates, and
downloads are excluded from this population before grouping, sorting, Top countries,
search, or pagination; they remain available to the common statistics and
other views where their existing formulas require them. Top countries and Regions
group by canonical country/region across providers. All maps groups by
canonical country/region plus provider. A popularity timestamp is the last
successful fresh install eligible for that grouped row, not arbitrary activity
or an update. The Admin presentation labels the summary view `Top countries`
and shows up to 10 ranked countries. Top countries, Regions, and All maps rows
use compact primary/secondary geometry, so an absent optional date does not
reserve an empty line. These are presentation rules only and do not change the
popularity population, grouping, ordering, or pagination.

Map-statistics `provider`, `map`, `region`, and date filters define the KPI,
coverage, and popularity population. `eventType`, `outcome`, and pagination
filters affect only the Event detail disclosure. Therefore event-detail
filtering, outcome filtering, and page changes must not change KPI totals,
success rates, coverage, or popularity. An empty detail result does not erase
the selected population's summary or show an overall no-data state. Initial
HTML and asynchronous refresh use the same population summary.

GitHub download history is a display of observed cumulative-counter increases
between valid checks, not individual downloads. The first valid observation is
a baseline and contributes no increase. An unchanged valid counter is an
observed zero; an absent check is unknown and is not filled with zero. Counter
decreases and confirmed release/asset-population changes are discontinuities.
Missing newly introduced metadata must not automatically invalidate historical counter observations. Observed counter deltas and population-comparability confidence are separate dimensions.

The collector retains a separate small `github_release_marker` population from
the authoritative GitHub release collection. A marker is attributable to a
chart interval only when its stable GitHub release identity is retained and its
published time falls strictly after the previous observation and at or before
the current observation. This permits historical release backfill and multiple
releases in one chart bucket without binding release identity to one snapshot.
Release names and dates are never inferred from a counter jump. Legacy rows
without a retained marker, asset-only changes, and counter decreases remain
unattributed boundaries.

The GitHub read model uses these meanings:

GitHub download trends use the same bucket rule as the map trends, so one
Dashboard period selects one grid for every chart: Today and 24 hours hourly,
seven days daily, 30 days weekly, and all time adaptive by the observed span since the first
retained snapshot (up to 14 days daily, 15–60 days weekly, longer monthly).

For the hourly (Today and 24-hour) trend read model, `hour_start` is the
canonical hourly floor of an observation. The exact `observed_at` remains
available as factual interval metadata. This changes display bucketing only: deltas, baselines, gaps,
discontinuities, legacy confidence, partial aggregation, and period-boundary
handling continue to use the real retained observations. The Admin chart's
equal-width slots and `HH:00` labels are presentation rules in
[`admin-behavior-contract.md`](../backend/catalog-api/docs/admin-behavior-contract.md).

The trend `state` carries interval continuity and rendering semantics;
`confidence` carries whether a retained delta is `legacy`, `verified`, or
`partial`, while `population_comparability` carries `baseline`, `verified`,
`unconfirmed`, `mixed`, or `changed` population evidence.

- `baseline`: the first observation in the retained history; it has no delta.
Every trusted non-negative interval is rendered as a normal bar, including a
trusted `+1` in the final slot. A counter decrease or confirmed population
change remains an unattributed data boundary and is rendered with a visible
`Data boundary` label and accessible reason; it is never represented as a
dashed zero-only value. Independently retained release markers in the same
interval add `New release` or `New releases · N`; both labels may coexist and
the exact release labels remain available in accessible text.

- `legacy`: a nonnegative counter delta retained from an interval where one or
  both observations lack the post-057 asset count or population fingerprint.
  It is a legacy observed counter delta, not a verified count of individual
  downloads; population comparability is unconfirmed. Arrival of the new
  metadata alone is not a discontinuity, and equal `release_count` alone does
  not prove that the asset population is unchanged.
- `verified`: both observations have complete population metadata and the
  stored release/asset identity facts agree, so the counter delta is
  population-comparable.
- `partial`: an aggregated day or month has some known deltas and one or more
  uncertain or discontinuous intervals. Known values remain visible and are
  labelled partial; an observed zero in such a bucket is not a confirmed
  full-bucket zero.
- `discontinuity`: a counter decreased or the stored facts confirmed a
  release/asset-population change. The affected interval has no fabricated
  delta and remains separately marked.
- `gap`: a retained nonnegative delta spans missing checks; its previous and
  actual ending `observed_at` values remain visible and the interval is
  uncertain. Missing intervals are never rendered as fake zero observations or
  used to spread a delta across hours.

Increases across a selected-period boundary may also be shown as an uncertain
observed interval, retaining the previous observation time, the actual ending
`observed_at`, both deltas, and the continuity state; no individual download
time is invented. Failed collection leaves the last successful snapshot and
its timestamp unchanged.

The Providers view reports separate last successful install and update dates.
Popularity dates remain fresh-install-only. Diagnostic-only update NOT_STARTED
outcomes appear in Activity as blocked before writing with a retained report
link/reason when reports agree. They do not fabricate map telemetry, write
failures, or additional successful/failed update totals. Missing, disabled or
unassigned diagnostics cannot be reconstructed from acquisition completion.

A map event whose `mapId` was not yet in the catalog keeps that exact reported ID;
when the package is published later, read models attribute the event to it by
exact identity. This is not a provider + region guess.

Recent map activity remains mixed and may show provider downloads, fresh
install outcomes, optional-component warnings, and updates. Map history keeps
the installed map and version facts, including unknown or unmapped values.
Fresh popularity and country coverage use only successful main-map fresh
installs. Custom fresh results may be included in common fresh totals but do
not acquire a guessed provider, region, country, or map package. Unknown and
unmapped results remain visible as unknown/unmapped rather than being silently
discarded or assigned by provider + region heuristics. In particular a
diagnostic-only fresh result (no matching map event) keeps an unknown package and
geography even when exactly one catalog package currently has its region; it
counts in fresh totals but never in popularity or country coverage.

Provider problems are three separate current-state populations: affected
packages (unique current package IDs with at least one failed or unavailable
artifact), problematic sources (unique trusted source identities for those
artifacts), and the latest provider-health check state/error. The same source
on two packages is two affected packages and one problematic source; two broken
artifacts in one package remain one package. A health-only error creates no
package or source problem. Retired/resolved historical rows are excluded from
the current counts, and the full current catalog population is counted before
any display pagination.

The private Needs attention read model counts active actionable tasks, not unique incidents.
Installation failure-diagnostic review and GitHub handling for one operation are alternative
states of one task; linking an issue moves that task between categories and
does not add a second task. Identity review is an independent task, and
publication review is counted per exact model. Installation queue entries use
operation-level grouping. This installation task is the single definition of an
open installation problem: one operation with an active, nonlocal, non-excluded
`phaseOutcome=FAILED` diagnostic that is not a provider download/pre-install
failure and has no linked GitHub issue. Pre-write preflight/storage blocks are
open problems (they need review) even though they are not fresh failures.
Installations `Open problems`, its per-identity column and model detail use this
same predicate and unit; each operation is attributed to exactly one identity so
the rows sum to the total, and Dashboard `Installation problems` equals
Installations `Open problems` for the same population. Linked update review adds one entry per active,
nonlocal diagnostic UUID; the GitHub badge includes those same entries. Unlinked
update reports do not enter installation issue counts. Both scopes exclude
resolved work and are not labelled as a count of unique GitHub issues. A failed queue query is
`unavailable`, never an empty zero queue.
Needs attention actions use the operation-level diagnostic scope when a batch contains
multiple map-result rows; this does not merge those rows in installation
statistics or change their per-map historical outcomes.

A map-operation install failure without a matching device diagnostic is a
separate review task for the exact immutable `map_download_event.event_id`.
Its dismiss/reopen state is stored in the operator-only review tables and is
audited with administrator, time, transition and exact target; it never edits
map telemetry, install outcomes, coverage, or compatibility evidence. The
Dashboard dismiss action is idempotent, requires no reason, and offers Undo.
Dismissed gaps are excluded from the active queue, while a later matching
diagnostic independently removes the gap through normal reconciliation. Any
retained nonlocal diagnostic for the result is present evidence, including a
statistics-excluded one; an `OUT_OF_SCOPE_PREWRITE` diagnostic for the same
operation result (or the same operation when the map event has no result index)
is a policy block and suppresses the gap instead of creating a review task. A
statistics link for a gap carries the exact `eventId` and opens Event detail;
aggregate population KPIs remain unchanged.

Across API and UI read models, numeric zero, unknown, unavailable, stale, and
partial values are distinct. A present zero remains `0`; missing or invalid
data is `—`/`Unknown`; query failure is unavailable/stale; and partial data is
marked partial. Boolean `false` remains `No`. A metric never falls back across
units (for example operation count to event count, or provider health error to
package count).

A successful full statistics query with no matching rows reports `0 recorded
events` and zero terminal attempts; its success-rate denominator is zero, so
the rate is `—`. That empty-population state is different from a failed or
partial query, which is unavailable or partial.

Worked examples: `9` fresh successes plus `1` fresh failure is `90%`; `4`
successful acquisitions plus `1` failed acquisition is `80%`; and `3`
successful updates plus `2` failed updates is `60%`. Two selected fresh map
attempts with one reliable diagnostic link are `50%` coverage; when the second
diagnostic arrives late, coverage becomes `100%` while the denominator stays
`2`. A GitHub counter change from `100` to `103` is `+3` for that interval, and
`103` to `110` across a missing hourly check is `+7` for the retained interval,
not seven downloads assigned to the final hour. Two affected packages sharing
one broken source are `2 packages · 1 source`; a health-only error contributes
neither object count. A failed operation plus pending identity is `2` review
tasks, and linking its GitHub issue keeps the total at `2`. A measured `0`
bytes, `0 ms`, or `0` recorded problems remains zero; `0` successes plus `1`
failure is `0%`, while `0` successes plus `0` failures is `—`.

## Historical and operator data

The original event facts are immutable. Classification is derived in the
backend read model; it does not rewrite old events. `ACTIVE` and `RESOLVED`
diagnostic status controls operator workflow and attention queues, not whether
a historical completed result happened. Reopened diagnostics remain linked to
the same event and do not create a new attempt. Conflicting or insufficient
facts remain visible as unknown/diagnostic data and are excluded from rates.

The regression case for the Freizeitkarte `CZE+` package with
`INSTALL_BLOCKED_DOWNLOAD_FAILED` is an acquisition `FAILED` event and a
device installation `NOT_STARTED` result. It contributes zero fresh attempts,
zero fresh failures, and does not alter the compatibility model rate. The
backend must not synthesize an `INSTALL_FAILED` map event from that evidence.

## Privacy and limits

Statistics use only the documented compatibility and map telemetry fields.
They must never require Garmin Unit IDs, serial numbers, accounts, local paths,
manifests, raw logs, map binaries, credentials, or persistent user/watch IDs.
The contract does not guarantee complete use: telemetry is opt-out, delivery
can fail, reports may be delayed, and legacy records can have unknown fields.
