#!/bin/zsh

set -euo pipefail

script_dir="$(cd "$(dirname "$0")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"
catalog_urls=("https://api.terento.app/maps/catalog.json" "https://api.terento.app/maps/catalog-v3.json")
if [[ -n "${TERENTO_CATALOG_CONTRACT_URL:-}" ]]; then
    catalog_urls=("$TERENTO_CATALOG_CONTRACT_URL")
fi
work_dir="$(/usr/bin/mktemp -d /private/tmp/terento-live-catalog-contract.XXXXXX)"
catalog_path="$work_dir/catalog.json"

cleanup() {
    /bin/rm -rf -- "$work_dir"
}
trap cleanup EXIT

for catalog_url in "${catalog_urls[@]}"; do
/usr/bin/python3 "$repo_root/scripts/ci_http.py" live-catalog \
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

catalog_sha256="$(/usr/bin/shasum -a 256 "$catalog_path" | /usr/bin/awk '{print $1}')"
print "Catalog SHA-256: $catalog_sha256"
/usr/bin/python3 - "$catalog_path" "$catalog_url" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    catalog = json.load(handle)

providers = catalog.get("providers", [])
if sys.argv[2].endswith('/maps/catalog.json'):
    ids = {provider.get('id') for provider in providers}
    if ids - {'freizeitkarte', 'opentopomap'}:
        raise SystemExit('Legacy catalog must not expose providers unknown to released clients')
for provider in providers:
    print(f"Catalog provider {provider.get('id', '<missing>')}: {len(provider.get('maps', []))} maps")
print(f"Catalog total: {sum(len(provider.get('maps', [])) for provider in providers)} maps")
PY

TERENTO_CATALOG_CONTRACT_PATH="$catalog_path" \
    "$repo_root/app/TerentoCore/Tests/run-native-provider-neutral-tests.sh"

print "PASS: the release client accepts every entry in $catalog_url"
done
