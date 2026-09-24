#!/bin/sh
set -eu

repo_root="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
. "$repo_root/Tests/backend-python-runtime.sh"

for test_file in \
  scripts/infra/test-install-terento-production-ops.py \
  scripts/infra/test-terento-deploy.py \
  scripts/infra/test-terento-deploy-migration.py \
  scripts/infra/test-terento-deploy-ssh-entry.py
do
  PYTHONDONTWRITEBYTECODE=1 "$TERENTO_PYTHON_BIN" "$repo_root/$test_file"
done
