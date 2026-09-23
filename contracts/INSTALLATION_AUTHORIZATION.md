# Native installation authorization

This is the canonical product decision for starting or continuing a native map
write. The API device catalog, not public Compatibility or the local Map Manager
presentation registry, owns the capability decision. The current implementation
is local and has not been released; the live policy endpoint returned HTTP 404
in the 2026-09-22 read-only audit.

The client must identify the connected Garmin manufacturer and a reliable,
normalized **base model** without substring or broad family matching. Collect
all active catalog rows for that base model, then use reliable variant facts
only to narrow the candidate rows. Evaluate variant attributes independently.
If evidence for a variant attribute conflicts, treat that attribute as unknown
and do not filter on it. **Conflicting variant evidence broadens the candidate
set. It does not by itself deny authorization. Authorization is determined from
the Maps capability of all remaining possible candidates.** A conflict in
manufacturer or base-model identity itself is unreliable and must produce
`PENDING`; it is not a variant conflict. `catalogDeviceID` is only a hint and
cannot choose or narrow candidates by itself. Missing case size, display,
Solar, or inReach information does not prevent approval if every plausible
active candidate has `mapCapable=true`. All candidates with Maps=Yes produce
`APPROVED`; all with Maps=No produce `BLOCKED`; mixed candidates or any NULL
capability produce `PENDING`. An unknown base model or no candidates is
`PENDING`, with no write. Inactive rows never confer approval. A policy
endpoint failure, missing route, or invalid response is `CATALOG_UNAVAILABLE`,
also with no write. This is a temporary verification failure, not evidence of
permanent incompatibility.

The public Compatibility directory and its `TESTED`/`SUPPORTED`/`VERIFIED`
evidence categories, `successfulInstallations`, Admin `support_status`, and
prior successful installs neither grant nor revoke write authority. Catalog
`mapCapable` is the stored nullable value; separately observed or inferred
map capability is diagnostic evidence only. The current Garmin Edge models
are absent from the API catalog and therefore `PENDING`, not permanently
unsupported. A future reliably identified, active Edge catalog model with
Maps=Yes follows the same rule without a dedicated blacklist, whitelist, or
feature flag. Public product claims remain independently evidence-gated.

Installation checks current policy before provider/custom acquisition or
extraction and again at the final write boundary. Safe Update checks when the
operation starts and immediately before its first remote write, comparing the
connected identity around both requests. Once writing has started, exact
target cleanup and rollback use the operation's established safety facts and
do not require another policy request. All other live-device, ownership,
no-overwrite, storage, and transfer checks remain in force.

`installation-policy.schema.json` defines the response shape. Local backend
code serves a public-read, metadata-only `GET /devices/installation-policy.json`
projection with `schemaVersion: 3`. The local implementation requires a fresh
response and uses `Cache-Control: no-store`; conditional requests return a
new 200 policy rather than 304. The deploy smoke check now includes this
endpoint. None of these local changes proves a live 200 or authorizes an app
release: schema reconciliation, backend deployment, live projection validation,
and a separate release decision remain gates.
