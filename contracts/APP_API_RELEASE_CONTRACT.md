# App–API compatibility and release contract

This is the shared release contract for the native app, catalog/evidence API and
admin read models. Read it before changing either diagnostic stream, payload
schemas, accepted codes, correlation, counting, or release order. The behavioral
requirements remain in [the admin contract](../backend/catalog-api/docs/admin-behavior-contract.md);
statistics populations and formulas are canonical in
[`STATISTICS_CONTRACT.md`](STATISTICS_CONTRACT.md).
A build number is not an API schema version.

## Required compatibility record

Every affected release receipt must identify the app build/tag and packaged
source SHA, API source SHA and completed deployment run, payload schema versions,
changed fields/codes, old-client compatibility, test runs and live verification.
List each stream separately:

| Stream | Producer and context | Delivery | Consumers |
| --- | --- | --- | --- |
| Compatibility diagnostics | Operation-owned observer; initial device/map context and observed per-map result | InstallationEvidenceController durable queue, independent sharing choice | /compatibility/events, exact-model evidence, Review queue and diagnostic actions |
| Map activity | MapEngine and existing acquisition journal; provider/map/component phases | MapStatisticsEventController queue, independent sharing choice | /map-events, Map statistics and Overview reconciliation |

Use the same random operationId for an operation in both streams. Correlate each
map result by `operationId + mapResultIndex` when available, together with
package/map, provider/region and component identity; legacy records retain their
event identity. Do not use operationId alone, provider/region alone, timestamp,
or a nearby watch. Neither stream can manufacture missing facts from the other.
Different sharing preferences can legitimately leave only one stream. A missing
report must remain visible as missing.

## Mandatory tests before merging/releasing

1. Coordinate the native encoder/producer, shared schema/fixtures and API
   acceptance when fields or controlled codes change. Additive server acceptance
   may land first with fixtures; native emission follows its deployed acceptance
   gate and must pass freshly encoded payload tests. Do not assume API acceptance
   from a successful statistics upload or a matching version label.
2. Run the native operation diagnostics suite. It exercises a real MapEngine
   failure without ConnectScreen, persists and sends reports through the existing
   queue, and passes freshly Swift-encoded failure payloads to the loopback API
   intake/storage/identity/admin tests. Committed fixture tests remain available
   on Linux. All InstallationFailure codes plus the diagnostic-only unknown code
   must pass both schema and actual API validation.
3. Preserve result semantics: one fresh result per main map, optional components,
   write/pre-write/verification failure, separate acquisition/update outcomes,
   partial maps, NOT_STARTED, cancellation, disconnect, screen reset,
   retry/restart, duplicate event IDs and opt-out. Do not fabricate writeStarted,
   cause or device identity.
4. Run backend PostgreSQL migration/read-model integration, full app/native and
   release suites. Retain legacy client contracts and local-test exclusion.
5. Follow the admin contract through review → diagnostic → correct device/history
   and existing assignment/issue actions. Record live authenticated read-only
   verification after deployment. Never create public issues or synthetic public
   install data merely to make a release gate green. Missing access is pending
   evidence, not a successful check.

The executable native-to-API gate is
`app/TerentoCore/Tests/run-app-installation-operation-diagnostics-tests.sh`.
Its backend half is `Tests/run-backend-operation-diagnostic-contract-tests.sh`.
Both are registered in the test-suite manifest; the full packaging suite runs
them. Live semantic behavior still needs the separate read-only review above.

## Publication order and recovery

1. Merge tested source and deploy additive API/schema acceptance first. Confirm
   the deployment's exact SHA contains every code/field the candidate can emit.
2. Verify old-client catalog contracts, health and affected authenticated admin
   workflows. Record unresolved criteria honestly; do not equate green deploy
   status with complete workflow validation.
3. Package from the exact clean, GitHub-verified merged source; sign/notarize and
   validate artifacts. Only then publish the immutable app tag/assets and update
   the public manifest/notes with real checksums and the next build number.
4. Never release a client against an API known to reject its payloads. If a server
   rollback is needed after client publication, retain additive acceptance for
   every distributed client. Prefer a compatible forward fix over rejecting
   queued reports. Retried event IDs must retain idempotency.

For build31, `INSTALL_FAILED_UNKNOWN` is the additive compatibility-event code;
existing schema versions and fields remain unchanged. `MAP_UPDATE_SUCCEEDED` and
`MAP_UPDATE_FAILED` are additive map-event types for the local Update candidate;
the API acceptance and database check constraint must be deployed before a
public client can emit them. Initial operation context
is in memory and terminal reports enter the existing durable outbox. This does
not add crash journaling before a result exists, and cannot recover a historical
missing report or infer an unknown user's watch.

## Server-first structured failure context

The version-4 additive contract accepts optional top-level `failureContext` and
`originalFailureContext`. Either omitted or explicitly null context is
unavailable; non-null objects use the same nonrecursive closed shape, with
optional nested `protection`. Null normalizes to absence and SQL NULL, not JSONB
`null`, without schema v5 or an additional migration. A non-null original
context still requires a terminal cleanup context object. The exact fields and bounds are defined in
[the shared event contract](README.md#structured-installation-failure-context).
Versions 1–3 remain accepted without the new fields, and existing v4 payloads
remain valid. Server acceptance alone is not app emission or a deployment claim.

The server group covers schema/explicit validation, additive persistence,
Admin/report presentation and tests. Its prerequisite gate is recorded by the
release coordinator as passed for source `97e6cd9`, deployment
[35565491844](https://github.com/VooZ2/terento/actions/runs/35565491844) and beta CI
[35565491848](https://github.com/VooZ2/terento/actions/runs/35565491848): migration
and legacy acceptance verified, production absent/null/object requests accepted
with idempotent replays, and historical unavailable context verified in
Admin/report presentation. This backend evidence does not release the app.
Historical rows retain unavailable context. Preserve both terminal cleanup context and its
original failure context; do not reconstruct either from a legacy code.

Validation must exercise nested privacy rejection and numeric bounds, legacy
requests, absent/null equivalence, idempotent replay, SQL NULL persistence and
Admin/generated-report unavailable presentation. Both optional fields,
including explicit null, are v4-only; versions 1–3 remain accepted unchanged
when both fields are absent. Non-null objects remain strictly validated.
The loopback delivery suite uses SQLite and does not replace PostgreSQL migration
and read-model integration. Before merging the local app candidate, run the actual Swift
encoder-to-API gate, app/native suites and the Xcode product build; verify new
Swift source membership in both the Xcode target and explicit shell-runner
source lists. The repository all-suite runner does not replace those separate
PostgreSQL and Xcode gates.

Comparator version 1 denotes existing semantics during diagnostics-only work.
Version 2 is reserved for a separate safety change, independent review and real
hardware gate. Neither accepting that value nor a green diagnostic test proves
the comparator safe. No operation retries are introduced. The local app candidate
now supplies typed context and a shared boundary-to-stage resolver for known
preflight reads and protection failures, retaining original context when cleanup
fails. Native categories are captured at explicit C failure branches. Final
validation covers transport wrappers, local diagnostics, outbox reload, encoding
and API delivery preserving observed provenance and component identity. The
current encoder runner requires fresh preflight, protection and contours-cleanup
fixtures, then verifies HTTP/storage/report round-trips and idempotent replay;
committed fallback examples cannot satisfy that fresh-encoder requirement.
Final focused/full-matrix results belong
to the candidate's integration record, not the earlier server test results.
Comparator version 2 remains unimplemented. Neither an app release nor a hardware
pass is established by this local diagnostics implementation.

## Toolchain changes and final artifact startup

An SDK/toolchain upgrade requires a fresh bundled-native build and a launch
check of the final app extracted from each distribution format on the local
macOS host. API contract tests, signing, deployment-target load commands and
Apple notarization are independent evidence; none proves the app starts.
A failed local launch blocks publication of the app, tag and update metadata.
Record the OS, Xcode version, exact source and runtime checks in the release
receipt. Do not infer older-OS compatibility from a successful newer-host run.

## Coordinate the release source window

Before final candidate CI, identify the release owner and pause unrelated merges
into `beta` until the candidate is merged and its verified source SHA is recorded.
An API change required by the new client must land before this window. Otherwise
an unrelated merge can invalidate an up-to-date-branch check and force the entire
candidate CI to rerun. Do not bypass branch protection to recover lost time.
After the immutable source is recorded, later API/admin work must preserve the
released-client acceptance contract; it does not change the artifact's source.
