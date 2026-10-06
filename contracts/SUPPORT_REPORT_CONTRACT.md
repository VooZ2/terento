# Terento support report contract

Status: active (backend accepts, stores and shows reports in Admin; the app
sender ships separately)
Schema version: 1

This document owns the meaning of support reports: the already-sanitised local
issue report that a user explicitly chooses to send to Terento ("Send report
to Terento"), so that a user without a GitHub account can still report a
problem. The GitHub issue option stays available and unchanged.

## Consent and privacy

A report is sent only after an explicit per-send action in a sheet that shows
exactly what will be sent. That consent is independent of the automatic
telemetry and diagnostic-sharing toggles: a report the user chose to send is
allowed even when automatic sharing is off, and turning sharing on never sends
a support report.

A report carries no serial number, Garmin Unit ID, account, username, local
path, raw log, file content or map content, and the server never stores the
client IP address (the trusted-proxy client address is used only by the
in-memory rate limiter). The `report` object is a closed structure of the
facts already shown in the sanitised GitHub issue report; unknown keys are
rejected at every level. Free text (`title`, `stage`, `message`, lifecycle
facts and the optional description) must be passed through the app's
`DiagnosticReportSanitizer` first; the server additionally rejects text
containing a local path marker (`/Users/`, `file://`, `/private/`,
`/Volumes/`, `\Users\`) or control characters. Reports are used only to
diagnose the reported problem.

## Request: `POST /support/reports`

JSON (`Content-Type: application/json`), at most 64 KiB, schema
[`support-report.schema.json`](support-report.schema.json).

| Field | Rule |
| --- | --- |
| `schemaVersion` | integer `1` |
| `id` | canonical UUID; report identity and idempotency key |
| `createdAt` | RFC 3339 UTC timestamp (`Z` or `+00:00`) |
| `appBuild` | non-blank string, at most 80 characters |
| `releaseLabel` | strict SemVer; a label ending in `-local` marks a local test report |
| `category` | `INSTALL_FAILED`, `UPDATE_FAILED`, `REMOVE_FAILED`, `CONNECTION` or `OTHER` |
| `operationId` | optional UUID of the failed operation (the report's Installation ID) |
| `userMessage` | optional description, 1–2000 Unicode scalar values, at least one non-space character; newlines and tabs allowed |
| `report` | required structured report, below |

Optional fields may be omitted or `null`.

### `report` keys

Keys mirror the sections of the GitHub issue body built by
`app/TerentoCore/Sources/TerentoPoC/Diagnostics/InstallationIssueReport.swift`.
Unknown values are omitted, never sent as `Unavailable`. "Text" means a string
without control characters, leading or trailing whitespace or a local path
marker; limits are in Unicode scalar values.

| Key | Type and limit | GitHub report source |
| --- | --- | --- |
| `macOSVersion` | **required** text ≤ 120 | Operation · macOS |
| `title` | text ≤ 180 | issue title |
| `operation` | `INSTALLATION`, `UPDATE` or `REMOVAL` | Operation · Operation |
| `stage` | text ≤ 120 | stage label |
| `failureStages` | 1–8 texts ≤ 120 | Summary · Failure stage |
| `errorCategory` | text ≤ 80 | Summary · Error category |
| `errorCodes` | 1–8 codes `^[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}$` | Summary · Error code |
| `message` | text ≤ 500 | Failure details · Detail |
| `device` | object, at least one of `model` ≤ 120, `variant` ≤ 120, `family` ≤ 120, `firmware` ≤ 40, `mtpModel` ≤ 120 | Device (model name strings only) |
| `maps` | 1–8 objects: `provider` (required) ≤ 80, `region` ≤ 200, `package` ≤ 200, `release` ≤ 80, `plannedBytes` integer 0…2^53−1 | Map packages |
| `writeStarted`, `objectCreated`, `cleanupAttempted`, `cleanupSucceeded` | boolean | Failure details |
| `transferProgressPercent` | integer 0…100 | Failure details · Transfer progress |
| `verification` | object: `originalFailure`, `cleanupFailure`, `transportClassification`, `failedComponent` (codes as above); `sourceBytes`, `remoteBytes`, `transferredBytes`, `elapsedMilliseconds`, `sampledBytes` (integer 0…2^53−1); `sampleCount`, `matchedSampleCount` (integer 0…2^31−1) | Verification details |
| `lifecycleFacts` | 1–16 texts ≤ 500 | Verification details (lifecycle lines) |
| `failureContext`, `originalFailureContext` | the closed failure-context object of `compatibility-event.schema.json` (same enums, counts and protection rules) | Structured / Original failure context |
| `finishingTrace` | 1–64 lines ≤ 300, each `FINISH_TRACE swift|native` followed by `key=value` tokens (lowercase keys, values limited to `A–Z a–z 0–9 _ . -`) including one `event=` token | Finishing diagnostics (already filtered by `FinishingTrace.safeLine`, `t`/`pid`/`child`/`trace` tokens removed; lines that do not match are omitted by the client) |

The report's random Diagnostic ID and the constant `Transport: MTP` line are
not sent.

### Responses

| Status | Body | Meaning |
| --- | --- | --- |
| `201` | `{"reference":"TR-XXXXXX","status":"stored"}` | new report stored |
| `200` | `{"reference":"TR-XXXXXX","status":"duplicate"}` | replay of an existing `id`; the stored report is unchanged |
| `400` | `{"error":"<code>"}` | validation failure (for example `unknown_fields`, `unknown_report_fields`, `invalid_userMessage`, `invalid_report_message`) |
| `409` | `{"error":"reference_conflict"}` | another report already owns this reference; create a new `id` and send again |
| `413` | `{"error":"invalid_size"}` | body empty or larger than 64 KiB |
| `415` | `{"error":"invalid_content_type"}` | not `application/json` |
| `429` | `{"error":"rate_limited"}` | more than 10 reports per client per minute (client derived behind the trusted proxy) |
| `503` | `{"error":"support_reports_unavailable"}` | storage unavailable; keep the report locally and offer Try again |

The reference is deterministic: `TR-` followed by the first six characters of
the RFC 4648 base32 encoding (uppercase, alphabet `A–Z2–7`) of the SHA-256
digest of the lowercase canonical UUID string. For example
`6f1d2c3b-8a4e-4f60-9b7a-2c1d0e9f8a71` → `TR-FYMEFT`. A retry with the same
`id` therefore always returns the same reference. Six base32 characters allow
about 10^9 values, so a `409` is practically never seen.

## Storage and retention

Migration 071 adds `support_report` (`id` primary key, unique `reference`,
`received_at`, `created_at`, `app_build`, `release_label`, `is_local_test`,
`category`, `operation_id`, `user_message`, `report` JSONB, `status`
`OPEN|HANDLED`, `handled_at`, `handled_by`, `linked_github_issue`, `note`,
`updated_at`) and `support_report_audit`. Reports are deleted **12 months after
receipt**, whatever their status, by the scheduled retention job that also
prunes telemetry; their audit rows go with them. Local test reports
(`-local`) are also deleted by the Admin Test data purge.

## Admin

Support reports are operator work, shown under Dashboard → Needs attention →
Support reports (open reports from public builds) and on
`/admin/support-reports`. An administrator can mark a report handled or reopen
it, link or unlink a Terento GitHub issue and keep a short note; every change
is authenticated, CSRF-protected and audited and never changes the received
report. A report with an `operationId` links to the public installation or
update diagnostics of the same operation when they exist. Local test reports
appear only under Tools → Test data. Presentation rules are owned by
`backend/catalog-api/docs/admin-behavior-contract.md`.

## Population boundary

Support reports are never statistics. They never enter acquisition,
fresh-install, update, download, compatibility, model-evidence, funnel or
public compatibility counts, never create identity evidence, and never grant or
revoke native write authorization.
