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
owned-map lifecycle actions and exact recognized external-map removal with
separate confirmation. About is opened through `Terento → About Terento`;
Diagnostics contains sharing settings. The sidebar remains Device, Install
maps, Manage maps. UI layout and exact copy are reviewed visually; tests should
protect actions, state transitions, accessibility and data contracts.

## Safety and verification

Ownership requires BOTH an approved managed filename and the exact file in the
local device manifest. Unknown files, Garmin maps, GMA/UNL and protected system
files remain read-only. Recognized external maps require a separate exact-target
confirmation and live recheck; recognition never confers ownership.

A safe update downloads and validates the replacement, checks space for both
versions, uploads and verifies the replacement, then removes the old owned
version. Insufficient space stops the update. Interrupted transfers must not
remove a known-good version. Recovery records retain exact created-object
identity; cleanup never expands into heuristic deletion.

Remote transfer verification uses the implemented bounded sampled-read policy;
it is not a claim of a whole remote-file SHA-256. Sample workers have a
120-second advancing-byte inactivity limit and a 600-second absolute limit.
Only strictly increasing validated progress renews inactivity. Cancellation
reaps the owned child before releasing its lifecycle lease. These limits do
not impose a universal timeout on every synchronous native inventory call.
Connection/inventory and readback failures may still require physical reconnect.

Installation/removal evidence is model-specific. A real update to a newer map
release remains untested; neither automated tests nor reconnect recovery closes
that hardware gate. See [historical evidence](../../history/README.md).

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
turned off in Diagnostics. Custom maps contribute compatibility evidence only.
Strict `-local` labels keep local-test events outside public aggregates.
Report issue opens a user-reviewed GitHub draft; raw logs are not automatically
uploaded. App updates use metadata checks and an explicit official-download
handoff, never silent application replacement.

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
absent from app builds; no production retry policy is changed.

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
visibility/usability and real update acceptance require independent owner tests.

## Exact-model diagnostic metadata

The XML reader accepts the official namespaced GarminDevice v2 `Device` root
and the legacy `GarminDevice` root, and independently extracts Model/Description
and Model/PartNumber,
including when the local Unit ID is unavailable or invalid. Existing local
identity keys, write profiles, ownership and install/update/remove sequences
are unchanged. A missing XML document preserves valid MTP DeviceInfo.
AMOLED/MicroLED/MIP, Solar and inReach are separate reported properties;
missing words do not mean false. Technical originals appear in Diagnostics.
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

The existing v4 event queue sends only the two bounded optional model fields,
with the existing diagnostic opt-out and local-test partition. The API must
accept these additions before releasing the app. The current candidate uses
beta.12 with build29; the published release remains whatever the canonical
update manifest records. A read-only Mac-side observation of fēnix 8 47 mm
received original XML AMOLED text and code 006-B4536-00; this is metadata
evidence for that watch, not other variants or map lifecycle acceptance. Map-operation safety
regressions remain required; no new install/remove hardware test is introduced.
