#!/bin/zsh
set -euo pipefail

repo_root="${0:A:h:h}"
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

assert '"download-click"' in privacy_script
assert '"download-cta-click"' in privacy_script
assert '"dmg"' in privacy_script and '"zip"' in privacy_script
assert '"download-page"' in privacy_script
assert '"home-hero"' in privacy_script
assert '"home-final-cta"' in privacy_script
assert '"support-click"' in privacy_script
assert 'location: "footer"' in privacy_script
assert 'destination: "buymeacoffee"' in privacy_script
conversion_block = privacy_script.split("const setConversionEvent", 1)[1].split("const banner", 1)[0]
assert "addEventListener" not in conversion_block
assert "preventDefault" not in conversion_block
assert "window.umami" not in conversion_block
assert "utm_" not in conversion_block


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
    assert html.count('class="product-showcase product-showcase--muted"') == 2, f"{path}: expected two product showcases"
    assert html.count('class="scope-section"') == 1, f"{path}: expected beta scope section"
    assert html.count("<details>") == 6, f"{path}: expected six FAQ answers"
    assert 'class="final-cta"' in html, f"{path}: expected final CTA"
    assert "/assets/app/optimized/your-garmin-640.avif" in html, f"{path}: expected responsive hero artwork"
    items = anchors(path)
    hero = [item for item in items if "text-link" in item["class"] and urlparse(item["href"]).path.endswith("/download/")]
    assert len(hero) == 1, f"{path}: expected one home hero CTA"
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
    assert all("text-link" not in item["class"] and "download-action" not in item["class"] for item in header_downloads)

for path in download_files:
    html = path.read_text(encoding="utf-8")
    versions = set(re.findall(r"v1\.0\.0-beta\.\d+", html))
    assert versions == {"v1.0.0-beta.6"}, f"{path}: expected current beta.6 release metadata"
    items = anchors(path)
    dmg = [item for item in items if urlparse(item["href"]).path.lower().endswith(".dmg")]
    zip_files = [item for item in items if urlparse(item["href"]).path.lower().endswith(".zip")]
    assert len(dmg) == 1, f"{path}: expected one DMG download"
    assert len(zip_files) == 1, f"{path}: expected one ZIP download"
    assert "/releases/download/" in dmg[0]["href"], f"{path}: unexpected DMG URL {dmg[0]['href']}"
    assert "/releases/download/" in zip_files[0]["href"], f"{path}: unexpected ZIP URL {zip_files[0]['href']}"

update = json.loads((root / "site/updates/macos-arm64.json").read_text(encoding="utf-8"))
assert update["build"] == 5
assert update["releaseLabel"] == "1.0.0-beta.6"
assert update["downloadURL"].endswith("/Terento-1.0.0-beta.6-macOS-arm64.dmg")
assert update["sha256"] == "f206816fbee38fe2092cdfc91d58eb68e88c2b0f7ee0c909c327b4b1d455ccb5"

assert "data-umami-event" not in privacy_script
assert "data-umami-event-file" not in privacy_script
assert "link.dataset.umamiEvent" in privacy_script
assert "const attribute = `umamiEvent" in privacy_script
assert "key.charAt(0).toUpperCase()" in privacy_script

assert 'href="https://buymeacoffee.com/vooz2"' in site_shell
assert 'class="footer-support-link" data-support-link' in site_shell
assert 'Support Terento' in site_shell

for path in [root / "site/index.html", *sorted(root.glob("site/*/index.html")), *sorted(root.glob("site/*/download/index.html")), root / "site/download/index.html"]:
    html = path.read_text(encoding="utf-8")
    if 'class="footer-status"' not in html:
        continue
    assert 'href="https://buymeacoffee.com/vooz2"' in html, f"{path}: missing static support link"
    assert 'class="footer-support-link"' in html, f"{path}: missing support link class"
    assert 'data-umami-event="support-click"' not in html, f"{path}: tracking must remain consent-gated"
    support = [item for item in anchors(path) if "footer-support-link" in item["class"]]
    assert len(support) == 1, f"{path}: expected one support link"
    assert any("footer-identity" in ancestor for ancestor in support[0]["ancestors"]), f"{path}: support link moved out of footer metadata"
    assert not any("footer-nav" in ancestor for ancestor in support[0]["ancestors"]), f"{path}: support link entered footer navigation"

print("PASS: localized beta parity, Umami conversion taxonomy, CTA scope, download links, and failure-safe behavior")
PY
