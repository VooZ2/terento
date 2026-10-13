# Terento web installer statistics contract

Status: active (backend accepts and reads; the web installer server forwards)
Schema version: 1

This document owns the meaning of web installer statistics: what the web
installer page reports about each visit, and what the installer server itself
did when it relayed a map. Owner decision 2026-10-10 (Gediminas): web installer
statistics move from the lab admin page into the production Admin, on its own
**Web installer** page, starting from empty tables (lab journal data is not
imported).

## Shared install statistics

Owner decision 2026-10-11 (Gediminas), replacing the earlier separate
population and the ADR 0034 thresholds: web installer results count in the
shared install statistics from the start, like app results.

- **Counted map result**: every `MAP_RESULT` attempt, like app results (not
  only the last one of a page load). `SUCCEEDED` counts as a success; `FAILED`
  counts only when `writeStarted` is `true`. `CANCELLED`, preparation and
  download failures (`writeStarted` not `true`) and connection problems never
  count. Test records never count. The API's `web_installer_map_result` view
  is this definition.
- **Download**: a relay job `DELIVERED` is a successful download; `FAILED`,
  `REFUSED` and `INTERRUPTED` are failed downloads; other outcomes do not count.
- **Watch model**: the API resolves the catalog model of each `CONNECT` and
  `MAP_RESULT` from `model` and the USB model code with the same identity
  assessment as app reports, at receipt and again on each scheduler cycle
  while unresolved. Only resolved results count per model. The assessment
  reads the reviewed generation-label aliases of
  `contracts/INSTALLATION_AUTHORIZATION.md` (a watch text `epix pro - 47mm`
  names `epix Pro (Gen 2)`), and a reported case size prefers the catalog
  rows that state that size over a same-name row with no size. Text without
  a size that several sizes share stays unresolved.
- **Learned USB code** (owner decision 2026-10-13): when the assessment leaves
  the model open, the USB model code decides it if the code names exactly one
  catalog model and the reported text names that model too
  (`identity_resolution = USB_LEARNED`). The models a code names are its
  catalog mappings that are not rejected plus every model a confirmed app
  report (resolved by exact match or Identity review, not a local test) gave
  with that code. A code alone, or a code that names several models, resolves
  nothing; a `USB_LEARNED` record loses its model on the next scheduler cycle
  once its code names several models.
- **Identity review** (owner request 2026-10-13): counted web installs with no
  model wait in Identity review like app results. An administrator assigns
  the model with the app identity form (`identity_resolution = MANUAL`; a
  model the reported text or USB code contradicts needs the explicit manual
  assignment) and can remove it again (`Unassign` on the model page). Every
  decision is audited, and a record with a decision is never resolved
  automatically again. A manual assignment never teaches a USB code.
- **Where they appear**: Dashboard charts (All, the default, App and Web
  switch), Dashboard Activity (web rows marked with the Web icon), Maps page
  and providers (combined numbers), Devices list and model pages (App, Web and
  All rows; the model page Installation history lists each counted web
  install with the Web icon), and the public Compatibility JSON and watch cards
  (`successfulInstallations` = app + web, with `appSuccessfulInstallations` and
  `webSuccessfulInstallations`).
- **What stays app-only**: the app read models and Event detail, evidence
  status (Tested/Verified), reconnect-verified installs, distinct-watch counts,
  Needs attention (except its Identity review count, which adds the counted
  web installs with no model), the first-run funnel. Web results never grant
  or revoke write authority.
- **Lab and public**: until the public web installer launches at
  `terento.app/install/`, the lab page's records count. After that launch the
  lab installer server marks all its records `isTest: true`.

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
| `browserFamily` | optional, every stage: `Chrome`, `Edge`, `Opera`, `Brave`, `Chromium` (a Chromium browser with no other brand), `Firefox`, `Safari`, `Other` |
| `browserMajor` | optional integer 1–999, every stage |
| `model` | optional watch model text as the watch reports it, lower case, `[a-z0-9 .+\-–/()]`, 1–80; not on `GATE` |
| `firmware` | optional `\d{1,5}(\.\d{1,3})?`; not on `GATE` |
| `usbVendorId`, `usbProductId` | optional integers 0–65535, both or neither; the watch's USB model code (the same for every watch of one model); `CONNECT` and `MAP_RESULT` only |
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
| `CONNECT` | `CONNECTED`, `NO_WATCH_CHOSEN`, `CHOOSER_TIMEOUT`, `STARTUP_ENTRY`, `MODEL_NOT_ENABLED`, `POLICY_UNAVAILABLE`, `OTHER_TAB`, `TIMEOUT`, `CONNECTION_LOST`, `OPEN_ACCESS_DENIED`, `INTERFACE_CLAIM_FAILED`, `USB_TRANSFER_FAILED`, `WATCH_REFUSED`, `UNEXPECTED_RESPONSE`, `FAILED` |
| `MAP_RESULT` | `SUCCEEDED`, `FAILED`, `CANCELLED` |
| `REMOVE` | `SUCCEEDED`, `FAILED` |
| `RECOVERY` | `FINISHED`, `STILL_BLOCKED` |

`PASSED_TESTING_PLATFORM`: a desktop Chromium browser with WebUSB passed the
gate on a system or browser not yet hardware-verified (Windows, Linux, or any
brand other than Google Chrome, such as Edge, Opera or Brave).
`BLOCKED_BROWSER`: the browser has no WebUSB (Firefox, Safari).

`OPEN_ACCESS_DENIED` and `INTERFACE_CLAIM_FAILED`: the system refused the browser's
USB open or interface claim before any MTP session existed (an unsupported
Windows driver, missing Linux USB permission, possibly another app). `CONNECTION_LOST` is only for a
connection that was made and then ended or became uncertain.

A setup failure before that names its cause: `STARTUP_ENTRY` (the watch's
startup USB entry was chosen, among them USB code `091e:0003`, "GPS (various
models)"), `TIMEOUT` (a USB step got no answer in time), `USB_TRANSFER_FAILED`
(the browser's USB transfer failed or ended short), `WATCH_REFUSED` (the watch
answered with an MTP error code, sent as `mtpResponse`), `UNEXPECTED_RESPONSE`
(an answer that is not the expected MTP, or a watch that does not report as a
Garmin with the needed operations), `POLICY_UNAVAILABLE` (the list of supported
watches could not be loaded, its timeout too). `FAILED` is left for anything
else.

Page reason codes: `CANCELLED`, `WATCH_FULL`, `CHECK_MISMATCH`,
`CONNECTION_LOST`, `CATALOG_CHANGED`, `COMPUTER_FULL`, `EARLIER_CHANGE`,
`SERVER_BUSY`, `PREPARE_FAILED`, `BAD_FILE`, `DOWNLOAD_STOPPED`,
`DOWNLOAD_BLOCKED` (neither the direct download host nor the Cloudflare-proxied
lab host could be reached from the visitor's network), `OTHER`.

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
| `requestedAt`, `finishedAt` | RFC 3339 UTC; `requestedAt` ≤ `finishedAt` ≤ API time + 10 minutes |
| `readyAt` | optional RFC 3339 UTC, when the map copy was ready for the browser; between `requestedAt` and `finishedAt` |
| `provider` | `[a-z0-9-]{1,40}` |
| `packageId` | `[A-Za-z0-9._-]{1,120}` |
| `region` | optional text, 1–120, no control characters |
| `release` | optional text, 1–40, no control characters |
| `sizeBytes` | optional integer ≥ 0, size of the prepared map |
| `servedBytes` | integer ≥ 0, bytes that reached the browser |
| `outcome` | `DELIVERED`, `NOT_DOWNLOADED`, `FAILED`, `CANCELLED`, `EXPIRED`, `REFUSED`, `INTERRUPTED` |
| `reason` | server reason code below; required for `FAILED`, `REFUSED`, `INTERRUPTED`, not allowed otherwise |
| `providerHttpStatus` | optional integer 100–599, only with `PROVIDER_HTTP_ERROR` |
| `servedVia` | optional: `direct` (from `dl.terento.app:8443`), `proxied` (through the Cloudflare-proxied lab host, used when the visitor's network blocks the direct port) or `mixed` (both, e.g. a resumed download) |

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

- **Counted map result** (above): **Maps installed**, **Maps updated**,
  **Failed after write start**, **Writing · median** and **Checking · median**
  (median `writeS` and median `verifyS` of counted successes) use counted
  results; **Recent results on watches** lists every
  map result and removal.
- **Connected visits**: distinct sessions with `CONNECT=CONNECTED`.
- **Watch models**: per model text and system (`osFamily osMajor`): firmware
  seen, connected sessions, counted installs, updates and failures, last seen.
- **Systems and browsers**: `GATE` events per system and browser, and how many
  were blocked, grouped by system family (`osFamily`) or by browser family
  (`browserFamily`); each family row shows its totals and opens its
  system and browser versions.
- **Problems** (connection, install and removal): every failed
  attempt (counted or not), grouped by codes, with the codes shown next
  to their plain words so a failure can be traced to its cause.
  Connection problems also show the watch models (the model text, or, when
  the failure came before the watch reported its text, the one catalog model
  that reviewed USB mappings name for its USB model code; a code shared by
  several models or with an unreviewed model names none, and this display never
  resolves or counts the event for a model), the MTP response code, and Visits: distinct
  sessions (page loads), so one person's retries are not read as many people.
  They are grouped by problem, system family or browser family; each group row
  shows its own distinct Visits (not the sum of its rows), count, watch models
  and last time, and opens its rows.
- **Server**: relay jobs. Requests exclude `REFUSED`; Failed counts
  `FAILED`, `REFUSED` and `INTERRUPTED`; preparation time is `readyAt −
  requestedAt`, sending time `finishedAt − readyAt` of `DELIVERED` jobs; data
  sent is the sum of `servedBytes`; sent through Cloudflare counts `DELIVERED`
  jobs with `servedVia` `proxied` or `mixed`.
- **Export** (`/admin/web-installer.csv?period=…&timeZone=…`, Admin session
  only): one CSV row per page event and relay job of the period, newest first,
  test records excluded, no row limit. Columns: Time (Admin time zone), Record
  (Page/Server), Step, Action, Result (stored outcome), Problem (plain words),
  Failed step, Reason, Error, HTTP (`httpStatus`, or `providerHttpStatus` for a
  job), MTP, Write started, Watch (model text), Catalog model, Firmware, USB,
  System, Browser, Provider, Package, Region, Release, Size (bucket), Size
  bytes, Sent bytes, Sent via, Writing s, Checking s, Preparing s, Sending s,
  Visit (session ID), ID. An unknown value is empty, never 0; text starting
  with `=`, `+`, `-` or `@` is prefixed with `'` so a spreadsheet does not run it.
- **Dashboard Web switch**: Downloads = relay jobs per bucket of `requestedAt`
  (delivered, and failed on the server); Installations = counted map results
  per bucket of `occurredAt` (install succeeded, install failed, update
  succeeded, update failed). The All view adds them to the App view per bucket.
