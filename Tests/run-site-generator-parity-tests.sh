#!/bin/sh
set -eu

cd "$(dirname "$0")/.."

PYTHONDONTWRITEBYTECODE=1 python3 - <<'PYTHON'
import runpy

links = runpy.run_path("scripts/add-guide-links.py")
normalize = links["normalize_download_layout"]
for locale in links["COPY"]:
    source = links["path_for"](locale, "download/index.html").read_text(encoding="utf-8")
    normalized = normalize(source, locale)
    assert normalize(normalized, locale) == normalized, locale
    for layout in ("download-layout", "download-grid", "download-sections", "unknown"):
        try:
            normalize(source.replace('class="download-hero"', f'class="{layout}"'), locale)
        except ValueError as error:
            assert "download-hero" in str(error), error
        else:
            raise AssertionError(f"{locale}: obsolete or unknown layout accepted: {layout}")
print("Download layout checks passed for all six locales.")
PYTHON

generated="site/privacy/index.html
site/legal/index.html
site/guides/install-garmin-maps-mac/index.html
site/de/guides/install-garmin-maps-mac/index.html
site/fr/guides/install-garmin-maps-mac/index.html
site/pl/guides/install-garmin-maps-mac/index.html
site/cs/guides/install-garmin-maps-mac/index.html
site/it/guides/install-garmin-maps-mac/index.html
site/index.html
site/de/index.html
site/fr/index.html
site/pl/index.html
site/cs/index.html
site/it/index.html
site/about/index.html
site/de/about/index.html
site/fr/about/index.html
site/pl/about/index.html
site/cs/about/index.html
site/it/about/index.html
site/download/index.html
site/de/download/index.html
site/fr/download/index.html
site/pl/download/index.html
site/cs/download/index.html
site/it/download/index.html
site/compatibility/index.html
site/de/compatibility/index.html
site/fr/compatibility/index.html
site/pl/compatibility/index.html
site/cs/compatibility/index.html
site/it/compatibility/index.html"

regenerate_site() {
  PYTHONDONTWRITEBYTECODE=1 python3 scripts/build-legal-pages.py >/dev/null
  PYTHONDONTWRITEBYTECODE=1 python3 scripts/normalize-release-pages.py --write
  PYTHONDONTWRITEBYTECODE=1 python3 scripts/build-about-pages.py >/dev/null
  PYTHONDONTWRITEBYTECODE=1 python3 scripts/normalize-home-ia.py >/dev/null
  PYTHONDONTWRITEBYTECODE=1 python3 scripts/build-guide-pages.py
  PYTHONDONTWRITEBYTECODE=1 python3 scripts/add-guide-links.py >/dev/null
  PYTHONDONTWRITEBYTECODE=1 python3 scripts/build-compatibility-pages.py >/dev/null
  PYTHONDONTWRITEBYTECODE=1 python3 scripts/normalize-public-shell.py >/dev/null
  PYTHONDONTWRITEBYTECODE=1 python3 scripts/normalize-site-metadata.py --write >/dev/null
}

before="$(cksum $generated)"
regenerate_site
after="$(cksum $generated)"
if [ "$before" != "$after" ]; then
  echo "Public-site generator output drift detected; regenerate the committed localized pages." >&2
  exit 1
fi

before="$after"
regenerate_site
after="$(cksum $generated)"
if [ "$before" != "$after" ]; then
  echo "Guide generator output is not deterministic." >&2
  exit 1
fi

echo "Guide and public-link generator parity passed for all six locales."
