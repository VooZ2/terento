#!/usr/bin/env bash
# CI sends only a digest/revision request; root-owned VPS configuration owns execution.
set -euo pipefail
role="${1:-}"
[[ $# == 1 && ( "$role" == site || "$role" == api ) ]] || exit 64
[[ "${GITHUB_REPOSITORY:-}" == VooZ2/terento ]] || exit 64
if [[ "${GITHUB_REF:-}" == refs/heads/beta ]]; then
  :
elif [[ "$role" == site && "${GITHUB_REF:-}" == refs/tags/v* ]]; then
  : # The publication job already verifies the tagged commit belongs to beta.
else
  exit 64
fi
[[ "${VPS_IMAGE_DIGEST:-}" =~ ^sha256:[0-9a-f]{64}$ ]] || exit 64
[[ "${GITHUB_SHA:-}" =~ ^[0-9a-f]{40}$ ]] || exit 64
: "${VPS_SSH_KEY:?Scoped environment SSH key required}"
: "${RUNNER_TEMP:?Runner temporary directory required}"
umask 077
keydir="$(mktemp -d "$RUNNER_TEMP/rukas-ssh.XXXXXX")"
trap 'rm -rf -- "$keydir"' EXIT
printf '%s\n' "$VPS_SSH_KEY" > "$keydir/key"
unset VPS_SSH_KEY
printf '%s\n' '179.198.204.47 ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAII4/GzEE6xDFxBp4kE17EKNR3q70vpmkOJSp7/otiAq0' > "$keydir/known_hosts"
ssh -i "$keydir/key" -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes \
  -o "UserKnownHostsFile=$keydir/known_hosts" -o ConnectTimeout=15 \
  "terento-ci-$role@179.198.204.47" "deploy $VPS_IMAGE_DIGEST $GITHUB_SHA"
