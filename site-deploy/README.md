# Public site deployment

The production site runs on the personal Hostinger VPS. Cloudflare provides DNS,
HTTPS and the proxy edge; it is not the site origin or a Cloudflare Pages project.
A restricted host Caddy service terminates origin TLS and forwards site traffic to
the unprivileged Caddy container on loopback. API traffic uses its separate route.

`.github/workflows/deploy-site.yml` publishes the tracked `site/` tree after a
push to `beta` or a `v*` tag. The reusable `publish-vps-images.yml` workflow runs
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

The September 2026 legal-notice rollout also synchronizes the previously
published `970a16a` public-site polish into `beta`. Production had received
that site revision through a separate deployment. Retain its shared menu,
language-label and layout behavior when deploying the legal-notice update.

## 2026-09-05 About, Home and Download refresh

About now leads with product value and a short maker story. Home uses the
Installing maps screenshot. Download pairs a compact Your Garmin preview with
Free, Notarized and Apple Silicon badges sharing the Guide CSS rule. All six
locales use stylesheet version `20260905-shared-badges-v1`. App release files
and hardware compatibility claims are unchanged. Full public-site and release
preflight checks must pass before the workflow publishes this source.

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

The `rukas-api` environment permits only branch `beta`; `rukas-site` permits
branch `beta` and `v*` tags. The publisher requires a tagged site revision to be an ancestor of `beta`.
API release dispatch remains beta-only. The access-check workflow performs command
rejection checks only and cannot replay an older deployment. The temporary
`terento/vps-image-publish` environment policies have been removed. Workflows
paused for the cutover have been re-enabled.

API publication depends on the backend/PostgreSQL quality workflow. The installed
root-owned handler owns schema migration and internal checks. Public Access/API
contracts, release-client validation and operations observations remain CI gates.
Both server `verify-public` markers must remain present during production releases
so the handler checks public routes as well as loopback. Public checks establish
this host's serving readiness only after DNS actually routes traffic here.

The personal-VPS cutover and scoped workflow merge have occurred. Site deployment
run `33996930727` and API deployment run `33996929154`, including its native
release-client check, passed. At this documentation update, final migrated-owner
login confirmation and independent demo recovery access remain pending acceptance
items; successful CI does not establish either. The old demo authorized public key
and local CI private key are retained until those checks pass. Removing the old
repository secrets does not revoke that server key. After verifying independent
owner/console rollback access, revoke only the exact demo CI authorized-key entry
and retire its local private key; preserve unrelated accounts and keys.

Root provisioning preserves operations-ingest secret continuity; CI no longer
uploads or edits server environment files. Future rotation must update root
configuration and GitHub together. No Access administrator or service bypass token
is provided to CI. Never run two writable production copies. Once any new writer
runs, including the scheduler, returning to the demo requires a freeze and reverse
data synchronization; image or DNS rollback does not revert database writes or
schema migrations.
