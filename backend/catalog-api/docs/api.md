# Catalog API contract

Base URL in production:

```text
https://api.terento.app
```

The map and device catalog routes are public read-only metadata. Compatibility
evidence and map-operation statistics are separate data boundaries: the former
is an explicit product-purpose sharing flow, while the latter accepts only
privacy-minimised map operation events. Compatibility evidence is
accepted for the explicit reviewed provider allowlist (`freizeitkarte` and
`opentopomap`) so the two streams can be linked by a shared operation ID when
both opt-ins are enabled. Provider controls and statistics are private
authenticated admin routes. No route serves map binaries.

## `POST /compatibility/events`

Accepts at most 16 KiB of allowlisted schema-version-1, schema-version-2, or schema-version-3 JSON after client
opt-in. Event UUIDs are idempotent. Unknown fields, local paths, malformed
payloads, providers outside the current compatibility-evidence allowlist, and
privacy-prohibited data are rejected. The compatibility evidence provider
allowlist is explicit and remains separate from the provider-neutral map
catalog; a new provider must be added to that allowlist and pass the normal
review before its compatibility events are accepted. A random per-event deletion token is required; older beta payloads
without one are rejected rather than retained without a self-service deletion
credential. The endpoint is rate limited and stores allowlisted columns in the
separate compatibility table. The original JSON body is not retained; only
the approved fields and a SHA-256 hash of the event deletion token are stored.
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
It then uses the successful opt-in installation count: `TESTING` for zero successful installations on
recognized map-capable evidence, `TESTED` for 1–2, `SUPPORTED` for 3–4, and
`VERIFIED` for 5 or more. Failed reports, opt-out local installs, and duplicate
event IDs do not increase the successful count. Firmware variation, physical
device count, operator review, reconnect, and map visibility are retained only
as optional evidence dimensions and do not promote a status.

Version 3 groups all map results from one Install press under a random
`operationId` and records the exact app release/build plus controlled failure
stage/code, write/remote-object/cleanup booleans, and a coarse transfer
progress bucket. It may also record the sanitized raw MTP model label and one
allowlisted identity-source category (`MTP_SERIAL`, `GARMIN_UNIT_ID`, or
`UNAVAILABLE`) without the identifier value. It never accepts raw native messages, local paths, object
IDs, manifests, hashes, serials, Unit IDs, or local watch keys. Selected maps
not reached after an earlier failure use `NOT_STARTED`. Download, extraction,
source-validation, and preflight failures remain visible in the private
operation detail but do not enter the main Installations or compatibility-rate
aggregate when `writeStarted=false`. Compatibility thresholds count successful
distinct write-started operations, not child map rows; a multi-map operation
succeeds only when all of its selected map results verify. Legacy events remain
one operation each.

## `DELETE /compatibility/events`

Accepts the event UUID and its 64-character deletion token. The service hashes
the supplied token and deletes the matching event. A missing event and an
incorrect token both return the same not-found response. This prevents the
event UUID alone from authorizing deletion. The route is rate limited and the
client keeps deletion tokens locally; the server stores only their hashes.

Compatibility events older than 24 months are pruned from the active database
by the service health cycle.

## `GET https://api.terento.app/admin`

Returns the authenticated operator Overview. The default period is the last 24
hours; `?period=7d`, `?period=30d`, and `?period=all` are also supported. Its
primary operational domain is the existing `map_download_event` table: Map
installs, Map install success, Failed map installs, recent map activity, and
the installs-over-time chart use distinct map operation IDs. Historical
`DOWNLOAD_FAILED` and `INSTALL_FAILED` map events remain in activity and
statistics, but are not placed in `Needs attention` because map events do not
carry an unresolved/actionable lifecycle state. Compatibility evidence remains a secondary, explicitly
labelled block with its own variants, write-started attempts, evidence success,
open errors, and normalized failure reasons. Common reason spelling variants
are collapsed into stable canonical groups such as `source_validation`; only
events without a classifiable category, stage, or code remain `unknown`. If the selected domain has no
data, event-derived values use an em dash rather than zero. No new client
telemetry, public statistics, or map-event payload is created by this page.

The first administrator can
be created only once through `/admin/setup` with the environment-provided
bootstrap secret. Passwords use salted PBKDF2-SHA256;
opaque sessions and CSRF values are stored only as SHA-256 hashes. Cookies are
Secure, HttpOnly, SameSite=Strict, and scoped to `/admin`. Login/setup attempts
are rate limited. Pages include no-store, noindex and restrictive CSP headers.

## `GET https://api.terento.app/admin/installations`

Returns the authenticated compatibility/installations view. It keeps the
existing five KPI cards, historical-failure distinction, exact model/variant
table, search, compatibility-status filter, sort, and model drill-down. The
quick filters `All`, `Failed`, `Open errors`, and `Successful` are
presentation-only filters over the existing aggregate rows. The page labels
the compatibility counters `Write-started attempts` and `Successful`, plus the
explicitly scoped `Evidence success` percentage.
The canonical compatibility view itself uses active, write-started operations
and excludes pre-write failures; the rendered page also retains historical
failures for operator review. Open errors remain a separate unresolved
diagnostic state. The route is the target of the earlier
`/internal/compatibility/` redirect.

The first screen stops at the KPI summary, filters, and one-row-per-exact-
model/variant table. Resolved and legacy diagnostics remain available in model
history and may contribute to its historical-failure presentation, but are not
part of the canonical compatibility view. Identity-pending evidence is shown
separately. Selecting a model or its error count opens the private per-model
diagnostics view below. Device history uses the existing event groups and
provides 25/50-row presentation pagination. Failed rows use the existing
normalized error category or failure stage as a concise reason; raw diagnostic
codes remain behind the per-operation Details action.

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
Stage, Code, Issue, and State, and defaults to Open. A Review action opens the
detail dialog with the separate evidence/lifecycle summary, Resolve/Reopen,
auditable identity selector, GitHub issue link/create actions, and collapsed
technical fields. Successful normal evidence remains historical evidence and
does not appear as an open problem. Identity-pending success is a separate
state from Failed. This is an additive admin-only route and does not alter any
native, public, or existing device API contract.

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

Returns the authenticated Garmin device observability page. The page is
limited to Garmin catalog records and combines catalog metadata, map
capability, separate installation authorization, exact-ID installation
aggregates, approved cached assets or allowlisted Garmin `sourceAsset`
thumbnails, and latest successful sync metadata. Map-capable Yes/No uses a
stored `device_model.map_capable` value when present; otherwise the page
classifies the canonical model with the same Map Manager prefix list as the
native macOS client. Unknown remains only for models outside that list. The
page keeps the dense list paginated in the browser and opens a detail dialog
for technical fields, including which image origin was used
(controlled Terento asset vs official Garmin product media).

`GET https://api.terento.app/admin/devices.json` returns the same additive
data as JSON for admin tooling. The endpoint uses the existing admin session,
is no-store/noindex, and joins installation events only through
`canonical_device_model_id`. It is not part of the native or public device
catalog API contracts.

Device-card installation statistics preserve successful operation history but
exclude every failure received before migration
`025_device_card_failure_epoch.sql`. From that migration's production
application time onward, each distinct failed operation contributes one card
Attempt and one Failed result even when the device write did not start. This
epoch rule is private to the device card and does not change the Installations
dashboard or public compatibility aggregate.

The page labels the operator field `Installation authorization` and shows a
separate, classifier-derived `Compatibility status`. The visible values are
Pending, Approved, and Blocked; the existing internal enum remains
`NOT_EVALUATED`, `SUPPORTED`, or `UNSUPPORTED`. CSRF-protected
`POST /admin/devices/authorization` (with the legacy `/admin/devices/support`
alias retained) updates only `device_model.support_status` and records an
audit entry. It cannot change evidence events, operation-level install counts,
compatibility status, or any native device write authorization.

The detail dialog also exposes the independent `Public compatibility` review.
An exact catalog record becomes eligible only after it has recognized,
map-capable compatibility evidence. CSRF-protected
`POST /admin/devices/public-compatibility` accepts an explicit `PUBLISH` or
`UNPUBLISH` action. Publishing sets the exact-identity review to `APPROVED`
and enables public statistics; withdrawing returns it to `PENDING` and
disables public statistics. Every change is audited. This action does not
change evidence events, calculated status, installation counts, installation
authorization, or any existing public/native/device API field.

The shared authenticated admin navigation shows `Needs review` only when an
actionable queue is non-empty. Its count is split into distinct active failed
installation operations, unresolved-identity operations, and exact eligible
models awaiting first public publication. The popover links failures and
identity work to Installation evidence and publication work to Devices.
Resolved diagnostics, `NOT_IDENTIFIABLE` identities, rejected publication
reviews, and already-published models are excluded. The summary is private,
no-store, and does not add fields to any public or native API response.

`POST /admin/diagnostics/resolve` and `/admin/diagnostics/reopen` change only
the retained diagnostic lifecycle, while `POST /admin/diagnostics/identity`
assigns or leaves an exact canonical Garmin record and writes an identity audit
entry. `POST /admin/diagnostics/issue` links, changes, or removes a GitHub issue
reference without changing evidence outcome or lifecycle. The create-issue
flow opens a sanitized prefilled GitHub form; it does not create an issue for
every error or auto-close an issue when a diagnostic is resolved. Neither
action deletes evidence or changes the original install outcome. Admin counts
are grouped by distinct install operation, not raw per-map evidence rows.
When ingestion validates or resolves a canonical Garmin model, the server also
marks the internal identity-review state resolved without requiring a new client
field. Migration 022 audits and aligns older canonical rows; it does not change
installation outcomes, diagnostic lifecycle, timestamps, or compatibility counts.

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
broken URL count, and the last health error. The endpoint never returns
provider binaries or executable adapter configuration.

## `GET /admin/providers` and `GET /admin/providers/{id}`

These authenticated, no-store/noindex HTML pages provide the operator views
for the provider registry and each registered provider. The list shows provider name and
secondary ID, lifecycle/health state, package count, catalog sync, last check,
and issues, with a compact total/active/healthy/package/issue summary. The
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
`providerId`, optional `mapId`/`region`, `eventType`, `outcome`, and optional
`appBuild`. Event types are `DOWNLOAD_STARTED`, `DOWNLOAD_SUCCEEDED`,
`DOWNLOAD_FAILED`, `INSTALL_SUCCEEDED`, and `INSTALL_FAILED`; event IDs are
UUIDs and are idempotent. The server stores only the normalized columns in
`map_download_event`; it does not retain the raw JSON body. A successful
insert returns `201`, a duplicate returns `200`, and both return the
`operationId`.

This endpoint is intended for explicit map-operation statistics consent and
must not be used as unrelated background telemetry. It contains no raw device
identifier and does not alter compatibility evidence.

## `GET /admin/map-statistics.json`

Returns private aggregate map-operation rows with `event_count`, distinct
`operation_count`, first/last occurrence, provider, map, region, event type,
and outcome. Where the existing registry has names, admin rows also include
`provider_name` and `map_package_name` for human-readable popularity tables;
`region_display_name` is an additive display-only region label and
`region_identity` is an additive cross-provider grouping key derived from
existing canonical region/country metadata. The technical IDs remain available.
Supported query filters are `provider`, `map`, `region`,
`dateFrom`, `dateTo`, and `eventType`. The response is no-store/noindex and
does not expose individual event payloads or device identifiers. Each response
row is an event group, not a complete download/install total: a single map
operation can produce started, completed, and failed event groups. Admin KPI
totals count the distinct operations for the relevant completed/failed event
type, while compatibility evidence remains a separate data source.
The response also includes an additive `linkage` summary. It matches one
operation from each stream only when their UUID `operationId` values are equal;
the server first aggregates each stream to one row per operation, so a
multi-map install is never counted once per child map. `linkedInstallationCount`
and `mapOnlyInstallationCount` describe map operations that emitted an install
event, while `linkedSuccessfulInstallCount` and `linkedFailedInstallCount`
use the linked watch evidence outcome. A missing watch event is coverage data,
not an inferred installation failure. This field is private admin data and
does not recalculate or merge the existing compatibility and map-operation
aggregates.
The linkage summary contains `mapOperationCount`, `linkedOperationCount`,
`mapInstallationCount`, `linkedInstallationCount`,
`mapOnlyInstallationCount`, `linkedWriteStartedInstallCount`,
`linkedSuccessfulInstallCount`, `linkedFailedInstallCount`,
`linkedPrewriteFailureCount`, and `linkageRate`.
`linkedPrewriteFailureCount` is the subset that failed before a device write;
it remains visible for traceability but is not folded into the existing
write-started compatibility success-rate aggregate.

The response's `rows` remain the complete filtered aggregate used for KPI and
popularity calculations. The additive `detailRows` projection is bounded for
the Event detail disclosure. `detailPage` and `detailPageSize` (`25` or `50`)
select its page, and `detailTotal` reports the number of filtered aggregate
groups. This keeps the event-detail DOM bounded without changing aggregate
totals. These pagination parameters are private admin presentation controls.

## `GET /admin/map-statistics`

Authenticated, no-store/noindex HTML dashboard for the same aggregate read
model. It supports Last 24 hours, Last 7 days, Last 30 days, and All time
ranges plus provider, map, region, and event-type filters. It displays map
operation totals, map-package download/install totals, success rates, Top 5
maps with a single-table View all disclosure, collapsed Regions, per-provider
popularity, provider health, and broken provider package/link counts. When a
provider filter is selected, the health, issue, and per-provider popularity
summaries are scoped to that provider. The UI labels the distinction between
distinct map operations and map-package records because one operation may
contain multiple packages. Overview and Map statistics therefore do not imply
identical totals. The Regions disclosure groups equivalent provider labels by
`region_identity`, sums their package-operation counts, and keeps the newest
activity timestamp; Popular maps remains grouped by provider package.
Compatibility Installations remain an all-time evidence
view. Missing or unknown values use an explicit neutral state or em dash,
rather than silently presented zeros. Unauthenticated requests redirect to
`/admin/login`. Linkage is possible only when the app's map-statistics and
compatibility-evidence choices are both enabled for the same installation
operation.

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
identifiers and it does not authorize MTP operations, map installation, or
ownership decisions. Those decisions remain local to the macOS client and its
compatibility/manifest layers.

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
validated. `observationId` makes retries idempotent. The route does not execute
tests, accept raw logs, or expose a public read API; retained results are shown
only on authenticated `/admin/system-health`.
