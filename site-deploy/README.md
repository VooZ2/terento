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

Public compatibility pages use a loading shell and the live API, not checked-in
model evidence rows. Initial failure shows Retry; a failed background refresh
labels the last loaded results potentially outdated. API data may change without
requiring a site deployment.

Production content acceptance also requires live HTML/asset and localized Guide
validation plus a recorded Google Rich Results Test for relevant structured-data
changes. Search Console Validate fix is a separate owner action. Test/lab hosts
must stay excluded from indexing; robots.txt alone is not access control.
