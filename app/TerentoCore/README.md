# Terento native core

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

A safe update downloads and validates the replacement, checks space for both
versions, uploads and verifies the replacement, then removes the old owned
version. Insufficient space stops the update. Interrupted transfers must not
remove a known-good version. The update does not create a persistent local
backup; the existing device object is the recovery boundary until the new
object is verified. Recovery records retain exact created-object
identity; cleanup never expands into heuristic deletion. The write profile is
bound from the live Garmin USB identity and read-only `/GARMIN` inventory; it
does not contain a model allowlist.

Remote transfer verification uses the implemented bounded sampled-read policy;
it is not a claim of a whole remote-file SHA-256. Sample workers have a
120-second advancing-byte inactivity limit and a 600-second absolute limit.
Only strictly increasing validated progress renews inactivity. Cancellation
reaps the owned child before releasing its lifecycle lease. These limits do
not impose a universal timeout on every synchronous native inventory call.
Connection/inventory and readback failures may still require physical reconnect.

For issue #222, a local follow-up now classifies a pre-write inventory worker
timeout as preflight MTP-read failure instead of verification failure, records
the measured bounded wait, and never starts upload when inventory has not
completed. Inventory has a finite 60-second worker bound matching libmtp's
LONG_TIMEOUT; this is not a model-specific USB workaround. Local sanitized
trace markers separate session open, file-list read, session close and native
cleanup. The initiating 091e:51b5 hardware stall remains unproven pending a
controlled failing/successful-model retest.

Installation/removal evidence is model-specific. The owner reported a
successful real-device BBBike Lithuania Update using the local Debug candidate;
Manage maps shows the installed `2026-09-16` release. This is owner-reported
evidence, not independent verification or evidence for every model/provider.
Freizeitkarte and OpenTopoMap still require their own real newer-release update
gates. There is no public release or API deployment implied. See
[historical evidence](../../history/README.md).

## Catalog and privacy contracts

The current app uses `/maps/catalog-v4.json`. Legacy v2 and v3 routes retain
provider sets understood by older clients. The full bundled fallback is a
native decoder projection; it must not be silently rewritten into an API schema.
See [shared contracts](../../contracts/README.md).

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
uploaded. App updates use metadata checks and an explicit official-download
handoff, never silent application replacement.

Map-use delivery drains events appended during an in-flight upload before
reporting the queue uploaded. Retryable failures retain the queue and use the
existing bounded retry schedule; permanent failures stop that send attempt.
Opt-out clears pending events and stops the sender before another event is sent.
A response already in flight cannot restore the opted-out status. This does not
add cancellation/interruption events or reconstruct missing historical outcomes;
a download start without a received outcome is not proof of a failed download.

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
missing variant evidence cannot select an exact ID. Catalog-derived screen
properties are labelled separately from MTP/XML observations; a submitted
catalog ID remains a hint rechecked by the server. API failure preserves raw
device metadata. Local map-capability and installation permission registries
are unchanged. Historical manifest naming is frozen in the storage layer and
is never a model-identification source.

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

### Hybrid mutation safety (local candidate)

The candidate replaces whole-device inventory equality with three independent
controls: native mutation authorization, exact target verification, and protected
inventory comparison. No new hardware pass or public release is claimed. Native
and Swift integration, independent review, and a fresh real-device gate must
complete before merge; earlier install evidence does not validate this model.

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

`ProtectedMapInventory` compares storage ID, exact full path, filename, size and
file/folder kind; item/parent handles are session-scoped navigation and diagnostics.
It conservatively protects unknown objects, all-storage IMG/GMA/UNL/SID, map and
SID containers, explicit operation/manifest locations, and required ancestors.
Classification grants no ownership or deletion authority. Duplicates, aliases,
invalid paths and incoherent ancestry fail closed. Existing protected objects
must remain stable; only explicit operation targets may change.

Diagnostic-only cases are the exact `/GARMIN/GarminDevice.xml` file, immediate
FIT files in `/GARMIN/Monitor`, and descendant folders of `/GARMIN/TLG/PER`, based
on the captured no-write controls. Positive map classification or explicit target
scope overrides those cases. There is no blanket FIT/XML rule. Unknown companion
formats remain protected rather than assuming a complete Garmin format catalog.
Global changes outside protected/operation scope are observations, not proof that
Terento mutated them. Metadata equality does not prove unchanged same-size bytes.

The runtime integration remains subject to the full test matrix and new hardware
gate: recoverability, native authorization and journal, exact target verification,
protected-map preservation, reconnect and on-watch use. Cleanup is a separate
authorized hardware test. Historical issue #249's exact trigger remains unproven.

Run `Tests/run-app-installation-operation-diagnostics-tests.sh` for the actual
engine/no-screen regression and producer/outbox/privacy cases. Initial context
is in memory; force-quitting before a terminal result is observed is not a
crash-recovery journal. Reports already persisted retain existing retry behavior.
No device-operation behavior changes are part of this diagnostic producer fix.
