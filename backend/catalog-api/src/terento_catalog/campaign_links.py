"""Pure campaign-link contract used by the private admin link builder.

The admin page performs generation locally in the browser.  Keeping the
destination and normalization rules here gives the contract a small,
dependency-free test surface without introducing persistence or an API
endpoint for campaign links.
"""

from __future__ import annotations

import re
import unicodedata
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


DESTINATIONS = {
    "home": "https://terento.app/",
    "download": "https://terento.app/download/",
    "compatibility": "https://terento.app/compatibility/",
}

SOURCE_OPTIONS = (
    ("reddit", "Reddit"),
    ("github", "GitHub"),
    ("discord", "Discord"),
    ("facebook", "Facebook"),
    ("x", "X"),
    ("linkedin", "LinkedIn"),
    ("email", "Email"),
    ("other", "Other"),
)

MEDIUM_OPTIONS = (
    ("social", "Social"),
    ("community", "Community"),
    ("email", "Email"),
    ("referral", "Referral"),
    ("paid_social", "Paid social"),
    ("other", "Other"),
)

CAMPAIGN_SUGGESTIONS = ("early_beta", "launch", "compatibility", "community")

UTM_KEYS = {"utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term"}


def normalize_value(value: str | None) -> str:
    """Return the canonical, URL-safe value used for a UTM component."""

    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(character for character in text if not unicodedata.combining(character))
    text = text.strip().lower()
    text = re.sub(r"\s+", "_", text)
    # Keep the two documented separators, remove other punctuation, and
    # preserve valid values such as ``garmin-forum-de`` unchanged.
    text = re.sub(r"[^a-z0-9_-]", "", text)
    text = re.sub(r"[-_]{2,}", lambda match: match.group(0)[0], text)
    return text.strip("-_")


def _destination_url(destination: str, custom_destination: str | None = None) -> str:
    if destination in DESTINATIONS:
        return DESTINATIONS[destination]
    if destination != "other":
        raise ValueError("Unknown destination")
    value = str(custom_destination or "").strip()
    if not value:
        raise ValueError("A custom Terento destination is required")
    if value.startswith("/"):
        return "https://terento.app" + value
    parsed = urlsplit(value)
    if parsed.scheme != "https" or parsed.hostname != "terento.app" or parsed.username or parsed.password:
        raise ValueError("Custom destinations must use https://terento.app")
    if parsed.port not in (None, 443):
        raise ValueError("Custom destinations must use https://terento.app")
    return urlunsplit(("https", "terento.app", parsed.path or "/", parsed.query, parsed.fragment))


def build_campaign_url(
    *,
    destination: str,
    source: str,
    medium: str,
    campaign: str,
    content: str = "",
    term: str = "",
    custom_destination: str = "",
    custom_source: str = "",
    custom_medium: str = "",
) -> str:
    """Build a canonical campaign URL or raise ``ValueError`` when incomplete."""

    destination_url = _destination_url(destination, custom_destination)
    source_value = normalize_value(custom_source if source == "other" else source)
    medium_value = normalize_value(custom_medium if medium == "other" else medium)
    campaign_value = normalize_value(campaign)
    if not source_value or not medium_value or not campaign_value:
        raise ValueError("Source, medium, and campaign are required")

    parsed = urlsplit(destination_url)
    existing = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() not in UTM_KEYS
    ]
    params = existing + [("utm_source", source_value), ("utm_medium", medium_value), ("utm_campaign", campaign_value)]
    content_value = normalize_value(content)
    term_value = normalize_value(term)
    if content_value:
        params.append(("utm_content", content_value))
    if term_value:
        params.append(("utm_term", term_value))
    return urlunsplit(("https", "terento.app", parsed.path or "/", urlencode(params), parsed.fragment))
