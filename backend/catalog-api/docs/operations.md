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

The current backfill command uses the reference provider package URL and
bounded `HEAD` / `Range` requests. It does not download the archive body to the
server. A provider without Range support can still provide `downloadSizeBytes`
from `Content-Length`, but cannot provide a new `installSizeBytes` measurement.
Future provider backfills must resolve their URL through the provider adapter;
the command must not assume Freizeitkarte-specific URL or archive rules.
The command preserves existing known-good values on failure and reports the
failed rows in its JSON summary.

For a read-only provider check:

```sh
terento-catalog-backfill-sizes --dry-run
```

## Live installation-statistics migration 062

The 2026-09-23 live audit and confirmed schema drift are recorded in the
[062 runbook](installation-statistics-062-live-runbook.md). Three production
operations are distinct:

- **STATUS** — `terento-deploy api status` reads existing container/image
  metadata and the migration ledger in an explicit read-only transaction. It
  does not call HTTP health, pull an image, run maintenance, or mutate services.
- **MIGRATE** — `terento-deploy api migrate --target 062 ...` is a root-owned,
  migration-only source path pinned to a registry digest, revision, migration
  SQL hash, and runner hash. It runs only the one-shot migration service; the
  API and scheduler are not restarted or replaced.
- **DEPLOY** — the existing `terento-deploy api <digest> <revision>` remains a
  separate service deployment operation. Its combined deploy behavior is not
  a substitute for target-062 migration. The API workflow no longer deploys on
  pushes; a manual dispatch requires a positive target-062 completion input
  and the owner-controlled `TERENTO_FIXED_OPS_INSTALLED=true` repository
  variable. Migration-source pushes are excluded as an additional guard, and
  the new helper requires a valid candidate identity and rejects deployment
  unless candidate inventory and live ledger both match exactly 001–062. DEPLOY
  does not run a migrator; a pending/later schema blocks service replacement.
  Images with 063+ are refused until a separately reviewed migration gate is
  implemented. The variable is not set by this task.

The canonical helper, migration module, installer, and tests are prepared in
the local working tree but remain untracked/uncommitted and are **not installed
on the VPS**. The forced-SSH template has also not been installed; therefore
these command forms are not currently available remotely. The owner-run
installer requires a clean committed checkout and a separate authorized apply
step. No production migration or deployment is authorized by this code.

The operations share one non-blocking host lock for deploy and migration;
read-only status does not take the lock. The migration runner verifies an
immutable candidate and the exact 001–062 image inventory, requires a live
ledger exactly at 001–061 (or reports safe `ALREADY APPLIED` for exactly
001–062), and rejects gaps or later entries. Its 062 SQL statements and ledger
insert execute in one database transaction. For the current reviewed runner,
any 063+ migration file is reported by name and rejected before DB execution.

`GET /health` is read-only in this candidate source: it checks DB readiness
but does not run retention. The existing scheduler performs retention once
per configured collector cycle. The local default is daily at 03:00 UTC, and
the production scheduler configuration was read as
`COLLECTOR_SCHEDULE_UTC=03:00` on 2026-09-23. The 24-month cutoff is unchanged;
daily cleanup may lag by up to 24 hours, which is accepted behavior. This
candidate implementation has not been deployed. See the
[production operations protocol](production-operations-protocol.md) and
[recovery procedure](production-db-recovery.md) for exact gates. Fresh
PostgreSQL-only backup creation/restore validation remains unproven: the DB
container provides `pg_dump` and `pg_restore` 16.15, matching the live server
version, and the live DB identity/ledger were read-only verified. No approved
encrypted off-host destination or isolated restore evidence is available. The
Hostinger points are whole-VPS restores and require owner selection and
acceptance; they are not a normal schema rollback.

062 is still **NOT READY** for live approval or execution: the tracked source
candidate is clean, but no immutable image/receipt or validated PostgreSQL
recovery point exists; the new helper has not been installed, and the recovery
point gate remains open. Do not call Docker/migrator directly, create a backup,
deploy, or run the migration without separate authorization. If execution
status is uncertain, use the SELECT-only postcheck; never replay SQL or downgrade.

## Scheduled collection

The provider catalog sweep runs daily at 03:00 UTC:

```text
COLLECTOR_SCHEDULE_UTC=03:00
```

The scheduler runs the reviewed Freizeitkarte, MapRando, and OpenTopoMap
adapters independently. A failed or partial provider run does not stop the
other providers and does not clear the previous catalog. Each successful run retains
the provider's latest release label, deterministic metadata fingerprint, and
whether a change from the previous successful snapshot was detected. On
Monday, the provider phases are followed by the weekly Garmin device metadata
collection.
The Garmin collector creates a `MISSING` asset baseline for new devices; it
does not request product-image binaries and it never changes an asset to
`AVAILABLE`.

The scheduler records `WAITING`, `RUNNING`, `HEALTHY`, `WARNING`, or `FAILED`
state in `scheduler_heartbeat`. `/admin/system-health` treats overdue or stale
heartbeats as a warning. Failure to write observability does not stop the next
scheduled collection attempt.

The same scheduler process performs a bounded GitHub Releases API read at
startup and then at every UTC hour. It follows all public release pages for
`VooZ2/terento` and aggregates only the current `download_count` values of
`.dmg` and `.zip` assets. It stores one cumulative snapshot per hour in
`github_download_snapshot`; a failed read leaves the previous snapshot intact.
The Overview chart derives observed `.dmg`/`.zip` deltas for the selected
period while its two total fields use the newest cumulative values. Historical
rows without the population metadata retain nonnegative deltas as
legacy/unverified observations; confirmed counter or population discontinuity
intervals remain unknown, and long gaps remain uncertain. No GitHub token,
release metadata, or binary is stored.

## CI, deployment, and weekly email health

GitHub Actions remains the test executor. The API stores only bounded results
posted to `/internal/operations/observations`; `/admin` cannot start a test.
Configure the same long random value as `OPERATIONS_INGEST_SECRET` in the API
environment and `TERENTO_OPERATIONS_INGEST_SECRET` in GitHub Actions secrets.

The Monday full-matrix workflow retains its report and sends it to
`report@terento.app` with SMTP2GO STARTTLS through `mail-eu.smtp2go.com:2525`.
Configure `SMTP2GO_USERNAME` and `SMTP2GO_PASSWORD` as GitHub Actions secrets.
The sending domain `terento.app` must be verified in SMTP2GO before enabling
the workflow. Never commit SMTP credentials or the provider-supplied DNS
values. Email delivery is reported separately from test health, so a mail
failure cannot turn a failed test into a passing result or erase the retained
report. The report also includes each supported provider's catalog status,
latest release, last successful collection, last detected release change, and
the reason for any stale or failed state. This context is read through the
same bearer-protected operations boundary and contains metadata only.

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
received before that timestamp and count distinct eligible failures received
afterward, except server-classified `OUT_OF_SCOPE_PREWRITE` blocks. Current
pre-write and unknown-write results remain visible in diagnostic history but
stay outside completed installation counts. A reported write boundary or
remote object is retained for security review. Successful device-card history
is preserved. Do not edit the epoch after deployment unless a separately
reviewed counter reset is explicitly requested.

Migration `021_canonical_admin_semantics.sql` keeps its SQL
compatibility-status classifier parameter as `BIGINT`, matching PostgreSQL's
`count(*)` aggregate type, so the derived view can be rebuilt during a forward
deployment.

Migration `027_restore_otm_paused_state.sql` is a historical one-time safety
repair. It restores OpenTopoMap to `PAUSED` only when the provider is active,
has no available packages, and has no audited activation. The repair is
recorded in `admin_audit_log`; an explicitly audited activation is preserved.

Migration `028_force_otm_beta8_paused.sql` is the historical release-state
correction. It pauses an existing `ACTIVE` OpenTopoMap record once and
records the correction in `admin_audit_log`, so testing starts from the
required paused state and a later activation remains an intentional admin
action.

Migration `058_remove_authorized_test_events_20260825.sql` is a one-time,
owner-authorized cleanup of five test installation minutes displayed in the
Europe/Vilnius timezone. It requires exactly five matching `1.0.0` rows with
the requested regions and outcomes in one telemetry stream, or the same five
operation IDs in both streams, before making any change; the temporary check
constraint aborts the migration when that shape does not match (a completely
empty telemetry database is treated as a safe no-op for fresh database
bootstraps). It then removes only lifecycle rows keyed by those operation IDs
and compatibility rows linked to or explicitly identified by those targets
(dependent evidence records use the existing cascade rules), and records the
exact request and deletion counts in `admin_audit_log`. It does not use the
broad local-test purge endpoint and does not change UI or design behavior.

The OpenTopoMap collector accepts exactly 177 official `main` ZIP
archives. `contours` links remain visible to the parser for source auditing,
but are not collected or allowed to fail the main catalog; their installation
gate is deferred. Main archive inspection uses bounded range requests with a
small retry and a maximum of four concurrent provider requests.

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

### BBBike metadata preparation

Migration044 registers BBBike PAUSED and adds additive package type/geography
columns plus compatibility-evidence acceptance. Do not activate it as part of
migration or metadata collection. The reviewed `bbbike` adapter is included in
the normal collector and authenticated provider collection action. Collection
of a paused provider prepares metadata; it does not change provider status.

The collector traverses the ready region tree, including subregion links, and
excludes the Russia branch before requests. It makes at most four concurrent
bounded artifact metadata inspections. A source429 ends further requests from
that fetcher; no retry or alternative host bypass is attempted. Every source
redirect is rejected. Persisted validated source proofs are reused only when
an exact HEAD tuple (strong ETag, modification time, ZIP size) and source identity
are unchanged, reducing the daily scheduler's archive reads. A changed source
must pass a new bounded ZIP/README/checksum/IMG-header inspection. One bad
artifact retains its known release as unavailable instead of dropping the
whole provider. A failed directory traversal fails the collection and preserves
the last committed snapshot.

Before local hardware tests: migrate the receiving backend, collect BBBike while
PAUSED, check the exact candidate IDs against stored packages, then verify both
`-local` streams in Test data. Do not use synthetic production events. The
`tools/check_bbbike_database.py` check permits synthetic classification evidence
only in a disposable database named `terento_ci`.
