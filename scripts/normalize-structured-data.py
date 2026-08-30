#!/usr/bin/env python3
"""Render Terento's public JSON-LD from visible page content and release data."""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import textwrap
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "site" / "metadata.json"
RELEASE_PATH = ROOT / "site" / "updates" / "macos-arm64.json"
BASE_URL = "https://terento.app"
REPOSITORY_URL = "https://github.com/VooZ2/terento"
LOGO_URL = f"{BASE_URL}/assets/logo-sky.svg"
ORGANIZATION_ID = f"{BASE_URL}/#organization"
SOFTWARE_ID = f"{BASE_URL}/#software"
JSON_LD_RE = re.compile(
    r"(?P<indent>[ \t]*)<script\b[^>]*type=[\"']application/ld\+json[\"'][^>]*>"
    r"(?P<body>[\s\S]*?)</script>",
    re.IGNORECASE,
)
FAQ_SECTION_RE = re.compile(
    r'<section\b[^>]*\bid=["\']faq["\'][^>]*>(?P<body>[\s\S]*?)</section>',
    re.IGNORECASE,
)
FAQ_ENTRY_RE = re.compile(
    r"<details>\s*<summary>(?P<question>[\s\S]*?)</summary>\s*"
    r"<p>(?P<answer>[\s\S]*?)</p>\s*"
    r"(?:<div class=\"faq-support-actions\">[\s\S]*?</div>\s*)?</details>",
    re.IGNORECASE,
)


def json_ld(source: str, path: Path) -> dict:
    matches = list(JSON_LD_RE.finditer(source))
    if len(matches) != 1:
        raise ValueError(f"{path}: expected exactly one JSON-LD block")
    try:
        value = json.loads(matches[0].group("body").strip())
    except json.JSONDecodeError as error:
        raise ValueError(f"{path}: invalid JSON-LD: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"{path}: JSON-LD root must be an object")
    return value


def entity(data: dict, entity_type: str, path: Path) -> dict:
    if data.get("@type") == entity_type:
        return data
    for item in data.get("@graph", []):
        if item.get("@type") == entity_type:
            return item
    raise ValueError(f"{path}: missing {entity_type} entity")


def visible_text(fragment: str) -> str:
    without_tags = re.sub(r"<[^>]+>", "", fragment)
    return " ".join(html.unescape(without_tags).split())


def visible_faq(source: str, path: Path) -> list[dict[str, str]]:
    section = FAQ_SECTION_RE.search(source)
    if not section:
        raise ValueError(f"{path}: missing visible #faq section")
    entries = [
        {
            "question": visible_text(match.group("question")),
            "answer": visible_text(match.group("answer")),
        }
        for match in FAQ_ENTRY_RE.finditer(section.group("body"))
    ]
    if not entries:
        raise ValueError(f"{path}: visible #faq section has no entries")
    return entries


def canonical_url(page: dict) -> str:
    path = page["path"]
    if not path.startswith("/") or "localhost" in path or "test.terento.app" in path:
        raise ValueError(f"invalid canonical path: {path}")
    return f"{BASE_URL}{path}"


def organization() -> dict:
    return {
        "@type": "Organization",
        "@id": ORGANIZATION_ID,
        "name": "Terento",
        "url": f"{BASE_URL}/",
        "logo": LOGO_URL,
        "sameAs": [REPOSITORY_URL],
    }


def application(
    source_application: dict,
    locale: str,
    url: str,
    release: dict,
) -> dict:
    required_source_fields = (
        "applicationCategory",
        "operatingSystem",
        "softwareRequirements",
        "description",
    )
    missing = [field for field in required_source_fields if not source_application.get(field)]
    if missing:
        raise ValueError(f"{locale}: missing localized application fields: {', '.join(missing)}")
    app = {
        "@type": "SoftwareApplication",
        "@id": SOFTWARE_ID,
        "name": "Terento",
        "url": url,
        "applicationCategory": source_application["applicationCategory"],
        "operatingSystem": source_application["operatingSystem"],
        "downloadUrl": release["downloadURL"],
        "releaseNotes": release["releaseNotesURL"],
        "offers": {"@type": "Offer", "price": "0", "priceCurrency": "EUR"},
        "inLanguage": locale,
        "publisher": {"@id": ORGANIZATION_ID},
    }
    source_order = list(source_application)
    description_before_version = source_order.index("description") < source_order.index("softwareVersion")
    if description_before_version:
        app["description"] = source_application["description"]
    app["softwareVersion"] = release["releaseLabel"]
    app["softwareRequirements"] = source_application["softwareRequirements"]
    if not description_before_version:
        app["description"] = source_application["description"]
    return {
        key: app[key]
        for key in (
            "@type",
            "@id",
            "name",
            "url",
            "applicationCategory",
            "operatingSystem",
            "description" if description_before_version else "softwareVersion",
            "softwareVersion" if description_before_version else "softwareRequirements",
            "softwareRequirements" if description_before_version else "description",
            "downloadUrl",
            "releaseNotes",
            "offers",
            "inLanguage",
            "publisher",
        )
    }


def faq_page(entries: list[dict[str, str]], locale: str, url: str) -> dict:
    return {
        "@type": "FAQPage",
        "@id": f"{url}#faq",
        "url": f"{url}#faq",
        "inLanguage": locale,
        "mainEntity": [
            {
                "@type": "Question",
                "name": entry["question"],
                "acceptedAnswer": {"@type": "Answer", "text": entry["answer"]},
            }
            for entry in entries
        ],
    }


def rendered_block(data: dict, indent: str) -> str:
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    return (
        f'{indent}<script type="application/ld+json">\n'
        f"{textwrap.indent(payload, indent + '  ')}\n"
        f"{indent}</script>"
    )


def replace_json_ld(source: str, data: dict, path: Path) -> str:
    match = JSON_LD_RE.search(source)
    if not match:
        raise ValueError(f"{path}: missing JSON-LD block")
    return source[: match.start()] + rendered_block(data, match.group("indent")) + source[match.end() :]


def page_groups(config: dict) -> tuple[dict[str, dict], dict[str, dict]]:
    homes: dict[str, dict] = {}
    downloads: dict[str, dict] = {}
    for page in config["pages"]:
        path = page["path"]
        if path == "/" or path == f'/{page["locale"]}/':
            homes[page["locale"]] = page
        elif path.rstrip("/").endswith("/download"):
            downloads[page["locale"]] = page
    if set(homes) != set(downloads):
        raise ValueError("home and download locale sets differ")
    return homes, downloads


def build_pages() -> list[tuple[Path, str]]:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    release = json.loads(RELEASE_PATH.read_text(encoding="utf-8"))
    for field in ("releaseLabel", "downloadURL", "releaseNotesURL"):
        if not release.get(field):
            raise ValueError(f"release metadata is missing {field}")
    homes, downloads = page_groups(config)

    download_data: dict[str, dict] = {}
    for locale, page in downloads.items():
        path = ROOT / page["file"]
        download_data[locale] = entity(json_ld(path.read_text(encoding="utf-8"), path), "SoftwareApplication", path)

    rendered: list[tuple[Path, str]] = []
    for locale, page in homes.items():
        path = ROOT / page["file"]
        source = path.read_text(encoding="utf-8")
        current_json_ld = json_ld(source, path)
        current_website = entity(current_json_ld, "WebSite", path)
        current_application = entity(current_json_ld, "SoftwareApplication", path)
        url = canonical_url(page)
        website = {
            "@type": "WebSite",
            "@id": f"{url}#website",
            "name": "Terento",
            "url": url,
            "inLanguage": locale,
            "description": current_website["description"],
            "publisher": {"@id": ORGANIZATION_ID},
        }
        graph = {
            "@context": "https://schema.org",
            "@graph": [
                organization(),
                application(current_application, locale, url, release),
                website,
                faq_page(visible_faq(source, path), locale, url),
            ],
        }
        rendered.append((path, replace_json_ld(source, graph, path)))

    for locale, page in downloads.items():
        path = ROOT / page["file"]
        source = path.read_text(encoding="utf-8")
        app_source = entity(json_ld(source, path), "SoftwareApplication", path)
        app = application(app_source, locale, canonical_url(page), release)
        rendered.append((path, replace_json_ld(source, {"@context": "https://schema.org", **app}, path)))
    return rendered


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true", help="rewrite public pages")
    mode.add_argument("--check", action="store_true", help="fail when pages need rewriting")
    args = parser.parse_args()
    try:
        rendered = build_pages()
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1

    changed = [path for path, output in rendered if output != path.read_text(encoding="utf-8")]
    if changed and not args.write:
        print("Structured-data drift detected; rerun with --write:")
        for path in changed:
            print(f"- {path.relative_to(ROOT)}")
        return 1
    if args.write:
        for path, output in rendered:
            if output != path.read_text(encoding="utf-8"):
                path.write_text(output, encoding="utf-8")
    print(f"Structured-data audit passed for {len(rendered)} localized pages.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
