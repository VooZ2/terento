# Terento native dependencies

The production macOS target builds and bundles these libraries from pinned
upstream source archives:

| Library | Version | License | Source |
| --- | --- | --- | --- |
| libmtp | 1.1.23 | LGPL-2.1-or-later | <https://github.com/libmtp/libmtp> |
| libusb | 1.0.30 | LGPL-2.1-or-later | <https://github.com/libusb/libusb> |

The archive URLs and SHA-256 values are pinned in `build.sh`. The build uses
Apple Silicon (`arm64`) and the Xcode target's `MACOSX_DEPLOYMENT_TARGET`.
The resulting shared libraries use these install names:

```text
@rpath/libmtp.9.dylib
@rpath/libusb-1.0.0.dylib
```

The Xcode target invokes the script before compiling the C bridge. It places
the build outputs in derived data, links against those outputs, and copies
only the two shared libraries into `Terento.app/Contents/Frameworks`.
Apple system frameworks and `/usr/lib/libiconv.2.dylib` remain system
dependencies and are not bundled.

To build the native dependencies independently:

```sh
Packaging/NativeDependencies/build.sh \
  --output /private/tmp/terento-native-dependencies \
  --deployment-target 13.0 \
  --arch arm64
```

The script does not use Homebrew libraries and fails if a produced dylib
contains `/opt/homebrew`, `/usr/local`, or a developer `/Users/...` path.

Before compiling a newly extracted libmtp source archive, the script also
fails unless the pinned source still contains the Garmin-relevant MTP transport
behaviors verified for Terento: automatic 12-byte split-header detection, the
matching split-send path, and a zero-length terminating USB write for
packet-aligned transfers. This is a source-level dependency upgrade gate, not
a substitute for a real-device transfer test.

The `partial-read-diagnostics-v1` local libmtp patch preserves a failed
`GetPartialObject` PTP response in the existing error stack. The bridge exports
only its numeric code in `read_ptp_response`; no raw error text is shared. USB
requests, retries and return values are unchanged. The exact-source patch is
idempotent and rejects source drift. A patch-versioned prefix and cache marker
force rebuilding libmtp even when an older unpatched runtime is cached.

The local `usb-session-v1` patch corrects five failed-open paths in libmtp's
USB glue so that an opened USB handle is closed before its wrapper is freed;
a claimed interface is released before that close. Descriptor/claim failures
do not attempt to release an unclaimed interface. These are resource-lifecycle
fixes, not map-file cleanup operations.

As a local hardware-test candidate, the same patch suppresses the inherited
`FORCE_RESET_ON_CLOSE` quirk only on macOS for Garmin VID/PID `091e:51b8`
(fēnix 8 AMOLED). The guard applies whenever `close_usb` would perform that
flag-driven reset, including recovery closes; the explicit reset after a failed
OpenSession remains. Other flags and device IDs retain upstream behavior.
Sample coverage, transfer verification and ownership rules are unchanged.
The cache revision is `partial-read-diagnostics-v1-usb-session-v1`.
This candidate has not yet established a hardware fix for issue 148 and has
been included in local build20 for owner retesting, not publicly released. The existing native profile checks
exercise the transformed C lifecycle paths with fake USB handles and reject
source drift; real repeated install/remove testing remains required.

## Build23-local recovery candidate

The additional `patch-usb-recovery.py` runs against checksum-verified pristine
upstream files after the existing lifecycle patch. Cache revision `recovery-v1`
forces a newly linked library and exports two explicit Terento extension symbols.
Bundled Xcode builds define `TERENTO_BUNDLED_MTP`; legacy Homebrew SwiftPM tests
do not claim this runtime behavior. The operation gate ends the exact idle
libmtp context before releasing its native lock. All bridge device objects must
have been released before that boundary. Failed sampled reads abort host USB
resources before ordinary object destruction, without CloseSession or endpoint
recovery I/O. On macOS091e:51b8, failed OpenSession returns without automatic
reset; healthy close and other devices retain their policy. No verification
coverage, map mutation rules, or native dependency versions changed.

This is a local hardware-test candidate, not a public release or proven fix for
the initiating USB transaction error. Context reinitialization, resource abort,
platform/product scope and gate ordering have synthetic regression coverage.
