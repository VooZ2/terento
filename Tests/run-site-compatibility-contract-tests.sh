#!/bin/sh
set -eu

repo_root="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
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
    assert '<article class="watch-card card" data-device-type=' in page, f"{path}: missing server-rendered cards"
    assert 'id="successful-install-filter"' in page, f"{path}: missing successful-install filter"
    assert 'id="compatibility-clear"' in page
    assert 'Not seeing your model' in page or 'Brak Twojego modelu' in page or 'Wenn dein Modell' in page or 'L’absence de votre modèle' in page or 'Pokud zde svůj model' in page or 'Se il tuo modello' in page
    assert not any(f'<option value="{status}"' in page for status in ("TESTING", "TESTED", "SUPPORTED", "VERIFIED"))
    assert 'class="compatibility-status' not in page
    assert 'successful-install-filter' in page
    assert '1–2' in page and '5+' in page
    assert 'compatibility.js?v=20261119-compatibility-cards-v5' in page
    assert '<noscript class="compatibility-noscript">' in page

    assert 'class="watch-install-sources"' in page, f"{path}: missing app/web install split"
    assert 'class="watch-install-source-icon"' in page and 'stroke-width="1.75"' in page, f"{path}: install source icons must follow the outline icon spec"

# Static cards: app/web split and the card rounding rule (exact below 100, then
# rounded down to the hundred with a plus); the page summary stays exact.
import runpy
generator = runpy.run_path(str(root / "scripts/build-compatibility-pages.py"))
card, summary = generator["card_markup"], generator["summary_markup"]
model = {"model": "fēnix 8 · 47 mm, AMOLED", "variant": "47 mm, AMOLED", "caseSizeMm": 47, "family": "fenix", "familyName": "fēnix", "successfulInstallations": 1234, "appSuccessfulInstallations": 1180, "webSuccessfulInstallations": 54, "lastSuccessfulInstallation": "2026-10-11T10:00:00Z"}
english = card(model, "en")
assert ">1,200+ successful installs</p>" in english, english
assert "</svg>App 1,100+</span>" in english and "</svg>Web 54</span>" in english, english
assert "1,200+ successful installs, 1,100+ with the app, 54 with the web installer" in english, english
assert english.count('aria-hidden="true" focusable="false"') == 2
assert ">1.200+ erfolgreiche Installationen</p>" in card(model, "de")
assert ">1 200+ installations réussies</p>" in card(model, "fr")
assert ">1200+ udanych instalacji</p>" in card(model, "pl")
assert ">1 200+ úspěšných instalací</p>" in card(model, "cs")
assert ">1200+ installazioni riuscite</p>" in card(model, "it")
assert "1 100+ přes aplikaci, 54 přes webový instalátor" in card(model, "cs")
quiet = summary({"models": [model]}, "en")
assert '<span data-summary="successes">1,234</span> successful installs on <span data-summary="models">1</span> <span data-summary-model-label>model</span>. <span data-summary-updated>Latest install <time data-summary="updated" datetime="2026-10-11T10:00:00Z">October 11, 2026</time>.</span>' in quiet, quiet
assert "<strong" not in quiet
plain = card({**{k: v for k, v in model.items() if k != "caseSizeMm"}, "variant": "", "model": "fēnix 8"}, "en")
assert "watch-variant" not in plain and "Smartwatch" not in plain, plain
assert "Last install Oct 11, 2026" in english and "/2026" not in english
for count, label in ((1, "1 successful install"), (99, "99 successful installs"), (100, "100+ successful installs"), (199, "100+ successful installs"), (250, "200+ successful installs")):
    assert generator["install_label"](count, "en") == label, (count, generator["install_label"](count, "en"))
app_only = card({**model, "successfulInstallations": 7, "appSuccessfulInstallations": 7, "webSuccessfulInstallations": 0}, "en")
assert "</svg>App 7</span>" in app_only and "Web" not in app_only.split("watch-install-sources", 1)[1].split("</p>", 1)[0]
assert "7 with the app, Last install" in app_only and "web installer" not in app_only
web_only = card({**model, "successfulInstallations": 2, "appSuccessfulInstallations": 0, "webSuccessfulInstallations": 2}, "en")
assert "</svg>Web 2</span>" in web_only and "with the app" not in web_only and "</svg>App" not in web_only
legacy = {key: value for key, value in model.items() if not key.endswith("SuccessfulInstallations") or key == "successfulInstallations"}
assert "</svg>App 1,200+</span>" in card({**legacy, "successfulInstallations": 1234}, "en") and "</svg>Web" not in card(legacy, "en")
try:
    card({**model, "webSuccessfulInstallations": 55}, "en")
except ValueError:
    pass
else:
    raise AssertionError("inconsistent app/web split accepted")

print("Compatibility web tests passed (successful-installation snapshot, static cards, app/web split, card rounding, filters, disclosure, and fallback contract).")
PY

. "$repo_root/Tests/node-runtime.sh"
"$NODE_BIN" "$repo_root/Tests/shared-compatibility-data-tests.cjs"
"$NODE_BIN" "$repo_root/Tests/compatibility-snapshot-growth-tests.cjs"
