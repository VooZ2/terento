#!/bin/sh
set -eu

cd "$(dirname "$0")/.."

generated="site/guides/install-garmin-maps-mac/index.html
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
  PYTHONDONTWRITEBYTECODE=1 python3 scripts/normalize-release-pages.py --write
  PYTHONDONTWRITEBYTECODE=1 python3 scripts/build-guide-pages.py
  PYTHONDONTWRITEBYTECODE=1 python3 scripts/add-guide-links.py >/dev/null
  PYTHONDONTWRITEBYTECODE=1 python3 scripts/normalize-public-shell.py >/dev/null
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
