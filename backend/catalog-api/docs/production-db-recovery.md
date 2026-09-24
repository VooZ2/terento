# Production PostgreSQL recovery preparation

## Scope and current evidence

This document defines a future VPS-only PostgreSQL dump and isolated restore
check. No dump, restore, Hostinger snapshot, database write, migration, or
deployment was performed for this preparation. The Mac is not a backup or
restore target. A successful logical restore check is not off-host disaster
recovery; a fresh Hostinger VPS recovery point is also required before the
separately approved 062 operation.

Read-only observations available for this candidate:

| Check | Observation | Limit |
| --- | --- | --- |
| Hostinger VPS | `rukas.terento.app`, VPS `1958677`, running; Ubuntu 26.04 LTS, 100 GiB disk plan | Provider metadata does not prove container state or filesystem headroom. |
| Hostinger recovery points, refreshed 2026-09-24 | Weekly backups `52757820` (2026-09-19 11:10:29 UTC) and `51894425` (2026-09-12 14:15:16 UTC) | Neither is accepted as the fresh pre-062 recovery point. |
| Current Hostinger snapshot | API returned ID `0` with no usable timestamp | No current snapshot is available. |
| Hostinger Docker Manager API | Unsupported by the VPS operating system | Use the authenticated VPS shell for narrowly scoped, read-only Docker checks. |
| Production DB client, last shell observation 2026-09-23 | `pg_dump (PostgreSQL) 16.15` inside the existing DB container; host `pg_dump` unavailable | This was a version check, not a dump. `pg_restore --version`, current container/image identity, credential path, and restore image digest still need confirmation in the VPS shell. |
| Previous storage check, 2026-09-23 | `/var/backups` was on the same filesystem as the VPS root; approximately 87 GiB was free | Recheck at execution time. `/var/backups` is not the selected destination and is not evidence that `/var/lib/terento/backups` exists or is protected. |
| Database-only recovery | No archive or restore validation exists | Do not report PostgreSQL recovery as ready until an exact fresh archive is restored and checked. |

Hostinger's current guidance (updated one week before this check) says backups
are stored separately from the server; weekly backups are enabled by default,
daily backups may require an eligible paid option, and at most two daily plus
two weekly points are retained (each new point replaces the oldest in its
set). Backup or restore can take 10 minutes to a few hours. The VPS is locked
and cannot be managed during either action; availability/performance may vary,
but this does not say that the VPS is necessarily stopped. A manual snapshot
captures the whole VPS, only one is stored, a new one overwrites the previous
snapshot, and it expires after one day. Restore overwrites all current VPS
content, is irreversible/non-cancelable, and may roll back later data. Inspect
the live hPanel action summary before scheduling. No provider recovery point
was created here. See [Hostinger VPS backup and restore guidance](https://www.hostinger.com/support/1583232-how-to-back-up-or-restore-a-vps-at-hostinger/).

## Recovery gate

Before live 062, both conditions must be evidenced:

1. **HOSTINGER RECOVERY POINT READY** — a fresh provider backup/snapshot has
   completed, its exact ID and timestamp are recorded, and the owner has
   accepted its whole-VPS restore consequences and recovery window.
2. **POSTGRESQL RESTORE VALIDATED** — a fresh custom-format logical dump is
   stored root-only on the VPS and has restored successfully into a separate,
   temporary PostgreSQL 16 instance on that VPS. The archive remains available
   until 062 and the separately approved backend deployment are complete.

Normal schema problems use forward recovery; a logical DB failure uses the
validated `pg_dump`; loss/corruption of the VPS or its filesystem uses the
Hostinger recovery point. Do not attempt an automatic 062 downgrade.

Creating the Hostinger point, producing a production dump, and creating or
removing the temporary restore resources are external production operations.
They require a separate explicit owner authorization. The procedures below
are not run instructions for the current turn.

## Read-only preflight before an authorized backup

Using the authenticated VPS shell, re-confirm only the facts needed for this
run. Do not print container environment, Compose-expanded configuration,
secret files, credentials, database rows, or full `docker inspect` output.

- Identify the exact production DB container ID and immutable image ID/digest;
  confirm it is running and belongs to the expected Compose project.
- Read database identity, PostgreSQL server version, migration ledger and
  selected row counts through an explicit read-only transaction. Record only
  database/user/schema/version, counts, and migration versions.
- Confirm `pg_dump --version` and `pg_restore --version` inside the approved
  container. Both must be PostgreSQL 16 tooling compatible with the live
  server; stop if either is missing or mismatched.
- Verify an existing credential source that works with `--no-password`, such
  as a mounted, protected `PGPASSFILE` readable only to the dump process or an
  already-approved local socket-auth path. Never put a password in command
  arguments, a URL, shell history, SQL, logs, or this repository. Do not infer
  that container environment values are safe to print or relay.
- Recheck free space and mount identity. `/var/lib/terento/backups` must be
  on the intended VPS filesystem and have no symlink components. Create it
  only during the separately authorized backup operation, as `root:root`
  mode `0700`; archive and receipt files must be `root:root` mode `0600`.
- Confirm enough free space for the compressed custom archive, a second
  temporary restore database/volume, and normal production headroom. The
  restore target must use a separately verified PostgreSQL 16 image digest
  and required extensions.

If the credential source, container identity, versions, free space, or paths
cannot be verified without exposing secrets, stop. A database name or count
is not a secret, but no row values or identifying device data belong in the
receipt.

## Logical dump procedure (future, requires approval)

Use a fresh unique UTC directory under `/var/lib/terento/backups`; do not use
`/tmp`, the repository, an image layer, or a world-readable location. Use
`umask 077`, `set -euo pipefail`, and no shell tracing. The following is a
template: replace only non-secret placeholders after preflight. `PGPASSFILE`
must already be securely mounted; do not create or copy credentials as part
of an ad-hoc command.

```sh
umask 077
set -euo pipefail
DB_CONTAINER='__verified_container_name_or_id__'
BACKUP_ROOT=/var/lib/terento/backups
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
FINAL="$BACKUP_ROOT/terento-catalog-$STAMP"
STAGE="$BACKUP_ROOT/.stage-$STAMP"
test ! -e "$FINAL" && test ! -e "$STAGE"
test ! -L "$BACKUP_ROOT"
if test -e "$BACKUP_ROOT"; then
  test -d "$BACKUP_ROOT"
  test "$(stat -c '%u:%g:%a' "$BACKUP_ROOT")" = '0:0:700'
else
  install -d -o root -g root -m 0700 "$BACKUP_ROOT"
fi
mkdir -m 0700 "$STAGE"
chown root:root "$STAGE"

# DB_USER, DB_NAME, and PGPASSFILE are non-secret identifiers/path values
# from the approved runtime configuration; never print their source env.
docker exec --user postgres \
  --env PGPASSFILE='__verified_existing_secret_file_path__' \
  "$DB_CONTAINER" sh -eu -c '
    test -r "$PGPASSFILE"
    exec pg_dump --no-password --format=custom --lock-wait-timeout=30s \
      --username="$POSTGRES_USER" --dbname="$POSTGRES_DB"
  ' > "$STAGE/catalog.dump.partial"
test -s "$STAGE/catalog.dump.partial"
chown root:root "$STAGE/catalog.dump.partial"
chmod 0600 "$STAGE/catalog.dump.partial"

# Validate the archive structure without exposing its TOC/object names.
docker exec -i "$DB_CONTAINER" pg_restore --list - \
  < "$STAGE/catalog.dump.partial" > /dev/null
mv -- "$STAGE/catalog.dump.partial" "$STAGE/catalog.dump"
(cd "$STAGE" && sha256sum catalog.dump > SHA256SUMS)
chown root:root "$STAGE/SHA256SUMS"
chmod 0600 "$STAGE/SHA256SUMS"
stat -c '%s %a %U:%G' "$STAGE/catalog.dump"
test ! -e "$FINAL"
mv -T -- "$STAGE" "$FINAL"
```

The credential variables above are deliberately placeholders: confirm the
container actually receives the approved identifiers and password file
without printing them. If this cannot be done safely, do not substitute
`PGPASSWORD` on a command line. The `docker exec` invocation must run
`pg_dump -Fc` with `--no-password`; an absent/invalid credential must fail
closed. On any dump, archive-list, checksum, permission, or rename failure,
do not call the partial output a backup.

Write a root-only manifest alongside the archive containing only the UTC
start/end, VPS ID, DB container/image IDs, database/schema/user, server and
client versions, archive filename/size/SHA-256, ownership/mode, exit statuses,
selected table counts and migration ledger. Include no credentials, row
contents, raw SQL, or full command environment. Record counts for
`device_model`, `compatibility_evidence_event`, and `map_download_event`, plus
`schema_migrations` and the `compatibility_model_statistics` view. Record the
complete migration version ledger. The pre-dump counts and ledger must be
captured read-only and rechecked against the restored database.

`pg_dump` is transaction-consistent but does not freeze subsequent writes or
include cluster-wide roles/tablespaces. Record the accepted recovery point and
RPO. Preserve ownership/ACL metadata in the archive. If non-default
tablespaces or required roles cannot be reproduced in the isolated instance,
record that limitation or stop; never add production role passwords or use
`pg_dumpall` as a shortcut.

## Isolated PostgreSQL 16 restore (future, requires approval)

Use a unique throwaway PostgreSQL 16 container and a new named volume that is
not used by production. Pin its image by the verified immutable digest and
ensure required extensions are present. Do not mount production data, Compose
files, environment files, secrets, sockets, or networks. Publish no ports.
Use `--network none` (stronger isolation than an internal production network)
and mount only the verified archive read-only. Generate a unique temporary
database password into a root-only secret file; mount it read-only into this
throwaway container. Do not print it or include it in command arguments or
logs. Do not use production credentials.

Illustrative command skeleton (all identifiers, paths and the image digest
must be verified before separately approved execution):

```sh
umask 077
RESTORE_NAME="terento-pg16-restore-$STAMP"
RESTORE_VOLUME="terento-pg16-restore-$STAMP"
RESTORE_PASSWORD_FILE="$FINAL/.restore-password"
RESTORE_PGPASS_FILE="$FINAL/.restore-pgpass"
RESTORE_IMAGE='__verified_postgresql_16_image@sha256:...__'
RESTORE_PASSWORD=$(openssl rand -hex 32)
printf '%s' "$RESTORE_PASSWORD" > "$RESTORE_PASSWORD_FILE"
printf '127.0.0.1:5432:*:postgres:%s\n' "$RESTORE_PASSWORD" > "$RESTORE_PGPASS_FILE"
unset RESTORE_PASSWORD
chown root:root "$RESTORE_PASSWORD_FILE" "$RESTORE_PGPASS_FILE"
chmod 0600 "$RESTORE_PASSWORD_FILE" "$RESTORE_PGPASS_FILE"

docker volume create "$RESTORE_VOLUME"
docker run --pull=never --detach --name "$RESTORE_NAME" \
  --network none \
  --mount "type=volume,src=$RESTORE_VOLUME,dst=/var/lib/postgresql/data" \
  --mount "type=bind,src=$RESTORE_PASSWORD_FILE,dst=/run/secrets/pg-password,readonly" \
  --mount "type=bind,src=$RESTORE_PGPASS_FILE,dst=/run/secrets/pgpass,readonly" \
  --mount "type=bind,src=$FINAL/catalog.dump,dst=/restore/catalog.dump,readonly" \
  --env POSTGRES_PASSWORD_FILE=/run/secrets/pg-password \
  "$RESTORE_IMAGE"

# Inspect only container ID, image ID, network mode, mounts and published ports.
docker inspect --format '{{.Id}} {{.Image}} {{.HostConfig.NetworkMode}} {{json .Mounts}} {{json .NetworkSettings.Ports}}' "$RESTORE_NAME"
ready=false
for attempt in $(seq 1 60); do
  if docker exec --env PGPASSFILE=/run/secrets/pgpass "$RESTORE_NAME" \
    pg_isready --host=127.0.0.1 --username=postgres --dbname=postgres >/dev/null; then
    ready=true
    break
  fi
  sleep 2
done
test "$ready" = true
docker exec --env PGPASSFILE=/run/secrets/pgpass "$RESTORE_NAME" \
  createdb --host=127.0.0.1 --username=postgres --template=template0 terento_restore_validation
docker exec --env PGPASSFILE=/run/secrets/pgpass "$RESTORE_NAME" \
  pg_restore --host=127.0.0.1 --username=postgres --exit-on-error --single-transaction \
    --dbname=terento_restore_validation /restore/catalog.dump
```

The password values above are generated at runtime and are never printed or
placed in a Docker command argument; Docker receives only paths to root-only,
read-only mounted files. Do not run `docker inspect` without the narrow format
above because its full output can expose configuration. Before the restore,
independently confirm the exact container ID, image digest, volume, network,
mounts, and absence of published ports. If the verified PostgreSQL image uses
a different supported data path or secret-file behavior, stop and review the
command before running it.

Because `pg_dump` does not include global roles, inventory object owners and
grantees without exposing row data. For a full ownership/ACL restore, create
only the required role names as `NOLOGIN` roles from a reviewed, secret-free
role manifest in the isolated instance, then restore without `--no-owner` or
`--no-acl`. Never copy production role passwords. If roles/grants are omitted
with `--no-owner --no-acl`, record the result as a schema/data-only rehearsal,
not a full restore validation, unless the owner explicitly accepts that scope.

After confirming the container ID, image digest, volume, network, mounts and
absence of published ports with narrow `docker inspect` fields:

0. Recheck the retained archive before using it: `(cd "$FINAL" && sha256sum
   --check --status SHA256SUMS)` must exit 0.
1. Create an empty validation database from `template0`.
2. Run `pg_restore --exit-on-error --single-transaction` against only that
   validation database. Use the approved role/ownership restoration plan;
   if production roles are absent, a schema/data-only `--no-owner --no-acl`
   restore does not validate ownership/grants and must be reported as such.
3. Require restore exit status 0. Compare server/encoding/collation, required
   schemas, tables, views, PK/FK/CHECK constraints, complete
   `schema_migrations` ledger and highest version, plus pre-dump counts for
   `device_model`, `compatibility_evidence_event`, and `map_download_event`.
   Run read-only sanity SELECTs and verify
   `compatibility_model_statistics`. Never print row data.
4. Record the exact archive SHA, dump/restore/image versions, restore exit
   status, ledger/count/schema checks, and PASS/FAIL in the root-only receipt.
5. Only after all checks pass report **POSTGRESQL RESTORE VALIDATED** for this
   database-only scope. Then, under the separately approved cleanup step,
   remove only the exact temporary container and volume after verifying their
   recorded IDs/names. Keep the production dump and receipt until 062 and
   backend deployment have both been separately approved and verified.

For the separately approved cleanup, confirm the exact recorded temporary
container and volume are not production objects; stop and remove only that
container, remove only its named temporary volume, then unlink the two exact
temporary credential files. Do not delete the archive, checksum, or receipt.

`pg_restore` executes SQL from the archive. The network/mount/volume isolation
is mandatory, not optional. Any restore, count, schema, ledger, extension,
ownership, or checksum mismatch is a hard FAIL. Do not retry against
production, downgrade 062, or delete the known-good logical archive.

## Hostinger whole-VPS recovery point

The Hostinger points listed above are stale for a pre-062 gate. Obtain separate
owner approval before creating a fresh provider recovery point. Check the
current hPanel summary immediately before confirming: exact VPS, selected
backup/snapshot type, expected duration, retention/overwrite behavior, and
availability impact. A new manual snapshot may overwrite the previous single
snapshot. A provider restore replaces the whole VPS state; it is not a
database-only rollback and may lose all changes after its timestamp. Do not
restore it without a separate explicit approval naming the exact recovery
point and target.

After provider completion, verify its exact ID/timestamp is listed and record
**HOSTINGER RECOVERY POINT READY** only if the owner accepts the point-in-time
loss window and full-server restore semantics. Do not treat a requested,
pending, expired, or unverified point as ready.
