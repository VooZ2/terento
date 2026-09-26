> Behavioral requirements and release acceptance criteria:
> [Admin behavior contract](admin-behavior-contract.md). Route descriptions below
> describe implementation; known gaps are not a waiver of that contract.

# Catalog API contract

Base URL in production:

```text
https://api.terento.app
```

The map and device catalog routes are public read-only metadata. Compatibility
evidence and map-operation statistics are separate data boundaries: the former
is an explicit product-purpose sharing flow, while the latter accepts only
privacy-minimised map operation events from registered providers. Compatibility evidence is
accepted for the explicit currently enabled and reviewed provider set plus the
separate `custom` local-IMG source label. Custom
events use literal `custom` region and release labels so no local filename,
hash-derived identity, or provider claim is uploaded. Provider installation
evidence can be linked to map-operation events by a shared operation ID when
both default-on diagnostics streams are enabled; users can disable either
stream from the app's Diagnostics window. Custom events do not create a provider
map-statistics event; eligible custom fresh results can still be projected into the
private map-statistics read model without a guessed catalog package or country.
Provider controls and statistics are private
authenticated admin routes. No route serves map binaries.

## `POST /compatibility/events`

Accepts at most 16 KiB of allowlisted schema-version-1 through schema-version-4 JSON under the client’s
default-on privacy-minimised diagnostics policy. Event UUIDs are idempotent. Unknown fields, local paths, malformed
payloads, providers/sources outside the current compatibility-evidence allowlist, and
privacy-prohibited data are rejected. The compatibility evidence source
allowlist is explicit and remains separate from the provider-neutral map
catalog; a new reviewed provider must be added to that allowlist and pass the
normal review before its compatibility events are accepted. `custom` is a
fixed local-IMG source label, not a provider, and only accepts literal
`custom` region and release values. New schema-version-4 clients do not send
deletion credentials; schema versions 1–3 remain readable for backward
compatibility. The endpoint is rate limited and stores allowlisted columns in
the separate compatibility table. The original JSON body is not retained.
New clients do not send a post-install
confirmation signal; legacy `userConfirmed` fields are tolerated only for
backward compatibility with older beta clients. Upload failure never changes
the macOS installation result.

Version 2 events may include an exact `compatibilityIdentity`, `variant`,
`caseSizeMm`, privacy-safe `displayType`, and `canonicalDeviceId`, plus
optional `reconnectVerified` and `mapVisibleAfterReconnect` observations.
Older beta clients remain accepted when the newer identity fields are absent;
such model-only evidence must not be matched to a sibling exact variant.
Reconnect is never required for any compatibility status. The canonical
aggregate groups by `canonicalDeviceId` when available and uses exact
`compatibilityIdentity` only as the fallback for older uncanonicalized events.
It then uses the successful shared installation count: `TESTING` for zero successful installations on
recognized map-capable evidence, `TESTED` for 1–2, `SUPPORTED` for 3–4, and
`VERIFIED` for 5 or more. Failed reports, opt-out local installs, and duplicate
event IDs do not increase the successful count. Firmware variation, physical
device count, operator review, reconnect, and map visibility are retained only
as optional evidence dimensions and do not promote a status.

Version 3 groups all map results from one Install press under a random
`operationId`; each result is identified by `mapResultIndex` plus package/map,
provider/region and selected-component facts. The exact app release/build plus
controlled failure stage/code, write/remote-object/cleanup booleans, and a
coarse transfer progress bucket are recorded. It may also record the sanitized
raw MTP model label and one allowlisted identity-source category
(`MTP_SERIAL`, `GARMIN_UNIT_ID`, or `UNAVAILABLE`) without the identifier value.
It never accepts raw native messages, local paths, object IDs, manifests,
hashes, serials, Unit IDs, or local watch keys. Selected maps not reached after
an earlier failure use `NOT_STARTED`. Download, extraction, source-validation,
and preflight failures remain visible in private operation detail but do not
enter fresh-install attempts or compatibility rates when `writeStarted=false`.
A current missing write fact is unknown and is not guessed. Compatibility
thresholds count distinct verified per-result successes, not child component
rows; optional contours remain part of the main-map result. Legacy events remain
one operation each.

Schema version 4 keeps the structured diagnostics contract while removing the
per-event deletion token. Uploaded compatibility events are immutable through
the public API; `DELETE /compatibility/events` returns `405 Method Not Allowed`.
The authenticated `/admin` GET views project the same
persisted compatibility columns and remain schema-version agnostic: v4 uses
the existing model, variant, firmware, operation, outcome, and failure fields.
Admin workflow metadata is extended separately by migration 040 and is not
part of the public or native event contract.

`GET /health` is read-only and does not run retention. Compatibility events
older than 24 months are pruned by the catalog scheduler, not by a health
request. The production scheduler is configured for 03:00 UTC daily; with
that schedule, cleanup may lag by up to 24 hours, which is accepted behavior.
The candidate scheduler implementation documenting this behavior has not
been deployed to production.

### Optional v4 failure context: server-first acceptance

The additive server contract accepts optional top-level `failureContext` and
`originalFailureContext` only on version 4, including explicit null values.
In v4, omitted and explicitly null values both mean unavailable and normalize
to absence. Non-null objects have the same closed,
nonrecursive shape, with optional nested `protection`; the exact enums,
required fields and numeric bounds are defined in the
[shared event contract](../../../contracts/README.md#structured-installation-failure-context).
Versions 1–3 remain accepted unchanged without these fields; existing v4 clients
may omit them or send null. Null-as-absent requires no schema v5 or additional
migration; persistence uses SQL NULL, not JSONB `null`. This server-first change does not implement app emission or
comparator version 2 and does not establish deployment.

Each non-null context object requires boundary, classification source and device presence.
Only allowlisted enums, bounded integers, and the documented nullable target
booleans are accepted. Native namespace/code must occur together, with a signed
32-bit code and no boolean-to-integer coercion. Unknown nested properties and
privacy-prohibited values are rejected; allowing a structured object is not an
exemption from the existing privacy checks or the 16 KiB request limit.

Cleanup failure retains its terminal cleanup context separately from the
unchanged originating context. A successful main-map outcome does not by itself
forbid context for a failed optional component: it requires explicit
`componentKind=contours`, `optionalComponentSelected=true` and
`optionalComponentOutcome=FAILED`, with boundary checked against
`optionalComponentFailureStage`. Aggregate `cleanupSucceeded` may refer to
another component and cannot alone invalidate that context. A non-null original context
requires a non-null terminal context object with boundary `cleanup`; an absent
or null terminal context is insufficient. Component kinds must match
when both are supplied, and original protection is checked against its own
boundary. Reject either context field on versions 1–3, even when null, before
null normalization or any legacy validation early return. Intake checks consistency where the
reported fields establish it and preserves legacy requests without context.
Context does not change statistical populations, event idempotency, sharing,
retention or device-operation authority. Missing or explicitly null fields remain
unavailable in authenticated diagnostics and generated issue reports.

## `GET https://api.terento.app/admin`

Returns the authenticated operator Dashboard. The default period is the last 24
hours; `?period=7d`, `?period=30d`, and `?period=all` are also supported.

The first row contains always-visible Map downloads and Map installs trends. The
Successful, Failed, and Success rate badges use all retained history; the period
selector changes only the trend series and Activity. Needs attention covers
unresolved work across all dates. App downloads is the separate Terento `.dmg`
and `.zip` cumulative-counter trend and is omitted without usable data. Activity
is bounded and internally scrollable. Generic rows have no Maps link unless an
exact event/detail destination exists.

Map/package reconciliation requires shared operation, provider, and exact or
unambiguous package-region identity. Operation ID alone is not a unique map.
Historical acquisition failures remain activity and Maps evidence. A failure
with `write_started=false` is not projected as `INSTALL_FAILED` or a fresh
installation attempt. Existing explicit map events and eligible fallback rows
are deduplicated by logical map result.

A map install failure without a matching device diagnostic appears in Needs
attention across all dates and is keyed by the immutable event ID. Authenticated,
CSRF-protected dismiss and undo routes change only operator review state and its
audit. An exact event link opens collapsed Maps Event detail without changing
aggregate statistics. Compatibility evidence remains the source for exact-device
facts and actionable diagnostic work.

App download counter history keeps `.dmg` and `.zip` separate. The first valid
snapshot is a baseline; unchanged counters are observed zero; missing snapshots
are unknown. Counter decreases or confirmed population changes are discontinuity.
Gap and period-boundary increases are retained as uncertain intervals, and
aggregated partial buckets stay marked partial. A failed GitHub read does not
erase the last successful observation or timestamp.

Production `/admin*` is first protected by Cloudflare Access and the trusted
origin assertion. The application then requires its native admin session and
CSRF checks. A local preview that bypasses Access is not production authorization
evidence. The first administrator can be created only once through `/admin/setup`
with the environment bootstrap secret. Passwords use salted PBKDF2-SHA256;
opaque session and CSRF values are stored only as SHA-256 hashes. Cookies are
Secure, HttpOnly, SameSite=Strict. Authenticated Admin responses are no-store and
noindex.

## `GET https://api.terento.app/admin/installations`

Returns the authenticated all-time model installation evidence view. Its summary
order is Attempts, Successful, Failed, Success rate, and Open errors. `Failed`
includes resolved historical failures; `Open errors` is active actionable work.
Positive Failed values use the shared danger styling.

The page supports All, Failed, Open errors, Successful, and Identity review
filters plus sorting and search. True no-evidence omits metrics, filters, table,
and pagination. Filtered-empty preserves the active controls and clear action.
Pagination appears only for multiple pages. Known exact models group by canonical
ID; unresolved identities remain visible. Historical catalog provenance is
presentation only and changes no status or count.

## `GET https://api.terento.app/admin/diagnostics?identity=...`

Returns an authenticated, no-store/noindex diagnostic drill-down for one exact
compatibility identity. Dashboard links add the internal `canonical_device_id`
query parameter when available, so harmless formatting differences in legacy
identity labels remain in one model history; identity text remains the fallback
for records without a canonical link. Links for records without a canonical
device also add the internal `identity_scope=unresolved` parameter. That scope
prevents a pending record from being redirected to a canonical device that
happens to use the same textual identity and limits the drill-down to
uncanonicalized operations. Assigning a canonical Garmin device redirects to
that exact device history after the audited identity update. The list uses the compact columns Date, Region, Result,
Stage, Code, Issue, and State, and defaults to active diagnostic history. A
linked issue is shown as `In progress` or `Under review`, rather than `Open`. A Review action opens the
detail dialog with the separate evidence/lifecycle summary, Resolve/Reopen,
auditable identity selector, GitHub issue link/create actions, and collapsed
technical fields. Successful normal evidence remains historical evidence and
does not appear as an open problem. Identity-pending success is a separate
state from Failed. This is an additive admin-only route and does not alter any
native, public, or existing device API contract.

## `GET https://api.terento.app/admin/review/github-issues`

Returns the authenticated active GitHub issue queue. Each linked issue is
listed once per installation operation with its device, map/region, result,
workflow state, and last activity. Linking an active diagnostic automatically
sets its workflow to `IN_PROGRESS`; the detail dialog also allows
`UNDER_REVIEW`. The diagnostic remains active and the issue remains in this
queue until the read-only GitHub synchronizer observes the issue as closed;
closure then moves the diagnostic to resolved history.

The device detail history keeps the exact model/variant scope, supports All,
Successful, Failed, Open errors, and Resolved errors filters, and uses a
25/50-row presentation page. The provider detail primary health disclosure
shows the newest check; its history disclosure contains only previous checks,
so the newest row is not repeated.

## `GET https://api.terento.app/admin/campaign-links`

Returns the authenticated operator's local Campaign link builder. It is a
client-side tool: no campaign links, history, or analytics data are stored and
no campaign-link API is exposed. The builder restricts destinations to
`terento.app`, normalizes UTM values, replaces existing UTM parameters, and
keeps the canonical parameter order `utm_source`, `utm_medium`,
`utm_campaign`, `utm_content`, `utm_term`. The page uses the same private
admin session, CSRF cookie, no-store response policy, and noindex policy as
`GET https://api.terento.app/admin`.

## `GET https://api.terento.app/admin/devices`

Returns the authenticated Garmin catalog and device-evidence workspace. `Maps`,
`Install policy`, and `Evidence` are separate. Maps exposes the stored nullable
`device_model.map_capable`; NULL remains Unknown. Install policy is the derived
write decision from active/catalog capability facts. Evidence contains observed
installation history and cannot override the stored Maps fact or authorize a
write.

`GET https://api.terento.app/admin/devices.json` returns the same additive data
for Admin tooling. It is no-store/noindex and joins evidence through
`canonical_device_model_id`. It is not a public or native device contract.

The list is dense and paginated. A device link opens a detail page with catalog
facts, Maps, Install policy, Evidence, separate public-compatibility and support
metadata, collapsed Administration, and secondary Technical details. Empty
history omits unusable controls. Summary and Installation history may be side by
side at suitable desktop widths and stack on narrow layouts.

The internal payload field remains `installationAuthorization`; the visible
label is `Install policy`. Pending, Approved, and Blocked derive from the exact
catalog row's `active` and stored `map_capable` values. The native resolver still
evaluates every plausible active variant. `support_status`, observed capability,
public compatibility, and install counts never grant native write permission.

CSRF-protected `POST /admin/devices/authorization` (and legacy
`/admin/devices/support`) updates only support metadata and its audit; it cannot
change Install policy. `POST /admin/devices/public-compatibility` explicitly
publishes or withdraws an eligible exact model and is independently audited.
Neither mutation changes installation evidence or native authorization.

The primary navigation has no duplicate Review item. Dashboard Needs attention
is the queue entry point. Missing-diagnostic dismiss/undo changes only the exact
operator review state. Diagnostic resolve/reopen changes lifecycle only;
workflow state and exact-model assignment retain their existing bounded,
audited actions.

## `GET /compatibility/public/top-models.json`

Prepared for a later public TOP-models widget. The route returns 404 unless
`PUBLIC_COMPATIBILITY_STATS_ENABLED=true`. Even then, it includes only model
rows that an operator has separately marked `APPROVED` and enabled for public
statistics. Results are ordered by successful installation count and include
attempted, successful, failed, canonical model, exact identity, case size,
display type, canonical device-catalog ID, map-capability, last-evidence, and
canonical-status fields; firmware and raw event records are omitted. All
four canonical statuses may be public after review. The native macOS client
continues to use this existing route. The public website uses the additive
`/compatibility/public/models.json` projection below. The endpoint remains
default-disabled and the page shows no public evidence when the flag or
approved aggregate data is absent.

The response's `evidenceStatus` is the authoritative public status for the
exact `compatibilityIdentity`. It is one of `TESTING`, `TESTED`, `SUPPORTED`,
or `VERIFIED`; non-map devices are not represented by a compatibility status.
`canonicalModel`, `caseSizeMm`, `displayType`, `variant`, and
`canonicalDeviceId` identify the exact reviewed catalog variant. Clients must
not fall back from a sized row to a model-only or sibling-size row. The native macOS client
refreshes this endpoint after device discovery, stores only a bounded
exact-identity cache for offline presentation, and uses a neutral unavailable
UI when neither a current response nor a recent cached canonical result is
available. A transport/install registry or write-safety decision must not
change `evidenceStatus`.

The production website and native macOS client request `limit=500` before
performing exact-identity matching. Clients must not rely on the route's
smaller default result page to represent the complete reviewed catalog.

The reviewed Garmin `091e:51b8` hardware identity is associated separately
with `garmin-fenix-8-47-amoled` and may therefore match that exact public row
when MTP omits the display token. This is reviewed identity evidence, not an
inference from case size or artwork. An unreviewed 47 mm identity without
display evidence must not match either the AMOLED or Solar row, including via
the native offline cache.

## `GET /compatibility/public/models.json`

Additive evidence-first projection for the public Compatibility page. It uses
the same default-disabled flag and `APPROVED`/`public_statistics_enabled`
review gate as the existing route, but it is a separate contract so the
website does not need to join the retail device catalog. Historical evidence
rows can therefore appear even when Garmin no longer lists that model in its
current retail category. The response contains exact identity, evidence
counts, `evidenceStatus`, family/variant display metadata, and an `image`
object. `image` follows controlled Terento asset → allowlisted Garmin
`garmin-source` URL → the neutral Terento `fallback` image at
`https://terento.app/assets/generic-garmin-watch.png` (with a cache-busting
version query in emitted URLs). The fallback is
presentation-only and does not indicate a model match or compatibility.

This endpoint does not expose `supportStatus`, operator review decisions,
transport profiles, write authorization, Unit IDs, or raw event data. The
website uses only `evidenceStatus` for its compatibility badge. Existing
native/web clients are not required to call this endpoint, and
`/devices/catalog.json` remains unchanged.

## `GET /health`

Returns HTTP 200 when the service can reach PostgreSQL:

```json
{"status":"ok"}
```

Returns HTTP 503 and `{"status":"error"}` when the database is unavailable.
Responses use `Cache-Control: no-store`.

## `GET /maps/catalog.json`

Returns an additive provider-neutral catalog. `schemaVersion: 2` identifies the
new provider/package/artifact fields, while `catalogVersion: 1`, the legacy map
fields, and `sourceURL` remain for existing macOS clients. The response
contains all validated packages known to enabled or paused prebuilt adapters;
catalog membership is distinct from acquisition availability. The collector
keeps original provider download URLs and never downloads or proxies map
packages through Terento.

```json
{
  "schemaVersion": 2,
  "catalogVersion": 1,
  "updatedAt": "2026-08-21T06:27:14Z",
  "providers": [
    {
      "id": "freizeitkarte",
      "name": "Freizeitkarte",
      "adapterId": "freizeitkarte",
      "status": "ACTIVE",
      "health": "HEALTHY",
      "website": "https://www.freizeitkarte-osm.de/garmin/en/mitteleuropa.html",
      "attribution": "Map data © OpenStreetMap contributors; produced map © FZK project",
      "licenseURL": "https://www.freizeitkarte-osm.de/garmin/en/imprint.html",
      "licenseInformation": "...",
      "maps": [
        {
          "id": "freizeitkarte-deu",
          "region": "DEU",
          "name": "Germany",
          "country": "Germany",
          "version": {"year": 2026, "month": 5},
          "downloadSizeBytes": 361187697,
          "installSizeBytes": 429793280,
          "sizeBytes": 361187697,
          "sourceURL": "https://download.freizeitkarte-osm.de/garmin/latest/DEU+_en_gmapsupp.img.zip",
          "releaseDate": "2026-05-03",
          "identifier": "DEU+",
          "release": "2026-05",
          "artifacts": [
            {
              "id": "freizeitkarte-deu-main",
              "kind": "main",
              "sourceUrl": "https://download.freizeitkarte-osm.de/garmin/latest/DEU+_en_gmapsupp.img.zip",
              "sizeBytes": 429793280,
              "downloadSizeBytes": 361187697,
              "required": true,
              "validationState": "validated"
            }
          ]
        }
      ]
    }
  ]
}
```

The example shows one map entry for brevity; the current snapshot contains 63
Freizeitkarte Garmin map entries. The provider catalog may change after that
date.

The client-compatible package list contains only records with a normalized
version and a known download size. `sizeBytes` remains the backwards-compatible
package-size field. New clients must use `downloadSizeBytes` for
archive/network sizing and `installSizeBytes` for final Garmin storage sizing.
`installSizeBytes` may be `null`; `null` is unknown and must not be treated as
zero or as the download size. The macOS storage gate blocks until it has a
measured final IMG size. The client still validates the extracted IMG before
installation even when the catalog provides this metadata.
`sourceURL` is always an original provider URL. The API never fetches that
archive for the client and never streams its bytes.

`version` is the comparable year/month value used by clients for update
ordering. When a provider publishes a native release label such as FZK's
`2/2026`, the API derives this comparable value from the provider source date
(`2026-05` for a `2026-05-03` source date) and preserves the original label in
`release` and `releaseMetadata.versionLabel`. The historical `2000-01`
serializer sentinel is never emitted.

The collector uses the release page as the provider-wide version signal. For
each official regional page it selects the English Garmin package when
available, otherwise the first published language variant. It validates the
archive byte length with `HEAD` when available and reads only bounded ZIP tail
and central-directory `Range` sections from the original provider URL to find
the selected `.img` entry's uncompressed size. It never downloads the full
archive to the VPS. If Range is unavailable or the ZIP is malformed, the
download size may remain known while `installSizeBytes` remains unknown; a
diagnostic is stored and the previous known-good value is preserved. A full
collection failure does not clear the previous known-good catalog.

Successful responses include:

```text
Cache-Control: public, max-age=300, stale-while-revalidate=86400
ETag: "<sha256>"
Last-Modified: <HTTP date>
```

Clients should send `If-None-Match` or `If-Modified-Since` and accept HTTP 304.
The `catalogVersion` value changes only for an intentional contract change;
adding optional metadata fields does not require a version bump.

For the new artifact contract, package `sizeBytes` and
`downloadSizeBytes` describe the provider archive/network payload. Artifact
`sizeBytes` is the final extracted Garmin IMG size when measured and is
`null` when that measurement is unavailable;
`downloadSizeBytes` is the archive size. This preserves the native client's
storage gate while making both meanings explicit. Artifact `sourceUrl` is
always an original provider URL. `checksumSha256` is optional until a
provider-published checksum is available. `main` is required and `contours`
is optional; artifact validation and package availability are independent.
Providers are registered only through known server-side adapters. A provider's
catalog visibility, lifecycle status, source health, and acquisition
availability remain separate; publishing metadata never activates a provider
or grants a device write path.

## `GET /admin/providers.json`

Returns the authenticated provider registry as a private, no-store/noindex
JSON response. Each row contains `id`, `name`, `adapterId`, lifecycle
`status` (`ACTIVE`, `PAUSED`, `RETIRED`), health (`HEALTHY`, `DEGRADED`,
`DOWN`, `UNKNOWN`), official website, license and attribution metadata,
catalog-sync/check timestamps, package counts, broken-package count, and the
broken URL count, and the last health error. Additive `affectedPackageCount`
and `problematicSourceCount` are the current problem units used by the admin
UI; the health state/error is separate. The endpoint never returns
provider binaries or executable adapter configuration.

## `GET /admin/providers` and `GET /admin/providers/{id}`

These authenticated, no-store/noindex HTML pages provide the operator views
for the provider registry and each registered provider. The list shows provider name and
secondary ID, lifecycle/health state, package count, current problems and catalog sync,
and current Problems (affected packages · problematic sources), with a compact
total/active/healthy/package/problem summary. The
detail page shows metadata, license/attribution, provider-level original
source links, and progressive-disclosure sections for download sources,
regions/packages, health details/history, collection history, and retained
provider history. Large source and package lists have client-side search,
broken-only filters, 25/50-row pagination, and no zero-item package-source
disclosure. An empty collection uses a compact `Collection · No runs yet`
state. It also provides `Check now`, `Collect
catalog`, `Pause`/`Activate`, and an overflow `Retire` control. A request
without a valid admin session redirects to `/admin/login`; the page never
serves map binaries.

`GET /admin/providers/{id}.json` and `GET /admin/providers/{id}/audit` are
private JSON projections for operator tooling and carry the same session gate.
Provider detail also returns an `activationGate` projection. Its
`canActivate` value is false until the latest health check is `HEALTHY`, a
successful catalog collection is recorded, the stored current package set
matches that collection, all current packages are `AVAILABLE`, and every
required artifact is present, validated, and free of broken links. A provider
may add a stricter completeness requirement in its reviewed adapter policy;
such a requirement is provider-specific evidence, not a universal package
count.

## `GET /admin/providers/{id}/health`

Returns the latest provider health result and bounded health history. The
health record separates website, catalog, redirect, download, MIME, magic
bytes, ZIP, IMG, and last-update statuses. Checks use bounded `HEAD`/`GET`/`Range`
requests and do not persist an archive on the server.

## `POST /admin/providers/{id}/check`

Runs one authenticated CSRF-protected health check and records an audit row.
The request body is an empty JSON object. The response includes the health
check ID and the component result. Health checks are operational metadata, not
device compatibility evidence.

## `GET /admin/providers/{id}/runs`

Returns the append-only catalog collection runs for one known provider,
including status, timestamps, package/artifact counts, and bounded error
details.

## `POST /admin/providers/{id}/state`

Changes only the lifecycle state of a known prebuilt adapter. The JSON body is
`{"status":"ACTIVE"}`, `{"status":"PAUSED"}`, or
`{"status":"RETIRED"}`, with an optional bounded `reason`. The action requires
the existing admin session and CSRF token and writes an `admin_audit_log`
record with the admin user, provider, old status, new status, timestamp, and
reason. Changing to `ACTIVE` is rejected with HTTP `409` and
`provider_activation_blocked` when `activationGate.canActivate` is false. The
HTML `Activate` control is disabled in the same state. It cannot upload parser
code, execute arbitrary provider logic, or activate an unknown provider.

## `POST /admin/providers/{id}/collect`

Runs one known server-side adapter, stores metadata-only package/artifact
records, records a `catalog_collection_run`, and returns counts. The body is
an empty JSON object. Provider map binaries remain direct provider → user's
Mac.

## `POST /admin/providers/{id}/retire`

Equivalent to a CSRF-protected state change to `RETIRED`; it accepts an empty
JSON body or an optional bounded `reason`, and writes an audit record.
Retiring a provider does not delete its historical metadata.

## `POST /map-events`

Accepts at most 8 KiB of schema-version-1 JSON and is rate limited per source
address. This is deliberately separate from `/compatibility/events` and does
not accept compatibility, device, manifest, path, serial, Unit ID, raw log, or
raw error fields. The allowlisted fields are `id`, `operationId`, `timestamp`,
`providerId`, `releaseLabel`, optional `mapId`/`region`, `eventType`, `outcome`,
and optional `appBuild`. `releaseLabel` must be a strict SemVer app identity;
the exact `-local` suffix classifies the row server-side as local test data.
Event types are `DOWNLOAD_STARTED`, `DOWNLOAD_SUCCEEDED`,
`DOWNLOAD_FAILED`, `INSTALL_SUCCEEDED`, `INSTALL_FAILED`,
`MAP_UPDATE_SUCCEEDED`, and `MAP_UPDATE_FAILED`; event IDs are
UUIDs and are idempotent. The server stores only the normalized columns in
`map_download_event`; it does not retain the raw JSON body. A successful
insert returns `201`, a duplicate returns `200`, and both return the
`operationId`. Local rows are excluded from production map statistics and can
be removed only by an authenticated, CSRF-protected admin action at
`/admin/test-data`; the purge deletes both telemetry streams in one transaction.

`MAP_UPDATE_*` events represent a safe replacement of an already installed
Terento-owned provider map. They are counted separately from first
installations; they do not increase installation totals, country coverage, or
map popularity counts. Admin Dashboard renders both update outcomes as one
dedicated Map update chart series, while Map statistics exposes their success
and failure breakdown and supports filtering by either event type.

This endpoint receives map-usage diagnostics while the independent map-usage
diagnostics switch is enabled in `Terento → Diagnostics`; it must not be used
as unrelated background telemetry. It contains no raw device identifier and
does not alter compatibility evidence.

## `GET /admin/map-statistics.json`

Returns private aggregate map-operation rows with `event_count`, a source-aware
statistical `operation_count`, first/last occurrence, provider, map, region, event type,
outcome, and the optional `component_kind` (`main` or `contours`). Where the existing registry has names, admin rows also include
`provider_name` and `map_package_name` for human-readable popularity tables;
`region_display_name` is an additive display-only region label and
`region_identity` is an additive cross-provider grouping key derived from
existing canonical region/country metadata. The technical IDs remain available.
Supported query filters are `provider`, `map`, `region`,
`dateFrom`, `dateTo`, `eventType`, and `outcome`. `provider`, `map`, `region`,
and dates define the KPI, coverage, and popularity population. `eventType` and
`outcome` affect only the Event detail projection; pagination is also detail
only. The response is no-store/noindex and
does not expose individual event payloads or device identifiers. Each response
row is an event group, not a complete download/install total: a single map
operation can produce started, completed, and failed event groups. For download
event groups, `operation_count` counts distinct `acquisition_id` values (or the
legacy event identity when that field is absent), so main-map and contours
acquisitions remain separate. For explicit install/update groups it counts
distinct retained result events. Admin KPI totals use that source-aware count
for the relevant terminal event type, while compatibility evidence remains a
separate data source.
The response also includes an additive `linkage` summary. It matches one
map result from each stream only when their UUID `operationId`, provider and
region are equal and the match is unambiguous; `mapResultIndex` keeps sibling
results separate. An operation ID alone, or provider + region alone when
multiple map results are possible, is not enough to infer a match. A missing or
ambiguous watch event is coverage data, not an inferred installation outcome.
This field is private admin data and does not change either stored event stream.
Compatibility fallback rows include only verified successes or failures after
writing started. An explicit `write_started = false` result remains diagnostic
detail, not a failed fresh-install row. An existing explicit
`map_download_event` `INSTALL_FAILED` is never removed or duplicated.
The linkage summary contains `mapOperationCount`, `mapSessionCount`,
`linkedOperationCount`, `mapInstallationCount`, `linkedInstallationCount`,
`mapOnlyInstallationCount`, `linkedWriteStartedInstallCount`,
`linkedSuccessfulInstallCount`, `linkedFailedInstallCount`,
`linkedPrewriteFailureCount`, `linkedUnclassifiedInstallCount`, and
`linkageRate`, plus the explicit aliases
`freshMapAttemptCount`, `freshMapLinkedDiagnosticCount`,
`freshMapMissingDiagnosticCount`, and `freshMapDiagnosticCoverageRate`.
The historical operation/session compatibility fields and `linkageRate` stay
at operation-key scope (`mapSessionCount` is the distinct non-null operation
UUID count). The explicit `freshMap*` fields are per-map-result fields and are
the only linkage fields used for diagnostic coverage. They must not be
interchanged merely because both are returned in the same object.
`linkedPrewriteFailureCount` is the subset that failed before a device write;
it remains visible for traceability but is not folded into the existing
write-started compatibility success-rate aggregate.

The response's `rows` remain the complete population aggregate used for KPI,
coverage, and popularity calculations. The additive `summary` object contains
those KPI values and is never recomputed from detail rows. The additive
`allTimeSummary` object contains the matching all-time badge values. The
additive `trend`, `bucket`, and `timeZone` fields carry the selected-period
download/install series and its display boundary. Period selection therefore
changes the series while the all-time badges remain all-time. The additive
`detailRows` projection is bounded for the Event detail disclosure.
`detailPage` and `detailPageSize` (`25` or `50`) select its page, and
`detailTotal` reports the number of detail-filtered aggregate groups. An empty
detail projection does not turn a non-empty population into an overall no-data
state. These pagination parameters are private admin presentation controls.

The aggregate response carries the complete population summary used by the
Admin map-statistics view. Visible labels, KPI grouping, popularity row layout,
provider-table columns, and chart presentation are defined in
[`admin-behavior-contract.md`](admin-behavior-contract.md); statistical
populations and formulas are defined in
[`contracts/STATISTICS_CONTRACT.md`](../../../contracts/STATISTICS_CONTRACT.md).
In the current HTML runtime, Provider comparison groups Downloads, Installs,
and Updates under Successful, Failed, and Rate subcolumns, with Provider and
Last install outside those groups. The API populations and payload are
unchanged.
Popular-map grouping still uses only the eligible successful fresh main-map
population, and the response searches the complete eligible set before any
All maps pagination. Provider activity is an independent projection and does
not infer installs from downloads or downloads from installs.

Linkage is per independent map result. A reliable shared `operationId` and
`mapResultIndex`, with unambiguous provider/region identity, is required;
session-level `min(provider)`, time, model, or region matching is not used. A
linked diagnostic is an observation regardless of success/failure state, while
a missing diagnostic is an observation gap and never a synthesized failure.
Needs attention actions may operate on all diagnostic rows in the selected
operation; the missing-diagnostic dismiss action instead targets one exact map
event ID. Neither administrative action scope merges per-map statistics.

## `GET /admin/map-statistics`

Returns the authenticated, no-store/noindex Maps page for the aggregate read
model. It supports Last 24 hours, Last 7 days, Last 30 days, and All time, plus
provider, map, region, event-type, outcome, and exact `eventId` detail filters.

The visible primary order is summary, world map with Top countries, Provider
comparison, Maps by provider, Map downloads trend, Map installs trend, and
Updates. These analytics remain visible. Diagnostic linkage coverage is retained
in the private JSON contract but is not rendered as an Admin block. Raw Event
detail remains collapsed and secondary.

Provider, map, region, and date filters define the summary population. Event
type, outcome, exact event, and detail pagination affect Event detail only.
Missing/unknown values use an explicit neutral state or em dash. Unauthenticated
requests redirect to `/admin/login`. A pre-write diagnostic remains outside the
fresh-install denominator; an explicit `DOWNLOAD_FAILED` remains acquisition
activity and is not converted into an installation failure.

## `GET /devices/catalog.json`

Returns catalog version 2 for the separate Garmin device catalog. Records are discovered from the
official smartwatch category and do not mean that Terento has tested or
supports the model. The retail source is not a complete historical Garmin
database; inactive historical records can remain in the response.

```json
{
  "catalogVersion": 2,
  "updatedAt": "2026-08-21T06:27:14Z",
  "legal": {
    "manufacturerNotice": true,
    "text": "Garmin and fēnix are trademarks of Garmin Ltd. Terento is an independent open-source project and is not affiliated with Garmin."
  },
  "devices": [
    {
      "id": "garmin-fenix-8-47-amoled",
      "manufacturer": "Garmin",
      "family": "fenix",
      "familyName": "fēnix",
      "model": "fēnix 8",
      "canonicalModel": "fenix 8",
      "variant": "47 mm, AMOLED",
      "caseSizeMm": 47,
      "displayType": "AMOLED",
      "partNumber": "010-02904-10",
      "productURL": "https://www.garmin.com/en-US/p/1228429/",
      "active": true,
      "asset": {
        "status": "AVAILABLE",
        "url": "https://api.terento.app/assets/devices/garmin/fenix-8-47-amoled.webp",
        "version": 1,
        "scope": "MODEL_SIZE",
        "source": {
          "type": "OFFICIAL_PRODUCT_MEDIA",
          "brand": "Garmin",
          "attributionRequired": true
        }
      },
      "sourceAsset": {
        "url": "https://res.garmin.com/en/products/010-02904-10/g/cf-lg.jpg",
        "scope": "MODEL",
        "version": 1,
        "attribution": "Garmin official product media",
        "source": {
          "type": "OFFICIAL_PRODUCT_MEDIA",
          "brand": "Garmin",
          "attributionRequired": true
        }
      }
    }
  ]
}
```

`caseSizeMm`, `displayType`, and `partNumber` may be `null` when the official
source does not provide the field. `asset` is always present in version 2 and
is either `{ "status": "MISSING" }` or an `AVAILABLE` asset. An optional
`sourceAsset` contains only allowlisted official Garmin media metadata and is
not a Terento-hosted binary. Review and
deprecated states are never exposed as public URLs. An available asset has a
scope of `FAMILY`, `MODEL`, `MODEL_SIZE`, `EXACT_VARIANT`, or `GENERIC`, a
valid `source` declaration, a version, and an optional checksum under the same API domain:
`https://api.terento.app/assets/devices/`. A discovered device remains catalog
metadata only and never becomes a compatibility or support claim.

### Device Assets and Attribution

Device images are used only for device identification and a better display of
the connected hardware. They do not indicate endorsement, partnership,
certification, or official support. Asset availability never changes the
separate compatibility evidence status (`TESTING`, `TESTED`, `SUPPORTED`, or
`VERIFIED`).

The `asset.source` object uses exactly one of these source types:

- `OFFICIAL_PRODUCT_MEDIA` — official Garmin product media used only for
  identification; `brand` is `Garmin` and `attributionRequired` is `true`.
- `TERENTO_RENDER` — a Terento-created visual representation; `brand` is
  `Terento` and `attributionRequired` is `false`.
- `GENERIC_FALLBACK` — the neutral Terento fallback illustration; `brand` is
  `Terento` and `attributionRequired` is `false`.

The top-level `legal` object is reusable global metadata. For Garmin product
media, clients must show or make available the following notice:

> Garmin and fēnix are trademarks of Garmin Ltd.
> Terento is an independent open-source project and is not affiliated with Garmin.

The macOS app consumes the controlled `asset` first. If that is missing, it
may consume `sourceAsset.url`, or derive the documented Garmin product-media
URL from a validated catalog `partNumber`, only after validating the HTTPS
`res.garmin.com` origin and Garmin attribution metadata. The image is fetched
directly by the Mac and cached locally; the API does not proxy or host it. A
missing or invalid asset/source falls back to the generic Terento watch
illustration.

The device endpoint supports the same public cache policy as the map endpoint:
`ETag`, `Last-Modified`, `Cache-Control: public, max-age=300,
stale-while-revalidate=86400`, and conditional GET responses with HTTP 304.

The device catalog is metadata only. It has no route for connected-device
identifiers or ownership decisions.

## `GET /devices/installation-policy.json`

Returns the small, public-read policy projection consumed before any native
write. Schema version 3 contains exact internal catalog model/variant records,
the nullable `mapCapable` value, and derived `installationAuthorization`
(`APPROVED`, `BLOCKED`, or `PENDING`) plus `scope` (`IN_SCOPE`,
`OUT_OF_SCOPE`, or `UNKNOWN`). `active=true` and `mapCapable=true` are the only
catalog conditions that produce `APPROVED`; `support_status` is intentionally
absent. It contains no compatibility counts, evidence status, Unit IDs,
operation IDs, or map data. A model absent from this response is pending/unknown
and a failed or invalid response is unavailable; both must fail closed.

`baseModel` is derived from the catalog `model` label, whose identity is shared
by SKU variants; `canonicalModel` may contain Solar, Sapphire or no-Wi-Fi
details. The app first matches a normalized exact base model, then narrows
candidates only with reliable variant facts. A conflicting variant attribute
is treated as unknown and does not filter candidates: conflicting variant
evidence broadens the candidate set. It does not by itself deny authorization.
Authorization is determined from the Maps capability of all remaining
possible candidates. All active candidates with Maps=Yes permit installation;
all Maps=No block it; mixed or NULL capability, an unresolved base-model
identity, or no candidates produces `PENDING`. A base-model conflict is not
treated as a variant conflict and remains pending. This endpoint is not the
public Compatibility surface and successful-install counts never grant
authorization. A stale `catalogDeviceID` is only a hint and cannot narrow the
candidate set by itself. The
read-only `tools/installation-policy-audit.sql` query reports the live Garmin
row counts and expected row-level decisions; it does not mutate the database.

The local policy implementation sends `Cache-Control: no-store` and returns
fresh HTTP 200 JSON even when a conditional request is supplied; it does not
reuse the public device-catalog 304/stale-cache behavior. The native client
also requests a fresh response and treats invalid payloads as unavailable.
Safe Update fetches policy at operation start and again immediately before
its first remote mutation, and aborts if the connected identity changes.
Cleanup after writing begins requires no further policy request.
This route returned HTTP 404 in the 2026-09-22 live audit, so the local
contract must not be read as a deployed capability. The backend must be
deployed and the live route, schema, projection and cache headers checked
before distributing a dependent app. See the
[tracked authorization rule](../../../contracts/README.md).

## `GET /assets/devices/<asset>.webp`

Serves only validated WebP runtime assets from the same `api.terento.app`
origin. Assets use a long-lived immutable cache policy and an SHA-256 ETag.
Review storage, source images, arbitrary files, and traversal paths are not
served.

## `POST /internal/operations/observations`

Accepts a schema-version 1 operational observation from reviewed Terento
GitHub workflows. Requests require `Authorization: Bearer` with the separately
configured `OPERATIONS_INGEST_SECRET`, use JSON, and are limited to 16 KiB.
Kinds, components, statuses, GitHub run URLs, commit hashes, timestamps,
release/build labels, summaries, and scalar detail values are allowlisted and
validated. `observationId` makes retries idempotent. In addition to existing
workflow observations, `kind: "INDEXNOW"` and `component: "indexnow"` accept
only the bounded submission result contract: publication ID, result code,
last real submission and last HTTP 200 timestamps, attempted URL count,
separate HTTP 200/202 counts, an optional HTTP status, pending count and
oldest-pending timestamp, a safe error code/summary, and at most ten validated
`https://terento.app/` URL preview entries. Keys, key locations, authorization
values, raw requests/responses, exception text, and private paths are rejected
by the allowlist. HTTP 200/201 from this route means only that the report was
stored; it is not an IndexNow HTTP 200.

`observationId` is also the retry identity when a workflow must resend the
same report. The existing observation table is the durable store; no second
IndexNow queue is created. The route does not execute tests, accept raw logs,
or expose a public read API; retained results are shown only on authenticated
`/admin/system-health`.

## `GET /internal/operations/report-context`

Returns bounded provider catalog status for the weekly health workflow.
Requests require the same independent `OPERATIONS_INGEST_SECRET` bearer token.
The response contains only provider ID/name, normalized health, latest release,
last successful collection, last detected release change, and an actionable
reason. It contains no credentials, user/device identifiers, raw logs, or map
binaries and is returned with `Cache-Control: no-store`.

## Optional contour metadata and admin projections

OpenTopoMap source-validated contours are enabled by the public rollout policy.
Live collection counts vary and are not an API invariant. Main-map availability
must not depend on an optional contour download.

The collector independently inspects optional official contour sources using
bounded HTTP ranges (8 MiB total, 4 MiB per request), exact root IMG path,
Garmin/provider/region header identity, stable strong ETag and Last-Modified.
Unreachable or invalid optional sources are omitted without failing main.
Shared Canada sources are inspected once and attached to both regions.
Independent HTTP dates and metadata-derived source proofs are retained; revision
is not a payload checksum. Legacy beta.9 URL/size fields always describe main,
including when database rows arrive contours first. No map binaries are stored,
mirrored or served. No native Install/Remove code is changed. No application
release, website announcement or issue closure is included.

Optional artifact `version` is its independent HTTP source year/month;
`sourceProof.revision` is metadata identity, not a payload checksum. PostgreSQL
integration validates source-proof round trips and legacy main-field projections.

Provider-wide availability probes sample active required main artifacts only.
Optional contour failure cannot mark the whole provider unavailable; contour
validation remains attached to the independently collected optional artifact.

Artifact details are disclosed under the wide region/package column, with
readable header widths and top-aligned cells; the count column remains numeric.

Map accessibility labels use standard country display names rather than
normalized alias tokens, preserving spaces and accented country names.


### Coverage interaction

Map dragging suppresses native browser selection, including WebKit selection;
Reset clears stale selection and region emphasis. Top 5 remains a stable summary;
All maps has search and ten-row pagination, while Regions remains the full
canonical-region grouping. Download sources use
artifact metadata to show Main map / Contours labels and separate source counts
(shared contour URLs count once).

Map resource review: Leaflet's official GeoJSON choropleth example
(https://leafletjs.com/examples/choropleth/) supplies country hover, fitBounds,
legend and navigation primitives. OpenFreeMap's MapLibre integration
(https://openfreemap.org/quick_start/) offers a modern vector basemap; it adds
external tile requests and WebGL. OpenTopoMap tiles are a possible optional
terrain background, subject to current service terms and visible attribution
(https://wiki.opentopomap.org/about). Leaflet with the local OpenStreetMap-derived
country data is the current choice. No new mapping dependency or external tile
service is added by this selection/interaction fix.

### Leaflet coverage component

Admin Map statistics uses self-hosted Leaflet 1.9.4 (BSD-2-Clause), loaded only
on that page. Exact allowlisted `/admin/map-assets/` JS/CSS routes require the
existing session and CSRF cookie checks. Assets are privately cached; script
nonces and same-origin stylesheet policy preserve the admin CSP.

`static/map/coverage-map-v1.js` exposes `TerentoCoverageMap(container, options)`:
trusted bundled SVG, country names, callbacks, `update([{code,count,name}])`,
`highlight(code, focus)`, `zoom(action)` and `destroy()`. The renderer performs
no fetches and knows no admin routes, cookies, telemetry IDs or provider query
schema. Admin aggregates its existing data and owns provider tooltip details.
A future public page can reuse the renderer with separately approved aggregate
data and its own asset delivery; no public statistics route is introduced now.
OpenStreetMap-derived boundaries use Leaflet CRS.Simple/SVGOverlay without
downloading map tiles. The generated snapshot keeps the Ukraine relation above
the overlapping Russia relation for the Crimea area, matching the selected
product presentation. CSS tokens have neutral fallbacks. JS/CSS footprint is approximately
162 KB raw / 46 KB gzip before the small adapter; the existing SVG is reused.

### Diagnostic report boundary

The compatibility event schema is unchanged. Administrator GitHub exports label
the reported transport category as potentially inferred and direct the user to
the app's Report issue for the extended local trace. The API does not receive,
store or reconstruct that trace. Legacy event values remain unchanged.

### BBBike v4 projection

`/maps/catalog-v4.json` adds the active `bbbike` provider. Registration migrations initially pause a
provider; activation is a separately reviewed operation.
`/maps/catalog.json` remains exactly the reviewed FZK/OTM provider set and v3
remains exactly FZK/OTM/MapRando. The additive catalog body retains schemaVersion2.
Provider registration is not a public compatibility claim or activation.

BBBike packages expose `mapType` (`bbbike-latin1` or `ontrail-latin1`) and
`geographicRegionId`. `region` and `canonicalRegionId` are the existing native
lifecycle identity slot and include source path plus type; for example
`EUROPE-LITHUANIA-BBBIKE-LATIN1`. `providerRegionId` is `europe/lithuania`, and
both variants share geographic identity `LITHUANIA`. The package name is the
reviewed geographic display name. Two types remain one statistics provider.

Main artifacts include bounded original-source `sourceProof`: source URL,
strong ETag, Last-Modified, exact ZIP/IMG lengths, payload path, README source
region/style/generated timestamp, payload MD5, a source revision, and the
header-identity validation marker. MD5 is the provider's payload-integrity
value, not a Terento cryptographic trust assertion. Native acquisition must
validate the whole downloaded payload independently. Calendar versions use
README day; same-day republishes do not invent a new version ordering.

Unavailable BBBike entries may have unknown ZIP bytes represented as0, unknown
install size, unavailable artifact validation and no source proof. They are
catalog metadata only and cannot be acquired. Ready-region pages for Cambodia, Jordan and Luxembourg point to the provider's
separate example namespace. Exactly those six URLs (three regions × two types)
are reviewed aliases: source README/IMG identity, complete country input-PBF
bounds and ready-region polygon bounds were checked for both styles. No other
example URLs are accepted. Other types and the Russia subtree are outside
this adapter's catalog scope.

Both telemetry streams accept `bbbike`; the existing strict `-local` label
classification, deduplication, privacy schema and local purge boundary remain.
Map statistics resolve the stored package to its geographic identity and expose
`map_type`; diagnostics fallback without a variant identity does not guess a
package or type. Candidate package IDs must be seeded in the receiving DB before
owner testing, because unknown map IDs cannot link to package geography.

### Acquisition lifecycle extension

Schema1 additionally accepts paired optional `acquisitionId` (random UUID) and
`componentKind` (`main` or `contours`) for download events. Earlier client
requests remain valid. `DOWNLOAD_PROCESSING`, `DOWNLOAD_CANCELLED`, and `DOWNLOAD_INTERRUPTED`
require this pair and outcome `UNKNOWN`; new successes/failures require the
corresponding outcome. These are metadata only, never filenames or device IDs.
A repeated event/phase is idempotent and one acquisition admits one terminal.
Recent activity groups the new acquisition phases with component and history;
non-terminal observations are explicitly labelled `Outcome not received`.
Cancellation/interruption are excluded from download failure/success ratios.
The API and migration supporting this contract must be deployed before a client
that emits these fields is distributed.

### Admin information hierarchy (local UI implementation)

Diagnostic detail presents the saved model assignment separately from automatic
source checks. An administrator assignment does not turn incomplete evidence
into a match; a conflicting check for the assigned candidate remains visible.
The compact outcome precedes expandable identity evidence, source corrections,
issue management and full technical details. Other candidates retain their
complete check tables behind individual disclosures. Source correction forms
show the selected field's original reported value; corrections do not reassign
installations. Original identifiers, source revisions and review history remain
available. No identity policy, API mutation semantics or compatibility counts
change as part of this presentation work.

Provider details distinguish AVAILABLE package counts, non-retired catalog
entries and broken artifacts. The latest recorded check and its coverage are
separate from package issues. Collection and check results precede source URLs
and release distributions. Download history uses a compact wrapping timeline;
full timestamps remain in markup and accessible labels, with time-only visible
labels when all phases occur on the same day in the selected timezone.

### Model source review

`GET /admin/device-identification` is the authenticated, no-store Model
source review tool under Tools. Its primary workflow is `Source reported` →
`Match to` → `Other models using this code` → `Confirm match` → `Technical
details`. Raw codes, mapping/catalog IDs, source revision, policy internals,
missing-source inventory, reasons, and history remain secondary. Existing
CSRF-protected `POST /admin/devices/identity-mapping` remains the mutation route.
Saved installation assignments and compatibility approval semantics are
unchanged.

### Per-collection map updates (local, not deployed)

Provider collection history includes Updates, the sum of new package IDs and
existing packages with changed release or source_updated_at. One package counts
once, independent of its artifacts; removed packages are not updates. The
initial catalog import counts all packages as new. Counts are captured during
snapshot persistence in the same transaction, tied to a RUNNING run for the
same provider. Scheduled/manual collectors and BBBike candidate import supply
that run ID. Health checks alone do not populate these counts.

Migration 054 adds nullable new_package_count and updated_package_count to
catalog_collection_run. Historical unknowns stay NULL. The admin table shows
counts only for successful runs with both values recorded; older, incomplete
and failed runs show —, never an inferred zero from release_change_detected.

Compatibility intake delivery logs record stored, duplicate and validation-rejected
reports with strictly formatted random event/operation UUIDs and rejection reason
codes. They do not record raw request payloads, device identity fields or native
logs. This allows delivery correlation without synthesizing a device diagnostic
from a map-statistics event. Historical rejected payloads cannot be reconstructed
from these new log entries.

### Operation-owned installation failure reports (local follow-up)

The compatibility-event failure-code allowlist additionally accepts
`INSTALL_FAILED_UNKNOWN`. This represents a failed boundary for which the app
has no proven domain-specific failure code; it must not be relabelled as an
assumed disconnect. Existing schema versions/fields and the other failure codes
remain unchanged. Release this additive acceptance before publishing a client
that can emit it.

App reports retain the operation ID shared with map statistics. Model assignment
continues to require existing identity evidence. An unassigned historical map
statistic cannot provide a missing watch identity. Final FAILED reports enter
compatibility accounting only when writing actually started (or the documented
legacy fallback applies); current pre-write results remain diagnostic history and
are outside completed attempts and the Dashboard fresh-install fallback.
NOT_STARTED remains outside completed attempts; an explicit download-only map
event is still not converted into an additional install failure.

`test_operation_diagnostic_delivery.py` checks intake, idempotency, actual insert
and identity assessment (SQLite adaptation), and review/diagnostic/model/photo
and assignment/GitHub control rendering. It does not create issues or constitute
production PostgreSQL/browser validation.

### Build31 operation diagnostic acceptance

Compatibility-event intake additionally accepts INSTALL_FAILED_UNKNOWN without
adding fields or changing schema versions. The app uses it only when an observed
failed boundary has no proven domain-specific cause. All prior accepted codes
remain valid. Apply this acceptance before publishing build31; follow the
[app–API release contract](../../../contracts/APP_API_RELEASE_CONTRACT.md).

Operation-owned reports retain initial identity/map context and operationId even
when the screen closes. Existing received-versus-reviewed identity, assignment,
local-test partition and counting rules remain unchanged. This prospective fix
does not reconstruct historical missing reports.
