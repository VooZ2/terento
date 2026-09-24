# Public site deployment

The production site runs on the personal Hostinger VPS. Cloudflare provides DNS,
HTTPS and the proxy edge; it is not the site origin or a Cloudflare Pages project.
A restricted host Caddy service terminates origin TLS and forwards site traffic to
the unprivileged Caddy container on loopback. API traffic uses its separate route.

`.github/workflows/deploy-site.yml` publishes the tracked `site/` tree after a
relevant push to `beta` (or an explicit beta dispatch). Tags do not deploy the
site a second time. The reusable `publish-vps-images.yml` workflow runs
site/release/legal checks and builds the pinned Caddy image on GitHub Actions. It
publishes the image to GHCR and returns its immutable digest. The site deploy job
then sends only that digest and the matching source revision to the VPS. The
root-owned handler controls Compose, health verification, container registration
and previous-image rollback. CI cannot upload scripts, edit server configuration
or run arbitrary Docker commands. Site deployment does not replace the API or DB.

Configure the following scoped GitHub secrets:

- Environment `rukas-site`: its independent `VPS_SSH_KEY` for `terento-ci-site`.
- Environment `rukas-site`: `TERENTO_INDEXNOW_KEY`, a stable 32-character
  hexadecimal IndexNow key. The secret value is never committed, copied into
  the public image, printed in logs, or included in workflow summaries.
- Environment `rukas-api`: its independent `VPS_SSH_KEY` for `terento-ci-api`.
- Repository `TERENTO_OPERATIONS_INGEST_SECRET`: deployment health observations
  and operational reporting; preserve its value in root-provisioned API settings.
- Repository `SMTP2GO_USERNAME` and `SMTP2GO_PASSWORD`: operational email reports,
  not SSH access or image publication.

The accounts, destination and SSH host key are pinned in
`scripts/infra/deploy-vps-image.sh`. Each SSH key is bound to a fixed project
command; neither CI account needs Docker-group membership or a general shell.
Image publication receives only GitHub's job token with package-write permission
and no VPS credentials. The five retired shared `TERENTO_SITE_SSH_*` repository
secrets have been removed; these workflows use only the scoped environment keys.

The update manifest is deliberately sent with `Cache-Control: no-store` so an
old app-update response cannot remain cached after a release.

### IndexNow key provisioning

The public Caddy image contains no IndexNow key. The owner provisions the same
stable value in two server-only locations before enabling the notification
step:

1. Store the value in the `TERENTO_INDEXNOW_KEY` GitHub environment secret.
2. Store the value, without a trailing newline, in
   `/etc/terento/deployment/site/indexnow-key.txt` and set `INDEXNOW_KEY` to
   that value in the server-only site `release.env`.
3. Keep the key file root-owned with mode `0444` and mount it read-only. The
   operator-only Compose template at
   `internal/infra/vps/deployment/site/compose.json` mounts that exact file read-only at
   `/srv/${INDEXNOW_KEY}.txt`; Caddy serves it as plain text at the
   corresponding random `/<KEY>.txt` path. The read permission is required by
   the unprivileged Caddy container user.

The deployment workflow verifies the live sitemap, changed pages and (when the
CI secret is configured) the key file before sending. A missing or mismatched
key is an IndexNow warning and leaves the site deployment successful; planned
URLs remain pending for a later retry. The secret itself is never passed as a
Docker build argument or SSH command argument. IndexNow does not require a
separate Bing Webmaster Tools registration or a Bing Webmaster API account key.

`.github/indexnow/site-state.json` is the persistent publication and
submission state, not merely a build-content manifest. The build manifest is a
per-run file under `$RUNNER_TEMP`; the checked-in state retains the last
live-verified publication snapshot, accepted URL/fingerprint records, pending
notifications, and the last real submission/HTTP 200 timestamps. Accepted
records are retained and deduplicated by URL plus content fingerprint; pending
records, including their known oldest-pending time, are carried into the next
plan and retried. A no-change run does not change either submission timestamp.
The workflow updates only this file after successful live verification through
a state-only pull request to the protected `beta` branch; the path is outside
the site deployment filters, so state retention does not trigger a second site
deployment. The current workflow uses the default `GITHUB_TOKEN`; a PR created
with it does not trigger new `pull_request` workflows on GitHub. Automatic
state-PR merging therefore still requires a follow-up workflow wiring change
plus an approved non-`GITHUB_TOKEN` automation identity. Until both are
provisioned, the deploy retains the state as a fallback artifact and an
operator must merge the state-only PR after the normal checks pass. If the file is
missing or invalid, the next confirmed publication records a bootstrap
baseline and sends no bulk notification; it does not infer a full-sitemap
submission.

### IndexNow operational reporting

After every production site workflow execution that reaches the deployment
gate, the workflow sends one bounded `INDEXNOW/indexnow` observation to
`POST /internal/operations/observations` using the existing
`TERENTO_OPERATIONS_INGEST_SECRET`. The report distinguishes HTTP 200
submission, HTTP 202 validation-pending, no changes, pending retry, action
required, bootstrap, and live-verification failure. It carries only allowlisted
counts, safe timestamps, a maximum ten-URL public preview, and a short safe
error code; it never carries the IndexNow key, key location, authorization
header, request payload, or raw response.

The report is separate from the IndexNow request. A successful IndexNow
request is written to the local state before the operations report is sent, so
a report-delivery failure is retried through the existing bounded operations
HTTP retry and does not resend URLs. The backend observation insert is
idempotent by `observationId`; a duplicate or late report remains historical
and cannot replace a newer deployment. The authenticated Admin **System
health** page shows the **IndexNow submissions** card. Its status describes
submission evidence only and does not confirm search indexing. A missing
report warning is evaluated only for a deployment that explicitly marked an
IndexNow result as expected, after the documented 30-minute workflow/report
grace period; historical, skipped, superseded, PR, fork, and dry-run runs are
not treated as missing production reports.

Apply the catalog API migration and verify its health before enabling the site
workflow's new report format. The API migration is
`backend/catalog-api/src/terento_catalog/migrations/061_indexnow_operational_observations.sql`.
No production migration, key provisioning, deployment, or real IndexNow
submission is performed by local tests.

### Google Search Console

Search Console submission is not automated because this repository has no
authorized Search Console session or Sitemaps API credential. After the sitemap
is live, the owner should choose the verified Terento property, open
**Sitemaps**, submit `https://terento.app/sitemap.xml`, and confirm the result.
For a Domain property, enter the full URL. For a URL-prefix property whose
prefix is already shown as `https://terento.app/`, enter only `sitemap.xml` so
the domain is not duplicated. The same sitemap address should be maintained,
not resubmitted after every deployment.

The public-shell normalizer also synchronizes the stylesheet cache version on
standalone pages (404 and legacy redirect). The shared brand contract checks
every HTML page, including these pages, before deployment.

### In-page language switching

Legal and Privacy language choices use native buttons so analytics tracking
cannot redirect an in-page language change to Home. Both pages share the
language controller in `site/page-language.js`; translations remain in their
page-specific scripts. Mobile language choices also release the menu scroll
lock. Public shell/CSS versions and generated pages are maintained by the
normalizer. The retired Guide progress script is removed; reading-position
restoration is retained. Download normalization accepts the current layout and
fails explicitly for obsolete layouts.

### Admin edge authentication

The root-owned VPS verifier checks native application login and private-page
protection through loopback. Public CI checks use
`scripts/infra/check-admin-boundary.py` without administrator credentials or an
Access bypass token. `deploy-catalog-api.yml` explicitly sets the checker
environment `TERENTO_ADMIN_ACCESS_REQUIRED: 'true'`, so public native login,
unrelated redirects and errors fail. The former repository variable of that name
is no longer read by the workflow. For a manual strict check, set the environment
variable explicitly; the standalone script retains its transition-mode default.
Test the boundary rules with `python3 Tests/admin-access-boundary-tests.py`.

### Production release and migration boundaries

Both deployment workflows and the scoped request script accept only `beta`.
A release tag records app provenance and triggers release CI, not a second site
publication. GitHub environment restrictions can be stricter, never broader,
than these workflow gates.

API publication depends on the backend/PostgreSQL quality workflow. The installed
root-owned handler owns schema migration and internal checks. Public Access/API
contracts, release-client validation and operations observations remain CI gates.
Both server `verify-public` markers must remain present during production releases
so the handler checks public routes as well as loopback. Public checks establish
this host's serving readiness only after DNS actually routes traffic here.

Host migration acceptance and old-key retirement are operator tasks, separate
from CI. Passing HTTP checks does not prove independent console recovery or
owner login. Do not revoke unrelated keys or infer those gates from a deployment.

Root provisioning preserves operations-ingest secret continuity; CI no longer
uploads or edits server environment files. Future rotation must update root
configuration and GitHub together. No Access administrator or service bypass token
is provided to CI. Never run two writable production copies. Once any new writer
runs, including the scheduler, returning to the demo requires a freeze and reverse
data synchronization; image or DNS rollback does not revert database writes or
schema migrations.

## Public content and verification

Home renders five map choices across six locales: Freizeitkarte, OpenTopoMap,
MapRando, BBBike and BBBike (Ontrail). Counts come from the live validated
catalog; they are not compatibility evidence. The row scrolls when needed.
OpenTopoMap contour information remains an optional disclosure.

Change generated content in its source generator, then regenerate. Public asset
versions are maintained in `scripts/normalize-public-shell.py`; do not copy dated
version strings into this document. `Tests/run-site-tests.sh` covers all-locale
content, layout contracts, structured JSON-LD and generator parity. Release and
legal checks also pass before publication. No production app artifact is rebuilt
by a site deployment.

After deployment, compare the live update manifest's version, label, build,
channel, minimum macOS, official URLs and checksum against the tested input.
Transport retries discard partial responses. The fixed SSH request retries only
connection-establishment timeouts; an established-session failure has unknown
remote outcome and is not automatically replayed. Observation delivery is
reported separately; transient reporting failure cannot invalidate passed tests.

Public compatibility pages contain a generated factual snapshot and refresh
from the live API. Failed background refresh retains the snapshot with a stale
notice and Retry. The six-hour scheduled/manual snapshot workflow fetches the
public API through the bounded CI HTTP transport, validates and regenerates
the snapshot/pages. An unchanged factual snapshot succeeds without a commit,
PR or deployment.

Factual changes use the single workflow-owned
`terento/compatibility-snapshot-refresh` branch and a reusable PR into protected
`beta`; only the snapshot JSON and six generated compatibility HTML files may
be committed. Existing branch ownership is checked before an explicit
force-with-lease update. The workflow never pushes beta directly. It explicitly
dispatches Swift CI and waits for a new run on the exact PR head, including
`build-and-test`, then checks all required PR checks and mergeability before
merging without bypass. Failed checks retain the PR for investigation/reuse.

GitHub-token event suppression is handled explicitly: after a factual PR merge,
the workflow verifies the exact beta merge SHA and dispatches one site deploy,
or reuses an existing exact-SHA active/successful deployment. A failed existing
deploy requires investigation rather than a duplicate dispatch. Concurrent beta
changes fail closed. The automation branch is deleted with an exact lease after
successful deployment. Workflow enablement alone is not a deployment trigger.

Production content acceptance also requires live HTML/asset and localized Guide
validation plus a recorded Google Rich Results Test for relevant structured-data
changes. Search Console Validate fix is a separate owner action. Test/lab hosts
must stay excluded from indexing; robots.txt alone is not access control.
