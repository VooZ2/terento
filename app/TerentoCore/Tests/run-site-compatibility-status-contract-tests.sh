#!/bin/sh
set -eu

repo_root="$(CDPATH= cd -- "$(dirname "$0")/../../.." && pwd)"
python3 - "$repo_root" <<'PY'
from pathlib import Path
import sys

root = Path(sys.argv[1])
js = (root / "site/compatibility/compatibility.js").read_text()
data_js = (root / "site/compatibility/compatibility-data.js").read_text()
html = (root / "site/compatibility/index.html").read_text()
compatibility_files = [root / "site/compatibility/index.html", *sorted((root / "site").glob("*/compatibility/index.html"))]

assert (root / "site/compatibility/public-models.snapshot.json").exists()
assert "initializeSnapshot" in js
assert "public/models.json" in js
assert "filter((row) => row.successful > 0)" in js
assert "preserveExistingResults" in js
assert "successfulRange" in js
assert "canonicalFamilyKey" in data_js
assert "familyOptions" in data_js
assert "statusCodes" not in js and "createStatusBadge" not in js
assert not any(status in js for status in ("TESTING", "TESTED", "SUPPORTED", "VERIFIED"))

for path in compatibility_files:
    page = path.read_text()
    assert 'id="compatibility-snapshot"' in page, f"{path}: missing checked-in snapshot"
    assert '<article class="watch-card"' in page, f"{path}: missing server-rendered cards"
    assert 'id="successful-install-filter"' in page, f"{path}: missing successful-install filter"
    assert 'id="compatibility-clear"' in page
    assert 'Not seeing your model' in page or 'Brak Twojego modelu' in page or 'Wenn dein Modell' in page or 'L’absence de votre modèle' in page or 'Pokud zde svůj model' in page or 'Se il tuo modello' in page
    assert not any(f'<option value="{status}"' in page for status in ("TESTING", "TESTED", "SUPPORTED", "VERIFIED"))
    assert 'class="compatibility-status' not in page
    assert 'successful-install-filter' in page
    assert '1–2' in page and '5+' in page
    assert 'compatibility.js?v=20260918-compatibility-successful-snapshot-v1' in page
    assert '<noscript class="compatibility-noscript">' in page

print("Compatibility web tests passed (successful-installation snapshot, static cards, filters, disclosure, and fallback contract).")
PY

. "$repo_root/Tests/node-runtime.sh"
"$NODE_BIN" "$repo_root/Tests/shared-compatibility-data-tests.cjs"
