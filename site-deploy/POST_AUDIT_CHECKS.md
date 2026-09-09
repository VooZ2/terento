# September 9 public/admin audit contract

The public interface and admin presentation use the existing Terento tokens;
no native application release, evidence approval, device operation, or data
collection behavior changes in this patch.

Public compatibility pages embed the approved API snapshot in all six locales.
`scripts/update-compatibility-snapshot.py --check` compares semantic evidence
(not the response generation timestamp) against the live API without writing.
The site publication preflight requires parity. A saved snapshot is explicitly
dated; failed browser refreshes preserve it with a warning and Retry action.
The latest installation date is separately named, not presented as refresh time.

The scheduled refresh proposes a PR rather than writing to protected beta.
An existing pending snapshot PR prevents duplicates. Review, required checks,
and merge remain necessary; GitHub-token PR creation does not automatically
trigger push/PR workflows. Owners must run required checks before merging.
The owner approved the additional `pull-requests: write` permission for this
workflow; no branch protection is bypassed.

Public regression coverage includes six-locale snapshot equality, translated
summaries/DMG recommendation, shared asset versions, offline refresh recovery,
Retry, and Clear filters. Home and Guide describe the existing app Report issue
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
