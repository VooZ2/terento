#!/usr/bin/env bash
# CI sends only an immutable 063 migration request; root-owned VPS
# configuration owns execution through the fixed SSH command dispatcher.
set -euo pipefail
role="${1:-}"
[[ $# == 1 && "$role" == api ]] || exit 64
[[ "${GITHUB_REPOSITORY:-}" == VooZ2/terento ]] || exit 64
[[ "${GITHUB_REF:-}" == refs/heads/beta ]] || exit 64
[[ "${VPS_IMAGE_DIGEST:-}" =~ ^sha256:[0-9a-f]{64}$ ]] || exit 64
[[ "${GITHUB_SHA:-}" =~ ^[0-9a-f]{40}$ ]] || exit 64
[[ "${VPS_MIGRATION_063_SHA256:-}" =~ ^[0-9a-f]{64}$ ]] || exit 64
[[ "${VPS_MIGRATE_PY_SHA256:-}" =~ ^[0-9a-f]{64}$ ]] || exit 64
: "${VPS_SSH_KEY:?Scoped environment SSH key required}"
: "${RUNNER_TEMP:?Runner temporary directory required}"
umask 077
keydir="$(mktemp -d "$RUNNER_TEMP/rukas-ssh.XXXXXX")"
trap 'rm -rf -- "$keydir"' EXIT
printf '%s\n' "$VPS_SSH_KEY" > "$keydir/key"
unset VPS_SSH_KEY
printf '%s\n' '179.198.204.47 ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAII4/GzEE6xDFxBp4kE17EKNR3q70vpmkOJSp7/otiAq0' > "$keydir/known_hosts"
request="migrate --target 063 --image $VPS_IMAGE_DIGEST --revision $GITHUB_SHA --expected-migration-063-sha256 $VPS_MIGRATION_063_SHA256 --expected-migrate-py-sha256 $VPS_MIGRATE_PY_SHA256"
for attempt in 1 2 3; do
  result=0
  ssh -i "$keydir/key" -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes \
    -o "UserKnownHostsFile=$keydir/known_hosts" -o ConnectTimeout=15 \
    "terento-ci-$role@179.198.204.47" "$request" \
    > "$keydir/response" 2>&1 || result=$?
  cat "$keydir/response"
  [[ "$result" == 0 ]] && exit 0
  # A lost established SSH session has unknown remote outcome: do not replay it.
  if [[ "$result" != 255 ]] || ! grep -Eq '^ssh: connect to host .* port 22: Connection timed out$' "$keydir/response" || [[ "$attempt" == 3 ]]; then
    exit "$result"
  fi
  sleep "$((attempt * 2))"
done
