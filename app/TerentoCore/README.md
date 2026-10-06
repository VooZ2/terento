# Terento native core

## Local update diagnostic continuation — 2026-10-02

The working tree accepts both reviewed BBBike README date layouts. Safe Update
now retains an explicit `writeStarted` fact at the transport write boundary,
including failures that return no remote object. Update completion produces a
schema-v4 diagnostic with `operationKind=update`, a shared operation ID, closed
failure stage/code and `oldMapPreserved`. The local issue report uses that same ID.
Pre-write failure is `NOT_STARTED`; only successful updates or failures after
the write boundary emit terminal map-update statistics.

These reports reuse `InstallationEvidenceController` delivery and its sharing
preference. Backend migration 064 and matching intake must be deployed before
this app producer is released. Backend storage is update-only, separate from
installation compatibility evidence and counts. Raw local reports remain on the
Mac. This is a local implementation description, not a new published release or
real-device acceptance claim; see `contracts/APP_API_RELEASE_CONTRACT.md`.

This is the production SwiftPM module and native regression harness consumed by
`Terento.xcodeproj`. `app/Terento/` owns the macOS shell and packaging resources.
The retained `TerentoPoC`, `TerentoWriteTest` and `TerentoInterruptionTest` target
names are implementation identities, not a claim that the product is a prototype.

Current release identity and beta limitations are in
[release notes](../../RELEASE_NOTES.md). Terento supports macOS 13+ on Apple
Silicon. Production builds bundle source-built arm64 libmtp/libusb; users do
not need Homebrew. See [packaging](../../Packaging/README.md) and
[third-party notices](../../THIRD_PARTY_NOTICES.md).

## Current functionality

The app connects a map-capable Garmin smartwatch, resolves provider metadata,
downloads to the Mac, validates the source package and Garmin image, checks
storage, installs, verifies the transfer, and records local ownership.

Device discovery starts automatically. While no Garmin is on USB, the Device
page shows a calm "Connect your watch" checklist and polls only the USB device
list; libmtp is not entered and no timeout runs. The 2-minute connection window
starts when a Garmin USB device appears. More than one Garmin, a watch held by
another app (repeated session-open failures) and a Garmin that never appears as
a file-transfer device are shown while discovery keeps polling; only
not-yet-enumerated and transient read failures are silent retries. After a
timeout, a failed check or an unexpected disconnect, unplugging and reconnecting
the watch restarts discovery. `DeviceConnectOutcome` exposes each episode
outcome for the first-run funnel; `DeviceEngine` itself sends no telemetry.

While maps are downloaded and checked on the Mac, or the no-write preflight
runs, the install page offers Cancel; it uses the existing task cancellation
and workspace cleanup, and nothing has been written to the watch. Once the
install step owns the device it is not cancellable. After a failure in which
nothing was written, validated provider artifacts are kept for 30 minutes,
keyed by package and artifact with their SHA-256; Try again (offered for
download, connection, pre-write check, write-start and authorization-check
failures) keeps the selection, rereads the watch and reuses them instead of
downloading again. Availability is rechecked and the coordinator revalidates
identity, version, size and SHA-256 before any write. Quitting removes retained
artifacts. While maps are downloaded, prepared, written or verified, and during
Update and Remove, the app holds a user-initiated activity that prevents idle
system sleep; Quit during a device write asks for confirmation. The app has one
main window; reopening it shares the same engines and lifecycle model.

Before a download starts, Terento checks that the Mac's temporary and Caches
volumes have about 2.5 times the download size free. A full disk before or
during download, copy or extraction is reported as "Your Mac doesn't have
enough free space (needs X GB)", never as a connection problem. Downloads are
written in the chunks URLSession delivers instead of byte by byte, with the
same 64 KiB progress cadence, reviewed redirect policy, 30-second inactivity
bound and BBBike source-proof checks. Download files left in the temporary
directory by a crash (`terento-map-download-*`, untouched for an hour) are
removed at launch. Every map scan, including the one after an install, Update
or Remove, refreshes the watch's free space for the Device page and the storage
planner. A failed map read on a connected watch shows "Couldn't read your
maps" with Try again. When an install fails after a map object was created,
the original cause stays the primary message, followed by "The map file may be
on your watch. Open Manage maps to remove it, then install it again." and a
"Go to Manage maps" action; automatic cleanup is still declined.

The review Install action starts from idle. After successful preflight, the
engine continues automatically; its transient `awaitingConfirmation` phase is
processing, not a second executable Install action. Authorization, device
identity and pre-write safety checks still apply to the continuation.

Freizeitkarte, OpenTopoMap, MapRando and BBBike use the shared lifecycle.
BBBike and BBBike (Ontrail) are separate map types from one provider; opposite
same-region types conflict and cannot be installed together. OpenTopoMap
contours are optional source-validated components, not a Debug-only feature.
Compatible local IMG imports have no automatic provider update path.

Install Maps provides geographic and provider/type filtering, local search,
retained selections and one-provider batches. Filtering uses a cached
presentation index and does not rescan the device. Manage Maps exposes current
owned-map lifecycle actions and exact valid external-map removal with
separate confirmation. About is opened through `Terento → About Terento`;
Diagnostics contains sharing settings. The sidebar remains Device, Install
maps, Manage maps. UI layout and exact copy are reviewed visually; tests should
protect actions, state transitions, accessibility and data contracts.

## Safety and verification

Ownership requires BOTH an approved managed filename and the exact file in the
local device manifest. Garmin maps, GMA/UNL and protected system files remain
read-only. A valid IMG with no identified provider may be removed explicitly,
including an unowned file with a Terento-style name. Each external row represents
one exact file; separate confirmation and a fresh live identity/header check are
required. Invalid/unreadable images and ambiguous multi-file targets remain blocked;
recognition never confers ownership. Protected filename checks apply in both
Swift and the native delete bridge.

BBBike inventory joins both fixed description fields and recognizes the complete
source path, style and BBBike.org marker, corroborated by its binary creation
date. An old exact manifest entry without BBBike context can then be recognized;
a truncated path/style is never guessed. Duplicate or contradictory contextual
records do not grant ownership.

Removal content check (inside the native delete session, after the exact live
object is resolved and before `DeleteObject`):

- Terento-managed map with a recorded removal proof (Remove and Update's
  old-map removal): only the recorded sampled regions are read. At install or
  update time, after the written object passed its verification, Terento records
  in the local manifest entry a format-1 proof computed from the validated local
  artifact in one pass that also re-hashes the whole file against the recorded
  SHA-256: 32 non-overlapping 65,535-byte regions (2,097,120 bytes; maps up to
  that size are covered completely), always including the first region with the
  `DSKIMG`/`GARMIN` header and the final bytes, the other 30 spread one per equal
  stratum by a seed derived from the artifact SHA-256, plus the SHA-256 of the
  concatenated regions. The native mutation authorization carries the plan and
  digest; the bridge validates the exact geometry itself, reads each region from
  the object resolved in the same session (unique `/GARMIN` entry, filename,
  size, storage, parent folder), checks the IMG header, compares the digest, and
  re-confirms the same object handle, name and size before the authorized delete.
  Any mismatch, read error, malformed or partial proof refuses the delete
  exactly as before; it never falls back to another check. This is sufficient
  because the proof is not a claim about an unknown file: it binds the exact
  object Terento itself wrote, verified and recorded on this Mac to sample
  digests of those same bytes, and the same-session identity checks are
  unchanged. A same-name, same-size replacement that differs only outside the
  sampled regions is not detected by this check; the ownership, identity and
  protected-file rules still apply. A 434 MB map is read as about 2 MB instead
  of 434 MB (the fake-libmtp harness reads 2,097,120 bytes in 32 requests instead
  of 434,000,000 bytes in 6,624).
- Terento-managed map without a proof (entries written before this format, a
  proof that does not exactly match the entry's size and SHA-256, failed-install
  recovery records): the full SHA-256 of the object, as before.
- External (not Terento-managed) map: always the full SHA-256 of the object
  confirmed by the user; the native external delete refuses any sampled proof.

The manifest change is additive: `removalProof` (`format`, `regionLength`,
`offsets`, `sha256`) is optional per entry. Older entries decode unchanged, are
re-encoded without the key, and an unreadable proof leaves the entry readable
with the full check. Older app versions ignore the field.

A safe update downloads and validates the replacement, checks space for both
versions, uploads and verifies the replacement, then removes the old owned
version. Insufficient space stops the update. Interrupted transfers must not
remove a known-good version. The update does not create a persistent local
backup; the existing device object is the recovery boundary until the new
object is verified. Recovery records retain exact created-object
identity; cleanup never expands into heuristic deletion. The write profile is
bound from the live Garmin USB identity and read-only `/GARMIN` inventory; it
does not contain a model allowlist.

Manage maps shows a determinate bar, percentage and current action throughout
Update. Downloading and Installing retain their byte counts and transfer speed.
Preparing reports completed package checks and measured local hashing; Checking
combines local source validation with measured read-back/hash validation of the
installed map. Verifying separately reports validation of the newly written map.
Removing old reports measured content verification before deletion (the
sampled removal proof, or the full read without one), and
Finishing advances through the existing confirmed checks. Each
percentage belongs to its displayed stage, not the whole update or time remaining.
Stage weights allocate work; they do not predict duration. ZIP extraction, device
inventory and the deletion command itself do not expose intermediate completion, so
progress holds at the last completed checkpoint with an action description until
the call returns. Unknown download lengths remain at 0% until a total is known;
no timer fabricates progress. Device safety checks and mutation order are unchanged.
Remove and Update's old-map removal reserve 20–90% for the content check
immediately before deletion (the recorded sampled proof of a managed map, which
usually ends before the 5-second estimate warm-up, so no time estimate appears,
or the full SHA-256 read otherwise). The internal C bridge reports bytes read
without changing read sizes, content/identity checks or authorization. Read
completion is not deletion success: hash or target mismatch still prevents the
destructive call. At 93%, the UI says “Confirming the map was removed”; repeated
inventory checks hold that value rather than increasing it for each retry. Only
confirmed absence completes removal. The existing settle delays and retry limits
are unchanged. No watchdog, shortened timeout or new USB recovery is introduced.

This change is a candidate for the next app release; automated tests do not replace
a real-device large-map update acceptance check.

Remote transfer verification uses the implemented bounded sampled-read policy;
it is not a claim of a whole remote-file SHA-256. Sample workers have a
120-second advancing-byte inactivity limit and a 600-second absolute limit.
Only strictly increasing validated progress renews inactivity. Cancellation
reaps the owned child before releasing its lifecycle lease.
Connection/inventory and readback failures may still require physical reconnect.

The detection snapshot and the map scan's snapshot, inventory and map-header
reads also run in that bounded worker, so a stalled watch can no longer hold the
operation gate indefinitely. The detection snapshot has a 90-second bound. Scan
inventory allows 60 seconds plus 30 ms per object seen by the previous inventory
of the same watch, at most 600 seconds (600 seconds before the first
observation); header reads add 5 seconds per map. When a bound is reached the
worker child is ended, the gate is released and the user sees "The watch stopped
responding. Unplug it, wait 5 seconds, plug it back in." Later reads of that scan
fail immediately instead of retrying file by file. What is read is unchanged; the
detection IPC carries the device descriptor and serial inside the private,
per-operation worker directory, which is removed afterwards. USB presence probes
stay in-process because they only read the USB device list.

For issue #222, a local follow-up now classifies a pre-write inventory worker
timeout as preflight MTP-read failure instead of verification failure, records
the measured bounded wait, and never starts upload when inventory has not
completed. The pre- and post-write inventory worker bound scales with the
object count of the baseline inventory: 60 seconds (libmtp's LONG_TIMEOUT)
plus 30 ms per object, at most 600 seconds. A heavy watch with years of
activities and music (about 12,000 objects) therefore gets about 7 minutes
instead of a fixed minute; this is not a model-specific USB workaround. These
reads now use the map scope described under "Map-scope protection inventory"
below, so the bound (still derived from the full scan count) is an upper limit
rather than an expected duration. Local sanitized
trace markers separate session open, file-list read, session close and native
cleanup. The initiating 091e:51b5 hardware stall remains unproven pending a
controlled failing/successful-model retest.

Installation/removal evidence is model-specific. On 2026-10-02, the owner
confirmed **BBBike Update — PASS** and **MapRando Update — PASS** on Garmin
fēnix 8 47 mm AMOLED using beta.15 build 37 after a Migration Assistant transfer
to another Mac. This is owner-reported hardware evidence, not independent
verification or evidence for other models/variants. Two real newer-release
update checks remain: **Freizeitkarte** and **OpenTopoMap**. These results do
not establish the cause of the earlier update-blocking message or confirm a
code fix. No new release or API deployment is implied. See
[historical evidence](../../history/README.md).

## Catalog and privacy contracts

The current app uses `/maps/catalog-v4.json`. Legacy v2 and v3 routes retain
provider sets understood by older clients. The full bundled fallback is a
native decoder projection; it must not be silently rewritten into an API schema.
See [shared contracts](../../contracts/README.md).

The remote catalog is accepted per package: incompatible packages are omitted
and counted (`catalogDroppedPackageCount`) while every other map stays
installable. An incompatible catalog document keeps the local list browsable,
shows "Update Terento to install maps from the current catalog" and blocks
downloads with an update message instead of "check your connection"; a real
network failure keeps the existing local-catalog fallback. Connect and the
five-minute refresh share one load, merge and validate path, and the refresh is
skipped while the review or install step is open, so selections are not pruned.

Maps come directly from provider infrastructure. Catalog visibility is separate
from acquisition: canonical Russia and Crimea packages are withheld before
workspace creation or HTTP acquisition. Existing device files remain protected.

Manifests and device identifiers stay on the Mac. Compatibility and map-use
reports are privacy-minimised and enabled by default; either stream can be
turned off in Diagnostics. Custom maps contribute compatibility evidence and
eligible common fresh-install totals, but no provider-download event or guessed
catalog geography.
Strict `-local` labels keep local-test events outside public aggregates.
Report issue opens a user-reviewed GitHub draft; raw logs are not automatically
uploaded. "Send report to Terento" (failure dialog, Diagnostics, Help menu) is the
alternative without a GitHub account; see "Support reports" below. App updates use metadata checks and an explicit official-download
handoff, never silent application replacement.

Map-use delivery drains events appended during an in-flight upload before
reporting the queue uploaded. Retryable failures retain the queue and use the
existing bounded retry schedule. A non-retryable HTTP 4xx rejection parks only
that event (status, count, time and build are kept locally) and later events
continue in order; parked events are retried only by a new app build or after a
24-hour back-off, a bounded number of times, and expire with the 24-month
retention window. Compatibility/update diagnostics use the same parking rules.
Opt-out clears pending and parked events and stops the sender before another event is sent.
Telemetry queues, diagnostic stores and the compatibility-status cache are written with
`completeFileProtectionUntilFirstUserAuthentication`: still encrypted at rest, but writable
while the screen is locked, so a long operation that finishes on a locked Mac keeps its
results instead of failing the write.

The first-run funnel producer (`Telemetry/AppFunnelTelemetry.swift`, schema v1,
`POST /app-funnel/events`; meaning owned by `contracts/APP_FUNNEL_CONTRACT.md`)
records pre-install outcomes under the device-compatibility reporting
preference: device connect, resolved authorization (with the normalized base
model), catalog load result (`REMOTE`, `REMOTE_PARTIAL` with the dropped package
count, `BUNDLED_FALLBACK`, `UPDATE_REQUIRED`) and Install presses refused before
any device write. The session ID is random per launch and memory-only; at most one
event per stage, outcome and base model is queued per session in a durable outbox
with the shared parking rules. Turning off compatibility reporting clears it.
Connect outcomes are inferred from Device state until the connect classifier
calls `AppFunnelTelemetryController.recordDeviceConnect` directly. The API route
must be deployed before a release ships this producer; until then the route's
rejection parks events without affecting other telemetry.
A response already in flight cannot restore the opted-out status. This does not
add cancellation/interruption events or reconstruct missing historical outcomes;
a download start without a received outcome is not proof of a failed download.

### First-run additions (local candidate)

- **Support reports** (`Diagnostics/SupportReport*.swift`, `POST /support/reports`,
  schema v1; meaning owned by `contracts/SUPPORT_REPORT_CONTRACT.md`). The sheet
  shows exactly the JSON that Send uploads: the structured form of the sanitised
  GitHub report (unknown values omitted, never "Unavailable"; no serial, Unit ID,
  account, local path, raw log or file content; the Diagnostic ID and
  `Transport: MTP` line are not sent) plus an optional description of at most
  2000 characters. Nothing is sent before Send, and sending does not depend on
  the sharing toggles. The reply's reference is shown ("Report TR-XXXXXX sent");
  409 resends once under a new id; 429, 503 and network failures keep the report
  in `Application Support/Terento/support-report-unsent.json` and offer Try
  again with the same id. Saved failures keep their structured fields in
  `failure-report.json` beside `failure-report.md`, so the Diagnostics and Help
  menu entry points send the full report; without one only `macOSVersion` and a
  chosen category are sent. `-local` builds are marked by `releaseLabel`. The
  API must be deployed before an app that sends reports is released.
- **Help links.** `Errors/TroubleshootingHelp.swift` is the only mapping from
  connection outcomes, authorization verdicts, catalog/acquisition errors,
  storage, post-write and Update/Remove states to the anchors of
  `https://terento.app/guides/troubleshooting/` (English URL). Links reuse the
  existing app referral parameters (`utm_source=terento_app`,
  `utm_medium=referral`) with `utm_campaign=app_troubleshooting` and
  `utm_content=<anchor>` (Help → Troubleshooting uses `help_menu`), followed by
  the `#<anchor>` fragment; no model, version or id is added. A "Help" text link
  appears next to those messages; it is never a primary button.
- **Install selection guidance.** Every selectable map row shows the catalog
  download size and "about N min" ("Download 412 MB · about 7 min") from the
  median of the last five measured download speeds on this Mac (30 days, local
  only) or a conservative 1 MB/s. While no map on the watch is managed by
  Terento (first map selection only), the locale recommendation is also
  highlighted with "Recommended for your region" (never selected
  automatically), and "Keep the watch connected and the Mac awake until Terento
  finishes." appears once a map is selected.
- **Resumed downloads.** A provider download that fails or is cancelled after at
  least 1 MiB is kept for 30 minutes when the server advertised byte ranges with
  a strong validator (non-weak ETag or Last-Modified), sent no content encoding
  and did not redirect to another host. Try again sends `Range` and `If-Range`;
  a 200, changed validator, size or host, 416 or malformed range restarts from
  zero. BBBike source-proof downloads are not resumed. Final size, identity,
  version and SHA-256 validation is unchanged; quitting removes partial files and
  the launch scavenger removes stale ones.
- **Time left.** "About N min left" is shown only for measured phases (download,
  device write, read-back, Update/Remove content checks) after a 5-second, 2 %
  warm-up, from a smoothed measured rate; it disappears after 15 seconds without
  progress and never appears for checkpoint-only phases.

These are local changes, not release or hardware evidence.

## Build and automated validation

Use Xcode with Swift 6 and macOS 13+ SDK support. The development SwiftPM bridge
uses libmtp/libusb from Homebrew or `LIBMTP_PREFIX`; distribution uses bundled
libraries. Node.js 22 is required for cross-component checks; backend tests use
Python 3.12/3.13 and the declared test dependencies.

From the repository root:

```sh
swift build --package-path app/TerentoCore
Tests/run-app-tests.sh
Tests/run-native-tests.sh
```

The app suite owns UI wiring contracts. The native suite owns device safety,
provider acquisition/identity, manifests and lifecycle behavior. The diagnostics
runner compiles a `TERENTO_TESTING`-only task observer so tests await the real
automatic upload rather than sleeping for a guessed 180 ms. The observer is
absent from app builds; no production retry policy is changed. Map-statistics
tests similarly observe real record/send task completion and hold one fake
response until a terminal event is durably queued. They cover queue draining,
retry exhaustion, permanent failure and opt-out during delivery without using
real telemetry endpoints.

Filter timings are always reported. For a controlled-machine performance gate,
set `TERENTO_ENFORCE_FILTER_BENCHMARK=1` when running the native map-selection
runner; the p95 threshold remains 16 ms. Functional and fixture checks always run.
See [test and CI policy](../../Tests/README.md) for selection and failure evidence.

## Developer hardware tools

`run-write-test.sh` and `run-interruption-test.sh` are developer-only tools.
They require explicit authorization for the exact device operation; never run
them as ordinary CI or infer general map compatibility from them. Read each
script's guard and target description before use. A failed exact-target check
must stop, not trigger broader cleanup.

For an authorized connection check, close other MTP clients, launch Terento,
connect the watch, inspect exact model/variant/firmware and storage, then check
disconnect/reconnect behavior. Automatic connection is the current app flow;
old “Read device” prototype instructions are not current UI. On-watch map
visibility/usability and other-provider update acceptance require separate
hardware evidence; the BBBike result above remains owner-reported.

## Exact-model diagnostic metadata

The XML reader accepts the official namespaced GarminDevice v2 `Device` root
and the legacy `GarminDevice` root, and independently extracts Model/Description
and Model/PartNumber,
including when the local Unit ID is unavailable or invalid. Existing local
identity keys, ownership and install/update/remove sequences are unchanged.
Write profiles are now live-bound and model-neutral; a missing XML document
preserves valid MTP DeviceInfo.
AMOLED/MicroLED/MIP, Solar and inReach are separate reported properties;
missing words do not mean false. Technical originals appear in Diagnostics
only in Debug builds with a `-local` release label. Public Diagnostics keeps
sharing controls and delivery status without connected-device technical fields;
the bounded API report fields are unchanged.
Opening Diagnostics neither sends a report nor starts a device operation.

Model labels and catalog IDs have no compiled per-model identification rules.
The client fetches public catalog v2 without uploading device observations,
then compares original model/size/screen/features conservatively. Shared or
missing variant evidence cannot assign a unique exact catalog ID for
model-specific diagnostic linkage. That linkage rule is separate from write
authorization, which matches a base model and evaluates Maps capability across
all remaining candidates. Catalog-derived screen properties are labelled
separately from MTP/XML observations; a submitted catalog ID remains a hint,
not identity proof. API failure preserves raw device metadata. The local
Map Manager registry is presentation/classification evidence, not a write
allowlist; native write permission comes from fresh API catalog authorization.
Historical manifest naming is frozen in the storage layer and is never a
model-identification source.

The existing v4 event queue sends bounded optional model and component-outcome
fields, with the existing diagnostic opt-out and local-test partition. The API
must accept these additions before releasing the app. The published release
remains whatever the canonical update manifest records. A read-only Mac-side
observation of fēnix 8 47 mm
received original XML AMOLED text and code 006-B4536-00; this is metadata
evidence for that watch, not other variants or map lifecycle acceptance. Map-operation safety
regressions remain required; no new install/remove hardware test is introduced.


### Device display labels

Connected-device headings format model names for display only; the model keeps
Pro, generation and size-family suffixes, while size, screen, Solar and inReach
appear in the subtitle in that order. Supplied special editions remain visible.
Commas separate variant facts; firmware remains a separate subtitle segment.
Missing specifications are not inferred from model names. This formatting does
not alter identity/evidence strings, catalog matching, local manifest keys or
installation authorization. The Map Manager registry includes the officially
documented fēnix 9 family; exact-model public evidence remains independent.
That local registry is presentation evidence, not a native write allowlist; it
never disables a server-approved Install action and is hidden on the Device
page once the watch is "Ready for maps".
The install/update path requires fresh API catalog authorization before
acquisition and again before writing. It matches a normalized base model and
filters candidates only with reliable variant facts. Conflicting variant
evidence broadens the candidate set rather than denying authorization; the
Maps capability of all remaining candidates determines the result. Unknown
base models, mixed or unknown candidate capability, and unavailable policy
remain pending/fail closed. See the [tracked authorization contract](../../contracts/INSTALLATION_AUTHORIZATION.md).
After connect the Device page shows the verdict with text and an icon: "Checking…"
while the policy is resolving (never a connection error), "Ready for maps",
"Not yet enabled for this model" for PENDING/unknown/ambiguous models (browsing
stays available and Install maps is labelled), "Not available for this model",
or "Couldn't check" with Try again when the policy could not be fetched. The
five-minute catalog timer re-resolves an unavailable policy. A decision fetched
at download time is applied to `DeviceEngine`, so a rejection is shown on the
review page instead of silently returning to it. These are presentation and
retry changes only; the authorization rules are unchanged.
The public beta.15 build 37 passes the connected-device authorization state into
the map engine and shows pending or blocked authorization on the Install review
screen. It also removes obsolete internal installation/update paths while
retaining the current safety boundaries. Owner hardware evidence covers a
Garmin fēnix 8 AMOLED 47 mm: BBBike install/update/remove, MapRando multi-map
installation, and disconnect/reconnect inventory verification.

### Provider download failures

Install and Update name the map provider when its download server cannot be
reached or returns an error. A timeout says the server did not respond in time;
it does not claim a confirmed provider outage. Offline errors identify the Mac's
connection. Server errors, missing downloads, rejected requests and rate limits
have separate guidance. Update preserves the typed, safe acquisition message
instead of replacing it with a generic failure; raw paths and unclassified
technical errors remain excluded from normal UI.

Provider downloads use a 30-second request inactivity timeout, not a 30-second
limit on the full map download. Structured network failures do not trigger an
additional health probe before showing the error. Downloads still come directly
from reviewed provider sources. A failed update download stops before device
writes and leaves the installed map intact.

### Map acquisition reporting

The app records each provider component acquisition directly through the shared
statistics controller, including checking/unpacking, cancellation and interruption.
The atomic local event queue journals active acquisitions; a subsequent launch
closes unfinished entries as interrupted, retaining their original build/provider
identity. Disconnect records interruption before clearing map state. Opt-out
clears both queued events and journal entries. Delivery remains bounded/retryable
and independent of installation safety. An absent server outcome is not proof
of download failure. OTM main maps and contours use separate random acquisition
IDs; manually imported IMG files do not create provider-download events, but
their eligible main-map results participate in the shared fresh-install read
model without guessed provider or geography. The API migration that introduced
these fields is append-only and must be deployed before distribution of a
client that emits them.

### Operation-owned installation reports

`InstallationOperationDiagnostics` captures the operation ID, initial device
identity and selected maps when MapEngine starts an operation. Workers report
actual component outcomes directly, independently of ConnectScreen lifetime.
The existing `InstallationEvidenceController` persists and retries one event ID
per map, using the same operation ID as map statistics and preserving the
compatibility sharing preference. Untouched maps after a failure are
`NOT_STARTED`; ordinary cancellation is not synthesized as `FAILED`.
Unclassified failures use `INSTALL_FAILED_UNKNOWN`, without guessing a cause.

The local installation-diagnostics candidate records a known initial snapshot,
initial inventory or prewrite inventory failure as
`INSTALL_FAILED_PREFLIGHT_MTP_READ`, with preflight stage and transport category.
A generic read error does not establish device disconnection; presence remains
unknown unless observed evidence establishes it. Confirmed disconnection retains
its disconnect classification. The shared boundary-to-stage resolver supplies
the local failure stage and uploaded result stage.

Optional v4 `failureContext` records bounded observations at the failed boundary.
Native read categories are captured explicitly in the C branch that encounters
the failure, rather than parsed from unrestricted native error text. Worker
timeout, process, I/O, decoding and native failures retain distinct result kinds.
The candidate adds no device-operation retries, extra probes or timeout-policy
changes. Regression coverage exercises native provenance through boundary and
worker wrappers, the durable outbox, local reports and Swift-to-API delivery.

Prewrite protection reports preflight; postwrite protection reports verify.
Protection detail records the failed condition and only observed bounded counts
and target booleans. Successful cleanup preserves the originating failure;
failed cleanup records terminal cleanup context and retains the origin separately
in `originalFailureContext`. A failed contours component is identified explicitly
and retains its own failure stage without rewriting a successful main-map result.
Manual IMG import remains custom, including an OTM-origin file; catalog OTM
installation remains a provider operation. No private filename, path, object ID,
hash or raw native message is added to uploaded context. The field contract lives
in [the shared contracts](../../contracts/README.md#structured-installation-failure-context).

### Hybrid mutation safety

The implementation replaces whole-device inventory equality with three independent
controls: native mutation authorization, exact target verification, and protected
inventory comparison. Native and Swift integration, independent review, and a fresh
real-device gate must complete together; comparator relaxation cannot ship alone.
The evidence below applies to the tested source, not a new public app release.

Native authorization must bind the physical device, operation purpose, exact
storage/path/name and expected state at the mutation boundary. A final same-session
target-absence check precedes upload. The local mutation journal records prepared,
dispatched and terminal outcomes per artifact; incomplete or incoherent successful
native results fail closed. An exclusive native claim prevents replay. This local
journal is separate from compatibility/statistics delivery and never grants retry
or cleanup authority merely because a record exists.

Fresh installation permits one authorized send and no delete. Update distinguishes
new-artifact send from old-artifact removal. Explicit removal requires its own
purpose and exact target validation. A failed-install object must not be deleted
based only on matching filename and size after reconnect: uncertain creation
identity leaves recovery evidence and refuses cleanup. External removal requires
final protected-file/header validation and full content-hash comparison inside
the delete session. Matching content establishes equivalence to the confirmed
map, not unique physical-object identity. Cleanup refuses deletion after its
creation session is lost; a filename/size match cannot restore that authority.

Removal has three distinct authority sources. Automatic failed-install cleanup
requires evidence that this same operation created the object; user confirmation
cannot replace that evidence. Managed Remove and Update require the durable local
manifest for the physical device and map. The manifest survives app version changes
and is independent of the short-lived mutation journal. A different Mac, reinstall
or lost local state grants no ownership, but leaves explicit external Remove
available, including for an unowned Terento-style filename. External confirmation
binds only the selected map and its content; the native delete session revalidates
the physical device, storage, exact path/name/size/kind, presence, uniqueness,
protected status and content hash. Missing manifest or old operation evidence never
makes a valid external map inherently unremovable. It also never grants automatic
replacement or Update authority. Garmin/protected objects stay read-only in every
case. Historical model-only manifest records remain on disk, but cannot silently
establish ownership of a physical watch. Scanning must not merge those records
with a physically bound namespace or combine conflicting physical identities.
Only the currently proven physical namespace may supply managed lifecycle records;
unproven legacy records leave the external Remove fallback available.
If the physical watch's manifest cannot be read when an install starts, Terento
renames it to `manifest.corrupt-<UTC date>.json` beside the original (never
deleting it), writes a local diagnostic and stops before downloading or writing;
the next install starts a fresh manifest. Maps listed only in the set-aside
record are then treated like any other unowned map (external Remove, no managed
Update), so no authority is widened. Recording after a write still fails closed.

After an authorized deletion, a fresh inventory proves removal by the old exact
path's absence. Historical MTP handles may identify unrelated objects in that
session. Update completion and manifest reconciliation likewise identify the
verified replacement by its unique stable path/name/size and compatible map
metadata, retaining the earlier verified hash and ownership evidence. They do not
require historical handles to disappear. Native live-handle revalidation before
deletion is a separate, unchanged gate; no cleanup authority or mutation retry
follows from these post-delete checks.

Before an Update sends its replacement, a physically bound native session reads
the map-scope raw inventory (see below) and builds the canonical
`ProtectedMapInventory`. After verified replacement and old-map removal, another
bound raw map-scope snapshot must match exactly the baseline minus the old target
plus the verified replacement, compared in the narrowest scope both reads cover.
Baseline protected locations remain protected in the final comparison. Unknown
objects, sidecars, folders and storage identity participate in the same classifier
used by installation. Invalid or ambiguous inventory blocks completion. A failed
final check does not commit a clean manifest or trigger another mutation. Completed
or uncertain deletion is never reported as proof that the old map was preserved.

Prefix reads pass stable storage/path/name/size/kind descriptors into a new native
session. That session resolves current handles before reading content; batches
resolve every member before the first read and return results by stable identity.
Lifecycle readers also validate the physical device in that session. Historical
handles never identify a cross-session read target. These metadata checks do not
establish whole-device byte equality.

`ProtectedMapInventory` compares storage ID, exact full path, filename, size and
file/folder kind; item/parent handles are session-scoped navigation and diagnostics.
Within the compared inventory it conservatively protects unknown objects,
IMG/GMA/UNL/SID files on every storage, map and SID containers, explicit
operation/manifest locations, and required ancestors.
Classification grants no ownership or deletion authority. Duplicates, aliases,
invalid paths and incoherent ancestry fail closed, with one narrow exception:
several entries listed under one path (or case alias) are tolerated when every
entry is a plain file outside `/GARMIN` without a map suffix, for example two
music tracks with the same name. Those entries stay protected and are compared
as a multiset, so removing or changing any of them still fails; a local
`*_inventory_duplicates` trace records how many such locations were seen. Folders,
duplicate handles, map files on any storage and everything under `/GARMIN`
(write target, map containers and runtime namespaces) keep failing closed.
Existing protected objects must remain stable; only explicit operation targets
may change.

**Map-scope protection inventory.** The pre-write and post-write protection inventories of a fresh installation and
the protected baseline/final inventories of Safe Update read the **map scope**:
every storage-root entry on every storage (files and folder entries with their
name, size and kind) plus the complete recursive subtree of the single root
folder named `GARMIN` (ASCII case ignored). Everything in that scope is compared
exactly as before, including the write target, every managed, third-party and
Garmin map in `/GARMIN` and `/GARMIN/Map`, SID data, activities and other
`/GARMIN` content, and a map-like file placed at a storage root. Objects inside
other top-level folders (for example `/Music/**` or `/Podcasts/**`, including any
map-suffixed file there) are no longer compared; their top-level folder entries
still are.

This keeps the safety goals: every Terento write is one object-scoped send into
the verified `/GARMIN` folder handle under native authorization with a
same-session no-overwrite check; every native delete (Update's replaced map,
managed and external Remove) resolves the same folder and removes one exact
verified object after its content check (the recorded sampled removal proof for
a Terento-managed map that has one, otherwise full SHA-256 comparison; always the
full SHA-256 for external maps), and cleanup after a lost creation session is
refused. The scanner only recognizes, manages or offers Remove for
`/GARMIN/*.img` and `/GARMIN/Map/**/*.img`. Ownership, manifests and native
authorization are unchanged. Changes outside the scope cannot be caused by those
operations and were already only observations, not attribution.

The native session uses the scoped walk only when it finds exactly one
storage-root entry named `GARMIN` across all storages, and that entry is a folder
with nonzero storage and object IDs. No root (`no_root`), several case-alias or
cross-storage roots or a root-level non-folder with that name
(`ambiguous_root`), or a failed scoped listing (`scoped_failed`) are answered by
the previous full walk in the same session; partial scoped results are never
returned. Every comparison uses the narrowest scope both sides cover: the full
scan baseline of an installation is projected onto the map scope when the live
read is scoped, and full-walk answers keep the full comparison. The worker bound
and libmtp timeouts are unchanged.

Map scan and detection, Remove (its live inspection and post-delete rescan), the
post-update rescan, header prefix reads and exact content reads keep their full
walk; none of them performs the protected comparison. A watch whose bulk is
inside `/GARMIN` (for example years of activities in `/GARMIN/Activity`) still
walks those objects, so the gain depends on how much content lies outside
`/GARMIN`.

Installation and Safe Update record privacy-safe `inventoryMetrics`: `scope`
(`GARMIN` only when every measured read was scoped, otherwise `FULL`),
`prewriteObjectCount`, `prewriteDurationMs` and, once a post-write read
completed, `postwriteObjectCount` and `postwriteDurationMs`. Post-write duration
includes the single retry when the target was transiently absent. Durations
include worker start-up. They are attached to the installation/update
compatibility evidence, listed in the local issue report, and traced locally as
`prewrite_inventory_metrics` / `postwrite_inventory_metrics` (with the full scan
`baseline` count and fallback reason), `update_inventory_metrics` and native
`inventory_scope` (`rc` = fallback reason, `detail` = scope). No path, name,
size or handle is recorded. Protection-context object counts cover the compared
scope. The API must accept `inventoryMetrics` before a client emitting it ships.

Diagnostic-only cases are the exact `/GARMIN/GarminDevice.xml` file, immediate
FIT files in `/GARMIN/Monitor`, and descendant folders of `/GARMIN/TLG/PER`, based
on the captured no-write controls. Positive map classification or explicit target
scope overrides those cases. There is no blanket FIT/XML rule. Unknown companion
formats remain protected rather than assuming a complete Garmin format catalog.
Global changes outside protected/operation scope are observations, not proof that
Terento mutated them. Metadata equality does not prove unchanged same-size bytes.

Source `7a6067a3` passed the 77-runner matrix, Xcode Debug build, required CI and
independent safety/privacy review. On 2026-09-21, its fresh MapRando Malta install
passed the hardware gate on fēnix 8 47 mm AMOLED, firmware 23.31: recoverability,
one authorized native send, zero deletes, verified target and stable protected
metadata. After physical reconnect, the complete target SHA-256 matched the
provider source despite 313 item/41 parent handle changes. On-watch visibility and
basic use were owner-confirmed PASS. One Monitor FIT removal was diagnostic only.
This is evidence for that exact device and installation, not a hardware claim for
Update, external Remove or cleanup; those destructive paths have automated evidence
and require separately authorized hardware tests. Historical issue #249's exact
physical trigger remains unproven.

Local simulation follow-up (2026-09-21) reproduced false Update/Remove failures
caused by cross-session handle comparisons. PR258 corrected those checks; the
original Update reproduction is retained alongside the dedicated regressions.
The local simulation matrix now drives production install/update coordinators,
source validation, ownership/version comparison, durable manifests, protected
inventory and mutation ledger with injected device I/O. Its v1→v2 path verifies
one send/one delete, handle renumber/reuse and durable manifest advancement;
negative cases deny unproven ownership, changed source/target, incomplete ledger
and unexpected protected deltas. Separate executable native tests prove actual
entrypoint refusal and zero unauthorized primitive calls. These are layered local
evidence, not a real-provider hardware Update claim.
Fresh-install hardware evidence does not validate the destructive lifecycle
paths. Current cleanup APIs refuse deletion after the creation session closes;
successful same-operation cleanup must not be simulated by bypassing that refusal.
The local cleanup test invokes the actual refusal entrypoint and reloads retained
recovery from disk, with no native open/send/delete. Fresh-install hardware PASS
remains separate; real newer-provider Update and external Remove hardware remain
pending opportunistic validation and are not gates for this beta release.

Run `Tests/run-app-installation-operation-diagnostics-tests.sh` for the actual
engine/no-screen regression and producer/outbox/privacy cases. Initial context
is in memory; force-quitting before a terminal result is observed is not a
crash-recovery journal. Reports already persisted retain existing retry behavior.
Diagnostic delivery does not itself grant any device mutation authority.

### Provider and map download availability

Catalog v4 keeps blocked maps visible and supplies `downloadBlockReason` on
providers and packages. The native client carries these reasons through artifact
selection, disables Install/Update with provider-specific copy, and preserves
Remove and the installed map inventory. Provider website health alone does not
block acquisition; the API's download decision is authoritative.

Production acquisition checks current remote catalog authorization before creating
an acquisition workspace or sending a provider download request. Failure to obtain
current authorization stops acquisition; bundled data cannot authorize it. During
the running session the last accepted remote catalog is retained if a refresh
fails, preserving known blocks and disabling other rows until status can be checked.
Connection failures are explained as an inability to check availability, separately
from a confirmed provider outage. Failed or unavailable required main artifacts
also block acquisition when legacy metadata has no explicit reason. Every five minutes an idle app refreshes metadata
and recomputes comparisons from the existing inventory without scanning or writing
the device. Acquisition still rechecks authorization independently of this timer.

Provider availability shipped in beta.17/build39. Its automated checks do not
establish a new hardware lifecycle result.


### Garmin root/write profile correction — beta.18/build40 (2026-10-05)

The shared write-target resolver accepts the single valid ASCII root variants
`/GARMIN`, `/Garmin` and `/garmin`, keeps its actual storage binding, and refuses
missing/ambiguous roots, zero storage/object IDs and incomplete physical identity.
Install/custom acquisition checks the full profile before preparation; production
installation rechecks it against physically bound final inventory before write.
Lifecycle uses the same resolver and Safe Update rechecks the bound root/storage.
See `contracts/INSTALLATION_AUTHORIZATION.md` for the representation and privacy
contract. Canonical operation/manifest paths remain `/GARMIN`; no manifest or API
schema changes, fallback storage guesses or model exceptions are introduced.

`run-native-device-binding-profile-tests.sh` covers profile resolution and its
negative cases. The pre-fix regression reproduced the accepted `/Garmin` root
losing storage binding through an exact `/GARMIN` lookup. The native prefix
runner covers the actual C projection and Swift write adapter's nil/stale-profile
refusal. Protected inventory retains the observed root filename while accepting
the canonical path. The local managed-update simulation runs the production
coordinators and durable manifests for all three root spellings, including
reconnect, historical canonical paths and the existing failure matrix; its
injected inventory calls the actual C projection helper. Separate installation,
safe-update, native authorization and recovery tests retain the destructive-path
guards. No real Garmin writes are needed for these automated checks.

These tests reproduce a code defect, not the missing historical device facts.
The eight reported beta.16 attempts remain unconfirmed on hardware. The correction
is published in beta.18/build40; affected-watch confirmation remains a separate
evidence stage.

Candidate validation: native 34/34 and app 26/26 suite runners PASS, including
125 installation tests, 25 safe-update tests, 33 local lifecycle simulations and
actual Swift-to-backend diagnostic validation. Unsigned arm64 Xcode Debug build,
release documentation checks and `git diff --check` PASS. These initial results apply to
the candidate based on integrated beta `0febd192`. Packaged source `e0f0e704`
subsequently passed the full 83-runner release suite, signing, notarization,
Gatekeeper and both ZIP/DMG launch checks before beta.18 publication.

### Local statistics reconciliation candidate

Acquisition events carry an optional `acquisitionPurpose` (`install` or `update`)
through all phases; legacy saved events without it remain unknown. Fresh events
also preserve the selected map result index. Download reporting starts only at
the awaited downloader boundary, after policy, current availability, workspace
and source checks. Pre-download failures produce no fictitious download attempt.
Rejected compatibility reports remain available under their original IDs and
are parked (see map-use delivery above) while independent reports continue.
A preflight component failure is attributed to its owning selected map, not the
flattened component position. MapRando's standalone France contours catalog entry
has its own main artifact; it remains a selectable independent map, distinct from
attached optional component downloads. These are local changes, not release or
hardware evidence. No Checking UI or device-write sequencing changes are included.

### Connection and disconnect messages

While a Garmin is on USB but not yet offering file transfer, the app shows the
calm "Waiting for your Garmin…" state; the USB-mode hint appears only after the
watch stays invisible to file transfer for 45 seconds (watches commonly need
20-30 seconds after plugging in or unlocking). A watch that drops off USB for
less than 10 seconds while connecting keeps the connecting state. After an
unexpected disconnect the waiting screen is titled "Your Garmin was
disconnected" and, when Remove or Update was running, states what the safety
order guarantees at that point: before the removal content check finished
nothing was removed; an interrupted update keeps the current map until the new
one is verified; later phases point to Manage maps to check the result.
