# Production operations protocol

This document describes the canonical local source prepared for a future
production operations update. It does not assert that this source is committed,
installed, or available on the VPS. It grants no approval to change production.

## Three separate operations

### STATUS — read-only

The root helper supports:

```sh
terento-deploy api status
```

An optional candidate receipt can be checked without pulling or running it:

```sh
terento-deploy api status \
  --candidate-digest sha256:<64-lowercase-hex> \
  --candidate-revision <40-lowercase-hex> \
  --expected-migration-062-sha256 <64-lowercase-hex>
```

Status reads Docker's existing API, scheduler, and database containers; reports
validated immutable image digests, revisions, start times and states; reads
database identity/version/ledger/timezone through a fixed SQL statement in an
explicit `READ ONLY` transaction; and inspects the local image cache for the
candidate. It neither pulls candidate images nor invokes Compose health checks,
the HTTP `/health` route, retention, a migration, or service mutation. It
redacts database credentials and reports unavailable data as status enums.
An uncached candidate is informational (`not_cached`), not evidence of its
contents. Re-run after it is present in the local registry cache if artifact
inspection is required.

### MIGRATE — exactly target 062, no service deployment

The fixed root helper accepts only:

```sh
terento-deploy api migrate \
  --target 062 \
  --image sha256:<64-lowercase-hex> \
  --revision <40-lowercase-hex> \
  --expected-migration-062-sha256 <64-lowercase-hex> \
  --expected-migrate-py-sha256 <64-lowercase-hex>
```

The repository and image name are fixed in code; callers provide only the
immutable digest, full source revision, and receipt hashes. The helper pulls
only `ghcr.io/vooz2/terento-catalog@sha256:…`, verifies that exact RepoDigest,
OCI source/revision labels, SQL and runner labels, then starts a disposable
`--network none`, read-only audit container with no added capabilities. That
audit hashes the actual image files and statically verifies the runner's sole
target choice, inventory branch, ledger branch, and call site. Before execution
the helper prints the image digest, revision, 062 SQL hash, runner hash, target
guard result, and inventory. It then checks that the existing, correctly
identified DB container is already running and reads its migration ledger in a
read-only transaction.

For this reviewed implementation, the artifact must contain exactly one
canonical SQL migration for each version 001–062. A later file such as
`063_example.sql` is named to the operator and causes a fail-closed refusal
before the ledger query or migration container runs. This is stricter than
necessary if a future runner can prove target isolation with later files, but
must not be relaxed without adding artifact-level proof and regression tests.
The root CLI preserves this validated refusal detail for the operator; it does
not hide the later filename only in server logs.
The live ledger must be exactly 001–061; exactly 001–062 yields an explicit
`ALREADY APPLIED` no-op; any gap, alias, earlier version, or later entry is an
abort. After a successful runner result the helper re-identifies the same DB
container and verifies the exact 001–062 ledger in a fresh read-only
transaction before reporting `MIGRATION_PASS`. A failed postcondition is a
nonzero refusal, even if the runner printed success.

Only the Compose `catalog-migrate --target 062` one-shot is invoked. No API or
scheduler container is started, stopped, recreated, or health-checked by this
path. SQL statements and the `schema_migrations` insert share one PostgreSQL
transaction; failure rolls both back and returns nonzero. The helper does not
perform automatic schema downgrade or replay.

### DEPLOY — separate service replacement path

The existing deploy command remains:

```sh
terento-deploy api sha256:<64-lowercase-hex> <40-lowercase-hex>
```

It is not the migration-only command. Deployment uses the same non-blocking
operations lock and retains its own pre-existing Compose/service behavior. The
API deploy workflow excludes pushes that change migration files or
`migrate.py`; unknown push ancestry is fail-closed. More broadly, API deploy is
manual-only: dispatch requires an explicit `target_062_separately_applied`
boolean (default false) and the owner-controlled repository variable
`TERENTO_FIXED_OPS_INSTALLED=true`. This variable is not set by this task and
must only be enabled after the new helper is installed and verified. The
helper requires valid migration SQL/runner labels, verifies the exact
immutable image's migration set and target-062 runner, and refuses deployment
unless a read-only ledger check confirms exactly 001–062 are already applied.
DEPLOY does not start the database or run a migrator; it only replaces
application/scheduler services after the schema gate passes. Images with
migration 063+ or ledgers with any pending/later version fail closed until a
separate reviewed migration gate is implemented. Future deployments remain
separately gated by release checks and operator authorization.

Deploy and migrate both use `/var/lib/terento/deployment/operations.lock` for
the full operation and refuse rather than wait if another mutation holds it.
Status does not acquire the lock because all of its operations are read-only.
This lock is shared only by the new helper version; an older installed helper
may not honor it. Before installing/updating the helper, the owner must ensure
all old helper and deployment activity is quiescent.

## Installation boundary and current state

Canonical local sources are:

- `scripts/infra/terento-deploy.py` — root-owned fixed helper, status and
  operation dispatch;
- `scripts/infra/terento-deploy-migration.py` — image verification and
  migration-only operation;
- `scripts/infra/install-terento-production-ops.py` — owner-run read-only
  preflight by default; a separate explicit apply installs only those two
  helper files from a clean, committed checkout;
- `scripts/infra/terento-deploy-ssh-entry.py.in` — fixed SSH command template
  for API status/migrate and existing deploy dispatch; not installed by the
  current helper installer;
- `scripts/infra/test-terento-deploy.py`,
  `scripts/infra/test-terento-deploy-migration.py`,
  `scripts/infra/test-terento-deploy-ssh-entry.py`, and
  `scripts/infra/test-install-terento-production-ops.py` — offline regressions.

The forced-SSH template is source/test coverage only. The existing SSH entry
point remains unchanged until a separately reviewed/authorized configuration
update installs it and the corresponding sudo allowlist. Do not claim remote
status or migration access until that independent step is complete. The direct
root command above likewise does not exist on the VPS until the helper pair is
installed.

The owner installer verifies clean Git state, both tracked canonical paths,
the full commit id, AST parseability, root-owned safe destinations, and the
shared lock. The migration-module destination may be absent on first install;
its parent must already exist and be secure. Before replacing either file,
apply creates `/var/lib/terento/deployment/<UTC timestamp>-<source SHA>/` as
`root:root` mode `0700`. The root-only manifest records each target as
`PRESENT` (backup bytes, SHA-256, owner/group and mode) or `ABSENT`; backup
files and manifest are `root:root` mode `0600`. The installer stages
same-directory root-owned mode-0755 files, replaces the migration module
first and executable helper last, and prints the rollback ID before the first
replacement. Each rename is atomic; the pair is not one filesystem
transaction. If a caught install step fails, the installer attempts to roll
back automatically and reports whether that completed; the saved rollback ID
remains usable for explicit recovery. A crash or power loss can still interrupt
between renames, so inspect the target hashes and use the recorded rollback
procedure rather than assuming either complete state. The installer never
calls Docker, Compose, systemd, SQL, or deployment commands. Apply changes
production helper files and has not been run. Because the old helper may not
share the new lock, the owner must separately authorize and schedule a
quiescent install.

If rollback is required, use the clean committed installer from the recorded
source revision with:

```sh
python3 scripts/infra/install-terento-production-ops.py \
  --rollback <recorded-rollback-id> \
  --confirm-production-helper-rollback
```

Rollback verifies the saved bytes and current installed hashes before changing
either target. It restores prior bytes/owner/mode atomically, or removes the
migration helper if its recorded pre-install state was `ABSENT`. Unexpected
post-install file changes fail closed. The rollback record is retained for
operator review; cleanup needs a separate decision. Do not change the existing
`/usr/local/bin/terento-ops-entry` forced-command entrypoint. After a future
authorized install, run only `terento-deploy api status`; do not run MIGRATE or
DEPLOY as part of install validation.

## Required future gate order for target 062

1. Track, commit, and test every normative source path listed in the
   [candidate receipt](production-candidate-receipt.md). Build only from a
   clean exact commit using the manual `build-catalog-migration-candidate`
   workflow. The receipt is evidence, not approval.
2. Separately authorize installation of the helper pair; if remote SSH
   invocation is required, separately review/install the SSH template and
   sudo policy. Capture helper source hashes and prove the actual installed
   version.
3. Resolve/accept both recovery layers: a fresh Hostinger VPS backup/snapshot
   for off-host disaster recovery and a fresh PostgreSQL-only dump stored
   root-only on the VPS whose checksum and isolated PostgreSQL 16 restore are
   validated. A VPS-local logical dump alone is not protection against VPS or
   disk loss.
4. Run read-only STATUS; independently confirm the correct DB, API/scheduler
   image identity, ledger, and target environment. Do not use `/health` as the
   status command.
5. Run the SELECT-only live 062 precheck and require `READY FOR 062`.
6. Obtain a separate explicit approval for the exact immutable digest,
   revision, SQL SHA, runner SHA, target 062, and selected recovery point.
7. Invoke MIGRATE only. Require the helper's postcondition-verified
   `Applied migrations: 062` or a confirmed `ALREADY APPLIED` no-op. Any
   mismatch, nonzero result, lost session, unexpected target or ledger is STOP;
   resolve with read-only checks, never manual SQL replay.
8. Run the SELECT-only postcheck and require `POSTCHECK PASS 062`. Confirm
   STATUS shows API and scheduler unchanged and only the DB schema/ledger
   advanced.
9. A backend DEPLOY is a later, separate operation and requires its own
   approval after postcheck PASS. Migration success does not deploy the app.

No step above was executed against production as part of preparing this source.
