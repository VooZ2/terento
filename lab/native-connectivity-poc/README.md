# Terento native connectivity PoC

This document covers the legacy SwiftPM connectivity target and its native
Garmin MTP proof-of-concept tests. The production app is the root
`Terento.xcodeproj` macOS target, which consumes this source module and now has
a guarded map-installation flow. The SwiftPM PoC window remains read-only;
separate developer-only tests can perform narrow, harmless MTP roundtrips.

## Scope

The PoC only:

1. detects one Garmin USB MTP device;
2. reads manufacturer, model, VID, PID, and device version;
3. reads storage IDs, capacities, free space, and descriptions;
4. creates a stable in-memory device identity;
5. evaluates that identity against a local exact-device registry;
6. loads a bundled provider-neutral metadata catalog;
7. enumerates existing device files under the Garmin map locations;
8. reads bounded prefixes of existing `.img` files;
9. validates the Garmin IMG header signatures and parses conservative metadata when available;
10. compares installed map versions with the local catalog;
11. evaluates whether a selected map package fits the reported free space;
12. displays a user-facing map comparison result;
13. releases the MTP device cleanly;
14. provides a separately invoked, fixed-payload write/read-back/hash/cleanup
    test for the validated fēnix 8 device.

The Swift layers are intentionally separated:

```text
SwiftUI
  └── DeviceEngine
        ├── CompatibilityEngine
        │     └── DeviceRegistry (local, in-memory)
        └── MTPTransport
              └── C libmtp bridge
```

The local registry contains exact Garmin smartwatch identities and safe
capability profiles only. Public compatibility status comes from the canonical
API: `TESTING` is zero successful shared installations, `TESTED` is 1–2,
`SUPPORTED` is 3–4, and `VERIFIED` is 5 or more for the exact model and
variant. Reconnect, map visibility, physical-device count, firmware variation,
and operator review do not promote a status. Exact model names and firmware
values belong in internal compatibility records, not this public PoC overview.

The metadata-only catalog records downloadable Freizeitkarte and OpenTopoMap
packages. The bundled fallback contains all 63 official Freizeitkarte
packages plus all 177 official OpenTopoMap Garmin rows. It records provider
attribution, source and license URLs, release, and provider-listed package
sizes; 176 OTM contour artifacts are optional and the one empty contour source
is omitted from installable artifacts. The loader tries
`https://api.terento.app/maps/catalog.json` first and falls back to
`Resources/Maps/catalog.json`. If the live catalog is temporarily missing a
bundled provider, the loader supplements it with the missing local metadata;
if the live catalog contains a paused, retired, or down provider, that remote
state remains authoritative and bundled packages cannot re-enable it. Neither
path downloads a map binary. Catalog timestamps accept ISO 8601 values with or
without fractional seconds so decoding remains consistent across supported
macOS releases.

Map scanning is deliberately content-first. Known Garmin-owned images are
excluded before their prefix is read. Remaining `.img` candidates are read
through one small, read-only header prefix. The filename is not sufficient to
prove identity, but is retained as a bounded fallback for a recognized OTM
header when the fixed header truncates a long country name. This means a
`gmapsupp.img` file or a BaseCamp-renamed Freizeitkarte image can still be
recognized from its IMG metadata. Recognized Freizeitkarte and OpenTopoMap
images can be grouped by provider; unsupported or unrecognized images remain
read-only after inspection, without any write, rename, overwrite, or delete
operation. The header parser recognizes the fixed `DSKIMG`/`GARMIN` signatures,
provider region identity, Freizeitkarte release labels such as `Release 26.05`,
and OpenTopoMap generated dates such as `2026-05-24`. The OTM provider parser
joins the two bounded fixed-header fields before parsing, so it accepts both
the compact `0YY-MM-DD` form (`026-05-24`) and dates split at the field
boundary (`202` + `6-05-24`, or `20` + `26-08-26`). All 177 current OTM main
ZIP sources passed a read-only IMG-header audit; identity and release checks
remain strict.

The prefix is currently limited to 4 KiB. This is enough for the fixed header
metadata observed on the fēnix 8 test device and avoids downloading complete
map images just to identify them. `Release 26.05` is retained as raw metadata
and normalized to the comparable version `2026-05` by the Freizeitkarte
parser; OpenTopoMap generated dates use its own parser, including compact
`0YY-MM-DD` and full dates split across the two fixed header fields. A missing
or conflicting release remains a fail-closed acquisition error.

The local beta.8 Install maps flow presents an alphabetical provider dropdown
without selecting a default provider. A batch may contain one or more maps
from the selected provider only; rows from other providers become inactive and
the planner rejects a defensive mixed-provider selection. Mixed-provider
batch installation is deferred to beta.9/beta.10. OpenTopoMap's optional
contours artifacts are catalogued, but their user-selectable installation flow
is deferred beyond beta.8; beta.8 installs the main map artifact.
Map rows use the country/region as the title, normalize legacy provider-
decorated names such as `Lithuania · Otm Lithuania`, and show provider plus
normalized release on the second line. Same-provider regional variants use a
parenthesized qualifier only when needed.
The owner has confirmed one-map and same-provider two-map OTM installation,
watch use, reconnect persistence, Manage maps discovery, one-map Remove, and
the one-provider selection lock on the tested fēnix 8. An earlier two-map OTM
release-candidate run verified and recorded the first map but exposed an
affected-firmware MTP stall when the next device session was opened
immediately. The batch transition now uses a provider-neutral five-second
device-settle boundary before reopening MTP. The exact two-map OTM scenario
passed on real hardware in build 8; the equivalent two-map Freizeitkarte
scenario also passed. Broader device evidence remains a separate release
claim.

The final beta.8 app presentation keeps only `Update` and `Remove` in normal
Manage maps rows. `Update` appears only from the canonical provider-neutral
lifecycle comparison and reuses the existing safe-update transaction; Backup
and ownership-recovery tooling remain implemented for internal validation but
are not exposed through a production overflow menu. The active installation
page measures the real window viewport, keeps a 28-point bottom breathing
space when content fits, sizes one- to three-map lists to their visible rows,
and retains native scrolling for four or more maps or reduced window height.

Map-operation statistics use a separate, explicit opt-in from compatibility
evidence. Provider maps enqueue idempotent download/install lifecycle events
without Garmin identifiers, serials, local paths, manifests, binary content,
or diagnostic logs. Delivery is best-effort through a local retry queue and
never blocks installation. Server-side raw map events are retained for no
longer than 24 months before pruning.

For this SwiftPM PoC target, the normal SwiftUI window contains no map write or
device modification path. The production Xcode app owns the guarded map
installation and optional compatibility-report flow. The separate
`TerentoWriteTest` command is deliberately narrower: it accepts only
`terento-write-test.txt`, advertises it as a generic MTP object, targets only
`/GARMIN/terento-write-test.txt` on the validated fēnix 8 profile, refuses an
existing target, reads the object back, checks size and SHA-256, and removes only
the exact object it created. It does not write maps or touch any existing Garmin
or user-managed file.

The separate `TerentoInterruptionTest` command uses only a generated
`terento-interrupt-test.bin` payload and a distinct `/GARMIN` test filename. In
`controlled` mode it cancels at 50%. In `physical` mode it pauses at 50%, asks
the operator to disconnect the watch, and then verifies cleanup after reconnect.
It never accepts an IMG/map source and refuses to remove an object unless the
exact object identity returned by the same transfer matches.

The beta.8 production lifecycle path forwards native MTP read progress through
the local read-back adapter. Backup and one-file external Remove can therefore
show measured byte progress; Remove additionally reports determinate progress
through exact verification, deletion, and bounded post-delete rescans. This
does not change the PoC's read-only scope or claim hardware evidence for the
production lifecycle path.

## Dependencies

- macOS 13 or newer
- Swift 6 or newer
- Xcode with SwiftUI support for the native windowed app
- Homebrew `libmtp` 1.1.23
- Homebrew `libusb` 1.0.30, used by libmtp

The PoC links to the Homebrew libraries on the development Mac. It does not
bundle or redistribute either dependency.

## Build

From this directory:

```sh
export LIBMTP_PREFIX=/opt/homebrew/opt/libmtp
export CLANG_MODULE_CACHE_PATH=/tmp/terento-native-poc-module-cache
swift build
```

To run the native window:

```sh
swift run TerentoPoC
```

To verify the beta.8 provider-neutral Stage 1 foundation and its related
regression boundaries:

```sh
./Tests/run-stage1-provider-neutral-tests.sh
./Tests/run-stage2-custom-map-import-tests.sh
./Tests/run-stage2c-custom-map-import-ux-tests.sh
./Tests/run-stage3-generic-lifecycle-tests.sh
./Tests/run-stage41-acquisition-tests.sh
./Tests/run-stage42-installation-tests.sh
./Tests/run-stage45-map-selection-tests.sh
./Tests/run-stage53-safe-update-tests.sh
./Tests/run-map-statistics-event-tests.sh
./Tests/run-beta8-installation-progress-failure-polish-tests.sh
./Tests/run-beta8-manage-maps-polish-tests.sh
```

Release preparation additionally validates the exact production catalog with
the current client decoder, provider adapters, source policies, and complete
Freizeitkarte/OpenTopoMap identity matrix:

```sh
/bin/zsh ../../Packaging/validate-live-map-catalog.sh
```

`Packaging/release.sh` runs this live check automatically before signing or
notarization. If one remote package is incompatible with the current client,
runtime catalog loading fails closed to the bundled last-known-good snapshot.

These checks validate the provider-neutral catalog and acquisition seams,
custom `.img` staging/validation, compact custom-import presentation and
confirmation, generic provider/custom inventory grouping, optional artifact
storage planning, model-admission safety, and the Freizeitkarte/OpenTopoMap
source paths. The common multi-map lifecycle resolves MTP object IDs again by
exact managed filename and validated size after a write, because some Garmin
firmware re-enumerates handles between sessions. It also applies one bounded,
provider-neutral settle window between successful batch items so firmware can
commit/index the completed IMG before Terento opens the next MTP inventory.
The owner has separately confirmed same-provider multi-map OpenTopoMap and
Freizeitkarte installation, Manage maps and watch visibility, reconnect
persistence, and isolated one-map removal on real fēnix 8 hardware. These
native tests do not turn that result into a broader device-support claim or
exercise the separate web/admin UI. The focused beta.8 checks also cover the independent statistics
consent/queue contract, measured installation viewport, and production
`Update`/`Remove` action matrix. The metadata API contract is covered by backend tests; these
native tests do not exercise it. The external-map safety tests cover only the
local one-file Remove boundary; they are not hardware evidence.

To run the explicit developer-only Write Test after connecting the validated
Garmin fēnix 8 and closing other Garmin/MTP applications:

```sh
./run-write-test.sh ~/Downloads/terento-write-test.txt
```

The command stops before writing when the source file name/content is not the
Terento test payload, the target already exists, the device is not the
validated fēnix 8, or the `/GARMIN` target cannot be identified exactly. It
must be started manually; the normal app never invokes it.

To run the controlled interruption test first:

```sh
./run-interruption-test.sh controlled
```

This keeps the watch connected and cancels the generated transfer at 50%.
After it reports cancellation, press Return so it can inspect and, only when
safe, remove the exact temporary object.

To run the physical interruption test:

```sh
./run-interruption-test.sh physical
```

At the 50% pause, disconnect only the Garmin watch, then press Return. Reconnect
the same watch when the command asks. The test then checks whether no temporary
object remained or removes only the exact object identity created by that run.
Do not use a map file, and do not continue if the command reports `MANUAL
REVIEW` or an existing interruption-test target.

Alternatively, open this directory as a Swift package in Xcode and run the
`TerentoPoC` macOS executable target.

## Hardware test procedure

Use the Garmin fēnix 8 AMOLED 47mm test watch. Close Garmin Express, OpenMTP,
MacDroid, and other MTP clients first.

1. Launch with no watch connected. The window should ask you to connect the
   device.
2. Connect the watch and press “Connect device”.
3. Confirm model, firmware, and storage capacity/free-space values.
4. Disconnect the watch and confirm no crash or write activity.
5. Reconnect and press “Read device” again.
6. Confirm a second successful read.

The developer-details toggle shows local diagnostic messages, VID/PID, stages,
errors, timing, identity fields, map identity/version evidence, catalog source,
and compatibility evidence. Normal UI does not expose USB IDs, MTP terminology,
or protocol details. For this SwiftPM PoC target the network paths are the
metadata-only catalog lookup and current public compatibility-status lookup;
map binary download and map installation belong to the production Xcode app,
while analytics and account paths remain absent. The compatibility lookup
uses the exact model/size/display identity, refreshes from the public aggregate
API after discovery, and falls back only to a recent exact-identity cache. It
never changes device write authorization. The separately reviewed Garmin
`091e:51b8` identity resolves to the exact fēnix 8 47 mm AMOLED catalog row;
other size-only identities remain variant-unknown and cannot inherit its
status or cached result.

## Known limitation

The native SwiftUI target builds successfully with the selected full Xcode
toolchain on arm64. Physical-device rendering still requires an explicitly
connected Garmin and remains a separate hardware check. The source remains intentionally separated into the
SwiftUI app, device engine, compatibility engine, local device registry,
map catalog, transport model, bundled metadata resource, and C libmtp bridge.

The bundled package size is a catalog snapshot from the provider directory and
must be revalidated against the actual download before any future map transfer
work. Neither developer write test performs map transfer.
