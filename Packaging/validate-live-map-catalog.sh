#!/bin/zsh

set -euo pipefail

script_dir="$(cd "$(dirname "$0")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"
catalog_url="${TERENTO_CATALOG_CONTRACT_URL:-https://api.terento.app/maps/catalog.json}"
work_dir="$(/usr/bin/mktemp -d /private/tmp/terento-live-catalog-contract.XXXXXX)"
catalog_path="$work_dir/catalog.json"

cleanup() {
    /bin/rm -rf -- "$work_dir"
}
trap cleanup EXIT

/usr/bin/curl \
    --fail \
    --silent \
    --show-error \
    --location \
    --proto '=https' \
    --tlsv1.2 \
    --connect-timeout 10 \
    --max-time 30 \
    --output "$catalog_path" \
    "$catalog_url"

[[ -s "$catalog_path" ]] || {
    print -u2 "Live map catalog is empty"
    exit 1
}

TERENTO_CATALOG_CONTRACT_PATH="$catalog_path" \
    "$repo_root/lab/native-connectivity-poc/Tests/run-stage1-provider-neutral-tests.sh"

print "PASS: the release client accepts every entry in $catalog_url"
