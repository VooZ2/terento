# Build23-local USB recovery candidate

Owner authorized local testing with a strict-local semantic label. Worktree:
/private/tmp/terento-usb-recovery-build23; branch terento/usb-recovery-build23-local.
Base:0635cd75108133b35ae0aab05a35c1ba016dff27 (public22 source).

Implemented: explicit bundled libmtp context lifetime under the existing native
gate; abort host resources on failed sampled read; no implicit failed-open reset
on macOS091e:51b8; parent-only metadata retry with600s whole-verification budget,
unchanged120s progress idle and45s cleanup; generic verification error classified
as verification-required instead of physical disconnect. Existing failed-install
recovery record and separate original/cleanup failures retained. Source patches
and LGPL notices accompany the local app. Full3GB read-back not introduced.

Tests completed at this checkpoint: Xcode arm64 Debug;40 installation coordinator
cases;10 concurrency cases including blocking context shutdown after native error;
compiled fakeUSB context init/exit/reinit, abort versus healthy close, narrow
platform/product reset policy, strict patch idempotence/drift; bounded process
progress/deadline/cancellation/reaping. Native safety/profile suite PASS. Initial
build/test infrastructure issues (blank export line, patch-chain restart, shell
and SwiftPM sandbox) corrected; no hardware diagnosis inferred from those.

Full regression and packaged artifact receipt recorded below. No app launched against
hardware, no file installed/deleted, no public release or backend modification.
Known limitation: first USB transaction error not proven solved; context shutdown
may change connection timing, and fast failed-open can require reconnect sooner.
Owner must repeat map navigation/Eject and installation before public acceptance.
Canonical ARCHITECTURE/PLAN/PROJECT_STATE and ADR0026 synchronized locally.

## Final local artifact — 2026-09-12

PASS: Xcode arm64 Debug built with CURRENT_PROJECT_VERSION=23; plist label
1.0.0-beta.11-local/build23 verified. Checked-in public numbering stays22.
All67 declared regression runners pass across the full run (site/app/native/backend)
and the final release/shared/CI runs after correcting the Debug-number default.
This preserves the public manifest contract rather than weakening its test.
Legacy Homebrew bridge compile fixed without changing the bundled abort path.

Final package: dist/Terento-1.0.0-beta.11-local-build23-macOS-arm64.zip,
6987964 bytes, SHA256 d9913a3f4d6122f105933ac70c9b3c9881d895a82abcb012a46059a43cd8d4f3.
Extracted signatures, strict local label, arm64/no-Homebrew dependency linkage,
and both custom library exports verified. Worker-entry startup exercised with an
invalid request that exits before touching USB; no GUI/hardware smoke claimed.
Ad-hoc signed, not notarized; local testing only. Patch sources/licenses included.
No real map writes/deletes or publication performed. Owner hardware gate pending.
