#!/bin/zsh
set -euo pipefail

repo_root="${0:A:h:h:h:h}"
python3 - "$repo_root" <<'PY'
from pathlib import Path
import sys

root = Path(sys.argv[1])
js = (root / "site/compatibility/compatibility.js").read_text()
data_js = (root / "site/compatibility/compatibility-data.js").read_text()
html = (root / "site/compatibility/index.html").read_text()
css = (root / "site/styles.css").read_text()

required_statuses = ("TESTING", "TESTED", "SUPPORTED", "VERIFIED")
for status in required_statuses:
    assert status in js, f"missing web status: {status}"
    assert f"status-{status.lower()}" in css, f"missing badge style: {status}"

assert 'status-${escapeHtml(statusClass)}' in js, "missing shared status badge template"
assert js.count("createStatusBadge(") >= 3, "cards and explanation must use the shared badge renderer"

assert "How compatibility works" in html
assert "status-info" not in js and "status-info" not in css
assert "info-circle" not in js and "(i)" not in js
assert "Compatibility is based on real installation reports shared by Terento users." in html
assert "Thanks for helping us understand which Garmin models work." in html
assert "Unknown</dt>" not in html
assert 'option value="TESTING"' in html
assert "Garmin models with evidence" in html
assert "compatibilityIdentity" in js
assert "caseSizeMm" in js
assert 'successful > 0 ? "SUPPORTED"' not in js, "web must not promote status from install counts"
assert 'attempted > 0 ? "TESTING"' not in js, "web must not invent a status from attempt counts"
assert 'const rawStatus = String(row.status || row.evidenceStatus || row.calculated_status || "").toUpperCase();' in js
assert "canonicalFamilyKey" in data_js
assert "familyOptions" in data_js
assert "min-width: 74px" in css
print("Compatibility status web tests passed (statuses, exact variants, disclosure, shared badge contract).")
PY

node_bin="${NODE_BIN:-$(command -v node || true)}"
if [[ -z "$node_bin" ]]; then
    echo "Node.js is required for compatibility family data tests." >&2
    exit 1
fi
"$node_bin" "$repo_root/Tests/compatibility-data-tests.cjs"
