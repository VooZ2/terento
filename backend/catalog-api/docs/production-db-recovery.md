# Production PostgreSQL recovery procedure

## Status and observed facts

**Future procedure only — not executed.** No production backup was created,
copied, or verified, and no restore validation was performed. No production
database or service command was run for this document. These steps do not
authorize a migration, deployment, restore, or other production change.

The operator-reported read-only terminal findings for 2026-09-23 are:

| Check | Observation | Meaning / limit |
| --- | --- | --- |
| Host `pg_dump --version` | `command not found` | A host client is not currently available. |
| `docker exec terento-catalog-catalog-db-1 pg_dump --version` | PostgreSQL 16.15 | This establishes the container `pg_dump` client version only; it is not the server version, a dump, or a restore test. |
| `pg_restore` availability/version | Not checked | Safari had switched to a non-terminal window after the `pg_dump` checks; no `pg_restore --version` command was run. Verify it before any TOC check or restore. |
| PostgreSQL server version and database identity | Not checked during the terminal check described here; no additional server command was run | The earlier 062 runbook contains historical preflight values (`16.15`, `terento_catalog`, schema `public`); they were not refreshed or corroborated in this check and must be re-verified at execution time. |
| Hostinger VPS API inventory (2026-09-23) | VPS `1958677` (`rukas.terento.app`) reported `running`; details report a 100 GiB plan disk | This is control-plane metadata only; it does not establish free filesystem space or DB-container state. |
| Hostinger Docker Manager project inventory (2026-09-23) | Unavailable: API reports that the installed operating system does not support Docker Manager | No container/project inventory, mount, image, or DB-container capability fact was verified through this API. Use an authenticated VPS shell and narrow read-only checks before any backup operation. |
| Hostinger backups (refreshed 2026-09-23) | `52757820` from 2026-09-19 11:10:29 UTC and `51894425` from 2026-09-12 14:15:16 UTC | The live Hostinger API still lists only these old whole-VPS points; they are not accepted fresh database recovery points for a later migration. |
| Hostinger snapshot (2026-09-23) | Snapshot endpoint returned ID `0` and no usable snapshot | No current snapshot was confirmed. |
| Database-only backup / isolated restore | None performed | Do not claim a backup exists or is verified. |

This record is supplemental to the [062 live runbook](installation-statistics-062-live-runbook.md).

## Preconditions before a future backup

1. Obtain separate authorization for the backup window and confirm the exact
   production VPS, Docker DB container ID/image, active database, and database
   role using narrow read-only queries. Do not infer identity from a container
   name alone.
2. Confirm the exact PostgreSQL server version and both container client
   versions (`pg_dump` and `pg_restore`) before using either client. The dump
   client must not be older than the server major version. Verify that
   `pg_restore` exists and record its version before `pg_restore --list` or any
   restore; use the same major version as the archive producer, preferably the
   exact same minor version. Stop on a mismatch or if either client is absent.
3. Use a database credential path that is already provisioned and protected,
   such as an approved Unix-socket authentication path or a mounted
   `PGPASSFILE` readable only by the dump process. Never put a password in a
   command argument, URL, pasted SQL, shell history, terminal output, or this
   repository. Use `--no-password` so a batch command fails closed instead of
   prompting. Do not print container environment, `docker inspect` environment,
   Compose-expanded configuration, or secret-file contents. PostgreSQL's
   password-file permission requirement is documented in its
   [password-file documentation](https://www.postgresql.org/docs/16/libpq-pgpass.html).
4. Confirm an approved **encrypted-at-rest** destination and enough free space
   for the encrypted archive, temporary validation material, and metadata.
   Root-only file permissions are necessary but are not encryption. No
   encryption recipient, key path, or independent off-host destination has
   been established by this task. If those are unavailable, stop; do not leave
   an unencrypted dump on the VPS and call it a secure recovery point.
5. Decide the acceptable recovery point and RPO. `pg_dump` produces a
   transaction-consistent snapshot while the database is in use, but it cannot
   recover writes committed after that snapshot. If the required RPO excludes
   that interval, arrange a separately approved write freeze and record its
   start/end; do not stop application services ad hoc.
6. Treat the archive as sensitive production data. Keep its directory private,
   avoid row contents and SQL text in the operator receipt, and transfer an
   accepted recovery copy only to a separately approved encrypted off-host
   destination over an authenticated channel. A copy left only on this VPS
   cannot recover from loss of that VPS or its disk.

`pg_dump` reads one database; it does not include cluster-wide role definitions
or tablespace definitions. The archive should retain database object ownership
and ACL metadata; do not use `--no-owner` or `--no-acl` when creating it. Global
role passwords and other secrets must not be added to this database-only
backup. If the database refers to non-default tablespaces, record and reproduce
their mapping in the isolated clone or stop the restore test.
See the [PostgreSQL 16 `pg_dump` documentation](https://www.postgresql.org/docs/16/app-pgdump.html).

## Future backup sequence

The following are command patterns, not commands run or approved for immediate
execution. Replace only non-secret placeholders after the preconditions above
have passed. Do not enable shell tracing (`set -x`).

### 1. Capture narrow identity and version metadata

Use the exact container name already supplied by the read-only inventory, then
capture its immutable container/image identifiers without printing its
environment. Reconfirm the database identity and server version through the
approved credential path:

```sh
DB_CONTAINER=terento-catalog-catalog-db-1

docker inspect --format '{{.Id}} {{.Image}}' "$DB_CONTAINER"
docker exec "$DB_CONTAINER" pg_dump --version
docker exec "$DB_CONTAINER" pg_restore --version

# PGPASSFILE must name an already-mounted, protected file; the path is not a
# password. If no such credential path is configured, stop rather than inline
# or print credentials.
docker exec \
  --user postgres \
  --env PGPASSFILE=/approved/mounted/path/catalog.pgpass \
  -i "$DB_CONTAINER" sh -eu -s <<'IN_CONTAINER'
test -r "$PGPASSFILE"
psql -X --no-password -At \
  --username="$POSTGRES_USER" --dbname="$POSTGRES_DB" \
  --command="SELECT current_database(), current_user, current_schema(), current_setting('server_version');"
IN_CONTAINER
```

Record the query's database/role/server-version result privately. Confirm it
matches the intended production database. The `docker inspect` format above
intentionally selects only container and image IDs; never replace it with an
unfiltered `docker inspect` or `docker compose config` dump.

### 2. Create, validate, and atomically publish the archive

Use a root-owned directory on the already-confirmed encrypted filesystem. The
staging directory and final bundle must be on the same filesystem. Keep the
entire operation under a separately reviewed maintenance/backup lock so two
operators cannot publish the same timestamp. Do not automatically delete older
recovery points.

```sh
set -euo pipefail
umask 077

BACKUP_ROOT=/approved/encrypted/backup/path/terento-catalog
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
install -d -o root -g root -m 0700 "$BACKUP_ROOT"
STAGE=$(mktemp -d "$BACKUP_ROOT/.stage-${STAMP}.XXXXXX")
chmod 0700 "$STAGE"
FINAL="$BACKUP_ROOT/$STAMP"
test ! -e "$FINAL"

# This writes a single-database custom-format dump to the encrypted staging
# filesystem. PGPASSFILE must already be mounted and readable by the postgres
# OS user inside this container. The command fails instead of prompting.
docker exec \
  --user postgres \
  --env PGPASSFILE=/approved/mounted/path/catalog.pgpass \
  "$DB_CONTAINER" sh -eu -c '
    test -r "$PGPASSFILE"
    exec pg_dump --no-password --format=custom --lock-wait-timeout=30s \
      --username="$POSTGRES_USER" --dbname="$POSTGRES_DB"
  ' > "$STAGE/catalog.dump.partial"

test -s "$STAGE/catalog.dump.partial"
chmod 0600 "$STAGE/catalog.dump.partial"

# Parse the archive TOC with the PostgreSQL container client; suppress object
# names from terminal output. This is a structural check, not a restore test.
docker exec -i "$DB_CONTAINER" pg_restore --list - \
  < "$STAGE/catalog.dump.partial" > /dev/null

mv -- "$STAGE/catalog.dump.partial" "$STAGE/catalog.dump"
sha256sum "$STAGE/catalog.dump" > "$STAGE/SHA256SUMS"
chmod 0600 "$STAGE/SHA256SUMS"
stat -c '%s bytes; mode=%a; owner=%U:%G' "$STAGE/catalog.dump"
```

Before continuing, write a root-only `manifest.txt` in `STAGE` with only:

- UTC start/end timestamps;
- VPS identifier and exact DB container ID/image ID or immutable image digest;
- `current_database()`, `current_user`, schema, server version, `pg_dump`, and
  `pg_restore` versions;
- archive format, byte size, SHA-256, file mode, owner/group, and encrypted
  storage destination identifier;
- the accepted recovery point/RPO and operator identity;
- the dump and archive-list check exit statuses.

Do not include credentials, environment dumps, table rows, raw SQL, or full
diagnostic output. Confirm the archive checksum, mode `0600`, owner `root:root`,
and stage directory mode `0700`. Then atomically publish the complete bundle
with a same-filesystem directory rename, only if `FINAL` is still absent:

```sh
test ! -e "$FINAL"
mv -T -- "$STAGE" "$FINAL"
```

An incomplete staging directory is never a backup. A successful rename only
proves atomic publication on that filesystem; it does not prove recoverability.
Keep the encrypted local bundle until an independently stored copy has been
transferred and its SHA-256 rechecked. Do not label the backup verified until
the isolated restore below succeeds and its evidence is recorded.

If the approved encrypted destination requires client-side encryption instead
of encrypted filesystem storage, the dump stream must pass through a separately
installed and reviewed encryptor using only an approved recipient key. That
encryptor and key are not currently identified; do not invent a command or
write plaintext to disk while waiting for one. Decrypt only into a protected,
short-lived scratch area for validation.

## Isolated restore validation

Run only after a backup has been created in a separate, approved operation.
Prefer a disposable lab host. If an owner separately approves using the
production VPS for the rehearsal, first confirm that disk, memory, and CPU
headroom are adequate; the rehearsal itself must remain disconnected from
production services and networks.

1. Verify the published bundle's SHA-256 before decrypting or mounting it. Use
   a fresh scratch directory with mode `0700` on encrypted storage or a
   sufficiently sized protected temporary filesystem. Never overwrite the
   published archive during validation.
2. Start one uniquely named throwaway PostgreSQL container from an immutable
   image digest matching the source PostgreSQL major version and required
   extensions. Give it a new private data directory on a sufficiently sized
   protected tmpfs (or an approved encrypted scratch volume). Set Docker
   network mode to `none`, publish no ports, mount only the archive read-only,
   and do not attach the production DB data volume, production Docker network,
   production Compose project, or production environment files. Confirm these
   properties from narrow `docker inspect` fields before restore. This is a
   template only; fill each placeholder from separately verified local state:

   ```sh
   RESTORE_CONTAINER=terento-restore-check-__UNIQUE_SUFFIX__
   RESTORE_ARCHIVE=/protected/scratch/__REPLACE_WITH_ARCHIVE_PATH__
   PGDATA_TMPFS_SIZE=__REPLACE_WITH_MEASURED_SIZE__
   APPROVED_POSTGRES_IMAGE=__REPLACE_WITH_APPROVED_IMAGE_DIGEST__

   docker run --pull=never --detach --name "$RESTORE_CONTAINER" \
     --network none \
     --tmpfs "/var/lib/postgresql/data:rw,noexec,nosuid,size=$PGDATA_TMPFS_SIZE" \
     --mount "type=bind,src=$RESTORE_ARCHIVE,dst=/restore/catalog.dump,readonly" \
     --env POSTGRES_HOST_AUTH_METHOD=trust \
     "$APPROVED_POSTGRES_IMAGE"
   ```

   The `__REPLACE_...__` values are deliberately non-runnable placeholders. Do
   not use them literally or select an unverified image. `trust` applies only to
   this isolated container under the network/mount restrictions above.
3. If archive decryption is needed, decrypt only into the protected scratch
   area and verify its SHA-256 against the recorded plaintext checksum, if one
   was recorded. Keep private keys out of command arguments, logs, terminal
   output, and the repository. Remove the plaintext scratch copy after the
   test.
4. Initialize a fresh empty validation database from `template0`. A temporary
   `trust` authentication setting is acceptable only inside this one-off
   container while it has `network=none`, no published ports, no production
   mounts, and no other services; destroy that isolated instance after the
   test. Never change production authentication to `trust`.
5. A DB-only archive does not contain global roles. For a schema/data restore
   check, restore into the empty validation database with
   `pg_restore --exit-on-error --single-transaction --no-owner --no-acl` and
   explicitly record that this did not validate production role ownership or
   grants. For a fuller database-object check, create only the required role
   names as `NOLOGIN` roles in the isolated instance from a reviewed,
   secret-free role manifest, then restore without `--no-owner` or `--no-acl`.
   Do not add production role passwords or use a cluster-wide `pg_dumpall`.
6. Restore without `--clean` and without `--create` into the newly created
   scratch database. Use `--exit-on-error`; `--single-transaction` is preferred
   for an all-or-nothing test, and do not combine it with parallel jobs. For
   example, after verifying the exact throwaway container and archive paths:

   ```sh
   docker exec "$RESTORE_CONTAINER" \
     createdb --username=postgres --template=template0 terento_restore_validation

   docker exec "$RESTORE_CONTAINER" \
     pg_restore --username=postgres --exit-on-error --single-transaction \
       --no-owner --no-acl \
       --dbname=terento_restore_validation /restore/catalog.dump
   ```

   The second command performs a schema/data check only; use the reviewed
   `NOLOGIN`-role path in step 5 for ownership/ACL validation. Any failure means
   the restore validation failed; discard only that exact throwaway
   database/container and investigate. Never retry against a production
   database. PostgreSQL notes that restore executes SQL from the archive, which
   is another reason this clone must have no network or production mounts
   ([`pg_restore` documentation](https://www.postgresql.org/docs/16/app-pgrestore.html)).
7. On the restored clone, compare the source receipt with read-only results:
   server/encoding/collation, expected schemas and relation signatures, the
   complete `schema_migrations` ledger, selected table row counts recorded
   before the dump, and the target migration state. Do not print row data.
   Missing extensions/roles, count or schema mismatches, a different unexpected
   ledger, warnings indicating omitted objects, or incomplete output are a
   hard FAIL. Record exact client/server versions and pass/fail results.
8. Only after the checks pass, mark the recovery point **restore-tested** for
   the tested scope, not as a proof of PITR, cluster-global role recovery, or
   full-VPS recovery. Remove only the exact disposable container and scratch
   paths after confirming their recorded IDs/paths; retain the encrypted
   published archive and its receipt according to the approved retention
   policy.

`pg_dump` creates a consistent snapshot without blocking normal readers or
writers, but that does not stop later commits from occurring. Its output can
restore to the same or a newer PostgreSQL major, not reliably to an older one;
keep the isolated validation target on the same major and record its exact
version ([PostgreSQL 16 `pg_dump` documentation](https://www.postgresql.org/docs/16/app-pgdump.html)).

## Hard stop conditions

Stop without publishing or accepting a recovery point if any of these apply:

- production container/database/role identity is ambiguous or differs from the
  approved target;
- server or client version check fails, the dump client is older than the
  server major, or `pg_restore` is unavailable;
- no already-provisioned private credential path works with `--no-password`;
- encrypted-at-rest storage or the approved encryption/key path is unverified;
- insufficient disk/temporary capacity, dump timeout/error, empty archive,
  failed checksum/TOC parse, unsafe ownership/modes, or failed atomic rename;
- the isolated clone can reach production, has a published port, or uses any
  production data volume, environment file, or network;
- restore, schema/ledger comparison, or selected count validation fails;
- the backup exists only on the VPS but is being represented as protection
  against VPS/disk loss.

Do not suppress a failing command with `|| true`, accept a partial archive, or
infer success from file existence or size alone.

## Hostinger whole-VPS fallback

The two currently listed Hostinger points (2026-09-19 and 2026-09-12 UTC) are
not fresh accepted database recovery points for a later migration. A Hostinger
backup/snapshot restore is a last-resort whole-server rollback, not a
PostgreSQL-only restore: Hostinger warns that it overwrites the VPS's current
content and is irreversible, so data and configuration created after the
selected point can be lost; availability may also be affected while the VPS
is restored ([Hostinger VPS backup and restore guidance](https://www.hostinger.com/support/1583232-how-to-back-up-or-restore-a-vps-at-hostinger/)).
This can roll back application images, configuration, local files, and the
database together, potentially reintroducing an older or incompatible
application state. Refresh the available points, identify the exact point in
time, assess the full-VPS data-loss window, and obtain separate explicit
owner approval before any Hostinger restore. No Hostinger restore or test was
performed for this procedure.
