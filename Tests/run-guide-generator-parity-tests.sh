#!/bin/sh
set -eu

cd "$(dirname "$0")/.."

generated="site/guides/install-garmin-maps-mac/index.html
site/de/guides/install-garmin-maps-mac/index.html
site/fr/guides/install-garmin-maps-mac/index.html
site/pl/guides/install-garmin-maps-mac/index.html
site/cs/guides/install-garmin-maps-mac/index.html
site/it/guides/install-garmin-maps-mac/index.html"

regenerate_site() {
  PYTHONDONTWRITEBYTECODE=1 python3 scripts/build-guide-pages.py
  PYTHONDONTWRITEBYTECODE=1 python3 scripts/add-guide-links.py >/dev/null
  PYTHONDONTWRITEBYTECODE=1 python3 scripts/normalize-public-shell.py >/dev/null
}

regenerate_site
if ! git diff --quiet -- $generated; then
  echo "Guide generator output drift detected; regenerate the six committed guide pages." >&2
  git diff -- $generated >&2 || true
  exit 1
fi

regenerate_site
if ! git diff --quiet -- $generated; then
  echo "Guide generator output is not deterministic." >&2
  exit 1
fi

echo "Guide generator parity passed for all six locales."
