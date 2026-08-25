# Terento metadata service

This service is a metadata-only source for the Terento macOS catalog client.
It stores map-provider metadata and a separate Garmin smartwatch device
catalog. It does not download, host, proxy, mirror, cache, repackage, or serve
Freizeitkarte map binaries or Garmin product images.

The pre-MVP map-provider hard gate remains Freizeitkarte only. A separate
Garmin collector indexes official smartwatch-category metadata; it is a device
catalog, not a compatibility registry. Opt-in compatibility evidence uses a
separate schema and endpoints; it accepts no Unit ID, serial number, manifest,
account, private log, or map binary.

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
- `GET /maps/catalog.json` returns catalog version 1. The response includes
  `ETag`, `Last-Modified`, and cache headers and supports conditional GETs.
- `GET /devices/catalog.json` returns catalog version 2 for discovered Garmin
  smartwatch models, including `MISSING` or `AVAILABLE` asset metadata. It
  includes reusable legal metadata and validated `asset.source` attribution
  metadata. It uses the same cache validators and never includes a
  compatibility status.
- `GET /assets/devices/<name>.webp` serves validated runtime assets from the
  same API domain.
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
  after `PUBLIC_COMPATIBILITY_STATS_ENABLED=true`; it never returns raw events.

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
variant. The live-source dry-run on 2026-08-21 produced 63 map packages. This
is a dated provider snapshot, not a permanent claim about the current catalog.

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

All provider fetches happen in the collector process, never in an API request.
The API only reads PostgreSQL and returns metadata.

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
