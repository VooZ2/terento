#!/bin/zsh
# Execute each published client's actual source decoder, pinned independently of beta.
set -euo pipefail
repo_root="$(cd "$(dirname "$0")/.." && pwd)"
work_dir="$(mktemp -d /private/tmp/terento-released-catalog.XXXXXX)"
trap 'rm -rf -- "$work_dir"' EXIT
python3 - "$repo_root/contracts/released-catalog-clients.json" > "$work_dir/clients" <<'PYCLIENT'
import json,re,sys
for row in json.load(open(sys.argv[1])):
    assert re.fullmatch(r'[0-9a-f]{40}',row['commit'])
    assert row['route'] in {'catalog.json','catalog-v3.json','catalog-v4.json'}
    assert re.fullmatch(r'v[0-9A-Za-z.-]+',row['tag'])
    print(row['commit'],row['route'],row['tag'])
PYCLIENT
while read -r commit route tag; do
  git -C "$repo_root" cat-file -e "$commit^{commit}" 2>/dev/null || git -C "$repo_root" fetch origin "$commit"
  mkdir "$work_dir/$commit"
  git -C "$repo_root" archive "$commit" | tar -x -C "$work_dir/$commit"
  python3 "$repo_root/scripts/ci_http.py" "released-$route" --fail --silent --show-error \
    --connect-timeout 10 --max-time 60 --output "$work_dir/catalog.json" "https://api.terento.app/maps/$route"
  print "Checking $tag ($commit) against $route"
  runner="$work_dir/$commit/app/TerentoCore/Tests/run-native-provider-neutral-tests.sh"
  TERENTO_CATALOG_CONTRACT_PATH="$work_dir/catalog.json" /bin/zsh "$runner"
done < "$work_dir/clients"
