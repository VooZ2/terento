# Catalog database schema

The PostgreSQL schema is applied by the forward-only migrations in
`src/terento_catalog/migrations/`. Map/provider tables store metadata only.
Compatibility evidence, administrator credentials, and sessions are isolated
from those tables and contain no Garmin Unit IDs, serial numbers, local
manifests, local paths, or map binaries.

## `map_provider`

One row for the external map provider.

| Column | Type | Meaning |
| --- | --- | --- |
| `id` | `text` | Stable Terento provider ID, currently `freizeitkarte` and `opentopomap` |
| `name` | `text` | Display name |
| `adapter_id` | `text` | Stable ID of a server-side prebuilt adapter; never uploaded through the API |
| `status` | `text` | `ACTIVE`, `PAUSED`, or `RETIRED` lifecycle state |
| `website` | `text` | Official provider map page |
| `license` | `text` | Provider/data licensing summary (canonical beta.8 field) |
| `license_information` | `text` | Provider/data licensing summary |
| `attribution` | `text` | Attribution shown to clients |
| `license_url` | `text` | Official license/source page |
| `last_catalog_sync` | `timestamptz` | Last successful metadata snapshot time |
| `created_at`, `updated_at` | `timestamptz` | Local catalog audit timestamps |

## `map`

One logical map region owned by a provider.

| Column | Type | Meaning |
| --- | --- | --- |
| `id` | `text` | Stable map ID, for example `freizeitkarte-deu` |
| `provider_id` | `text` | Foreign key to `map_provider` |
| `name` | `text` | User-facing name, for example `Germany` |
| `region` | `text` | Normalized provider region, for example `DEU` |
| `country` | `text` | Country or provider region label |
| `identifier` | `text` | Provider identifier, for example `DEU+` |
| `managed_by_terento` | `boolean` | Catalog management flag; not device ownership |
| `created_at`, `updated_at` | `timestamptz` | Local catalog audit timestamps |

`managed_by_terento` describes catalog scope only. It never proves that a
remote device file is Terento-owned; that proof remains local to the Mac
manifest.

## `map_version`

The latest known metadata for a normalized provider release. A unique
`(map_id, version_year, version_month)` key makes the weekly collector
idempotent while retaining the provider's raw release label.

| Column | Type | Meaning |
| --- | --- | --- |
| `id` | `bigserial` | Internal database ID |
| `map_id` | `text` | Foreign key to `map` |
| `version_year` | `smallint` | Comparable release year |
| `version_month` | `smallint` | Comparable release month |
| `raw_version` | `text` | Provider signal, e.g. `2/2026` or `Release 26.05` |
| `file_size_bytes` | `bigint` | Legacy provider package/download size; exposed as the backwards-compatible `sizeBytes` field |
| `download_size_bytes` | `bigint` | Explicit validated archive/network size from `Content-Length` or Range total |
| `install_size_bytes` | `bigint` | Exact uncompressed size of the selected final Garmin `.img` payload; nullable when unknown |
| `install_payload_path` | `text` | Canonical ZIP entry selected as the final install payload |
| `size_measurement_method` | `text` | Internal measurement method, for example `zip-central-directory-range` |
| `size_measured_at` | `timestamptz` | Internal last measurement timestamp |
| `size_measurement_warning` | `text` | Internal bounded-measurement diagnostic; not exposed by the API |
| `source_url` | `text` | Original provider download URL; HTTPS only |
| `release_date` | `date` | Provider underlying-data date when published |
| `checksum_sha256` | `text` | Optional provider checksum, currently nullable |
| `detected_at` | `timestamptz` | Last successful observation |
| `updated_at` | `timestamptz` | Last metadata change used for cache validators |

The API selects the highest normalized version for each map. If a version has
no known download size, it remains in PostgreSQL but is omitted from the
current public package list rather than being assigned a placeholder. An
unknown install size does not hide a map; it is returned as `null` and blocks
storage approval in the client.

## `provider_source`

Allowlisted provider source endpoints (`WEBSITE`, `CATALOG`, `LICENSE`, or
`DOWNLOAD`). URLs are HTTPS-only and are metadata references, not server-side
binary storage. The unique provider/type/URL key makes collection updates
idempotent and `last_checked_at` supports health freshness reporting.

## `map_package`

Provider-neutral package identity and release metadata. `provider_region_id`
preserves the provider token; `canonical_region_id` and `region` are the
normalized geographic presentation values. `availability` is independent of
provider health and artifact validation (`AVAILABLE`, `WITHHELD`,
`UNAVAILABLE`, or `RETIRED`). Existing `map` rows are linked through
`legacy_map_id` during migration 026 so the current FZK client remains
compatible. OpenTopoMap package IDs use the complete official region slug, so
country and multi-region packages share the same provider-neutral shape and
are not limited by a hardcoded country allowlist.

## `map_artifact`

One package payload, currently `main` or optional `contours`.

| Column | Type | Meaning |
| --- | --- | --- |
| `kind` | `text` | `main` or `contours` |
| `source_url` | `text` | Original provider URL; HTTPS only |
| `size_bytes` | `bigint` | Provider archive/network size |
| `install_size_bytes` | `bigint` | Extracted Garmin IMG size used by the native storage gate |
| `checksum_sha256` | `text` | Optional provider checksum |
| `content_type` | `text` | Observed/declared MIME type |
| `required` | `boolean` | Whether the artifact is required for package usability |
| `validation_status` | `text` | `NOT_VALIDATED`, `VALIDATING`, `VALIDATED`, `FAILED`, or `UNAVAILABLE` |
| `install_payload_path` | `text` | Selected archive entry when applicable |

The unique `(package_id, kind)` key prevents duplicate main/contours records.
The server never stores the artifact bytes.

## `provider_health_check`

Append-only bounded provider checks. It stores aggregate status and separate
website, catalog, redirect, download, MIME, magic bytes, ZIP, IMG, and last-update results,
plus final URL/content metadata, checked artifact count, timing, and a bounded
error code/detail. It does not store response bodies or map archives.
The aggregate describes checks that were actually performed: unavailable
freshness metadata or not-yet-collected artifact probes remain individually
`UNKNOWN` without masking healthy website/catalog availability.

## `catalog_collection_run`

Append-only metadata collection execution record for a provider. It records
`RUNNING`, `SUCCEEDED`, `PARTIAL`, or `FAILED`, timestamps, package/artifact
counts, and bounded failure details.

## `map_download_event`

Privacy-minimised, idempotent map-operation statistics. It stores UUID event
and operation IDs, known provider/package references, region, allowlisted event
type/outcome, app build, and occurrence/receipt timestamps. It has no device
identifier, raw JSON, local path, manifest, serial, Unit ID, or log field.
`event_id` is the primary idempotency key; a secondary unique operation/event
type/package key prevents accidental duplicates.

## `admin_audit_log`

Append-only audit records for provider health checks, collections, lifecycle
state changes, and other provider administration. It stores the admin user
reference, action, provider, structured old/new status, reason, target, request
ID, bounded JSON details, and timestamp. It never stores provider code or
binary payloads. Provider rows are retained; lifecycle retirement is a state
transition, not deletion.

## `device_family`

One canonical Garmin family discovered from the official smartwatch source.

| Column | Type | Meaning |
| --- | --- | --- |
| `id` | `text` | Stable family ID, for example `garmin-fenix` |
| `manufacturer` | `text` | Manufacturer, currently `Garmin` |
| `name` | `text` | Display family name, preserving diacritics |
| `canonical_name` | `text` | ASCII identity slug, for example `fenix` |
| `source_url` | `text` | Official category source URL; HTTPS only |
| `created_at`, `updated_at` | `timestamptz` | Local audit timestamps |

## `device_model`

One canonical model or meaningful hardware/display variant. Cosmetic color,
band, and material SKUs are collapsed by the collector.

| Column | Type | Meaning |
| --- | --- | --- |
| `id` | `text` | Deterministic stable device ID |
| `family_id` | `text` | Foreign key to `device_family` |
| `manufacturer` | `text` | Manufacturer name |
| `model` | `text` | Official display model name |
| `canonical_model` | `text` | ASCII canonical model identity, for example `fenix 8` |
| `variant` | `text` | Official meaningful variant text |
| `case_size_mm` | `smallint` | Explicit case size, nullable |
| `display_type` | `text` | Explicit AMOLED/Solar/MicroLED label, nullable |
| `part_number` | `text` | Representative official part number, nullable |
| `product_url` | `text` | Official Garmin product page |
| `source_url` | `text` | Official category source |
| `source_image_url` | `text` | Allowlisted direct official Garmin media URL (`res.garmin.com`), nullable |
| `active` | `boolean` | Conservative current/ historical state |
| `consecutive_missed_collections` | `smallint` | Absence counter used by inactive policy |
| `record_source` | `text` | `CURRENT_RETAIL`, `HISTORICAL_REVIEWED`, or `EVIDENCE_DISCOVERED` |
| `collector_managed` | `boolean` | Whether the current retail collector may update/deactivate this row |
| `first_seen_at`, `last_seen_at` | `timestamptz` | Observation timestamps |
| `created_at`, `updated_at` | `timestamptz` | Local audit timestamps |

Records are preserved. Only `collector_managed = true` rows participate in the
absence policy: `active` becomes false after three consecutive successful
complete collections do not observe a model; a partial or failed collection
does not advance that policy. Migration `016` seeds reviewed historical
identities, including fēnix 7, with `collector_managed = false`, so retail
absence cannot deactivate them.

## `device_usb_identity`

Separately reviewed hardware evidence associated with a model. This table is
not populated from Garmin retail metadata and is not returned by the public
device catalog endpoint. The initial row is the narrowly validated fēnix 8
MTP observation (`091e` / `51b8`); it must not be generalized.

## `device_asset`

Lifecycle-managed metadata for a Terento-controlled product asset. The
collector creates a `MISSING` baseline for discovered devices; it never
approves an image automatically. Review candidates are private.

| Column | Type | Meaning |
| --- | --- | --- |
| `device_model_id` | `text` | Foreign key to `device_model`; nullable only for `GENERIC` |
| `asset_type` | `text` | Asset role, for example `product-image` |
| `status` | `text` | `MISSING`, `PENDING_REVIEW`, `AVAILABLE`, or `DEPRECATED` |
| `url` | `text` | Available URL under `https://api.terento.app/assets/devices/`, nullable |
| `storage_key` | `text` | Private storage key such as `devices/garmin/fenix-8.webp` |
| `scope` | `text` | `EXACT_VARIANT`, `MODEL_SIZE`, `MODEL`, `FAMILY`, or `GENERIC` |
| `sha256` | `text` | Optional content checksum |
| `width`, `height` | `integer` | Optional dimensions |
| `mime_type` | `text` | Optional declared media type |
| `source_url` | `text` | Licensing/source evidence URL |
| `license_information` | `text` | Asset licensing notes |
| `attribution` | `text` | Required display attribution when applicable |
| `source_type` | `text` | `OFFICIAL_PRODUCT_MEDIA`, `TERENTO_RENDER`, or `GENERIC_FALLBACK` |
| `source_brand` | `text` | Controlled source brand: `Garmin` or `Terento` |
| `attribution_required` | `boolean` | Whether external attribution is required |
| `asset_version` | `integer` | Optional asset version |

Migration `004` adds scope support. Migration `005` changes the lifecycle,
adds the storage key, permits a global generic asset, and limits public URLs
to the existing API domain. Migration `006` restores a PostgreSQL unique
constraint for model-owned assets and a separate unique index for the global
generic asset. Migration `007` adds the explicit source type/brand/attribution
contract and fail-closes legacy available rows without that metadata. Separate
asset records are allowed for different scopes. Migration `008` adds the
allowlisted nullable `device_model.source_image_url` used for direct official
Garmin source media metadata. The Garmin collector never
approves these rows automatically. The public device catalog also exposes one
reusable top-level `legal` object containing the Garmin/Terento independence
notice; it is not duplicated in each device row.

`source_image_url` is not a `device_asset` row and is never downloaded by the
catalog service. When valid, the API exposes it as `sourceAsset` with
`OFFICIAL_PRODUCT_MEDIA` metadata. The macOS client may fetch it directly and
cache it locally only after validating the host and HTTPS URL.

## `device_collection_run`

Append-only operational diagnostics for Garmin collections. It stores source,
timestamps, counts, status (`RUNNING`, `SUCCEEDED`, `PARTIAL`, `FAILED`), and
structured warning/error diagnostics. These diagnostics are not exposed by
the public API. Migration `014` adds nullable before/after/add/update counts
for syncs recorded after that migration and exact first/last collection-run
links on `device_model`. Historical runs without those counters remain
explicitly unknown rather than being presented as zero.

Migration `014` also adds the independently reviewed `device_model.map_capable` field
(`true`, `false`, or `NULL` for unknown) and the separate operator-controlled
`device_model.support_status` field (`SUPPORTED`, `UNSUPPORTED`, or
`NOT_EVALUATED`). Neither field is added to the public device catalog
contract. Map capability, support state, and installation evidence remain
independent concepts. The migration carries forward the existing exact
write-capable `garmin-fenix-8-47-amoled` profile as `map_capable = true` and
`support_status = 'SUPPORTED'`. The public device-catalog v2 contract exposes
this as additive nullable `mapCapable`; it remains capability metadata, not a
support status or write grant. For other records, a stored `map_capable`
value still wins, but a `NULL` column is classified at admin-read time and on
the next Garmin collection from the same Map Manager prefix list used by the
native client (`terento_catalog.map_capability`, kept aligned with
`GarminMapCapabilityRegistry`). That classification is not a support claim
and does not authorize writes. Unrecognised models remain `NULL` / Unknown.

## Compatibility evidence and statistics

`compatibility_evidence_event` contains idempotent opt-in event rows identified
by a client-generated UUID. Only allowlisted columns are retained; the original
JSON payload is not stored. A per-event deletion token is retained only as a
SHA-256 hash, allowing the client to erase an uploaded event without an
account. Rows older than 24 months are deleted automatically. The retired
confirmation table has been removed because the current client does not create
a separate post-install confirmation signal. Migration 011 also removes older
beta events that had no deletion token, rather than retaining reports the
revised client could not erase. `compatibility_model_review`
stores maintainer-reviewed physical-device evidence, notes, review state, and
the default-false public-statistics switch/display name.

Migration 017 adds schema-v3 structured diagnostics. `operation_id` groups the
per-map rows produced by one Install action; map index/count, app build/release,
allowlisted failure stage and codes, write/object/cleanup state, and coarse
progress are stored as separate columns. No raw JSON or error message is
retained. `NOT_STARTED` is reserved for selected child maps skipped after an
earlier result stopped the batch.

Migration 018 adds the sanitized `raw_mtp_model` label and the controlled
`identity_resolution_code` category. It stores neither the MTP serial nor the
Garmin Unit ID. The migration also quarantines only the issue #32 legacy
`CHE+` failures (fēnix 8, 51 mm, firmware 2326, 2026-08-26) under an
identity-pending label; it preserves the rows for diagnosis and prevents their
lossy base-model identity from affecting public aggregation.

Migration 019 adds the internal `diagnostic_status` lifecycle (`ACTIVE` or
`RESOLVED`) and resolution metadata. Failed events from clients before the
beta.6 structured-diagnostics rollout are marked `RESOLVED`, not deleted. They
remain available in the private exact-model diagnostics drill-down but are
excluded from current compatibility counts, rates, status badges, and public
evidence projections. New beta.6 and later events remain active by default.

Migration 021 adds additive diagnostic resolution fields and lifecycle audit
rows, exact identity-resolution state/audit rows, and installation-
authorization audit rows. It also installs the canonical threshold function
used by the live compatibility view: recognized map-capable evidence is
required, then 0 successful operations is `TESTING`, 1–2 is `TESTED`, 3–4 is
`SUPPORTED`, and 5+ is `VERIFIED`; unrecognized or non-map records have no
compatibility status. Migration 025 restores the view to distinct active,
write-started installation operations while retaining per-map evidence for
diagnosis. Historical reviewed records are not deactivated by the retail
collector. Compatibility evidence, canonical links, and operator installation
authorization remain separate from device write authorization.

`compatibility_model_statistics` is a live SQL view over the evidence event
table and model review metadata. It includes only `ACTIVE` diagnostic events;
resolved history remains queryable through the private diagnostics path.
Events with a `canonical_device_model_id` are
grouped by that exact Garmin catalog record; textual `compatibility_identity`
is only the fallback for older uncanonicalized events. Formatting changes
between app versions therefore increase one variant's report and success
counts instead of creating another model row. Schema-v3 rows are first grouped
by operation; legacy rows each form one operation. Only write-started
operations enter attempted/success/failed compatibility counts, and a
multi-map operation succeeds only if every selected child result verifies.
Separate map-result and pre-write-failure totals remain available for private
diagnosis. The view calculates attempted, successful and
failed installation counts, success rate, firmware coverage, latest outcomes,
error-category totals and the canonical evidence status. Events carry an exact
compatibility identity plus optional variant/case-size and reconnect/map-
visibility observations. Reconnect is informational only. Status depends only
on successful opt-in installations: zero is `TESTING`, 1–2 is `TESTED`, 3–4
is `SUPPORTED`, and 5 or more is `VERIFIED`. The private dashboard reads this view. The
prepared public query additionally requires both `review_status = 'APPROVED'`
and `public_statistics_enabled = true` and only exposes evidence-backed
statuses.

Migration `015_canonical_compatibility_aggregation.sql` replaces the earlier
view rule that promoted one successful install to `SUPPORTED`. The view now
uses the same thresholds as `terento_catalog.compatibility_status`, and the
runtime API reapplies that classifier before rendering. This keeps raw DB
views, admin output, and public evidence output aligned.

Compatibility evidence may resolve to a reviewed historical `device_model`
transactionally during ingestion. An unresolved identity is retained under
its textual compatibility identity rather than rejected for missing retail
catalog membership. Neither the canonical link nor the evidence status is a
device write authorization.

The private `/admin/devices.json` aggregate joins evidence only through
`compatibility_evidence_event.canonical_device_model_id = device_model.id`.
It returns one row per exact Garmin catalog record, so display model strings
cannot merge separate variants. The HTML `/admin/devices` page uses the same
query and keeps technical USB identities inside the detail dialog. Migration
025 stores one server-time row in `compatibility_device_card_failure_epoch`.
Device-card Attempts include all retained successful operations plus failed
operations received on or after that epoch; Failed includes only those
post-epoch failures. Resolving a post-epoch failure does not remove it from the
card, while every failure received before the epoch remains excluded.

## Administrator authentication

`admin_user` stores a unique username and salted PBKDF2-SHA256 password hash;
no recoverable password is stored. `admin_session` stores only hashes of the
opaque session and CSRF tokens with an expiry and user foreign key. PostgreSQL
is not published outside the private Docker network.
