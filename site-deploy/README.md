# Public site deployment

The production site is currently served by a Caddy container on the existing
Hostinger VPS. Cloudflare provides DNS, HTTPS and the proxy edge; it is not the
site origin or a Cloudflare Pages project.

`.github/workflows/deploy-site.yml` publishes the tracked `site/` tree after a
push to `beta` or a `v*` tag. The workflow connects to the VPS with a GitHub
Actions SSH key, builds the pinned Caddy image, replaces only the `terento-web`
container, and keeps the previous web container as a rollback target only
until the new deployment passes its checks. The workflow then removes that
temporary rollback container; rerunning the same commit also clears a stale
rollback bearing the same release identifier before switching containers. It
does not touch Traefik, the catalog API, PostgreSQL, or map files. After the
new container starts, the workflow first verifies that the update manifest
exists inside the image, then waits up to 60 seconds for the public
Traefik/Cloudflare route to serve the arm64 manifest. A transient route-refresh
delay therefore does not cause an unnecessary rollback.

Configure these GitHub repository secrets before enabling the workflow:

- `TERENTO_SITE_SSH_HOST` — VPS hostname or IP;
- `TERENTO_SITE_SSH_PORT` — usually `22`;
- `TERENTO_SITE_SSH_USER` — the restricted deployment user;
- `TERENTO_SITE_SSH_KEY` — a private deploy key whose public key is authorized
  for that user;
- `TERENTO_SITE_SSH_KNOWN_HOSTS` — the pinned `known_hosts` line for the VPS.

The deployment user needs Docker access and membership/permission for the
`terento-site` Docker network, but must not receive repository secrets or
passwords. The current VPS operator account does not have write access to the
root-owned `/docker/terento-site` checkout, so the workflow deploys from a
temporary Docker build context and does not rewrite that checkout.

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

API deployment verifies the native login and private-page redirect inside its
container. Public checks use `scripts/infra/check-admin-boundary.py`, without an
administrator credential or Access bypass token. The rollout checker accepts the
existing application gate or the exact configured Cloudflare Access login redirect.
After activation, repository variable `TERENTO_ADMIN_ACCESS_REQUIRED=true`
requires the edge gate; unrelated redirects and errors fail. Test with
`python3 Tests/admin-access-boundary-tests.py`.

### Personal VPS production workflow cutover candidate

The scoped deployment workflows publish tested immutable GHCR images in a job
without VPS credentials, then send only an image digest and matching caller
revision to the root-owned personal VPS deployment handler. `rukas-site` and
`rukas-api` each supply their own `VPS_SSH_KEY`; accounts, address and host key
are pinned in `scripts/infra/deploy-vps-image.sh`. API schema migration and native
admin checks stay in the installed root-owned handler/verifier. Public Access,
API contracts, release-client validation and operations observations remain CI
gates. The image publisher retains the public site/release/legal checks, and API
publication depends on the existing backend/PostgreSQL quality workflow.

This change is a cutover candidate: merging it replaces demo deployment workflows.
Do not merge until the final database/assets copy, root-owned API configuration,
origin protections and personal VPS activation are ready, production DNS routes
to the personal VPS, and both root-owned `verify-public` markers are installed.
Before that point public CI checks can reach the demo and cannot establish that a
personal-VPS deployment is publicly serving traffic. Freeze automated demo deploys
and scheduler before final data export; never run two writable production copies.

At coordinated cutover, permit branch `beta` in both GitHub environments and tag
pattern `v*` in `rukas-site` only. Existing site tag releases are preserved; the
publisher additionally requires the tagged commit to be an ancestor of `beta`.
API release dispatch remains beta-only. Remove the rehearsal branch policy after
cutover. Environment policy and secret changes are separate owner-authorized
infrastructure operations, not effects of merging this candidate. The access-check
workflow now performs command rejection checks only and cannot replay an old image.

Root provisioning preserves `TERENTO_OPERATIONS_INGEST_SECRET` continuity; CI no
longer uploads or edits server environment files. Future rotation must update root
configuration and GitHub together. No Access administrator/service bypass token is
provided to CI. Keep old demo credentials for the controlled rollback window, then
revoke them after migration acceptance. Once any new writer runs, including the
scheduler, returning to the demo requires a freeze and reverse data synchronization;
image or DNS rollback does not revert database writes or schema migrations.
