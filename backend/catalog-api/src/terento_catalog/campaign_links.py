"""Pure campaign-link contract used by the private admin link builder.

The admin page performs generation locally in the browser.  Keeping the
destination and normalization rules here gives the contract a small,
dependency-free test surface without introducing persistence or an API
endpoint for campaign links.
"""

from __future__ import annotations

import re
import unicodedata
from typing import NamedTuple
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


DESTINATIONS = {
    "home": "https://terento.app/",
    "download": "https://terento.app/download/",
    "compatibility": "https://terento.app/compatibility/",
}

DESTINATION_OPTIONS = (
    ("home", "Home"),
    ("download", "Download"),
    ("compatibility", "Compatibility"),
)

SOURCE_OPTIONS = (
    ("reddit", "Reddit"),
    ("garmin_forum", "Garmin forum"),
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


class Channel(NamedTuple):
    """Where a link is shared, with its fixed ``utm_source`` and ``utm_medium``.

    ``other`` has no fixed pair: the operator types the source and picks a
    medium.  ``content_hint`` is the example shown for ``utm_content``.
    """

    key: str
    label: str
    source: str
    medium: str
    content_hint: str


CHANNELS = (
    Channel("reddit", "Reddit post", "reddit", "community", "Subreddit or thread, e.g. r_garmin"),
    Channel("garmin_forum", "Garmin forum", "garmin_forum", "community", "Forum section or thread, e.g. fenix_8"),
    Channel("github", "GitHub", "github", "referral", "Page or issue, e.g. readme"),
    Channel("discord", "Discord", "discord", "community", "Server or channel, e.g. garmin_hikers"),
    Channel("facebook", "Facebook group", "facebook", "social", "Group name, e.g. fenix_owners"),
    Channel("x", "X post", "x", "social", "Post or thread, e.g. launch_thread"),
    Channel("email", "Email", "email", "email", "Newsletter or message, e.g. october_update"),
    Channel("other", "Other", "", "", "Placement, e.g. blog_sidebar"),
)

CHANNEL_BY_KEY = {channel.key: channel for channel in CHANNELS}

# Default medium offered for the ``other`` channel.
OTHER_CHANNEL_DEFAULT_MEDIUM = "referral"

# The public site forwards a UTM value to Umami only when it matches
# ``^[A-Za-z0-9._~-]{1,80}$`` (site/privacy-consent.js); longer values are dropped.
MAX_VALUE_LENGTH = 80

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


def channel_source_medium(
    channel: str, *, custom_source: str = "", medium: str = "", custom_medium: str = "",
) -> tuple[str, str]:
    """Return the normalized ``(utm_source, utm_medium)`` pair for a channel.

    Fixed channels ignore the custom arguments, so one channel is always
    counted the same way.  ``other`` uses ``custom_source`` and ``medium``
    (``custom_medium`` when ``medium`` is ``other``).
    """

    entry = CHANNEL_BY_KEY.get(channel)
    if entry is None:
        raise ValueError("Unknown channel")
    if entry.key != "other":
        return entry.source, entry.medium
    medium_value = custom_medium if medium == "other" else medium
    return normalize_value(custom_source), normalize_value(medium_value)


def build_campaign_url(
    *,
    destination: str,
    campaign: str,
    channel: str = "",
    source: str = "",
    medium: str = "",
    content: str = "",
    term: str = "",
    custom_destination: str = "",
    custom_source: str = "",
    custom_medium: str = "",
) -> str:
    """Build a canonical campaign URL or raise ``ValueError`` when incomplete.

    With ``channel`` the source and medium come from :data:`CHANNELS`;
    without it ``source`` and ``medium`` are used directly (``other`` selects
    the matching custom value).
    """

    destination_url = _destination_url(destination, custom_destination)
    if channel:
        source_value, medium_value = channel_source_medium(
            channel, custom_source=custom_source, medium=medium, custom_medium=custom_medium,
        )
    else:
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
    if any(len(value) > MAX_VALUE_LENGTH for value in (source_value, medium_value, campaign_value, content_value, term_value)):
        raise ValueError(f"UTM values must be at most {MAX_VALUE_LENGTH} characters")
    if content_value:
        params.append(("utm_content", content_value))
    if term_value:
        params.append(("utm_term", term_value))
    return urlunsplit(("https", "terento.app", parsed.path or "/", urlencode(params), parsed.fragment))
