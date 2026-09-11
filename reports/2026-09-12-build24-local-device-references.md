# Build24-local — repair repeated Connect device

Local-only follow-up on `terento/usb-recovery-build23-local`, parent `61448cb`.
Public build22 is unchanged. Runtime Swift/UI, map verification coverage,
write/delete safety and public release metadata are unchanged in this follow-up.
The native dependency patch and cache revision change; app resources do not.

## Diagnosis

Build23-local was reproduced on the connected fenix 8 47 mm AMOLED / firmware
23.31. The app discovered it, then returned to Disconnected. Captured native
stderr reports `device still referenced at libusb_exit`, followed by
`libusb_device reference not released on last exit. will not continue`.
The presence monitor interprets this failed library initialization as lost
connectivity; its 1.5-second interval explains the repeated Connect action.
This is a confirmed build23-local regression, not evidence of a physical unplug.

Pinned libmtp1.1.23 freed enumeration arrays with unref=0, leaving device
references alive across the new context teardown. Build24 uses unref=1 on all
ten discovery/open exits, explicitly retains/releases entries in the MTP list,
preserves that list on append allocation failure, and releases it on raw-array
allocation failure. Both specific-device scan exits also release their array.
Open handles continue to own their independent device reference until close.
No USB reset, device-file cleanup or verification shortcut is added.

## Evidence and limits

PASS: patch applied against actual pinned source; idempotence and drift checks;
100 executable reference-ownership cycles with enumeration, retained list,
open-handle, allocation-failure and specific-device cases. Full native map-profile
contract runner and connection-lifecycle runner pass. Xcode Debug arm64 build24
succeeds, with checked-in public version counter still22.

Read-only real hardware PASS: fresh GUI launch automatically identified the
connected watch; connection persisted across multiple presence intervals;
Device/sidebar Eject became enabled; Manage maps completed inventory and showed
installed and incomplete maps. No native reference/reinitialization errors in
`/private/tmp/usb24-gui-debug.log` during these checks. Install maps was entered,
but its final state was not independently verified because the owner resumed
GUI interaction. The agent stopped clicking when this was detected. Eject was
not executed, and the agent did not initiate any install/remove operation.

Full Finishing/install acceptance and the original USB transaction failure
remain unverified. Build23-local is superseded and fails its hardware gate.
Build24-local is an ad-hoc signed local test candidate, not a public release.
Canonical Architecture/Plan/Project State and ADR0026 reviewed and synchronized.

## Artifact receipt

`dist/Terento-1.0.0-beta.11-local-build24-macOS-arm64.zip`
SHA256: `53bebd873ec7981a5d3c6e053ed6a825cb4fde7f6acdb8779cfaf5222b011dd8`.
Extracted bundle verifies with codesign --deep --strict; arm64 executable; label
`1.0.0-beta.11-local`, build24; no Homebrew runtime paths. Four native patches
and license/source notices accompany the app. The already running test instance
was left open for the owner; packaged copy contains the same built executable.

## Owner installation test — FAILED — 2026-09-12

Diagnostic e1b2d7d8-40f0-4abe-bcf0-27dc8e497ed8, installation
4965afa1-2ba2-4bd8-826e-c6cd9ab75c5b: build24-local MapRando France IGN
contours,2962751488 bytes, upload100%, verification READBACK_FAILED with
PTP_ERROR_IO767 at offset827710662 after11534336 verified sample bytes.
The samples operation returned its failure in18.5996s, without worker deadline
or retry storm. Cleanup completed successfully in1.6517s. Source/remote length
match is not content-verification success. Full install acceptance FAIL.

Independent macOS log correlation: 2026-09-12 00:46:36.470, IOUSBHostDevice
@00100000 endpoint0x81, status0xe00002ed transaction error,0 transferred bytes
(`/private/tmp/usb24-install-kernel.log`). This establishes a failed USB read,
not a proven physical disconnect or a precise firmware/cable/host root cause.
No library reinitialization errors appeared in the parent diagnostic stderr.

Build22 failed at825154758 after8978432 sample bytes; both are in the same
4MiB region starting824564934 (after two complete4MiB samples). Build24 advanced
39 additional64KiB chunks, so the failures do not establish a fixed corrupt byte
or offset boundary. ADR0025 also records the partial-read error on a different
map/provider-era test, connecting this to the earlier #148 failing path.

Next diagnostic candidate, not implemented or proven here: retain identical
sample coverage/comparison and apply controlled pacing between partial reads;
compare one changed parameter at a time (64KiB+pacing first, smaller reads only
as a separate experiment). Capture native transfer status, requested/actual bytes,
region/chunk and timing to distinguish command/response/data-stage failure.
Increasing Finishing deadlines cannot fix this early explicit I/O error.
No fresh device write or new public release was initiated by the agent.

## Second owner test: small MapRando Andorra — FAILED

Diagnostic a809654a-d910-4f69-850a-e0cfc8f72730; installation
af0ef7e6-e9bf-430a-9b24-78ac1940ae2b. Same watch/build24-local,23905280-byte
Andorra map, upload100%, same PTP_ERROR_IO767/READBACK_FAILED. First region
starts at0;62 consecutive64KiB chunks (4063232 bytes) verified before failure
at4063232. No nonsequential region transition had yet occurred. Samples failed
in1.4348s; full failure5940ms; exact cleanup succeeded in0.2312s.

Kernel correlation independently confirms endpoint0x81 transaction errors with
0 bytes at00:48:27.852 and00:48:29.015, plus controller I/O failure00:48:29.016
(`/private/tmp/usb24-andorra-kernel.log`). The retained log does not establish
which higher-level transaction produced each event. Large map size, long
internet acquisition, verification deadline, a single France-file location and
nonsequential seeking are not necessary conditions for this observed failure.
It remains an unresolved partial-read transport failure. Pace/chunk-size testing
is experimental; no firmware, cable, host, or specific protocol defect is proven.
The small Andorra package is sufficient for the next controlled reproduction.
