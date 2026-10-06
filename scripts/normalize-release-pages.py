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


# Visible wording follows the manifest label family (VERSIONING.md). The
# public program stays a beta; only the description of the current build
# changes when the manifest publishes a release candidate. A stable label needs
# its own copy review, so it is rejected instead of being described as a beta.
LATEST = {
    "beta": {"en": "Latest", "de": "Neueste Beta", "fr": "Dernière bêta", "pl": "Najnowsza beta", "cs": "Nejnovější beta", "it": "Ultima beta"},
    "rc": {
        "en": "Latest",
        "de": "Neuester Release Candidate",
        "fr": "Dernière version candidate",
        "pl": "Najnowsza wersja kandydująca",
        "cs": "Nejnovější kandidát na vydání",
        "it": "Ultima release candidate",
    },
}
CURRENT_BUILD = {
    "beta": {
        "en": "This is the current Terento beta.",
        "de": "Dies ist die aktuelle Terento-Beta.",
        "fr": "Il s’agit de la bêta actuelle de Terento.",
        "pl": "To aktualna beta Terento.",
        "cs": "Jde o aktuální betu Terento.",
        "it": "Questa è la beta attuale di Terento.",
    },
    "rc": {
        "en": "This is the current Terento release candidate.",
        "de": "Dies ist der aktuelle Terento Release Candidate.",
        "fr": "Il s’agit de la version candidate actuelle de Terento.",
        "pl": "To aktualna wersja kandydująca Terento.",
        "cs": "Jde o aktuálního kandidáta na vydání Terento.",
        "it": "Questa è la release candidate attuale di Terento.",
    },
}


def release_family(label: str) -> str:
    match = re.fullmatch(r"\d+\.\d+\.\d+-(beta|rc)\.[1-9]\d*", label)
    if not match:
        raise ValueError(f"unsupported public release label for Download copy: {label}")
    return match.group(1)


def release_line(locale: str, label: str, published: date) -> str:
    month = MONTHS[locale][published.month - 1]
    latest = LATEST[release_family(label)][locale]
    versions = {
        "en": f"{latest}: <strong>v{label}</strong> <span aria-hidden=\"true\">·</span> Released {published.day} {month} {published.year}",
        "de": f"{latest}: <strong>v{label}</strong> <span aria-hidden=\"true\">·</span> Veröffentlicht am {published.day}. {month} {published.year}",
        "fr": f"{latest}: <strong>v{label}</strong> <span aria-hidden=\"true\">·</span> Publiée le {published.day} {month} {published.year}",
        "pl": f"{latest}: <strong>v{label}</strong> <span aria-hidden=\"true\">·</span> Wydana {published.day} {month} {published.year}",
        "cs": f"{latest}: <strong>v{label}</strong> <span aria-hidden=\"true\">·</span> Vydáno {published.day}. {month} {published.year}",
        "it": f"{latest}: <strong>v{label}</strong> <span aria-hidden=\"true\">·</span> Pubblicata il {published.day} {month} {published.year}",
    }
    return f'<p class="download-release">{versions[locale]}</p>'


def current_build_sentence(source: str, locale: str, label: str) -> tuple[str, int]:
    known = "|".join(re.escape(copy[locale]) for copy in CURRENT_BUILD.values())
    return re.subn(
        rf'(<section class="download-detail"><h2>[^<]+</h2><p>)(?:{known})',
        lambda match: match.group(1) + CURRENT_BUILD[release_family(label)][locale],
        source,
        count=1,
    )


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
    published = date.fromisoformat(str(release["publishedAt"]))
    source, line_count = re.subn(
        r'<p class="download-release">[\s\S]*?</p>',
        release_line(locale, label, published),
        source,
        count=1,
    )
    source, status_count = current_build_sentence(source, locale, label)
    counts = (dmg_count, zip_count, notes_count, line_count, schema_version_count, schema_download_count, schema_notes_count, status_count)
    if counts != (1, 1, 1, 1, 1, 1, 1, 1):
        raise ValueError(
            f"{path}: expected one DMG, ZIP, notes, visible release record, schema release record and current-build status; "
            f"got {counts}"
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
