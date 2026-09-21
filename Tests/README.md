# Test and CI policy

`test-suites.json` is the inventory; suite names describe ownership, not individual
test counts. `ci-test-inventory-tests.py` rejects unassigned, missing, duplicate
and non-executable runners. `select-test-suites.py` selects affected suites.

| Change | Required checks |
| --- | --- |
| Ordinary Markdown, including component and contracts README | shared/CI documentation and inventory checks |
| README release identity, release notes, packaging/native dependency docs, third-party notices | release plus shared/CI |
| Legal web source | site, release, shared/CI |
| App shell or presentation | app, shared/CI |
| Native core or lifecycle | app, native, shared/CI |
| Backend implementation | backend, shared/CI; selected catalog interfaces also native |
| Shared schema/fixture or unknown implementation path | all suites |

The full release matrix runs on tags, manual full checks, weekly CI and release
packaging. The required `build-and-test` aggregate rejects failed/cancelled jobs;
only intentionally unselected suites may be skipped. A newer PR commit cancels
older PR CI. Deployment jobs are serialized, not cancelled mid-mutation.

## Purpose of each check

App checks cover presentation behavior and wiring. Native checks cover manifests,
provider identity/acquisition, storage, safe install/update/removal and failure
recovery. Text/layout checks are not hardware evidence. Prefer behavior and
structural assertions to exact function names, spacing values or prose sentences.
The native prefix-session runner executes the production C bridge and Swift
transport against an offline libmtp fixture, including current-handle reuse and
batch result correlation. It never requires a connected device. Update regression
tests apply the canonical raw protected-inventory transition before manifest commit.
Keep privacy, trusted destinations, release identity and safety guards explicit.

Backend checks include unit tests and a real PostgreSQL migration/health round
trip. Migration versions must be unique before any DB connection is opened.
Applying migrations twice deliberately tests idempotency; do not remove the
second execution. Deployment repeats backend checks on its own exact commit;
removing that repeat requires a verified same-SHA quality artifact handoff, not
trust in an earlier PR head. The current explicit rerun is retained.

Backend test modules are named by current ownership: provider acquisition and
catalog projection live in `test_provider_catalog.py` and `test_maprando.py`,
event validation/lifecycle tests live in their respective modules, and Admin
map activity/API tests live in `test_admin_map_activity.py` and
`test_catalog_api.py`. The shared `FakeProviderDatabase` lives in the
non-discoverable `api_test_fixtures.py` helper; it is not an additional test
suite.

`validate-live-map-catalog.sh` tests the current checkout decoder against live
routes for a candidate. Daily monitoring and API deployment additionally use
`validate-released-map-catalog.sh` with immutable published source commits from
`contracts/released-catalog-clients.json`. Those tests execute source decoders,
not the downloaded application or Garmin hardware. Weekly CI does not duplicate
the daily live monitor. CodeQL scans Python on affected paths and weekly.

## Local mutation simulations

The native managed-update simulation executes production coordinators, source
validation, physical ownership, comparison, durable manifests, protected inventory
and ledger transitions with injected I/O and an isolated temporary application
support directory. Its mutation counts describe simulated device I/O. The native
authorization executable separately counts calls at the real C mutation boundary.
The installation runner also invokes the real cleanup-refusal path through an
offline native fixture and verifies durable recovery with zero native operations.
No simulated provider, fixture state or telemetry client enters the app target.
Release isolation checks run on compiler inputs and the actual packaged bundle.

## Failures and retries

Each runner streams output and saves its first-attempt log under ignored
`test-results/`; CI retains logs for 14 days. No assertion is automatically retried.
The diagnostics test observes the actual scheduled upload task through a
compile-only test accessor. Waiting for completion replaces the old 180/100 ms
sleep assumptions. The manual-retry fixture deliberately takes 300 ms to
complete successfully, exceeding the old assertion window; a 30-second harness
timeout still fails a hung task.

Filter performance is reported without a machine-speed assertion in normal CI.
A controlled benchmark sets `TERENTO_ENFORCE_FILTER_BENCHMARK=1` and retains the
16 ms p95 target. All functional/catalog invariants remain mandatory.

A failed run report must state: failing step/assertion; evidenced cause; whether
runtime or the test changed; why the invariant was preserved; focused result;
and required integration gates. A green rerun alone is not a fix. Keep unresolved
race hypotheses open until a controlled reproduction supports the conclusion.

HTTP retry policy is documented in [CI_HTTP.md](CI_HTTP.md). Only bounded
transient transport failures may retry; malformed data, failed assertions and
authentication failures remain failures. SSH retries only a confirmed connection
timeout before the remote command can run. A dropped established connection
must be investigated before replaying a mutation.

Site publication comes from beta once. Live manifest identity must match the
tested file, not merely report arm64. Operations-observation delivery is distinct
from deployment/test success; permanent reporting configuration errors are still
visible. Do not mute notifications to hide unexplained failures.

## Documentation hygiene

Keep current behavior in component READMEs and API contracts, release identity in
release notes/manifest, and dated evidence in `history/`. Do not accumulate local
candidate instructions in current build documentation. Public instructions must
work without private `internal/` files. Preserve legal sources, migrations,
legacy client contracts and regression fixtures even when they refer to old versions.

For a same-beta or next-numbered-beta candidate, release contracts separately validate the exact
Xcode/candidate build and the still-published manifest/notes/downloads. The
candidate must advance the build and preserve the public version/label; it
cannot carry distribution URLs or checksums. Removing it restores the direct
Xcode/public-manifest equality requirement.

Release documentation checks also protect the current Compatibility semantics:
the public page is a successful-installation directory, exact model/variant
entries require at least one successful shared installation, and a missing
model is not an unsupported claim. The release gate checks all six guide
locales, release identity parity, generator-produced help copy, and known
retired public wording without scanning internal status terminology.
