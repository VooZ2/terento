#!/usr/bin/env python3
"""Render and audit Terento's static public-page metadata from one config."""

from __future__ import annotations

import argparse
import html
import json
import re
import struct
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "site" / "metadata.json"
TAG_RE = re.compile(r"<(?:title\b[^>]*>.*?</title>|meta\b[^>]*>|link\b[^>]*>)", re.IGNORECASE | re.DOTALL)
ATTR_RE = re.compile(r"([a-zA-Z_:][-a-zA-Z0-9_:]*)\s*=\s*([\"'])(.*?)\2", re.IGNORECASE | re.DOTALL)


def attributes(tag: str) -> dict[str, str]:
    return {name.lower(): value for name, _, value in ATTR_RE.findall(tag)}


def metadata_tag(tag: str) -> bool:
    lowered = tag.lower()
    if lowered.startswith("<title"):
        return True
    if lowered.startswith("<meta"):
        attrs = attributes(tag)
        name = attrs.get("name", "").lower()
        prop = attrs.get("property", "").lower()
        return name in {"description", "robots"} or name.startswith("twitter:") or prop.startswith("og:")
    if lowered.startswith("<link"):
        attrs = attributes(tag)
        rel = {part.lower() for part in attrs.get("rel", "").split()}
        return "canonical" in rel or ("alternate" in rel and "hreflang" in attrs)
    return False


def esc(value: str) -> str:
    return html.escape(value, quote=True)


def page_metadata_block(config: dict, page: dict) -> str:
    base = config["baseUrl"].rstrip("/")
    canonical = f"{base}{page['path']}"
    image = f"{base}{config['socialImage']}"
    locale = config["locales"][page["locale"]]
    lines = [
        f'    <meta name="description" content="{esc(page["description"])}">',
        '    <meta name="robots" content="index,follow">',
        f'    <link rel="canonical" href="{esc(canonical)}">',
    ]
    if page.get("alternates"):
        group = "download" if page["path"].rstrip("/").endswith("/download") else "home"

        def in_group(candidate: dict) -> bool:
            candidate_group = "download" if candidate["path"].rstrip("/").endswith("/download") else "home"
            return candidate_group == group

        for language in config["alternateLanguages"]:
            localized = next(item for item in config["pages"] if in_group(item) and item["locale"] == language)
            lines.append(f'    <link rel="alternate" hreflang="{language}" href="{base}{localized["path"]}">')
        default = next(item for item in config["pages"] if in_group(item) and item["locale"] == "en")
        lines.append(f'    <link rel="alternate" hreflang="x-default" href="{base}{default["path"]}">')
    lines.extend(
        [
            '    <meta property="og:type" content="website">',
            f'    <meta property="og:site_name" content="{esc(config["siteName"])}">',
            f'    <meta property="og:title" content="{esc(page["title"])}">',
            f'    <meta property="og:description" content="{esc(page["description"])}">',
            f'    <meta property="og:url" content="{esc(canonical)}">',
            f'    <meta property="og:image" content="{esc(image)}">',
            f'    <meta property="og:image:type" content="{esc(config["socialImageType"])}">',
            f'    <meta property="og:image:width" content="{config["socialImageWidth"]}">',
            f'    <meta property="og:image:height" content="{config["socialImageHeight"]}">',
            f'    <meta property="og:image:alt" content="{esc(config["socialImageAlt"])}">',
            f'    <meta property="og:locale" content="{locale}">',
            '    <meta name="twitter:card" content="summary_large_image">',
            f'    <meta name="twitter:title" content="{esc(page["title"])}">',
            f'    <meta name="twitter:description" content="{esc(page["description"])}">',
            f'    <meta name="twitter:image" content="{esc(image)}">',
            f'    <title>{esc(page["title"])}</title>',
        ]
    )
    return "\n".join(lines)


def render(source: str, config: dict, page: dict) -> str:
    head_match = re.search(r"<head\b[^>]*>(?P<head>.*?)</head>", source, re.IGNORECASE | re.DOTALL)
    if not head_match:
        raise ValueError(f"{page['file']} has no head element")
    head = head_match.group("head")
    head = TAG_RE.sub(lambda match: "" if metadata_tag(match.group(0)) else match.group(0), head)
    head = re.sub(r"(?:[ \t]*\n){3,}", "\n\n", head)
    head = re.sub(r"[ \t]+$", "", head, flags=re.MULTILINE)
    theme_match = re.search(r"<meta\s+name=[\"']theme-color[\"'][^>]*>", head, re.IGNORECASE)
    if not theme_match:
        raise ValueError(f"{page['file']} has no theme-color meta tag")
    insertion = "\n" + page_metadata_block(config, page) + "\n"
    head = head[: theme_match.end()] + insertion + head[theme_match.end() :]
    return source[: head_match.start("head")] + head + source[head_match.end("head") :]


def png_dimensions(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        raise ValueError(f"{path} is not a valid PNG")
    return struct.unpack(">II", data[16:24])


def meta_content(source: str, selector: str) -> list[str]:
    pattern = rf'<meta\s+{selector}\s+content="([^"]*)"'
    return re.findall(pattern, source, re.IGNORECASE)


def validate_rendered(config: dict) -> list[str]:
    errors: list[str] = []
    image_path = ROOT / "site" / config["socialImage"].lstrip("/")
    try:
        dimensions = png_dimensions(image_path)
    except (OSError, ValueError) as error:
        errors.append(str(error))
        dimensions = None
    expected_dimensions = (config["socialImageWidth"], config["socialImageHeight"])
    if dimensions != expected_dimensions:
        errors.append(f"social image dimensions {dimensions} != {expected_dimensions}")

    for page in config["pages"]:
        path = ROOT / page["file"]
        source = path.read_text(encoding="utf-8")
        title_match = re.search(r"<title>(.*?)</title>", source, re.IGNORECASE | re.DOTALL)
        desc_match = re.search(r'<meta\s+name="description"\s+content="(.*?)">', source, re.IGNORECASE | re.DOTALL)
        if not title_match or title_match.group(1) != page["title"]:
            errors.append(f"{page['path']}: title mismatch")
        if len(page["title"]) >= 60:
            errors.append(f"{page['path']}: title is not comfortably below 60 characters")
        if "|" in page["title"]:
            errors.append(f"{page['path']}: title uses a pipe separator")
        if not desc_match or html.unescape(desc_match.group(1)) != page["description"]:
            errors.append(f"{page['path']}: description mismatch")
        if len(re.findall(r"<title\b", source, re.IGNORECASE)) != 1:
            errors.append(f"{page['path']}: expected exactly one title")
        for pattern, label in [
            (r'<meta\s+property="og:title"', "og:title"),
            (r'<meta\s+name="twitter:title"', "twitter:title"),
            (r'<link\s+rel="canonical"', "canonical"),
            (r'<meta\s+property="og:image"', "og:image"),
        ]:
            if len(re.findall(pattern, source, re.IGNORECASE)) != 1:
                errors.append(f"{page['path']}: expected one {label}")
        if f'content="{page["title"]}"' not in source:
            errors.append(f"{page['path']}: title is not shared by social metadata")
        og_titles = meta_content(source, r'property="og:title"')
        twitter_titles = meta_content(source, r'name="twitter:title"')
        if og_titles != [page["title"]] or twitter_titles != [page["title"]]:
            errors.append(f"{page['path']}: title, og:title, and twitter:title are not identical")
        image_url = f'{config["baseUrl"]}{config["socialImage"]}'
        if source.count(image_url) != 2:
            errors.append(f"{page['path']}: expected og:image and twitter:image to share social URL")
        if meta_content(source, r'property="og:image:width"') != [str(config["socialImageWidth"])] or meta_content(source, r'property="og:image:height"') != [str(config["socialImageHeight"])] :
            errors.append(f"{page['path']}: social image dimensions metadata mismatch")
        if f'href="{config["baseUrl"]}{page["path"]}"' not in source:
            errors.append(f"{page['path']}: canonical URL mismatch")
    return errors


def print_report(config: dict) -> None:
    image = f'{config["baseUrl"]}{config["socialImage"]}'
    dimensions = png_dimensions(ROOT / "site" / config["socialImage"].lstrip("/"))
    print("Page | Locale | Title | Title length | Description length | Canonical | OG image | Dimensions | Status")
    print("--- | --- | --- | ---: | ---: | --- | --- | --- | ---")
    for page in config["pages"]:
        print(
            f"{page['path']} | {page['locale']} | {page['title']} | {len(page['title'])} | "
            f"{len(page['description'])} | {config['baseUrl']}{page['path']} | {image} | "
            f"{dimensions[0]}×{dimensions[1]} | PASS"
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true", help="rewrite static pages from metadata.json")
    mode.add_argument("--check", action="store_true", help="fail if rendered pages drift from metadata.json")
    parser.add_argument("--report", action="store_true", help="print the audited metadata table")
    args = parser.parse_args()
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    changed = []
    for page in config["pages"]:
        path = ROOT / page["file"]
        source = path.read_text(encoding="utf-8")
        rendered = render(source, config, page)
        if rendered != source:
            changed.append(path)
            if args.write:
                path.write_text(rendered, encoding="utf-8")
    if changed and not args.write:
        print("Metadata drift detected; rerun with --write:")
        for path in changed:
            print(f"- {path.relative_to(ROOT)}")
        return 1
    errors = validate_rendered(config)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    if args.report:
        print_report(config)
    print(f"Metadata audit passed for {len(config['pages'])} indexable pages.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
