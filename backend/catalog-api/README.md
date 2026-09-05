# Terento metadata service

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
closed reference before investigating a manually reopened new problem. See
`internal/adr/0019-admin-github-issue-resolution-sync.md` for audit and safety rules.

Overview attention is independent of the statistics date filter. Visible admin
pages check every minute and offer Refresh when data changes, protecting unsaved
form edits. These changes are production-verified in release `932d757` (deployment run `33925498939`).

At phone widths (up to 700 px), admin navigation collapses into Menu with a review
shortcut, Overview attention precedes statistics, and the existing tables become
labelled records. Search remains visible; secondary device/installation filters
and the full device sorter are under Filters and sorting. Primary controls and
form typography are sized for touch. Diagnostic dialogs keep their close header
visible during content scrolling. These presentation changes reuse existing
endpoints and permissions. Local evidence is recorded in
`internal/audits/2026-09-05-admin-mobile-audit.md`; production rollout completed in release `932d757`.

Desktop admin tables fit their cards and wrap long values. Provider source
details show complete URLs; campaign output wraps. Installation history uses
page scrolling and diagnostic dialogs keep their close header visible. The
local ten-page audit and long-content evidence are recorded in
`internal/audits/2026-09-05-admin-desktop-fit-audit.md`; rollout completed in release `932d757`.

Production validation on 2026-09-05 covered all ten admin page types at 1280 px
and 390 px, the mobile menu, and automatic resolution of the two active
diagnostics linked to closed GitHub issue #94. Historical failure results were
retained. Deployment workflow: https://github.com/VooZ2/terento/actions/runs/33925498939.

### Admin custom IMG chart series — 2026-09-05

The Overview chart adds a separately labelled green Custom .img series from
successful, verified, complete compatibility operations whose provider is custom.
Grouped operation IDs (legacy event IDs when absent) prevent multi-map double
counting; bucket placement uses completion time and the selected time zone.
This is a read-only admin aggregation: custom imports remain excluded from
provider map telemetry, KPI success rates and the public catalog. No filenames
or paths are collected. HTML legend swatches now use background colors, matching
the SVG fills. Deployed as `ee9d25e`; workflow 33926631093 passed all jobs, including
237 backend tests and release-client catalog validation. Live Overview shows
one Custom .img installation in both 24h (00:00 Europe/Vilnius bucket) and
all-time views. The legend fits at 390 px without horizontal overflow.

Admin chart follow-up: event types remain stacked in one continuous bar per
time bucket. Segments have square joins; only the complete column silhouette
has rounded corners through one shared clip path. Each segment has its own
hover title and accessible label with event type, count and time. Data
aggregation is unchanged. Deployed as `4f47d35`, workflow `33927056958` PASS, including 238 tests
and release-client validation. Live segments share one x position and square
internal joins; individual titles show type, count and local time.

Admin model rows no longer show the Custom installation badge. Manual IMG
imports remain visible in the chart and installation history. Presentation-only
change; evidence and counters are unchanged. Deployed as `40272ed`; workflow `33927386387` passed all jobs and 238
backend tests. Live Installations has zero custom badges, and the existing
custom installation history entry remains visible.

### Diagnostic presentation cleanup

The current diagnostic dialog remains the supported admin presentation. Unused
legacy renderers and their exclusive CSS have been removed; regression tests
exercise the current page for technical details, linked issues, resolved
outcomes, multiple map results and reopen actions. API routes, evidence,
authentication, storage and lifecycle behavior are unchanged.
