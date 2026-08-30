#!/usr/bin/env python3
"""Validate structured data emitted by the public static site.

The validator is intentionally structural: it parses every JSON-LD block and
walks objects, arrays, @graph values, and nested entities before applying the
site-wide BreadcrumbList contract.
"""

from __future__ import annotations

import argparse
import html.parser
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SITE_ROOT = ROOT / "site"
BASE_URL = "https://terento.app"
BASE_HOST = "terento.app"
SUPPORTED_LOCALES = {"de", "fr", "pl", "cs", "it"}
INTENTIONAL_REDIRECT_URLS: set[str] = set()
PLACEHOLDERS = {"", "n/a", "na", "none", "null", "placeholder", "todo"}


class HtmlPageParser(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.canonical: str | None = None
        self.jsonld_blocks: list[str] = []
        self._jsonld_buffer: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {name.lower(): value for name, value in attrs}
        if tag.lower() == "link":
            rel = {part.lower() for part in (attributes.get("rel") or "").split()}
            if "canonical" in rel and attributes.get("href"):
                self.canonical = attributes["href"]
        if tag.lower() == "script" and (attributes.get("type") or "").lower() == "application/ld+json":
            self._jsonld_buffer = []

    def handle_data(self, data: str) -> None:
        if self._jsonld_buffer is not None:
            self._jsonld_buffer.append(data)

    def handle_entityref(self, name: str) -> None:
        if self._jsonld_buffer is not None:
            self._jsonld_buffer.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        if self._jsonld_buffer is not None:
            self._jsonld_buffer.append(f"&#{name};")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "script" and self._jsonld_buffer is not None:
            self.jsonld_blocks.append("".join(self._jsonld_buffer))
            self._jsonld_buffer = None


@dataclass(frozen=True)
class Page:
    source: Path
    relative_source: str
    canonical: str | None
    jsonld_blocks: tuple[str, ...]


def parse_page(source: Path, site_root: Path) -> Page:
    parser = HtmlPageParser()
    parser.feed(source.read_text(encoding="utf-8"))
    return Page(
        source=source,
        relative_source=source.relative_to(ROOT).as_posix() if source.is_relative_to(ROOT) else source.relative_to(site_root).as_posix(),
        canonical=parser.canonical,
        jsonld_blocks=tuple(parser.jsonld_blocks),
    )


def entity_type(entity: dict[str, object]) -> str | None:
    value = entity.get("@type")
    if isinstance(value, str):
        return value
    if isinstance(value, list) and "BreadcrumbList" in value:
        return "BreadcrumbList"
    return None


def breadcrumb_entities(value: object):
    if isinstance(value, dict):
        if entity_type(value) == "BreadcrumbList":
            yield value
        for child in value.values():
            yield from breadcrumb_entities(child)
    elif isinstance(value, list):
        for child in value:
            yield from breadcrumb_entities(child)


def entity_id(entity: dict[str, object]) -> str:
    value = entity.get("@id")
    return value if isinstance(value, str) and value else "<missing>"


def fail(page: Page, entity: dict[str, object], position: object, rule: str, detail: str) -> str:
    if isinstance(position, int) and not isinstance(position, bool):
        position_text = str(position)
    elif position is None:
        position_text = "<unknown>"
    else:
        position_text = str(position)
    return (
        f"source={page.relative_source}; page_canonical={page.canonical or '<missing>'}; "
        f"entity_id={entity_id(entity)}; item_position={position_text}; rule={rule}; detail={detail}"
    )


def is_placeholder(value: object) -> bool:
    return isinstance(value, str) and value.strip().lower() in PLACEHOLDERS


def validate_url(item: object, page: Page, entity: dict[str, object], position: object, known_pages: set[str]) -> str | None:
    if not isinstance(item, str) or is_placeholder(item):
        return fail(page, entity, position, "item is non-empty and not a placeholder", "item is empty or placeholder")
    parsed = urlsplit(item)
    if parsed.scheme != "https" or not parsed.netloc or parsed.hostname is None:
        return fail(page, entity, position, "item is an absolute HTTPS URL", f"invalid URL {item!r}")
    if parsed.query:
        return fail(page, entity, position, "item URL has no query string", f"query found in {item!r}")
    if parsed.fragment:
        return fail(page, entity, position, "item URL has no fragment", f"fragment found in {item!r}")
    if item in INTENTIONAL_REDIRECT_URLS:
        return fail(page, entity, position, "item URL is not an intentional redirect", f"redirect URL {item!r}")
    if parsed.hostname.lower() == BASE_HOST:
        if item not in known_pages:
            path = parsed.path.rstrip("/") or "/"
            if path == "/guides" or re.fullmatch(r"/(?:de|fr|pl|cs|it)/guides", path):
                return fail(page, entity, position, "item URL does not use a phantom parent route", f"parent route {item!r} is not a page")
            return fail(page, entity, position, "internal item URL resolves to a generated page", f"unknown internal route {item!r}")
    return None


def validate_breadcrumb(page: Page, entity: dict[str, object], known_pages: set[str]) -> list[str]:
    errors: list[str] = []
    entries = entity.get("itemListElement")
    if not isinstance(entries, list):
        return [fail(page, entity, None, "itemListElement is a list", "missing or non-list itemListElement")]
    if len(entries) < 2:
        errors.append(fail(page, entity, None, "BreadcrumbList has at least two items", f"found {len(entries)} item(s)"))

    positions: list[int] = []
    items: list[str] = []
    for index, entry in enumerate(entries, 1):
        if not isinstance(entry, dict):
            errors.append(fail(page, entity, index, "each breadcrumb entry is an object", "ListItem is not an object"))
            continue
        position = entry.get("position")
        if not isinstance(position, int) or isinstance(position, bool):
            errors.append(fail(page, entity, position, "ListItem.position is an integer", "position is missing or not an integer"))
        else:
            positions.append(position)
            if position != index:
                errors.append(fail(page, entity, position, "ListItem positions are contiguous starting at 1", f"expected {index}"))
        if entry.get("@type") != "ListItem":
            errors.append(fail(page, entity, position, "each breadcrumb entry has @type ListItem", "wrong or missing @type"))
        name = entry.get("name")
        if not isinstance(name, str) or not name.strip() or is_placeholder(name):
            errors.append(fail(page, entity, position, "ListItem.name is localized and non-empty", "missing, empty, or placeholder name"))
        item = entry.get("item")
        url_error = validate_url(item, page, entity, position, known_pages)
        if url_error:
            errors.append(url_error)
        elif isinstance(item, str):
            items.append(item)
            if item in items[:-1]:
                errors.append(fail(page, entity, position, "breadcrumb item URLs are unique", f"duplicate URL {item!r}"))
            if page.canonical and item == page.canonical and index != len(entries):
                errors.append(fail(page, entity, position, "final breadcrumb item is the page canonical", "page canonical appears before the final item"))

    if positions and len(set(positions)) != len(positions):
        errors.append(fail(page, entity, None, "ListItem positions are unique", f"duplicate positions {positions}"))
    if page.canonical and items:
        if items[-1] != page.canonical:
            errors.append(fail(page, entity, len(entries), "final breadcrumb item is the page canonical", f"expected {page.canonical!r}, found {items[-1]!r}"))
    return errors


def main() -> int:
    argument_parser = argparse.ArgumentParser(description=__doc__)
    argument_parser.add_argument("--site-root", type=Path, default=DEFAULT_SITE_ROOT)
    arguments = argument_parser.parse_args()
    site_root = arguments.site_root.resolve()
    pages = [parse_page(source, site_root) for source in sorted(site_root.rglob("*.html"))]
    known_pages = {page.canonical for page in pages if page.canonical}
    errors: list[str] = []
    jsonld_count = 0
    breadcrumb_count = 0

    for page in pages:
        for block_index, block in enumerate(page.jsonld_blocks, 1):
            jsonld_count += 1
            try:
                data = json.loads(block)
            except json.JSONDecodeError as error:
                errors.append(
                    f"source={page.relative_source}; page_canonical={page.canonical or '<missing>'}; "
                    f"entity_id=<jsonld-block-{block_index}>; item_position=<unknown>; "
                    f"rule=every JSON-LD block is valid JSON; detail={error.msg} at line {error.lineno}, column {error.colno}"
                )
                continue
            for entity in breadcrumb_entities(data):
                breadcrumb_count += 1
                errors.extend(validate_breadcrumb(page, entity, known_pages))

    if errors:
        print(f"Structured-data validation failed with {len(errors)} error(s):", file=sys.stderr)
        for error in errors:
            print(error, file=sys.stderr)
        return 1

    print(
        f"Structured-data validation passed: {len(pages)} HTML pages, "
        f"{jsonld_count} JSON-LD blocks, {breadcrumb_count} BreadcrumbList entities."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
