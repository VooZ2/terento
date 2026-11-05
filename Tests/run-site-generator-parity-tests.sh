#!/bin/sh
set -eu

cd "$(dirname "$0")/.."

PYTHONDONTWRITEBYTECODE=1 python3 - <<'PYTHON'
import runpy

# The Download page renders its release line from the manifest label family
# (stable, rc, beta); other labels are rejected and a round trip is lossless.
import json
release_pages = runpy.run_path("scripts/normalize-release-pages.py")
published = json.loads(open("site/updates/macos-arm64.json", encoding="utf-8").read())
candidate = dict(published, releaseLabel="1.0.0-rc.1", releaseTag="v1.0.0-rc.1-build41",
                 downloadURL="https://github.com/VooZ2/terento/releases/download/v1.0.0-rc.1-build41/Terento-1.0.0-rc.1-macOS-arm64.dmg",
                 releaseNotesURL="https://github.com/VooZ2/terento/releases/tag/v1.0.0-rc.1-build41")
for locale in release_pages["LOCALES"]:
    path = release_pages["page_path"](locale)
    source = path.read_text(encoding="utf-8")
    copy = release_pages["COPY"][locale]
    assert release_pages["render"](source, locale, published, path) == source, f"{locale}: page is current"
    rc = release_pages["render"](source, locale, candidate, path)
    rc_prefix = copy["release_rc"].split("{version}")[0]
    assert rc_prefix + "<strong>v1.0.0-rc.1</strong>" in rc, locale
    assert copy["release_stable"].split("{version}")[0] + "<strong>" not in rc, locale
    assert '"softwareVersion": "1.0.0-rc.1"' in rc, locale
    assert candidate["downloadURL"] in rc, locale
    assert release_pages["render"](rc, locale, published, path) == source, f"{locale}: rc round trip"
    beta = release_pages["render"](source, locale, dict(candidate, releaseLabel="1.0.0-beta.2"), path)
    assert copy["release_beta"].split("{version}")[0] + "<strong>v1.0.0-beta.2</strong>" in beta, locale
    for label in ("1.0", "01.0.0", "1.0.0-RC.1", "1.0.0-rc.0", "1.0.0-beta.0", "1.0.0-rc.1-local", "1.0.0-local"):
        try:
            release_pages["render"](source, locale, dict(candidate, releaseLabel=label), path)
        except ValueError:
            pass
        else:
            raise AssertionError(f"{locale}: unsupported release label accepted: {label}")
    try:
        release_pages["render"](source, locale, dict(published, sha256="nope"), path)
    except ValueError:
        pass
    else:
        raise AssertionError(f"{locale}: malformed sha256 accepted")
print("Download release-candidate and stable copy checks passed for all six locales.")
PYTHON

generated="site/privacy/index.html
site/legal/index.html
site/guides/install-garmin-maps-mac/index.html
site/de/guides/install-garmin-maps-mac/index.html
site/fr/guides/install-garmin-maps-mac/index.html
site/pl/guides/install-garmin-maps-mac/index.html
site/cs/guides/install-garmin-maps-mac/index.html
site/it/guides/install-garmin-maps-mac/index.html
site/guides/troubleshooting/index.html
site/de/guides/troubleshooting/index.html
site/fr/guides/troubleshooting/index.html
site/pl/guides/troubleshooting/index.html
site/cs/guides/troubleshooting/index.html
site/it/guides/troubleshooting/index.html
site/guides/install-garmin-maps-edge-mac/index.html
site/de/guides/install-garmin-maps-edge-mac/index.html
site/fr/guides/install-garmin-maps-edge-mac/index.html
site/pl/guides/install-garmin-maps-edge-mac/index.html
site/cs/guides/install-garmin-maps-edge-mac/index.html
site/it/guides/install-garmin-maps-edge-mac/index.html
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
site/it/compatibility/index.html
site/map-styles/index.html
site/de/map-styles/index.html
site/fr/map-styles/index.html
site/pl/map-styles/index.html
site/cs/map-styles/index.html
site/it/map-styles/index.html"

regenerate_site() {
  PYTHONDONTWRITEBYTECODE=1 python3 scripts/build-legal-pages.py >/dev/null
  PYTHONDONTWRITEBYTECODE=1 python3 scripts/normalize-release-pages.py --write
  PYTHONDONTWRITEBYTECODE=1 python3 scripts/build-about-pages.py >/dev/null
  PYTHONDONTWRITEBYTECODE=1 python3 scripts/normalize-home-ia.py >/dev/null
  PYTHONDONTWRITEBYTECODE=1 python3 scripts/build-guide-pages.py
  PYTHONDONTWRITEBYTECODE=1 python3 scripts/add-guide-links.py >/dev/null
  PYTHONDONTWRITEBYTECODE=1 python3 scripts/build-compatibility-pages.py >/dev/null
  PYTHONDONTWRITEBYTECODE=1 python3 scripts/build-map-style-pages.py >/dev/null
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

# The scheduled compatibility refresh runs only build-compatibility-pages.py.
# It must write exactly what the full site build writes, or every refresh PR
# fails this parity test (2026-11-02..04: compatibility-locales.js cache version).
compatibility="site/compatibility/index.html
site/de/compatibility/index.html
site/fr/compatibility/index.html
site/pl/compatibility/index.html
site/cs/compatibility/index.html
site/it/compatibility/index.html"
before="$(cksum $compatibility)"
PYTHONDONTWRITEBYTECODE=1 python3 scripts/build-compatibility-pages.py >/dev/null
after="$(cksum $compatibility)"
if [ "$before" != "$after" ]; then
  echo "Compatibility refresh generator output differs from the full site build." >&2
  exit 1
fi

echo "Guide and public-link generator parity passed for all six locales."
