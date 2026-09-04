#!/bin/sh
set -eu

repo_root="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
python3 - "$repo_root" <<'PY'
from html.parser import HTMLParser
from pathlib import Path
import json
import re
from urllib.parse import urlparse
import sys

root = Path(sys.argv[1])
privacy_script = (root / "site/privacy-consent.js").read_text(encoding="utf-8")
site_shell = (root / "site/site-shell.js").read_text(encoding="utf-8")
umami_version = "20260904-public-link-events-v2"

assert '"download-click"' in privacy_script
assert '"download-cta-click"' in privacy_script
assert '"dmg"' in privacy_script and '"zip"' in privacy_script
assert '"download-page"' in privacy_script
assert '"home-hero"' in privacy_script
assert '"home-final-cta"' in privacy_script
assert '"header-nav"' in privacy_script
assert '"compatibility-link-click"' in privacy_script
assert '"support-click"' in privacy_script
assert '"project-link-click"' in privacy_script
assert 'instrumentCompatibilityLinks(campaignParams)' in privacy_script
assert 'instrumentSupportAndProjectLinks(campaignParams)' in privacy_script
assert 'a[href]:not(.language-option)' in privacy_script
assert '"footer-nav"' in privacy_script
assert '"github-issues"' in privacy_script
assert '"github-source"' in privacy_script
assert '"garmin-support"' in privacy_script
assert '"apple-support"' in privacy_script
assert 'url.protocol === "mailto:"' in privacy_script
assert 'location: "footer"' in privacy_script
assert 'destination: "buymeacoffee"' in privacy_script
assert 'destination: "github"' in privacy_script
conversion_block = privacy_script.split("const setConversionEvent", 1)[1].split("const banner", 1)[0]
assert "addEventListener" not in conversion_block
assert "preventDefault" not in conversion_block
assert "window.umami" not in conversion_block
assert "utm_" in conversion_block
assert "terento-analytics-consent" not in privacy_script
assert "consent-banner" not in privacy_script
assert "privacy-settings" not in privacy_script
assert "getChoice" not in privacy_script
assert "localStorage" not in privacy_script
assert privacy_script.index("instrumentConversionLinks(campaignParams);") < privacy_script.index("loadUmami();")


class AnchorParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack = []
        self.anchors = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a":
            self.anchors.append({
                "href": attrs.get("href", ""),
                "class": set(attrs.get("class", "").split()),
                "attributes": attrs,
                "ancestors": [set(item.get("class", "").split()) for item in self.stack],
            })
        self.stack.append({"tag": tag, "class": attrs.get("class", "")})

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index]["tag"] == tag:
                del self.stack[index:]
                break


def anchors(path):
    parser = AnchorParser()
    parser.feed(path.read_text(encoding="utf-8"))
    return parser.anchors


allowed_internal_events = {
    "compatibility-link-click",
    "download-cta-click",
    "faq-link-click",
    "guide-link-click",
    "home-link-click",
    "internal-link-click",
    "language-switch-click",
    "legal-link-click",
    "navigation-link-click",
    "privacy-link-click",
}
for path in sorted((root / "site").rglob("*.html")):
    html = path.read_text(encoding="utf-8")
    for heading in re.findall(r"<h1\b[^>]*>([\s\S]*?)</h1>", html, flags=re.IGNORECASE):
        text = re.sub(r"<[^>]+>", "", heading).strip()
        assert not text.endswith("."), f"{path}: H1 must not end with a full stop"
    for item in anchors(path):
        href = item["href"]
        if not (href.startswith("/") or href.startswith("#")):
            continue
        event = item["attributes"].get("data-umami-event")
        location = item["attributes"].get("data-umami-event-location")
        assert event in allowed_internal_events, f"{path}: internal link {href!r} has no standard Umami event"
        assert location and re.fullmatch(r"[a-z0-9-]+", location), f"{path}: internal link {href!r} has no standard Umami location"


home_files = [
    root / "site/index.html",
    root / "site/de/index.html",
    root / "site/fr/index.html",
    root / "site/pl/index.html",
    root / "site/cs/index.html",
    root / "site/it/index.html",
]
download_files = [
    root / "site/download/index.html",
    root / "site/de/download/index.html",
    root / "site/fr/download/index.html",
    root / "site/pl/download/index.html",
    root / "site/cs/download/index.html",
    root / "site/it/download/index.html",
]

for path in home_files:
    html = path.read_text(encoding="utf-8")
    assert html.count('class="map-feature-section"') == 1, f"{path}: expected one consolidated map feature section"
    assert html.count('class="map-feature-tab"') == 2, f"{path}: expected Install and Manage feature tabs"
    assert 'class="scope-section"' not in html, f"{path}: Beta scope section must be removed"
    assert html.count('class="provider-card"') == 2, f"{path}: expected two provider cards"
    assert html.count('class="provider-benefits"') == 2, f"{path}: expected one benefits list per provider"
    assert html.count("<details>") == 5, f"{path}: expected five FAQ answers"
    assert 'class="final-cta"' in html, f"{path}: expected final CTA"
    assert "/assets/app/optimized/your-garmin-640.avif" in html, f"{path}: expected responsive hero artwork"
    items = anchors(path)
    hero = [item for item in items if "hero-download-action" in item["class"] and "download-action" in item["class"] and urlparse(item["href"]).path.endswith("/download/")]
    assert len(hero) == 1, f"{path}: expected one home hero CTA"
    hero_compatibility = [
        item for item in items
        if "hero-compatibility-link" in item["class"]
        and "text-link" in item["class"]
        and urlparse(item["href"]).path.endswith("/compatibility/")
    ]
    assert len(hero_compatibility) == 1, f"{path}: expected one home hero Compatibility CTA"
    assert hero_compatibility[0]["attributes"].get("data-umami-event") == "compatibility-link-click"
    assert hero_compatibility[0]["attributes"].get("data-umami-event-location") == "home-hero"
    if any("final-cta" in ancestor for item in items for ancestor in item["ancestors"]):
        final = [
            item for item in items
            if "download-action" in item["class"]
            and any("final-cta" in ancestor for ancestor in item["ancestors"])
            and urlparse(item["href"]).path.endswith("/download/")
        ]
        assert len(final) == 1, f"{path}: expected one home final CTA"

    header_downloads = [
        item for item in items
        if urlparse(item["href"]).path.endswith("/download/")
        and any("site-header" in ancestor for ancestor in item["ancestors"])
    ]
    assert header_downloads, f"{path}: expected header download navigation"
    assert all("download-action" in item["class"] for item in header_downloads)

for path in download_files:
    html = path.read_text(encoding="utf-8")
    update = json.loads((root / "site/updates/macos-arm64.json").read_text(encoding="utf-8"))
    expected_version = f'v{update["releaseLabel"]}'
    versions = set(re.findall(r"v1\.0\.0-beta\.\d+", html))
    assert versions == {expected_version}, f"{path}: expected current release metadata"
    items = anchors(path)
    dmg = [item for item in items if urlparse(item["href"]).path.lower().endswith(".dmg")]
    zip_files = [item for item in items if urlparse(item["href"]).path.lower().endswith(".zip")]
    assert len(dmg) == 1, f"{path}: expected one DMG download"
    assert len(zip_files) == 1, f"{path}: expected one ZIP download"
    compatibility = [
        item for item in items
        if "download-info-link" in item["class"]
        and urlparse(item["href"]).path.endswith("/compatibility/")
    ]
    assert len(compatibility) == 1, f"{path}: expected one Download compatibility link"
    assert compatibility[0]["attributes"].get("data-umami-event") == "compatibility-link-click"
    assert compatibility[0]["attributes"].get("data-umami-event-location") == "download-page"
    assert "/releases/download/" in dmg[0]["href"], f"{path}: unexpected DMG URL {dmg[0]['href']}"
    assert "/releases/download/" in zip_files[0]["href"], f"{path}: unexpected ZIP URL {zip_files[0]['href']}"
    assert dmg[0]["href"] == update["downloadURL"], f"{path}: DMG URL drifted from update manifest"
    assert zip_files[0]["href"] == update["downloadURL"][:-4] + ".zip", f"{path}: ZIP URL drifted from update manifest"

compatibility_files = [
    root / "site/compatibility/index.html",
    root / "site/de/compatibility/index.html",
    root / "site/fr/compatibility/index.html",
    root / "site/pl/compatibility/index.html",
    root / "site/cs/compatibility/index.html",
    root / "site/it/compatibility/index.html",
]
for path in compatibility_files:
    html = path.read_text(encoding="utf-8")
    assert 'data-umami-event="download-cta-click"' in html, f"{path}: missing compatibility CTA event"
    assert 'data-umami-event-location="compatibility-community-testing"' in html, f"{path}: missing compatibility CTA location"

update = json.loads((root / "site/updates/macos-arm64.json").read_text(encoding="utf-8"))
assert update["build"] > 0
assert re.fullmatch(r"1\.0\.0-beta\.\d+", update["releaseLabel"])
assert update["downloadURL"].endswith(f'/Terento-{update["releaseLabel"]}-macOS-arm64.dmg')
assert re.fullmatch(r"[0-9a-f]{64}", update["sha256"])

assert "data-umami-event" not in privacy_script
assert "data-umami-event-file" not in privacy_script
assert "link.dataset.umamiEvent" in privacy_script
assert "const attribute = `umamiEvent" in privacy_script
assert "key.charAt(0).toUpperCase()" in privacy_script

assert 'href="https://buymeacoffee.com/vooz2"' in site_shell
assert 'class="footer-support-link" data-support-link' in site_shell
assert 'Support Terento' in site_shell
assert 'href="https://github.com/VooZ2/terento"' in site_shell
assert 'class="footer-status footer-project-link" data-project-link' in site_shell
assert 'src="/assets/logo-white.svg"' in site_shell

for path in [root / "site/index.html", *sorted(root.glob("site/*/index.html")), *sorted(root.glob("site/*/download/index.html")), root / "site/download/index.html"]:
    html = path.read_text(encoding="utf-8")
    if 'class="footer-status"' not in html:
        continue
    assert 'href="https://buymeacoffee.com/vooz2"' in html, f"{path}: missing static support link"
    assert 'class="footer-support-link"' in html, f"{path}: missing support link class"
    assert 'class="footer-project-link"' in html, f"{path}: missing GitHub project link class"
    assert '/assets/logo-white.svg' in html, f"{path}: footer must use the white logo"
    assert '<meta name="theme-color" media="(prefers-color-scheme: dark)" content="#222A2B">' in html, f"{path}: missing dark theme color"
    assert 'data-umami-event="support-click"' not in html, f"{path}: support event metadata must remain script-owned"
    assert 'data-umami-event="project-link-click"' not in html, f"{path}: project event metadata must remain script-owned"
    support = [item for item in anchors(path) if "footer-support-link" in item["class"]]
    project = [item for item in anchors(path) if "footer-project-link" in item["class"]]
    assert len(support) == 1, f"{path}: expected one support link"
    assert len(project) == 1, f"{path}: expected one GitHub project link"
    assert project[0]["href"] == "https://github.com/VooZ2/terento", f"{path}: unexpected GitHub project link"
    assert any("footer-identity" in ancestor for ancestor in support[0]["ancestors"]), f"{path}: support link moved out of footer metadata"
    assert any("footer-identity" in ancestor for ancestor in project[0]["ancestors"]), f"{path}: project link moved out of footer metadata"
    assert not any("footer-nav" in ancestor for ancestor in support[0]["ancestors"]), f"{path}: support link entered footer navigation"
    assert not any("footer-nav" in ancestor for ancestor in project[0]["ancestors"]), f"{path}: project link entered footer navigation"

tracked_pages = [
    root / "site/404.html",
    root / "site/index.html",
    root / "site/about/index.html",
    root / "site/compatibility/index.html",
    root / "site/download/index.html",
    root / "site/guides/install-garmin-maps-mac/index.html",
    root / "site/legal/index.html",
    root / "site/privacy/index.html",
    *sorted(root.glob("site/*/index.html")),
    *sorted(root.glob("site/*/about/index.html")),
    *sorted(root.glob("site/*/compatibility/index.html")),
    *sorted(root.glob("site/*/download/index.html")),
    *sorted(root.glob("site/*/guides/install-garmin-maps-mac/index.html")),
]
tracked_pages = [path for path in tracked_pages if path != root / "site/supported-watches/index.html"]
for path in set(tracked_pages):
    html = path.read_text(encoding="utf-8")
    assert html.count('src="/privacy-consent.js?v=') == 1, f"{path}: expected one Umami loader"
    assert html.count(f'src="/privacy-consent.js?v={umami_version}"') == 1, f"{path}: stale Umami loader version"

print("PASS: localized beta parity, Umami conversion taxonomy, CTA scope, download links, and failure-safe behavior")
PY

. "$repo_root/Tests/node-runtime.sh"
"$NODE_BIN" "$repo_root/Tests/site-campaign-attribution-tests.cjs"
