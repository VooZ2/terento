"""JSON-LD for the public pages that have no richer entity of their own.

About, Compatibility and Map styles describe themselves as a web page with a
breadcrumb back to the localized home page and the canonical publisher. The
page builders call `json_ld_block` so the block is part of every regeneration;
nothing here states support, ratings or counts.
"""

from __future__ import annotations

import html
import json
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE_URL = "https://terento.app"
ORGANIZATION_ID = f"{BASE_URL}/#organization"
HOME_LABELS = {
    "en": "Home",
    "de": "Startseite",
    "fr": "Accueil",
    "pl": "Strona główna",
    "cs": "Domů",
    "it": "Home",
}


def localized_path(locale: str, suffix: str = "") -> str:
    return "/" + ("" if locale == "en" else f"{locale}/") + suffix


def organization() -> dict:
    return {
        "@type": "Organization",
        "@id": ORGANIZATION_ID,
        "name": "Terento",
        "url": f"{BASE_URL}/",
        "logo": f"{BASE_URL}/assets/logo-sky.svg",
        "sameAs": ["https://github.com/VooZ2/terento"],
    }


def metadata_page(locale: str, slug: str) -> dict:
    """The page's entry in site/metadata.json, the one SEO source."""
    path = localized_path(locale, slug)
    config = json.loads((ROOT / "site/metadata.json").read_text(encoding="utf-8"))
    for page in config["pages"]:
        if page["path"] == path:
            return page
    raise ValueError(f"site/metadata.json has no page {path}")


def page_graph(locale: str, slug: str, page_type: str) -> dict:
    url = f"{BASE_URL}{localized_path(locale, slug)}"
    page = metadata_page(locale, slug)
    description = page["description"]
    # The page title without the site suffix, e.g. "About Terento".
    name = page["title"].rsplit(" — Terento", 1)[0].split(" — ")[0]
    return {
        "@context": "https://schema.org",
        "@graph": [
            organization(),
            {
                "@type": page_type,
                "@id": f"{url}#webpage",
                "url": url,
                "name": html.unescape(name),
                "description": html.unescape(description),
                "inLanguage": locale,
                "isPartOf": {"@id": f"{BASE_URL}{localized_path(locale)}#website"},
                "publisher": {"@id": ORGANIZATION_ID},
                "breadcrumb": {"@id": f"{url}#breadcrumb"},
            },
            {
                "@type": "BreadcrumbList",
                "@id": f"{url}#breadcrumb",
                "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": HOME_LABELS[locale], "item": f"{BASE_URL}{localized_path(locale)}"},
                    {"@type": "ListItem", "position": 2, "name": html.unescape(name), "item": url},
                ],
            },
        ],
    }


def json_ld_block(locale: str, slug: str, page_type: str, indent: str = "    ") -> str:
    payload = json.dumps(page_graph(locale, slug, page_type), ensure_ascii=False, indent=2)
    payload = payload.replace("</", "<\\/")
    return f'{indent}<script type="application/ld+json">\n{textwrap.indent(payload, indent + "  ")}\n{indent}</script>'
