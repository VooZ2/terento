# beta.11 build 22 — Finishing deadline correction

Status: signed/notarized build22 artifacts ready; publication pending at this checkpoint.

Issue157's first report is an unstarted batch item
(INSTALL_NOT_STARTED_AFTER_EARLIER_FAILURE), not proof of a download failure.
The antecedent failure is absent from that report.

The owner's second report and matching complete local trace show successful
sample reads through119.59 seconds, with28508160 of29360128 planned bytes
verified (97.10%). The first worker has no read/mismatch/native failure before
the parent kills it at120 seconds. Later session-open failures and cleanup
expiry follow. This shares issue148's recovery symptoms, but148 began with a
partial-read I/O failure. No general USB reliability fix is claimed.

Only sample-worker deadlines change:120 seconds without new verified bytes,
600 seconds absolute per worker. Validation progress is independent of the UI
callback. Inconsistent totals, out-of-range counters and non-increasing values
are ignored. Final result verification, cancellation/reaping,45-second other
workers,120-second discovery, native calls, sample coverage, retries, ownership,
cleanup/update/delete sequencing and dependencies remain unchanged.

Validation: deterministic simulated180-second progressing verification,
inactivity, late/repeated/regressing progress, absolute ceiling and unchanged
fixed deadlines; real subprocess completion/timeout/reaping checks. Existing
Debug and Release bounded-worker runner passes. Full release checks PASS (67/67 runners); live provider catalog PASS.

User explicitly requested immediate build22 publication after checks. No new
hardware installation or device mutation was performed during this task; this
release must not be described as a successful hardware retest. The original
working tree's unrelated backend changes are excluded by an isolated worktree.

Canonical architecture, plan and state documents were reviewed and updated
locally; Packaging/README.md records the distributed behavior. Website/update
metadata, release notes and build ordering are synchronized for publication.

## Final local artifact evidence

The canonical release pipeline PASS: fresh arm64 Release build22, Developer ID
signatures, bundled libraries with no Homebrew runtime paths, Apple notarization
and stapling, Gatekeeper and launch smoke for extracted ZIP and mounted DMG.
DMG:6290471 bytes, SHA2564f96a8e60f4ecb68cb9a5ea1ebd4490b0b65564d1659b607f1c44e60ffcd01dc.
ZIP:5743971 bytes, SHA2569b5c7d355c37411988825a7be5781fc7779e97ba7844af1a4522a3cc0c5e6550.
Release metadata now contains the actual DMG hash. The suite was rerun with
the existing supported Python3.12 environment after an environment-only failure.
No native source changed after these checks. Publication/CI still pending.

## CI subprocess scheduling tolerance

The identical native test code passed on the first PR head but the later CI
run exited133 inside the bounded-worker runner, whose redirected stderr was
removed before upload. Exact assertion evidence was therefore unavailable.
The newly added subsecond progress tests were vulnerable to runner scheduling
delays: increase their real-process inactivity windows to1–2 seconds and keep
exact boundary testing deterministic through the injected clock model. The
runner now prints captured stderr on failure. Production code/artifacts are
unchanged; recheck the bounded runner and final PR CI before publication.
