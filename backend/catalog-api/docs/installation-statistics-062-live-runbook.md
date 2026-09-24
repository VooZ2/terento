# Live installation-statistics schema reconciliation (062)

## Status

**NOT READY for separate 062 approval or execution.** The complete 2026-09-23
live audit confirmed the drift below. The candidate source contains
separate source implementations for read-only STATUS, root-owned MIGRATE
`--target 062`, and the existing DEPLOY operation. Migration requires a pinned
image digest, full revision, 062 SQL hash and runner hash; it verifies the
candidate inventory and target enforcement, requires an exact live ledger,
and does not invoke API/scheduler services. A shared non-blocking operations
lock serializes migration and deployment. See
[`production-operations-protocol.md`](production-operations-protocol.md).

The production helper and migration module are not installed on the VPS. The
existing forced-SSH entry point remains unchanged; the tracked SSH template is
not installed by the owner-run helper installer. Therefore neither the direct
root commands nor status/migration SSH commands are currently available in
production. Do not use combined deploy as a migration-only substitute, and do
not bypass the root boundary with an ad-hoc Docker or shell command. The
installed helper version was not inspected or updated.

This document and its SQL checks are preparation only. They do not authorize a
live migration, service change, deployment, or release. The SQL and runner
source must be bound to the exact clean candidate commit and immutable image
receipt before execution; this preparation itself grants no permission to
build, deploy, or migrate. For source comparison, the current 062 SQL SHA-256 is
`92aa31455667de34701a9d4810bde282e0e648e5f42fa53163c397ad0a761203`; this is
not proof that any image contains those bytes. The CI receipt must independently
verify the image digest, embedded revision, migration inventory and file hash.

## Recovery-path audit (read-only provider check plus local evidence)

On 2026-09-24, the authenticated Hostinger account API was used read-only to
confirm VPS `1958677` (`rukas.terento.app`) is running and refresh provider
recovery points. It lists `52757820` from 2026-09-19 11:10:29 UTC and
`51894425` from 2026-09-12 14:15:16 UTC; the snapshot endpoint returns ID `0`,
so neither is a fresh accepted pre-062 recovery point. The last VPS-shell
check on 2026-09-23 found no host `pg_dump`; the DB container reported
`pg_dump (PostgreSQL) 16.15`. No backup was created, restored or tested, and
no database write was performed. Hostinger provider restore replaces the
whole VPS, not only PostgreSQL ([Hostinger VPS backup and restore guidance](https://www.hostinger.com/support/1583232-how-to-back-up-or-restore-a-vps-at-hostinger/)).
Hostinger's current help page says provider backups/restores can take 10 minutes
to a few hours and lock the VPS from management until complete; availability
and performance can vary, but it does not claim the VPS is necessarily
stopped. Up to two daily and two weekly backups are retained, with each new
backup replacing the oldest in its set. Only one manual snapshot exists; a new
one overwrites it and it expires after one day. Restore overwrites the whole
current VPS and cannot be canceled or reverted. Check the current hPanel action
summary before scheduling.
The Hostinger Docker Manager endpoint reports this Ubuntu OS is unsupported by
that feature. `pg_restore`, container/image identity, a secure credential path,
the proposed root-only backup directory, free space, and the PostgreSQL 16
restore image digest remain to be verified read-only in the authenticated VPS
shell; a provider-control-plane response does not verify these.

`/deploy/` and `/internal/` are Git-ignored by `.gitignore`, so their paths
below describe this workstation's operator material, not a guaranteed release
artifact or proof of what is installed on the VPS.

| Mechanism / record | What the local evidence establishes | What it does not establish |
| --- | --- | --- |
| `deploy/hostinger/catalog/backup.sh` (ignored local file) | A manual PostgreSQL dump piped through gzip to a local directory; `umask 077`; default 14-day deletion of older matching files. | It backs up the database volume only, not `catalog-asset-data`; it has no `pipefail`, dump validation, checksum/restore verification, off-host copy, or timer installation. A `pg_dump` failure may be hidden by successful `gzip`. The ignored operator notes say not to enable it unchanged. It was not run during this audit. |
| Hostinger VPS backup list (read-only account API, refreshed 2026-09-24) | Two provider VPS backup points are listed: `52757820` (2026-09-19 11:10:29 UTC) and `51894425` (2026-09-12 14:15:16 UTC). A current snapshot was not present. | Neither is the fresh pre-062 provider recovery point. The API listing does not prove restore; provider restore replaces the whole VPS. A fresh point requires separate owner approval. |
| Hostinger backup notes in ignored `internal/infra/vps/deployment/MIGRATION.md` | The owner accepted a weekly-backup policy on 2026-09-06. The historical hPanel check reported no completed automatic backups and a manual snapshot at 2026-09-06 01:10, expiring 2026-09-07. | This older note predates the two backup points now listed by the read-only account API. It remains evidence only of the earlier state; it does not test provider restore. |
| Historical stopped-writer export and restore | The ignored migration record reports a 2026-09-06 final database-and-assets bundle restored into fresh volumes: schema 034, 29 tables, 1,305 rows, asset hash/count checks, and native API checks passed. The earlier isolated rehearsal also passed at schema 034 with 29 tables and 1,303 rows. | These are historical logical restore results, not a Hostinger full-VPS backup restore and not a recovery point for the current schema through 061 or a future 062. The record said the final bundle was retained root-only at that time; its present availability was not verified. |
| `restore-final-data.py` and its tests (ignored local operator material) | The one-time restore code verifies outer/member hashes and exact table counts, refuses existing destination volumes, and starts API only; its offline tests check refusal/preflight behavior without Docker. The historical migration record reports a successful execution. | The script is pinned to a historical schema-034 cutover and is not a general current-production/062 restore command. Offline refusal tests alone do not prove that a current backup can be restored. |
| `internal/backups/beta11-*` | Local Git bundles and working-tree patches exist as source/repository recovery material. | They are not PostgreSQL or asset-volume backups. |

The pre-062 gate requires both a fresh Hostinger whole-VPS recovery point and a
fresh VPS-local PostgreSQL custom-format dump successfully restored into a
separate PostgreSQL 16 instance. The logical dump validates database restore
capability; it is not protection from VPS/disk loss. Mac is not part of this
recovery path. The historical schema-034 restore and PGlite migration tests
are not substitutes for either current recovery gate. See
[`production-db-recovery.md`](production-db-recovery.md) for the future
procedure; none of it was executed for this audit.

## Confirmed starting state

The complete `tools/installation-statistics-schema-preflight.sql` ran as one
audit in a PostgreSQL `READ ONLY` transaction (`transaction_read_only = on`),
then ended with `ROLLBACK`. It inspected `terento_catalog`, schema `public`, on
PostgreSQL 16.15. Of 25 expected relation objects, 24 matched; the missing
relation is `statistics_exclusion_audit`. The ledger contains entries through
061, but has no SQL content hashes, so version marks alone do not prove schema
parity.

Confirmed live drift:

| Area | Expected before 062 | Confirmed live state |
| --- | --- | --- |
| `compatibility_evidence_event` | Three nullable text fields | All three absent: `statistics_exclusion_code`, `statistics_exclusion_reason`, `security_issue_code` |
| `map_download_event` | Nullable integer result index and three nullable text fields | All four absent: `map_result_index`, plus the three exclusion/security fields |
| `statistics_exclusion_audit` | Table with bigint identity PK, stream CHECK, unique key, and lookup index | Relation absent, so its table constraints and index are absent too |
| Event indexes | One exclusion index on each event table | Both absent |
| `compatibility_model_statistics` | Current result grouping plus exclusion filter | View exists with the expected 29-column output signature, but without the exclusion filter |
| Migration history | 060 and 061 present; 062 absent | Versions through 061; 062 not recorded |

The exact current database counts and schema fingerprint must be refreshed by
the precheck at the time of a future approved run. Historical
`map_download_event.map_result_index` values must remain NULL; 062 contains no
backfill, identity inference, or event-row DML.

## Static audit of 062

`src/terento_catalog/migrations/062_reconcile_installation_statistics_schema.sql`
contains seven SQL statements:

| # | Statement | Classification | Event data mutation |
| --- | --- | --- | --- |
| 1 | `ALTER TABLE compatibility_evidence_event ADD COLUMN IF NOT EXISTS ...` | Additive DDL | None |
| 2 | `ALTER TABLE map_download_event ADD COLUMN IF NOT EXISTS ...` | Additive DDL; `map_result_index` has no default and is nullable | None |
| 3 | `CREATE TABLE IF NOT EXISTS statistics_exclusion_audit ...` | Additive DDL, including PK/CHECK/UNIQUE | None |
| 4 | Create compatibility exclusion index | Additive DDL | None |
| 5 | Create map exclusion index | Additive DDL | None |
| 6 | Create audit event lookup index | Additive DDL | None |
| 7 | `CREATE OR REPLACE VIEW compatibility_model_statistics ...` | View replacement DDL | No event-row mutation |

There is no row-level `UPDATE`, `DELETE`, `INSERT`, or `TRUNCATE` statement.
The replacement view has the same 29 column names, order, and types
as the existing view; its intended semantic change is to filter rows with a
server-classified `statistics_exclusion_code`. PGlite tests compare both the
view signature and the post-migration exclusion behavior.

The PostgreSQL driver context in `Database.connection()` commits on normal
context exit and rolls back on an exception. `apply_migrations()` executes all
SQL statements and its `schema_migrations` insert inside that one connection
context. Therefore a failed migration transaction rolls back 062's DDL and
ledger entry together. Both the local CLI and the fixed root-owned migration
helper invoke the runner with explicit `--target 062`. The runner validates
the exact local file set and ledger; the helper independently audits the image
inventory and byte hashes before invoking only the 062 one-shot. The precheck
must show every image migration 001–061 applied and 062 absent, and the pinned
image must contain exactly canonical migration files 001–062 with no
later/unreviewed files.

## Pre-migration check

Use the SELECT-only file
[`../tools/installation-statistics-062-live-precheck.sql`](../tools/installation-statistics-062-live-precheck.sql)
against the exact target database. In the verified PostgreSQL session, run:

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
SHOW transaction_read_only;
```

Require `on`, then execute the full precheck file. It returns `READY FOR 062`
only when the target, ledger, expected-before drift, free object names, and
29-column view signature match. Any `ABORT 062`, SQL error, missing baseline
output, or unexpected object is a hard stop. Record the exact event counts,
server version, schema/search-path metadata, view-definition MD5, and all 29
view columns. Finish with `ROLLBACK;`.

The file reports both event row counts and the number of existing map rows
expected to receive NULL when the nullable/no-default column is added. Exact
pre/post count equality requires no ingestion or retention writes during the
measurement window. If the live API or retention task remains active, a count
delta must be attributed to specific legitimate concurrent activity; never
assume that a mismatch was harmless.

`READY FOR 062` is a schema-state result only. It is not permission to run the
migration and does not replace image, target, backup, or execution-path checks.

## Execution procedure — candidate source prepared, production gate blocked

This is the gate order for a future separately authorized run. The command
implementations are included in the candidate source; no root helper has been
installed and no new SSH entry point is active. The command
examples describe the reviewed source protocol, not currently executable VPS
commands. Do not invoke Docker or the migrator directly.

### Step 0 — production status (blocked)

The prepared root-helper command is `terento-deploy api status`. It reports
existing API/scheduler/database container and image identity, state, start
time, database/schema/PostgreSQL version, migration ledger, timestamp and
timezone, plus optional cached immutable candidate identity. Its SQL is fixed
inside an explicit read-only transaction; it does not call `/health`, pull an
image, or mutate files/services. The helper and status command are not
installed, so do not run this as a production command yet. Current local
source `GET /health` checks DB readiness only; retention runs in the existing
scheduler once per configured collector cycle. The local default is daily at
03:00 UTC, but the production `COLLECTOR_SCHEDULE_UTC` override has not been
verified; the up-to-24-hour cleanup lag assumes the deployed schedule is daily.

### Step 1 — two recovery layers (not ready)

The newest listed Hostinger recovery point is backup `52757820` from
2026-09-19 11:10:29 UTC; the 2026-09-24 snapshot API response has no usable
snapshot. Neither listed backup is the fresh pre-062 provider point. Obtain
separate owner approval to create a fresh Hostinger recovery point and record
its exact ID/timestamp, accepted RPO and whole-VPS restore impact. Also obtain
separate owner approval for a VPS-local `pg_dump -Fc` and isolated PostgreSQL
16 restore validation. Both must pass; a VPS-local dump alone is not protection
from VPS/disk loss. Do not create a snapshot, backup or restore anything as
part of this runbook. See [`production-db-recovery.md`](production-db-recovery.md).

### Step 2 — SELECT-only precheck

Run the following SQL gate only after a separately authorized, correctly
identified database session is available:

1. Run the exact precheck below inside `REPEATABLE READ READ ONLY` and require
   `READY FOR 062`.
2. Preserve the exact event counts and 29-column view signature as the
   postcheck baseline. Any other result is STOP.

### Step 3 — migration-only (source prepared; install and approval blocked)

The prepared syntax is `terento-deploy api migrate --target 062 --image
sha256:<digest> --revision <40-hex> --expected-migration-062-sha256 <64-hex>
--expected-migrate-py-sha256 <64-hex>`. It validates the immutable image,
prints candidate identity and hashes before execution, checks a strict ledger,
and invokes only the one-shot migration service. It shares the deploy lock.
The image must contain exactly canonical migrations 001–062; any 063+ file is
reported by name and rejected before migration. The helper and SSH template
are not installed, so this is not a currently executable VPS command. Never
use generic DEPLOY or ad-hoc Docker/Compose as a substitute.

### Step 4 — SELECT-only postcheck

After a future successful migration-only result of exactly `062`, run the exact
postcheck below read-only using the Step 2 count baselines. Require
`POSTCHECK PASS 062`; otherwise STOP and do not deploy.

### Step 5 — status comparison (blocked)

After its separately authorized installation, use the fixed read-only status
action described in the operations protocol. Require unchanged API/scheduler
container IDs, immutable image digests, revisions, start times, and running
states, and only the database ledger/schema state to have advanced from 061 to
062. STATUS does not call a health endpoint or perform a health check, so do
not treat it as a health probe. The local implementation is not installed, so
this comparison is not currently available through a supported operator route.

Before a future separate approval, the operator must be able to record:

1. The exact target database and current schema/migration snapshot metadata
   from the precheck. The snapshot records database/schema, PostgreSQL version,
   read-only/search-path state, event counts, view-definition MD5, and all 29
   view columns/types.
2. The currently running API image digest and OCI revision through the prepared
   fixed read-only status operation, after its separately authorized
   installation. The current SSH boundary remains deploy-only, and the local
   helper source is not installed.
3. The immutable candidate API image digest and source revision containing the
   reviewed 062 file, plus the SHA-256 of that exact file. Verify the image's
   migration directory and confirm no pending migration other than 062 can
   run. The immutable receipt must be from the exact reviewed candidate SHA.
4. Both recovery gates: a fresh Hostinger whole-VPS point with the exact ID,
   timestamp, accepted RPO and full-restore impact; and a fresh VPS-local
   PostgreSQL custom-format dump restored successfully into an isolated
   PostgreSQL 16 target. Last observed `pg_dump` was 16.15 inside the DB
   container; host `pg_dump` is absent. `pg_restore`, container/image identity,
   secure credential source, root-only destination, free space and isolated
   restore image remain to be verified in the VPS shell. No backup or restore
   was performed. Both actions require separate owner approval.
5. A fixed, root-owned migration-only invocation that passes
   `terento-catalog-migrate --target 062` using the reviewed image, existing
   private DB network/configuration, and `catalog-migrate` service; validates
   the same image source/revision as deployment; serializes against API
   deployment; and does **not** replace or restart API/scheduler services.

The existing `deploy <digest> <commit>` is now a distinct service-only step;
the prepared helper never starts a migration container during DEPLOY. It
requires candidate inventory and live ledger to match exactly at 001–062, and
refuses 063+ candidates until a later reviewed gate is implemented. API
deployment is manual-only and requires the
`target_062_separately_applied=true` input plus
`TERENTO_FIXED_OPS_INSTALLED=true`; migration-source commits are excluded as
an additional guard. The helper also requires valid SQL/runner labels and
performs a read-only schema gate before any app service change. These
safeguards are local and not yet installed. The helper,
installer, candidate workflow, SSH template if required, and regressions must
be tracked/committed, tested, installed, and independently verified before a
separate migration approval. Do not substitute direct `docker compose run`, an
ad-hoc shell/Python command, or manual replay of SQL.

Once that gate is separately satisfied, the invocation must use the standard
migration runner against a pinned image and, after a read-only ledger
postcondition verifies exactly 001–062, report:

```text
Applied migrations: 062
```

Any nonzero exit, output of `none`, or version other than exactly `062` is a
STOP. The runner is transactional; after an uncertain SSH/session outcome,
inspect the ledger and schema with the read-only postcheck before considering a
retry. Never replay 060/061.

## Post-migration check

Use the SELECT-only file
[`../tools/installation-statistics-062-live-postcheck.sql`](../tools/installation-statistics-062-live-postcheck.sql).
First replace its two typed NULL baseline values with the exact
`compatibility_event_rows_before` and `map_event_rows_before` captured by the
precheck. In the verified database session, run it inside
`BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY` / `ROLLBACK` and require
`transaction_read_only = on`.

`POSTCHECK PASS 062` requires all of the following:

- migration 062 appears exactly once; no later migration is present;
- all seven columns have the expected types, remain nullable, and have no
  defaults (especially `map_result_index INTEGER NULL`);
- the audit relation is a plain table with exactly the expected eight columns,
  order, types, nullability, and defaults; its exact PK, stream CHECK, unique
  constraint, and all five expected valid indexes are present;
- the view still has exactly 29 agreed column names/order/types and its
  definition contains the exclusion filter and result-index grouping;
- compatibility/map event counts equal the saved baselines;
- every current map event has NULL `map_result_index`; and
- the new audit table is empty.

Any SQL error, changed view signature, non-NULL historical map index,
unexplained row-count delta, missing/invalid index or constraint, or failed
gate is `ABORT POSTCHECK`; do not deploy the backend.

## Failure and recovery

- If the runner exits nonzero before commit, its connection transaction must
  roll back all 062 statements and its ledger insert. Leave the old backend in
  place. Do not blindly retry; run the SELECT-only precheck again and inspect
  the error/ledger first.
- If output or connection loss leaves commit status uncertain, use the
  postcheck. Do not repeat migration SQL manually.
- If 062 commits but a later backend deployment fails, retain the additive
  schema and run the old backend. Do not automatically `DROP` columns, indexes,
  table, or revert the view. Recovery is forward-only: diagnose, correct the
  candidate backend/migration in a new reviewed change, then validate again.
- Backward-compatibility audit: new columns are nullable/no-default; old event
  inserts name their columns explicitly; old health checks select established
  columns; the new audit table is unused by old code; and the view keeps the
  old 29-column signature. Thus the old backend can continue reading/writing
  through this additive schema, subject to the normal database backup and
  restore gate.

## Later backend deployment gate (not part of this procedure)

Only after 062 postcheck PASS and a separate deployment approval:

1. Validate service health using the reviewed deployment procedure. Current
   source `/health` checks DB readiness only and has no mutation side effect.
   Retention runs once daily in the existing scheduler with the same 24-month
   cutoff; deletion may lag by up to one day. This local fix has not been
   deployed.
2. Validate `GET /devices/installation-policy.json` returns HTTP 200,
   `Content-Type: application/json`, `Cache-Control: no-store`, valid
   `schemaVersion: 3`, and a valid live projection.
3. Derive live per-catalog-row counts from the response, not hard-coded
   historical totals. Recompute `APPROVED`, `BLOCKED`, and `PENDING` from each
   row's `active` and nullable `mapCapable` values. Verify representative
   Maps=Yes, Maps=No, Maps=NULL, and absent Edge cases; absent Edge is PENDING,
   not permanently unsupported.
4. Any 404, 5xx, invalid schema/header, stale projection, or capability/status
   mismatch is STOP APP RELEASE. Public Compatibility, install counts, and
   `support_status` do not override policy.

The current deploy workflow checks health, catalogs, policy schema v3 and
`Cache-Control: no-store`; this runbook does not perform that workflow or claim
the live endpoint has been validated after 062.

## Documentation tracking gate

The candidate receipt enumerates the normative paths that must be tracked at
the exact candidate commit. This includes the migration SQL and runner,
precheck/postcheck/runbook, installation authorization contract, root helper
and migration module, first-install-aware installer, SSH template when used,
build/deploy/publish workflows, operation tests and runner, and VPS recovery
procedure. Confirm the committed manifest and clean candidate checkout before
building; no required policy rule may exist only in ignored `internal/`
context. The immutable workflow receipt is the authoritative build/test result.

## Test receipt

Before the first-install change, the backend suite passed 546 tests with 2
skipped and the production-operations runner passed 11 installer tests among
its operations checks. Those earlier counts are historical and are superseded
by the exact candidate workflow run for the committed source. The focused
installer regression now exercises both existing-helper restoration and the
first-install `ABSENT` rollback case. Passing code/CI tests do not prove that a
production helper is installed, that a live backup was created, or that an
isolated restore was validated.
