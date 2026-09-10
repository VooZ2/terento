# September 9 public/admin audit contract

The public interface and admin presentation use the existing Terento tokens;
no native application release, evidence approval, device operation, or data
collection behavior changes in this patch.

Public compatibility counts, statuses, dates and model cards come directly from
the live public compatibility API. The six localized HTML files contain only a
loading shell and no checked-in evidence rows or numeric snapshot. A failed
initial request shows the localized unavailable state and Retry action. If a
later background refresh fails, the page keeps only the last results loaded
from the API and labels them as potentially outdated.

Site publication validates deterministic HTML, JavaScript and release
contracts without comparing a changing live API response to the commit. Live
evidence can therefore change independently without blocking an unrelated site
deployment. The obsolete scheduled snapshot-refresh workflow and its write and
pull-request permissions have been removed.

Public regression coverage includes six-locale API-only loading shells,
translated summaries/DMG recommendation, shared asset versions, initial API
failure, background-refresh recovery, Retry, and Clear filters. Home and Guide describe the existing app Report issue
action (copy report, open GitHub, review before public posting), not a log export
command that does not exist. Mail links remain optional support contact.

Admin checks cover local table scrolling at intermediate widths, empty filters
and time ranges, package-vs-watch units, one provider-health summary, expanded
map-search labels, 40/44 px map controls, singular/plural labels and display-only
model cleanup. Canonical identities and diagnostic resolution behavior remain
unchanged. Visual acceptance includes 1280, 768 and 390 px widths and populated,
empty, expanded and filtered states.

Run `python Tests/run-test-suite.py site` and
`Tests/run-backend-api-unit-tests.sh` with Python 3.12/3.13 and Node available.
Guide generation, JSON-LD validation and committed-output parity must pass.
Production completion requires successful site/API workflows and live checks;
local test results alone are not publication evidence.
