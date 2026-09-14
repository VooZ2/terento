# Terento metadata service

The overview uses a compact mobile SVG with the same complete time series and
three time-axis labels; desktop keeps its detailed chart. Clip IDs are unique
between variants. Identity review uses a searchable native select with exact
canonical IDs rather than datalist suggestions. Editing the search clears the
selection, and typing immediately shows matching model buttons below the search
field (including accent-insensitive fenix matches). The native select remains
available as a fallback. Assignment requires an explicit model choice and a
reason, and conflicts require a separate audited source correction. Other
identity actions disable the picker.

GitHub report actions share inline-flex alignment, zero margins and stretched
row heights for both the link and button; copy feedback occupies its own row.
Admin filter actions align with the labelled controls' bottom edge. Mobile
filter values use regular-weight 16px Inter and retain 44px touch targets;
the device sort label stacks above its select. Coverage maps initially show
the complete world with a small inset at 100%. Reset returns to that fit;
resizing an untouched overview refits it while preserving manual navigation.
All zoom percentages use the current full-world fit as their baseline. The existing equirectangular SVG stays
north-up, without rotation or perspective. Data updates, including empty or changed
country sets, preserve manual pan and zoom rather than auto-fitting coverage.

This service is a metadata-only source for the Terento macOS catalog client.
It stores map-provider metadata and a separate Garmin smartwatch device
catalog. It does not download, host, proxy, mirror, cache, repackage, or serve
provider map binaries or Garmin product images.

The catalog is provider-neutral and has no fixed provider count. Each enabled
provider must be represented by a reviewed server-side adapter and pass its own
source, licensing, metadata, validation, and activation gates. A separate
Garmin collector indexes official smartwatch-category metadata; it is a device
catalog, not a compatibility registry. Compatibility evidence and map-operation
statistics use separate schemas and endpoints; neither accepts Unit IDs,
serial numbers, manifests, accounts, private logs, or map binaries.

## Local development

Admin presentation checks must inspect the rendered page, including populated
and empty map statistics. Each component must have a unique DOM ID: duplicated
targets can leave a second table or map empty while the first updates normally.
System-health disclosures use the shared UI typography and retain padded,
keyboard-accessible summary rows in both collapsed and expanded states. Filter
clearing uses the page-specific clear event once per action.

The September 9 post-audit contract keeps persistent labels above filters
(including expanded map search), sentence-case health badges, and at least
40 px desktop / 44 px mobile map controls. Wide evidence tables scroll inside
their container instead of splitting headings. Empty time ranges and filtered
searches explain how to recover. Map statistics count packages; compatibility
statistics count watch-installation attempts that reached transfer. Success
rates exclude in-progress operations. Provider health has one summary, with
per-provider status retained as row context. Display-name cleanup must not
change stored identities or evidence.

Python 3.12 or 3.13 is required. A PostgreSQL database is required for migrations and
the API; parser and HTTP contract tests use fakes and do not require a live
database.

```sh
cd backend/catalog-api
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
export DATABASE_URL='postgresql://terento_catalog:password@localhost:5432/terento_catalog'
export ADMIN_BOOTSTRAP_SECRET='use-a-long-random-one-time-secret'
export PUBLIC_COMPATIBILITY_STATS_ENABLED='false'
terento-catalog-migrate
terento-catalog-collect
terento-catalog-backfill-sizes
terento-catalog-api
```

The API listens on `http://127.0.0.1:8000` by default when `CATALOG_HOST` is
set to `127.0.0.1`. The production Compose file binds the service only to the
private Docker network and lets Traefik provide HTTPS.

Run the offline tests from the repository root after installing the test extra:

```sh
python -m pip install -e 'backend/catalog-api[test]'
Tests/run-backend-tests.sh
```

The backend regression suite includes generated-admin JavaScript checks and
therefore requires Node.js. Set `TERENTO_NODE_BIN` when Node.js is not on
`PATH`.

The shared [public schemas and fixtures](../../contracts/README.md) document
current map/device projections and event bodies. Tests use jsonschema only in
the optional test environment; the production container keeps its existing
runtime dependencies.

## Endpoints

- `GET /health` checks database reachability and returns `{"status":"ok"}`.
- `POST /internal/operations/observations` accepts only bounded CI or
  deployment metadata authenticated with the independent
  `OPERATIONS_INGEST_SECRET`. It does not accept raw logs or execute tests.
- `GET /internal/operations/report-context` exposes bounded provider catalog
  freshness and release-change metadata to the weekly workflow under the same
  independent bearer secret. It is not a public catalog endpoint.
- `GET /maps/catalog.json` returns an additive provider-neutral `schemaVersion: 2`
  projection while retaining catalog version 1 fields for existing macOS
  clients. The response includes `ETag`, `Last-Modified`, and cache headers and
  supports conditional GETs.
- `GET /devices/catalog.json` returns catalog version 2 for discovered Garmin
  smartwatch models, including `MISSING` or `AVAILABLE` asset metadata. It
  includes reusable legal metadata and validated `asset.source` attribution
  metadata. It uses the same cache validators and never includes a
  compatibility status.
- `GET /assets/devices/<name>.webp` serves validated runtime assets from the
  same API domain.
- `GET /admin/providers`, `GET /admin/providers/<id>`, and
  `GET /admin/map-statistics` serve authenticated, no-store/noindex provider
  and map-statistics admin pages. Unauthenticated requests redirect to
  `/admin/login`.
- `GET /admin/providers.json`, `GET /admin/providers/<id>.json`,
  `GET /admin/providers/<id>/health`, `GET /admin/providers/<id>/runs`, and
  `GET /admin/providers/<id>/audit` expose the corresponding authenticated,
  no-store provider registry, detail, health, collection-run, and audit
  metadata.
- CSRF-protected `POST /admin/providers/<id>/check`, `/state`, `/collect`, and
  `/retire` operate only on known server-side adapters; they cannot upload
  parser or executable provider code.
- `POST /map-events` accepts a separate rate-limited, idempotent,
  privacy-minimised map-operation event contract. `GET
  /admin/map-statistics.json` exposes its private aggregates and never returns
  raw events or device identifiers. Raw map events are pruned after 24 months.
- `POST /compatibility/events` accepts validated, rate-limited, idempotent
  privacy-minimised install events under the default-on diagnostics
  policy. It stores only allowlisted columns and never stores the submitted JSON
  body. Exact model variants are retained separately; reconnect observations are
  optional and never gate compatibility status.
- Uploaded compatibility events are immutable through the public API;
  `DELETE /compatibility/events` returns `405 Method Not Allowed`. Events are
  also pruned automatically after 24 months by the service health cycle.
- `GET https://api.terento.app/admin` serves the authenticated, noindex
  aggregate operator dashboard from the same API container as the catalog
  and account settings. The first account requires `ADMIN_BOOTSTRAP_SECRET`;
  later credentials are PBKDF2-hashed in PostgreSQL.
- `GET https://api.terento.app/admin/system-health` combines the existing
  provider/catalog state with scheduler, GitHub quality-gate, deployment,
  commit, release, and build observations. Missing evidence is `Unknown`.
- `GET https://api.terento.app/admin/campaign-links` serves the authenticated,
  client-side campaign link builder. It shares the `/admin` session gate and
  stores no campaign links or history.
- `GET /compatibility/public/top-models.json` is a prepared, default-disabled
  aggregate API. It returns only individually reviewed and approved models
  after `PUBLIC_COMPATIBILITY_STATS_ENABLED=true`, with the canonical
  `TESTING`, `TESTED`, `SUPPORTED`, or `VERIFIED` status, successful count, and
  last evidence date; it never returns raw events.

The public Compatibility page is the single public list for these statuses.
The shared thresholds are 0 successful installations for `TESTING`, 1–2 for
`TESTED`, 3–4 for `SUPPORTED`, and 5 or more for `VERIFIED`, always for the
exact model and variant. The API must not introduce a second threshold or
promote a family-level status.

Production API and admin updates are rolled out only when the catalog backend
or its deployment workflow changes; application releases and unrelated site
changes do not restart this service. They are rolled out by
`.github/workflows/deploy-catalog-api.yml`. The workflow builds the API image
from the checked-in source, runs the forward migration command against the
existing private database, replaces only the API and scheduler containers,
removes services from the known stale Compose project without deleting its
volumes, and asserts that exactly one API, scheduler, and healthy database are
running. It verifies the image release label, internal API-to-database health,
the public catalog/device endpoints, the website's API reference, the
authenticated admin gate at `api.terento.app`, and the immutable compatibility
event contract. It keeps the previous API image available for rollback and
does not change the PostgreSQL or asset volumes.

The catalog includes a map only after a collector has a normalized version and
a known download size. A missing size is retained in the database but omitted
from the public package list; the collector never invents a size. The explicit
`downloadSizeBytes` field is the archive/network size. The explicit
`installSizeBytes` field is the final uncompressed Garmin IMG size and may be
unknown. Unknown install size is never treated as zero or as the archive size.

## Collector behavior

The collector reads the official Freizeitkarte release page and seven official
Garmin regional pages: Northern, Eastern, South-Eastern, Southern, Western and
Middle Europe, plus the other-countries page. It selects one package per map,
preferring the English variant and falling back to the first published language
variant. The collector includes every downloadable official Freizeitkarte
Garmin package. The current bundled snapshot contains 63 map packages.

It uses the underlying OSM data date when the provider uses a release number
such as `2/2026`; it does not incorrectly treat that release number as a month.
It uses `HEAD` when available and bounded HTTP `Range` requests for the ZIP
tail, ZIP64 metadata when needed, and central directory. It reads the selected
final `.img` entry's uncompressed size without downloading the full archive to
the VPS. A Range/ZIP failure records a diagnostic and leaves the install size
unknown while preserving any previous known-good value.

After applying migrations, an operator can measure existing map versions with:

```sh
terento-catalog-backfill-sizes
```

Use `terento-catalog-backfill-sizes --dry-run` to inspect the provider without
writing PostgreSQL. The command is idempotent and never downloads a complete
map archive.

The production scheduler checks both release-supported provider adapters every
day at 03:00 UTC (`COLLECTOR_SCHEDULE_UTC=03:00`). Freizeitkarte and
OpenTopoMap run independently, so one provider failure is retained without
preventing the other snapshot from updating. The check reads provider metadata
and bounded archive metadata only; it does not download or store map payloads.
The Garmin retail device catalog keeps its weekly Monday collection cadence.

Scheduled catalog collection remains a separate process. The authenticated
admin `/collect` action may run one known adapter on demand and records a
collection run; health checks perform only bounded source probes. Neither path
downloads, stores, proxies, mirrors, or serves a provider map binary.

The scheduler also reads the public `VooZ2/terento` GitHub Releases API at
startup and once per UTC hour. It follows all release pages and aggregates only
`.dmg` and `.zip` asset download counts. Migration 042 stores one cumulative
hourly snapshot; the authenticated Overview renders the last 24 hourly deltas
and all-time totals for each extension. GitHub failures leave the previous
snapshot intact, and no GitHub token, release metadata, or binary is stored.

The reviewed OpenTopoMap adapter derives stable package identity from the
official `otm-<region>.zip` filename and reads each country row's generated-at
timestamp. It accepts all current official Garmin region shapes, excludes
Basecamp archives, and relates the shared Canada contours archive to both
Canada main packages. This provider-specific behavior is an example of the
reviewed adapter boundary; another provider must supply its own identity,
source, artifact, and activation rules. Deploying an adapter never activates a
provider automatically.

Provider health is an availability summary. A provider can be `HEALTHY` when
its website and catalog are reachable even before package downloads have been
collected; untested artifact fields and missing freshness metadata remain
`UNKNOWN` individually. A checked but unreachable artifact makes the provider
`DOWN`, while stale known metadata makes it `DEGRADED`.

## Garmin device collector

The collector reads the official [Garmin smartwatch category](https://www.garmin.com/en-US/c/wearables-smartwatches/) through the official
category JSON used by that page. It runs as a scheduled job, not in an API
request. Product pages may be read for text metadata such as a representative
part number. Product-image binaries are never fetched.

The collector canonicalizes family/model names, preserves display diacritics,
extracts explicit case sizes and display variants, and collapses cosmetic SKU
differences. It keeps historical records and only marks a model inactive after
three consecutive successful full collections fail to observe it. A partial
collection does not advance that absence counter.

The catalog does not claim that a discovered device is tested or supported.
The validated fēnix 8 USB identity is stored separately as narrow hardware
evidence and is not generalized to other models.

Device assets are optional. Only an explicitly available asset record with a
supported scope and a URL under `https://api.terento.app/assets/devices/` can
be returned by the API. Missing, pending-review, deprecated, non-controlled,
or Garmin-hosted assets are exposed as `{"status":"MISSING"}`. The
collector does not mirror or approve Garmin images automatically. The device
catalog remains separate from compatibility and never contains USB or support
claims.

The controlled operator workflow is:

```sh
terento-catalog-asset prepare --device-model-id garmin-fenix-8-47-amoled \
  --scope EXACT_VARIANT --storage-key devices/garmin/fenix-8-47-amoled.webp \
  --source /path/to/normalized.webp \
  --source-type OFFICIAL_PRODUCT_MEDIA --attribution-required
terento-catalog-asset approve --device-model-id garmin-fenix-8-47-amoled \
  --scope EXACT_VARIANT --storage-key devices/garmin/fenix-8-47-amoled.webp \
  --version 1 --source-type OFFICIAL_PRODUCT_MEDIA --attribution-required
```

Preparation is private review storage. Only the explicit approval step moves
the validated WebP into the public API asset tree.

The daily scheduler runs the reviewed Freizeitkarte and OpenTopoMap adapters
as isolated map phases. On Monday it then runs the separate Garmin device
collection. A provider or Garmin collection failure is logged and retained
without clearing any previous known-good catalog.

### Build 11 diagnostics storage correction

Migration 033 drops only the legacy deletion-token NOT NULL constraint. Schema
v4 events have no token; legacy hashes and all retained events are preserved.
Public event APIs remain immutable and retries retain the same event ID.
`/health` checks the installed migration set, the nullable token column, and
read-only projections of both diagnostic tables with a local statement timeout.
Missing or incompatible storage returns 503 without creating a test event.

### Admin issue synchronization and attention

The API process now runs a bounded GitHub issue-state worker (migration 034).
After normal migration-before-start deployment, closed explicitly linked
`VooZ2/terento` issues resolve ACTIVE diagnostics, normally within 15 minutes.
Ten oldest due issues are checked per cycle; rate limits or a larger backlog can
delay completion. System health reports errors and overdue checks. No GitHub token
or webhook is required. This is one-way closure synchronization; relink/remove a
closed reference before investigating a manually reopened new problem. See [API operations](docs/api.md) for review actions and synchronization rules.

Overview attention is independent of the statistics date filter. Visible admin
pages check every minute and offer Refresh when data changes, protecting unsaved
form edits.

At phone widths (up to 700 px), admin navigation collapses into Menu with a review
shortcut, Overview attention precedes statistics, and the existing tables become
labelled records. Search remains visible; secondary device/installation filters
and the full device sorter are under Filters and sorting. Primary controls and
form typography are sized for touch. Diagnostic dialogs keep their close header
visible during content scrolling. These presentation changes reuse existing
endpoints and permissions.

Desktop admin tables fit their cards and wrap long values. Provider source
details show complete URLs; campaign output wraps. Installation history uses
page scrolling and diagnostic dialogs keep their close header visible.

### Admin installation counting

Migration 038 and the current statistics projections count individual verified
map results. Migration ordering and repeatability are tested against PostgreSQL.

Admin attempts count retained map results, not batch/session IDs: a custom IMG
plus OTM session contributes two attempts and two successes when both verify.
The installation overview, identity table, watch counters and chart use this
unit. Resolved failures stay in all-time attempt/failure totals; unstarted
siblings do not become fabricated attempts. Immutable event IDs provide replay
idempotency. Diagnostic review actions remain grouped by the original session.

Overview reconciles map events against compatibility results by session,
provider and region. One catalog event cannot suppress a custom result or a
different region. Map statistics remains catalog-only. Existing retained mixed
sessions recalculate on read; no production event rewrite or backfill is needed.
The public API, watch cards and Installations use compatibility_model_statistics
as the authoritative full-history source; the 500-row diagnostics display limit
cannot truncate totals. A custom + catalog batch contributes two successes when
both verify, even before other selected results arrive. Failed/unverified results
never advance status. Thresholds remain 0 TESTING, 1–2 TESTED, 3–4 SUPPORTED,
5+ VERIFIED. Local telemetry stays excluded, resolved failures stay in historical
counts, and existing exact-model administrator publication approval is preserved.
Native telemetry contracts, provider-only Map statistics and review actions are
unchanged. These counts represent map installations, not unique users or watches.

### Admin custom IMG chart series

Custom imports appear in the installation chart and history through compatibility
results, never provider map telemetry. Charts count individual map outcomes;
local-test rows remain excluded. Segments retain accessible labels and per-type
hover details. Historical batch-counting descriptions no longer define this API.

### Diagnostic presentation cleanup

The current diagnostic dialog remains the supported admin presentation. Unused
legacy renderers and their exclusive CSS have been removed; regression tests
exercise the current page for technical details, linked issues, resolved
outcomes, multiple map results and reopen actions. API routes, evidence,
authentication, storage and lifecycle behavior are unchanged.

### MapRando provider

MapRando is the third registered adapter and is **ACTIVE**.
The scheduler and provider admin use the same metadata collection, last-success,
health, status, and per-provider failure isolation as the existing adapters.
This working-tree implementation has not been deployed or hardware-validated.

`/maps/catalog.json` preserves the Freizeitkarte/OpenTopoMap projection for
already-distributed native clients, which reject an unknown provider.
`/maps/catalog-v3.json` is additive and retains `schemaVersion: 2`; it includes
MapRando with a daily `version.day`, full `release` and release metadata. The
old endpoint remains limited to Freizeitkarte/OpenTopoMap for older clients;
the beta.11 app reads the v3 projection.
Neither endpoint changes existing provider versions or contour publication policy.

Source evidence: the [official MapRando page](https://ravenfeld.gitlab.io/open-garmin-map/)
links to the [original directory](https://ravenfeld.fr/MapRando/) and documents
`MapRando_<region>_YYYY_MM_DD.img` and direct installation. Collection walks every
immediate region directory, skips BaseCamp-only content, and takes its latest
dated direct IMG. There is no membership allowlist. Identity collisions,
ambiguous latest files and malformed calendar dates fail the snapshot.
Only bounded HTML and a 512-byte HTTP range per IMG are read; binaries are never
stored, mirrored or proxied. HTTP range inspection rejects a changed final host.

IMG validation checks the unencrypted DSKIMG/GARMIN header and joins its two
fixed description fields before matching the full MapRando region and calendar
date to the filename. Accent folding is confined to MapRando identity. A
truncated or mismatched description retains the package as `UNAVAILABLE`, with
an unavailable artifact, rather than making an unsafe match. Native acquisition
still validates the entire downloaded file. Original source sizes are both
download and installation sizes. No provider checksum is invented.

A complete metadata-only inspection on 2026-09-10 found **160** direct IMG
packages: **158** matching headers and **2 unavailable**. Haiti/Dominican
Republic has a truncated fixed description; New Zealand's filename date is
2026-09-02 but the header says 01.09.2026. These remain visible but blocked.
`France_Courbes_IGN` is a standalone alternative package, never an OTM-style
optional overlay. Geographic metadata derives from the reviewed provider
`country.txt` extract paths and explicit directory country/subregion names in
`maprando_geography.py`; it does not constrain future catalog membership.
Unmapped future packages retain empty country codes and a subregion shape.
Russia and Crimea identities remain explicit in the adapter's policy mapper.
Geography is projected for MapRando at serialization without changing the
existing database schema or either existing provider's output; the existing
package `country` stores an ISO code for single-country admin aggregation.

The source page provides a download/install path; this is not a grant to
redistribute source code, rendering assets, elevation data or map binaries.
Attribution is retained and no such assets are bundled. The API exposes the
provider as ACTIVE for the beta.11 catalog while compatibility claims remain
model-specific and evidence-based.

Migration `037_maprando_compatibility_evidence.sql` adds MapRando to the
privacy-safe compatibility evidence provider constraint. Migration
`039_activate_maprando_beta11.sql` makes the provider ACTIVE and registers its
original source links. Neither migration grants a general device-compatibility
claim. Existing map-event validation already accepts registered provider IDs.
Admin filters, operation links and health support MapRando;
raw IMG health uses header/title validation and marks ZIP inspection inapplicable.
A complete successful MapRando snapshot retires only its own disappeared package
metadata, preserving installed manifests and all existing-provider records.

Validation uses the existing backend unit/contract suite with narrow additions
for daily dates, strict source identity, standalone variants, geographic
projection and byte-identical legacy endpoint output. PostgreSQL migration integration runs in CI. Owner-reported real installs and
removals exist; a real update to a newer map release remains untested.
The review found no proven unused transport/catalog lines safe to remove;
legacy compatibility branches and the OTM package-count guard remain in use.

## BBBike provider

BBBike is active in the v4 projection with BBBike and BBBike (Ontrail) as distinct
map types under one provider. Lifecycle IDs include type; geographic IDs remain
shared for statistics. Same-region opposite types conflict. See the
[API contract](docs/api.md) and [historical source review](../../history/2026-09-12-bbbike-local-contract.md).
Provider package counts are live metadata, not hardcoded compatibility claims.

## Explainable exact-model identification

Migration 047 adds optional XML model fields, nullable screen/Solar/inReach
specifications, a server-only identifier registry, immutable ingestion
assessments, and audited correction/review records. Original metadata and old
assignments remain intact. Retail SKUs (`010-…`) and XML/Connect IQ codes
(`006-B…`) have distinct kinds; USB and XML mappings can identify multiple
variants. Unknown feature values are not negative evidence.

Five checks evaluate model/variant, case size, screen, XML code and USB.
Automatic assignment requires all five to match and exactly one non-conflicting
candidate. Only approved mappings are positive evidence. Pending alternative
targets prevent a partially reviewed shared code from appearing unique. Shared mappings only
prove a property when all targets agree. Missing observations require a reasoned
admin decision; a conflict cannot be overridden by the assignment form. Source
corrections are separate append-only overlays, retaining the original field and
administrator/reason/history. Each assignment review stores its complete
assessment in the append-only decision audit; the original ingestion assessment
is never overwritten. Neither correction nor mapping approval silently
reassigns events. Public compatibility approval remains a separate action.

Authenticated model/installation details show checks and provenance; Devices
links to the read-only `/admin/devices/identity-audit.json` report, including
classification and hypothetical count/status impact. Old assignments may be
changed only after the owner separately approves that report. New unresolved
reports remain reviewable and cannot inherit a text-label public approval.
Assessment version 2 treats legacy model-field review statuses such as
`Identity pending` as missing model evidence. They cannot prove or contradict
a model; original MTP/XML observations still participate in every check.
Stored source values, intake assessments, assignments and public counts are
unchanged by this classification correction.

Operator commands (supply DATABASE_URL securely; snapshots are local files):

```sh
python -m terento_catalog.identity_registry import garmin connect-iq.json
python -m terento_catalog.identity_registry import usb music-players.h
python -m terento_catalog.identity_registry specifications /path/to/product-pages
python -m terento_catalog.identity_registry audit
```

Imports/enrichment default to dry-run. `--apply` stages identifier candidates
as PENDING, or enriches existing exact product URLs from `<product-id>.html`;
it never reassigns installations. Identifier approval is a separate admin
review requiring evidence and reason. Source SHA-256/revision and review
history remain in the registry. If the original XML field actually contains a
`010-…` SKU, its check uses the retail registry kind; `006-B…` observations use
the XML/Connect IQ kind. No SKU is fabricated from a generic XML code. Preserve upstream license notices when distributing any snapshots;
raw Garmin/Connect IQ snapshots are not included in this repository or client.
The routine Garmin collector also enriches exact specifications during sync.

Migration 048 supplies a reviewed 2026-09-13 bootstrap of 86 exact Garmin product
pages: 175 retail SKU links, 80 known screen technologies, 15 explicit Solar
and 10 explicit inReach values. Only matching existing IDs/product URLs are
enriched. Retail links have a recorded source review; 126 Connect IQ and 39
libmtp candidate links remain pending. The 27 historical records lacking exact
product URLs are preserved. This contains factual mappings/specifications and
source hashes, not raw upstream pages or private installation reports.

Admin identifiers are collapsed and grouped by code; original source names,
versions, decisions and review actions are disclosed on demand. Case dimensions,
physical screen size and resolution from reviewed specifications are shown
separately. Screen size/resolution alone cannot distinguish AMOLED/MicroLED;
several variants have the same values. No external AI service is integrated.

Device information presents the catalog model followed by watch size, display,
Solar charging and inReach. Unknown values remain `Not confirmed`; absence of
a feature name is not a negative specification. More specifications reveals
dimensions, screen size, resolution and family. A labelled Garmin source link
replaces the raw URL in this overview. Retail codes, catalog bookkeeping,
reported identifiers and all source-review actions remain under Technical
details. The overview adapts from four fact columns to two using its available
container width, keeps native keyboard disclosures and has no added motion.

Deploy migration/API first, then catalog/admin/site, audit historical reports,
and only then release the new app build. DB integration tests exercise replay,
shared codes, contradictory manual choices, audited correction, old aggregate
preservation and new unresolved/public-count isolation on a disposable DB.

## Model review presentation

Diagnostic details retain the device/variant, date, map/region, result, app
version and review-state summary above Model identification. Identification
shows one model with five concise match/missing-information bullets; full
candidate checks, original observations and source decisions remain in a
collapsed technical disclosure. A recommendation is preselected only when
every report has the same single non-conflicting candidate. A shared model
name can be shown while the exact size/screen remains unknown. Recommendations
never assign records automatically or waive the required evidence reason.
The resolver, source-correction rules and public approval counts are unchanged.

Model/variant presentation is standardized without changing stored identities:
`Pro`, generation and model suffixes stay in Model; size, screen technology,
Solar, inReach and existing edition labels appear in Variant, in that order.
For example `fenix 9 Pro - inReach, 51mm` displays as `fēnix 9 Pro` with
`51 mm, inReach`. Supplied true feature flags are displayed; missing flags do
not mean false. Unknown or conflicting screens are not filled from family
names. See [the display contract](docs/device-api.md#display-only-label-contract).
Approved records retain their IDs, specifications, assignments, counts and
approval state. The underlying catalog and event fields remain unchanged.

Build30 preparation adds migration049 and backward-compatible component
acquisition outcomes, preserving build29 intake and legacy deduplication.
Admin shows received XML/USB codes independently of mapping approval and derives
only unanimous reviewed specification facts for XML-matching variants.
New acquisition phases are grouped in Recent activity with component/history;
missing terminal receipt is explicit rather than treated as an active job.
