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
