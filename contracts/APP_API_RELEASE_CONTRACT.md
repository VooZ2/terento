# App–API compatibility and release contract

This is the shared release contract for the native app, catalog/evidence API and
admin read models. Read it before changing either diagnostic stream, payload
schemas, accepted codes, correlation, counting, or release order. The behavioral
requirements remain in [the admin contract](../backend/catalog-api/docs/admin-behavior-contract.md);
statistics populations and formulas are canonical in
[`STATISTICS_CONTRACT.md`](STATISTICS_CONTRACT.md).
A build number is not an API schema version.

## Beta.15 build 36 UI and update-metadata correction

Compared with beta.14 build 35, beta.15 build 36 forwards the current connected
device authorization into the map engine, keeps Install disabled with a visible
reason until authorization and the map scan are ready, and surfaces an operation
failure if authorization is unavailable. It also accepts the existing bounded
plain-text release summary while keeping the public summary within the beta.14
client's 240-character limit. There are no diagnostic payload, API schema,
catalog route, or backend runtime changes in this release.

Published tag `v1.0.0-beta.15-build36` points to packaged source
`facaa07a8ca6a4fb687f3fefc889ff49ee4f730e`. The release pipeline passed all
83 regression runners, live catalog validation, Developer ID signing, Apple
notarization, stapling and ZIP/DMG Gatekeeper and launch checks. Tag CI
[36237324252](https://github.com/VooZ2/terento/actions/runs/36237324252) passed
the native-to-API, PostgreSQL, app/native, site and release contracts. Freshly
downloaded published assets matched the approved checksums. The owner confirmed
the corrected Install and Update behavior with the local candidate on a Garmin
fēnix 8 47 mm; this remains owner-reported hardware evidence for that model and
behavior.

## Beta.14 build 35 authorization delta

Compared with beta.13 build 34, beta.14 build 35 refreshes schema-3
installation policy before acquisition and at the final write boundary, including
Safe Update. Matching and unknown/conflicting identity semantics are owned by
[`INSTALLATION_AUTHORIZATION.md`](INSTALLATION_AUTHORIZATION.md), independently
of public Compatibility status. Authorization refusals do not manufacture an
installation diagnostic result. The API accepts the additive failure codes
`INSTALL_BLOCKED_TERENTO_DEVICE_SCOPE` and `INSTALL_AUTHORIZATION_UNAVAILABLE`.
Map activity adds optional `mapResultIndex`; older payloads without it remain
accepted, and historical indices are not inferred.

Deployed backend source `0f9905fa63e6c61bd21cc68539bc680f84a86e99` includes these
contracts. Integrated source `e8f6005a3da20c0588da59ec569abd0b9c9b46fa` has no
backend runtime differences from that revision: subsequent differences are
workflow/helper, tests and documentation only. This compatibility record does not
replace fresh encoder-to-API, PostgreSQL, live-read and final artifact gates.

Published tag `v1.0.0-beta.14-build35` points to packaged source
`19d465dc97c53198dff3ec10c4cd73dad13fa2df`. Full packaging tests, Developer ID
signing, Apple notarization, stapling and ZIP/DMG launch checks passed. Tag CI
[36043055010](https://github.com/VooZ2/terento/actions/runs/36043055010) passed
the native-to-API, PostgreSQL, app/native and release contracts. Downloaded
published ZIP/DMG checksums match the approved artifacts. These automated and
artifact gates do not add real-device lifecycle evidence or resolve #278.

## Required compatibility record

Every affected release receipt must identify the app build/tag and packaged
source SHA, API source SHA and completed deployment run, payload schema versions,
changed fields/codes, old-client compatibility, test runs and live verification.
List each stream separately:

| Stream | Producer and context | Delivery | Consumers |
| --- | --- | --- | --- |
| Compatibility diagnostics | Operation-owned observer; initial device/map context and observed per-map result | InstallationEvidenceController durable queue, independent sharing choice | /compatibility/events, exact-model evidence, Needs attention and diagnostic actions |
| Map activity | MapEngine and existing acquisition journal; provider/map/component phases | MapStatisticsEventController queue, independent sharing choice | /map-events, Maps and Dashboard reconciliation |

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

Comparator version 1 denotes the earlier diagnostics-only comparison semantics.
The hybrid safety implementation retains the accepted version 2 numeric value and
existing payload schema with its bounded protected-inventory implementation.
No backend field, accepted value, app version or public release is changed by this
work. Release review must identify the exact app source/build and its comparator
scope; the version number alone does not establish which files were compared.

The safety contract uses native authorization and a local per-artifact
mutation journal as primary controls, exact target verification, and a secondary
protected inventory comparison. The stable metadata key is storage/path/name/size/
kind; session handles are not cross-session identity. Whole-device equality is
not an installation invariant. Existing protection booleans describe the bounded
protected scope, not proof that every device byte stayed fixed.
Unknown objects remain protected; only evidence-scoped runtime categories outside
map and operation scope are diagnostic. Incomplete authorization/journal evidence,
ambiguous targets and uncertain cleanup identity fail closed. No automatic retry
or name-plus-size cleanup authority is introduced.

Durable local ownership is independent of app version and mutation-journal lifetime.
Without a reliable device/map manifest, managed Update is unavailable and no silent
ownership inference is allowed. Explicit external Remove remains available after
confirmation and native same-session physical-device, exact-target, protection and
content revalidation. A prior install ledger is not required for this new removal
operation. Confirmation is never a substitute for same-operation cleanup provenance.
Cross-computer, app-upgrade and state-loss regressions must preserve these separate
authorities; protected maps remain read-only with or without a manifest.
Model-only legacy namespaces and conflicting physical-device namespaces must never
be combined into managed ownership. Preserve legacy files as local evidence,
without silently migrating or binding them to the current physical device.

Native journal identifiers, exact paths, physical identity, handles, claim files
and raw outcomes remain local; they are not new backend diagnostics fields.
Existing privacy minimization, opt-out, outbox and idempotency contracts remain.
The app retains typed failure provenance and original context when cleanup fails.
Before any distribution, source/encoder/API validation must confirm that candidate
protection semantics are documented without changing accepted schema values by
accident. Independent reviews, native executable tests, full matrix and a fresh
real-device hybrid gate are required. Source `7a6067a3` passed those integration
gates with MapRando Malta on fēnix 8 47 mm AMOLED / firmware 23.31, including
independent reconnect/full-target hashing and owner-confirmed on-watch use.
This validates the tested fresh-install path; it does not establish destructive
lifecycle hardware evidence, a new app release or historical #249 causation.

The existing failure-context release gate still requires fresh encoder fixtures
for preflight, protection and contours cleanup, followed by HTTP/storage/report
round-trips and idempotent replay. Committed fallback examples cannot replace
fresh encoder output. Native failure categories must reflect explicit failure
branches, preserving original provenance and component identity through transport,
local diagnostics, outbox reload, encoding and API delivery. Focused/full-matrix
results belong to the candidate integration record, not earlier server results.

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
