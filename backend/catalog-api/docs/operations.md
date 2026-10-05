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

The previous API/scheduler stay running while this stage executes, and a failed
rollout may restore that service revision without downgrading schema. Therefore
ordinary migrations must be backward-compatible with both the running revision
and that rollback. Prefer expand/contract changes such as additive tables,
nullable or default-safe columns, and additive indexes. Drops or renames,
incompatible data semantics, destructive transforms, new-code-first changes,
non-transactional or downtime-required work, and large external backfills stop
for exceptional review; defer removal to a later cleanup migration after old
usage is retired.

The image digest binds the migration contents. Per-version image labels,
target-specific hashes, migration branches, manual SQL, and separate ordinary
migration/deploy protocols are not part of the design.

Migration 063 remains the additive `github_release_marker` schema change. It
does not rewrite historical download snapshots. The collector upserts GitHub
release ID/tag/label/`published_at` facts from the authoritative release list,
so historical markers and multiple releases in one chart bucket are not
guessed from counter discontinuities. Counter decreases and other unexplained
population changes remain independent Data boundary or unattributed evidence.

## Client address and intake limits

The API binds only to the private Docker network and Traefik terminates HTTPS,
so the direct TCP peer of every public request is the proxy. Per-client limits
therefore derive the client from `X-Forwarded-For` only when the direct peer is a
trusted proxy: the rightmost hop that is not itself a trusted proxy is the
client the proxy saw; a malformed hop falls back to the peer address, and a
header from an untrusted peer is ignored. `CATALOG_TRUSTED_PROXIES` lists the
trusted proxy addresses or CIDR networks (comma-separated); the default is
loopback plus the private ranges `10.0.0.0/8`, `172.16.0.0/12`,
`192.168.0.0/16` and `fc00::/7`, which covers the Docker network Traefik uses.
Set it to the exact Traefik address to narrow trust, or to `none` to disable
forwarded-header trust. Without this, every user shared one limit bucket.

Anonymous intake allows 600 map events and 300 compatibility reports per client
address per minute. One install of up to 100 maps with optional contours emits
about seven map events and one diagnostic per map, uploaded sequentially by the
app with short retries, so the earlier 60/30 limits rejected a single large
batch. The higher limits still bound abuse; `429` responses remain retryable for
clients. Idle limiter keys are swept so memory stays bounded. Each request
socket has a 60-second timeout per blocking read or write, so a stalled client
releases its server thread while large requests and responses still progress.

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
