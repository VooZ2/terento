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
6. loads a bundled Freizeitkarte metadata catalog;
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

The local registry contains exact tested Garmin smartwatch identities with
status `TESTED`. This status records read-only connectivity evidence only. A
successful verified map installation promotes the exact identity to
`SUPPORTED`; reconnect verification and map visibility are optional
observations, not status gates. `VERIFIED` additionally requires multiple
operator-reviewed physical devices and firmware variation. Exact model names
and firmware values belong in internal compatibility records, not this public
PoC overview.

The metadata-only catalog records Freizeitkarte packages. The bundled fallback
is a small snapshot containing Lithuania and Latvia; the live catalog may
contain more regions. It records provider attribution, source and license URLs,
release, and provider-listed package sizes. The loader tries
`https://api.terento.app/maps/catalog.json` first and falls back to
`Resources/Maps/catalog.json`; neither path downloads a map binary.

Map scanning is deliberately content-first. Known Garmin-owned images are
excluded before their prefix is read. Remaining `.img` candidates are read
through one small, read-only header prefix; the filename is retained only as a
diagnostic path and is not used to identify a map. This means a `gmapsupp.img`
file or a BaseCamp-renamed Freizeitkarte image can still be recognized from
its IMG metadata. Non-Freizeitkarte images are ignored after inspection,
without any write, rename, overwrite, or delete operation. The header parser
recognizes the fixed `DSKIMG`/`GARMIN` signatures, the Freizeitkarte provider
and region code such as `LTU`, and release labels such as `Release 26.05`.

The prefix is currently limited to 4 KiB. This is enough for the fixed header
metadata observed on the fēnix 8 test device and avoids downloading complete
map images just to identify them. `Release 26.05` is retained as raw metadata
and normalized to the comparable version `2026-05` by the Freizeitkarte parser.

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
or protocol details. For this SwiftPM PoC target the only network path is
metadata-only catalog lookup; map binary download and map installation belong
to the production Xcode app, while analytics and account paths remain absent.

## Known limitation

The repository Mac currently has Swift command-line tools but no full Xcode
installation selected, so the SwiftUI windowed build must be validated on a
Mac with Xcode available. The source remains intentionally separated into the
SwiftUI app, device engine, compatibility engine, local device registry,
map catalog, transport model, bundled metadata resource, and C libmtp bridge.

The bundled package size is a catalog snapshot from the provider directory and
must be revalidated against the actual download before any future map transfer
work. Neither developer write test performs map transfer.
