# Terento web installer statistics contract

Status: active (backend accepts and reads; the web installer server forwards)
Schema version: 1

This document owns the meaning of web installer statistics: what the Chrome web
installer page reports about each visit, and what the installer server itself
did when it relayed a map. Owner decision 2026-10-10 (Gediminas): web installer
statistics move from the lab admin page into the production Admin, on its own
**Web installer** page, starting from empty tables (lab journal data is not
imported).

## Separate population

Web installer visits and relay jobs are their own populations. They are never
mixed into app acquisition, fresh-install, update, download, compatibility,
first-run funnel, watch (Devices) or Needs attention counts, and they never
grant or revoke write authority. The Dashboard Downloads and Installations
charts show them only behind their **Web** switch; the **App** view and every
other app statistic stay app-only.

## Privacy

Events carry no serial number, Garmin Unit ID, account, IP address, file name,
local path, map list, raw error text or persistent user or watch identifier.
`sessionId` is a random UUID made per page load, kept in page memory only. The
server stores only the normalized columns below, never the raw body or the
client address. There is no on-page opt-out in this release. Rows are deleted
24 months after receipt.

## Transport

The page never calls the production API. It posts to its own installer server
(`./api/events` on `https://lab.terento.app/install/`), which applies its
per-computer limit (kept in memory only) and forwards each accepted event, and
each finished relay job, to the production catalog API:

- `POST https://api.terento.app/internal/web-installer/events`
- `POST https://api.terento.app/internal/web-installer/relay-jobs`

Both require `Authorization: Bearer <WEB_INSTALLER_INGEST_SECRET>` (32–512
characters, its own secret, configured on the API and on the installer
server), `Content-Type: application/json` and at most 4 KiB. Unknown fields are
rejected with `400` and a short error code; a new record returns `201`, a
replay of the same `id` `200` and no second row; a wrong secret `401`; the
route limit (1200 a minute) `429`. Forwarding is fire and forget with a short
timeout: a lost record is acceptable and is never retried in a loop.

Optional fields may be omitted or `null`. `isTest: true` marks a check record
(for example a page opened with `?test=1`): it is stored, kept out of every
count, and shown only as the "Test records" line on the Web installer page.

## Page events: `/internal/web-installer/events`

| Field | Rule |
| --- | --- |
| `schemaVersion` | integer `1` |
| `id` | canonical UUID; event identity |
| `sessionId` | canonical UUID; random per page load |
| `occurredAt` | RFC 3339 UTC time the installer server received the event; a time more than 10 minutes after API receipt uses the receipt time |
| `isTest` | optional boolean |
| `stage` | `GATE`, `CONNECT`, `MAP_RESULT`, `REMOVE` or `RECOVERY` |
| `outcome` | one of the stage's outcomes below |
| `osFamily` | optional, every stage: `macOS`, `Windows`, `Linux`, `ChromeOS`, `Android`, `iOS`, `Other` |
| `osMajor` | optional integer 0–99, every stage |
| `browserFamily` | optional, every stage: `Chrome`, `Edge`, `Opera`, `Firefox`, `Safari`, `Other` |
| `browserMajor` | optional integer 1–999, every stage |
| `model` | optional watch model text as the watch reports it, lower case, `[a-z0-9 .+\-–/()]`, 1–80; not on `GATE` |
| `firmware` | optional `\d{1,5}(\.\d{1,3})?`; not on `GATE` |
| `baseModel` | optional, same rule as `model`; `CONNECT` only |
| `operation` | `install` or `update`; `MAP_RESULT` only (required there) |
| `provider` | `[a-z0-9-]{1,40}`; `MAP_RESULT` and `REMOVE` |
| `packageId` | catalog package ID `[A-Za-z0-9._-]{1,120}`; `MAP_RESULT` only |
| `sizeBucket` | `<100MB`, `100-500MB`, `500MB-1GB`, `1-2GB`, `2-4GB`, `>4GB`; `MAP_RESULT` only |
| `failureStage` | `PREPARE`, `DOWNLOAD`, `WRITE`, `VERIFY`; failed or cancelled `MAP_RESULT` only |
| `reason` | reason code below; failed or cancelled `MAP_RESULT`, failed `REMOVE` |
| `writeStarted` | boolean; `MAP_RESULT` only |
| `writeS`, `verifyS` | integer seconds 0–86400; `MAP_RESULT` only |
| `errorName` | optional diagnostic, any failure: `AbortError`, `DataError`, `InvalidAccessError`, `InvalidStateError`, `NetworkError`, `NotAllowedError`, `NotFoundError`, `NotReadableError`, `NotSupportedError`, `OperationError`, `QuotaExceededError`, `SecurityError`, `TimeoutError`, `TypeError`, `RangeError`, `UnknownError`, `Error`, `Other` |
| `httpStatus` | optional integer 100–599: the installer server's HTTP status when a download step failed |
| `mtpResponse` | optional integer 8192–43263 (`0x2000`–`0xA8FF`): the MTP response code when the watch refused an operation |

| Stage | Outcomes |
| --- | --- |
| `GATE` | `PASSED`, `PASSED_TESTING_PLATFORM`, `BLOCKED_BROWSER`, `BLOCKED_MOBILE`, `BLOCKED_PLATFORM` |
| `CONNECT` | `CONNECTED`, `NO_WATCH_CHOSEN`, `CHOOSER_TIMEOUT`, `STARTUP_ENTRY`, `MODEL_NOT_ENABLED`, `POLICY_UNAVAILABLE`, `OTHER_TAB`, `TIMEOUT`, `CONNECTION_LOST`, `FAILED` |
| `MAP_RESULT` | `SUCCEEDED`, `FAILED`, `CANCELLED` |
| `REMOVE` | `SUCCEEDED`, `FAILED` |
| `RECOVERY` | `FINISHED`, `STILL_BLOCKED` |

Page reason codes: `CANCELLED`, `WATCH_FULL`, `CHECK_MISMATCH`,
`CONNECTION_LOST`, `CATALOG_CHANGED`, `COMPUTER_FULL`, `EARLIER_CHANGE`,
`SERVER_BUSY`, `PREPARE_FAILED`, `BAD_FILE`, `DOWNLOAD_STOPPED`, `OTHER`.

The page sends one `GATE` per load, one `CONNECT` per connection attempt, one
`MAP_RESULT` per map when it ends, one `REMOVE` per removal and one `RECOVERY`
per recovery check.

## Relay jobs: `/internal/web-installer/relay-jobs`

Sent once, when the job ends (a job that a restart cut short is sent as
`INTERRUPTED` when the server starts again).

| Field | Rule |
| --- | --- |
| `schemaVersion` | integer `1` |
| `id` | the server's job reference, `[0-9a-f]{16,32}`; never the browser's job key |
| `isTest` | optional boolean |
| `requestedAt`, `finishedAt` | RFC 3339 UTC; `finishedAt` ≥ `requestedAt` |
| `readyAt` | optional RFC 3339 UTC, when the map copy was ready for the browser |
| `provider` | `[a-z0-9-]{1,40}` |
| `packageId` | `[A-Za-z0-9._-]{1,120}` |
| `region` | optional text, 1–120, no control characters |
| `release` | optional text, 1–40, no control characters |
| `sizeBytes` | optional integer ≥ 0, size of the prepared map |
| `servedBytes` | integer ≥ 0, bytes that reached the browser |
| `outcome` | `DELIVERED`, `NOT_DOWNLOADED`, `FAILED`, `CANCELLED`, `EXPIRED`, `REFUSED`, `INTERRUPTED` |
| `reason` | server reason code below; required for `FAILED`, `REFUSED`, `INTERRUPTED`, not allowed otherwise |
| `providerHttpStatus` | optional integer 100–599, only with `PROVIDER_HTTP_ERROR` |

`DELIVERED`: the browser downloaded every byte. `NOT_DOWNLOADED`: the copy was
ready but the browser let it go before it had every byte. `EXPIRED`: the copy
was never collected. `CANCELLED`: the browser cancelled before the copy was
ready.

Server reason codes and the installer server messages they replace:

| Code | Meaning |
| --- | --- |
| `NOT_REVIEWED` | provider is not enabled for relaying (redistribution review) |
| `SERVER_BUSY` | queue full or server busy |
| `COMPUTER_LIMIT` | this computer already has the maximum maps in preparation |
| `POLICY_WITHHELD` | catalog policy withholds the map (region or provider rule) |
| `NO_ARTIFACT` | unknown package, no validated main file, or unsupported size |
| `SOURCE_NOT_ALLOWED` | provider URL outside the official HTTPS allowlist or not public |
| `PROVIDER_HTTP_ERROR` | provider answered with an HTTP error (`providerHttpStatus`) |
| `PROVIDER_UNREACHABLE` | provider timed out or could not be reached |
| `PROVIDER_CHANGED` | provider file size or checksum differs from the catalog |
| `BAD_ARCHIVE` | archive or IMG failed the safety checks (entries, paths, one exact-size IMG, header) |
| `SIZE_LIMIT` | download, metadata or unpacked size above the limit |
| `DISK_FULL` | no room on the server within its budget |
| `SERVICE_RESTARTED` | the server restarted during the job |
| `OTHER` | anything else |

## Admin read model (`/admin/web-installer`)

Periods are the Admin set (`today`, `24h`, `7d`, `30d`, `all`), filtered by
`occurredAt` (events) and `requestedAt` (relay jobs). Test records are excluded
from every number below.

- **Final map result**: one per (`sessionId`, `packageId`, `operation`), the
  latest `MAP_RESULT` of that page load. A failure that a retry in the same page
  load replaced is not a final failure. **Maps installed**, **Maps updated**,
  **Failed**, **Writing** (median `writeS`, then median `verifyS`, of final
  successes) and **Recent results on watches** use final results only.
- **Watch connected**: distinct sessions with `CONNECT=CONNECTED`.
- **Watch models**: per model text and system (`osFamily osMajor`): firmware
  seen, connected sessions, final installs, updates and failures, last seen.
- **Systems and browsers**: `GATE` events per system and browser, and how many
  were blocked.
- **Connection problems** and **Install and removal problems**: every failed
  attempt (not only final results), grouped by codes, with the codes shown next
  to their plain words so a failure can be traced to its cause.
- **On the server**: relay jobs. Requests exclude `REFUSED`; Failed counts
  `FAILED`, `REFUSED` and `INTERRUPTED`; preparation time is `readyAt −
  requestedAt`, sending time `finishedAt − readyAt` of `DELIVERED` jobs; data
  sent is the sum of `servedBytes`.
- **Dashboard Web switch**: Downloads = relay jobs per bucket of `requestedAt`
  (delivered, and failed on the server); Installations = final map results per
  bucket of `occurredAt` (install succeeded, install failed, update succeeded,
  update failed).
