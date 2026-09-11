"""Bounded read-only GitHub release asset download collection."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

LOGGER = logging.getLogger(__name__)
REPOSITORY_RELEASES = "https://api.github.com/repos/VooZ2/terento/releases"
PAGE_SIZE = 100
MAX_PAGES = 100
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
REQUEST_TIMEOUT_SECONDS = 10


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def release_download_totals(releases: list[Any]) -> dict[str, int]:
    """Aggregate public release assets, keeping only DMG and ZIP downloads."""
    dmg_total = 0
    zip_total = 0
    release_count = 0
    for release in releases:
        if not isinstance(release, dict):
            raise ValueError("Unexpected GitHub release response")
        if release.get("draft") is True:
            continue
        release_count += 1
        assets = release.get("assets")
        if not isinstance(assets, list):
            raise ValueError("Unexpected GitHub release assets")
        for asset in assets:
            if not isinstance(asset, dict):
                raise ValueError("Unexpected GitHub release asset")
            name = asset.get("name")
            count = asset.get("download_count")
            if not isinstance(name, str) or not isinstance(count, int) or isinstance(count, bool) or count < 0:
                raise ValueError("Unexpected GitHub release download count")
            normalized_name = name.casefold()
            if normalized_name.endswith(".dmg"):
                dmg_total += count
            elif normalized_name.endswith(".zip"):
                zip_total += count
    return {
        "dmg_total": dmg_total,
        "zip_total": zip_total,
        "release_count": release_count,
    }


def _fetch_page(opener: Any, page: int) -> list[Any]:
    query = urlencode({"per_page": PAGE_SIZE, "page": page})
    request = Request(
        f"{REPOSITORY_RELEASES}?{query}",
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "Terento-GitHub-download-collector",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with opener.open(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        body = response.read(MAX_RESPONSE_BYTES + 1)
    if len(body) > MAX_RESPONSE_BYTES:
        raise ValueError("GitHub response exceeds limit")
    document = json.loads(body)
    if not isinstance(document, list):
        raise ValueError("Unexpected GitHub releases response")
    return document


def fetch_github_download_totals(*, opener: Any | None = None) -> dict[str, int]:
    """Read every public release page and return current cumulative totals."""
    opener = opener or build_opener(NoRedirect())
    totals = {"dmg_total": 0, "zip_total": 0, "release_count": 0}
    for page in range(1, MAX_PAGES + 1):
        releases = _fetch_page(opener, page)
        page_totals = release_download_totals(releases)
        for key in totals:
            totals[key] += page_totals[key]
        if len(releases) < PAGE_SIZE:
            return totals
    raise ValueError("GitHub releases pagination exceeds limit")


def collect_once(
    database: Any,
    *,
    now: datetime | None = None,
    fetch=fetch_github_download_totals,
) -> dict[str, Any]:
    """Fetch one snapshot and persist it without storing release metadata."""
    totals = fetch()
    observed_at = now or datetime.now(timezone.utc)
    if observed_at.tzinfo is None:
        observed_at = observed_at.replace(tzinfo=timezone.utc)
    stored = database.record_github_download_snapshot(
        dmg_total=totals["dmg_total"],
        zip_total=totals["zip_total"],
        release_count=totals["release_count"],
        observed_at=observed_at,
    )
    return {**totals, "observed_at": observed_at, "stored": bool(stored)}


def main() -> None:
    from .config import Settings
    from .db import Database

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = Settings.from_env()
    result = collect_once(
        Database(
            settings.database_url,
            connect_timeout_seconds=settings.database_connect_timeout_seconds,
        )
    )
    LOGGER.info(
        "GitHub download snapshot: %s DMG, %s ZIP, %s releases",
        result["dmg_total"], result["zip_total"], result["release_count"],
    )


if __name__ == "__main__":
    main()
