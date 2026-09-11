# Build25-local — partial-read USB termination candidate

Date: 2026-09-12. Local branch `terento/usb-recovery-build23-local`, based on
build24-local commit `5cf150f`. Public build22 remains unchanged.

## Upstream investigation

- OpenMTP #153 and merged go-mtpfs PR4 identify Garmin split header/data mode;
  both sender and receiver must honor it. The pinned libmtp already detects
  `split_header_data` in `ptp_usb_getdata` and honors it when sending. Duplicating
  that patch would not correct a missing feature in this version.
  https://github.com/ganeshrvel/openmtp/issues/153
  https://github.com/ganeshrvel/go-mtpfs/pull/4
- OpenMTP's current `bulkRead` uses nonempty receive buffers and short-packet
  termination. See go-mtpfs commit1c3302b3c476f69e787a0339122a804dd518a007,
  mtp/mtp.go lines605 onward. Pinned libmtp's `ptp_read_func` separately calls
  USB_BULK_READ with length0 after a split payload that is a packet-size multiple.
  The terminating-read error is logged rather than propagated directly; the
  following response read can fail. This is an implementation difference and
  candidate mechanism, not proof that it caused every captured kernel error.
  https://github.com/ganeshrvel/go-mtpfs/blob/1c3302b3c476f69e787a0339122a804dd518a007/mtp/mtp.go#L605
- OpenMTP #389 concerns Edge1050 enumeration/string descriptors, with device
  firmware fixes reported. Our watch enumerates and reads many blocks, so this
  is not an applicable source fix.
  https://github.com/ganeshrvel/openmtp/issues/389
- libmtp #8 / PR9 handle a Samsung EOF-specific partial-read packet boundary
  bug. Our failure occurs before EOF and is not that demonstrated Samsung bug;
  its model flag was not applied to Garmin.
  https://github.com/libmtp/libmtp/issues/8
  https://github.com/libmtp/libmtp/pull/9
- libusb #1798 surveys Darwin concurrency issues. Several fixes are already in
  pinned1.0.30; no exact GetPartialObject fix matching these reports was found.
  No speculative full-library upgrade/reset policy was introduced.
  https://github.com/libusb/libusb/issues/1798
- MacDroid's official troubleshooting recommends cable/direct connection and
  conflicting-app checks; release notes mention MTP improvements without a
  public source patch applicable here. No official public implementation was
  located to port.
  https://www.macdroid.app/faq/macdroid-not-connecting/
  https://help.electronic.us/support/solutions/articles/44001895298-macdroid-version-history

## Implemented candidate

Only sampled verification on macOS Garmin091e:51b8 uses odd payload sizes, at
most65535 bytes. Valid bulk packet sizes are even, so a successful split data
payload finishes short and does not require libmtp's separate zero-length
terminator read. An even final remainder is split into an odd read and its
remaining byte. Requested sample offsets, deduplicated total byte coverage,
source comparison, target/device identity, failure handling, ownership and
cleanup remain unchanged. Other platforms/models retain the64KiB limit.
The existing bounded trace includes `read_chunk_limit` (rc1/detail65535 here).
No delay, verification bypass, full-file readback or new retry/reset is added.
No code/dependency from OpenMTP is bundled; this is an original narrow workaround
based on the inspected protocol behavior, not a claimed ready-made Garmin fix.

## Hardware evidence

Owner authorized read-only comparison, stopped installation, and replugged USB
when the first open failed. Only the existing429793280-byte Terento-named map
was read; the probe has no write/delete API. Each run read the same first32MiB:
- 65536-byte baseline:512 requests, PASS.
- 65535-byte candidate with short final requests:514 requests, PASS.
Both SHA256:effad0b6bd988f70fdefee85829d172ed2b774df9d1709add5dc4c8849ff084b.
Logs:/private/tmp/terento-probe-64k-fresh.log and terento-probe-short-fresh.log.
The successful baseline after replug means this does NOT prove the candidate
fixes post-upload failures. Exact readback and tiny-tail handling are observed;
full installation/Finishing required the subsequent owner hardware gate below.

## Automated evidence

Xcode Debug arm64 build25 PASS. Native profile/ownership/reference runner PASS,
including exhaustive byte-bitmap coverage in both ordinary and short-packet
modes, no missing/duplicate/out-of-range bytes, and request sizes1..131073.
Bounded-process runner PASS. All40 installation coordinator tests PASS.
App semantic label1.0.0-beta.11-local; public checked-in build counter stays22.
Canonical Architecture/Plan/Project State and ADR0026 synchronized locally.

## Artifact receipt

ZIP:dist/Terento-1.0.0-beta.11-local-build25-macOS-arm64.zip
SHA256:2ee2e98c76bd228bb40f8af03fe7fb7d46408d4f9b1adbd6254d61d1f34a9bf3
Extracted app label/build verified; codesign --deep --strict PASS; executable
and bundled libraries arm64; no Homebrew runtime paths. Local ad-hoc signed,
not notarized. Runtime sampled-read sizing/diagnostics changed; resources and
public release/deployment settings unchanged. See the subsequent owner installation result below.

## Owner installation result — 2026-09-12

Owner subsequently reported MapRando Andorra PASS and France installation PASS
on build25-local, on the same fēnix 8 47 mm AMOLED / firmware23.31 test setup.
France is the previously failing france-courbes-ign package (2,962,751,488 bytes).
These are owner-reported completed installations, not independently observed
step-by-step runs. No on-watch visibility/usability or safe-update lifecycle
result is inferred. The local installation retest gate is PASS for these two
reported cases; broad device compatibility and public release remain separate.
Build26 carries the same install/remove/USB implementation, with a UI-only fix.
