"""Bounded read-only GitHub release asset download collection."""
from __future__ import annotations

import json
import logging
import hashlib
import re
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
# Public pre-release labels are beta.N or release-candidate rc.N
# (VERSIONING.md); the trailing RC group keeps historical "beta.N RC" names.
_RELEASE_PATTERN = re.compile(r"\b((?:beta|rc)\.\d+)(?:\s*[-·( ]\s*(RC))?\b", re.IGNORECASE)
_BUILD_PATTERN = re.compile(r"\bbuild\s*(\d+)\b", re.IGNORECASE)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def release_download_totals(releases: list[Any]) -> dict[str, Any]:
    """Aggregate assets and return authoritative release identities for retention."""
    dmg_total = 0
    zip_total = 0
    release_count = 0
    asset_keys: list[str] = []
    release_markers: list[dict[str, Any]] = []
    for release in releases:
        if not isinstance(release, dict):
            raise ValueError("Unexpected GitHub release response")
        if release.get("draft") is True:
            continue
        release_count += 1
        release_id = release.get("id")
        if isinstance(release_id, bool) or release_id is None:
            release_id = None
        elif not isinstance(release_id, (int, str)):
            raise ValueError("Unexpected GitHub release identity")
        tag = release.get("tag_name")
        if tag is not None and not isinstance(tag, str):
            raise ValueError("Unexpected GitHub release tag")
        name = release.get("name")
        if name is not None and not isinstance(name, str):
            raise ValueError("Unexpected GitHub release name")
        published_at = release.get("published_at")
        if published_at is not None and not isinstance(published_at, str):
            raise ValueError("Unexpected GitHub release publication time")
        parsed_published_at = None
        if published_at:
            try:
                parsed_published_at = datetime.fromisoformat(
                    published_at.replace("Z", "+00:00")
                )
            except ValueError:
                parsed_published_at = None
        if (
            (release_id or tag)
            and parsed_published_at is not None
            and parsed_published_at.tzinfo is not None
        ):
            # GitHub's human release name may omit a build that remains
            # authoritative in the tag (for example beta.15-build36).
            source_label = " ".join(
                value.strip() for value in (name, tag) if value and value.strip()
            )
            beta = _RELEASE_PATTERN.search(source_label)
            build = _BUILD_PATTERN.search(source_label)
            if beta:
                label = beta.group(1).lower() + (" RC" if beta.group(2) else "")
                if build:
                    label += f" · build {build.group(1)}"
            else:
                label = source_label.strip() or str(release_id or tag)
            release_markers.append({
                "id": str(release_id) if release_id else None,
                "tag": tag.strip() if tag and tag.strip() else None,
                "label": label,
                "published_at": parsed_published_at.astimezone(timezone.utc).isoformat(),
            })
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
                asset_keys.append(f"{release_id or tag or ''}:dmg:{name.casefold()}")
            elif normalized_name.endswith(".zip"):
                zip_total += count
                asset_keys.append(f"{release_id or tag or ''}:zip:{name.casefold()}")
    population_fingerprint = hashlib.sha256(
        "\n".join(sorted(asset_keys)).encode("utf-8")
    ).hexdigest()
    return {
        "dmg_total": dmg_total,
        "zip_total": zip_total,
        "release_count": release_count,
        "asset_count": len(asset_keys),
        "population_fingerprint": population_fingerprint,
        "release_markers": release_markers,
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


def fetch_github_download_totals(*, opener: Any | None = None) -> dict[str, Any]:
    """Read every public release page and return current cumulative totals."""
    opener = opener or build_opener(NoRedirect())
    totals = {
        "dmg_total": 0, "zip_total": 0, "release_count": 0,
        "asset_count": 0, "population_fingerprint": None,
        "release_markers": [],
    }
    population_parts: list[str] = []
    for page in range(1, MAX_PAGES + 1):
        releases = _fetch_page(opener, page)
        page_totals = release_download_totals(releases)
        for key in totals:
            if key in {"population_fingerprint", "release_markers"}:
                continue
            totals[key] += page_totals[key]
        totals["release_markers"].extend(page_totals["release_markers"])
        population_parts.append(page_totals["population_fingerprint"])
        if len(releases) < PAGE_SIZE:
            totals["population_fingerprint"] = hashlib.sha256(
                "\n".join(population_parts).encode("utf-8")
            ).hexdigest()
            return totals
    raise ValueError("GitHub releases pagination exceeds limit")


def collect_once(
    database: Any,
    *,
    now: datetime | None = None,
    fetch=fetch_github_download_totals,
) -> dict[str, Any]:
    """Fetch one snapshot and retain authoritative releases plus counters."""
    totals = fetch()
    observed_at = now or datetime.now(timezone.utc)
    if observed_at.tzinfo is None:
        observed_at = observed_at.replace(tzinfo=timezone.utc)
    database.record_github_release_markers(totals.get("release_markers") or [])
    stored = database.record_github_download_snapshot(
        dmg_total=totals["dmg_total"],
        zip_total=totals["zip_total"],
        release_count=totals["release_count"],
        asset_count=totals.get("asset_count"),
        population_fingerprint=totals.get("population_fingerprint"),
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
