# Catalog operations

The catalog service is metadata-only. PostgreSQL is private to the Docker
network, and the service never hosts or proxies map archives or Garmin image
binaries.

## Forward migration and size backfill

Apply migrations in filename order. Migration `003` adds explicit map download
and install-size fields and backfills only the legacy download-size field.
Migration `004` adds device-asset scopes. Migration `005` adds the asset
lifecycle, review/public storage key, generic scope, and restricts public
asset URLs to the existing API domain. Migration `006` makes model-owned
asset uniqueness compatible with PostgreSQL upserts. Migration `007` adds
validated asset source metadata and hides legacy available rows that do not
declare attribution semantics.

Run the existing migration command first, then run the size backfill:

```sh
terento-catalog-migrate
terento-catalog-backfill-sizes
```

The backfill uses the original Freizeitkarte package URL and bounded `HEAD` /
`Range` requests. It does not download the archive body to the server. A
provider without Range support can still provide `downloadSizeBytes` from
`Content-Length`, but cannot provide a new `installSizeBytes` measurement.
The command preserves existing known-good values on failure and reports the
failed rows in its JSON summary.

For a read-only provider check:

```sh
terento-catalog-backfill-sizes --dry-run
```

## Weekly collection

The scheduled sweep is weekly on Monday at 03:00 UTC:

```text
COLLECTOR_SCHEDULE_UTC=MON 03:00
```

The scheduler collects Freizeitkarte maps first and Garmin device metadata
second. A failed or partial provider run does not clear the previous catalog.
The Garmin collector creates a `MISSING` asset baseline for new devices; it
does not request product-image binaries and it never changes an asset to
`AVAILABLE`.

## Evidence lifecycle cleanup

Migration `019_resolved_legacy_diagnostics.sql` is applied automatically by
the normal forward migration command. It marks failed pre-beta.6 events as
`RESOLVED` without erasing the old reports. Migration
`024_count_all_installation_events.sql` briefly broadened all aggregates;
migration `025_device_card_failure_epoch.sql` supersedes that behavior. The
main Installations and public compatibility view again counts only active,
write-started operations. The old events remain in the database and are
visible in the exact model's authenticated diagnostics drill-down when the
operator selects `All` or `Resolved`.

Migration 025 also records its application time in
`compatibility_device_card_failure_epoch`. Device cards exclude failures
received before that timestamp and count every distinct failure received
afterward, including pre-write failures. Successful device-card history is
preserved. Do not edit the epoch after deployment unless a separately reviewed
counter reset is explicitly requested.

Migration `021_canonical_admin_semantics.sql` keeps its SQL
compatibility-status classifier parameter as `BIGINT`, matching PostgreSQL's
`count(*)` aggregate type, so the derived view can be rebuilt during a forward
deployment.

Migration `027_restore_otm_paused_state.sql` is a one-time safety repair for
beta.8. It restores OpenTopoMap to `PAUSED` only when the provider is active,
has no available packages, and has no audited activation. The repair is
recorded in `admin_audit_log`; an explicitly audited activation is preserved.

## Asset review and publication

Asset work is explicit and non-destructive. A candidate is prepared into
private review storage and only an operator approval moves it into the public
asset tree:

```sh
terento-catalog-asset prepare \
  --device-model-id garmin-fenix-8-47-amoled \
  --scope MODEL_SIZE \
  --storage-key devices/garmin/fenix-8-47-amoled.webp \
  --source /path/to/normalized.webp \
  --source-url https://res.garmin.com/en/products/010-02904-10/v/cf-lg.jpg \
  --source-type OFFICIAL_PRODUCT_MEDIA \
  --license-information "Official Garmin product media; source URL retained in the asset record" \
  --attribution "Garmin product media used for device identification; Terento is independent" \
  --attribution-required

terento-catalog-asset approve \
  --device-model-id garmin-fenix-8-47-amoled \
  --scope MODEL_SIZE \
  --storage-key devices/garmin/fenix-8-47-amoled.webp \
  --source-url https://res.garmin.com/en/products/010-02904-10/v/cf-lg.jpg \
  --version 1 \
  --source-type OFFICIAL_PRODUCT_MEDIA \
  --license-information "Official Garmin product media; source URL retained in the asset record" \
  --attribution "Garmin product media used for device identification; Terento is independent" \
  --attribution-required
```

For a Terento-created asset, use `--source-type TERENTO_RENDER`; for the
neutral fallback use `--source-type GENERIC_FALLBACK`. Both use `Terento` as
the source brand and do not require the attribution flag. The CLI validates
that the source type, brand, and attribution requirement agree before an asset
can become `AVAILABLE`.

Only validated WebP files up to 8 MiB with valid dimensions are accepted.
Review files are not served by the API. Assets are served from
`https://api.terento.app/assets/devices/`; no asset subdomain is used.

## Public verification

After a successful operational update, verify the read-only routes and cache
validators:

```sh
curl -fsS https://api.terento.app/health
curl -fsSI https://api.terento.app/maps/catalog.json
curl -fsSI https://api.terento.app/devices/catalog.json
curl -fsSI https://api.terento.app/assets/devices/garmin/example.webp
curl -fsSI https://api.terento.app/admin
```

The asset URL returns 404 until an asset is explicitly approved and published.
Before an administrator exists, `https://api.terento.app/admin` returns a 303
redirect to `/admin/setup`; after setup it redirects unauthenticated requests
to `/admin/login`. Both are expected and remain noindex/no-store.
