"""Small helpers for reading the shared Admin component kit in tests."""

from __future__ import annotations

import re


def metric_value(body: str, label: str) -> str | None:
    """Return the visible value text of the first metric tile with ``label``."""
    match = re.search(
        r"<span class='admin-metric-label'>" + re.escape(label)
        + r"(?:<a [^>]*>.*?</a>)?</span><strong class='admin-metric-value'[^>]*>"
        r"(?:<svg.*?</svg>)?(.*?)</strong>",
        body,
        re.S,
    )
    if not match:
        return None
    return re.sub(r"<[^>]+>", "", match.group(1)).replace("Unknown", "").replace("Unavailable", "").strip()


def metric_tone(body: str, label: str) -> str | None:
    match = re.search(
        r"<(?:div|a) class='admin-metric[^']*'[^>]*data-tone='(\w+)'[^>]*>"
        r"<span class='admin-metric-label'>" + re.escape(label),
        body,
    )
    return match.group(1) if match else None


def visible_text(markup: str) -> str:
    """Return the sighted-reader text of ``markup``: tags and ``sr-only`` spans removed."""
    markup = re.sub(r"<span class='sr-only'>[^<]*</span>", "", markup)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", markup)).strip()
