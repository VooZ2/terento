# App–API compatibility and release contract

## Beta.16 build 38 — provider recovery and update diagnostics

Beta.16 build 38 accepts both reviewed BBBike README date forms in
backend and native validation. It adds provider artifact rechecks and separate
update outcome diagnostics. Published tag `v1.0.0-beta.16-build38` points to GitHub-verified source
`b2bbabf5afd0acd4cb655e0859cd8da34a6dce8f`. All 83 release runners passed;
the optional migration 062 PostgreSQL check also passed separately. Signing,
Apple notarization, stapling, Gatekeeper and launch checks passed for ZIP and DMG.
API deployment [37059654512](https://github.com/VooZ2/terento/actions/runs/37059654512)
deployed that same source before distribution, including migrations 064–065 and
released-client catalog verification. The initial SSH timeout was retried with
the same immutable image.

The DMG is 6,860,640 bytes, SHA-256
`7cd45a731d3cdfa589ac4fe7fa41aae4226a381ee447bf6b9247962152d9a794`;
the ZIP is 6,182,464 bytes, SHA-256
`90ad60036a2020ca1a15743d89e64e07009aa2ba913f27450564b1ef69698ea2`.
No new hardware test or broader model claim is established by this release.

Before shipping the native producer, deploy migrations 064–065 and backend acceptance
of schema-v4 `operationKind=update`, required Boolean `oldMapPreserved`, and the
closed `UPDATE_*` failure-code set. These additive fields do not change schema
version or catalog routes. Old producers remain accepted; an old backend may
reject the new update report, so backend deployment and intake verification must
precede the app release. Report storage must bypass installation/compatibility
aggregation and share the existing diagnostic opt-out and 24-month retention.

Migration 065 adds only server-side identity assessment and admin review fields,
plus review audit storage. Shared install/update error presentation, GitHub
report preparation/linking, and exact-model update history do not add native
payload fields. Model update totals use retained diagnostics and remain separate
from map-activity totals and installation evidence. Conflicting reports for one
logical operation are excluded from model attempt totals and remain inspectable.
GitHub closure synchronization changes review state only; it never changes a
recorded failure into a successful operation. Existing reports with no assessed
identity remain unassigned instead of being backfilled by name.

Update diagnostics send measured cleanup attempt/result facts. An unmeasured
`transferProgressBucket` is omitted only for explicit update reports; the
existing installation contract still requires it. If a rolled-back backend
returns HTTP 400 for an update report, the client retains its original ID and
kind for a later flush and continues sending supported installation reports.
It never removes the discriminator or recasts the update as an installation.

Local update reports and their pending/uploaded IDs are stored separately in
`update-evidence.json`. The legacy `installation-evidence.json` contains only
installation reports, so an older app cannot resend updates as installations.
The installation file remains the canonical sharing-choice record. The update
file stores its last consent stamp; a changed stamp or a declined choice clears
pending updates on load, including an old-app revoke/reaccept cycle. Local reports
remain available. Each file is written atomically, updates first; event IDs remain
idempotent across retries and recovery of an unreleased mixed-file candidate.

Release checks include separate fresh/update counters, pre-write NOT_STARTED,
write failure, duplicate/intake-order handling, exact diagnostic correlation,
old-client acceptance, provider queue recovery and the two BBBike date formats.
Use the same operation ID for local, diagnostic and map-update records. Publish
neither a cause for the historical France failure nor new hardware compatibility
claims from these checks. The owner approved the release notes and app-update notification copy on
2026-10-02; the approved text is published with build 38.

This is the shared release contract for the native app, catalog/evidence API and
admin read models. Read it before changing either diagnostic stream, payload
schemas, accepted codes, correlation, counting, or release order. The behavioral
requirements remain in [the admin contract](../backend/catalog-api/docs/admin-behavior-contract.md);
statistics populations and formulas are canonical in
[`STATISTICS_CONTRACT.md`](STATISTICS_CONTRACT.md).
A build number is not an API schema version.

## Beta.15 build 37 cleanup and Install action parity

Beta.15 build 37 keeps the beta.15 API and telemetry contract unchanged. It
further hardens the Install action handoff so transient preparation states do
not expose an action the operation engine cannot accept, and removes obsolete
internal installation/update code. Current authorization, ownership, transfer
verification, rollback and cleanup safeguards remain in force. There are no
backend, API schema, catalog route or telemetry semantic changes.

Published tag `v1.0.0-beta.15-build37` points to packaged source
`6a1c9823f7b6308d50d0d74d23540d310bee6125`. The release pipeline passed the
full regression suite, live catalog validation, Developer ID signing, Apple
notarization, stapling, and ZIP/DMG Gatekeeper and launch checks. PR CI run
[36277139019](https://github.com/VooZ2/terento/actions/runs/36277139019) passed
all applicable checks. The published DMG is 6,837,465 bytes with SHA-256
`35fe79dab413843300e1cac4d0bfa07af1641ded5083e580318697566ea75ec3`; the ZIP
is 6,165,106 bytes with SHA-256
`44118c6b303a3bd5d0cf90cc65cbbad85d4b30b45fd025ecb4fbc0362046464f`.

Owner-reported hardware evidence on a Garmin fēnix 8 AMOLED 47 mm covers BBBike
fresh install, update and remove, MapRando three-map installation, and
disconnect/reconnect inventory verification. Update/remove duration, including
remove pausing around 87% before completion, and intermittent USB/MTP stalls
remain known follow-ups; OpenTopoMap India issue
#278 remains under investigation. This release does not claim broader model
compatibility or an Edge path.

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


## Beta.17 build 39 — provider availability (PR 336)

Published on 2026-10-05, tag `v1.0.0-beta.17-build39` points to signed source
`8a709166274359061bf0776f5b6e348d8c2e4929`. Apple notarization submission
`b20e8c57-eeab-4811-92d0-9bb55c1de408` was accepted without issues. Stapling,
Gatekeeper and launch validation passed for the ZIP and DMG.

The DMG is 6,901,952 bytes, SHA-256
`3fd52d6c23177f7d20354f9ef298be8306f086f0e1e3f60ebdf5f22ded8cd745`;
the ZIP is 6,226,377 bytes, SHA-256
`4ed5db9c5e0b35349279c5091e52252f588f5c8c87dff3e2d3ca8c827442eafd`.
GitHub asset digests match these packaged artifacts. Publication metadata and
the site deployment follow the real artifact publication; a GitHub release
alone is not evidence that the site's manifest has updated.

The release adds migration 066 (default-safe provider monitoring/cooldown and
package download overrides), an hourly scheduler worker with per-provider
1/6/24-hour intervals, and additive nullable `downloadBlockReason` in the map
catalog. Schema and catalog versions remain unchanged. Backend revision
`f81eab2ef7ae41825fc0312ee7652d34041c6439` was deployed before distribution via
the normal immutable-image migration path; deployment
[37231790220](https://github.com/VooZ2/terento/actions/runs/37231790220) passed,
including live catalog and released-client checks. The scheduler and catalog
`no-store` response were verified. This release establishes no new hardware
PASS or broader model compatibility claim.

Released older clients ignore the new restriction fields; this rollout does
not retroactively enforce manual map controls in those binaries. The beta.17
native client keeps restricted maps visible, disables Install/Update, and
checks current remote eligibility before acquisition. Removal and device
ownership rules are unchanged. If the API is unreachable or its health evidence
is stale, new acquisition waits for a current response. An in-flight transfer
is not cancelled when monitoring changes. The released-client registry pins
beta.17 build 39 as the representative decoder for this behavior.


## Beta.18 build 40 — Garmin write profile correction

Published on 2026-10-05 from GitHub-verified source
`e0f0e7041e4aed9e53bdeebb226dff4cd2b6b8c5`, tag `v1.0.0-beta.18-build40`.
The shared root/storage resolver checks the complete physical profile before
acquisition and final write. Root-only canonical comparison preserves existing
manifest paths and protected-object facts. No payload fields, schema versions,
catalog routes, server codes or database migrations change. The deployed API
remains `f81eab2ef7ae41825fc0312ee7652d34041c6439` (deployment 37231790220),
which already accepts these schema-v4 preparation-failure reports. Beta.17 stays
the representative released catalog decoder; the tag CI also validates this
release source against the live catalog.

The full 83-runner packaging suite and PR/merged-source/tag CI passed, including
fresh Swift-to-API diagnostic payloads, backend integration, native mutation
safety and installation/update regressions. Apple submission
`2875108d-bf2e-4d6c-8765-cd35f0180ac5` was Accepted without issues. Signing,
stapling, Gatekeeper and ZIP/DMG launch checks passed. The owner approved the
release notes before publication. No new hardware result is claimed.

DMG: 6,908,669 bytes, SHA-256
`17dc52b1c213add8217ad6f2bee4e392e1264fb1ecccc62477c52ca5c9270755`.
ZIP: 6,233,753 bytes, SHA-256
`df5c5191d25941d251e8353b3eacd2d263085b8d09843a84bea349d74e0c0211`.
GitHub asset digests and independently downloaded draft bytes match these values;
public asset and website verification are separate publication checks.
