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
