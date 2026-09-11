# beta.11 build 22 — Finishing deadline correction

Status: local release preparation, not published at this checkpoint.

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
Debug and Release bounded-worker runner passes. Full release checks pending.

User explicitly requested immediate build22 publication after checks. No new
hardware installation or device mutation was performed during this task; this
release must not be described as a successful hardware retest. The original
working tree's unrelated backend changes are excluded by an isolated worktree.

Canonical architecture, plan and state documents were reviewed and updated
locally; Packaging/README.md records the distributed behavior. Website/update
metadata, release notes and build ordering are synchronized for publication.
