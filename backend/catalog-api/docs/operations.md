# Catalog operations

The catalog service is metadata-only. PostgreSQL is private to the Docker
network and the service never hosts, proxies, mirrors, caches, or repackages
provider map archives.

## One stable deployment path

The only normal production request from GitHub is:

```text
deploy sha256:<64 lowercase hex characters> <40 lowercase hex revision>
```

The forced API principal is deploy-only. The active production boundary is the
owner-managed `/usr/local/bin/terento-ci-api-entry`; the tracked SSH template
is a deploy-only reference for reviewed installations. It does not expose
remote status or migration commands. The GitHub principal is not a general
operator account and does not choose a migration number.

The root helper performs this sequence while holding one non-blocking
operations lock:

1. validate the digest, revision, enabled target, previous state, and Compose configuration;
2. pull and inspect the exact repository@digest image;
3. verify the immutable source and revision labels;
4. read the migration inventory from that same image in a network-disabled, read-only audit container;
5. read the existing database ledger without creating or modifying it;
6. require the ledger to be an exact canonical prefix of the image inventory;
7. run `terento-catalog-migrate` from the same image with no target-specific argument when entries are pending;
8. reread the ledger and require exact equality with the candidate inventory;
9. replace only the API/scheduler services with the same immutable image and verify health;
10. verify the release, record state, and retain the previous image for rollback.

The database container is never replaced by this path. A migration failure,
ledger mismatch, invalid inventory, or health failure leaves the previous
services in place; service replacement rollback never removes volumes or
attempts a schema downgrade. A missing or malformed ledger fails closed for an
existing production database. Local/new database bootstrap remains the
separate ordinary migration command used by development and CI.

## Forward migration contract

Migration files are the canonical contiguous sequence `001` through the
highest version in the candidate image. Filenames require a three-digit
version and a safe suffix. Duplicates, numeric aliases, malformed names,
gaps, unknown ledger entries, and a ledger ahead of the image are rejected
before SQL execution. Pending files run in numeric order in one transactional
runner invocation; SQL and its ledger entries commit together or roll back
together. Equal inventories are a verified no-op.

The image digest binds the migration contents. Per-version image labels,
target-specific hashes, migration branches, manual SQL, and separate ordinary
migration/deploy protocols are not part of the design.

Migration 063 remains the additive `github_release_marker` schema change. It
does not rewrite historical download snapshots. The collector upserts GitHub
release ID/tag/label/`published_at` facts from the authoritative release list,
so historical markers and multiple releases in one chart bucket are not
guessed from counter discontinuities. Counter decreases and other unexplained
population changes remain independent Data boundary or unattributed evidence.

## Authorization and exceptional migrations

The deployment workflow runs backend tests and publishes the immutable image
before the explicit production confirmation gate. It then calls only
`scripts/infra/deploy-vps-image.sh api`. It does not use a target input,
migration-specific workflow, migration-specific SSH credential, or separate
candidate branch.

Only an exceptional migration that is destructive, non-transactional,
downtime-requiring, or dependent on an external backfill may stop the normal
path for owner review. It must report the reason and receive a reviewed
architecture change; it must not create a second routine protocol.

## Local checks

```sh
terento-catalog-migrate
terento-catalog-migrate
python backend/catalog-api/tools/check_catalog_database.py
```

The repeated invocation proves idempotency. Run the backend suite and the
production-operations contract suite from the repository root before any
review or authorized production action.
