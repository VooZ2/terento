#!/bin/zsh
set -euo pipefail

repo_root="${0:A:h:h:h:h}"
python3 - "$repo_root" <<'PY'
from pathlib import Path
import sys

root = Path(sys.argv[1])
js = (root / "site/compatibility/compatibility.js").read_text()
html = (root / "site/compatibility/index.html").read_text()
css = (root / "site/styles.css").read_text()

required_statuses = ("UNKNOWN", "TESTING", "TESTED", "SUPPORTED", "VERIFIED")
for status in required_statuses:
    assert status in js, f"missing web status: {status}"
    assert f"status-{status.lower()}" in css, f"missing badge style: {status}"

assert 'status-${escapeHtml(statusClass)}' in js, "missing shared status badge template"

assert "How compatibility works" in html
assert "status-info" not in js and "status-info" not in css
assert "not required for any status" in html.lower()
assert "compatibilityIdentity" in js
assert "caseSizeMm" in js
assert "min-width: 74px" in css
print("Compatibility status web tests passed (statuses, exact variants, disclosure, shared badge contract).")
PY
