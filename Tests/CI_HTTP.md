# CI HTTP verification

`scripts/ci_http.py` requests compressed HTTPS responses and retries transient
transport errors and selected HTTP availability errors at most three times,
with 2/4 second backoff. Successful requests have no added wait. Callers retain
their connect/total time limits and strict JSON, catalog and security assertions.
Each attempt has a fresh response file; partial responses never reach validators.
Nested curl retries are rejected.

Use observation mode only for idempotent reporting requests carrying a fixed
observation ID. Exhausted transient reporting errors produce a GitHub warning
and summary instead of changing a passing quality result. Permanent errors,
including authentication errors, remain failures. Required live checks never
use observation mode. SMTP delivery behavior is unchanged.

The workflow contract suite exercises retries using synthetic curl results and
an injected sleep function; it makes no external requests or actual waits.
Run `python3 Tests/ci-workflow-contract-tests.py` and
`python3 Tests/admin-access-boundary-tests.py` for focused validation.
