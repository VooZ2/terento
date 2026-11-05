#!/usr/bin/env python3
"""Render the Download pages from download-copy.json and the update manifest."""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RELEASE_PATH = ROOT / "site" / "updates" / "macos-arm64.json"
LOCALES = ("en", "de", "fr", "pl", "cs", "it")
MONTHS = {
    "en": ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"),
    "de": ("Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober", "November", "Dezember"),
    "fr": ("janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"),
    "pl": ("stycznia", "lutego", "marca", "kwietnia", "maja", "czerwca", "lipca", "sierpnia", "września", "października", "listopada", "grudnia"),
    "cs": ("ledna", "února", "března", "dubna", "května", "června", "července", "srpna", "září", "října", "listopadu", "prosince"),
    "it": ("gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"),
}


def page_path(locale: str) -> Path:
    prefix = Path() if locale == "en" else Path(locale)
    return ROOT / "site" / prefix / "download" / "index.html"


COPY = json.loads((ROOT / "scripts" / "templates" / "download-copy.json").read_text(encoding="utf-8"))
# Empty until the Mac App Store listing is live; then the row becomes a link.
APP_STORE_URL = ""
SHOT = "/assets/app/optimized/your-garmin-{width}.{fmt}?v=20260912-app-screens-v2"
SHOT_SIZES = "(max-width: 899px) min(480px, calc(100vw - 32px)), 480px"
# Lucide 0.460.0 `clock` (ISC, see THIRD_PARTY_NOTICES.md); no inline license comment so the
# page carries only the release version string.
CLOCK_ICON = (
    '<svg class="download-v2-store-icon" aria-hidden="true" focusable="false" viewBox="0 0 24 24" fill="none" '
    'stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">'
    '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>'
)


def release_family(label: str) -> str:
    # Visible wording follows the manifest label family (VERSIONING.md): a beta,
    # a release candidate or a stable release. Any other label is rejected.
    match = re.fullmatch(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)(?:-(beta|rc)\.[1-9][0-9]*)?", label)
    if not match:
        raise ValueError(f"unsupported public release label for Download copy: {label}")
    return match.group(1) or "stable"


def release_date(locale: str, published: date) -> str:
    month = MONTHS[locale][published.month - 1]
    if locale in ("de", "cs"):
        return f"{published.day}. {month} {published.year}"
    if locale == "it":
        article = "l'" if published.day in (8, 11) else "il "  # Italian elides before 8 and 11
        return f"{article}{published.day} {month} {published.year}"
    return f"{published.day} {month} {published.year}"


def link(label: str, href: str, event: str, location: str, extra_class: str = "") -> str:
    return (f'<a class="text-link{extra_class}" href="{href}" data-umami-event="{event}" '
            f'data-umami-event-location="{location}">{html.escape(label)}</a>')


def fill(template: str, **links: str) -> str:
    text = html.escape(template, quote=False)
    for key, value in links.items():
        text = text.replace("{" + key + "}", value)
    return text


def render_main(locale: str, release: dict[str, object], dmg_url: str, notes_url: str) -> str:
    c = COPY[locale]
    root = "/" if locale == "en" else f"/{locale}/"
    label = str(release["releaseLabel"])
    sha = str(release.get("sha256", ""))
    if not re.fullmatch(r"[0-9a-f]{64}", sha):
        raise ValueError("release metadata sha256 must be a lowercase SHA-256 digest")
    published = date.fromisoformat(str(release["publishedAt"]))
    release_text = fill(c["release_" + release_family(label)],
                        version=f"<strong>v{html.escape(label)}</strong>", date=html.escape(release_date(locale, published)))
    store = (f'<a class="download-v2-store download-v2-store-link" href="{APP_STORE_URL}" data-umami-event="app-store-click" '
             f'data-umami-event-location="download-page">{html.escape(c["store_label"])}</a>'
             if APP_STORE_URL else
             f'<p class="download-v2-store">{html.escape(c["store_label"])} '
             f'<span class="download-v2-store-status">{CLOCK_ICON}{html.escape(c["store_status"])}</span></p>')
    sources = "".join(
        f'<source type="image/{fmt}" srcset="'
        + ", ".join(f"{SHOT.format(width=w, fmt=fmt)} {w}w" for w in (640, 960, 1280, 1600))
        + f'" sizes="{SHOT_SIZES}">'
        for fmt in ("avif", "webp")
    )
    shot = (f'<figure class="app-shot app-shot--download download-v2-shot"><picture>{sources}'
            f'<img src="{SHOT.format(width=1600, fmt="png")}" width="2358" height="1575" sizes="{SHOT_SIZES}" '
            f'alt="{html.escape(c["shot_alt"])}" decoding="async"></picture></figure>')
    web = fill(c["web_text"],
               web=link(c["web_label"], f"{root}install/", "web-installer-link-click", "download-page"),
               linux=link(c["linux_label"], f"{root}guides/install-garmin-maps-linux/", "guide-link-click", "download-page-linux"))
    needs = "".join(f"<li>{html.escape(item)}</li>" for item in c["needs"])
    steps = "".join(f"<li><h3>{html.escape(title)}</h3><p>{html.escape(body)}</p></li>" for title, body in c["steps"])
    guides = fill(c["guides_text"],
                  watch=link(c["watch_label"], f"{root}guides/install-garmin-maps-mac/", "guide-link-click", "download-page"),
                  edge=link(c["edge_label"], f"{root}guides/install-garmin-maps-edge-mac/", "guide-link-click", "download-page-edge"))
    return (
        '<main id="main-content" class="download-main download-v2"><div class="shell">'
        '<section class="download-v2-hero"><div class="download-v2-copy">'
        f'<h1>{html.escape(c["h1"])}</h1>'
        f'<p class="download-intro">{html.escape(c["intro"])}</p>'
        '<div class="download-v2-actions">'
        f'<a class="download-action download-v2-primary" href="{dmg_url}" rel="noopener noreferrer">{html.escape(c["download"])}</a>'
        f'{store}</div>'
        f'<p class="download-release">{release_text} '
        f'<a class="text-link" href="{notes_url}" rel="noopener noreferrer">{html.escape(c["notes"])}</a></p>'
        f'<p class="download-v2-web">{web}</p>'
        f'</div>{shot}</section>'
        '<div class="download-v2-info">'
        '<section class="download-v2-needs" aria-labelledby="download-needs-title">'
        f'<h2 id="download-needs-title">{html.escape(c["needs_title"])}</h2><ul>{needs}</ul>'
        + link(c["compat_label"], f"{root}compatibility/", "compatibility-link-click", "download-page", " download-info-link")
        + '</section>'
        '<section class="download-v2-steps" aria-labelledby="download-steps-title">'
        f'<h2 id="download-steps-title">{html.escape(c["steps_title"])}</h2><ol>{steps}</ol>'
        f'<p class="download-v2-guides">{guides}</p></section></div>'
        '</div></main>'
    )


def render(source: str, locale: str, release: dict[str, object], path: Path) -> str:
    label = str(release["releaseLabel"])
    dmg_url = str(release["downloadURL"])
    release_url = str(release["releaseNotesURL"])
    if not dmg_url.endswith(".dmg"):
        raise ValueError("downloadURL must identify the canonical DMG")
    if not dmg_url.startswith("https://github.com/VooZ2/terento/releases/download/"):
        raise ValueError("downloadURL must use the official Terento GitHub release path")
    if not release_url.startswith("https://github.com/VooZ2/terento/releases/tag/"):
        raise ValueError("releaseNotesURL must use the official Terento GitHub release path")

    source, main_count = re.subn(
        r'<main id="main-content"[^>]*>[\s\S]*?</main>',
        lambda _: render_main(locale, release, dmg_url, release_url),
        source,
        count=1,
    )
    source, schema_version_count = re.subn(
        r'("softwareVersion":\s*)"[^\"]+"',
        rf'\g<1>"{label}"',
        source,
        count=1,
    )
    source, schema_download_count = re.subn(
        r'("downloadUrl":\s*)"https://github\.com/VooZ2/terento/releases/download/[^\"]+\.dmg"',
        rf'\g<1>"{dmg_url}"',
        source,
        count=1,
    )
    source, schema_notes_count = re.subn(
        r'("releaseNotes":\s*)"https://github\.com/VooZ2/terento/releases/tag/[^\"]+"',
        rf'\g<1>"{release_url}"',
        source,
        count=1,
    )
    counts = (main_count, schema_version_count, schema_download_count, schema_notes_count)
    if counts != (1, 1, 1, 1):
        raise ValueError(f"{path}: expected one main element and one schema release record; got {counts}")
    return source


def outputs() -> list[tuple[Path, str]]:
    release = json.loads(RELEASE_PATH.read_text(encoding="utf-8"))
    required = ("releaseLabel", "downloadURL", "releaseNotesURL", "publishedAt")
    missing = [field for field in required if not release.get(field)]
    if missing:
        raise ValueError(f"release metadata is missing: {', '.join(missing)}")
    return [
        (path, render(path.read_text(encoding="utf-8"), locale, release, path))
        for locale in LOCALES
        for path in (page_path(locale),)
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()
    drift = []
    for path, rendered in outputs():
        current = path.read_text(encoding="utf-8")
        if current == rendered:
            continue
        drift.append(path)
        if args.write:
            path.write_text(rendered, encoding="utf-8")
    if drift and args.check:
        for path in drift:
            print(f"release metadata drift: {path.relative_to(ROOT)}", file=sys.stderr)
        return 1
    if args.write:
        print(f"Synchronized {len(drift)} Download release pages.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
