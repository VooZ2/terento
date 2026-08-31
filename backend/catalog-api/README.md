# Terento metadata service

This service is a metadata-only source for the Terento macOS catalog client.
It stores map-provider metadata and a separate Garmin smartwatch device
catalog. It does not download, host, proxy, mirror, cache, repackage, or serve
Freizeitkarte map binaries or Garmin product images.

The public/MVP map-provider hard gate remains Freizeitkarte only. The local
beta.8 API also carries the known, server-side OpenTopoMap adapter in a paused
state; activation is an explicit operator action after its source gate. A
separate Garmin collector indexes official smartwatch-category metadata; it is
a device catalog, not a compatibility registry. Compatibility evidence and
map-operation statistics use separate schemas and endpoints; neither accepts
Unit IDs, serial numbers, manifests, accounts, private logs, or map binaries.

## Local development

Python 3.12+ is required. A PostgreSQL database is required for migrations and
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

Run the dependency-free tests from the repository root:

```sh
PYTHONPATH=backend/catalog-api/src python3 -m unittest discover -s backend/catalog-api/tests -p 'test_*.py'
```

## Endpoints

- `GET /health` checks database reachability and returns `{"status":"ok"}`.
- `GET /maps/catalog.json` returns an additive provider-neutral `schemaVersion: 2`
  projection while retaining catalog version 1 fields for the current FZK
  client. The response includes `ETag`, `Last-Modified`, and cache headers and
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
  raw events or device identifiers.
- `POST /compatibility/events` accepts validated, rate-limited, idempotent
  privacy-minimised install events after client consent. It stores only
  allowlisted columns, hashes the per-event deletion token, and never stores
  the submitted JSON body. Exact model variants are retained separately;
  reconnect observations are optional and never gate compatibility status.
- `DELETE /compatibility/events` lets the client erase one uploaded event by
  presenting its event UUID and secret deletion token. Events are also pruned
  automatically after 24 months.
- `GET https://api.terento.app/admin` serves the authenticated, noindex
  aggregate operator dashboard from the same API container as the catalog
  and account settings. The first account requires `ADMIN_BOOTSTRAP_SECRET`;
  later credentials are PBKDF2-hashed in PostgreSQL.
- `GET https://api.terento.app/admin/campaign-links` serves the authenticated,
  client-side campaign link builder. It shares the `/admin` session gate and
  stores no campaign links or history.
- `GET /compatibility/public/top-models.json` is a prepared, default-disabled
  aggregate API. It returns only individually reviewed and approved models
  after `PUBLIC_COMPATIBILITY_STATS_ENABLED=true`, with the canonical
  `TESTING`, `TESTED`, `SUPPORTED`, or `VERIFIED` status, successful count, and
  last evidence date; it never returns raw events.

Production API and admin updates are rolled out only when the catalog backend
or its deployment workflow changes; application releases and unrelated site
changes do not restart this service. They are rolled out by
`.github/workflows/deploy-catalog-api.yml`. The workflow builds the API image
from the checked-in source, runs the forward migration command against the
existing private database, replaces only the API and scheduler containers,
removes services from the known stale Compose project without deleting its
volumes, and asserts that exactly one API, scheduler, and healthy database are
running. It verifies the image release label, internal API-to-database health,
the public catalog/device endpoints, the website's API reference, and the
authenticated admin gate at `api.terento.app`. It keeps the previous API image
available for rollback and does not change the PostgreSQL or asset volumes.

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

Freizeitkarte documents a release cadence of roughly every two to three months,
not daily. The production scheduler therefore runs the complete metadata sweep
weekly on Monday at 03:00 UTC (`COLLECTOR_SCHEDULE_UTC=MON 03:00`). A manual
collection can still be run immediately after a provider release or source
change.

Scheduled catalog collection remains a separate process. The authenticated
admin `/collect` action may run one known adapter on demand and records a
collection run; health checks perform only bounded source probes. Neither path
downloads, stores, proxies, mirrors, or serves a provider map binary.

The reviewed OpenTopoMap adapter derives stable package identity from the
official `otm-<region>.zip` filename and reads each country row's generated-at
timestamp. It accepts all current official Garmin region shapes, excludes
Basecamp archives, and relates the shared Canada contours archive to both
Canada main packages. OpenTopoMap remains `PAUSED` until the beta.8 deployment
gate is accepted; deploying the adapter does not activate it automatically.

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

The weekly scheduler runs the Freizeitkarte map collection first and then the
Garmin device collection. A Garmin collection failure is logged and recorded
without clearing the previous device catalog or changing the map catalog.
