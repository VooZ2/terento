# Terento statistics contract

Status: active
Semantics version: 2
Effective date: 2026-09-17

This document is the canonical meaning of Terento's retained statistics. It
describes read-model classification, not a promise that every installation or
download is reported. The statistics are privacy-minimised, aggregate evidence
and may be incomplete because users can disable either telemetry stream,
reports can be lost, and old releases emitted less information.

## Populations

Terento keeps four related but separate populations:

- **Acquisitions** are provider-download attempts. Only terminal
  `DOWNLOAD_SUCCEEDED` and `DOWNLOAD_FAILED` events count. `STARTED`,
  `PROCESSING`, `CANCELLED`, `INTERRUPTED`, missing, and unknown terminal
  states are excluded. A custom `.img` import is not an external provider
  acquisition.
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
  addon/component warning or diagnostic fact.
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
facts are excluded from the fresh denominator.

For every read model:

```text
F_success  = verified main-map fresh results
F_failed   = confirmed started fresh failures
F_completed = F_success + F_failed
F_success_rate = F_success / F_completed, when F_completed > 0
```

When `F_completed = 0`, the UI displays an em dash rather than zero percent.
The identities are stable across views: two selected provider maps produce two
fresh results; a provider map plus contours produces one; a provider map plus a
custom `.img` produces two; a fresh install plus an update produces one fresh
result and one update result; two updates produce no fresh result.

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

When both streams contain a trustworthy shared operation identity, linkage also
requires an unambiguous provider/region and map/package match. An operation ID
alone is not enough; provider + region alone is not enough when sibling maps or
custom images are possible. A missing or delayed stream preserves the received
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
are excluded from both sides. This metric is not support status, public
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
arrives late can change linkage for that map result, but never changes the
selected map-event denominator.

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
compatibility statistics, open errors, and installation review tasks. Raw
diagnostic and map-event facts remain retained and visible in acquisition
activity. `STARTED`, `PROCESSING`, `CANCELLED`, `INTERRUPTED`, stale and
missing terminal outcomes do not enter the acquisition failure denominator.

## Charts, cards, and activity

The Dashboard installation trend is an installation-outcome chart. It must never
include download or pre-install acquisition events.

Fresh-install outcomes and map-update outcomes are separate statistical
populations. Updates must never change fresh-install counts or success rates.

Its fresh series are provider fresh successes, custom fresh successes, and
confirmed fresh-install failures (including custom). The update series is
separate. Fresh attempt totals are `F_success + F_failed`; download,
pre-install, device-check, not-started, cancelled, and unknown events are not
chart series.

The map-statistics read model keeps fresh-install outcomes, acquisition
outcomes, and update outcomes separate. Period views use the selected period;
all-time views say so explicitly. Period boundaries use the server/read-model
timezone supplied by the request, and timestamps remain immutable source facts.
The 24-hour trend is hourly, seven-day trends are daily, and 30-day trends are
weekly. All-time trends use the observed span: up to 14 days is daily, 15–60
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

The GitHub read model uses these meanings:

For the 24-hour trend read model, `hour_start` is the canonical hourly floor of
an observation. The exact `observed_at` remains available as factual interval
metadata. This changes display bucketing only: deltas, baselines, gaps,
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
change remains an unknown interval and is rendered with a visible `Unknown`
label and accessible description; it is never represented as a dashed
zero-only value.

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

Recent map activity remains mixed and may show provider downloads, fresh
install outcomes, optional-component warnings, and updates. Map history keeps
the installed map and version facts, including unknown or unmapped values.
Fresh popularity and country coverage use only successful main-map fresh
installs. Custom fresh results may be included in common fresh totals but do
not acquire a guessed provider, region, country, or map package. Unknown and
unmapped results remain visible as unknown/unmapped rather than being silently
discarded or assigned by provider + region heuristics.

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
Failure-diagnostic review and GitHub handling for one operation are alternative
states of one task; linking an issue moves that task between categories and
does not add a second task. Identity review is an independent task, and
publication review is counted per exact model. Queue lists and badges use the
same operation-level grouping and exclude resolved work; operation work is not
labelled as a count of unique GitHub issues. A failed queue query is
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
diagnostic independently removes the gap through normal reconciliation. A
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
