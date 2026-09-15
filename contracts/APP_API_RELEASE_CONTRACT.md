# App–API compatibility and release contract

This is the shared release contract for the native app, catalog/evidence API and
admin read models. Read it before changing either diagnostic stream, payload
schemas, accepted codes, correlation, counting, or release order. The behavioral
requirements remain in [the admin contract](../backend/catalog-api/docs/admin-behavior-contract.md).
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
map by provider/region (and validated variant/component identity where applicable),
not by timestamp or a nearby watch. Neither stream can manufacture missing facts
from the other. Different sharing preferences can legitimately leave only one
stream. A missing report must remain visible as missing.

## Mandatory tests before merging/releasing

1. Change the native encoder/producer, shared schema/fixtures and API acceptance
   together when fields or controlled codes change. Do not assume API acceptance
   from a successful statistics upload or a matching version label.
2. Run the native operation diagnostics suite. It exercises a real MapEngine
   failure without ConnectScreen, persists and sends reports through the existing
   queue, and passes freshly Swift-encoded failure payloads to the loopback API
   intake/storage/identity/admin tests. Committed fixture tests remain available
   on Linux. All InstallationFailure codes plus the diagnostic-only unknown code
   must pass both schema and actual API validation.
3. Preserve result semantics: write/pre-write/verification failure, partial maps,
   NOT_STARTED, cancellation, disconnect, screen reset, retry/restart, duplicate
   event IDs and opt-out. Do not fabricate writeStarted, cause or device identity.
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
existing schema versions and fields remain unchanged. Initial operation context
is in memory and terminal reports enter the existing durable outbox. This does
not add crash journaling before a result exists, and cannot recover a historical
missing report or infer an unknown user's watch.

## Toolchain changes and final artifact startup

An SDK/toolchain upgrade requires a fresh bundled-native build and a launch
check of the final app extracted from each distribution format on the local
macOS host. API contract tests, signing, deployment-target load commands and
Apple notarization are independent evidence; none proves the app starts.
A failed local launch blocks publication of the app, tag and update metadata.
Record the OS, Xcode version, exact source and runtime checks in the release
receipt. Do not infer older-OS compatibility from a successful newer-host run.
