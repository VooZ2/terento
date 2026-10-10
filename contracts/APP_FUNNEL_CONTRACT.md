# Terento app first-run funnel contract

Status: active (backend accepts and reads; the app producer ships separately)
Schema version: 1

This document owns the meaning of app first-run funnel telemetry. It makes
pre-install failures visible in Admin: a session that never reaches an install
leaves no install, update, download or compatibility evidence, so without this
population those failures are invisible.

## Consent and privacy

Funnel events are sent under the existing device-compatibility reporting
consent (the same opt-out that controls compatibility evidence). They carry no
serial number, Garmin Unit ID, account, local path, IP-derived field or
persistent user/device identifier. `sessionId` is a random UUID created per app
launch, kept in memory only and never persisted. The server stores only the
normalized columns below and does not retain the raw JSON body or the client
address.

## Request: `POST /app-funnel/events`

JSON (`Content-Type: application/json`), at most 4 KiB, schema
[`app-funnel-event.schema.json`](app-funnel-event.schema.json). Unknown fields
are rejected with `400`. The event `id` is idempotent: a new event returns `201`,
a replay `200` and stores no second row. Validation failures return `400`, an
oversized body `413`, a wrong content type `415`, and the per-client limit
(120 events per minute, client derived behind the trusted proxy) `429`.

| Field | Rule |
| --- | --- |
| `schemaVersion` | integer `1` |
| `id` | canonical UUID; event identity |
| `sessionId` | canonical UUID; random per app launch |
| `occurredAt` | RFC 3339 UTC timestamp (`Z` or `+00:00`) |
| `appBuild` | non-blank string, at most 80 characters |
| `releaseLabel` | strict SemVer; a label ending in `-local` is stored as local test data |
| `stage` | `DEVICE_CONNECT`, `AUTHORIZATION`, `CATALOG` or `INSTALL_BLOCKED` |
| `outcome` | one of the stage's outcomes below |
| `baseModel` | optional normalized Garmin base model (for example `fenix 8`, `Forerunner 965`), at most 80 characters; only for `DEVICE_CONNECT=CONNECTED` and `AUTHORIZATION` |
| `droppedPackageCount` | optional integer ≥ 0; only for `CATALOG=REMOTE_PARTIAL` |

Optional fields may be omitted or `null`.

| Stage | Outcomes |
| --- | --- |
| `DEVICE_CONNECT` | `CONNECTED`, `TIMEOUT_NO_USB`, `TIMEOUT_USB_PRESENT`, `BUSY`, `MULTIPLE_DEVICES`, `NOT_MTP_MODE`, `DISCONNECTED`, `FAILED` |
| `AUTHORIZATION` | `APPROVED`, `PENDING`, `OUT_OF_SCOPE`, `UNKNOWN_MODEL`, `AMBIGUOUS`, `CATALOG_UNAVAILABLE`, `UPDATE_REQUIRED` |
| `CATALOG` | `REMOTE`, `REMOTE_PARTIAL`, `BUNDLED_FALLBACK`, `UPDATE_REQUIRED` |
| `INSTALL_BLOCKED` | `AUTHORIZATION`, `DEVICE_STORAGE`, `MAC_STORAGE`, `CATALOG_UNVERIFIED`, `LOCAL_CAPABILITY`, `OTHER` |

The app sends at most one event per (stage, outcome, baseModel) per session,
through the same durable queue and parking rules as other telemetry.

## Storage and retention

Migration 070 adds `app_funnel_event` (`event_id` primary key, `session_id`,
`occurred_at`, `received_at`, `app_build`, `release_label`, `is_local_test`,
`stage`, `outcome`, `base_model`, `dropped_package_count`). Database checks repeat
the stage/outcome and field-placement rules. Rows are deleted 24 months after
receipt, like the other telemetry streams. Local test rows are retained until
that retention and are excluded from every read model; the admin local-test
purge does not yet include this table.

## Read model: `GET /admin/app-funnel.json`

Admin authentication is required. `period` is `today`, `24h`, `7d` (default),
`30d` or `all`, with the windows defined in
[`STATISTICS_CONTRACT.md`](STATISTICS_CONTRACT.md); the optional `timeZone`
(IANA name; absent or unknown is UTC) sets where `today` starts and is echoed as
`timeZone`. Any other query parameter is `400`. The response reports, for the period,
the number of distinct non-local sessions with any funnel event
(`sessionCount`), the number of those sessions with no `DEVICE_CONNECT` outcome
`CONNECTED` event in the period (`neverConnectedSessionCount`), the distinct
session count for every stage/outcome pair (zero-filled), and the top ten base
models by distinct sessions with `AUTHORIZATION` outcome `PENDING`,
`UNKNOWN_MODEL` or `AMBIGUOUS`. A session that reports several outcomes counts
once in each, so outcome counts are not exclusive and their sum can exceed
`sessionCount`. Most non-`CONNECTED` `DEVICE_CONNECT` outcomes are signals seen
while the app keeps waiting (`TIMEOUT_NO_USB`, `NOT_MTP_MODE`, `BUSY`,
`MULTIPLE_DEVICES`), and `DISCONNECTED` follows a connection, so
`neverConnectedSessionCount` (not the sum of those outcomes) is the number of
sessions that did not connect. Period membership uses the event time, except that a time more
than 10 minutes after server receipt is treated as the receipt time (the same
rule as map statistics).

The read model also reports, for the same population:

- `journey`: `sessionCount`, `connectedSessionCount` (sessions with
  `DEVICE_CONNECT` `CONNECTED`) and `approvedSessionCount` (sessions with both
  `CONNECTED` and `AUTHORIZATION` `APPROVED` in the period).
- `neverConnected`: `sessionCount` (equal to `neverConnectedSessionCount`),
  `withoutConnectionSignalCount` (never-connected sessions with no
  `DEVICE_CONNECT` event at all) and `outcomes`, the distinct-session count of
  each `DEVICE_CONNECT` outcome among the never-connected sessions only,
  non-zero, largest first. These rows are not exclusive either.
- `previous`: the same `sessionCount`, `connectedSessionCount`,
  `neverConnectedSessionCount` and `approvedSessionCount` for the window just
  before the period (`today` compares with yesterday from midnight up to the
  same time; the rolling periods with the equally long window ending at
  `since`), with its `since`/`until`; `null` for `all`.
- `bucket` and `trend`: one entry per `hour` (`today`, `24h`), `day` (`7d`),
  `week` (`30d`) or `month` (`all`) in `timeZone`, with `sessionCount`,
  `connectedSessionCount` and `neverConnectedSessionCount`; a session counts
  once, in the bucket of its first event in the period. Empty buckets inside
  the period are filled with zeros for display; they are not telemetry.
- `catalogStatus` on each `modelsNeedingReview` entry: what the current
  installation policy says about that exact normalized base model
  (`NOT_IN_CATALOG`, `MAPS_UNKNOWN`, `MIXED`, `NO_MAPS`, `WITHDRAWN`,
  `APPROVED_NOW`, or `UNAVAILABLE` when the policy could not be read). It is a
  diagnostic explanation for Admin and never grants or revokes write
  authorization.

## Population boundary

Funnel sessions are a separate population. They are never mixed into fresh
install, update, download, acquisition, compatibility, model-evidence, public
compatibility or Needs attention counts, and they never grant or revoke native
write authorization. A funnel `AUTHORIZATION` outcome describes what the app
decided for that session; it is not identity evidence for a device model.
