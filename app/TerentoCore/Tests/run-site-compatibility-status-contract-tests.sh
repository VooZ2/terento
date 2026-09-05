#!/bin/sh
set -eu

repo_root="$(CDPATH= cd -- "$(dirname "$0")/../../.." && pwd)"
python3 - "$repo_root" <<'PY'
from pathlib import Path
import json
import sys

root = Path(sys.argv[1])
js = (root / "site/compatibility/compatibility.js").read_text()
data_js = (root / "site/compatibility/compatibility-data.js").read_text()
html = (root / "site/compatibility/index.html").read_text()
css = (root / "site/styles.css").read_text()
compatibility_files = [root / "site/compatibility/index.html", *sorted((root / "site").glob("*/compatibility/index.html"))]
snapshot = json.loads((root / "site/compatibility/public-models.snapshot.json").read_text())
snapshot_models = snapshot["models"]
assert snapshot["schemaVersion"] == 1
assert snapshot_models and all(row["evidenceStatus"] in ("TESTING", "TESTED", "SUPPORTED", "VERIFIED") for row in snapshot_models)
locales = ("de", "fr", "pl", "cs", "it")
public_pages = [
    root / "site/index.html",
    root / "site/download/index.html",
    root / "site/about/index.html",
    root / "site/guides/install-garmin-maps-mac/index.html",
    root / "site/legal/index.html",
    root / "site/privacy/index.html",
    *compatibility_files,
]
for locale in locales:
    public_pages.extend(
        [
            root / f"site/{locale}/index.html",
            root / f"site/{locale}/download/index.html",
            root / f"site/{locale}/about/index.html",
            root / f"site/{locale}/guides/install-garmin-maps-mac/index.html",
        ]
    )

for path in public_pages:
    page = path.read_text()
    assert "Freizeitkarte" in page and "OpenTopoMap" in page, f"{path}: public provider scope is incomplete"
    assert "Pre-MVP" not in page and "pre-MVP" not in page and "pre-release" not in page, f"{path}: stale pre-MVP wording"

provider_script = (root / "site/provider-list.js").read_text()
assert 'const PUBLIC_PROVIDER_IDS = new Set(["freizeitkarte", "opentopomap"]);' in provider_script

required_statuses = ("TESTING", "TESTED", "SUPPORTED", "VERIFIED")
for status in required_statuses:
    assert status in js, f"missing web status: {status}"
    assert f"status-{status.lower()}" in css, f"missing badge style: {status}"

assert 'status-${escapeHtml(statusClass)}' in js, "missing shared status badge template"
assert js.count("createStatusBadge(") >= 3, "cards and explanation must use the shared badge renderer"

assert "How compatibility works" in html
assert "status-info" not in js and "status-info" not in css
assert "info-circle" not in js and "(i)" not in js
assert "Public compatibility is based on real installation evidence for exact Garmin models and variants." in html
assert "models with evidence" in html
assert "Unknown</dt>" not in html
assert 'option value="TESTING"' in html
assert "compatibilityIdentity" in js
assert "caseSizeMm" in js
assert 'successful > 0 ? "SUPPORTED"' not in js, "web must not promote status from install counts"
assert 'attempted > 0 ? "TESTING"' not in js, "web must not invent a status from attempt counts"
assert 'const rawStatus = String(row.status || row.evidenceStatus || row.calculated_status || "").toUpperCase();' in js
assert "canonicalFamilyKey" in data_js
assert "familyOptions" in data_js
assert "min-width: 74px" in css
assert "data-summary-loading" in html
assert 'data-summary-content>' in html
assert 'id="compatibility-snapshot"' in html
assert "initializeSnapshot" in js
assert "invalid_compatibility_response" in js
assert "compatibility_http_" in js
assert "quiet && state.hasLoaded" in js
for path in compatibility_files:
    page = path.read_text()
    assert 'class="compatibility-summary-line compatibility-summary-loading"' in page, f"{path}: missing localized loading state"
    assert 'data-summary-content>' in page, f"{path}: snapshot summary must be present in initial HTML"
    assert 'id="compatibility-snapshot"' in page, f"{path}: missing compatibility snapshot"
    assert '<noscript class="compatibility-noscript">' in page, f"{path}: missing no-JS snapshot"
    assert f'<strong data-summary="models">{len(snapshot_models)}</strong>' in page, f"{path}: snapshot model count is not rendered"
    assert page.count('<article class="watch-card"') == len(snapshot_models), f"{path}: snapshot card count is not rendered"
    assert 'compatibility.js?v=20260904-snapshot' in page, f"{path}: missing cache-busted compatibility script"
print("Compatibility status web tests passed (statuses, snapshot, exact variants, disclosure, shared badge contract).")
PY

. "$repo_root/Tests/node-runtime.sh"
"$NODE_BIN" "$repo_root/Tests/shared-compatibility-data-tests.cjs"
