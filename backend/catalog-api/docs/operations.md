# Catalog operations

The catalog service is metadata-only. PostgreSQL is private to the Docker
network and the service never hosts, proxies, mirrors, caches, or repackages
provider map archives. The map style preview job is the one place that
downloads provider maps: one at a time, inside its rendering window, only to draw
preview tiles, and each download is deleted as soon as its tiles exist.

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
10. verify the release, record state, and retain the previous image for rollback;
11. after the recorded success, remove other local images of that repository without force, keeping only the current and previous images. Images still used by a container are left alone, and a cleanup problem never fails or rolls back the deployment.

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

## Map style previews

The preview renderer runs inside the existing `catalog-scheduler` service of
the same immutable image; it adds no deploy target, migration path or SSH
command. Migration `073_map_style_previews.sql` is additive and runs through
the normal helper. Before enabling previews the owner-run configuration for
the `api` project needs, once:

- the asset volume mounted read-write in `catalog-scheduler` at the same
  `TERENTO_ASSET_ROOT` the API reads, and a separate work volume at
  `TERENTO_PREVIEW_WORK_DIR`;
- a CPU and memory limit on `catalog-scheduler` (for a 2 vCPU / 8 GB host:
  `cpus: 1.0`, `mem_limit: 2g`) so rendering never competes with the API and
  database;
- `MAP_PREVIEW_ENABLED=true` in the release environment.

For the first fill, `MAP_PREVIEW_WINDOW_UTC=00:00-00:00` renders around the
clock inside the CPU limit; finished layers appear in the manifest at most
`MAP_PREVIEW_PUBLISH_MINUTES` (default 30) after they are drawn. A nightly
window such as the default `00:00-06:00` is enough for later refreshes.
`MAP_PREVIEW_RENDER_JOBS` (default 1) renders that many map tiles in parallel
inside one renderer process at the lowest CPU priority; on an otherwise idle
2 vCPU / 8 GB host the first fill can use `MAP_PREVIEW_RENDER_JOBS=2` with
`cpus: 2.0` and `mem_limit: 4g`, then return to the limits above. Each extra
job raises the renderer's address-space limit by 512 MiB.
Only one renderer runs at a time: it holds a 15-minute lease that it renews
while it works, so a renderer stopped by a deploy blocks the next one for at
most 15 minutes: a renderer that finds the lease taken retries every 2
minutes. The next renderer removes the downloads and staged tiles the stopped
one left behind, and redraws layers that were drawn but not yet published or
whose published tiles still have the transparent land of an earlier renderer.
A deploy never makes drawn previews disappear or start over: the manifest
follows the tiles in the current release, so a release switched by a renderer
stopped mid-publish stays visible, and the next renderer records that release
and keeps every published layer.

Then switch providers on one at a time under Admin › Providers › Map style
previews and check the `map-preview-renderer` heartbeat, the provider's
preview layer table and `/maps/previews/manifest.json`. Turning a
provider off hides its layers from the manifest immediately; its tiles leave
the disk with the next releases. `MAP_PREVIEW_MAX_TOTAL_BYTES` (default 55 GB)
caps all preview releases and `MAP_PREVIEW_MIN_FREE_BYTES` (default 20 GB) is
always left free; a window that would exceed either stops and reports a
warning instead of downloading.

## Local checks

```sh
terento-catalog-migrate
terento-catalog-migrate
python backend/catalog-api/tools/check_catalog_database.py
```

The repeated invocation proves idempotency. Run the backend suite and the
production-operations contract suite from the repository root before any
review or authorized production action.
