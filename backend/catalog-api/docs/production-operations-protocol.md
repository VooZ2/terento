# Production operations protocol

This is the current normal production protocol. It is intentionally one
stable deploy path. The current task changes source, tests, and documentation
only; it does not authorize a VPS mutation.

## Boundary

GitHub CI's API principal may send exactly:

```text
deploy sha256:<64 lowercase hex characters> <40 lowercase hex revision>
```

The active forced target is the owner-managed
`/usr/local/bin/terento-ci-api-entry`. The tracked
`scripts/infra/terento-deploy-ssh-entry.py.in` is a deploy-only template and is
not evidence that the active VPS target has been changed. The principal has
no remote STATUS or migration command. Read-only inspection, if separately
needed, is an owner/root operation outside the GitHub protocol.

## Canonical flow

1. GitHub tests the exact beta commit.
2. The publisher builds and pushes one immutable image and records its digest.
3. The owner confirms the generic `confirm_production_deploy` workflow gate.
4. CI sends only the digest and full revision through the deploy-only principal.
5. The root helper acquires the single operations lock for the whole operation.
6. It validates the candidate repository, digest, source label, revision label, enabled target, and previous state.
7. For the API, it inventories migrations from the same immutable image, reads the existing ledger, validates the exact prefix, and runs the candidate image's one-shot migrator with no target-specific argument when needed.
8. It rereads the ledger and requires exact equality with the candidate inventory before replacing services.
9. It replaces API/scheduler only, verifies service identity, image digest, health, and release, and records state.
10. On failure it leaves the old services and volumes intact or restores the previous service image; it never downgrades the schema.

The database container is not replaced. The root helper's operations lock spans
candidate validation, migration precheck, migration execution, postcheck, and
service replacement. The same immutable image reference is used for the
inventory audit, one-shot migration, and service rollout.

## Forward migration safety

The image inventory must be a canonical contiguous sequence beginning at 001.
The live ledger must be an exact prefix of that sequence. Missing or malformed
production ledgers, gaps, duplicates, numeric aliases, unknown versions, and
ledger-ahead states fail closed before SQL. Pending migrations execute in
numeric order in one transaction, and the ledger is checked again after the
runner reports success. Equal inventory is a verified no-op.

Because the old API/scheduler remain live during migration and may be restored
after a failed rollout, every ordinary migration must be backward-compatible
with that previous revision. Prefer expand/contract changes: additive tables,
nullable or default-safe columns, and additive indexes. Drops or renames,
incompatible data semantics, destructive transforms, new-code-first changes,
non-transactional or downtime-required work, and large external backfills stop
for exceptional review. Remove old schema only in a later safe cleanup
migration after old usage is retired.

The ordinary path has no migration target input, per-version image labels,
target-specific helper behavior, migration-only SSH account, migration branch,
manual SQL, or Web Console bootstrap. Migration 063 is therefore handled like
any other pending forward migration from the candidate image. Its SQL remains
additive and its release-marker population remains separate from historical
download-snapshot discontinuities.

## Owner gate and exceptional work

The workflow's `confirm_production_deploy` boolean is the single explicit
owner confirmation gate. The fixed-ops installation variable remains an
activation guard. Neither is a migration-version selector.

If a migration drops or renames schema, changes data semantics incompatibly,
performs a destructive transform, requires new code first, is
non-transactional, requires downtime, or needs a large external backfill, stop
the normal deployment, report the exact reason, and request a separately
reviewed architecture decision. Do not add a second routine deployment
protocol.

## Recovery and rollback

Forward schema recovery uses the validated database backup/recovery procedure
in [production-db-recovery.md](production-db-recovery.md). A service failure
may restore the previous immutable image, but it must not delete volumes or
attempt an automatic schema downgrade. Image cleanup runs only after a
verified, recorded deploy and always keeps the current and previous release
images, so rollback to the previous image never needs a registry pull. If the remote result is uncertain,
inspect the bounded root-owned state and ledger before considering any retry.

## Evidence before an authorized run

The review receipt must record the exact commit, image digest, workflow run,
test results, migration inventory, ledger precheck/postcheck, service health,
and rollback state. It must not contain credentials, environment dumps,
database rows, or private keys. The canonical template is
[production-candidate-receipt.md](production-candidate-receipt.md).
