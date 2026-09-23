# Catalog database schema

The PostgreSQL schema is applied by the forward-only migrations in
`src/terento_catalog/migrations/`. Map/provider tables store metadata only.
Compatibility evidence, administrator credentials, and sessions are isolated
from those tables and contain no Garmin Unit IDs, serial numbers, local
manifests, local paths, or map binaries.

## `map_provider`

One row for a reviewed external map provider. There is no fixed provider count;
the registry contains only providers with a known server-side adapter.

| Column | Type | Meaning |
| --- | --- | --- |
| `id` | `text` | Stable Terento provider ID, for example `freizeitkarte` or `opentopomap` |
| `name` | `text` | Display name |
| `adapter_id` | `text` | Stable ID of a server-side prebuilt adapter; never uploaded through the API |
| `status` | `text` | `ACTIVE`, `PAUSED`, or `RETIRED` lifecycle state |
| `website` | `text` | Official provider map page |
| `license` | `text` | Provider/data licensing summary (canonical field) |
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
`legacy_map_id` during migration 026 so existing macOS clients remain
compatible. Provider-specific package IDs and region shapes are preserved by
the adapter, while the public package contract remains provider-neutral and is
not limited by a hardcoded country allowlist.

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

## `github_download_snapshot`

One cumulative observation of public GitHub release asset downloads for a UTC
hour. The scheduler upserts the current hour so retries do not create duplicate
rows. The table stores aggregate counters and a compact release/asset
population identity; it does not retain release metadata, asset names,
response bodies, or binaries. The Overview derives `.dmg` and `.zip` increases
only between valid consecutive observations. The first observation is a
baseline; unchanged counters are observed zero; nonnegative deltas from rows
with missing population metadata remain legacy/unverified observations; counter
decreases or confirmed population changes are discontinuities; and missing or
long-gap intervals are unknown/uncertain rather than filled with zero.
`observed_at` is the source measurement time, while `hour_start` is only the
upsert key. Equality of `release_count` alone does not prove equal asset
composition, and a nullable fingerprint alone does not prove that the
population changed.

| Column | Type | Meaning |
| --- | --- | --- |
| `hour_start` | `timestamptz` | UTC start of the observed hour and primary key |
| `observed_at` | `timestamptz` | Time the GitHub totals were read |
| `dmg_total` | `bigint` | Current sum of `.dmg` asset download counts |
| `zip_total` | `bigint` | Current sum of `.zip` asset download counts |
| `release_count` | `integer` | Number of public releases observed in the paginated read |
| `asset_count` | `integer` | Number of counted `.dmg` and `.zip` assets in the observation; nullable for legacy rows |
| `population_fingerprint` | `text` | Stable hash of counted release/asset identities; nullable for legacy rows |

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
`support_status = 'SUPPORTED'`. The public-read installation-policy v3
contract exposes the stored nullable capability as `mapCapable` and derives
`baseModel` from the catalog model label. Only an active Maps=Yes row derives
`APPROVED`; Maps=No or an inactive row derives `BLOCKED`, and an active
Maps=NULL row derives `PENDING`.
`support_status` remains Admin/operator metadata and is not projected into or
used by that write policy. The native client uses normalized base-model and
available variant matching to determine which active catalog rows are
plausible. Conflicting variant evidence broadens the candidate set; it does
not by itself deny authorization. Authorization is determined from the Maps
capability of all remaining possible candidates. It approves only when all
plausible rows are Maps=Yes; all Maps=No blocks, and mixed or NULL values are
pending. A base-model conflict remains pending. Unrecognised models remain
pending/unknown rather than being treated as permanently unsupported. The
public device-catalog `mapCapable` display remains separate from the native
write-policy decision.

## Compatibility evidence and statistics

`compatibility_evidence_event` contains idempotent shared event rows identified
by a client-generated UUID. Only allowlisted columns are retained; the original
JSON payload is not stored. The nullable `deletion_token_hash` column remains
only for legacy schema-version-1 through schema-version-3 rows; current
schema-version-4 clients send no deletion credential, and uploaded events are
immutable through the public API. Rows older than 24 months are deleted
automatically. The retired confirmation table has been removed because the
current client does not create a separate post-install confirmation signal.
Migration 011 removed older beta events that had no deletion token, rather than
retaining reports the revised client could not erase. `compatibility_model_review`
stores maintainer-reviewed physical-device evidence, notes, review state, and
the default-false public-statistics switch/display name.

Migration 017 adds schema-v3 structured diagnostics. `operation_id` groups the
per-map rows produced by one Install action; map index/count, app build/release,
allowlisted failure stage and codes, write/object/cleanup state, and coarse
progress are stored as separate columns. No raw JSON or error message is
retained. `NOT_STARTED` is reserved for selected child maps skipped after an
earlier result stopped the batch.

The server-first v4 failure-context extension retains optional validated
`failureContext` and `originalFailureContext` separately on the compatibility
event in nullable JSONB columns `failure_context` and `original_failure_context`.
Non-null values use the same nonrecursive closed object; `protection` is nested
inside its owning context. This is allowlisted structured evidence, not storage
of the original request body or an unrestricted diagnostic JSON bag. The exact
field contract is defined in
[the shared event contract](../../../contracts/README.md#structured-installation-failure-context).
For accepted v4 events, omitted and explicit JSON-null contexts both persist as SQL NULL, not JSONB
`null`. This normalization uses the existing nullable columns and requires no
additional migration or schema v5. Strict validation of non-null v4 objects
remains unchanged; a non-null original context requires a terminal cleanup
context object. Absent context on existing rows remains absent, with no historical backfill or
inferred reason. Event identity, idempotency, retention and statistics semantics
are unchanged. Cleanup failure must not overwrite its originating context.
Migration replay and persistence/read-model tests must use PostgreSQL; SQLite
delivery tests alone do not establish this storage gate. This extension is a
server-first source change, not evidence of deployment or new app emission.

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
compatibility status. Migration 025's older active/write-started operation
projection is superseded by migration 056's logical per-result semantics while
per-map evidence remains available for diagnosis. Historical reviewed records
are not deactivated by the retail collector. Compatibility evidence, canonical
links, and operator installation authorization remain separate from device write
authorization.

`compatibility_model_statistics` is a live SQL view over the evidence event
table and model review metadata. It includes active events and retained failed
history under the historical-count rule; resolved history remains queryable
through the private diagnostics path. The
canonical population, result classification and rate definitions are in
[`contracts/STATISTICS_CONTRACT.md`](../../../contracts/STATISTICS_CONTRACT.md).
Migration `032_custom_img_compatibility_evidence.sql` extends the event source
constraint with the fixed `custom` local-IMG label. Custom evidence still uses
the same watch/model aggregation and never creates a provider map-event row;
eligible custom fresh results may be projected into common map-statistics read
models without a guessed catalog package or country.
Events with a `canonical_device_model_id` are
grouped by that exact Garmin catalog record; textual `compatibility_identity`
is only the fallback for older uncanonicalized events. Formatting changes
between app versions therefore increase one variant's report and success
counts instead of creating another model row. Schema-v3 rows are first grouped
by logical map result (`operation_id + map_result_index`); legacy rows each form
one result. A verified main-map result or a failure after writing began enters
the fresh-install denominator; current pre-install `write_started=false` and
unknown write facts do not. Optional component outcomes remain on the main
result, and a multi-map operation therefore contributes one result per selected
main map rather than one result per component.
Separate map-result and pre-write-failure totals remain available for private
diagnosis. The view calculates attempted, successful and
failed installation counts, success rate, firmware coverage, latest outcomes,
error-category totals and the canonical evidence status. Events carry an exact
compatibility identity plus optional variant/case-size and reconnect/map-
visibility observations. Reconnect is informational only. Status depends only
on successful shared installations: zero is `TESTING`, 1–2 is `TESTED`, 3–4
is `SUPPORTED`, and 5 or more is `VERIFIED`. The private dashboard reads this view. The
prepared public query additionally requires both `review_status = 'APPROVED'`
and `public_statistics_enabled = true` and only exposes evidence-backed
statuses.

Migration `056_statistics_semantics.sql` replaces the earlier per-operation and
`write_started` interpretation with logical map-result classification,
explicit pre-install exclusion and conflict-safe deduplication. It retains raw
evidence and historical failure visibility; it does not migrate or invent
production counts.

The alternate `060_installation_authorization_statistics_exclusions.sql` draft
is preserved only as [non-executable migration-source provenance](migration-source-provenance/060_installation_authorization_statistics_exclusions.sql.txt).
The executable beta migration `060_missing_diagnostic_review_tasks.sql` remains
unchanged. Candidate migration 062 adds server-classified statistics-exclusion
and security-review fields.
Only explicit `write_started=false` plus no remote object can receive
`OUT_OF_SCOPE_PREWRITE`; NULL or legacy write facts are not guessed. This
general exclusion mechanism preserves historical evidence and does not infer
missing write facts.

The complete `2026-09-23` live schema preflight ran from
`tools/installation-statistics-schema-preflight.sql` as one audit inside a
`READ ONLY` transaction (`transaction_read_only = on`) and ended with
`ROLLBACK`. Of 25 expected objects, 24 matched. The live `schema_migrations`
history contains versions through `061`, but confirmed drift remains:
`compatibility_evidence_event` lacks `statistics_exclusion_code`,
`statistics_exclusion_reason`, and `security_issue_code`;
`map_download_event` lacks `map_result_index` and those same three fields;
`statistics_exclusion_audit` and the expected exclusion/audit constraints and
indexes are absent; and the live `compatibility_model_statistics` view does
not apply the exclusion filter. The exact missing-object matrix is recorded in
the full preflight result and final task report. The original SQL executed for
the live migration records is unknown because the history stores no content
checksum. The new `062_reconcile_installation_statistics_schema.sql` is a local
additive draft derived from the full preflight; isolated migration tests cover
clean, live-like, and already-reconciled schemas, and confirm existing map
events keep `map_result_index = NULL`. The draft has **not** been approved or
applied. Do not treat the version marks or local SQL as proof of schema parity.
Historical map-download rows without a recorded result index remain `NULL`; the
reconciliation does not invent or backfill historical `map_result_index`
values.

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
Device-card Attempts include all retained successful results plus eligible
failed results received on or after that epoch; Failed includes only those
post-epoch eligible failures. Resolving a post-epoch failure does not remove it
from the card, while every failure received before the epoch remains excluded.

## Administrator authentication

`admin_user` stores a unique username and salted PBKDF2-SHA256 password hash;
no recoverable password is stored. `admin_session` stores only hashes of the
opaque session and CSRF tokens with an expiry and user foreign key. PostgreSQL
is not published outside the private Docker network.

## Operational health

Migration 030 adds `operational_observation` and `scheduler_heartbeat`.
Operational observations retain an idempotent GitHub run identity, a bounded
kind/component/status, timestamp, Terento Actions URL, commit SHA, optional
release/build labels, short summary, and scalar JSON details. Raw workflow
logs, arbitrary URLs, user/device identifiers, and credentials are outside the
contract. Observations are pruned after 180 days during later ingestion.

`scheduler_heartbeat` is a singleton per known job and records its next run,
latest start/completion, status, and a fixed bounded error summary. These
tables are private `/admin` observability inputs and grant no command or test
execution capability.

Migration044: `map_package.map_type`, `geographic_region_id`, `country_codes`
(JSONB), and `region_kind` are additive. Existing provider identities and
historical event rows are unchanged. BBBike enforces its two allowed map types
and non-null geographical key while lifecycle identity remains variant-specific.
The map statistics read model uses geographical identity for grouping and a
separate `map_type` for type attribution. The compatibility provider constraint
adds BBBike independently of its PAUSED activation state.

### Migration049: component acquisition evidence

`map_download_event` adds nullable paired `acquisition_id` UUID and
`component_kind` (main/contours). Legacy operation/event/package uniqueness is
retained as a partial index for NULL acquisition IDs. New attempts use unique
acquisition/event phases and at most one terminal phase. Existing rows are not
rewritten. Accepted additional phases are DOWNLOAD_PROCESSING,
DOWNLOAD_CANCELLED and DOWNLOAD_INTERRUPTED. All retain the existing telemetry
privacy, retention and local-test exclusion boundaries.
