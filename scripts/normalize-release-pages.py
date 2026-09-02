#!/usr/bin/env python3
"""Synchronize visible Download release data with the update manifest."""

from __future__ import annotations

import argparse
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


def release_line(locale: str, label: str, published: date) -> str:
    month = MONTHS[locale][published.month - 1]
    versions = {
        "en": f"Latest: <strong>v{label}</strong> <span aria-hidden=\"true\">·</span> Released {published.day} {month} {published.year}",
        "de": f"Neueste Beta: <strong>v{label}</strong> <span aria-hidden=\"true\">·</span> Veröffentlicht am {published.day}. {month} {published.year}",
        "fr": f"Dernière bêta: <strong>v{label}</strong> <span aria-hidden=\"true\">·</span> Publiée le {published.day} {month} {published.year}",
        "pl": f"Najnowsza beta: <strong>v{label}</strong> <span aria-hidden=\"true\">·</span> Wydana {published.day} {month} {published.year}",
        "cs": f"Nejnovější beta: <strong>v{label}</strong> <span aria-hidden=\"true\">·</span> Vydáno {published.day}. {month} {published.year}",
        "it": f"Ultima beta: <strong>v{label}</strong> <span aria-hidden=\"true\">·</span> Pubblicata il {published.day} {month} {published.year}",
    }
    return f'<p class="download-release">{versions[locale]}</p>'


def render(source: str, locale: str, release: dict[str, object], path: Path) -> str:
    label = str(release["releaseLabel"])
    dmg_url = str(release["downloadURL"])
    release_url = str(release["releaseNotesURL"])
    if not dmg_url.endswith(".dmg"):
        raise ValueError("downloadURL must identify the canonical DMG")
    zip_url = f"{dmg_url[:-4]}.zip"
    if not dmg_url.startswith("https://github.com/VooZ2/terento/releases/download/"):
        raise ValueError("downloadURL must use the official Terento GitHub release path")
    if not release_url.startswith("https://github.com/VooZ2/terento/releases/tag/"):
        raise ValueError("releaseNotesURL must use the official Terento GitHub release path")

    source, dmg_count = re.subn(
        r'href="https://github\.com/VooZ2/terento/releases/download/[^\"]+\.dmg"',
        f'href="{dmg_url}"',
        source,
    )
    source, zip_count = re.subn(
        r'href="https://github\.com/VooZ2/terento/releases/download/[^\"]+\.zip"',
        f'href="{zip_url}"',
        source,
    )
    source, notes_count = re.subn(
        r'href="https://github\.com/VooZ2/terento/releases/tag/[^\"]+"',
        f'href="{release_url}"',
        source,
    )
    published = date.fromisoformat(str(release["publishedAt"]))
    source, line_count = re.subn(
        r'<p class="download-release">[\s\S]*?</p>',
        release_line(locale, label, published),
        source,
        count=1,
    )
    if (dmg_count, zip_count, notes_count, line_count) != (1, 1, 1, 1):
        raise ValueError(
            f"{path}: expected one DMG, ZIP, notes, and visible release record; "
            f"got {(dmg_count, zip_count, notes_count, line_count)}"
        )
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
