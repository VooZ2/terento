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
    assert row['route'] in {'catalog.json','catalog-v3.json','catalog-v4.json','catalog-v5.json'}
    assert re.fullmatch(r'v[0-9A-Za-z.-]+',row['tag'])
    print(row['commit'],row['route'],row['tag'])
PYCLIENT
validated=0
# fd 3 keeps child commands from consuming the client list on stdin.
while read -r -u 3 commit route tag; do
  git -C "$repo_root" cat-file -e "$commit^{commit}" 2>/dev/null || git -C "$repo_root" fetch origin "$commit"
  mkdir "$work_dir/$commit"
  git -C "$repo_root" archive "$commit" | tar -x -C "$work_dir/$commit"
  python3 "$repo_root/scripts/ci_http.py" "released-$route" --fail --silent --show-error \
    --connect-timeout 10 --max-time 60 --output "$work_dir/catalog.json" "https://api.terento.app/maps/$route"
  print "Checking $tag ($commit) against $route"
  # Repair only the historical synthetic test fixture; production sources stay pinned.
  python3 "$repo_root/scripts/prepare-released-catalog-tests.py" "$work_dir/$commit"
  runner="$work_dir/$commit/app/TerentoCore/Tests/run-native-provider-neutral-tests.sh"
  TERENTO_CATALOG_CONTRACT_PATH="$work_dir/catalog.json" /bin/zsh "$runner"
  validated=$((validated + 1))
done 3< "$work_dir/clients"
expected="$(wc -l < "$work_dir/clients" | tr -d ' ')"
if (( validated == 0 || validated != expected )); then
  print -u2 "Validated $validated of $expected released catalog clients"
  exit 1
fi
print "Validated $validated released catalog clients"
