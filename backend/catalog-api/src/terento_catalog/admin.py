from __future__ import annotations

import base64
import hashlib
import hmac
import html
import json
from .admin_revisions import active_trend_buckets, section_revisions, statistics_revisions

import math
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote, urlencode, urlsplit
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .campaign_links import (
    CAMPAIGN_SUGGESTIONS,
    CHANNELS,
    DESTINATION_OPTIONS,
    DESTINATIONS,
    MAX_VALUE_LENGTH,
    MEDIUM_OPTIONS,
    OTHER_CHANNEL_DEFAULT_MEDIUM,
    SOURCE_OPTIONS,
    build_campaign_url,
)
from .asset_attribution import generic_fallback_image
from .admin_brand_tokens_generated import ADMIN_BRAND_TOKENS_CSS
from .compatibility_status import (
    CANONICAL_STATUS_ORDER,
    STATUS_PUBLIC_COPY,
    CompatibilityStatus,
    calculate_compatibility_status,
)
from .device_catalog import _official_source_image_url
from .models import RETAIL_RETIREMENT_MISSED_RUNS
from .failure_reasons import failure_reason_label, normalize_failure_reason
from .failure_context import validate_context
from .map_capability import classify_map_capable
from .installation_policy import installation_authorization_for_row
from .device_labels import model_label, variant_label
from .admin_world_map import WORLD_MAP_COUNTRY_ALIASES, WORLD_MAP_SVG
from .maprando_geography import (
    REGION_DISPLAY_NAMES as MAPRANDO_REGION_DISPLAY_NAMES,
    REGION_GEOGRAPHY,
)
from .operational_health import provider_catalog_health
from .statistics_periods import ADMIN_PERIOD_LABELS, ADMIN_PERIODS


PASSWORD_MIN_LENGTH = 14
USERNAME_PATTERN = re.compile(r"[A-Za-z0-9._-]{3,64}")
PBKDF2_ITERATIONS = 600_000
GITHUB_ADMIN_NOTE_MAX_LENGTH = 500
GITHUB_ISSUE_URL_MAX_LENGTH = 7_000
GITHUB_NEW_ISSUE_URL = "https://github.com/VooZ2/terento/issues/new"
# Per-process, unguessable placeholder: only template-owned <script> tags carry
# it, so escaped data can never receive the response nonce (ADM-28).
_ADMIN_NONCE_PLACEHOLDER = "__TERENTO_ADMIN_NONCE_" + secrets.token_hex(12) + "__"
_ADMIN_TEXT_INPUT_LIMIT = 8_192


class AdminValidationError(ValueError):
    pass


def validate_username(value: str) -> str:
    username = value.strip()
    if not USERNAME_PATTERN.fullmatch(username):
        raise AdminValidationError("Username must contain 3–64 letters, numbers, or . _ - characters.")
    return username


def validate_password(value: str) -> str:
    if len(value) < PASSWORD_MIN_LENGTH or len(value) > 256:
        raise AdminValidationError(f"Password must be {PASSWORD_MIN_LENGTH}–256 characters.")
    return value


def hash_password(password: str) -> str:
    validate_password(password)
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS
    )
    return "$".join(
        (
            "pbkdf2-sha256",
            str(PBKDF2_ITERATIONS),
            base64.urlsafe_b64encode(salt).decode("ascii").rstrip("="),
            base64.urlsafe_b64encode(digest).decode("ascii").rstrip("="),
        )
    )


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt, expected = encoded.split("$", 3)
        if algorithm != "pbkdf2-sha256":
            return False
        salt_bytes = _decode_base64(salt)
        expected_bytes = _decode_base64(expected)
        actual = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt_bytes, int(iterations), len(expected_bytes)
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected_bytes)


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def format_timestamp(value: Any) -> str:
    if value is None:
        return "—"
    parsed = _parse_timestamp(value)
    if parsed is not None:
        return parsed.strftime("%Y-%m-%d %H:%M")
    return str(value)


def _timestamp_markup(value: Any) -> str:
    parsed = _parse_timestamp(value)
    if parsed is None:
        return html.escape(format_timestamp(value))
    iso = parsed.isoformat()
    return (
        f"<time class='admin-timestamp' datetime='{html.escape(iso, quote=True)}' "
        f"data-admin-timestamp='{html.escape(iso, quote=True)}'>"
        f"{html.escape(format_timestamp(parsed))}</time>"
    )


def _parse_timestamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        normalized_value = value.strip()
        # Accept legacy admin strings that lost the separator between date
        # and time without changing the stored timestamp.
        normalized_value = re.sub(
            r"^(\d{4}-\d{2}-\d{2})(\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?)$",
            r"\1T\2",
            normalized_value,
        )
        try:
            parsed = datetime.fromisoformat(normalized_value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _timestamp_iso(value: Any) -> str:
    parsed = _parse_timestamp(value)
    return parsed.isoformat() if parsed is not None else ""


def _latest_data_timestamp(rows: list[dict[str, Any]]) -> datetime | None:
    values = [
        _parse_timestamp(row.get(key))
        for row in rows
        for key in ("last_success", "last_failure", "last_evidence")
    ]
    parsed = [value for value in values if value is not None]
    return max(parsed) if parsed else None


def _row_compatibility_status(row: dict[str, Any]) -> CompatibilityStatus | None:
    """Recompute the display status from the canonical evidence dimensions."""
    successful = int(row.get("successful_install_count") or 0)
    return calculate_compatibility_status(
        successful_install_count=successful,
        recognized_map_capable_evidence=(
            row.get("recognized_map_capable_evidence") is True or successful > 0
        ),
    )


def _format_rate(value: Any) -> str:
    if value is None:
        return "—"
    try:
        rate = float(value)
    except (TypeError, ValueError):
        return "—"
    if rate.is_integer():
        return f"{int(rate)}%"
    return f"{rate:.1f}%"


def _optional_nonnegative_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def _optional_count_label(value: Any, suffix: str = "") -> str:
    number = _optional_nonnegative_int(value)
    return f"{number:,}{suffix}" if number is not None else f"—{suffix}"


def _admin_error_counter(
    value: Any,
    *,
    available: bool = True,
    href: str | None = None,
    aria_label: str | None = None,
    data_stat: str | None = None,
) -> str:
    """Render an error count with neutral unknown and positive-only danger state."""
    number = _optional_nonnegative_int(value) if available else None
    rendered = str(number) if number is not None else "—"
    classes = "admin-error-counter" + (" is-positive" if number is not None and number > 0 else "")
    stat_attribute = f" data-stat='{html.escape(data_stat, quote=True)}'" if data_stat else ""
    counter = f"<strong class='{classes}'{stat_attribute}>{rendered}</strong>"
    if not href:
        return counter
    label = aria_label or f"View {rendered} open error{'s' if rendered != '1' else ''}"
    return (
        f"<a class='error-count' href='{html.escape(href, quote=True)}' "
        f"aria-label='{html.escape(label, quote=True)}'>{counter}</a>"
    )


def _count_label(value: Any, singular: str, plural: str | None = None) -> str:
    """Render a count with consistent singular/plural copy across the admin UI."""
    count = _optional_nonnegative_int(value)
    if count is None:
        return "—"
    noun = singular if count == 1 else (plural or f"{singular}s")
    return f"{count} {noun}"


# Admin icons are original Font Awesome Free 7.3.1 solid SVGs (owner decision
# 2026-10-06: no hand-drawn icons). Font Awesome Free 7.3.1 by @fontawesome -
# https://fontawesome.com License - https://fontawesome.com/license/free
# (Icons: CC BY 4.0) Copyright 2026 Fonticons, Inc. Paths are unchanged; see
# THIRD_PARTY_NOTICES.md. Keys are Admin names, comments the upstream icon.
_FA_ICONS = {
    "external": ("0 0 512 512", "M320 0c-17.7 0-32 14.3-32 32s14.3 32 32 32l82.7 0-201.4 201.4c-12.5 12.5-12.5 32.8 0 45.3s32.8 12.5 45.3 0L448 109.3 448 192c0 17.7 14.3 32 32 32s32-14.3 32-32l0-160c0-17.7-14.3-32-32-32L320 0zM80 96C35.8 96 0 131.8 0 176L0 432c0 44.2 35.8 80 80 80l256 0c44.2 0 80-35.8 80-80l0-80c0-17.7-14.3-32-32-32s-32 14.3-32 32l0 80c0 8.8-7.2 16-16 16L80 448c-8.8 0-16-7.2-16-16l0-256c0-8.8 7.2-16 16-16l80 0c17.7 0 32-14.3 32-32s-14.3-32-32-32L80 96z"),  # arrow-up-right-from-square
    "arrow-right": ("0 0 512 512", "M502.6 278.6c12.5-12.5 12.5-32.8 0-45.3l-160-160c-12.5-12.5-32.8-12.5-45.3 0s-12.5 32.8 0 45.3L402.7 224 32 224c-17.7 0-32 14.3-32 32s14.3 32 32 32l370.7 0-105.4 105.4c-12.5 12.5-12.5 32.8 0 45.3s32.8 12.5 45.3 0l160-160z"),  # arrow-right
    "arrow-left": ("0 0 512 512", "M9.4 233.4c-12.5 12.5-12.5 32.8 0 45.3l160 160c12.5 12.5 32.8 12.5 45.3 0s12.5-32.8 0-45.3L109.3 288 480 288c17.7 0 32-14.3 32-32s-14.3-32-32-32l-370.7 0 105.4-105.4c12.5-12.5 12.5-32.8 0-45.3s-32.8-12.5-45.3 0l-160 160z"),  # arrow-left
    "check": ("0 0 448 512", "M434.8 70.1c14.3 10.4 17.5 30.4 7.1 44.7l-256 352c-5.5 7.6-14 12.3-23.4 13.1s-18.5-2.7-25.1-9.3l-128-128c-12.5-12.5-12.5-32.8 0-45.3s32.8-12.5 45.3 0l101.5 101.5 234-321.7c10.4-14.3 30.4-17.5 44.7-7.1z"),  # check
    "clock": ("0 0 512 512", "M256 0a256 256 0 1 1 0 512 256 256 0 1 1 0-512zM232 120l0 136c0 8 4 15.5 10.7 20l96 64c11 7.4 25.9 4.4 33.3-6.7s4.4-25.9-6.7-33.3L280 243.2 280 120c0-13.3-10.7-24-24-24s-24 10.7-24 24z"),  # clock
    "close": ("0 0 384 512", "M55.1 73.4c-12.5-12.5-32.8-12.5-45.3 0s-12.5 32.8 0 45.3L147.2 256 9.9 393.4c-12.5 12.5-12.5 32.8 0 45.3s32.8 12.5 45.3 0L192.5 301.3 329.9 438.6c12.5 12.5 32.8 12.5 45.3 0s12.5-32.8 0-45.3L237.8 256 375.1 118.6c12.5-12.5 12.5-32.8 0-45.3s-32.8-12.5-45.3 0L192.5 210.7 55.1 73.4z"),  # xmark
    "x-circle": ("0 0 512 512", "M256 512a256 256 0 1 0 0-512 256 256 0 1 0 0 512zM167 167c9.4-9.4 24.6-9.4 33.9 0l55 55 55-55c9.4-9.4 24.6-9.4 33.9 0s9.4 24.6 0 33.9l-55 55 55 55c9.4 9.4 9.4 24.6 0 33.9s-24.6 9.4-33.9 0l-55-55-55 55c-9.4 9.4-24.6 9.4-33.9 0s-9.4-24.6 0-33.9l55-55-55-55c-9.4-9.4-9.4-24.6 0-33.9z"),  # circle-xmark
    "alert": ("0 0 512 512", "M256 0c14.7 0 28.2 8.1 35.2 21l216 400c6.7 12.4 6.4 27.4-.8 39.5S486.1 480 472 480L40 480c-14.1 0-27.2-7.4-34.4-19.5s-7.5-27.1-.8-39.5l216-400c7-12.9 20.5-21 35.2-21zm0 352a32 32 0 1 0 0 64 32 32 0 1 0 0-64zm0-192c-18.2 0-32.7 15.5-31.4 33.7l7.4 104c.9 12.5 11.4 22.3 23.9 22.3 12.6 0 23-9.7 23.9-22.3l7.4-104c1.3-18.2-13.1-33.7-31.4-33.7z"),  # triangle-exclamation
    "info": ("0 0 512 512", "M256 512a256 256 0 1 0 0-512 256 256 0 1 0 0 512zM224 160a32 32 0 1 1 64 0 32 32 0 1 1 -64 0zm-8 64l48 0c13.3 0 24 10.7 24 24l0 88 8 0c13.3 0 24 10.7 24 24s-10.7 24-24 24l-80 0c-13.3 0-24-10.7-24-24s10.7-24 24-24l24 0 0-64-24 0c-13.3 0-24-10.7-24-24s10.7-24 24-24z"),  # circle-info
    "question": ("0 0 512 512", "M256 512a256 256 0 1 0 0-512 256 256 0 1 0 0 512zm0-336c-17.7 0-32 14.3-32 32 0 13.3-10.7 24-24 24s-24-10.7-24-24c0-44.2 35.8-80 80-80s80 35.8 80 80c0 47.2-36 67.2-56 74.5l0 3.8c0 13.3-10.7 24-24 24s-24-10.7-24-24l0-8.1c0-20.5 14.8-35.2 30.1-40.2 6.4-2.1 13.2-5.5 18.2-10.3 4.3-4.2 7.7-10 7.7-19.6 0-17.7-14.3-32-32-32zM224 368a32 32 0 1 1 64 0 32 32 0 1 1 -64 0z"),  # circle-question
    "minus": ("0 0 512 512", "M256 512a256 256 0 1 0 0-512 256 256 0 1 0 0 512zM168 232l176 0c13.3 0 24 10.7 24 24s-10.7 24-24 24l-176 0c-13.3 0-24-10.7-24-24s10.7-24 24-24z"),  # circle-minus
    "download": ("0 0 448 512", "M256 32c0-17.7-14.3-32-32-32s-32 14.3-32 32l0 210.7-41.4-41.4c-12.5-12.5-32.8-12.5-45.3 0s-12.5 32.8 0 45.3l96 96c12.5 12.5 32.8 12.5 45.3 0l96-96c12.5-12.5 12.5-32.8 0-45.3s-32.8-12.5-45.3 0L256 242.7 256 32zM64 320c-35.3 0-64 28.7-64 64l0 32c0 35.3 28.7 64 64 64l320 0c35.3 0 64-28.7 64-64l0-32c0-35.3-28.7-64-64-64l-46.9 0-56.6 56.6c-31.2 31.2-81.9 31.2-113.1 0L110.9 320 64 320zm304 56a24 24 0 1 1 0 48 24 24 0 1 1 0-48z"),  # download
    "message": ("0 0 512 512", "M0 352L0 128C0 75 43 32 96 32l320 0c53 0 96 43 96 96l0 224c0 53-43 96-96 96l-120 0c-5.2 0-10.2 1.7-14.4 4.8L166.4 539.2c-4.2 3.1-9.2 4.8-14.4 4.8-13.3 0-24-10.7-24-24l0-72-32 0c-53 0-96-43-96-96z"),  # message
    "circle-check": ("0 0 512 512", "M256 512a256 256 0 1 1 0-512 256 256 0 1 1 0 512zM374 145.7c-10.7-7.8-25.7-5.4-33.5 5.3L221.1 315.2 169 263.1c-9.4-9.4-24.6-9.4-33.9 0s-9.4 24.6 0 33.9l72 72c5 5 11.8 7.5 18.8 7s13.4-4.1 17.5-9.8L379.3 179.2c7.8-10.7 5.4-25.7-5.3-33.5z"),  # circle-check
    "circle-exclamation": ("0 0 512 512", "M256 512a256 256 0 1 1 0-512 256 256 0 1 1 0 512zm0-192a32 32 0 1 0 0 64 32 32 0 1 0 0-64zm0-192c-18.2 0-32.7 15.5-31.4 33.7l7.4 104c.9 12.6 11.4 22.3 23.9 22.3 12.6 0 23-9.7 23.9-22.3l7.4-104c1.3-18.2-13.1-33.7-31.4-33.7z"),  # circle-exclamation
    "chevron-down": ("0 0 448 512", "M201.4 406.6c12.5 12.5 32.8 12.5 45.3 0l192-192c12.5-12.5 12.5-32.8 0-45.3s-32.8-12.5-45.3 0L224 338.7 54.6 169.4c-12.5-12.5-32.8-12.5-45.3 0s-12.5 32.8 0 45.3l192 192z"),  # chevron-down
    "chevron-right": ("0 0 320 512", "M311.1 233.4c12.5 12.5 12.5 32.8 0 45.3l-192 192c-12.5 12.5-32.8 12.5-45.3 0s-12.5-32.8 0-45.3L243.2 256 73.9 86.6c-12.5-12.5-12.5-32.8 0-45.3s32.8-12.5 45.3 0l192 192z"),  # chevron-right
    "image": ("0 0 448 512", "M64 32C28.7 32 0 60.7 0 96L0 416c0 35.3 28.7 64 64 64l320 0c35.3 0 64-28.7 64-64l0-320c0-35.3-28.7-64-64-64L64 32zm64 80a48 48 0 1 1 0 96 48 48 0 1 1 0-96zM272 224c8.4 0 16.1 4.4 20.5 11.5l88 144c4.5 7.4 4.7 16.7 .5 24.3S368.7 416 360 416L88 416c-8.9 0-17.2-5-21.3-12.9s-3.5-17.5 1.6-24.8l56-80c4.5-6.4 11.8-10.2 19.7-10.2s15.2 3.8 19.7 10.2l26.4 37.8 61.4-100.5c4.4-7.1 12.1-11.5 20.5-11.5z"),  # image
    "sort": ("0 0 384 512", "M2.4 204.2c5 12 16.6 19.8 29.6 19.8l320 0c12.9 0 24.6-7.8 29.6-19.8s2.2-25.7-6.9-34.9l-160-160c-12.5-12.5-32.8-12.5-45.3 0l-160 160c-9.2 9.2-11.9 22.9-6.9 34.9zm0 103.5c-5 12-2.2 25.7 6.9 34.9l160 160c12.5 12.5 32.8 12.5 45.3 0l160-160c9.2-9.2 11.9-22.9 6.9-34.9S364.9 288 352 288L32 288c-12.9 0-24.6 7.8-29.6 19.8z"),  # sort
    "sort-up": ("0 0 384 512", "M32 224c-12.9 0-24.6-7.8-29.6-19.8S.2 178.5 9.4 169.4l160-160c12.5-12.5 32.8-12.5 45.3 0l160 160c9.2 9.2 11.9 22.9 6.9 34.9S364.9 224 352 224L32 224z"),  # sort-up
    "sort-down": ("0 0 384 512", "M32 288c-12.9 0-24.6 7.8-29.6 19.8S.2 333.5 9.4 342.6l160 160c12.5 12.5 32.8 12.5 45.3 0l160-160c9.2-9.2 11.9-22.9 6.9-34.9S364.9 288 352 288L32 288z"),  # sort-down
    "ellipsis": ("0 0 448 512", "M0 256a56 56 0 1 1 112 0 56 56 0 1 1 -112 0zm168 0a56 56 0 1 1 112 0 56 56 0 1 1 -112 0zm224-56a56 56 0 1 1 0 112 56 56 0 1 1 0-112z"),  # ellipsis
    "arrows-left-right": ("0 0 512 512", "M502.6 150.6l-96 96c-12.5 12.5-32.8 12.5-45.3 0s-12.5-32.8 0-45.3L402.7 160 32 160c-17.7 0-32-14.3-32-32S14.3 96 32 96l370.7 0-41.4-41.4c-12.5-12.5-12.5-32.8 0-45.3s32.8-12.5 45.3 0l96 96c12.5 12.5 12.5 32.8 0 45.3zm-397.3 352l-96-96c-12.5-12.5-12.5-32.8 0-45.3l96-96c12.5-12.5 32.8-12.5 45.3 0s12.5 32.8 0 45.3L109.3 352 480 352c17.7 0 32 14.3 32 32s-14.3 32-32 32l-370.7 0 41.4 41.4c12.5 12.5 12.5 32.8 0 45.3s-32.8 12.5-45.3 0z"),  # arrow-right-arrow-left
}


def _admin_icon(name: str) -> str:
    """Return one small, accessible Font Awesome icon for admin affordances."""
    icon = _FA_ICONS.get(name)
    if not icon:
        return ""
    view_box, path = icon
    css_name = re.sub(r"[^a-z0-9_-]", "-", name.lower())
    return (
        f"<svg class='admin-icon admin-icon-{css_name}' viewBox='{view_box}' "
        f"aria-hidden='true' focusable='false'><path fill='currentColor' d='{path}'/></svg>"
    )


# ---------------------------------------------------------------------------
# Shared presentation kit (docs/admin-behavior-contract.md, "Shared component
# kit"). Every page renders numbers, statuses, cards, empty states and legends
# through these helpers so one concept looks the same everywhere.
# ---------------------------------------------------------------------------

ADMIN_SCOPE_LABELS = {**ADMIN_PERIOD_LABELS, "now": "Now"}


def _scope_chip(scope: str) -> str:
    """Visible scope for a number: a period, ``All time`` or ``Now``."""
    label = ADMIN_SCOPE_LABELS.get(scope, scope)
    kind = "period" if scope in {"today", "24h", "7d", "30d"} else "now" if scope == "now" else "all"
    return f"<span class='admin-scope-chip' data-scope='{kind}'>{html.escape(label)}</span>"


_PILL_ICONS = {
    "success": "check",
    "danger": "x-circle",
    "warning": "alert",
    "info": "info",
    "progress": "clock",
    "neutral": "minus",
    "unknown": "question",
}


def _status_pill(kind: str, label: str, *, title: str | None = None, value: str | None = None) -> str:
    """One status family: icon plus text; colour only supports the text."""
    kind = kind if kind in _PILL_ICONS else "neutral"
    title_attribute = f" title='{html.escape(title, quote=True)}'" if title else ""
    value_attribute = f" data-status='{html.escape(value, quote=True)}'" if value else ""
    return (
        f"<span class='admin-pill admin-pill-{kind}'{value_attribute}{title_attribute}>"
        f"{_admin_icon(_PILL_ICONS[kind])}<span>{html.escape(label)}</span></span>"
    )


def _metric_value_text(value: Any, fmt: str) -> str | None:
    if value is None or isinstance(value, bool):
        return None
    if fmt == "rate":
        text = _format_rate(value)
        return None if text == "—" else text
    if fmt == "text":
        return str(value)
    number = _optional_nonnegative_int(value)
    return f"{number:,}" if number is not None else None


def _metric_tile(
    label: str, value: Any, *, fmt: str = "count", scope: str | None = None,
    state: str | None = None, failure: bool = False, secondary: str = "",
    href: str | None = None,
    data_stat: str | None = None, hint: str | None = None,
    value_html: str | None = None,
) -> str:
    """One metric: label, value, visible scope chip and one optional secondary line.

    ``state`` is measured, unknown, unavailable or partial. A failure count uses
    the danger tone only when it is a measured value above zero; tiles carry no
    icons.
    """
    rendered = _metric_value_text(value, fmt)
    if state is None:
        state = "measured" if rendered is not None else "unknown"
    if state in {"unknown", "unavailable"}:
        rendered = None
    tone = "neutral"
    if failure and state in {"measured", "partial"} and (_optional_nonnegative_int(value) or 0) > 0:
        tone = "danger"
    value_markup = (value_html if value_html is not None and rendered is not None else
                    html.escape(rendered) if rendered is not None else (
        "—<span class='sr-only'>" + ("Unavailable" if state == "unavailable" else "Unknown") + "</span>"
    ))
    stat = f" data-stat='{html.escape(data_stat, quote=True)}'" if data_stat else ""
    state_pill = ""
    if state == "unavailable":
        state_pill = _status_pill("unknown", "Unavailable")
    elif state == "partial":
        state_pill = _status_pill("warning", "Partial", title=hint or "Some values were not recorded.")
    meta = "".join(part for part in (_scope_chip(scope) if scope else "", state_pill, (
        f"<span class='admin-metric-secondary'>{secondary}</span>" if secondary else ""
    )) if part)
    scope_text = f", {ADMIN_SCOPE_LABELS.get(scope, scope).lower()}" if scope else ""
    plain_value = rendered if rendered is not None else ("unavailable" if state == "unavailable" else "unknown")
    title = f" title='{html.escape(hint, quote=True)}'" if hint and state != "partial" else ""
    inner = (
        f"<span class='admin-metric-label'>{html.escape(label)}</span>"
        f"<strong class='admin-metric-value'{stat}>{value_markup}</strong>"
        + (f"<span class='admin-metric-meta'>{meta}</span>" if meta else "")
    )
    attributes = f"data-state='{state}' data-tone='{tone}'{' data-kind=' + chr(39) + 'text' + chr(39) if fmt == 'text' else ''}{title}"
    if href:
        return (
            f"<a class='admin-metric admin-metric-link' {attributes} href='{html.escape(href, quote=True)}' "
            f"aria-label='{html.escape(label + scope_text + ': ' + plain_value, quote=True)}'>{inner}</a>"
        )
    return f"<div class='admin-metric' {attributes}>{inner}</div>"


def _quick_select_filter(
    select_id: str, options: list[tuple[str, str]], selected: str, *, label: str, name: str | None = None,
) -> str:
    """Quick-filter buttons driving a hidden filter select.

    Owner decision 2026-10-06: every filter bar uses the Installations design,
    so a single-choice filter is a quick-filter group, not a dropdown. The
    native select stays in the DOM, hidden, as the source of truth for page
    scripts and GET forms; ``_admin_quick_select_script`` keeps both in sync.
    """
    buttons = "".join(
        f"<button type='button' class='quick-filter{' active' if value == selected else ''}' "
        f"data-quick-value='{html.escape(value, quote=True)}' aria-pressed='{'true' if value == selected else 'false'}'>"
        f"{html.escape(text)}</button>"
        for value, text in options
    )
    select_options = "".join(
        f"<option value='{html.escape(value, quote=True)}'{' selected' if value == selected else ''}>{html.escape(text)}</option>"
        for value, text in options
    )
    name_attribute = f" name='{html.escape(name, quote=True)}'" if name else ""
    return (
        f"<div class='quick-filter-group' role='group' aria-label='{html.escape(label, quote=True)}' "
        f"data-quick-select='{html.escape(select_id, quote=True)}'>{buttons}</div>"
        f"<label hidden><span class='sr-only'>{html.escape(label)}</span>"
        f"<select id='{html.escape(select_id, quote=True)}'{name_attribute}>{select_options}</select></label>"
    )


def _metric_row(tiles: list[str], *, label: str, css: str = "") -> str:
    return (
        f"<div class='admin-metric-row{(' ' + css) if css else ''}' role='group' "
        f"aria-label='{html.escape(label, quote=True)}'>{''.join(tiles)}</div>"
    )


def _section_card(
    title: str, body: str, *, card_id: str, action: tuple[str, str] | None = None,
    scope: str | None = None, css: str = "", totals: str = "",
    heading_tag: str = "h2", extra_attributes: str = "", mobile_collapse: bool = False,
) -> str:
    """A card with a 1–2 word title, an optional scope chip and one action link.

    ``mobile_collapse`` lets a long card start collapsed at ≤600 px behind a
    Show/Hide button (the shared mobile-collapse script); without script or on
    wider screens it stays fully open.
    """
    if mobile_collapse:
        extra_attributes += " data-mobile-collapse"
    toggle_markup = (
        f"<button type='button' class='secondary-button admin-card-toggle' data-mobile-collapse-toggle "
        f"aria-expanded='true' aria-controls='{html.escape(card_id, quote=True)}' hidden>"
        f"Hide<span class='sr-only'> {html.escape(title)}</span></button>"
        if mobile_collapse else ""
    )
    action_markup = (
        f"<a class='admin-card-action section-link' href='{html.escape(action[0], quote=True)}'>"
        f"{html.escape(action[1])}&nbsp;{_admin_icon('arrow-right')}</a>"
        if action else ""
    )
    head = (
        f"<header class='admin-card-head'><{heading_tag} id='{html.escape(card_id, quote=True)}-title'>"
        f"{html.escape(title)}</{heading_tag}>"
        + (_scope_chip(scope) if scope else "")
        + totals + action_markup + toggle_markup + "</header>"
    )
    return (
        f"<section class='admin-card{(' ' + css) if css else ''}' id='{html.escape(card_id, quote=True)}' "
        f"aria-labelledby='{html.escape(card_id, quote=True)}-title'{extra_attributes}>{head}{body}</section>"
    )


def _empty_state(kind: str, text: str, *, action: tuple[str, str] | None = None, css: str = "") -> str:
    """empty (measured nothing), filtered, or unavailable (query failed)."""
    kind = kind if kind in {"empty", "filtered", "unavailable"} else "empty"
    pill = _status_pill("unknown", "Unavailable") + " " if kind == "unavailable" else ""
    action_markup = (
        f" <a class='section-link' href='{html.escape(action[0], quote=True)}'>{html.escape(action[1])}</a>"
        if action else ""
    )
    role = " role='status'" if kind == "unavailable" else ""
    return (
        f"<p class='admin-empty{(' ' + css) if css else ''}' data-state='{kind}'{role}>"
        f"{pill}<span>{html.escape(text)}</span>{action_markup}</p>"
    )


def _unavailable_card(title: str, card_id: str, *, retry_href: str = "") -> str:
    """Section-level resilience: a failed sub-query keeps the admin chrome."""
    return _section_card(
        title,
        _empty_state("unavailable", "Could not load this section.", action=(retry_href or "", "Retry")),
        card_id=card_id, css="admin-card-unavailable",
    )


def _is_historical_catalog(row: dict[str, Any]) -> bool:
    return str(row.get("recordSource") or row.get("record_source") or "").upper() == "HISTORICAL_REVIEWED"


def _historical_catalog_indicator() -> str:
    """Compact provenance; the surrounding model link provides keyboard focus."""
    return (
        "<span class='historical-catalog-indicator'>"
        + '<svg class=\'catalog-archive-icon\' aria-hidden=\'true\' focusable=\'false\' xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512"><!--! Font Awesome Free 7.3.1 by @fontawesome - https://fontawesome.com License - https://fontawesome.com/license/free (Icons: CC BY 4.0, Fonts: SIL OFL 1.1, Code: MIT License) Copyright 2026 Fonticons, Inc. --><path fill="currentColor" d="M0 64C0 46.3 14.3 32 32 32l448 0c17.7 0 32 14.3 32 32l0 32c0 17.7-14.3 32-32 32L32 128C14.3 128 0 113.7 0 96L0 64zM32 176l448 0 0 240c0 35.3-28.7 64-64 64L96 480c-35.3 0-64-28.7-64-64l0-240zm152 64c-13.3 0-24 10.7-24 24s10.7 24 24 24l144 0c13.3 0 24-10.7 24-24s-10.7-24-24-24l-144 0z"/></svg>'
        + "<span class='historical-catalog-tooltip'>Historical catalog entry</span></span>"
    )


def _normalise_variant(value: Any) -> str:
    return variant_label({"variant": str(value or "")[:256]}) or "—"


def _identity_parts(row: dict[str, Any]) -> tuple[str, str, str]:
    model = str(row.get("model") or "—").strip()
    identity = str(row.get("compatibility_identity") or model).strip()
    variant = str(row.get("variant") or "").strip()
    case_size = row.get("case_size_mm")

    if "·" in identity:
        base, suffix = (part.strip() for part in identity.rsplit("·", 1))
        if base and not re.search(r"\binreach\b", suffix, flags=re.IGNORECASE):
            model = base
        if not variant:
            variant = suffix
    elif not variant:
        size_match = re.search(r"\b\d{2,3}\s*mm\b", identity, flags=re.IGNORECASE)
        if size_match:
            variant = size_match.group(0)
            model = (identity[:size_match.start()].rstrip(" -–—") + identity[size_match.end():]).strip()

    if case_size is not None and not re.search(r"\b\d{2,3}\s*mm\b", variant, flags=re.IGNORECASE):
        try:
            variant = f"{int(case_size)} mm {variant}".strip()
        except (TypeError, ValueError):
            pass
    # Display-only cleanup; the canonical identity remains unchanged.
    size = re.search(r"\b\d{2,3}\s*mm\b", variant, flags=re.IGNORECASE)
    if size:
        model = re.sub(r"\s*[,·|:–—-]?\s*" + re.escape(size.group(0)) + r"\s*$", "", model, flags=re.IGNORECASE)
    model = model.strip(" ,·|:–—-")
    if row.get("canonical_device_model_id"):
        model = row.get("canonical_model") or row.get("catalog_model") or model
    return model_label(model) or "—", variant_label({**row, "model": model, "variant": variant}) or "—", identity


def _operation_key(result: dict[str, Any]) -> str:
    return str(
        result.get("operation_key")
        or result.get("operation_id")
        or result.get("event_id")
        or ""
    ).strip()


def _result_key(result: dict[str, Any]) -> str:
    """Identify one main-map result, not the enclosing install batch."""
    operation = str(result.get("operation_id") or "").strip()
    index = result.get("map_result_index")
    if operation and index is not None:
        return f"result:{operation}:{index}"
    existing_key = str(result.get("operation_key") or "").strip()
    if existing_key:
        return existing_key
    event_id = str(result.get("event_id") or "").strip()
    return f"event:{event_id}" if event_id else _operation_key(result)


def _group_operations(events: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        key = _result_key(event)
        if key:
            grouped.setdefault(key, []).append(event)
    for results in grouped.values():
        results.sort(key=lambda item: int(item.get("map_result_index") or 0))
    return grouped


def _group_operation_tasks(events: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Group operator work by operation, keeping one task for a multi-map batch."""
    grouped: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        # compatibility_operation_details exposes a per-result operation_key;
        # deliberately prefer the raw operation ID here so the queue remains
        # operation-level when one batch contains several map results.
        key = str(
            event.get("operation_id")
            or event.get("operationId")
            or event.get("event_id")
            or event.get("eventId")
            or event.get("operation_key")
            or ""
        ).strip()
        if key:
            grouped.setdefault(key, []).append(event)
    for results in grouped.values():
        results.sort(key=lambda item: (_timestamp_iso(item.get("occurred_at")), str(item.get("event_id") or "")))
    return grouped


def _is_preinstall_download_failure(result: dict[str, Any]) -> bool:
    """Return whether a provider download failed before device installation."""
    if result.get("preinstall_download_failure") is True or result.get("preinstall_download_failure") == 1:
        return True
    write_started = result.get("write_started")
    if not (write_started is False or write_started == 0):
        return False
    stage = str(result.get("failure_stage") or "").strip().casefold()
    code = str(result.get("failure_code") or "").strip().upper()
    return stage == "download" or code == "INSTALL_BLOCKED_DOWNLOAD_FAILED"

def _is_preinstall_download_operation(results: list[dict[str, Any]]) -> bool:
    """Keep provider acquisition failures out of installation history views."""
    return bool(results) and all(_is_preinstall_download_failure(result) for result in results)

def _identity_is_pending(results: list[dict[str, Any]]) -> bool:
    if not results:
        return False
    if all(_is_preinstall_download_failure(result) for result in results):
        return False
    first = results[0]
    if first.get("canonical_device_model_id"):
        return False
    state = str(first.get("identity_resolution_state") or "").strip().upper()
    if state in {"RESOLVED", "NOT_IDENTIFIABLE"}:
        return False
    return state in {"", "UNRESOLVED", "PENDING"}


def _identity_group_key(value: dict[str, Any]) -> str:
    canonical_id = str(value.get("canonical_device_model_id") or "").strip()
    if canonical_id:
        return f"canonical:{canonical_id}"
    identity = str(value.get("compatibility_identity") or value.get("model") or "Unknown").strip()
    return f"identity:{identity}"


def _device_detail_url(
    device_id: Any, *, origin: str = "devices", state: str | None = None,
    anchor: str | None = None,
) -> str:
    parameters = {"from": "installations" if origin == "installations" else "devices"}
    if state:
        parameters["state"] = state
    url = f"/admin/devices/{quote(str(device_id or '').strip(), safe='')}?{urlencode(parameters)}"
    return f"{url}#{quote(anchor, safe='')}" if anchor else url


def _diagnostics_url(value: dict[str, Any], *, state: str | None = None) -> str:
    identity = str(value.get("compatibility_identity") or value.get("model") or "Unknown").strip()
    parameters = {"identity": identity}
    canonical_id = str(value.get("canonical_device_model_id") or "").strip()
    if canonical_id:
        parameters["canonical_device_id"] = canonical_id
    else:
        # A textual identity can be shared by both a canonical aggregate and a
        # still-unresolved aggregate. Preserve the unresolved scope so the
        # diagnostics route cannot redirect the pending row to the canonical
        # device before an operator reviews it.
        parameters["identity_scope"] = "unresolved"
    if state:
        parameters["state"] = state
    return "/admin/diagnostics?" + urlencode(parameters)


def _model_detail_url(value: dict[str, Any], *, state: str | None = None) -> str:
    canonical_id = str(value.get("canonical_device_model_id") or "").strip()
    if canonical_id:
        return _device_detail_url(
            canonical_id, origin="installations", state=state, anchor="installations",
        )
    return _diagnostics_url(value, state=state)


def _operation_is_problematic(results: list[dict[str, Any]]) -> bool:
    """Return whether an install operation needs diagnostic attention.

    Successful evidence is intentionally not a diagnostic error. A diagnostic
    is actionable when an install failed, never started, was blocked, or
    carries an explicit failure diagnostic.
    """
    for result in results:
        if _is_preinstall_download_failure(result):
            # Provider acquisition problems are expected operational history,
            # not installation defects requiring operator review.
            continue
        outcome = str(result.get("phase_outcome") or "").strip().upper()
        if outcome in {"FAILED", "NOT_STARTED", "INCOMPLETE", "BLOCKED"}:
            return True
        finishing = str(result.get("automatic_finishing_result") or "").strip().upper()
        if outcome == "SUCCEEDED" and finishing and finishing != "VERIFIED":
            return True
        if any(
            str(result.get(field) or "").strip()
            for field in ("failure_stage", "failure_code", "native_failure_code", "error_category")
        ):
            return True
        if result.get("write_started") is False:
            return True
    return False


def _result_is_open_problem(results: list[dict[str, Any]]) -> bool:
    """Row-level mirror of the canonical open installation problem predicate.

    A phase-FAILED diagnostic that is not a provider download/pre-install
    failure, without a linked GitHub issue. The authoritative count and unit
    (operations) come from ``Database.installation_problem_counts``.
    """
    return any(
        str(result.get("phase_outcome") or "").strip().upper() == "FAILED"
        and not _is_preinstall_download_failure(result)
        for result in results
    ) and not _operation_issue(results)


def _open_problem_operation_count(events: list[dict[str, Any]]) -> int:
    """Fallback operation-level open problem count when SQL counts are absent."""
    return sum(
        1 for results in _group_operation_tasks(events).values()
        if _result_is_open_problem(results)
    )


def _diagnostic_summary_by_identity(
    events: list[dict[str, Any]], resolved_events: list[dict[str, Any]] | None = None,
) -> dict[str, dict[str, int]]:
    """Summarise per-map results by identity with view-067 semantics.

    ``ACTIVE``/``RESOLVED`` is operator workflow only: a resolved verified
    success or started failure keeps its historical outcome in attempts,
    successes and failures. Only ``open_errors`` and ``identity_pending`` are
    workflow-scoped and therefore read active results alone.
    """
    by_identity: dict[str, dict[str, int]] = {}
    grouped: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for event in events:
        identity = _identity_group_key(event)
        key = _result_key(event)
        if identity and key:
            grouped.setdefault(identity, {}).setdefault(key, []).append(event)
    resolved_grouped: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for event in resolved_events or []:
        identity = _identity_group_key(event)
        key = _result_key(event)
        if identity and key:
            resolved_grouped.setdefault(identity, {}).setdefault(key, []).append(event)
    for identity in set(grouped) | set(resolved_grouped):
        operations = grouped.get(identity, {})
        historical = resolved_grouped.get(identity, {})
        results: dict[str, list[dict[str, Any]]] = {}
        for source in (operations, historical):
            for key, rows in source.items():
                results.setdefault(key, []).extend(rows)
        attempted = {
            key: _operation_result(rows) for key, rows in results.items()
            if _operation_counts_as_installation_attempt(rows)
        }
        open_errors = sum(
            1 for results_for_key in operations.values()
            if _operation_counts_as_installation_attempt(results_for_key)
            and _operation_result(results_for_key) == "FAILED"
        )
        pending = sum(1 for results_for_key in operations.values() if _identity_is_pending(results_for_key))
        by_identity[identity] = {
            "errors": open_errors,
            "open_errors": open_errors,
            "failed": sum(1 for result in attempted.values() if result == "FAILED"),
            "attempts": len(attempted),
            "successful": sum(1 for result in attempted.values() if result == "SUCCEEDED"),
            "identity_pending": pending,
        }
    return by_identity


def _normalise_github_issue_reference(value: Any) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    match = re.fullmatch(r"#?(\d{1,10})", raw)
    if not match:
        raise ValueError("GitHub issue must be a Terento issue number such as #32")
    return f"#{int(match.group(1))}"


def _diagnostic_state_badge(value: str) -> str:
    normalized = str(value).upper()
    if normalized == "NONE":
        return "<span class='muted-value'>—</span>"
    if normalized == "RESOLVED":
        return _status_pill("success", "Resolved", value="RESOLVED")
    if normalized in {"IN_PROGRESS", "IN-PROGRESS"}:
        return _status_pill("progress", "In progress", value="IN_PROGRESS")
    if normalized in {"UNDER_REVIEW", "UNDER-REVIEW"}:
        return _status_pill("info", "Under review", value="UNDER_REVIEW")
    if normalized in {"IDENTITY_PENDING", "UNRESOLVED", "PENDING"}:
        return _status_pill("unknown", "Identity review", value="IDENTITY_PENDING")
    return _status_pill("danger", "Open", value="OPEN")


def _diagnostic_value(value: Any) -> str:
    if value is None or value == "":
        return "<span class='muted-value'>—</span>"
    return html.escape(str(value))


def _diagnostic_boolean(value: Any) -> str:
    if value is None:
        return "<span class='muted-value'>—</span>"
    if isinstance(value, str):
        normalised = value.strip().casefold()
        if normalised in {"true", "1", "yes"}:
            return "Yes"
        if normalised in {"false", "0", "no"}:
            return "No"
    return "Yes" if bool(value) else "No"


def _diagnostic_result(value: Any) -> str:
    raw = str(value or "").strip().upper()
    labels = {
        "SUCCEEDED": ("success", "Successful"),
        "FAILED": ("danger", "Failed"),
        # A pre-write result is not a failed attempt (ADM-13). The pill says
        # "Blocked" so it fits table cells (owner decision 2026-10-06); its
        # title keeps the full term.
        "NOT_STARTED": ("warning", "Blocked"),
        "INCOMPLETE": ("warning", "Incomplete"),
        "BLOCKED": ("warning", "Blocked"),
    }
    kind, label = labels.get(raw, ("unknown", raw.title() if raw else "—"))
    title = "Blocked before writing" if raw == "NOT_STARTED" else None
    return _status_pill(kind, label, value=raw or "UNKNOWN", title=title)


def _failure_context_fields(result: dict[str, Any], key: str, *, technical: bool = False) -> list[tuple[str, Any]]:
    context = result.get(key)
    try:
        validate_context(context)
    except ValueError:
        context = {}
    protection = context.get('protection', {})
    fields = [
        ('Boundary', context.get('boundary')), ('Protection reason', protection.get('protectionReason')),
        ('Native category', context.get('nativeCategory')), ('Retry count', context.get('retryCount')),
        ('Classification source', context.get('classificationSource')), ('Device presence', context.get('devicePresence')),
        ('Component', context.get('componentKind')),
    ]
    if technical:
        fields.extend((label, context.get(name)) for label, name in (
            ('Last successful boundary', 'lastSuccessfulBoundary'), ('Operation', 'operation'),
            ('Execution mode', 'executionMode'), ('Result kind', 'resultKind'),
            ('Native code namespace', 'nativeCodeNamespace'), ('Native result code', 'nativeResultCode'),
        ))
        fields.extend((name, protection.get(name)) for name in (
            'protectionBoundary', 'stableIdentityComparisonVersion', 'beforeObjectCount', 'afterObjectCount',
            'addedObjectCount', 'removedObjectCount', 'changedObjectCount', 'targetPresent', 'targetUnique',
            'targetKindMatches', 'targetFilenameMatches', 'targetSizeMatches', 'targetPathMatches', 'targetItemIDMatches',
        ))
    return [(label, 'unavailable' if value is None else value) for label, value in fields]


def _failure_context_summary(results: list[dict[str, Any]]) -> str:
    summaries = []
    for number, result in enumerate(results, 1):
        context = result.get('failure_context') or {}
        stage = result.get('optional_component_failure_stage') if isinstance(context, dict) and context.get('componentKind') == 'contours' else result.get('failure_stage')
        fields = [('Stage', stage or 'unavailable')] + _failure_context_fields(result, 'failure_context')
        rows = ''.join(f'<div><dt>{html.escape(label)}</dt><dd>{_diagnostic_value(value)}</dd></div>' for label, value in fields)
        summaries.append(f'<p>Failure context · {html.escape(_failure_result_label(result, number))}</p><dl class="diagnostic-detail-summary">{rows}</dl>')
    return ''.join(summaries)


def _failure_result_label(result: dict[str, Any], number: int) -> str:
    index = result.get('map_result_index')
    return f'mapResultIndex {index}' if type(index) is int and 0 <= index < 100 else f'displayed result {number} (mapResultIndex unavailable)'


def _diagnostic_technical_details(result: dict[str, Any], result_number: int) -> str:
    fields: list[tuple[str, Any]] = []
    for label, key in (
        ("Raw MTP model", "raw_mtp_model"),
        ("Local identity", "identity_resolution_code"),
        ("Native code", "native_failure_code"),
        ("Transfer progress", "transfer_progress_bucket"),
        ("Map result", "map_result_index"),
        ("Selected maps", "selected_map_count"),
        ("Optional component selected", "optional_component_selected"),
        ("Optional component outcome", "optional_component_outcome"),
        ("Optional component failure stage", "optional_component_failure_stage"),
        ("Optional component failure code", "optional_component_failure_code"),
        ("Optional component native code", "optional_component_native_failure_code"),
        ("Error category", "error_category"),
        ("Transport", "transport"),
    ):
        value = result.get(key)
        if value is not None and value != "":
            fields.append((label, value))
    for label, key in (
        ("Object created", "remote_object_created"),
        ("Cleanup attempted", "cleanup_attempted"),
        ("Cleanup succeeded", "cleanup_succeeded"),
    ):
        if result.get(key) is not None:
            fields.append((label, _diagnostic_boolean(result.get(key))))
    metrics = result.get("inventory_metrics")
    if isinstance(metrics, str):
        try:
            metrics = json.loads(metrics)
        except ValueError:
            metrics = None
    if isinstance(metrics, dict):
        # Diagnostics only (inventoryMetrics); never a count.
        for label, key in (
            ("Inventory scope", "scope"),
            ("Pre-write objects", "prewriteObjectCount"),
            ("Pre-write check (ms)", "prewriteDurationMs"),
            ("Post-write objects", "postwriteObjectCount"),
            ("Post-write check (ms)", "postwriteDurationMs"),
        ):
            if metrics.get(key) is not None:
                fields.append((label, metrics[key]))
    for key, prefix in (('failure_context', 'Failure'), ('original_failure_context', 'Original failure')):
        if key == 'original_failure_context' and result.get(key) is None:
            fields.append(('Original failure context', 'unavailable'))
        else:
            fields.extend((f'{prefix}: {label}', value) for label, value in _failure_context_fields(result, key, technical=result.get(key) is not None))
    rows = "".join(
        f"<div><dt>{html.escape(label)}</dt><dd>{value if isinstance(value, str) and value.startswith('<span') else _diagnostic_value(value)}</dd></div>"
        for label, value in fields
    )
    content = (
        f"<dl>{rows}</dl>" if rows else
        "<p class='diagnostic-technical-empty'>Detailed diagnostics were not collected for this installation.</p>"
    )
    return (
        f"<details class='{DIAGNOSTIC_DISCLOSURE_CLASS} diagnostic-technical-details'>"
        f"<summary>Technical details <span class='disclosure-meta'>· map result {result_number}</span></summary>"
        f"<div class='disclosure-body'>{content}</div></details>"
    )


def _admin_brand(*, show_badge: bool = True) -> str:
    badge = '<span class="admin-badge">Admin</span>' if show_badge else ""
    return f"""<a class="admin-brand" href="/admin" aria-label="Terento admin home">
      <img src="https://terento.app/assets/logo-sky.svg" alt="" width="25" height="29">
      <span>Terento</span>{badge}
    </a>"""


def _admin_header(user: dict[str, Any], csrf_token: str, *, active: str = "evidence") -> str:
    username = html.escape(str(user.get("username") or ""))
    overview_class = " class='active'" if active == "overview" else ""
    evidence_class = " class='active'" if active in {"evidence", "installations"} else ""
    campaign_class = " class='active'" if active == "campaigns" else ""
    devices_class = " class='active'" if active == "devices" else ""
    providers_class = " class='active'" if active == "providers" else ""
    map_statistics_class = " class='active'" if active == "map-statistics" else ""
    system_health_class = " class='active'" if active == "system-health" else ""
    test_data_class = " class='active'" if active == "test-data" else ""
    tools_class = " class='active'" if active in {"test-data", "campaigns", "device-identification", "update-diagnostics"} else ""
    sources_class = " class='active'" if active == "device-identification" else ""
    update_reports_class = " class='active'" if active == "update-diagnostics" else ""
    account_class = " active" if active == "account" else ""
    tools_menu = f"""<details class="admin-tools-menu">
        <summary{tools_class}>Tools</summary>
        <div class="admin-tools-popover" role="group" aria-label="Admin tools">
          <a{sources_class} href="/admin/device-identification">Model sources</a>
          <a{update_reports_class} href="/admin/update-diagnostics">Update reports</a>
          <a{test_data_class} href="/admin/test-data">Test data</a>
          <a{campaign_class} href="/admin/campaign-links">Campaign links</a>
        </div>
      </details>"""
    return f"""<a class="admin-skip-link" href="#main-content">Skip to content</a><header class="admin-topbar"><div class="admin-topbar-inner">
      <div class="admin-header-zone admin-header-left">{_admin_brand(show_badge=False)}<span class="admin-badge">Admin area</span><a class="admin-website-link" href="https://terento.app/" target="_blank" rel="noopener noreferrer" aria-label="Open Terento website in a new tab">Website {_admin_icon('external')}</a></div>
      <button id="admin-menu-toggle" class="secondary-button" type="button" aria-controls="admin-menu-panel" aria-expanded="false" hidden>Menu</button>
      <div id="admin-menu-panel"><nav class="admin-section-nav" aria-label="Admin sections"><div class="admin-nav-group" role="group" aria-label="Primary"><a{overview_class} href="/admin">Dashboard</a><a{evidence_class} href="/admin/installations">Installations</a><a{devices_class} href="/admin/devices">Devices</a><a{map_statistics_class} href="/admin/map-statistics">Maps</a><a{providers_class} href="/admin/providers">Providers</a><a{system_health_class} href="/admin/system-health">Health</a></div>{tools_menu}</nav>
      <nav class="admin-nav" aria-label="Admin navigation"><label class="timezone-control"><span class="sr-only">Time zone</span><select id="admin-timezone" aria-label="Time zone" title="Time zone"><option value="browser">Automatic (browser)</option><option value="UTC">UTC</option><option value="Europe/Vilnius">Europe/Vilnius</option><option value="Europe/London">Europe/London</option><option value="Europe/Berlin">Europe/Berlin</option><option value="America/New_York">America/New_York</option><option value="America/Los_Angeles">America/Los_Angeles</option><option value="Asia/Tokyo">Asia/Tokyo</select></label><a class="admin-user{account_class}" href="/admin/account" aria-label="Account settings for {username}">{username}</a>
      <a class="admin-mobile-website" href="https://terento.app/" target="_blank" rel="noopener noreferrer">Website {_admin_icon('external')}</a><form method="post" action="/admin/logout"><input type="hidden" name="csrf_token" value="{html.escape(csrf_token)}"><button class="link-button" type="submit">Sign out</button></form></nav></div>
    </div></header>"""


def local_test_data_page(
    summary: dict[str, Any], user: dict[str, Any], csrf_token: str,
    *, success: str | None = None, error: str | None = None,
) -> bytes:
    """Authenticated, explicit purge UI for local-only telemetry."""
    diagnostic_event_count = int(summary.get("diagnosticEventCount") or 0)
    map_event_count = int(summary.get("mapEventCount") or 0)
    operation_count = int(summary.get("operationCount") or 0)
    labels = ", ".join(
        html.escape(str(label)) for label in summary.get("releaseLabels", [])
    ) or "None"
    activity_rows = ''.join(
        f"<tr><td>{html.escape(str(row.get('stream') or '—'))}</td>"
        f"<td><code>{html.escape(str(row.get('release_label') or '—'))}</code></td>"
        f"<td class='column-status'>{html.escape(str(row.get('outcome') or '—'))}</td>"
        f"<td class='column-number'>{int(row.get('event_count') or 0)}</td>"
        f"<td class='column-date'>{_timestamp_markup(row.get('last_occurred_at'))}</td></tr>"
        for row in summary.get('activity', [])
    ) or "<tr><td colspan='5'>No local test events recorded.</td></tr>"
    support_section = ""
    if "supportReports" in summary:
        # Local support reports appear only here (SUPPORT_REPORT_CONTRACT.md).
        from .support_report_admin import support_report_table
        local_reports = summary.get("supportReports")
        if not isinstance(local_reports, dict) or local_reports.get("available") is False:
            support_section = _unavailable_card("Support reports", "test-data-support-reports")
        else:
            rows = list(local_reports.get("rows") or [])
            total = _optional_nonnegative_int(local_reports.get("totalCount")) or 0
            support_section = _section_card(
                "Support reports",
                _metric_row([_metric_tile("Local reports", total, scope="now")],
                            label="Local support reports")
                + (support_report_table(rows, caption="Local test support reports, newest first, up to 50")
                   if rows else _empty_state("empty", "No local test support reports.")),
                card_id="test-data-support-reports", css="test-data-card",
            )
    content = f"""
      {_admin_header(user, csrf_token, active='test-data')}
      <main id="main-content" class="dashboard test-data-page" aria-labelledby="test-data-title">
        <div class="heading-row">
          <div>

            <h1 id="test-data-title">Test data</h1>

          </div>
        </div>
        {_success(success)}{_error(error)}
        <section class="provider-card test-data-card" aria-labelledby="local-telemetry-title">
          <div class="section-heading">
            <div>

              <h2 id="local-telemetry-title">Purgeable local telemetry</h2>
            </div>
          </div>
          <section class="admin-kpi-grid test-data-metrics" aria-label="Local test telemetry summary">
            <article><span>Diagnostic events</span><strong>{diagnostic_event_count}</strong></article>
            <article><span>Map events</span><strong>{map_event_count}</strong></article>
            <article><span>Distinct operations</span><strong>{operation_count}</strong></article>
          </section>
          <p class="test-data-release-labels">Release labels <code>{labels}</code></p>
          <p class="table-help">Local builds end in <code>-local</code> and are stored with <code>is_local_test=true</code>. Public beta and release-candidate builds use a public release label and <code>is_local_test=false</code>. These test events never contribute to user dashboards or public compatibility counts.</p>
          <div class="table-wrap"><table class="admin-table"><caption class="test-data-activity-caption">Latest local activity · up to 50 release/outcome groups</caption><thead><tr><th scope="col">Stream</th><th scope="col">Release</th><th scope="col" class="column-status">Result</th><th scope="col" class="column-number">Events</th><th scope="col" class="column-date">Last activity</th></tr></thead><tbody>{activity_rows}</tbody></table></div>
          <div class="test-data-danger-zone">
            <div>

              <h3>Delete test data</h3>
              <p class="table-help">This removes only server-classified local test telemetry and local test support reports.</p>
            </div>
            <form method="post" action="/admin/test-data/purge" class="admin-danger-form">
              <input type="hidden" name="csrf_token" value="{html.escape(csrf_token, quote=True)}">
              <label>Type <code>DELETE_LOCAL_TEST_DATA</code> to confirm
                <input name="confirmation" required autocomplete="off" pattern="DELETE_LOCAL_TEST_DATA" placeholder="DELETE_LOCAL_TEST_DATA" spellcheck="false">
              </label>
              <button type="submit" class="danger-button">Delete local test data</button>
            </form>
          </div>
        </section>
        {support_section}
      </main>
    """
    return _layout("Test data", content, sections={"testData": summary})


def setup_page(*, error: str | None = None) -> bytes:
    return _layout(
        "Create admin account",
        """
        <main class="auth-card" aria-labelledby="auth-title">
          {brand}

          <h1 id="auth-title">Create admin account</h1>

          {error}
          <form method="post" action="/admin/setup">
            <label>Username<input name="username" autocomplete="username" required minlength="3" maxlength="64"></label>
            <label>Password<input type="password" name="password" autocomplete="new-password" required minlength="14"></label>
            <label>Confirm password<input type="password" name="password_confirmation" autocomplete="new-password" required minlength="14"></label>
            <label>Deployment secret<input type="password" name="bootstrap_secret" autocomplete="one-time-code" required></label>
            <button type="submit">Create account</button>
          </form>
        </main>
        """.format(error=_error(error), brand=_admin_brand()),
    )


def login_page(*, error: str | None = None) -> bytes:
    return _layout(
        "Admin sign in",
        """
        <main class="auth-card" aria-labelledby="auth-title">
          {brand}

          <h1 id="auth-title">Sign in</h1>

          {error}
          <form method="post" action="/admin/login">
            <label>Username<input name="username" autocomplete="username" required></label>
            <label>Password<input type="password" name="password" autocomplete="current-password" required></label>
            <button type="submit">Sign in</button>
          </form>
        </main>
        """.format(error=_error(error), brand=_admin_brand()),
    )


def _diagnostic_error_reason(results: list[dict[str, Any]], *, resolved: bool = False) -> str:
    """Return a concise primary reason while keeping raw codes in Details."""
    for result in results:
        reason = normalize_failure_reason(result.get("error_category"))
        if reason != "unknown":
            return failure_reason_label(reason)
    for result in results:
        stage = str(result.get("failure_stage") or "").strip()
        if stage and stage.casefold() not in {"unknown", "none"}:
            return re.sub(r"[_-]+", " ", stage).strip().title() + " failed"
    if resolved:
        return "No normalized reason"
    return "Installation error"


def _overview_missing_diagnostic_item(
    event: dict[str, Any], csrf_token: str = "", *, return_to: str = "",
) -> str:
    href = html.escape(_overview_map_event_href(event), quote=True)
    context = html.escape(_overview_map_event_context(event))
    event_id = str(event.get("event_id") or event.get("eventId") or "").strip()
    try:
        event_id = str(UUID(event_id))
    except (ValueError, AttributeError):
        event_id = ""
    dismiss = ""
    if event_id:
        return_field = (
            f"<input type='hidden' name='return_to' value='{html.escape(return_to, quote=True)}'>"
            if return_to else ""
        )
        dismiss = (
            "<form method='post' action='/admin/review/missing-diagnostics/dismiss' "
            "class='admin-async-action overview-review-dismiss-form'>"
            f"<input type='hidden' name='csrf_token' value='{html.escape(csrf_token, quote=True)}'>"
            f"<input type='hidden' name='event_id' value='{html.escape(event_id, quote=True)}'>{return_field}"
            "<button type='submit' class='overview-dismiss-button' "
            f"aria-label='Dismiss review item' title='Dismiss review item'>{_admin_icon('close')}</button>"
            "</form>"
        )
    return (
        "<li class='overview-attention-item overview-attention-failed'>"
        f"{_status_pill('danger', 'Install failed')}"
        f"<div><strong>{context}</strong>"
        "<small>No device report · not counted in Failed · "
        f"{_timestamp_markup(event.get('occurred_at'))}</small></div>"
        f"<div class='overview-attention-actions'><a class='overview-detail-link' href='{href}'>Inspect&nbsp;{_admin_icon('arrow-right')}</a>{dismiss}</div></li>"
    )


_MAP_ACTIVITY_STATES = {
    "DOWNLOAD_STARTED": ("Download started · Outcome not received", "started", "info"),
    "DOWNLOAD_PROCESSING": ("Checking / unpacking · Outcome not received", "started", "info"),
    "DOWNLOAD_CANCELLED": ("Download cancelled", "unknown", "neutral"),
    "DOWNLOAD_INTERRUPTED": ("Download interrupted", "unknown", "warning"),
    # One vocabulary with the charts and tiles (Successful / Failed /
    # Blocked before writing).
    "DOWNLOAD_SUCCEEDED": ("Download successful", "succeeded", "success"),
    "DOWNLOAD_FAILED": ("Download failed", "failed", "error"),
    "INSTALL_SUCCEEDED": ("Install successful", "succeeded", "success"),
    "INSTALL_FAILED": ("Install failed", "failed", "error"),
    "MAP_UPDATE_SUCCEEDED": ("Update successful", "succeeded", "success"),
    "MAP_UPDATE_FAILED": ("Update failed", "failed", "error"),
    "MAP_UPDATE_NOT_STARTED": ("Update blocked before writing", "unknown", "warning"),
}


def _overview_map_event_label(event: dict[str, Any]) -> tuple[str, str]:
    if event.get("event_type") == "DOWNLOAD_STARTED" and event.get("has_recorded_outcome"):
        return "Download started · Outcome recorded", "started"
    if (
        event.get("event_type") in {"DOWNLOAD_STARTED", "DOWNLOAD_PROCESSING"}
        and event.get("is_stale")
    ):
        return (
            "Download started · Outcome missing"
            if event.get("event_type") == "DOWNLOAD_STARTED"
            else "Checking / unpacking · Outcome missing",
            "stale",
        )
    return _MAP_ACTIVITY_STATES.get(str(event.get("event_type") or "").upper(),
                                    ("Map activity", "unknown", "neutral"))[:2]


def _admin_event_outcome_label(value: Any) -> str:
    """Keep a non-terminal UNKNOWN outcome neutral in admin presentation."""
    normalized = str(value or "").strip().upper()
    if normalized == "UNKNOWN":
        return "—"
    return "Successful" if normalized == "SUCCEEDED" else normalized.title() if normalized else "—"


_ADMIN_REGION_DISPLAY_NAMES = {
    "SVN": "Slovenia", "SI": "Slovenia", "POL": "Poland",
    "CHE": "Switzerland", "DEU": "Germany", "AUT": "Austria",
    "FRA": "France", "ITA": "Italy", "ESP": "Spain",
    "PRT": "Portugal", "CZE": "Czechia", "SVK": "Slovakia",
    "HRV": "Croatia", "HUN": "Hungary", "ROU": "Romania",
    "BGR": "Bulgaria", "BEL": "Belgium", "NLD": "Netherlands",
    "DNK": "Denmark", "SWE": "Sweden", "NOR": "Norway",
    "FIN": "Finland", "EST": "Estonia", "GBR": "United Kingdom",
    "IRL": "Ireland", "GRC": "Greece", "LUX": "Luxembourg",
    "AND": "Andorra",
    "ANDORRA": "Andorra",
    "AT": "Austria",
    "CAPEVERDE": "Cape Verde",
    "CH": "Switzerland",
    "CENTRALAFRICANREPUBLIC": "Central African Republic",
    "DE": "Germany",
    "EE": "Estonia",
    "FAROEISLANDS": "Faroe Islands",
    "FI": "Finland",
    "FR": "France",
    "GB": "United Kingdom",
    "IT": "Italy",
    "LT": "Lithuania",
    "LTU": "Lithuania",
    "LVA": "Latvia",
    "LV": "Latvia",
    "NO": "Norway",
    "PL": "Poland",
    "REPUBLICOFLATVIA": "Latvia",
    "REPUBLICOFLITHUANIA": "Lithuania",
    "PRINCIPALITYOFANDORRA": "Andorra",
    "ES": "Spain",
    "SWITZERLAND": "Switzerland",
    "SUISSE": "Switzerland",
    "US": "United States",
    "USA": "United States",
    "UNITEDSTATES": "United States",
    "CZECHIA": "Czechia",
    "CZECHREPUBLIC": "Czechia",
    "SE": "Sweden",
    "UA": "Ukraine",
}

# MapRando keeps reviewed provider-region identities separately from the
# human-readable package names. Keep that vocabulary available for admin
# fallback paths without changing the stored catalog IDs.
_ADMIN_PROVIDER_REGION_DISPLAY_NAMES = {
    re.sub(r"[^A-Za-z0-9]+", "", slug).upper(): name
    for slug, name in MAPRANDO_REGION_DISPLAY_NAMES.items()
}

# OpenTopoMap publishes broad North American regions rather than state
# packages. These hints make labels and country-map links clear; they do not
# change the world map's country-level aggregation.
_ADMIN_REGION_PARENT_COUNTRIES = {
    "CANADAEAST": "Canada",
    "CANADAWEST": "Canada",
    "USMIDWEST": "United States",
    "USNORTHEAST": "United States",
    "USPACIFIC": "United States",
    "USSOUTH": "United States",
    "USWEST": "United States",
}

_ADMIN_REGION_IDENTITY_ALIASES = {
    "SI": "SLOVENIA", "SVN": "SLOVENIA",
    "PL": "POLAND", "POL": "POLAND",
    "CH": "SWITZERLAND", "CHE": "SWITZERLAND",
    "SWISSCONFEDERATION": "SWITZERLAND",
    "SUISSE": "SWITZERLAND",
    "US": "UNITEDSTATES", "USA": "UNITEDSTATES",
    "UNITEDSTATES": "UNITEDSTATES",
    "CZ": "CZECHIA", "CZE": "CZECHIA",
    "CZECHIA": "CZECHIA", "CZECHREPUBLIC": "CZECHIA",
    "REPUBLIQUETCHEQUE": "CZECHIA",
    "DE": "GERMANY", "DEU": "GERMANY",
    "AND": "ANDORRA",
    "ANDORRA": "ANDORRA",
    "PRINCIPALITYOFANDORRA": "ANDORRA",
    "LT": "LITHUANIA",
    "LTU": "LITHUANIA",
    "LITHUANIA": "LITHUANIA",
    "REPUBLICOFLITHUANIA": "LITHUANIA",
}


def _admin_region_token(value: Any) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "", str(value or "")).upper()


def _admin_country_alias_data() -> tuple[dict[str, str], dict[str, str]]:
    """Build country aliases without collapsing provider subregions.

    The world-map alias table knows many country spellings, while MapRando's
    reviewed geography table identifies which provider slugs are whole-country
    regions. Combine only those sources; broad map aliases such as Balearics
    must remain region-specific in the Regions statistics.
    """
    identities_by_country: dict[str, str] = {}
    displays_by_identity: dict[str, str] = {}

    # Preserve established admin identities where the existing display table
    # already names an ISO-2/ISO-3 country code.
    for alias, display in _ADMIN_REGION_DISPLAY_NAMES.items():
        token = _admin_region_token(alias)
        map_country = WORLD_MAP_COUNTRY_ALIASES.get(token)
        if len(token) not in {2, 3} or not map_country:
            continue
        country_code = _admin_region_token(map_country)
        identity = _admin_region_token(display)
        if country_code and identity and identity != "UNKNOWN":
            identities_by_country.setdefault(country_code, identity)
            displays_by_identity.setdefault(identity, display)

    # MapRando supplies the provider-native spellings (for example
    # BELGIQUE) and explicitly marks whole-country regions. Its display name
    # also gives the preferred human-readable label for other providers' IDs.
    for slug, (country_codes, region_kind) in REGION_GEOGRAPHY.items():
        if region_kind != "country" or len(country_codes) != 1:
            continue
        country_code = _admin_region_token(country_codes[0])
        display = str(MAPRANDO_REGION_DISPLAY_NAMES.get(slug) or "").strip()
        if not country_code or not display:
            continue
        identity = identities_by_country.setdefault(
            country_code, _admin_region_token(display),
        )
        displays_by_identity.setdefault(identity, display)

    aliases: dict[str, str] = {}

    # Add reviewed MapRando country slugs and their English labels.
    for slug, (country_codes, region_kind) in REGION_GEOGRAPHY.items():
        if region_kind != "country" or len(country_codes) != 1:
            continue
        country_code = _admin_region_token(country_codes[0])
        identity = identities_by_country.get(country_code)
        if not identity:
            continue
        display = str(MAPRANDO_REGION_DISPLAY_NAMES.get(slug) or "").strip()
        for alias in (slug, display, country_code):
            token = _admin_region_token(alias)
            if token:
                aliases.setdefault(token, identity)

    # Add ISO-3 aliases (BEL, CHE, CZE, …) and only the short country aliases
    # from the world-map table. Do not import its region-to-country aliases.
    for alias, map_country in WORLD_MAP_COUNTRY_ALIASES.items():
        token = _admin_region_token(alias)
        if len(token) not in {2, 3}:
            continue
        identity = identities_by_country.get(_admin_region_token(map_country))
        if identity:
            aliases.setdefault(token, identity)

    for token, identity in aliases.items():
        _ADMIN_REGION_IDENTITY_ALIASES.setdefault(token, identity)
        display = displays_by_identity.get(identity)
        if display:
            _ADMIN_REGION_DISPLAY_NAMES.setdefault(token, display)
    return aliases, displays_by_identity


_ADMIN_COUNTRY_IDENTITY_ALIASES, _ADMIN_COUNTRY_DISPLAY_NAMES = _admin_country_alias_data()


def _admin_region_identity(
    canonical_region_id: Any, country: Any = None, region: Any = None,
) -> str:
    """Return one cross-provider admin geography key from existing metadata."""
    canonical_token = _admin_region_token(canonical_region_id)
    if canonical_token:
        return _ADMIN_REGION_IDENTITY_ALIASES.get(
            canonical_token, canonical_token,
        )
    # A country is a fallback, not a region identity: Azores and Madeira
    # must never collapse into whichever Portuguese region appears first.
    region_token = _admin_region_token(region)
    if region_token:
        return _ADMIN_REGION_IDENTITY_ALIASES.get(region_token, region_token)
    country_identity = _admin_region_token(_admin_map_display_name(country)) if country else ""
    if country_identity and country_identity != "UNKNOWN":
        return _ADMIN_REGION_IDENTITY_ALIASES.get(
            country_identity, country_identity,
        )
    region_identity = _admin_region_token(region)
    return _ADMIN_REGION_IDENTITY_ALIASES.get(
        region_identity, region_identity or "UNKNOWN",
    )


def _admin_map_display_name(*values: Any) -> str:
    """Return one human-readable admin label without changing stored IDs."""
    for value in values:
        raw = str(value or "").strip()
        if not raw:
            continue
        candidate = re.sub(r"^(?:OpenTopoMap|Freizeitkarte)\s+", "", raw, flags=re.IGNORECASE).strip()
        key = re.sub(r"[^A-Za-z0-9]+", "", candidate).upper()
        if key in _ADMIN_REGION_DISPLAY_NAMES:
            return _ADMIN_REGION_DISPLAY_NAMES[key]
        if key in _ADMIN_PROVIDER_REGION_DISPLAY_NAMES:
            return _ADMIN_PROVIDER_REGION_DISPLAY_NAMES[key]
        display_candidate = re.sub(r"_+", " ", candidate)
        display_candidate = " ".join(display_candidate.split())
        display_candidate = re.sub(
            r"^(?:Federal\s+)?Republic\s+of\s+|^(?:Kingdom|Principality|State)\s+of\s+|^Grand\s+Duchy\s+of\s+|^Region\s+",
            "",
            display_candidate,
            flags=re.IGNORECASE,
        ).strip()
        display_candidate = re.sub(r"\s+-\s+", " – ", display_candidate)
        if candidate.isupper() or re.fullmatch(r"[A-Z][A-Z0-9_-]+", candidate):
            return display_candidate.title()
        return display_candidate or "—"
    return "—"


def _admin_region_display_name(
    canonical_region_id: Any = None,
    country: Any = None,
    region: Any = None,
    map_package_name: Any = None,
) -> str:
    """Return a readable region label, adding a known parent country."""
    region_name = _admin_map_display_name(
        map_package_name, region, canonical_region_id, country,
    )
    if region_name == "—":
        return "—"

    parent_token = ""
    for value in (country, canonical_region_id, region):
        token = re.sub(r"[^A-Za-z0-9]+", "", str(value or "")).upper()
        if token in _ADMIN_REGION_PARENT_COUNTRIES:
            parent_token = _ADMIN_REGION_PARENT_COUNTRIES[token]
            break
    country_name = _admin_map_display_name(parent_token or country)
    if country_name == "—" or region_name.casefold() == country_name.casefold():
        return region_name

    region_identity = _admin_region_identity(canonical_region_id, country, region)
    country_identity = _admin_region_identity(None, parent_token or country, None)
    if region_identity == country_identity:
        return region_name
    return f"{region_name} – {country_name}"


def _overview_map_event_context(event: dict[str, Any]) -> str:
    if event.get("provider_id") == "custom":
        return "Custom .img"
    display_name = _admin_map_display_name(
        event.get("display_name")
        or event.get("map_package_name")
        or event.get("map_package_id")
        or event.get("region")
        or "Map",
    )
    region = (
        _admin_region_display_name(
            event.get("canonical_region_id"),
            event.get("region_country"),
            event.get("region"),
            event.get("map_package_name"),
        )
        if event.get("region") or event.get("map_package_name")
        else ""
    )
    provider = str(event.get("provider_name") or "").strip()
    parts = [region] if region and display_name.casefold() in region.casefold() else [display_name]
    if region and parts[0] != region and region.casefold() != display_name.casefold():
        parts.append(region)
    if provider:
        parts.append(provider)
    return " · ".join(parts)


def _overview_activity_device(event: dict[str, Any]) -> str:
    device_id = str(event.get("canonical_device_model_id") or "").strip()
    model = str(event.get("model") or "").strip()
    if not device_id or not model:
        return ""
    variant = _normalise_variant(event.get("variant")) if event.get("variant") else ""
    if variant == "Historical":
        variant = ""
    label = model if not variant or variant in model else f"{model} · {variant}"
    href = _device_detail_url(device_id, origin="overview")
    return (
        f"<a class='overview-activity-device' href='{html.escape(href, quote=True)}'>"
        f"{html.escape(label)}</a>"
    )


def _overview_map_event_href(event: dict[str, Any]) -> str:
    if event.get("provider_id") == "custom":
        return "/admin/installations"
    parameters = {
        "eventType": str(event.get("event_type") or ""),
        "provider": str(event.get("provider_id") or ""),
        "map": str(event.get("map_package_id") or ""),
        "region": str(event.get("region") or ""),
        "eventId": str(event.get("event_id") or event.get("eventId") or ""),
    }
    return "/admin/map-statistics?" + urlencode({key: value for key, value in parameters.items() if value})


def _download_history_icon(event_type: str) -> str:
    """Original Font Awesome Free 7.3.1 assets; historical phases stay static."""
    icons = {
        'DOWNLOAD_STARTED': '<svg class="download-phase-icon fa-solid fa-hourglass-start" aria-hidden="true" focusable="false" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 384 512"><!--! Font Awesome Free 7.3.1 by @fontawesome - https://fontawesome.com License - https://fontawesome.com/license/free (Icons: CC BY 4.0, Fonts: SIL OFL 1.1, Code: MIT License) Copyright 2026 Fonticons, Inc. --><path fill="currentColor" d="M32 0C14.3 0 0 14.3 0 32S14.3 64 32 64l0 11c0 42.4 16.9 83.1 46.9 113.1l67.9 67.9-67.9 67.9C48.9 353.9 32 394.6 32 437l0 11c-17.7 0-32 14.3-32 32s14.3 32 32 32l320 0c17.7 0 32-14.3 32-32s-14.3-32-32-32l0-11c0-42.4-16.9-83.1-46.9-113.1l-67.9-67.9 67.9-67.9c30-30 46.9-70.7 46.9-113.1l0-11c17.7 0 32-14.3 32-32S369.7 0 352 0L32 0zM288 437l0 11-192 0 0-11c0-25.5 10.1-49.9 28.1-67.9l67.9-67.9 67.9 67.9c18 18 28.1 42.4 28.1 67.9z"/></svg>',
        'DOWNLOAD_PROCESSING': '<svg class="download-phase-icon fa-solid fa-spinner" aria-hidden="true" focusable="false" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512"><!--! Font Awesome Free 7.3.1 by @fontawesome - https://fontawesome.com License - https://fontawesome.com/license/free (Icons: CC BY 4.0, Fonts: SIL OFL 1.1, Code: MIT License) Copyright 2026 Fonticons, Inc. --><path fill="currentColor" d="M208 48a48 48 0 1 1 96 0 48 48 0 1 1 -96 0zm0 416a48 48 0 1 1 96 0 48 48 0 1 1 -96 0zM48 208a48 48 0 1 1 0 96 48 48 0 1 1 0-96zm368 48a48 48 0 1 1 96 0 48 48 0 1 1 -96 0zM75 369.1A48 48 0 1 1 142.9 437 48 48 0 1 1 75 369.1zM75 75A48 48 0 1 1 142.9 142.9 48 48 0 1 1 75 75zM437 369.1A48 48 0 1 1 369.1 437 48 48 0 1 1 437 369.1z"/></svg>',
        'DOWNLOAD_SUCCEEDED': '<svg class="download-phase-icon fa-solid fa-hourglass-end" aria-hidden="true" focusable="false" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 384 512"><!--! Font Awesome Free 7.3.1 by @fontawesome - https://fontawesome.com License - https://fontawesome.com/license/free (Icons: CC BY 4.0, Fonts: SIL OFL 1.1, Code: MIT License) Copyright 2026 Fonticons, Inc. --><path fill="currentColor" d="M32 0C14.3 0 0 14.3 0 32S14.3 64 32 64l0 11c0 42.4 16.9 83.1 46.9 113.1l67.9 67.9-67.9 67.9C48.9 353.9 32 394.6 32 437l0 11c-17.7 0-32 14.3-32 32s14.3 32 32 32l320 0c17.7 0 32-14.3 32-32s-14.3-32-32-32l0-11c0-42.4-16.9-83.1-46.9-113.1l-67.9-67.9 67.9-67.9c30-30 46.9-70.7 46.9-113.1l0-11c17.7 0 32-14.3 32-32S369.7 0 352 0L32 0zM96 75l0-11 192 0 0 11c0 25.5-10.1 49.9-28.1 67.9l-67.9 67.9-67.9-67.9C106.1 124.9 96 100.4 96 75z"/></svg>',
    }
    extra_icons = {'circle-xmark': '<svg class="download-phase-icon fa-solid fa-circle-xmark" aria-hidden="true" focusable="false" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512"><!--! Font Awesome Free 7.3.1 by @fontawesome - https://fontawesome.com License - https://fontawesome.com/license/free (Icons: CC BY 4.0, Fonts: SIL OFL 1.1, Code: MIT License) Copyright 2026 Fonticons, Inc. --><path fill="currentColor" fill="currentColor" d="M256 512a256 256 0 1 0 0-512 256 256 0 1 0 0 512zM167 167c9.4-9.4 24.6-9.4 33.9 0l55 55 55-55c9.4-9.4 24.6-9.4 33.9 0s9.4 24.6 0 33.9l-55 55 55 55c9.4 9.4 9.4 24.6 0 33.9s-24.6 9.4-33.9 0l-55-55-55 55c-9.4 9.4-24.6 9.4-33.9 0s-9.4-24.6 0-33.9l55-55-55-55c-9.4-9.4-9.4-24.6 0-33.9z"/></svg>', 'ban': '<svg class="download-phase-icon fa-solid fa-ban" aria-hidden="true" focusable="false" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512"><!--! Font Awesome Free 7.3.1 by @fontawesome - https://fontawesome.com License - https://fontawesome.com/license/free (Icons: CC BY 4.0, Fonts: SIL OFL 1.1, Code: MIT License) Copyright 2026 Fonticons, Inc. --><path fill="currentColor" fill="currentColor" d="M367.2 412.5L99.5 144.8c-22.4 31.4-35.5 69.8-35.5 111.2 0 106 86 192 192 192 41.5 0 79.9-13.1 111.2-35.5zm45.3-45.3c22.4-31.4 35.5-69.8 35.5-111.2 0-106-86-192-192-192-41.5 0-79.9 13.1-111.2 35.5L412.5 367.2zM0 256a256 256 0 1 1 512 0 256 256 0 1 1 -512 0z"/></svg>', 'triangle-exclamation': '<svg class="download-phase-icon fa-solid fa-triangle-exclamation" aria-hidden="true" focusable="false" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512"><!--! Font Awesome Free 7.3.1 by @fontawesome - https://fontawesome.com License - https://fontawesome.com/license/free (Icons: CC BY 4.0, Fonts: SIL OFL 1.1, Code: MIT License) Copyright 2026 Fonticons, Inc. --><path fill="currentColor" fill="currentColor" d="M256 0c14.7 0 28.2 8.1 35.2 21l216 400c6.7 12.4 6.4 27.4-.8 39.5S486.1 480 472 480L40 480c-14.1 0-27.2-7.4-34.4-19.5s-7.5-27.1-.8-39.5l216-400c7-12.9 20.5-21 35.2-21zm0 352a32 32 0 1 0 0 64 32 32 0 1 0 0-64zm0-192c-18.2 0-32.7 15.5-31.4 33.7l7.4 104c.9 12.5 11.4 22.3 23.9 22.3 12.6 0 23-9.7 23.9-22.3l7.4-104c1.3-18.2-13.1-33.7-31.4-33.7z"/></svg>', 'circle-check': '<svg class="download-phase-icon fa-solid fa-circle-check" aria-hidden="true" focusable="false" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512"><!--! Font Awesome Free 7.3.1 by @fontawesome - https://fontawesome.com License - https://fontawesome.com/license/free (Icons: CC BY 4.0, Fonts: SIL OFL 1.1, Code: MIT License) Copyright 2026 Fonticons, Inc. --><path fill="currentColor" fill="currentColor" d="M256 512a256 256 0 1 1 0-512 256 256 0 1 1 0 512zM374 145.7c-10.7-7.8-25.7-5.4-33.5 5.3L221.1 315.2 169 263.1c-9.4-9.4-24.6-9.4-33.9 0s-9.4 24.6 0 33.9l72 72c5 5 11.8 7.5 18.8 7s13.4-4.1 17.5-9.8L379.3 179.2c7.8-10.7 5.4-25.7-5.3-33.5z"/></svg>', 'circle-info': '<svg class="download-phase-icon fa-solid fa-circle-info" aria-hidden="true" focusable="false" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512"><!--! Font Awesome Free 7.3.1 by @fontawesome - https://fontawesome.com License - https://fontawesome.com/license/free (Icons: CC BY 4.0, Fonts: SIL OFL 1.1, Code: MIT License) Copyright 2026 Fonticons, Inc. --><path fill="currentColor" fill="currentColor" d="M256 512a256 256 0 1 0 0-512 256 256 0 1 0 0 512zM224 160a32 32 0 1 1 64 0 32 32 0 1 1 -64 0zm-8 64l48 0c13.3 0 24 10.7 24 24l0 88 8 0c13.3 0 24 10.7 24 24s-10.7 24-24 24l-80 0c-13.3 0-24-10.7-24-24s10.7-24 24-24l24 0 0-64-24 0c-13.3 0-24-10.7-24-24s10.7-24 24-24z"/></svg>'}
    if event_type in {"MAP_UPDATE_SUCCEEDED", "MAP_UPDATE_FAILED"}:
        return '<svg class="download-phase-icon fa-solid fa-arrows-rotate" aria-hidden="true" focusable="false" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512"><path fill="currentColor" d="M105 203c8 8 21 8 29 0l51-51 51 51c8 8 8 21 0 29s-21 8-29 0l-15-15v59c0 35 29 64 64 64 18 0 35-8 47-20 9-9 23-9 32-1s9 23 1 32c-21 22-49 36-80 36-62 0-112-50-112-112v-59l-51 51c-8 8-21 8-29 0s-8-21 0-29l40-40zm302 106c-8-8-21-8-29 0l-51 51-51-51c-8-8-8-21 0-29s21-8 29 0l15 15v-59c0-35-29-64-64-64-18 0-35 8-47 20-9 9-23 9-32 1s-9-23-1-32c21-22 49-36 80-36 62 0 112 50 112 112v59l51-51c8-8 21-8 29 0s8 21 0 29l-40 40z"/></svg>'
    names = {"DOWNLOAD_FAILED": "circle-xmark", "DOWNLOAD_CANCELLED": "ban", "DOWNLOAD_INTERRUPTED": "triangle-exclamation", "INSTALL_SUCCEEDED": "circle-check", "INSTALL_FAILED": "circle-xmark"}
    return icons.get(event_type) or extra_icons[names.get(event_type, "circle-info")]


def _overview_map_activity_row(event: dict[str, Any]) -> str:
    label, state = _overview_map_event_label(event)
    event_type = str(event.get("event_type") or "")
    tone = _MAP_ACTIVITY_STATES.get(event_type.upper(), ("Map activity", "unknown", "neutral"))[2]
    if state == "stale":
        tone = "neutral"
    status_markup = _download_history_icon(event_type) + html.escape(label)
    if event_type == 'MAP_UPDATE_NOT_STARTED' and event.get('diagnostic_report_id'):
        status_markup += f" <a href='/admin/update-diagnostics?diagnosticId={quote(str(event['diagnostic_report_id']), safe='')}'>View details</a>"
    if event_type == 'MAP_UPDATE_FAILED' and event.get('event_id'):
        status_markup += f" <a href='/admin/update-diagnostics?eventId={quote(str(event['event_id']),safe='')}'>View failure</a>"
    component = {"main": "Main map", "contours": "Contours"}.get(event.get("component_kind"), "")
    context = html.escape(_overview_map_event_context(event)) + (' · ' + component if component else '')
    device = _overview_activity_device(event)
    if device:
        context += " · " + device
    if event_type == 'MAP_UPDATE_NOT_STARTED' and event.get('reason_summary'):
        context += ' · ' + html.escape(str(event['reason_summary']))
    lifecycle = event.get("lifecycle") or []
    if len(lifecycle) > 1:
        started = next((_parse_timestamp(item.get("at")) for item in lifecycle
                        if item.get("type") == "DOWNLOAD_STARTED"), None)
        finished = next((_parse_timestamp(item.get("at")) for item in lifecycle
                         if item.get("type") in {"DOWNLOAD_SUCCEEDED", "DOWNLOAD_FAILED",
                                                 "DOWNLOAD_CANCELLED", "DOWNLOAD_INTERRUPTED"}), None)
        entries = []
        for item in lifecycle:
            phase = str(item.get("type") or "")
            timing = _timestamp_markup(item.get("at"))
            if phase == "DOWNLOAD_PROCESSING" and started is not None and finished is not None and finished >= started:
                seconds = int((finished - started).total_seconds())
                hours, remainder = divmod(seconds, 3600)
                minutes, seconds = divmod(remainder, 60)
                duration = " ".join(part for part in (
                    f"{hours}h" if hours else "", f"{minutes}m" if minutes else "",
                    f"{seconds}s" if seconds or not (hours or minutes) else "") if part)
                timing = (f"<span class='download-elapsed' title='Total time from download start to finish'>"
                          f"{duration}</span>")
            elif phase == "DOWNLOAD_PROCESSING":
                timing = "<span title='Start or finish time unavailable'>—</span>"
            entries.append("<li>" + _download_history_icon(phase)
                           + html.escape(phase.removeprefix("DOWNLOAD_").replace("_", " ").title())
                           + " · " + timing + "</li>")
        return (
            f"<li class='overview-activity-item overview-activity-{state} map-activity-row map-activity-{tone}'>"
            "<details class='download-history'><summary>"
            f"<span class='overview-activity-label'>{status_markup}</span>"
            f"{_timestamp_markup(event.get('occurred_at'))}"
            f"<span class='download-context'>{context}</span>"
            "</summary><ol class='download-timeline' aria-label='Download start, total duration and finish'>"
            + "".join(entries) + "</ol></details></li>"
        )
    return (
        f"<li class='overview-activity-item overview-activity-{state} map-activity-row map-activity-{tone}'>"
        f"<span class='map-activity-copy'><span class='overview-activity-label'>{status_markup}</span>"
        f"<span class='activity-context'>{context}</span></span>"
        f"{_timestamp_markup(event.get('occurred_at'))}</li>"
    )


def _admin_app_version_label(value: Any, build: Any = None) -> str:
    release = str(value or "—").strip() or "—"
    if release != "—":
        match = re.search(r"\b((?:beta|rc)\.\d+)(?:\s*[-·( ]\s*(RC))?\b", release, re.IGNORECASE)
        if match:
            release = match.group(1).lower() + (" RC" if match.group(2) else "")
    if build is not None and str(build).strip():
        release += f" · build {str(build).strip()}"
    return release


def _overview_chart_bucket_label(
    value: Any, bucket: str, time_zone: str = "UTC",
) -> str:
    parsed = _parse_timestamp(value)
    if parsed is None:
        return str(value or "—")
    try:
        parsed = parsed.astimezone(ZoneInfo(time_zone))
    except (ZoneInfoNotFoundError, ValueError):
        parsed = parsed.astimezone(timezone.utc)
    if bucket == "hour":
        return parsed.strftime("%H:00")
    if bucket == "month":
        return parsed.strftime("%b %Y")
    if bucket == "week":
        return parsed.strftime("%d %b")
    return parsed.strftime("%d %b")


# Minimum drawn height of a non-zero stacked segment, in chart units: about
# 3 CSS px at the narrowest supported card width (desktop 720-unit chart at
# ~0.63 scale, compact 360-unit chart at ~0.9 scale).
_CHART_MIN_SEGMENT = 5.0
_CHART_MIN_SEGMENT_COMPACT = 4.0


def _overview_stacked_segments(
    counts: tuple[int | None, ...], center: float, bar_width: float,
    baseline: float, plot_height: float, scale_maximum: float,
    *, minimum: float = _CHART_MIN_SEGMENT,
) -> dict[int, tuple[float, float, float, float]]:
    """Return one shared x/width and cumulative y geometry for each segment.

    The bar keeps its true height (``plot_height * total / scale``). A tiny
    non-zero segment is drawn at least ``minimum`` tall; the extra height is
    taken proportionally from the larger segments of the same bar, so the bar
    total and the axis scale stay truthful. Only when the true bar is shorter
    than ``minimum`` per non-zero segment does the bar grow to exactly that
    floor. Exact values remain in each bucket's label and value strip.
    """
    present = [(index, count) for index, count in enumerate(counts) if count is not None and count > 0]
    if not present:
        return {}
    total = sum(count for _, count in present)
    bar_height = max(plot_height * total / scale_maximum, minimum * len(present))
    heights = {index: bar_height * count / total for index, count in present}
    lifted: set[int] = set()
    while True:
        small = [index for index, height in heights.items() if index not in lifted and height < minimum]
        if not small:
            break
        lifted.update(small)
        free = [(index, count) for index, count in present if index not in lifted]
        free_total = sum(count for _, count in free)
        remaining = bar_height - minimum * len(lifted)
        for index in lifted:
            heights[index] = minimum
        for index, count in free:
            heights[index] = remaining * count / free_total if free_total else minimum
    x = center - bar_width / 2
    y = baseline
    segments: dict[int, tuple[float, float, float, float]] = {}
    for index, _ in present:
        y -= heights[index]
        segments[index] = (x, bar_width, y, heights[index])
    return segments


def _chart_value_attributes(date: str, values: list[tuple[str, str, int | None]], total: int | None) -> str:
    """Data for the tap/focus value strip: bucket date, every series and total."""
    payload = {"date": date, "total": total, "values": [list(item) for item in values]}
    return f" data-chart-values='{html.escape(json.dumps(payload, ensure_ascii=False), quote=True)}'"


def _chart_value_strip() -> str:
    """Small live strip under a chart; empty (and hidden) until the shared
    chart-values script fills it for a tapped or focused bucket."""
    return "<p class='overview-chart-values admin-legend' data-chart-values-strip aria-live='polite'></p>"


def _chart_axis_labels(
    positions: list[float], texts: list[str], *, font_size: float, chart_width: float,
    gap: float = 6.0,
) -> list[tuple[int, str]]:
    """X-axis labels without overlap: every bucket when the labels fit, else
    every second (or the smallest regular step that fits), always keeping the
    most recent bucket. Returns ``(index, text-anchor)`` pairs."""
    count = len(texts)
    if not count:
        return []
    widths = [len(text) * font_size * 0.6 for text in texts]
    spacing = min((b - a for a, b in zip(positions, positions[1:]) if b > a), default=chart_width)
    widest = max(widths)
    step = 1
    while step < count and step * spacing < widest + gap:
        step += 1
    placed: list[tuple[int, str, float, float]] = []
    for index in range(count - 1, -1, -step):
        x, width = positions[index], widths[index]
        anchor, start, end = "middle", x - width / 2, x + width / 2
        if start < 0:
            anchor, start, end = "start", x, x + width
        if end > chart_width:
            anchor, start, end = "end", x - width, x
        if placed and end + gap > placed[-1][2]:
            continue  # an edge-anchored label would touch its neighbour
        placed.append((index, anchor, start, end))
    return [(index, anchor) for index, anchor, _, _ in reversed(placed)]


_INSTALL_CHART_SERIES = (
    # (css name, label, payload field). Order is the stacking order from the
    # baseline and the legend order (owner colour decision 2026-10-05).
    ("success", "Install successful", "success_count"),
    ("custom", "Custom .img install", "custom_count"),
    ("failed", "Install failed", "failed_count"),
    ("update", "Update successful", "map_update_success_count"),
    ("update-failed", "Update failed", "map_update_failed_count"),
)
_LEGEND_COUNTED_SERIES = frozenset({"custom"})
_DOWNLOAD_CHART_SERIES = (
    ("download-success", "Download successful", "download_success_count"),
    ("download-failed", "Download failed", "download_failed_count"),
)


_LEGEND_NAME_ONLY = object()  # legend entry that names its series without a count


def _chart_legend(items: list[tuple[str, str, Any]], *, label: str) -> str:
    """One legend for every chart: swatch, noun and, when it adds information
    not already in a tile, the period count (``_LEGEND_NAME_ONLY`` omits it)."""
    entries = "".join(
        f"<li><i class='overview-chart-{html.escape(name, quote=True)}' aria-hidden='true'></i>"
        f"<span>{html.escape(text)}</span>"
        + ("" if count is _LEGEND_NAME_ONLY else
           f"<strong>{count:,}</strong>" if count is not None else "<strong>—</strong>")
        + "</li>"
        for name, text, count in items
    )
    return (
        f"<ul class='overview-chart-legend admin-legend' aria-label='{html.escape(label, quote=True)}'>"
        f"{entries}</ul>"
    )


def _overview_trend_chart(
    trend: list[dict[str, Any]], bucket: str, time_zone: str = "UTC",
    *, metric: str = "installs", has_activity: bool = False,
    chart_id: str = "", counted: frozenset[str] = _LEGEND_COUNTED_SERIES, _compact: bool = False,
) -> str:
    if not trend:
        if has_activity:
            return _empty_state("unavailable", "Trend data is unavailable for this period.", css="overview-empty-state")
        empty_label = "downloads" if metric == "downloads" else "map installations"
        return f"<p class='overview-empty-state admin-empty' data-state='empty'>No {empty_label} in this period.</p>"
    series = _DOWNLOAD_CHART_SERIES if metric == "downloads" else _INSTALL_CHART_SERIES
    chart_label = "Map download trend" if metric == "downloads" else "Map installation and update trend"
    chart_key = re.sub(r"[^a-z0-9-]", "-", (chart_id or metric).lower()) + ("-mobile" if _compact else "-desktop")
    pattern_id = f"update-failed-{chart_key}"
    values = []
    for item in trend:
        values.append(tuple(max(0, int(item.get(field) or 0)) for _, _, field in series))
    # Each bucket is one stacked bar.  Scale against the bucket total so the
    # full bar represents every event, while the segments retain their
    # canonical outcome composition.
    maximum = max((sum(counts) for counts in values), default=1) or 1
    tick_step = max(1, math.ceil(maximum / 4))
    scale_maximum = tick_step * 4
    chart_width, chart_height = (360, 220) if _compact else (720, 260)
    left, right, top, bottom = 42, 12, 20, 38
    plot_height = chart_height - top - bottom
    plot_width = chart_width - left - right
    slot = plot_width / max(len(values), 1)
    bar_width = min(slot * 0.72, 86 if not _compact else 64)
    grid = []
    for amount in range(0, scale_maximum + 1, tick_step):
        tick_y = top + plot_height * (1 - amount / scale_maximum)
        grid.append(
            f"<line class='overview-chart-grid' x1='{left}' x2='{chart_width-right}' "
            f"y1='{tick_y:.1f}' y2='{tick_y:.1f}'/>"
            f"<text class='overview-chart-axis-label' x='{left-8}' y='{tick_y+4:.1f}' "
            f"text-anchor='end'>{amount}</text>"
        )
    bars: list[str] = []
    labels: list[str] = []
    x_positions = [left + (index + 0.5) * slot for index in range(len(values))]
    for index, (counts, item) in enumerate(zip(values, trend)):
        center = x_positions[index]
        bucket_label = _overview_chart_bucket_label(item.get("bucket"), bucket, time_zone)
        series_titles: list[str] = []
        group_bars: list[str] = []
        stack_total = sum(counts)
        segments = _overview_stacked_segments(
            counts, center, bar_width, top + plot_height, plot_height, scale_maximum,
            minimum=_CHART_MIN_SEGMENT_COMPACT if _compact else _CHART_MIN_SEGMENT,
        )
        for series_index, (count, (name, label, field)) in enumerate(zip(counts, series)):
            timestamps = list(item.get(f"{field.removesuffix('_count')}_times") or [])
            title = f"{label}: {count} · {bucket_label} · {time_zone}"
            if timestamps:
                title = f"{label}: {count} · " + ", ".join(str(value) for value in timestamps) + f" · {time_zone}"
            series_titles.append(f"{label}: {count}")
            geometry = segments.get(series_index)
            if geometry is None:
                continue
            segment_x, segment_width, y, height = geometry
            style = f" style='fill:url(#{pattern_id})'" if name == "update-failed" else ""
            group_bars.append(
                f"<rect class='overview-chart-{name}'{style} data-stack-index='{series_index}' "
                f"data-stack-total='{stack_total}' x='{segment_x:.1f}' y='{y:.2f}' "
                f"width='{segment_width:.1f}' height='{height:.2f}' aria-hidden='true'>"
                f"<title>{html.escape(title)}</title></rect>"
            )
        group_title = f"{bucket_label} · Total: {stack_total}"
        if series_titles:
            group_title += " · " + " · ".join(series_titles)
        group_title += f" · {time_zone}"
        # One keyboard stop per bucket; the segments are presentational.
        strip_data = _chart_value_attributes(
            bucket_label, [(name, label, count) for count, (name, label, _) in zip(counts, series)], stack_total,
        )
        bars.append(
            f"<g class='overview-chart-group' role='img' tabindex='0'{strip_data} aria-label='{html.escape(group_title, quote=True)}'>"
            f"<title>{html.escape(group_title)}</title>{''.join(group_bars)}</g>"
        )
    axis_texts = [_overview_chart_bucket_label(item.get("bucket"), bucket, time_zone) for item in trend]
    for index, anchor in _chart_axis_labels(
        x_positions, axis_texts, font_size=13 if _compact else 11, chart_width=chart_width,
    ):
        labels.append(
            f"<text x='{x_positions[index]:.1f}' y='{chart_height - 8}' text-anchor='{anchor}' aria-hidden='true'>"
            f"{html.escape(axis_texts[index])}</text>"
        )
    svg = (
        f"<svg class='overview-trend-chart overview-trend-{'mobile' if _compact else 'desktop'}' viewBox='0 0 {chart_width} {chart_height}' role='group' aria-label='{chart_label}'>"
        f"<defs><pattern id='{pattern_id}' width='7' height='7' patternUnits='userSpaceOnUse' patternTransform='rotate(45)'><rect width='7' height='7' fill='var(--danger)'/><path d='M0 0V7' stroke='var(--surface)' stroke-width='3'/></pattern></defs>{''.join(grid)}{''.join(bars)}{''.join(labels)}</svg>"
    )
    if _compact:
        return svg
    # Tiles or card headers carry the period totals; the legend names the
    # series and counts only the ``counted`` series (none on the Dashboard).
    totals = [sum(counts[index] for counts in values) for index in range(len(series))]
    legend = _chart_legend(
        [(name, label, total if name in counted else _LEGEND_NAME_ONLY)
         for (name, label, _), total in zip(series, totals)],
        label=f"{chart_label} legend",
    )
    return (
        "<div class='overview-chart-wrap'>"
        + svg
        + _overview_trend_chart(
            trend, bucket, time_zone, metric=metric,
            has_activity=has_activity, chart_id=chart_id, _compact=True,
        )
        + _chart_value_strip() + legend + "</div>"
    )


def _overview_download_marker(
    item: dict[str, Any], center: float, top: float, plot_height: float,
    chart_bucket: str, time_zone: str, *, _compact: bool = False,
) -> str:
    markers = [marker for marker in item.get("release_markers") or [] if isinstance(marker, dict)]
    observed_label = _overview_chart_bucket_label(
        item.get("observed_at") or item.get("bucket"), chart_bucket, time_zone,
    )
    parts: list[str] = []
    labels: list[str] = []
    if markers:
        if len(markers) == 1:
            marker = markers[0]
            label = str(marker.get("label") or marker.get("tag") or "release")
            visible = "New release" if _compact else f"New release · {label}"
            detail = f"New release: {label}"
        else:
            visible = f"New releases · {len(markers)}"
            detail = "New releases: " + ", ".join(
                str(marker.get("label") or marker.get("tag") or "release")
                for marker in markers
            )
        labels.append(detail)
        title = f"{detail} · observed {observed_label} · {time_zone}"
        parts.append(
            f"<g class='overview-chart-download-release' role='img' aria-label='{html.escape(title, quote=True)}'>"
            f"<line x1='{center + 1.5:.1f}' x2='{center + 1.5:.1f}' y1='{top:.1f}' y2='{top + plot_height:.1f}'/>"
            f"<text x='{center:.1f}' y='{top - (24 if item.get('contains_discontinuity') or item.get('state') == 'discontinuity' else 8):.1f}' text-anchor='middle'>{html.escape(visible)}</text>"
            f"<title>{html.escape(title)}</title></g>"
        )
    if item.get("contains_discontinuity") or item.get("state") == "discontinuity":
        reason = {
            "counter_decrease": "download counter decreased",
            "population_change": "asset or release population changed",
        }.get(str(item.get("discontinuity_reason") or ""), "the interval cannot be compared")
        visible = "Data boundary"
        retained = int(item.get("discontinuity_count") or 0)
        retained_note = f" · {retained} data boundary retained" if retained == 1 else (
            f" · {retained} data boundaries retained" if retained > 1 else ""
        )
        title = f"Data boundary: {reason} · observed {observed_label} · interval unknown{retained_note} · {time_zone}"
        labels.append(title.split(" · observed", 1)[0])
        parts.append(
            f"<g class='overview-chart-download-boundary' role='img' aria-label='{html.escape(title, quote=True)}'>"
            f"<line x1='{center - 1.5:.1f}' x2='{center - 1.5:.1f}' y1='{top:.1f}' y2='{top + plot_height:.1f}'/>"
            f"<text x='{center:.1f}' y='{top - 8:.1f}' text-anchor='middle'>{html.escape(visible)}</text>"
            f"<title>{html.escape(title)}</title></g>"
        )
    if not parts:
        return ""
    return (
        f"<g class='overview-chart-download-marker' tabindex='0' role='group' "
        f"aria-label='{html.escape(' · '.join(labels), quote=True)}'>"
        f"<title>{html.escape(' · '.join(labels))}</title>{''.join(parts)}</g>"
    )


def _sum_known(values: list[tuple[int | None, ...]], index: int) -> int | None:
    known = [row[index] for row in values if row[index] is not None]
    return sum(known) if known else None


def _overview_downloads_chart(
    downloads: dict[str, Any], time_zone: str = "UTC", *, period: str = "24h",
    _compact: bool = False,
) -> str:
    trend = [item for item in downloads.get("trend") or [] if isinstance(item, dict)]
    if not trend:
        return "<p class='overview-empty-state'>No GitHub download data yet.</p>"
    chart_bucket = str(downloads.get("bucket") or {
        "today": "hour", "24h": "hour", "7d": "day", "30d": "day", "all": "month",
    }.get(period, "hour"))
    if chart_bucket not in {"hour", "day", "week", "month"}:
        chart_bucket = "hour"
    period_label = {
        "today": "today",
        "24h": "the last 24 hours",
        "7d": "the last 7 days",
        "30d": "the last 30 days",
        "all": "all time",
    }.get(period, "the selected period")
    values = []
    for item in trend:
        counts = []
        for key in ("dmg_count", "zip_count"):
            value = item.get(key)
            try:
                counts.append(int(value) if value is not None and int(value) >= 0 else None)
            except (TypeError, ValueError):
                counts.append(None)
        values.append(tuple(counts))
    maximum = max((sum(value for value in series if value is not None) for series in values), default=1) or 1
    scale_maximum = max(4, math.ceil(maximum * 1.2))
    chart_width, chart_height = (360, 220) if _compact else (720, 260)
    left, top, bottom = 38, 42, 34
    plot_height = chart_height - top - bottom
    slot = (chart_width - left - 12) / max(len(values), 1)
    tick_step = max(1, (scale_maximum + 3) // 4)
    grid = []
    for amount in sorted(set(range(0, scale_maximum + 1, tick_step)) | {scale_maximum}):
        tick_y = top + plot_height * (1 - amount / scale_maximum)
        grid.append(
            f"<line class='overview-chart-grid' x1='{left}' x2='{chart_width-12}' "
            f"y1='{tick_y:.1f}' y2='{tick_y:.1f}'/>"
            f"<text class='overview-chart-axis-label' x='{left-8}' y='{tick_y+4:.1f}' "
            f"text-anchor='end'>{amount}</text>"
        )
    bars: list[str] = []
    labels: list[str] = []
    plot_width = chart_width - left - 12
    position_times = [
        _parse_timestamp(item.get("observed_at") or item.get("bucket"))
        for item in trend
    ]
    valid_position_times = [value for value in position_times if value is not None]
    position_start = min(valid_position_times) if valid_position_times else None
    position_end = max(valid_position_times) if valid_position_times else None
    position_span = (
        position_end - position_start
        if position_start is not None and position_end is not None
        else None
    )
    edge_inset = min(slot / 2, plot_width / 2)
    timeline_width = max(0.0, plot_width - edge_inset * 2)

    def position_center(index: int) -> float:
        """Use ordered hourly slots; exact observation time stays metadata."""
        if chart_bucket == "hour":
            return left + (index + 0.5) * slot
        observed_at = position_times[index]
        if position_start is None or position_span is None or observed_at is None:
            return left + (index + 0.5) * slot
        if position_span.total_seconds() <= 0:
            return left + plot_width / 2
        fraction = (observed_at - position_start).total_seconds() / position_span.total_seconds()
        return left + edge_inset + max(0.0, min(1.0, fraction)) * timeline_width

    series = (
        (".dmg downloads", "overview-chart-download-dmg"),
        (".zip downloads", "overview-chart-download-zip"),
    )
    for index, (counts, item) in enumerate(zip(values, trend)):
        center = position_center(index)
        bar_width = min(44, slot * 0.58)
        x = center - bar_width / 2
        y = top + plot_height
        clip_id = f"overview-download-bar-clip-{'mobile-' if _compact else ''}{index}"
        observed_at = item.get("observed_at") or item.get("bucket")
        legacy_note = (
            " · legacy observed counter delta · population comparability unconfirmed"
            if item.get("legacy")
            or item.get("confidence") == "legacy"
            or item.get("population_comparability") == "unconfirmed"
            else ""
        )
        partial_note = " · partial known total" if item.get("partial") else ""
        stack_total = sum(count for count in counts if count is not None)
        zero_titles = []
        for (label, _), count in zip(series, counts):
            if count != 0:
                continue
            zero_description = (
                "known zero increase in partial bucket ending"
                if item.get("partial")
                else "observed zero increase between checks ending"
            )
            zero_title = f"{label}: 0 · {zero_description} {_overview_chart_bucket_label(observed_at, chart_bucket, time_zone)} · {time_zone}"
            zero_titles.append(zero_title + legacy_note + partial_note)
        group_title = (
            f"{_overview_chart_bucket_label(item.get('bucket'), chart_bucket, time_zone)}"
            f" · Observed increase: {stack_total}"
            + "".join(
                f" · {label}: {count}" for (label, _), count in zip(series, counts) if count
            )
        )
        if zero_titles:
            interval_title = "Download interval: " + " · ".join(zero_titles)
            group_title += " · " + interval_title
        # One keyboard stop per bucket; the segments are presentational.
        strip_data = _chart_value_attributes(
            _overview_chart_bucket_label(item.get("bucket"), chart_bucket, time_zone),
            [(css_class.removeprefix("overview-chart-"), label.removesuffix(" downloads"), count)
             for (label, css_class), count in zip(series, counts)],
            stack_total if all(count is not None for count in counts) else None,
        )
        group_accessibility = (
            " class='overview-chart-group' role='img' tabindex='0'" + strip_data + " aria-label='"
            + html.escape(group_title, quote=True)
            + "'"
        )
        group_title_markup = f"<title>{html.escape(group_title)}</title>"
        bars.append(
            f"<defs><clipPath id='{clip_id}'><rect x='{x:.1f}' "
            f"y='{top:.1f}' width='{bar_width:.1f}' height='{plot_height:.1f}' rx='3'></rect></clipPath></defs>"
            f"<g clip-path='url(#{clip_id})'{group_accessibility}>{group_title_markup}"
        )
        segments = _overview_stacked_segments(
            tuple(counts), center, bar_width, top + plot_height, plot_height, scale_maximum,
            minimum=_CHART_MIN_SEGMENT_COMPACT if _compact else _CHART_MIN_SEGMENT,
        )
        for series_index, ((label, css_class), count) in enumerate(zip(series, counts)):
            if count is None:
                continue
            geometry = segments.get(series_index)
            if geometry is None:
                continue
            segment_x, segment_width, y, height = geometry
            previous_observed_at = item.get("previous_observed_at")
            if item.get("state") in {"gap", "period_boundary", "partial"} and previous_observed_at is not None:
                interval_start = _overview_chart_bucket_label(previous_observed_at, chart_bucket, time_zone)
                interval_end = _overview_chart_bucket_label(observed_at, chart_bucket, time_zone)
                title = f"{label}: {count} · observed increase across {interval_start}–{interval_end} · {time_zone} · interval uncertain"
            else:
                title = f"{label}: {count} · observed increase ending {_overview_chart_bucket_label(observed_at, chart_bucket, time_zone)} · {time_zone}"
            title += legacy_note + partial_note
            bars.append(
                f"<rect class='{css_class}' data-stack-index='{series_index}' "
                f"data-stack-total='{stack_total}' x='{segment_x:.1f}' y='{y:.2f}' "
                f"width='{segment_width:.1f}' height='{height:.2f}' aria-hidden='true'>"
                f"<title>{html.escape(title)}</title></rect>"
            )
        bars.append("</g>")
        marker = _overview_download_marker(
            item, center, top, plot_height, chart_bucket, time_zone,
            _compact=_compact,
        )
        if marker:
            bars.append(marker)
    centers = [position_center(index) for index in range(len(values))]
    axis_texts = [_overview_chart_bucket_label(item.get("bucket"), chart_bucket, time_zone) for item in trend]
    for index, anchor in _chart_axis_labels(
        centers, axis_texts, font_size=13 if _compact else 11, chart_width=chart_width,
    ):
        labels.append(
            f"<text x='{centers[index]:.1f}' y='{chart_height - 8}' text-anchor='{anchor}'>"
            f"{html.escape(axis_texts[index])}</text>"
        )
    svg = (
        f"<svg class='overview-trend-chart overview-trend-{'mobile' if _compact else 'desktop'}' "
        f"viewBox='0 0 {chart_width} {chart_height}' role='group' "
        f"aria-label='Terento app downloads: observed counter increases between checks over {period_label}'>"
        f"{''.join(grid)}{''.join(bars)}{''.join(labels)}</svg>"
    )
    if _compact:
        return svg
    return (
        "<div class='overview-chart-wrap'>"
        + svg
        + _overview_downloads_chart(downloads, time_zone, period=period, _compact=True)
        + _chart_value_strip()
        + _chart_legend(
            [("download-dmg", ".dmg", _sum_known(values, 0)), ("download-zip", ".zip", _sum_known(values, 1))],
            label="Terento app download legend and period increases",
        )
        + "</div>"
    )


def _overview_period_script() -> str:
    return r"""(() => {
      let loadingKey = '';
      let overviewRequest = 0;
      const activeTimeZone = () => window.TerentoAdminTime?.timeZone?.()
        || Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
      const bind = () => {
        const form = document.querySelector('#overview-period-form');
        const select = document.querySelector('#overview-period');
        if (!form || !select || select.dataset.bound === 'true') return;
        select.dataset.bound = 'true';
        form.addEventListener('submit', (event) => {
          event.preventDefault();
          load(select.value, true, activeTimeZone());
        });
        select.addEventListener('change', () => form.requestSubmit());
      };
      const load = async (period, push, timeZone = activeTimeZone()) => {
        const current = document.querySelector('#main-content');
        const select = document.querySelector('#overview-period');
        const url = new URL('/admin', window.location.origin);
        url.searchParams.set('period', period);
        url.searchParams.set('timeZone', timeZone);
        const requestKey = `${period}\u0000${timeZone}`;
        if (loadingKey === requestKey) return;
        loadingKey = requestKey;
        const requestNumber = ++overviewRequest;
        if (current) current.setAttribute('aria-busy', 'true');
        if (select) select.disabled = true;
        try {
          const response = await fetch(url, {credentials: 'same-origin', headers: {'Accept': 'text/html'}});
          if (!response.ok) throw new Error(`Overview refresh failed (${response.status})`);
          const documentNext = new DOMParser().parseFromString(await response.text(), 'text/html');
          if (requestNumber !== overviewRequest) return;
          const mainNext = documentNext.querySelector('#main-content');
          if (!mainNext) throw new Error('Overview content is unavailable.');
          current?.replaceWith(mainNext);
          window.dispatchEvent(new Event('terento-admin-content-changed'));
          if (push) window.history.pushState({period, timeZone}, '', url);
          else window.history.replaceState({period, timeZone}, '', url);
          window.TerentoAdminTime?.render();
          bind();
        } catch (error) {
          window.location.assign(url);
        } finally {
          if (requestNumber === overviewRequest) loadingKey = '';
        }
      };
      window.addEventListener('popstate', () => {
        const period = new URL(window.location.href).searchParams.get('period') || '24h';
        load(period, false, activeTimeZone());
      });
      const synchronizeTimeZone = () => {
        const url = new URL(window.location.href);
        const period = url.searchParams.get('period') || document.querySelector('#overview-period')?.value || '24h';
        const timeZone = activeTimeZone();
        if (url.searchParams.get('timeZone') !== timeZone) load(period, false, timeZone);
      };
      window.addEventListener('terento-admin-timezone-ready', synchronizeTimeZone);
      window.addEventListener('terento-admin-timezone-change', synchronizeTimeZone);
      bind();
    })();"""


def _provider_problem_state(provider: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    """The single provider-problem definition (Dashboard, Providers and Health).

    Retired and paused providers are deliberate administrator states, not
    problems. An active provider has a problem when its source health is
    Degraded/Failed, its catalog collection failed or is stale/missing, or it
    has current package problems. Unknown package counts stay unknown.
    """
    status = str(provider.get("status") or "ACTIVE").strip().upper()
    if status in {"RETIRED", "PAUSED"}:
        return {"tracked": False, "problem": False, "packagesKnown": True, "reasons": [], "status": "HEALTHY"}
    reasons: list[str] = []
    worst = "HEALTHY"
    health = str(provider.get("health") or "UNKNOWN").strip().upper()
    if health == "DOWN":
        reasons.append("Health failed")
        worst = "FAILED"
    elif health in {"DEGRADED", "WARNING"}:
        reasons.append("Health degraded")
        worst = "WARNING"
    catalog = provider_catalog_health(provider, now=now)
    collection = str(provider.get("lastCollectionStatus") or "UNKNOWN").strip().upper()
    if collection == "FAILED":
        reasons.append("Catalog sync failed")
        worst = "FAILED"
    elif catalog["status"] in {"WARNING", "FAILED", "UNKNOWN"} and (
        "collection" in catalog["reason"].casefold() or "snapshot" in catalog["reason"].casefold()
    ):
        reasons.append("Catalog sync overdue")
        worst = worst if worst == "FAILED" else "WARNING"
    affected = _optional_nonnegative_int(provider.get("affectedPackageCount", provider.get("brokenPackageCount")))
    if affected:
        reasons.append(f"{affected} package {'problem' if affected == 1 else 'problems'}")
        worst = worst if worst == "FAILED" else "WARNING"
    if not reasons and health == "UNKNOWN":
        worst = "UNKNOWN"
    return {
        "tracked": True,
        "problem": bool(reasons),
        "packagesKnown": affected is not None,
        "reasons": reasons,
        "status": worst,
    }


_ATTENTION_ROWS = (
    # (review key, label, href, icon)
    ("installationIssues", "Open problems", "/admin/installations?state=open", "x-circle"),
    ("githubIssuesInProgress", "GitHub issues", "/admin/review/github-issues", "external"),
    ("identityPending", "Identity review", "/admin/review/identity", "question"),
    ("readyToPublish", "Publication review", "/admin/devices?review=publication", "check"),
    ("missingDiagnostics", "Missing reports", "/admin/review/missing-reports", "alert"),
)


def _attention_row(label: str, count: int | None, href: str, icon: str, *, unavailable: bool = False) -> str:
    """Needs attention row: icon, label, count (or —) and an arrow. A measured
    zero has nothing to act on, so it renders no row."""
    if not unavailable and count == 0:
        return ""
    if unavailable or count is None:
        value = "—<span class='sr-only'> unavailable</span>"
        state = "unavailable"
        aria = f"{label}: unavailable"
    else:
        value = f"{count:,}"
        state = "active"
        aria = f"{label}: {count}"
    return (
        f"<li class='overview-attention-row' data-state='{state}'>"
        f"<a href='{html.escape(href, quote=True)}' aria-label='{html.escape(aria, quote=True)}'>"
        f"{_admin_icon(icon)}<span class='overview-attention-label'>{html.escape(label)}</span>"
        f"<strong>{value}</strong>{_admin_icon('arrow-right')}</a></li>"
    )


# First run breakdown groups: (title, stage, outcome labels). Labels are per
# stage because outcome codes repeat across stages (UPDATE_REQUIRED, AUTHORIZATION).
_FUNNEL_CONNECT_LABELS = {
    "TIMEOUT_NO_USB": "No watch plugged in", "TIMEOUT_USB_PRESENT": "Didn't get ready",
    "NOT_MTP_MODE": "Not in file-transfer mode", "BUSY": "Watch in use by another app",
    "MULTIPLE_DEVICES": "Several Garmins", "DISCONNECTED": "Disconnected after connecting",
    "FAILED": "Stopped responding",
}
_FUNNEL_GROUPS: tuple[tuple[str, str, dict[str, str]], ...] = (
    ("Connection problems", "DEVICE_CONNECT", _FUNNEL_CONNECT_LABELS),
    ("Authorization", "AUTHORIZATION", {
        "APPROVED": "Approved", "PENDING": "Pending", "OUT_OF_SCOPE": "Out of scope",
        "UNKNOWN_MODEL": "Unknown model", "AMBIGUOUS": "Ambiguous",
        "CATALOG_UNAVAILABLE": "Catalog unavailable", "UPDATE_REQUIRED": "Update required",
    }),
    ("Catalog", "CATALOG", {
        "REMOTE": "Loaded", "REMOTE_PARTIAL": "Partly loaded", "BUNDLED_FALLBACK": "Built-in copy",
        "UPDATE_REQUIRED": "App update required",
    }),
    ("Install blocked", "INSTALL_BLOCKED", {
        "AUTHORIZATION": "Not allowed for this watch", "DEVICE_STORAGE": "Watch storage full",
        "MAC_STORAGE": "Mac storage problem", "CATALOG_UNVERIFIED": "Map not verified",
        "LOCAL_CAPABILITY": "Watch not identified", "OTHER": "Other",
    }),
)
# One short visible meaning per non-obvious outcome (stage, outcome).
_FUNNEL_HINTS = {
    ("AUTHORIZATION", "PENDING"): "Model not in the catalog, or its Maps value is unknown or mixed",
    ("AUTHORIZATION", "OUT_OF_SCOPE"): "The catalog says this model has no maps",
    ("AUTHORIZATION", "UNKNOWN_MODEL"): "The watch reported no usable model name",
    ("AUTHORIZATION", "AMBIGUOUS"): "The watch reported conflicting model names",
    ("AUTHORIZATION", "CATALOG_UNAVAILABLE"): "The policy check failed (network or server); nothing was written",
    ("AUTHORIZATION", "UPDATE_REQUIRED"): "This app version is too old for the current policy",
    ("CATALOG", "REMOTE_PARTIAL"): "Some map packages were left out as invalid",
    ("CATALOG", "BUNDLED_FALLBACK"): "The server catalog did not load; the app used its bundled list",
    ("CATALOG", "UPDATE_REQUIRED"): "This app version is too old for the current catalog",
    ("INSTALL_BLOCKED", "AUTHORIZATION"): "Install was refused because the watch was not approved",
}
_FUNNEL_NOTES = {
    "Connection problems": "Every session, including those that connected later.",
    "Why not connected": "Sessions that never connected; one can show several signals.",
}
# What the current policy says about a waiting model (diagnostic only).
_FUNNEL_MODEL_STATUS = {
    "NOT_IN_CATALOG": "Not in catalog",
    "MAPS_UNKNOWN": "Maps unknown",
    "MIXED": "Variants differ",
    "NO_MAPS": "No maps",
    "WITHDRAWN": "Withdrawn",
    "APPROVED_NOW": "Approved now",
    "UNAVAILABLE": "Catalog status unavailable",
}
_FUNNEL_PREVIOUS_LABELS = {
    "today": "yesterday", "24h": "previous 24 h", "7d": "previous 7 days", "30d": "previous 30 days",
}


def _funnel_display(funnel: dict[str, Any]) -> dict[str, Any]:
    """Exactly what the First run card shows (also its freshness revision).

    Journey: sessions, sessions that connected and connected sessions whose
    watch was approved, each with the previous period's value. Groups list
    non-zero per-session outcome counts, largest first; a session can appear in
    several rows of one group. Waiting models sit under their outcome row.
    """
    stages = {
        str(stage.get("stage")): {
            str(item.get("outcome")): _optional_nonnegative_int(item.get("sessionCount")) or 0
            for item in stage.get("outcomes") or [] if isinstance(item, dict)
        }
        for stage in funnel.get("stages") or [] if isinstance(stage, dict)
    }
    sessions = _optional_nonnegative_int(funnel.get("sessionCount"))
    if not sessions:
        return {"sessions": sessions}
    connected = stages.get("DEVICE_CONNECT", {}).get("CONNECTED", 0)
    journey = funnel.get("journey") if isinstance(funnel.get("journey"), dict) else {}
    approved = _optional_nonnegative_int(journey.get("approvedSessionCount"))
    previous = funnel.get("previous") if isinstance(funnel.get("previous"), dict) else None
    models: dict[str, list[tuple[str, int, str]]] = {}
    for item in funnel.get("modelsNeedingReview") or []:
        if isinstance(item, dict) and item.get("baseModel"):
            models.setdefault(str(item.get("outcome") or "PENDING"), []).append((
                str(item["baseModel"]),
                _optional_nonnegative_int(item.get("sessionCount")) or 0,
                _FUNNEL_MODEL_STATUS.get(str(item.get("catalogStatus") or ""), ""),
            ))
    groups: list[tuple[str, list[tuple[str, int, str, list[tuple[str, int, str]]]]]] = []
    never = funnel.get("neverConnected") if isinstance(funnel.get("neverConnected"), dict) else None
    never_count = _optional_nonnegative_int(funnel.get("neverConnectedSessionCount"))
    if never is not None and never_count:
        rows = [
            (_FUNNEL_CONNECT_LABELS.get(str(item.get("outcome")), str(item.get("outcome")).replace("_", " ").capitalize()),
             _optional_nonnegative_int(item.get("sessionCount")) or 0, "", [])
            for item in never.get("outcomes") or [] if isinstance(item, dict)
        ]
        silent = _optional_nonnegative_int(never.get("withoutConnectionSignalCount")) or 0
        if silent:
            rows.append(("Closed before any watch signal", silent, "", []))
        groups.append(("Why not connected", sorted(
            [row for row in rows if row[1]], key=lambda row: (-row[1], row[0]))))
    for title, stage, labels in _FUNNEL_GROUPS:
        items = {
            key: value for key, value in stages.get(stage, {}).items()
            if value and not (stage == "DEVICE_CONNECT" and key == "CONNECTED")
        }
        groups.append((title, [
            (labels.get(key, key.replace("_", " ").capitalize()), value,
             _FUNNEL_HINTS.get((stage, key), ""),
             models.pop(key, []) if stage == "AUTHORIZATION" else [])
            for key, value in sorted(items.items(), key=lambda item: (-item[1], item[0]))
        ]))
    trend = [
        (str(item.get("bucket") or ""), _optional_nonnegative_int(item.get("sessionCount")) or 0,
         _optional_nonnegative_int(item.get("connectedSessionCount")) or 0)
        for item in funnel.get("trend") or [] if isinstance(item, dict)
    ]
    return {
        "sessions": sessions,
        "connected": connected,
        "approved": approved,
        "neverConnected": never_count,
        "previous": None if previous is None else {
            key: _optional_nonnegative_int(previous.get(field))
            for key, field in (("sessions", "sessionCount"), ("connected", "connectedSessionCount"),
                               ("approved", "approvedSessionCount"))
        },
        "trend": trend,
        "bucket": str(funnel.get("bucket") or ""),
        "groups": groups,
    }


def _funnel_revision(display: dict[str, Any]) -> dict[str, Any]:
    """Displayed First run values without the zero trend buckets that only move
    with the rolling window."""
    return {**display, "trend": [item for item in display.get("trend") or [] if item[1]]}


def _funnel_share(part: int | None, whole: int | None) -> str:
    if part is None or not whole:
        return ""
    return f"{round(part / whole * 100)}%"


def _funnel_delta(current: int | None, previous: int | None, period: str) -> str:
    """Change against the previous period as text with an arrow (never colour alone)."""
    if current is None or previous is None:
        return ""
    against = _FUNNEL_PREVIOUS_LABELS.get(period, "previous period")
    change = current - previous
    if change == 0:
        text, arrow = f"Same as {against}", "="
    else:
        text, arrow = f"{change:+,} vs {against}", "▲" if change > 0 else "▼"
    return (f"<span class='funnel-step-delta' title='{html.escape(against.capitalize(), quote=True)}: {previous:,}'>"
            f"<span aria-hidden='true'>{arrow}</span> {html.escape(text)}</span>")


def _funnel_journey(display: dict[str, Any], period: str) -> str:
    """Opened app → Watch connected → Install allowed, with shares and drop-offs."""
    sessions, connected, approved = display["sessions"], display["connected"], display["approved"]
    previous = display.get("previous") or {}
    steps = [
        ("Opened app", sessions, "", "sessions"),
        ("Watch connected", connected, _funnel_share(connected, sessions) and
         _funnel_share(connected, sessions) + " of opened", "connected"),
        ("Install allowed", approved, _funnel_share(approved, connected) and
         _funnel_share(approved, connected) + " of connected", "approved"),
    ]
    items = []
    for label, value, share, key in steps:
        width = min(100.0, (value or 0) / sessions * 100) if sessions else 0.0
        value_text = f"{value:,}" if value is not None else "—"
        share_markup = f"<span class='funnel-step-share'>{html.escape(share)}</span>" if share else ""
        items.append(
            f"<li class='funnel-step' data-step='{key}'>"
            f"<span class='funnel-step-label'>{html.escape(label)}</span>"
            f"<strong class='funnel-step-value'>{value_text}</strong>{share_markup}"
            f"<span class='funnel-step-bar' aria-hidden='true'><i style='width:{width:.1f}%'></i></span>"
            f"{_funnel_delta(value, previous.get(key), period)}</li>"
        )
    drops = []
    never = display.get("neverConnected")
    if never:
        drops.append(f"<strong>{never:,}</strong> never connected")
    if approved is not None and connected > approved:
        drops.append(f"<strong>{connected - approved:,}</strong> connected but not allowed")
    drop_markup = (
        "<p class='funnel-dropoff'>" + _admin_icon("arrow-right") + " Lost on the way: " + " · ".join(drops) + "</p>"
        if drops else ""
    )
    return (
        "<ol class='funnel-journey' aria-label='First run journey'>" + "".join(items) + "</ol>" + drop_markup
    )


def _funnel_trend_strip(display: dict[str, Any], time_zone: str) -> str:
    """Sessions per hour or day: connected and never connected stacked; each
    bucket is focusable and names its values."""
    trend = display.get("trend") or []
    if len(trend) < 2:
        return ""
    bucket = display.get("bucket") or "hour"
    peak = max((total for _, total, _ in trend), default=0) or 1
    bars = []
    for stamp, total, connected in trend:
        label = _overview_chart_bucket_label(stamp, bucket, time_zone)
        never = max(0, total - connected)
        description = f"{label}: {total} sessions, {connected} connected, {never} never connected"
        bars.append(
            f"<li tabindex='0' aria-label='{html.escape(description, quote=True)}' title='{html.escape(description, quote=True)}'>"
            f"<span class='funnel-trend-never' style='height:{never / peak * 100:.1f}%'></span>"
            f"<span class='funnel-trend-connected' style='height:{connected / peak * 100:.1f}%'></span></li>"
        )
    first = _overview_chart_bucket_label(trend[0][0], bucket, time_zone)
    last = _overview_chart_bucket_label(trend[-1][0], bucket, time_zone)
    return (
        "<div class='funnel-trend'>"
        "<h3>Sessions over time</h3>"
        f"<ol class='funnel-trend-bars' aria-label='Sessions per {html.escape(bucket)}'>" + "".join(bars) + "</ol>"
        f"<div class='funnel-trend-axis' aria-hidden='true'><span>{html.escape(first)}</span><span>{html.escape(last)}</span></div>"
        "<ul class='funnel-trend-legend admin-legend' aria-label='Sessions over time legend'>"
        "<li><i class='funnel-trend-connected' aria-hidden='true'></i><span>Connected</span></li>"
        "<li><i class='funnel-trend-never' aria-hidden='true'></i><span>Never connected</span></li></ul>"
        "</div>"
    )


def _funnel_card(funnel: dict[str, Any] | None, period: str, time_zone: str = "UTC") -> str:
    """First run: the journey with drop-offs, sessions over time, then why."""
    if not isinstance(funnel, dict) or funnel.get("available") is False or "stages" not in funnel:
        return _unavailable_card("First run", "overview-funnel")
    display = _funnel_display(funnel)
    sessions = display["sessions"]
    if not sessions:
        body = _empty_state("empty", "No first-run sessions in this period.")
    else:
        def bars(title: str, items: list[tuple[str, int, str, list[tuple[str, int, str]]]]) -> str:
            """Label (with an optional meaning and waiting models), a bar scaled
            to the share of the group's population and the count."""
            whole = display["neverConnected"] if title == "Why not connected" else sessions
            noun = "never-connected sessions" if title == "Why not connected" else "sessions"
            rows = []
            for label, value, hint, models in items:
                hint_markup = f"<small class='funnel-hint'>{html.escape(hint)}</small>" if hint else ""
                model_markup = ""
                if models:
                    model_markup = "<ul class='funnel-models' aria-label='" + html.escape(label + " models", quote=True) + "'>" + "".join(
                        f"<li><a href='/admin/devices?{urlencode({'search': model})}'>{html.escape(model)}</a>"
                        + (f"<span class='funnel-model-status'>{html.escape(status)}</span>" if status else "")
                        + f"<strong>{count:,}</strong></li>"
                        for model, count, status in models
                    ) + "</ul>"
                rows.append(
                    f"<li><span class='overview-funnel-label'>{html.escape(label)}{hint_markup}</span>"
                    f"<span class='overview-funnel-bar' aria-hidden='true'><i style='width:{min(100.0, value / (whole or 1) * 100):.1f}%'></i></span>"
                    f"<strong>{value:,}</strong><span class='sr-only'> of {whole:,} {noun}</span>{model_markup}</li>"
                )
            row_markup = "".join(rows) or "<li class='overview-funnel-none'><span class='overview-funnel-label'>—</span></li>"
            note = _FUNNEL_NOTES.get(title) if items else None
            note_markup = f"<p class='overview-funnel-note muted-value'>{html.escape(note)}</p>" if note else ""
            return (
                f"<div class='overview-funnel-group'><h3>{html.escape(title)}</h3>{note_markup}"
                f"<ul class='overview-funnel-bars' aria-label='{html.escape(title, quote=True)}'>{row_markup}</ul></div>"
            )

        body = (
            _funnel_journey(display, period)
            + _funnel_trend_strip(display, time_zone)
            + "<div class='overview-funnel-breakdown'>"
            + "".join(bars(title, items) for title, items in display["groups"])
            + "</div>"
        )
    return _section_card(
        "First run", body, card_id="overview-funnel", scope=period,
        css="overview-panel overview-funnel-panel",
    )


def _card_totals(items: list[tuple[str, str]], *, label: str) -> str:
    """Compact value + noun chips that close a card header (Dashboard totals)."""
    return (
        f"<div class='overview-card-totals' role='group' aria-label='{html.escape(label, quote=True)}'>"
        + "".join(f"<span class='overview-card-total'>{value}<small>{html.escape(noun)}</small></span>"
                  for value, noun in items)
        + "</div>"
    )


def _period_totals(data: dict[str, Any], completed: str, failed: str, rate: str, *, label: str) -> str:
    completed_value = _optional_nonnegative_int(data.get(completed))
    return _card_totals([
        (f"<strong data-stat='{completed}'>{f'{completed_value:,}' if completed_value is not None else '—'}</strong>",
         "Successful"),
        (_admin_error_counter(data.get(failed), data_stat=failed), "Failed"),
        (f"<strong data-stat='{rate}'>{html.escape(_format_rate(data.get(rate)))}</strong>", "Success rate"),
    ], label=label)


def overview_page(
    overview: dict[str, Any], user: dict[str, Any], csrf_token: str,
    *, review_action: str = "", review_event_id: str = "",
) -> bytes:
    data_raw = overview.get("data") if isinstance(overview.get("data"), dict) else {}
    data_available = data_raw.get("available") is not False
    data = data_raw if data_available else {}
    downloads = overview.get("downloads") if isinstance(overview.get("downloads"), dict) else {}
    period = str(overview.get("period") or "24h")
    if period not in ADMIN_PERIODS:
        period = "24h"
    time_zone = str(overview.get("timeZone") or "UTC")
    # Picker order (owner request 2026-10-07): Today, then the rolling periods.
    period_options = "".join(
        f"<option value='{value}'{' selected' if value == period else ''}>{ADMIN_PERIOD_LABELS[value]}</option>"
        for value in ADMIN_PERIODS
    )
    recent = [
        item for item in data.get("recentActivity") or []
        if str(item.get("event_type") or "").upper()
        not in {"DOWNLOAD_STARTED", "DOWNLOAD_PROCESSING"}
    ]
    map_statistics_href = "/admin/map-statistics?" + urlencode({"period": period})

    # --- Needs attention: fixed category rows, explicit unavailable state ----
    review = overview.get("review") if isinstance(overview.get("review"), dict) else user.get("admin_review_summary")
    review = review if isinstance(review, dict) else {}
    review_available = bool(review) and review.get("available") is not False
    attention_rows: list[str] = []
    attention_counts: list[int | None] = []
    for key, label, href, icon in _ATTENTION_ROWS:
        count = _optional_nonnegative_int(review.get(key)) if review_available else None
        # A failed queue query is unavailable, never a smaller fallback number
        # from another definition (ADM-02).
        attention_counts.append(count)
        attention_rows.append(_attention_row(label, count, href, icon, unavailable=count is None))
    # Support reports have their own read model: a failed count is unavailable
    # for this row only, never a fallback number (SUPPORT_REPORT_CONTRACT.md).
    support = overview.get("supportReports")
    support_count = (
        _optional_nonnegative_int(support.get("openCount"))
        if isinstance(support, dict) and support.get("available") is not False else None
    )
    attention_counts.append(support_count)
    attention_rows.append(_attention_row("Support reports", support_count, "/admin/support-reports", "message"))
    # System checks (owner decision 2026-10-06): one row, only when Health has
    # failed or degraded checks, linking to Health with that status filter.
    # The Catalogs check summarises provider problems, which stay on Providers
    # and are not counted here; Maps unknown stays on Devices.
    system = overview.get("system") if isinstance(overview.get("system"), dict) else None
    system_available = isinstance(system, dict) and system.get("available") is not False
    health_cards = _system_health_cards(system)[0] if system_available else []
    system_issues = [
        card for card in health_cards
        if card["status"] in _HEALTH_ISSUE_STATES and card.get("group") != "catalogs"
    ]
    if system_issues:
        system_filter = "FAILED" if any(card["status"] == "FAILED" for card in system_issues) else "WARNING"
        attention_counts.append(len(system_issues))
        attention_rows.append(_attention_row(
            "System checks", len(system_issues), f"/admin/system-health?status={system_filter}", "circle-exclamation",
        ))
    attention_total = (
        sum(attention_counts) if all(value is not None for value in attention_counts) else None
    )
    notice_event_id = ""
    try:
        notice_event_id = str(UUID(str(review_event_id).strip()))
    except (ValueError, AttributeError):
        pass
    review_notice = _missing_report_notice(review_action, notice_event_id, csrf_token, return_to="")
    attention_status = ""
    if not review_available:
        attention_status = _empty_state("unavailable", "Review counts are unavailable.", action=("", "Retry"))
    elif attention_total == 0:
        attention_status = _empty_state("empty", "Nothing to review.")
    attention_section = _section_card(
        "Needs attention",
        review_notice + attention_status
        + ("<ul class='overview-attention-rows'>" + "".join(attention_rows) + "</ul>" if any(attention_rows) else ""),
        card_id="overview-attention", scope="now",
        totals=_card_totals([(_admin_error_counter(attention_total, available=attention_total is not None,
                                                   data_stat="attentionTotal"), "Total")],
                            label="Needs attention total") if review_available else "",
        css="overview-panel overview-attention-panel" + (" overview-attention-empty" if attention_total == 0 else ""),
    )

    # --- Charts with an explicit all-time line -------------------------------
    trend = list(data.get("trend") or [])
    bucket = str(data.get("bucket") or "day")
    if data_available:
        downloads_chart = _section_card(
            "Downloads",
            _overview_trend_chart(
                trend, bucket, time_zone, metric="downloads", chart_id="overview-downloads",
                counted=frozenset(),
                has_activity=bool((data.get("completedDownloadCount") or 0) + (data.get("failedDownloadCount") or 0)),
            ),
            card_id="overview-download-trend", scope=period,
            totals=_period_totals(data, "completedDownloadCount", "failedDownloadCount", "downloadSuccessRate",
                                  label="Downloads in this period"),
            css="overview-panel overview-chart-panel",
        )
        installs_chart = _section_card(
            "Installs",
            _overview_trend_chart(
                trend, bucket, time_zone, chart_id="overview-installs", counted=frozenset(),
                has_activity=bool((data.get("completedInstallCount") or 0) + (data.get("failedInstallCount") or 0) + (data.get("mapUpdateCount") or 0)),
            ),
            card_id="overview-trend", scope=period,
            totals=_period_totals(data, "completedInstallCount", "failedInstallCount", "installSuccessRate",
                                  label="Installs in this period"),
            css="overview-panel overview-chart-panel",
        )
    else:
        downloads_chart = _unavailable_card("Downloads", "overview-download-trend")
        installs_chart = _unavailable_card("Installs", "overview-trend")

    # --- Activity -------------------------------------------------------------
    if not data_available:
        recent_content = _empty_state("unavailable", "Could not load recent activity.", action=("", "Retry"))
    elif not recent:
        recent_content = _empty_state("empty", "No map activity in this period.")
    else:
        recent_content = "<ul class='overview-activity-list'>" + "".join(_overview_map_activity_row(item) for item in recent) + "</ul>"
    activity_section = _section_card(
        "Activity", recent_content, card_id="overview-activity", scope=period,
        action=(map_statistics_href, "View all"), css="overview-panel overview-activity-panel",
    )

    # --- Terento app downloads (GitHub) ---------------------------------------
    downloads_available = downloads.get("available") is not False
    download_has_data = bool(downloads.get("hasData")) and (downloads.get("dmgTotal") is not None or downloads.get("zipTotal") is not None or bool(downloads.get("trend")))
    download_last_update = downloads.get("lastSuccessfulObservedAt", downloads.get("lastObservedAt"))

    def download_total(key: str) -> str:
        value = _optional_nonnegative_int(downloads.get(key))
        return f"{value:,}" if value is not None else "—"

    if not downloads_available:
        downloads_section = _unavailable_card("App downloads", "overview-downloads")
    elif download_has_data:
        downloads_section = _section_card(
            "App downloads",
            # Legend: period increases; one compact All time line: totals.
            f"{_overview_downloads_chart(downloads, time_zone, period=period)}"
            f"<p class='overview-all-time overview-download-all-time'>{_scope_chip('all')}"
            f"<span>.dmg <strong>{download_total('dmgTotal')}</strong> · .zip <strong>{download_total('zipTotal')}</strong></span>"
            f"<span class='overview-chart-note'>Last update {_timestamp_markup(download_last_update) if download_last_update is not None else '—'}</span></p>",
            card_id="overview-downloads", scope=period,
            css="overview-panel overview-download-panel",
        )
    else:
        downloads_section = ""

    funnel_section = _funnel_card(overview.get("funnel"), period, time_zone) if "funnel" in overview else ""
    content = f"""
      {_admin_header(user, csrf_token, active='overview')}
      <main class='dashboard overview-page' id='main-content'>
        <div class='heading-row overview-heading'><div><h1>Dashboard</h1></div><form class='filter-bar overview-period-form' id='overview-period-form' method='get' action='/admin'><label><span class='sr-only'>Time period</span><select id='overview-period' data-admin-dropdown name='period'>{period_options}</select></label></form></div>
        <div class='overview-primary-grid'>{downloads_chart}{installs_chart}</div>
        <div class='overview-composition-grid'>{attention_section}{activity_section}{funnel_section}{downloads_section}</div>
      </main>
      <script nonce="{_ADMIN_NONCE_PLACEHOLDER}">{_overview_period_script()}</script>
    """
    return _layout("Dashboard", content, sections=_overview_revision_sections(
        overview, data, recent, downloads, review if review_available else None, system_issues,
    ))


# Dashboard map-activity fields that the page does not render.
_OVERVIEW_UNSHOWN_ACTIVITY = frozenset({
    "recentActivity", "attention", "missingDiagnosticFailures", "missingDiagnosticFailureCount", "trend",
})


def _overview_revision_sections(
    overview: dict[str, Any], data: dict[str, Any], recent: list[dict[str, Any]],
    downloads: dict[str, Any], review: dict[str, Any] | None, system_issues: list[dict[str, Any]],
) -> dict[str, Any]:
    """Freshness revisions for exactly what the Dashboard renders.

    Request-time values (the First run window bounds), payloads the page does
    not render (compatibility evidence, provider rows, Maps unknown, hidden
    in-progress downloads) and clock-moved zero chart buckets are left out, so
    an unchanged Dashboard never reports new data (docs/admin-behavior-contract.md).
    """
    funnel = overview.get("funnel")
    return {
        "mapActivity": {
            "available": bool(data),
            **{key: value for key, value in data.items() if key not in _OVERVIEW_UNSHOWN_ACTIVITY},
            "trend": active_trend_buckets(data.get("trend")),
            "recentActivity": recent,
        },
        "downloads": downloads,
        "review": {key: review.get(key) for key, *_ in _ATTENTION_ROWS} if review is not None else None,
        "funnel": (
            None if not isinstance(funnel, dict)
            else _funnel_revision(_funnel_display(funnel))
            if funnel.get("available") is not False and "stages" in funnel
            else {"available": False}
        ),
        "supportReports": overview.get("supportReports"),
        "system": [(card["title"], card["status"]) for card in system_issues],
    }


def _missing_report_notice(action: str, event_id: str, csrf_token: str, *, return_to: str) -> str:
    if not event_id or action not in {"dismissed", "reopened"}:
        return ""
    if action == "reopened":
        return "<div class='overview-review-notice' role='status'>Review item reopened.</div>"
    return_field = (
        f"<input type='hidden' name='return_to' value='{html.escape(return_to, quote=True)}'>" if return_to else ""
    )
    return (
        "<div class='overview-review-notice' role='status'>Review item dismissed. "
        "<form method='post' action='/admin/review/missing-diagnostics/undo' "
        "class='admin-async-action'>"
        f"<input type='hidden' name='csrf_token' value='{html.escape(csrf_token, quote=True)}'>"
        f"<input type='hidden' name='event_id' value='{html.escape(event_id, quote=True)}'>{return_field}"
        "<button type='submit' class='link-button'>Undo</button></form></div>"
    )


def missing_reports_page(
    payload: dict[str, Any] | None, user: dict[str, Any], csrf_token: str,
    *, review_action: str = "", review_event_id: str = "",
) -> bytes:
    """Every install failure without a matching device report (ADM-11)."""
    notice_event_id = ""
    try:
        notice_event_id = str(UUID(str(review_event_id).strip()))
    except (ValueError, AttributeError):
        pass
    notice = _missing_report_notice(
        review_action, notice_event_id, csrf_token, return_to="/admin/review/missing-reports",
    )
    if payload is None:
        body = _unavailable_card("Missing reports", "missing-reports")
    else:
        rows = list(payload.get("rows") or [])
        total = _optional_nonnegative_int(payload.get("total")) or 0
        offset = _optional_nonnegative_int(payload.get("offset")) or 0
        limit = _optional_nonnegative_int(payload.get("limit")) or 50
        items = "".join(
            _overview_missing_diagnostic_item(item, csrf_token, return_to="/admin/review/missing-reports")
            for item in rows
        )
        pagination = ""
        if total > limit:
            previous = (
                f"<a class='secondary-button' href='/admin/review/missing-reports?offset={max(0, offset - limit)}'>Previous</a>"
                if offset else ""
            )
            following = (
                f"<a class='secondary-button' href='/admin/review/missing-reports?offset={offset + limit}'>Next</a>"
                if offset + limit < total else ""
            )
            pagination = (
                "<div class='provider-pagination' aria-label='Missing report pages'>"
                f"{previous}<span>{offset + 1}–{min(total, offset + limit)} of {total}</span>{following}</div>"
            )
        list_markup = (
            f"<ul class='overview-attention-list'>{items}</ul>{pagination}" if rows
            else _empty_state("empty", "Nothing to review.")
        )
        body = _metric_row([
            _metric_tile("Missing reports", total, scope="now"),
        ], label="Missing report summary") + _section_card(
            "Reports", list_markup, card_id="missing-report-list", css="overview-attention-panel",
        )
    content = f"""
      {_admin_header(user, csrf_token, active='overview')}
      <main class='dashboard missing-reports-page' id='main-content'>
        <p class='back-link'><a href='/admin'>{_admin_icon('arrow-left')} Dashboard</a></p>
        <div class='heading-row'><div><h1>Missing reports</h1></div></div>
        {notice}{body}
      </main>
      <script nonce="{_ADMIN_NONCE_PLACEHOLDER}">{_diagnostics_script()}</script>
    """
    return _layout("Missing reports", content, sections={"missingReports": payload})


def admin_error_page(
    status: int, message: str, user: dict[str, Any] | None = None, csrf_token: str = "",
) -> bytes:
    """HTML error page for HTML routes, inside the admin chrome when signed in."""
    titles = {400: "Invalid link", 404: "Not found", 503: "Unavailable"}
    title = titles.get(int(status), "Something went wrong")
    header = _admin_header(user, csrf_token, active="") if user else ""
    content = f"""
      {header}
      <main class='dashboard admin-error-page' id='main-content' aria-labelledby='admin-error-title'>
        <div class='heading-row'><div><h1 id='admin-error-title'>{html.escape(title)}</h1></div></div>
        {_section_card('Details', _empty_state('unavailable' if int(status) >= 500 else 'empty', message, action=('', 'Retry') if int(status) >= 500 else ('/admin', 'Dashboard')), card_id='admin-error')}
      </main>
    """
    return _layout(title, content)


def _health_status_badge(status: Any) -> str:
    normalized = str(status or "UNKNOWN").strip().upper()
    labels = {
        "HEALTHY": ("success", "Healthy"), "WARNING": ("warning", "Degraded"),
        "FAILED": ("danger", "Failed"), "UNKNOWN": ("unknown", "No data"),
    }
    if normalized not in labels:
        normalized = "UNKNOWN"
    kind, label = labels[normalized]
    return _status_pill(kind, label, value=normalized)


def _health_run_url(observation: dict[str, Any] | None) -> str:
    """The retained GitHub Actions run URL, only for the Terento repository."""
    url = str((observation or {}).get("source_run_url") or "").strip()
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "github.com"
        or not re.fullmatch(r"/VooZ2/terento/actions/runs/\d+", parsed.path)
        or parsed.query
        or parsed.fragment
    ):
        return ""
    return url


def _health_run_link(observation: dict[str, Any] | None, *, label: str = "GitHub Actions") -> str:
    url = _health_run_url(observation)
    if not url:
        return ""
    return f"<a class='section-link' href='{html.escape(url, quote=True)}' target='_blank' rel='noopener noreferrer'>{html.escape(label)}&nbsp;{_admin_icon('external')}</a>"


_HEALTH_STATUS_RANK = {"FAILED": 0, "WARNING": 1, "UNKNOWN": 2, "HEALTHY": 3}
# Issues lists failing and degraded checks; No data and Healthy checks live in
# the Technical details tabs. Dashboard Needs attention counts the same states.
_HEALTH_ISSUE_STATES = frozenset({"FAILED", "WARNING"})


def _health_checked_markup(checked: Any) -> str:
    """Last checked time, or an explicit not-recorded dash."""
    if _parse_timestamp(checked) is None:
        return "—<span class='sr-only'>Not recorded</span>"
    return _timestamp_markup(checked)


def _latest_timestamp(*values: Any) -> datetime | None:
    parsed = [value for value in (_parse_timestamp(item) for item in values) if value is not None]
    return max(parsed) if parsed else None


def _health_action_markup(card: dict[str, Any]) -> str:
    """Next action: a link when a real target exists, otherwise muted help text."""
    action = str(card.get("action") or "").strip()
    if not action:
        return ""
    href = str(card.get("actionHref") or "")
    if href:
        external = href.startswith("https://")
        return (
            f"<a class='system-health-action section-link' href='{html.escape(href, quote=True)}'"
            + (" target='_blank' rel='noopener noreferrer'" if external else "")
            + f">{html.escape(action)}&nbsp;{_admin_icon('external' if external else 'arrow-right')}</a>"
        )
    return f"<span class='system-health-action'>{html.escape(action)}</span>"


def _health_check_row(card: dict[str, Any], row_id: str, *, issue: bool) -> str:
    """One check as a table row plus its attached, initially hidden Details row.

    Issue rows (the Issues card) show Check, Status, Reason with the next
    action under it, Last checked and a Details control. Group rows (the
    Technical details tabs) show Check, Status, Last checked and Details; a
    non-healthy group row keeps its reason under the name and its next action
    in Details. The Details row is a single full-width cell so the shared table
    sort keeps it attached to its check.
    """
    status = str(card.get("status") or "UNKNOWN").upper()
    title = str(card.get("title") or "")
    reason = str(card.get("reason") or "").strip()
    technical = str(card.get("technical") or "")
    details_id = html.escape(f"{row_id}-details", quote=True)
    detail_parts = []
    if not issue and status != "HEALTHY":
        action = _health_action_markup(card)
        if action:
            detail_parts.append(f"<p class='health-details-action'>{action}</p>")
    if technical.strip():
        detail_parts.append(technical)
    toggle = (
        f"<button type='button' class='health-details-toggle' data-health-details aria-expanded='false' "
        f"aria-controls='{details_id}'>Details<span class='sr-only'> for {html.escape(title)}</span>"
        f"{_admin_icon('chevron-down')}</button>"
        if detail_parts else ""
    )
    attrs = (
        f"data-health-status='{html.escape(status, quote=True)}' "
        f"data-health-name='{html.escape(str(card.get('searchName') or title).casefold(), quote=True)}' "
        f"data-health-group='{html.escape(str(card.get('group') or 'service'), quote=True)}'"
    )
    name_cell = f"<th scope='row' class='health-check-name'><span class='health-check-title'>{html.escape(title)}</span>"
    if not issue and status != "HEALTHY" and reason:
        name_cell += f"<span class='system-health-cause table-secondary'>{html.escape(reason)}</span>"
    cells = [
        name_cell + "</th>",
        f"<td class='column-status' data-sort-value='{_HEALTH_STATUS_RANK.get(status, 2)}'>{_health_status_badge(status)}</td>",
    ]
    if issue:
        cells.append(
            f"<td class='health-check-reason'><span class='system-health-cause'>{html.escape(reason) or '—'}</span>"
            f"{_health_action_markup(card)}</td>"
        )
    cells.append(f"<td class='column-date system-health-when'>{_health_checked_markup(card.get('lastChecked'))}</td>")
    cells.append(f"<td class='health-check-more'>{toggle}</td>")
    row = f"<tr class='system-health-row{' system-health-issue' if issue else ''}' {attrs}>{''.join(cells)}</tr>"
    if detail_parts:
        row += (
            f"<tr class='health-details-row' id='{details_id}' hidden><td colspan='{5 if issue else 4}'>"
            f"<div class='health-details-body system-health-technical'>{''.join(detail_parts)}</div></td></tr>"
        )
    return row


def _health_card_record(
    title: str, status: Any, *, technical: str, reason: str, action: str,
    action_href: str = "", checked: Any = None, group: str = "service", search_name: str = "",
) -> dict[str, Any]:
    normalized_status = str(status or "UNKNOWN").strip().upper()
    if normalized_status not in _HEALTH_STATUS_RANK:
        normalized_status = "UNKNOWN"
    card = {
        "title": title, "status": normalized_status, "reason": reason, "action": action,
        "actionHref": action_href, "lastChecked": checked, "group": group,
        "technical": technical, "searchName": search_name or title,
    }
    slug = re.sub(r"[^a-z0-9]+", "-", title.casefold()).strip("-") or "check"
    card["html"] = _health_check_row(card, f"health-check-{slug}", issue=True)
    return card


def _system_health_card(
    title: str,
    status: Any,
    description: str,
    observation: dict[str, Any] | None = None,
    *,
    reason: str = "",
    action: str = "",
    group: str = "service",
    checked_at: Any = None,
    action_href: str | None = None,
) -> dict[str, Any]:
    """One Health check.

    ``checked_at`` supplies the last-checked time for checks that are not
    backed by a retained observation (the live API and database probes, the
    scheduler heartbeat, issue sync and provider catalogs). An
    observation-backed action links to its workflow run when one is retained.
    """
    checked = checked_at if checked_at is not None else (observation or {}).get("observed_at")
    run_url = _health_run_url(observation)
    href = action_href if action_href is not None else run_url
    technical = ""
    if description.strip() or (run_url and href != run_url):
        technical = (
            f"<div class='system-health-description'>{description}</div>"
            + (_health_run_link(observation) if href != run_url else "")
        )
    return _health_card_record(
        title, status, technical=technical, reason=reason, action=action,
        action_href=href, checked=checked, group=group,
    )


def _health_details(observation: dict[str, Any] | None) -> dict[str, Any]:
    details = (observation or {}).get("details")
    if isinstance(details, dict):
        return details
    if isinstance(details, str):
        try:
            decoded = json.loads(details)
        except json.JSONDecodeError:
            return {}
        return decoded if isinstance(decoded, dict) else {}
    return {}


def _safe_indexnow_preview(details: dict[str, Any]) -> list[str]:
    raw = details.get("url_preview")
    if not isinstance(raw, str):
        return []
    urls = []
    for value in raw.splitlines():
        parsed = urlsplit(value)
        if (
            parsed.scheme == "https"
            and parsed.netloc == "terento.app"
            and parsed.path.startswith("/")
            and (parsed.path == "/" or parsed.path.endswith("/"))
            and not parsed.query
            and not parsed.fragment
        ):
            urls.append(value)
    return urls[:10]


def _indexnow_count(value: Any) -> int | None:
    return _optional_nonnegative_int(value)


def _indexnow_card(
    indexnow: dict[str, Any] | None,
    site: dict[str, Any] | None,
    *,
    now: datetime,
) -> dict[str, Any]:
    report = indexnow if isinstance(indexnow, dict) else None
    report_details = _health_details(report)
    site_details = _health_details(site)
    publication_id = str(site_details.get("indexnow_publication_id") or "").strip()
    reported_publication_id = str(report_details.get("publication_id") or "").strip()
    expected = site_details.get("indexnow_expected") is True
    matching_report = bool(report and publication_id and reported_publication_id == publication_id)
    report_status = str((report or {}).get("status") or "UNKNOWN").upper()
    result = str(report_details.get("result") or "not_initialized")
    reason = str((report or {}).get("summary") or "No IndexNow production report has been retained.")
    action = "Review the deployment workflow and sender state; no search-indexing claim is implied."
    status = report_status if report else "UNKNOWN"
    if status not in {"HEALTHY", "WARNING", "FAILED", "UNKNOWN"}:
        status = "UNKNOWN"

    if expected and not matching_report:
        deployed_at = _parse_timestamp((site or {}).get("observed_at"))
        grace_seconds = _indexnow_count(site_details.get("indexnow_grace_seconds")) or 1_800
        grace_elapsed = deployed_at is not None and now >= deployed_at + timedelta(seconds=grace_seconds)
        if grace_elapsed:
            status = "WARNING"
            result = "missing_report"
            reason = "IndexNow report missing for the latest deployment."
            action = "Inspect the workflow run and retry only the operational report after confirming sender state."
        else:
            status = "UNKNOWN"
            result = "awaiting_report"
            reason = "The latest deployment is still within the documented IndexNow report grace period."
            action = "Wait for the workflow report or inspect the linked deployment run if it exceeds the grace period."
    elif not report:
        if expected:
            reason = "No IndexNow report has been retained for the latest deployment."
        action = "Run a confirmed production deployment before treating IndexNow as initialized."

    pending_count = _indexnow_count(report_details.get("pending_url_count"))
    if report and (matching_report or not expected):
        if result in {"validation_pending", "pending_retry", "partial_success"}:
            status = "WARNING"
        elif result in {"action_required", "live_verification_failed"}:
            status = "FAILED"
        elif result in {"bootstrap", "not_initialized"}:
            status = "UNKNOWN"
        elif result in {"submitted", "no_changes"}:
            status = "HEALTHY" if pending_count == 0 else "WARNING" if pending_count is not None else "UNKNOWN"
    if matching_report and pending_count is not None and pending_count > 0 and status == "HEALTHY":
        status = "WARNING"
        reason = "IndexNow has pending URLs retained for retry."
        action = "Inspect the sender result and allow the next eligible workflow to retry the pending URLs."

    last_submission = report_details.get("last_submission_at")
    last_successful = report_details.get("last_successful_submission_at")
    attempted = _indexnow_count(report_details.get("attempted_url_count"))
    http_200_count = _indexnow_count(report_details.get("http_200_count"))
    http_202_count = _indexnow_count(report_details.get("http_202_count"))
    http_status = _indexnow_count(report_details.get("http_status"))
    if http_status is None:
        http_result = "No request"
    else:
        http_result = f"HTTP {http_status} · 200: {http_200_count if http_200_count is not None else '—'} · 202: {http_202_count if http_202_count is not None else '—'}"
    preview = _safe_indexnow_preview(report_details)
    preview_total = _indexnow_count(report_details.get("url_preview_total"))
    preview_markup = (
        f"<p>Showing {len(preview)} of {preview_total if preview_total is not None else len(preview)} URLs:</p>"
        "<ul class='indexnow-url-preview'>"
        + "".join(f"<li><code>{html.escape(url)}</code></li>" for url in preview)
        + "</ul>"
        if preview else "<p>No URL preview retained.</p>"
    )
    error_summary = report_details.get("error_summary")
    if not isinstance(error_summary, str) or len(error_summary) > 240:
        error_summary = None
    safe_error = html.escape(error_summary or "No additional error recorded.")
    checked = (report or site or {}).get("observed_at")
    short_result = {
        "submitted": "Submitted",
        "validation_pending": "Validation pending",
        "no_changes": "No changes to submit",
        "pending_retry": "Pending retry",
        "partial_success": "Partial success",
        "action_required": "Action required",
        "bootstrap": "Initialized — no submission yet",
        "not_initialized": "Not initialized",
        "missing_report": "Report missing",
        "awaiting_report": "Awaiting report",
    }.get(result, result.replace("_", " ").title())
    technical = (
        f"<p class='indexnow-status-note'>IndexNow submission status only. This does not confirm search indexing.</p>"
        f"<p class='sr-only'>Result: {html.escape(short_result)}</p>"
        "<dl class='indexnow-details'>"
        f"<div><dt>Last check</dt><dd>{_timestamp_markup(checked)}</dd></div>"
        f"<div><dt>Last submission</dt><dd>{_timestamp_markup(last_submission) if last_submission else 'No submissions yet'}</dd></div>"
        f"<div><dt>Last successful submission (HTTP 200)</dt><dd>{_timestamp_markup(last_successful) if last_successful else '—'}</dd></div>"
        f"<div><dt>Last execution</dt><dd>{attempted if attempted is not None else '—'} URL(s) · {html.escape(http_result)}</dd></div>"
        f"<div><dt>Pending URLs</dt><dd>{pending_count if pending_count is not None else '—'}</dd></div>"
        f"<div><dt>Oldest pending</dt><dd>{_timestamp_markup(report_details.get('oldest_pending_at'))}</dd></div>"
        "</dl>"
        f"<div class='system-health-description'>{preview_markup}</div>"
        f"<p class='indexnow-error'><strong>Safe error</strong>: {safe_error}</p>"
    )
    # The next action links to the retained workflow run when one exists.
    return _health_card_record(
        "Search indexing", status, technical=technical, reason=reason, action=action,
        action_href=_health_run_url(report or site), checked=checked, group="search",
        search_name="search indexing indexnow submissions",
    )


def _system_health_cards(health: dict[str, Any]) -> tuple[list[dict[str, Any]], Any, dict[str, Any]]:
    now = datetime.now(timezone.utc)
    providers = [
        provider for provider in health.get("providers") or []
        if str(provider.get("id") or "") in {"freizeitkarte", "opentopomap", "maprando", "bbbike"}
    ]
    observations = {
        str(item.get("component") or ""): item
        for item in health.get("observations") or [] if isinstance(item, dict)
    }
    weekly = health.get("weekly") if isinstance(health.get("weekly"), dict) else None
    scheduler = health.get("scheduler") if isinstance(health.get("scheduler"), dict) else None

    scheduler_status = "UNKNOWN"
    scheduler_reason = "No scheduler heartbeat has been retained yet."
    if scheduler:
        scheduler_status = {
            "HEALTHY": "HEALTHY", "WAITING": "HEALTHY", "RUNNING": "HEALTHY",
            "WARNING": "WARNING", "FAILED": "FAILED",
        }.get(str(scheduler.get("status") or "UNKNOWN").upper(), "UNKNOWN")
        next_run = _parse_timestamp(scheduler.get("next_run_at"))
        completed = _parse_timestamp(scheduler.get("completed_at"))
        if scheduler_status == "HEALTHY" and (
            (next_run is not None and next_run < now - timedelta(hours=6))
            or (completed is not None and now - completed > timedelta(days=10))
        ):
            scheduler_status = "WARNING"
            scheduler_reason = "The retained scheduler heartbeat is overdue or stale."
        elif scheduler_status in {"WARNING", "FAILED"}:
            scheduler_reason = str(scheduler.get("error_summary") or "The latest scheduler run did not complete cleanly.")

    weekly_status = str((weekly or {}).get("status") or "UNKNOWN").upper()
    weekly_at = _parse_timestamp((weekly or {}).get("observed_at"))
    if weekly_status == "HEALTHY" and weekly_at and now - weekly_at > timedelta(days=8):
        weekly_status = "WARNING"
    weekly_reason = str((weekly or {}).get("summary") or "No weekly quality-gate report has been received.")
    if weekly_status == "WARNING" and weekly_at and now - weekly_at > timedelta(days=8):
        weekly_reason = "The latest weekly quality-gate report is more than 8 days old."

    release = observations.get("release")
    site = observations.get("site")
    api = observations.get("catalog-api")
    drift_status = "UNKNOWN"
    drift_text = "Release or deployed website metadata has not been reported yet."
    if release and site:
        expected = (str(release.get("release_version") or ""), str(release.get("build_number") or ""))
        deployed = (str(site.get("release_version") or ""), str(site.get("build_number") or ""))
        drift_status = "HEALTHY" if expected == deployed and all(expected) else "WARNING"
        drift_text = (
            f"Manifest and release agree: {expected[0]} · build {expected[1]}."
            if drift_status == "HEALTHY" else
            f"Release expects {expected[0] or '—'} · build {expected[1] or '—'}; website reports {deployed[0] or '—'} · build {deployed[1] or '—'}."
        )
    elif site:
        deployed = (str(site.get("release_version") or ""), str(site.get("build_number") or ""))
        drift_status = str(site.get("status") or "UNKNOWN").upper() if all(deployed) else "WARNING"
        drift_text = (
            f"The deployed website manifest was verified as {deployed[0]} · build {deployed[1]}. "
            "No separate release-gate observation is required for this deployed-manifest check."
        )

    weekly_details = (weekly or {}).get("details") or {}
    if isinstance(weekly_details, str):
        try:
            weekly_details = json.loads(weekly_details)
        except json.JSONDecodeError:
            weekly_details = {}
    email_result = str(weekly_details.get("email") or "unknown").lower()
    email_status = (
        "HEALTHY" if email_result in {"success", "passed", "healthy"}
        else "FAILED" if email_result in {"failure", "failed", "cancelled", "timed_out"}
        else "UNKNOWN"
    )
    # API and Database are live probes: the snapshot this page renders was
    # read just now, so their last check is the snapshot time.
    cards = [
        _system_health_card(
            "API", health.get("api"), "<p>Authenticated response received when this page loaded.</p>",
            reason="The API health state could not be confirmed.",
            action="Reload the page, then inspect the catalog API deployment and service logs.",
            checked_at=now,
        ),
        _system_health_card(
            "Database", health.get("database"), "<p>Database snapshot read when this page loaded.</p>",
            reason="A live PostgreSQL health state could not be confirmed.",
            action="Inspect the database connection and migration state.",
            checked_at=now,
        ),
    ]
    # Provider catalogs collapse into one Catalogs row that links to Providers;
    # Providers owns the per-provider detail (no duplicate provider cards).
    provider_states = [(provider, provider_catalog_health(provider, now=now)) for provider in providers]
    if provider_states:
        rank_order = {"FAILED": 0, "WARNING": 1, "UNKNOWN": 2, "HEALTHY": 3}
        worst = min((state["status"] for _, state in provider_states), key=lambda value: rank_order.get(value, 2))
        affected = [provider for provider, state in provider_states if state["status"] != "HEALTHY"]
        names = ", ".join(str(provider.get("name") or provider.get("id")) for provider in affected)

        def provider_checked(provider: dict[str, Any]) -> datetime | None:
            # The latest recorded source check or catalog collection.
            return _latest_timestamp(
                provider.get("lastHealthCheck"), provider.get("lastCollectionFinished"),
                provider.get("lastCollectionAttempt"), provider.get("lastCollectionSuccess"),
                provider.get("lastCatalogSync"),
            )

        description = "<ul class='system-health-catalogs'>" + "".join(
            f"<li><a href='/admin/providers/{quote(str(provider.get('id')), safe='')}'>{html.escape(str(provider.get('name') or provider.get('id')))}</a> "
            f"{_health_status_badge(state['status'])} <span>{html.escape(state['reason'])}</span> "
            f"<span class='system-health-catalog-when'>Checked {_health_checked_markup(provider_checked(provider))}</span></li>"
            for provider, state in provider_states
        ) + "</ul>"
        cards.append(_system_health_card(
            "Catalogs", worst, description,
            reason=(f"{names}: " + "; ".join(state["reason"] for _, state in provider_states if state["status"] != "HEALTHY")) if affected else "All provider catalogs are current.",
            action="Open Providers and review the affected provider." if affected else "No action required.",
            group="catalogs",
            checked_at=_latest_timestamp(*(provider_checked(provider) for provider, _ in provider_states)),
            action_href="/admin/providers",
        ))
    cards.append(_indexnow_card(observations.get("indexnow"), site, now=now))
    scheduler_action = "Inspect the catalog scheduler container and its next scheduled run."
    cards.extend([
        _system_health_card(
            "Scheduler", scheduler_status,
            f"<p>Last completed: {_timestamp_markup((scheduler or {}).get('completed_at'))}.</p>"
            + (f"<p>Next check: {_timestamp_markup(scheduler['next_run_at'])}.</p>" if (scheduler or {}).get('next_run_at') else ''),
            reason=scheduler_reason, action=scheduler_action,
            # The heartbeat row's last write, else its last run times.
            checked_at=_latest_timestamp(*(
                (scheduler or {}).get(key) for key in ("updated_at", "completed_at", "started_at")
            )),
        ),
        _system_health_card(
            "Weekly tests", weekly_status,
            f"<p>{html.escape(str((weekly or {}).get('summary') or 'No weekly test report received yet.'))}</p><p>Observed: {_timestamp_markup((weekly or {}).get('observed_at'))}.</p>",
            weekly,
            reason=weekly_reason,
            action="Open the linked workflow and rerun the complete weekly matrix.",
            group="releases",
        ),
        _system_health_card(
            "Email report", email_status,
            f"<p>Latest SMTP2GO delivery step: <strong>{html.escape(email_result)}</strong>.</p>",
            weekly,
            reason=(
                "No weekly email-delivery result is retained."
                if email_result == "unknown"
                else f"The latest weekly email report step ended as {email_result}."
            ),
            action="Check the SMTP2GO step and credentials, then resend the weekly report.",
            group="releases",
        ),
        _system_health_card(
            "Website deploy", (site or {}).get("status"),
            f"<p>Commit {html.escape(str((site or {}).get('commit_sha') or '—')[:12])}; deployed {_timestamp_markup((site or {}).get('observed_at'))}.</p>",
            site,
            reason=str((site or {}).get("summary") or "No website deployment observation has been received."),
            action="Run the public-site deployment workflow and verify the live manifest.",
            group="releases",
        ),
        _system_health_card(
            "API deploy", (api or {}).get("status"),
            f"<p>Commit {html.escape(str((api or {}).get('commit_sha') or '—')[:12])}; deployed {_timestamp_markup((api or {}).get('observed_at'))}.</p>",
            api,
            reason=str((api or {}).get("summary") or "No catalog API deployment observation has been received."),
            action="Run the catalog API deployment workflow and confirm its retained observation.",
            group="releases",
        ),
        _system_health_card(
            "Release match", drift_status, f"<p>{html.escape(drift_text)}</p>", release or site,
            reason=drift_text,
            action="Deploy the website manifest again or run the release gate so both observations can be compared.",
            group="releases",
            checked_at=_latest_timestamp((release or {}).get("observed_at"), (site or {}).get("observed_at")),
        ),
    ])
    sync = health.get("githubSync")
    sync_status = "UNKNOWN" if sync is None else "WARNING" if sync.get("overdue") or sync.get("errors") else "HEALTHY"
    cards.append(_system_health_card(
        "Issue sync", sync_status,
        f"<p>Closed linked issues resolve diagnostics automatically. Checks run every 15 minutes.</p><p>Last check: {_timestamp_markup((sync or {}).get('checked_at'))}.</p>",
        reason="Linked issue checks are overdue or could not be verified.",
        action="Check the API worker and GitHub availability. Existing diagnostic states are preserved on errors.",
        checked_at=(sync or {}).get("checked_at"),
    ))
    cards.sort(key=lambda card: _HEALTH_STATUS_RANK.get(card['status'], 2))
    return cards, weekly, weekly_details


_HEALTH_GROUPS = (
    ("service", "Service"),
    ("releases", "Releases"),
    ("catalogs", "Catalogs"),
    ("search", "Search"),
)
_HEALTH_FILTERS = (
    ("FAILED", "Failed", "danger"),
    ("WARNING", "Degraded", "warning"),
    ("UNKNOWN", "No data", "unknown"),
    ("HEALTHY", "Healthy", "success"),
)


def _health_check_table(cards: list[dict[str, Any]], *, issue: bool, caption: str, id_prefix: str, body_id: str = "") -> str:
    """Compact check table shared by Issues and the Technical details tabs."""
    rows = "".join(
        _health_check_row(card, f"{id_prefix}-{index}", issue=issue) for index, card in enumerate(cards, 1)
    )
    columns = (
        "<col class='health-col-check'><col class='health-col-status'><col class='health-col-reason'>"
        "<col class='health-col-when'><col class='health-col-more'>"
        if issue else
        "<col class='health-col-check'><col class='health-col-status'><col class='health-col-when'><col class='health-col-more'>"
    )
    head = (
        "<th scope='col'>Check</th><th scope='col' class='column-status'>Status</th>"
        + ("<th scope='col'>Reason</th>" if issue else "")
        + "<th scope='col' class='column-date'>Last checked</th><td class='health-check-more'></td>"
    )
    tbody_id = f" id='{html.escape(body_id, quote=True)}'" if body_id else ""
    return (
        f"<div class='table-wrap health-check-wrap'><table class='admin-table health-check-table{' health-issue-table' if issue else ' health-group-table'}' data-own-mobile-layout>"
        f"<caption class='sr-only'>{html.escape(caption)}</caption><colgroup>{columns}</colgroup>"
        f"<thead><tr>{head}</tr></thead><tbody{tbody_id}>{rows}</tbody></table></div>"
    )


_HEALTH_SUITE_LABELS = {
    "selection": "Test-suite selection",
    "site": "Public website",
    "backend": "Backend / API",
    "app": "macOS application",
    "native": "Native device safety",
    "release": "Release contracts",
    "shared_ci": "Shared / CI contracts",
    "live_catalog": "Live catalog contract",
}


def _health_technical_card(cards: list[dict[str, Any]], weekly: Any, weekly_details: dict[str, Any]) -> str:
    """One collapsed Technical details card with one tab per check group.

    Owner decision 2026-10-06 (provider detail pattern): rarely needed lists
    live in one collapsed card with tabs. Each group tab keeps its summary
    (``N/M healthy``) and every check of the group that is not already listed
    under Issues; Weekly results keeps the weekly suite table.
    """
    panels: list[tuple[str, str, str]] = []
    for group, title in _HEALTH_GROUPS:
        members = [card for card in cards if card.get("group", "service") == group]
        if not members:
            continue
        healthy = sum(card["status"] == "HEALTHY" for card in members)
        listed = [card for card in members if card["status"] not in _HEALTH_ISSUE_STATES]
        in_issues = len(members) - len(listed)
        summary = (
            _status_pill("success" if healthy == len(members) else "warning", f"{healthy}/{len(members)} healthy")
            + (f"<span class='health-panel-note'>{in_issues} listed under Issues</span>" if in_issues else "")
            + (f"<a class='section-link' href='/admin/providers'>Open Providers&nbsp;{_admin_icon('arrow-right')}</a>"
               if group == "catalogs" else "")
        )
        body = (
            f"<div class='health-panel-summary'>{summary}</div>"
            + (_health_check_table(listed, issue=False, caption=f"{title} checks", id_prefix=f"health-{group}")
               + "<p class='admin-empty health-panel-empty' data-state='filtered' data-health-panel-empty hidden>"
               "<span>No checks in this group match your filters.</span></p>"
               if listed else "<p class='table-help'>Every check in this group is listed under Issues.</p>")
        )
        panels.append((group, title, body))
    weekly_rows = "".join(
        f"<tr><th scope='row'>{html.escape(_HEALTH_SUITE_LABELS.get(str(name), str(name).replace('_', ' ').title()))}</th>"
        f"<td class='column-status'>{_health_status_badge('HEALTHY' if str(value).lower() in {'success', 'passed', 'healthy'} else 'FAILED' if str(value).lower() in {'failure', 'failed', 'cancelled', 'timed_out'} else 'UNKNOWN')}</td>"
        f"<td class='column-status'>{html.escape(str(value))}</td></tr>"
        for name, value in sorted(weekly_details.items())
        if name != "email" and not str(name).startswith("catalog_")
    )
    weekly_link = _health_run_link(weekly)
    weekly_body = (
        (f"<div class='health-panel-summary'>{weekly_link}</div>" if weekly_link else "")
        + (
            "<div class='table-wrap health-check-wrap'><table class='admin-table health-check-table health-weekly-table'>"
            "<caption class='sr-only'>Weekly test suite results</caption>"
            "<thead><tr><th scope='col'>Check</th><th scope='col' class='column-status'>Health</th>"
            f"<th scope='col' class='column-status'>Result</th></tr></thead><tbody>{weekly_rows}</tbody></table></div>"
            if weekly_rows else _empty_state("empty", "No weekly suite details received yet.")
        )
    )
    panels.append(("weekly", "Weekly results", weekly_body))
    tabs = "".join(
        f"<button type='button' role='tab' class='quick-filter{' active' if index == 0 else ''}' "
        f"id='health-tab-{key}' data-health-tab='{key}' aria-controls='health-panel-{key}' "
        f"aria-selected='{'true' if index == 0 else 'false'}' tabindex='{0 if index == 0 else -1}'>"
        f"{html.escape(label)}</button>"
        for index, (key, label, _) in enumerate(panels)
    )
    bodies = "".join(
        f"<div class='health-technical-panel' role='tabpanel' id='health-panel-{key}' aria-labelledby='health-tab-{key}' "
        f"data-health-panel='{key}'{' data-health-group-card=' + chr(39) + key + chr(39) if key != 'weekly' else ''} "
        f"tabindex='0'{'' if index == 0 else ' hidden'}>{body}</div>"
        for index, (key, _, body) in enumerate(panels)
    )
    topics = " · ".join(label for _, label, _ in panels)
    return (
        "<section class='admin-card health-technical-card' id='health-technical' aria-labelledby='health-technical-title'>"
        "<details class='health-technical-disclosure' id='health-technical-disclosure'>"
        f"<summary><span class='health-technical-chevron'>{_admin_icon('chevron-right')}</span>"
        "<h2 id='health-technical-title'>Technical details</h2>"
        f"<span class='disclosure-meta'>{html.escape(topics)}</span></summary>"
        "<div class='health-technical-body'>"
        "<div class='filter-bar health-technical-switcher'><div class='quick-filter-group' role='tablist' "
        f"aria-label='Check groups'>{tabs}</div></div>{bodies}</div></details></section>"
    )


def _health_page_script() -> str:
    """Health filters, inline Details and the Technical details tabs.

    The status quick filter and search hide non-matching check rows (and their
    Details rows). A match that only exists inside a group tab opens the
    Technical details card and selects that tab. ``?status=FAILED`` (or any
    status value) preselects the quick filter, so Dashboard links land
    filtered; changing the filter keeps the query in sync.
    """
    return r"""(() => {
      const form = document.getElementById('health-filters');
      const search = document.getElementById('health-search');
      const status = document.getElementById('health-status');
      const technical = document.getElementById('health-technical-disclosure');
      const tabs = [...document.querySelectorAll('[data-health-tab]')];
      if (!form || !search || !status) return;
      form.addEventListener('submit', (event) => event.preventDefault());
      const detailsRow = (button) => document.getElementById(button.getAttribute('aria-controls'));
      document.querySelectorAll('[data-health-details]').forEach((button) => button.addEventListener('click', () => {
        const open = button.getAttribute('aria-expanded') !== 'true';
        button.setAttribute('aria-expanded', open ? 'true' : 'false');
        const row = detailsRow(button);
        if (row) row.hidden = !open;
      }));
      const selectTab = (tab, focus) => {
        tabs.forEach((other) => {
          const active = other === tab;
          other.classList.toggle('active', active);
          other.setAttribute('aria-selected', active ? 'true' : 'false');
          other.tabIndex = active ? 0 : -1;
          const panel = document.getElementById(other.getAttribute('aria-controls'));
          if (panel) panel.hidden = !active;
        });
        if (focus) tab.focus();
      };
      tabs.forEach((tab, index) => {
        tab.addEventListener('click', () => selectTab(tab, false));
        tab.addEventListener('keydown', (event) => {
          const next = {ArrowRight: index + 1, ArrowLeft: index - 1, Home: 0, End: tabs.length - 1}[event.key];
          if (next === undefined) return;
          event.preventDefault();
          selectTab(tabs[(next + tabs.length) % tabs.length], true);
        });
      });
      const filter = () => {
        const query = search.value.trim().toLocaleLowerCase();
        let visible = 0;
        document.querySelectorAll('tr[data-health-status]').forEach((row) => {
          row.hidden = !(row.dataset.healthName.includes(query) && (status.value === 'all' || row.dataset.healthStatus === status.value));
          const button = row.querySelector('[data-health-details]');
          const details = button && detailsRow(button);
          if (details) details.hidden = row.hidden || button.getAttribute('aria-expanded') !== 'true';
          if (!row.hidden) visible++;
        });
        const issues = document.getElementById('health-issue-rows');
        if (issues) {
          const shown = !!issues.querySelector('tr[data-health-status]:not([hidden])');
          issues.closest('.table-wrap').hidden = !shown;
          document.getElementById('health-issues-filtered').hidden = shown;
        }
        const matches = [];
        document.querySelectorAll('[data-health-panel]').forEach((panel) => {
          const rows = panel.querySelectorAll('tr[data-health-status]');
          const shown = panel.querySelector('tr[data-health-status]:not([hidden])');
          const empty = panel.querySelector('[data-health-panel-empty]');
          if (empty) empty.hidden = !rows.length || !!shown;
          const wrap = panel.querySelector('.health-check-wrap');
          if (wrap && rows.length) wrap.hidden = !shown;
          if (shown) matches.push(panel.dataset.healthPanel);
        });
        document.getElementById('health-empty').hidden = visible > 0;
        // A filter or search that matches checks inside a tab opens the card
        // on that tab (the current tab when it matches, else the first).
        if ((query || status.value !== 'all') && matches.length && technical) {
          technical.open = true;
          const current = tabs.find((tab) => tab.getAttribute('aria-selected') === 'true');
          if (!current || !matches.includes(current.dataset.healthTab)) {
            const target = tabs.find((tab) => tab.dataset.healthTab === matches[0]);
            if (target) selectTab(target, false);
          }
        }
      };
      const syncQuery = () => {
        try {
          const url = new URL(location.href);
          if (status.value === 'all') url.searchParams.delete('status'); else url.searchParams.set('status', status.value);
          history.replaceState(history.state, '', url);
        } catch (error) { /* the filter still works without the query */ }
      };
      const initial = new URLSearchParams(location.search).get('status');
      if (initial && [...status.options].some((option) => option.value === initial)) status.value = initial;
      search.addEventListener('input', filter);
      status.addEventListener('change', () => { filter(); syncQuery(); });
      filter();
    })();"""


def system_health_page(health: dict[str, Any], user: dict[str, Any], csrf_token: str) -> bytes:
    cards, weekly, weekly_details = _system_health_cards(health)
    counts = {state: sum(card['status'] == state for card in cards) for state, _, _ in _HEALTH_FILTERS}
    labels = {state: label for state, label, _ in _HEALTH_FILTERS}
    health_status_filter = _quick_select_filter(
        "health-status", [("all", "All"), *[(state, labels[state]) for state, _, _ in _HEALTH_FILTERS]], "all",
        label="Check status",
    )
    # One summary card with plain tiles like Installations (owner decision
    # 2026-10-06): no icons, no scope chips; the quick filters filter.
    summary = (
        "<section class='admin-card installation-kpis health-kpis' aria-label='Health summary'>"
        + _metric_row([
            _metric_tile(labels[state], counts[state], failure=state == "FAILED", data_stat=f"health{state.title()}")
            for state, _, _ in _HEALTH_FILTERS
        ], label="Health summary")
        + "</section>"
    )
    issue_cards = [card for card in cards if card["status"] in _HEALTH_ISSUE_STATES]
    issues = _section_card(
        "Issues",
        (_health_check_table(issue_cards, issue=True, caption="Failing and degraded checks",
                             id_prefix="health-issue", body_id="health-issue-rows")
         + "<p class='admin-empty' data-state='filtered' id='health-issues-filtered' hidden>"
         "<span>No issues match your filters.</span></p>")
        if issue_cards else _empty_state("empty", "No issues."),
        card_id="health-attention", css="system-health-problems",
    )
    content = f"""
      {_admin_header(user, csrf_token, active='system-health')}
      <main class='dashboard system-health-page' id='main-content'>
        <div class='heading-row'><div><h1>Health</h1></div></div>
        {summary}
        <form class='filter-bar' id='health-filters' role='search'>{health_status_filter}<label class='filter-search'><span class='sr-only'>Search checks</span><input type='search' id='health-search' placeholder='Search checks'></label></form>
        <p class='admin-empty' data-state='filtered' id='health-empty' hidden><span>No checks match your filters.</span></p>
        {issues}
        {_health_technical_card(cards, weekly, weekly_details)}
      </main>
      <script nonce="{_ADMIN_NONCE_PLACEHOLDER}">{_health_page_script()}</script>
    """
    return _layout("Health", content, sections={"health": health, "states": [(card["title"], card["status"], card["reason"]) for card in cards]})


def dashboard_page(
    rows: list[dict[str, Any]], user: dict[str, Any], csrf_token: str,
    *, operations: list[dict[str, Any]] | None = None,
    resolved_operations: list[dict[str, Any]] | None = None,
    public_stats_enabled: bool = False,
    identity_devices: list[dict[str, Any]] | None = None,
    diagnostic_summary: dict[str, dict[str, int]] | None = None,
) -> bytes:
    # The statistics view may retain a zero-attempt identity row so raw
    # pre-install evidence remains queryable, but it is not an installation
    # variant and must not appear in the Installations table.
    diagnostic_summary = diagnostic_summary if diagnostic_summary is not None else _diagnostic_summary_by_identity(
        operations or [], resolved_operations or [],
    )
    summary_source = diagnostic_summary
    rows = [
        row for row in rows
        if not (
            int(row.get("attempted_install_count") or 0) == 0
            and int(row.get("prewrite_failure_count") or 0) > 0
            # An identity with an open installation problem stays visible so
            # the Open problems total is the sum of the rendered rows.
            and not int((summary_source.get(_identity_group_key(row)) or {}).get("open_errors") or 0)
        )
    ]
    latest_copy = "All time · Model evidence"
    if not rows:
        content = f"""
          {_admin_header(user, csrf_token, active='installations')}
          <main class="dashboard" id="main-content">
            <div class="heading-row installation-heading"><div><h1>Installations</h1></div><p class="page-meta">{latest_copy}</p></div>
            <p class='empty'>No installation evidence yet.</p>
          </main>
        """
        return _layout("Installations", content, sections={"installations": []})

    catalog_by_id = {str(device.get("id") or device.get("device_id")): device
                     for device in identity_devices or []}
    status_values = [status.value for status in CANONICAL_STATUS_ORDER]
    status_options = "".join(
        f"<option value='{status.lower()}'>{status.title()}</option>"
        for status in status_values
    )
    def metric(row: dict[str, Any], summary_key: str, row_key: str) -> int:
        summary = diagnostic_summary.get(_identity_group_key(row), {})
        if row_key in row:
            return int(row[row_key] or 0)
        return int(summary[summary_key]) if summary_key in summary else int(row.get(row_key) or 0)

    attempts = sum(metric(row, "attempts", "attempted_install_count") for row in rows)
    successes = sum(metric(row, "successful", "successful_install_count") for row in rows)
    failures = sum(metric(row, "failed", "failed_install_count") for row in rows)
    # Sum only rendered identities (each identity once) so the KPI equals the
    # column total; with SQL counts it also equals Dashboard Installation problems.
    open_errors = sum(
        int((diagnostic_summary.get(identity) or {}).get("open_errors") or 0)
        for identity in dict.fromkeys(_identity_group_key(row) for row in rows)
    )
    success_rate = (successes / attempts * 100) if attempts else None
    identity_pending = sum(
        int((diagnostic_summary.get(identity) or {}).get("identity_pending") or 0)
        for identity in dict.fromkeys(_identity_group_key(row) for row in rows)
    )
    review_identities = (
        f"<a class='secondary-button identity-review-link' href='{IDENTITY_REVIEW_PATH}'>"
        f"Review identities&nbsp;{_admin_icon('arrow-right')}</a>"
        if identity_pending else ""
    )
    table_rows = "".join(
        _statistics_row(
            row,
            diagnostic_summary.get(_identity_group_key(row), {}),
            catalog_device=catalog_by_id.get(str(row.get("canonical_device_model_id") or "")),
        )
        for row in rows
    )
    pagination = "" if len(rows) <= 25 else f"""
          <div class='provider-pagination' id='installation-pagination' aria-live='polite'>
            <label>Rows <select id='installation-page-size' data-admin-dropdown aria-label='Rows per installation page'><option value='25' selected>25</option><option value='50'>50</option></select></label>
            <button type='button' data-installation-page='previous' disabled>Previous</button>
            <span>Showing 1–25 of {len(rows)} · page 1 of {(len(rows) + 24) // 25}</span>
            <button type='button' data-installation-page='next'>Next</button>
          </div>
    """
    content = f"""
      {_admin_header(user, csrf_token, active='installations')}
      <main class="dashboard" id="main-content">
        <div class="heading-row installation-heading"><div><h1>Installations</h1></div><p class="page-meta">{latest_copy}</p></div>
        <section class="admin-card installation-kpis" aria-label="Installation summary">
          {_metric_row([
              # No scope chips under these numbers (owner decision 2026-10-06).
              _metric_tile("Attempts", attempts, data_stat="attempts"),
              _metric_tile("Successful", successes, data_stat="successful"),
              _metric_tile("Failed", failures, failure=True, data_stat="failed"),
              _metric_tile("Success rate", success_rate, fmt="rate", data_stat="successRate"),
              _metric_tile("Open problems", open_errors, failure=True,
                           href="/admin/installations?state=open" if open_errors else None, data_stat="openProblems",
                           hint="Installs (operations) with an unresolved failure and no linked GitHub issue"),
          ], label="Installation summary")}
        </section>
        <section class="evidence-section" aria-label="Installation evidence table">
          <form class="filter-bar admin-filter-bar" id="evidence-filters" role="search"{' hidden' if len(rows) <= 1 else ''}>
            <div class="quick-filter-group" role="group" aria-label="Quick installation filters"><button type="button" class="quick-filter active" data-installation-filter="all" aria-pressed="true">All</button><button type="button" class="quick-filter" data-installation-filter="failed" aria-pressed="false">Failed</button><button type="button" class="quick-filter" data-installation-filter="open" aria-pressed="false">Open problems</button><button type="button" class="quick-filter" data-installation-filter="identity-pending" aria-pressed="false">Identity review</button><button type="button" class="quick-filter" data-installation-filter="successful" aria-pressed="false">Successful</button></div>{review_identities}
            <label class="filter-search"> <span class="sr-only">Search models</span><input id="evidence-search" type="search" placeholder="Search models" autocomplete="off"></label>
            <details class="admin-disclosure filter-disclosure" id="installation-more-filters"><summary>More filters</summary><div class="disclosure-body">
              <label><span class="sr-only">Filter by evidence</span><select id="evidence-status" data-admin-dropdown><option value="all">All evidence</option>{status_options}</select></label>
            </div></details><label class="device-mobile-sort"><span class="sr-only">Sort models</span><select id="evidence-sort" data-admin-dropdown><option value="latest" selected>Latest activity</option><option value="model:ascending">Model ↑</option><option value="model:descending">Model ↓</option><option value="variant:ascending">Variant ↑</option><option value="variant:descending">Variant ↓</option><option value="status:ascending">Evidence ↑</option><option value="status:descending">Evidence ↓</option><option value="attempts:ascending">Attempts ↑</option><option value="attempts:descending">Attempts ↓</option><option value="successfulCount:ascending">Successful ↑</option><option value="successfulCount:descending">Successful ↓</option><option value="failedCount:ascending">Failed ↑</option><option value="failedCount:descending">Failed ↓</option><option value="errors:ascending">Open problems ↑</option><option value="errors:descending">Open problems ↓</option><option value="lastSuccess:ascending">Last success ↑</option><option value="lastSuccess:descending">Last success ↓</option></select></label>
            <p class="results-count" id="results-count" aria-live="polite">{_count_label(len(rows), 'variant')}</p>
            <button type="button" class="secondary-button filter-clear" data-filter-clear aria-label="Clear installation filters" hidden>Clear</button>
          </form>
          <p id="installation-empty" class="table-help" role="status" hidden>No matching models.</p>
          <div class="table-wrap evidence-table-wrap" id="installation-table" tabindex="0" role="region" aria-label="Installation evidence table"><table class="admin-table"><caption class="sr-only">Installations by exact device identity</caption><colgroup><col class="evidence-column-model"><col class="evidence-column-variant"><col class="evidence-column-status"><col class="evidence-column-attempts"><col class="evidence-column-successful"><col class="evidence-column-failed"><col class="evidence-column-open-errors"><col class="evidence-column-last-success"></colgroup><thead><tr><th scope="col" class="" aria-sort="none"><button type="button" class="device-sort-button" data-installation-sort="model" aria-label="Model">Model <span class="sort-indicator" aria-hidden="true" data-sort="none"></span></button></th><th scope="col" class="" aria-sort="none"><button type="button" class="device-sort-button" data-installation-sort="variant" aria-label="Variant">Variant <span class="sort-indicator" aria-hidden="true" data-sort="none"></span></button></th><th scope="col" class="column-status" aria-sort="none"><button type="button" class="device-sort-button" data-installation-sort="status" aria-label="Evidence">Evidence <span class="sort-indicator" aria-hidden="true" data-sort="none"></span></button></th><th scope="col" class="column-number" aria-sort="none"><button type="button" class="device-sort-button" data-installation-sort="attempts" aria-label="Attempts">Attempts <span class="sort-indicator" aria-hidden="true" data-sort="none"></span></button></th><th scope="col" class="column-number" aria-sort="none"><button type="button" class="device-sort-button" data-installation-sort="successfulCount" aria-label="Successful">Successful <span class="sort-indicator" aria-hidden="true" data-sort="none"></span></button></th><th scope="col" class="column-number" aria-sort="none"><button type="button" class="device-sort-button" data-installation-sort="failedCount" aria-label="Failed">Failed <span class="sort-indicator" aria-hidden="true" data-sort="none"></span></button></th><th scope="col" class="column-number" aria-sort="none"><button type="button" class="device-sort-button" data-installation-sort="errors" aria-label="Open problems">Open problems <span class="sort-indicator" aria-hidden="true" data-sort="none"></span></button></th><th scope="col" class="column-date" aria-sort="none"><button type="button" class="device-sort-button" data-installation-sort="lastSuccess" aria-label="Last success">Last success <span class="sort-indicator" aria-hidden="true" data-sort="none"></span></button></th></tr></thead><tbody id="evidence-rows">{table_rows}</tbody></table></div>
          {pagination}
        </section>
      </main>
      <script nonce="{_ADMIN_NONCE_PLACEHOLDER}">{_dashboard_script()}</script>
    """
    return _layout("Installations", content, sections={"installations": rows, "diagnostics": diagnostic_summary, "catalog": identity_devices})


def _admin_json(value: Any) -> str:
    """Serialize data for an inert/nonce-protected inline admin script."""

    encoded = json.dumps(value, ensure_ascii=False, default=_admin_json_default)
    # Keep server-provided text from terminating a script element or becoming
    # HTML markup when an adapter/source value is unexpectedly user-controlled.
    return (
        encoded.replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def _admin_json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        normalized = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return normalized.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _provider_status_badge(value: Any, *, kind: str = "status") -> str:
    normalized = str(value or "UNKNOWN").strip().upper()
    labels = {
        "ACTIVE": ("success", "Active"),
        "PAUSED": ("neutral", "Paused"),
        "RETIRED": ("neutral", "Retired"),
        "HEALTHY": ("success", "Healthy"),
        "DEGRADED": ("warning", "Degraded"),
        "WARNING": ("warning", "Degraded"),
        # One health vocabulary everywhere: Healthy · Degraded · Failed · No data.
        "DOWN": ("danger", "Failed"),
        "UNKNOWN": ("unknown", "No data" if kind == "health" else "Unknown"),
        "RUNNING": ("progress", "Running"),
        "QUEUED": ("progress", "Queued"),
        "SUCCEEDED": ("success", "Successful"),
        "FAILED": ("danger", "Failed"),
        "AVAILABLE": ("success", "Available"),
        "UNAVAILABLE": ("danger", "Unavailable"),
        "NONE": ("neutral", "None"),
    }
    pill_kind, label = labels.get(normalized, ("neutral", normalized.replace("_", " ").title()))
    return _status_pill(pill_kind, label, value=normalized)


def _provider_url(value: Any, *, label: str | None = None) -> str:
    raw = str(value or "").strip()
    if not raw:
        return "<span class='muted-value'>—</span>"
    escaped = html.escape(raw, quote=True)
    text = html.escape(label or raw)
    if raw.startswith(("https://", "http://")):
        return f"<a href='{escaped}' target='_blank' rel='noopener noreferrer'>{text} {_admin_icon('external')}</a>"
    return text


def _provider_source_label(value: Any) -> str:
    # Source details are already collapsed; show the full URL when expanded.
    return str(value or "").strip() or "—"


def _provider_source_type_label(value: Any) -> str:
    labels = {
        "WEBSITE": "Website",
        "CATALOG": "Catalog",
        "LICENSE": "License",
        "DOWNLOAD": "Package download",
    }
    normalized = str(value or "").strip().upper()
    return labels.get(normalized, normalized.title() or "Source")


def _provider_check_badge(value: Any) -> str:
    return _provider_status_badge(value, kind="health")


def _provider_health_counts(health: dict[str, Any] | None) -> tuple[int, int]:
    if not health:
        return 0, 0
    component_keys = (
        "website_status", "catalog_status", "redirect_status", "download_status",
        "mime_status", "magic_status", "zip_status", "img_status",
        "last_update_status",
    )
    passed = sum(1 for key in component_keys if str(health.get(key) or "").upper() == "HEALTHY")
    not_evaluated = sum(1 for key in component_keys if str(health.get(key) or "UNKNOWN").upper() == "UNKNOWN")
    return passed, not_evaluated


def _provider_health_attention_count(health: dict[str, Any]) -> int:
    return sum(str(health.get(key) or "").upper() in {"DOWN", "DEGRADED"}
               for key in ("website_status", "catalog_status", "redirect_status", "download_status",
                           "mime_status", "magic_status", "zip_status", "img_status", "last_update_status"))


def _provider_action_label(value: Any) -> str:
    labels = {
        "provider.health_checked": "Health checked",
        "provider.catalog_collected": "Catalog collected",
        "provider.catalog_collection_failed": "Catalog collection failed",
        "provider.status_changed": "Status changed",
        "provider.retired": "Provider retired",
        "provider.health_schedule_changed": "Health check interval changed",
        "provider.previews_enabled": "Map style previews turned on",
        "provider.previews_disabled": "Map style previews turned off",
        "package.downloads_disabled": "Map downloads disabled",
        "package.downloads_enabled": "Map downloads enabled",
    }
    raw = str(value or "").strip()
    return labels.get(raw, raw.replace("_", " ").title() or "Provider action")


def _provider_action_button(
    provider_id: str,
    action: str,
    label: str,
    *,
    status: str | None = None,
    secondary: bool = False,
    disabled: bool = False,
) -> str:
    attributes = (
        f" data-provider-status='{html.escape(status, quote=True)}'" if status else ""
    )
    class_name = "secondary-button" if secondary else ""
    disabled_attribute = " disabled" if disabled else ""
    return (
        f"<button type='button' class='{class_name}' data-provider-action='{html.escape(action, quote=True)}'"
        f" data-provider-id='{html.escape(provider_id, quote=True)}'{attributes}{disabled_attribute}>"
        f"{html.escape(label)}</button>"
    )


_PREVIEW_STATUS_LABELS = {
    "AVAILABLE": "Published",
    "NOT_COVERED": "Not covered",
    "PENDING": "Waiting",
    "FAILED": "Failed",
}


def _provider_preview_state(previews: dict[str, Any] | None) -> tuple[bool, list[dict[str, Any]], dict[str, int]]:
    """Switch state, render results and per-state counts of one provider's map style previews."""
    previews = previews or {}
    enabled = bool(previews.get("enabled"))
    layers = list(previews.get("layers") or [])
    counts = {key: 0 for key in _PREVIEW_STATUS_LABELS}
    for layer in layers:
        key = str(layer.get("status") or "PENDING").upper()
        counts[key] = counts.get(key, 0) + 1
    return enabled, layers, counts


def _provider_preview_button(provider_id: str, status: str, enabled: bool) -> str:
    """The previews switch; a secondary action in the provider action bar."""
    label = "Turn previews off" if enabled else "Turn previews on"
    disabled = " disabled" if status == "RETIRED" else ""
    return (
        f"<button type='button' class='secondary-button' data-provider-action='previews'"
        f" data-provider-id='{html.escape(provider_id, quote=True)}'"
        f" data-previews-enabled='{'false' if enabled else 'true'}'{disabled}>{label}</button>"
    )


def _provider_preview_tile(enabled: bool, layers: list[dict[str, Any]], counts: dict[str, int]) -> str:
    """Compact preview status: on/off plus only the layer states that occur."""
    parts = [f"{counts[key]} {label.lower()}" for key, label in _PREVIEW_STATUS_LABELS.items() if counts.get(key)]
    secondary = " · ".join(parts) if parts else ("No layers rendered yet" if enabled else "No layers")
    return _metric_tile(
        "Previews", "On" if enabled else "Off", fmt="text",
        value_html=_status_pill("success", "On") if enabled else _status_pill("neutral", "Off"),
        secondary=html.escape(secondary),
    )


def _provider_preview_rows(layers: list[dict[str, Any]]) -> str:
    return "".join(
        "<tr>"
        f"<td data-label='Area'><code>{html.escape(str(layer.get('area_id') or ''))}</code></td>"
        f"<td data-label='Style'>{html.escape(str(layer.get('style_id') or ''))}</td>"
        f"<td data-label='State' class='column-status'>{_provider_status_badge(_PREVIEW_STATUS_LABELS.get(str(layer.get('status') or '').upper(), 'Waiting'))}</td>"
        f"<td data-label='Package'>{html.escape(str(layer.get('package_id') or '—'))}<small class='table-secondary'>{html.escape(str(layer.get('package_version') or ''))}</small></td>"
        f"<td data-label='Rendered' class='column-date'>{_timestamp_markup(layer.get('rendered_at'))}</td>"
        f"<td data-label='Last problem' class='provider-reason-cell'>{html.escape(str(layer.get('error_code') or '—'))}"
        + (f"<small class='table-secondary'>{html.escape(str(layer.get('error_message')))}</small>" if layer.get('error_message') else "")
        + "</td></tr>"
        for layer in layers
    )


def _provider_summary_row(provider: dict[str, Any]) -> str:
    provider_id = str(provider.get("id") or "").strip()
    name = str(provider.get("name") or provider_id or "Unknown provider")
    status = str(provider.get("status") or "UNKNOWN")
    health = str(provider.get("health") or "UNKNOWN")
    affected_packages = _optional_nonnegative_int(provider.get("affectedPackageCount", provider.get("brokenPackageCount")))
    problematic_sources = _optional_nonnegative_int(provider.get("problematicSourceCount", provider.get("brokenUrlCount")))
    provider_href = html.escape(quote(provider_id, safe=""), quote=True)
    # Issues shows affected packages; unknown stays — (ADM-15), never 0. The
    # count is plain text like every other number cell (owner decision
    # 2026-10-06): danger text only when positive, no pill or icon.
    if affected_packages is None:
        issue_markup = "<span class='muted-value' title='Package issues not measured'>—<span class='sr-only'> Unknown</span></span>"
    elif affected_packages:
        sources = f" · {_count_label(problematic_sources, 'source')}" if problematic_sources is not None else ""
        noun = "package" if affected_packages == 1 else "packages"
        label = f"{affected_packages} {noun} with issues{sources}"
        issue_markup = (
            f"<span class='provider-issue-count is-positive' title='{html.escape(label, quote=True)}'>"
            f"{_admin_error_counter(affected_packages)} {noun}<span class='sr-only'> with issues</span>"
            f"{html.escape(sources)}</span>"
        )
    else:
        issue_markup = _admin_error_counter(0)
    issue_sort = f" data-sort-value='{affected_packages}'" if affected_packages is not None else ""
    package_value = _optional_count_label(provider.get("packageCount"))
    health_error = str(provider.get("lastHealthError") or "").strip()
    health_title = f" title='{html.escape(health_error, quote=True)}'" if health_error else ""
    latest_release = provider.get("latestRelease")
    latest_markup = (
        f"<small class='table-secondary'>Newest package: {html.escape(str(latest_release))}</small>"
        if latest_release else ""
    )
    return (
        "<tr>"
        f"<td><a class='provider-name-link' href='/admin/providers/{provider_href}'><strong>{html.escape(name)}</strong></a>{latest_markup}</td>"
        f"<td class='column-status'>{_provider_status_badge(status)}</td>"
        f"<td class='column-status'{health_title}>{_provider_status_badge(health, kind='health')}"
        + (f"<small class='table-secondary'>{html.escape(health_error)}</small>" if health_error else "")
        + "</td>"
        f"<td class='column-number numeric'>{html.escape(package_value)}</td>"
        f"<td class='column-number numeric'{issue_sort}>{issue_markup}</td>"
        f"<td class='column-date'>{_timestamp_markup(provider.get('lastCatalogSync'))}</td>"
        "</tr>"
    )


def providers_page(
    providers: list[dict[str, Any]] | dict[str, Any], user: dict[str, Any], csrf_token: str
) -> bytes:
    provider_rows = providers.get("providers", []) if isinstance(providers, dict) else providers
    provider_rows = list(provider_rows or [])
    rows = "".join(_provider_summary_row(provider) for provider in provider_rows)
    empty = _empty_state("empty", "No known providers are registered.") if not provider_rows else ""
    states = [_provider_problem_state(provider) for provider in provider_rows]
    tracked = [state for state in states if state["tracked"]]
    active = sum(1 for provider in provider_rows if str(provider.get("status")).upper() == "ACTIVE")
    healthy = sum(1 for provider in provider_rows if str(provider.get("health")).upper() == "HEALTHY")
    affected = [_optional_nonnegative_int(provider.get("affectedPackageCount", provider.get("brokenPackageCount"))) for provider in provider_rows]
    affected_total = sum(value for value in affected if value is not None) if affected and all(value is not None for value in affected) else None
    latest_sync = max(
        (parsed for parsed in (_parse_timestamp(provider.get("lastCatalogSync")) for provider in provider_rows) if parsed),
        default=None,
    )
    # One summary card like Installations, no scope chips under the numbers;
    # Last sync sits in the heading meta like Devices (owner decision 2026-10-06).
    summary = "" if not provider_rows else (
        "<section class='admin-card installation-kpis provider-summary' aria-label='Provider summary'>"
        + _metric_row([
            _metric_tile("Active", active, secondary=f"of {len(provider_rows)}", data_stat="active"),
            _metric_tile("Healthy", healthy, secondary=f"of {len(provider_rows)}", data_stat="healthy"),
            _metric_tile("Package issues", affected_total, failure=True, data_stat="packageIssues",
                         state=None if affected_total is not None else "unknown"),
            _metric_tile("Provider issues", sum(1 for state in tracked if state["problem"]), failure=True,
                         data_stat="providerIssues",
                         hint="Active providers with degraded or failed health, a failed or overdue catalog sync, or package issues"),
        ], label="Provider summary")
        + "</section>"
    )
    sync_value = _timestamp_markup(latest_sync) if latest_sync else "—<span class='sr-only'> Unknown</span>"
    sync_meta = "" if not provider_rows else (
        f"<p class='page-meta provider-summary-sync'><strong>Last sync</strong> {sync_value}</p>"
    )
    content = f"""
      {_admin_header(user, csrf_token, active='providers')}
      <main class='dashboard providers-page' id='main-content'>
        <div class='heading-row installation-heading'><div><h1>Providers</h1></div>{sync_meta}</div>
        {summary}
        {empty}
        <section class='provider-section' aria-label='Provider list'>
          <div class='table-wrap provider-table-wrap'><table class='admin-table'><caption class='sr-only'>Map provider status</caption><thead><tr><th scope='col'>Provider</th><th scope='col' class='column-status'>State</th><th scope='col' class='column-status'>Health</th><th scope='col' class='column-number'>Packages</th><th scope='col' class='column-number'>Issues</th><th scope='col' class='column-date'>Last sync</th></tr></thead><tbody id='provider-rows'>{rows}</tbody></table></div>
        </section>
      </main>
    """
    return _layout("Providers", content, sections={"providers": provider_rows})


def _provider_problem_groups(packages: list[dict[str, Any]]) -> dict[str, list[tuple[dict[str, Any], dict[str, Any]]]]:
    """Group failed/unavailable artifacts by their recorded reason."""
    groups: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = {}
    for package in packages:
        for artifact in package.get('artifacts') or []:
            if artifact.get('validation_status') not in {'UNAVAILABLE', 'FAILED'}:
                continue
            check = artifact.get('last_check') or {}
            reason = str(check.get('message') or 'No reason recorded. Check this package again.')
            groups.setdefault(reason, []).append((package, artifact))
    return dict(sorted(groups.items(), key=lambda item: (-len({p.get('id') for p, _ in item[1]}), item[0])))


def _provider_problem(package: dict[str, Any], artifact: dict[str, Any], provider_id: str, provider_name: str) -> str:
    check = artifact.get('last_check') or {}
    url = str(artifact.get('source_url') or '')
    diagnostic = {'package': package.get('id'), 'source': url, **check}
    name = _admin_map_display_name(package.get('country'), package.get('name'), package.get('region'), package.get('id'))
    kind = {'main': 'Main map', 'contours': 'Contours'}.get(str(artifact.get('kind') or 'main'), str(artifact.get('kind') or 'Main map'))
    action = str(check.get('nextAction') or 'Recheck to get current validation evidence.')
    return (
        "<li class='provider-problem'>"
        f"<div><strong>{html.escape(name)}</strong><small>{html.escape(provider_name)} · {html.escape(kind)} · {_timestamp_markup(check.get('checkedAt'))}</small>"
        f"<small>{html.escape(action)}</small></div>"
        "<div class='provider-problem-actions'>"
        f"<button type='button' class='secondary-button' data-provider-action='rechecks' data-provider-id='{html.escape(provider_id, quote=True)}' data-package-id='{html.escape(str(package.get('id')), quote=True)}'>Recheck</button>"
        f"{_provider_url(url, label='Open source')}"
        f"<button type='button' class='link-button' data-copy-diagnostic='{html.escape(json.dumps(diagnostic), quote=True)}'>Copy details</button>"
        "</div></li>"
    )


def _provider_package_row(package: dict[str, Any], provider_id: str = "") -> str:
    broken_count = _optional_nonnegative_int(package.get("broken_artifact_count"))
    availability = str(package.get("availability") or "UNKNOWN")
    is_broken = broken_count is not None and broken_count > 0
    row_class = " provider-package-broken" if is_broken else ""
    package_state = "FAILED" if is_broken else "UNKNOWN" if broken_count is None else availability
    broken_markup = _provider_status_badge(package_state)
    package_id = str(package.get("id") or "—")
    package_name = _admin_map_display_name(
        package.get("country"), package.get("name"), package.get("region"), package_id,
    )
    region = str(package.get("region") or "").strip()
    search = " ".join((package_id, package_name, region, str(package.get("release") or ""))).casefold()
    artifact_details = ""
    first_source = ""
    for artifact in package.get("artifacts") or []:
        url = str(artifact.get("source_url") or "")
        first_source = first_source or url
        source = html.escape(url)
        if url.startswith("https://"):
            source = f"<a href='{html.escape(url, quote=True)}' target='_blank' rel='noopener noreferrer'>{source}</a>"
        artifact_details += (
            f"<p><strong>{html.escape(str(artifact.get('kind') or ''))}</strong> · "
            f"{html.escape(str(artifact.get('validation_status') or 'UNKNOWN'))}<br>"
            f"Download: {_optional_count_label(artifact.get('size_bytes'), ' bytes')} · IMG: {_optional_count_label(artifact.get('install_size_bytes'), ' bytes')}<br>"
            f"Source date: {html.escape(str(artifact.get('source_updated_at') or 'Unknown'))}<br>{source}</p>"
        )
    disabled = bool(package.get("downloads_disabled"))
    note = str(package.get("downloads_disabled_reason") or "").strip()
    download_state = ""
    if disabled:
        download_state = (
            "<div class='provider-download-control'>"
            + _status_pill("warning", "Downloads disabled by admin", title=note or None)
            + (f"<small>{html.escape(note)}</small>" if note else "") + "</div>"
        )
    menu_items: list[str] = []
    if provider_id:
        menu_items.append(
            f"<button type='button' class='secondary-button' data-provider-action='rechecks' data-provider-id='{html.escape(provider_id, quote=True)}' data-package-id='{html.escape(package_id, quote=True)}'>Recheck</button>"
        )
        if availability != "RETIRED":
            menu_items.append(
                f"<button type='button' class='secondary-button' data-provider-action='downloads' data-provider-id='{html.escape(provider_id, quote=True)}' data-package-id='{html.escape(package_id, quote=True)}' data-downloads-enabled='{str(disabled).lower()}'>{'Enable downloads' if disabled else 'Disable downloads'}</button>"
            )
    if first_source.startswith(("https://", "http://")):
        menu_items.append(_provider_url(first_source, label="Open source"))
    if artifact_details:
        menu_items.append(
            f"<details class='admin-disclosure provider-artifact-details'><summary>Artifact details</summary>{artifact_details}</details>"
        )
    menu = (
        f"<details class='provider-row-menu'><summary aria-label='Actions for {html.escape(package_name, quote=True)}'>{_admin_icon('ellipsis')}<span class='sr-only'> Actions</span></summary>"
        f"<div class='provider-row-menu-body'>{''.join(menu_items)}</div></details>"
        if menu_items else ""
    )
    return (
        f"<tr class='{row_class.strip()}' data-package-search='{html.escape(search, quote=True)}' data-package-state='{html.escape(availability,quote=True)}' data-package-broken='{str(is_broken).lower()}'><td><span class='provider-package-name'>{html.escape(package_name)}</span><code class='provider-package-id'>{html.escape(package_id)}</code>{f'<small>{html.escape(region)}</small>' if region and region.casefold() != package_name.casefold() else ''}</td>"
        f"<td>{html.escape(str(package.get('release') or '—'))}</td><td class='column-number numeric'>{_optional_count_label(package.get('artifact_count'))}</td>"
        f"<td class='column-status'>{broken_markup}{f' <small>{broken_count} need attention</small>' if is_broken else ''}{download_state}</td>"
        f"<td class='column-status provider-row-actions'>{menu}</td></tr>"
    )


def _provider_source_row(source: dict[str, Any]) -> str:
    source_type = str(source.get("source_type") or "").upper()
    source_url = str(source.get("source_url") or "")
    source_label = _provider_source_label(source_url)
    search = " ".join((source_type, source_url)).casefold()
    broken = str(source.get("validation_status") or "").upper() in {"FAILED", "UNAVAILABLE"}
    return (
        f"<tr data-source-type='{html.escape(source_type, quote=True)}' data-source-search='{html.escape(search, quote=True)}' data-source-broken='{str(broken).lower()}'><td data-label='Source'>{html.escape({'main': 'Main map', 'contours': 'Contours'}.get(source.get('artifact_kind'), _provider_source_type_label(source_type)))}</td>"
        f"<td data-label='Original link' class='provider-url-cell' title='{html.escape(source_url, quote=True)}'>{_provider_url(source_url, label=source_label)}</td>"
        f"<td data-label='Status' class='column-status'>{_provider_status_badge(str(source.get('validation_status') or 'UNKNOWN') if source.get('enabled', True) else 'PAUSED')}</td>"
        f"<td data-label='Last checked' class='column-date'>{_timestamp_markup(source.get('last_checked_at'))}</td></tr>"
    )


def _provider_current_health(health: dict[str, Any], provider: dict[str, Any]) -> str:
    monitoring = provider.get("monitoring") or {}
    reason = str(health.get("error_detail") or health.get("error_code") or "").strip()
    provider_status = str(provider.get("status") or "ACTIVE").upper()
    next_check = ("Automatic checks paused" if provider_status == "PAUSED" else
                  "Automatic checks stopped" if provider_status == "RETIRED" else
                  _timestamp_markup(monitoring.get("nextCheckAt")))
    components = (
        ("website_status", "Website"), ("catalog_status", "Catalog"),
        ("download_status", "Download server"), ("redirect_status", "Redirects"),
        ("mime_status", "Content type"), ("magic_status", "File signature"),
        ("zip_status", "Archive"), ("img_status", "Map image"),
        ("last_update_status", "Catalog freshness"),
    )
    checks = "".join(f"<div><dt>{label}</dt><dd>{_provider_check_badge(health.get(key))}</dd></div>" for key, label in components)
    stale = "<p class='provider-attention'><strong>Check overdue.</strong> The last result may no longer reflect availability.</p>" if monitoring.get("stale") else ""
    block = str(provider.get("downloadBlockReason") or "")
    block_message = {
        "STATUS_STALE": "Downloads are waiting for a fresh provider availability check. Run Check provider health or wait for the scheduled check.",
        "PROVIDER_DOWN": "Downloads unavailable: the provider download server did not respond to the latest check. Try again later.",
        "PROVIDER_RATE_LIMITED": "Downloads are temporarily unavailable because the provider requested a cooldown. Try again later.",
        "PROVIDER_PAUSED": "Downloads paused by an administrator.",
        "PROVIDER_RETIRED": "Downloads unavailable: this provider is retired.",
    }.get(block, "Downloads are blocked by the current provider policy." if block else "No provider-wide download block. Package checks and admin settings still apply.")
    if not health:
        return "<p class='empty'>No health checks recorded yet.</p>" + stale + f"<p>Next check: {next_check}</p>"
    reason_markup = f"<p class='provider-current-reason'><strong>Observed issue:</strong> {html.escape(reason)}</p>" if reason else ""
    return (
        f"<div class='provider-current-health'>{stale}<p>{html.escape(block_message)}</p>{reason_markup}"
        f"<dl class='provider-health-facts'><div><dt>Last checked</dt><dd>{_timestamp_markup(health.get('checked_at'))}</dd></div><div><dt>Next scheduled check</dt><dd>{next_check}</dd></div></dl>"
        f"<dl class='provider-health-checks'>{checks}</dl>"
        f"<p class='table-help'>HTTP: {_optional_count_label(health.get('http_status'))} · Artifacts sampled: {_optional_count_label(health.get('artifact_count'))} · Duration: {_optional_count_label(health.get('duration_ms'), ' ms')}</p>"
        "<p class='table-help'>Results describe the latest check from the Terento server. Missing evidence is not a failed check; this does not verify a complete download or installation.</p></div>"
    )


def _provider_health_history_item(health: dict[str, Any]) -> str:
    passed, missing = _provider_health_counts(health)
    reason = str(health.get("error_detail") or health.get("error_code") or "").strip()
    return (
        f"<li><div>{_timestamp_markup(health.get('checked_at'))}{_provider_status_badge(health.get('status'), kind='health')}</div>"
        f"<small>{passed} passed · {_provider_health_attention_count(health)} need attention · {missing} not evaluated</small>"
        + (f"<p>{html.escape(reason)}</p>" if reason else "") + "</li>"
    )


def _provider_health_row(health: dict[str, Any]) -> str:
    components = (
        ("website_status", "Website"), ("catalog_status", "Catalog"),
        ("redirect_status", "Redirects"), ("download_status", "Download"),
        ("mime_status", "MIME"), ("magic_status", "Magic bytes"),
        ("zip_status", "ZIP"), ("img_status", "IMG"),
        ("last_update_status", "Freshness"),
    )
    component_markup = " ".join(
        f"<span class='provider-component'><span>{html.escape(label)}</span>{_provider_check_badge(health.get(key))}</span>"
        for key, label in components
    )
    error = str(health.get("error_code") or health.get("error_detail") or "").strip()
    error_markup = (
        f"<span class='provider-error' title='{html.escape(error, quote=True)}'>{html.escape(error)}</span>"
        if error else "<span class='muted-value'>—</span>"
    )
    http_status = _optional_nonnegative_int(health.get("http_status"))
    if http_status is not None and not 100 <= http_status <= 599:
        http_status = None
    return (
        f"<tr><td class='column-date'>{_timestamp_markup(health.get('checked_at'))}</td><td class='column-status'>{_provider_status_badge(health.get('status'), kind='health')}</td>"
        f"<td class='column-status'><div class='provider-component-list'>{component_markup}</div></td><td class='column-number'>{_optional_count_label(http_status)}</td>"
        f"<td class='column-number'>{_optional_count_label(health.get('artifact_count'))}</td><td class='column-number'>{_optional_count_label(health.get('duration_ms'), ' ms')}</td>"
        f"<td>{error_markup}</td></tr>"
    )


def _provider_update_count(run: dict[str, Any]) -> str:
    new, updated = run.get('new_package_count'), run.get('updated_package_count')
    if run.get('status') != 'SUCCEEDED' or new is None or updated is None:
        return "<span class='muted-value' title='Update count was not recorded for this collection'>—</span>"
    return f"<strong>{int(new) + int(updated)}</strong><small class='table-secondary'>{int(new)} new · {int(updated)} updated</small>"


def _provider_run_row(run: dict[str, Any]) -> str:
    error = str(run.get("error_code") or run.get("error_detail") or "").strip()
    error_markup = html.escape(error) if error else "<span class='muted-value'>—</span>"
    return (
        f"<tr><td data-label='Run'><code>{html.escape(str(run.get('id') or '—'))}</code></td><td data-label='Started' class='column-date'>{_timestamp_markup(run.get('started_at'))}</td>"
        f"<td data-label='Finished' class='column-date'>{_timestamp_markup(run.get('finished_at'))}</td><td data-label='Result' class='column-status'>{_provider_status_badge(run.get('status'))}<small class='table-secondary'>{'Release change detected' if run.get('release_change_detected') is True else 'No release change detected' if run.get('release_change_detected') is False else 'Release change not recorded'} · {html.escape(str(run.get('latest_release') or '—'))}</small></td>"
        f"<td data-label='Updates' class='column-number numeric'>{_provider_update_count(run)}</td><td data-label='Packages' class='column-number numeric'>{_optional_count_label(run.get('package_count'))}</td><td data-label='Files' class='column-number numeric'>{_optional_count_label(run.get('artifact_count'))}</td>"
        f"<td data-label='Error' class='provider-reason-cell'>{error_markup}</td></tr>"
    )


def _provider_audit_row(audit: dict[str, Any]) -> str:
    details = audit.get("details")
    changes_markup = ""
    if audit.get('action') == 'CATALOG_RELEASES_UPDATED' and isinstance(details, dict):
        changes = [
            f"<li>{html.escape(str(item.get('region') or item.get('packageId') or 'Map'))}: {html.escape(str(item.get('previousRelease') or '—'))} → {html.escape(str(item.get('release') or '—'))}</li>"
            for item in details.get('packages', []) if isinstance(item, dict)
        ]
        # A long change list shows three items and keeps the rest one click away.
        changes_markup = "<ul class='catalog-release-changes'>" + ''.join(changes[:3]) + "</ul>"
        if len(changes) > 3:
            changes_markup += (
                f"<details class='admin-disclosure catalog-release-more'><summary>+{len(changes) - 3} more</summary>"
                f"<ul class='catalog-release-changes'>{''.join(changes[3:])}</ul></details>"
            )
    technical_values = {
        "adminUserId": audit.get("admin_user_id"),
        "target": audit.get("target"),
        "details": details,
    }
    technical_text = json.dumps(
        {key: value for key, value in technical_values.items() if value not in (None, "", {})},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    old_status, new_status = str(audit.get('old_status') or ''), str(audit.get('new_status') or '')
    status_change = (
        f"{html.escape(old_status.title() or '—')} → {html.escape(new_status.title() or '—')}"
        if old_status or new_status else "<span class='muted-value'>—</span>"
    )
    return (
        f"<tr><td data-label='Action' title='{html.escape(str(audit.get('action') or ''), quote=True)}'>{html.escape(_provider_action_label(audit.get('action')))}</td>"
        f"<td data-label='Status change' class='column-status{'' if old_status or new_status else ' is-empty'}'>{status_change}</td>"
        f"<td data-label='Reason' class='provider-reason-cell'>{html.escape(str(audit.get('reason') or '—'))}{changes_markup}</td><td data-label='Time' class='column-date'>{_timestamp_markup(audit.get('occurred_at'))}</td>"
        f"<td data-label='Details'><details class='audit-technical-details admin-disclosure'><summary>Raw record</summary><code>{html.escape(technical_text if technical_text != '{}' else '—')}</code></details></td></tr>"
    )


def _provider_technical_tabs(panels: list[tuple[str, str, str, str, int | None]], *, topics: str) -> str:
    """Technical details: one switcher, one visible panel (owner decision 2026-10-06).

    ``panels`` holds (key, label, panel id, body, count). The first panel is
    selected; the others render hidden and the provider script switches them.
    """
    tabs = "".join(
        f"<button type='button' role='tab' class='quick-filter{' active' if index == 0 else ''}' "
        f"id='provider-technical-tab-{key}' data-technical-tab='{key}' aria-controls='{panel_id}' "
        f"aria-selected='{'true' if index == 0 else 'false'}' tabindex='{0 if index == 0 else -1}'>"
        f"{html.escape(label)}" + (f" <span class='provider-tab-count'>{count}</span>" if count is not None else "")
        + "</button>"
        for index, (key, label, panel_id, _, count) in enumerate(panels)
    )
    bodies = "".join(
        f"<div class='provider-technical-panel' role='tabpanel' id='{panel_id}' aria-labelledby='provider-technical-tab-{key}' "
        f"data-technical-panel='{key}' tabindex='0'{'' if index == 0 else ' hidden'}>{body}</div>"
        for index, (key, _, panel_id, body, _) in enumerate(panels)
    )
    return (
        "<section class='admin-card provider-technical-card' id='provider-technical-details' aria-labelledby='provider-technical-details-title'>"
        "<details class='provider-technical-disclosure' id='provider-technical-disclosure'>"
        f"<summary><span class='provider-technical-chevron'>{_admin_icon('chevron-right')}</span>"
        "<h2 id='provider-technical-details-title'>Technical details</h2>"
        f"<span class='disclosure-meta'>{html.escape(topics)}</span></summary>"
        "<div class='provider-technical-body'>"
        f"<div class='filter-bar provider-technical-switcher'><div class='quick-filter-group' role='tablist' aria-label='Technical details sections'>{tabs}</div></div>"
        f"{bodies}</div></details></section>"
    )


def provider_detail_page(
    detail: dict[str, Any], runs: list[dict[str, Any]], audits: list[dict[str, Any]],
    user: dict[str, Any], csrf_token: str,
) -> bytes:
    runs = runs[:10]
    audits = audits[:10]
    provider = detail.get("provider", detail)
    provider_id = str(provider.get("id") or "").strip()
    name = str(provider.get("name") or provider_id or "Provider")
    status = str(provider.get("status") or "UNKNOWN").upper()
    health_record = provider.get("health") if isinstance(provider.get("health"), dict) else {}
    health = str(provider.get("healthStatus") or health_record.get("status") or provider.get("health") or "UNKNOWN").upper()
    packages = [
        package for package in list(provider.get("maps") or [])
        if str(package.get("availability") or "").upper() != "RETIRED"
    ]
    sources = list(provider.get("sources") or [])
    provider_sources = [source for source in sources if str(source.get("source_type") or "").upper() != "DOWNLOAD"]
    download_sources = [source for source in sources if str(source.get("source_type") or "").upper() == "DOWNLOAD"]
    health_history = list(provider.get("healthHistory") or [])
    affected_package_count = _optional_nonnegative_int(provider.get("affectedPackageCount"))
    if affected_package_count is None:
        affected_values = [_optional_nonnegative_int(package.get("broken_artifact_count")) for package in packages]
        affected_package_count = (
            sum(value > 0 for value in affected_values if value is not None)
            if all(value is not None for value in affected_values) else None
        )
    release_counts: dict[str, int] = {}
    for package in packages:
        release = str(package.get('release') or 'Not recorded')
        release_counts[release] = release_counts.get(release, 0) + 1
    release_summary = ' · '.join(
        f"{html.escape(release)}: {count} packages"
        for release, count in sorted(release_counts.items(), reverse=True)
    ) or 'No package releases recorded.'
    latest_health = health_record or (health_history[0] if health_history else {})
    previous_health = [
        item for item in health_history
        if (item.get("id") != latest_health.get("id") if item.get("id") is not None and latest_health.get("id") is not None
            else item.get("checked_at") != latest_health.get("checked_at"))
    ][:10]
    health_passed, health_not_evaluated = _provider_health_counts(latest_health)
    latest_health_status = str(latest_health.get("status") or health or "UNKNOWN").upper()
    latest_run = runs[0] if runs else {}
    latest_run_status = str(latest_run.get("status") or "NONE").upper()
    activation_gate = provider.get("activationGate")
    if not isinstance(activation_gate, dict):
        activation_gate = {}
    can_activate = bool(activation_gate.get("canActivate"))
    activation_blockers = [
        str(item.get("message") or "")
        for item in activation_gate.get("blockers", [])
        if isinstance(item, dict) and str(item.get("message") or "")
    ]
    state_button = ""
    if status != "RETIRED":
        next_status = "PAUSED" if status == "ACTIVE" else "ACTIVE"
        state_button = _provider_action_button(
            provider_id, "state", "Pause" if next_status == "PAUSED" else "Activate",
            status=next_status, secondary=True, disabled=next_status == "ACTIVE" and not can_activate,
        )
    activation_note = ""
    if status != "ACTIVE" and status != "RETIRED" and not can_activate:
        if not activation_blockers:
            activation_blockers = ["Activation checks are not available."]
        activation_note = (
            "<p class='provider-activation-note' role='status'><strong>Activation blocked.</strong> "
            + html.escape(" ".join(activation_blockers)) + "</p>"
        )
    previews_enabled, preview_layers, preview_counts = _provider_preview_state(provider.get("previews"))
    action_provider = provider_id if status != "RETIRED" else ""
    rows_packages = "".join(_provider_package_row(package, action_provider) for package in packages)
    rows_sources = "".join(_provider_source_row(source) for source in provider_sources)
    artifact_kinds = {str(a.get("source_url") or ""): str(a.get("kind") or "main")
                      for package in packages for a in package.get("artifacts") or []}
    typed_sources = [dict(source, artifact_kind=artifact_kinds.get(str(source.get("source_url") or ""), "unknown")) for source in download_sources]
    contour_sources = sum(source["artifact_kind"] == "contours" for source in typed_sources)
    main_sources = sum(source["artifact_kind"] == "main" for source in typed_sources)
    rows_download_sources = "".join(_provider_source_row(source) for source in typed_sources)
    rows_health = "".join(_provider_health_history_item(item) for item in previous_health)
    rows_runs = "".join(_provider_run_row(run) for run in runs)
    rows_audits = "".join(_provider_audit_row(audit) for audit in audits)
    empty_packages = _empty_state("empty", "No catalog packages collected yet.") if not packages else ""
    # Rarely needed lists start short; the provider script adds "Show N more"
    # (no pagination, nothing removed from the page).
    source_table = f"<div class='table-wrap provider-table-wrap'><table class='admin-table provider-source-table mobile-record-table'><caption class='sr-only'>Provider-level original sources</caption><thead><tr><th scope='col'>Source</th><th scope='col'>Original link</th><th scope='col' class='column-status'>Status</th><th scope='col' class='column-date'>Last checked</th></tr></thead><tbody data-row-limit='10'>{rows_sources}</tbody></table></div>" if provider_sources else "<p class='empty'>No provider source links recorded.</p>"
    download_source_table = f"<div class='table-wrap provider-table-wrap'><table class='admin-table provider-source-table mobile-record-table'><caption class='sr-only'>Download source URLs</caption><thead><tr><th scope='col'>Source</th><th scope='col'>Original link</th><th scope='col' class='column-status'>Status</th><th scope='col' class='column-date'>Last checked</th></tr></thead><tbody id='provider-download-source-rows'>{rows_download_sources}</tbody></table></div>" if download_sources else ""
    package_table = f"<div class='table-wrap provider-table-wrap'><table class='admin-table provider-package-table'><caption class='sr-only'>Packages</caption><thead><tr><th scope='col'>Map</th><th scope='col'>Release</th><th scope='col' class='column-number'>Files</th><th scope='col' class='column-status'>State</th><th scope='col' class='column-status'><span class='sr-only'>Actions</span></th></tr></thead><tbody id='provider-package-rows'>{rows_packages}</tbody></table></div>" if packages else ""
    latest_health_table = _provider_current_health(latest_health, provider)
    monitoring = provider.get("monitoring") or {}
    schedule_options = "".join(f"<option value='{hours}'{' selected' if monitoring.get('intervalHours', 1) == hours else ''}>Every {hours} {'hour' if hours == 1 else 'hours'}</option>" for hours in (1, 6, 24))
    # One control row: label, native select (a POST action, so no data-admin-dropdown) and Save, one height.
    schedule = f"<div class='provider-health-schedule'><label for='provider-health-interval'>Automatic health checks</label><select id='provider-health-interval'{ ' disabled' if status == 'RETIRED' else ''}>{schedule_options}</select>{_provider_action_button(provider_id, 'health-schedule', 'Save interval', secondary=True, disabled=status == 'RETIRED')}</div>"
    run_table = f"<div class='table-wrap provider-table-wrap'><table class='admin-table provider-run-table mobile-record-table'><caption class='sr-only'>Catalog collection runs</caption><thead><tr><th scope='col'>Run</th><th scope='col' class='column-date'>Started</th><th scope='col' class='column-date'>Finished</th><th scope='col' class='column-status'>Result</th><th scope='col' class='column-number' title='New and changed packages; — means not recorded'>Updates</th><th scope='col' class='column-number'>Packages</th><th scope='col' class='column-number'>Files</th><th scope='col'>Error</th></tr></thead><tbody data-row-limit='5'>{rows_runs}</tbody></table></div>" if runs else "<p class='empty'>No catalog collection runs recorded yet.</p>"
    audit_table = f"<div class='table-wrap provider-table-wrap'><table class='admin-table provider-audit-table mobile-record-table'><caption class='sr-only'>Provider audit history</caption><thead><tr><th scope='col'>Action</th><th scope='col' class='column-status'>Status change</th><th scope='col'>Reason</th><th scope='col' class='column-date'>Time</th><th scope='col'>Details</th></tr></thead><tbody data-row-limit='5'>{rows_audits}</tbody></table></div>" if audits else "<p class='empty'>No provider audit entries recorded yet.</p>"
    preview_table = (
        "<div class='table-wrap provider-table-wrap'><table class='admin-table provider-preview-table mobile-record-table'><caption class='sr-only'>Map style preview layers</caption>"
        "<thead><tr><th scope='col'>Area</th><th scope='col'>Style</th><th scope='col' class='column-status'>State</th>"
        "<th scope='col'>Package</th><th scope='col' class='column-date'>Rendered</th><th scope='col'>Last problem</th></tr></thead>"
        f"<tbody data-row-limit='10'>{_provider_preview_rows(preview_layers)}</tbody></table></div>"
        if preview_layers else "<p class='empty'>No preview layers rendered yet.</p>"
    )
    health_summary = (
        f"{_provider_status_badge(latest_health_status, kind='health')} "
        f"<span>{health_passed} passed · {_provider_health_attention_count(latest_health)} need attention · {health_not_evaluated} not evaluated</span>"
        if latest_health else "<span class='muted-value'>No health check recorded yet.</span>"
    )
    if monitoring.get("stale"):
        health_summary += " " + _status_pill("warning", "Check overdue")

    # --- Summary: one card of tiles, like Installations (owner decision 2026-10-06) ---
    disabled_maps = sum(1 for package in packages if package.get("downloads_disabled"))
    block = str(provider.get("downloadBlockReason") or "")
    tiles = _metric_row([
        _metric_tile("Health", latest_health_status.title(), fmt="text",
                     value_html=_provider_status_badge(latest_health_status if latest_health else "UNKNOWN", kind="health"),
                     secondary=f"Last check {_timestamp_markup(latest_health.get('checked_at') or provider.get('lastHealthCheck'))}"),
        _metric_tile("Catalog", latest_run_status.title(), fmt="text",
                     value_html=_provider_status_badge(latest_run_status) if latest_run else _status_pill("unknown", "No runs"),
                     secondary=f"Sync {_timestamp_markup(provider.get('lastCatalogSync'))}"),
        _metric_tile("Package issues", affected_package_count, failure=True,
                     secondary=f"of {_optional_count_label(len(packages))} packages"),
        _metric_tile("Downloads", "Blocked" if block else "Allowed", fmt="text",
                     value_html=_status_pill("danger", "Blocked", title=block) if block else _status_pill("success", "Allowed"),
                     secondary=_count_label(disabled_maps, "map disabled", "maps disabled") if disabled_maps else "No maps disabled"),
        _provider_preview_tile(previews_enabled, preview_layers, preview_counts),
    ], label="Provider summary")
    summary_card = f"<section class='admin-card installation-kpis provider-kpis' aria-label='Provider summary'>{tiles}</section>"

    # --- Issues grouped by reason (preview five per group) ---------------------
    groups = _provider_problem_groups(packages)
    group_markup: list[str] = []
    for reason, items in groups.items():
        package_ids = list(dict.fromkeys(str(package.get("id")) for package, _ in items))
        preview = "".join(_provider_problem(package, artifact, provider_id, name) for package, artifact in items[:5])
        more = (
            f"<p class='provider-problem-more'><a href='#provider-packages' data-show-problems>Show all {len(items)} in Packages</a></p>"
            if len(items) > 5 else ""
        )
        recheck = (
            f"<button type='button' class='secondary-button' data-provider-action='rechecks' data-provider-id='{html.escape(provider_id, quote=True)}' data-package-id='{html.escape(package_ids[0], quote=True)}'>Recheck</button>"
            if len(package_ids) == 1 else
            f"<button type='button' class='secondary-button' data-provider-action='rechecks' data-provider-id='{html.escape(provider_id, quote=True)}' title='Rechecks every affected package of this provider'>Recheck affected</button>"
        )
        group_markup.append(
            "<details class='provider-problem-group' open"
            + f"><summary>{_status_pill('danger', _count_label(len(package_ids), 'package'))}<span class='provider-problem-reason'>{html.escape(reason)}</span></summary>"
            f"<div class='provider-problem-group-body'><div class='provider-problem-group-actions'>{recheck if status != 'RETIRED' else ''}</div><ul class='provider-problem-list'>{preview}</ul>{more}</div></details>"
        )
    if affected_package_count is None and not groups:
        problems_body = _empty_state("unavailable", "Issue count unavailable.", action=("#provider-packages", "Review packages"))
    elif not groups:
        problems_body = _empty_state("empty", "No known package issues.")
    else:
        problems_body = "".join(group_markup)
    problems_section = _section_card(
        "Issues",
        f"<p id='provider-recheck-progress' role='status'></p>{problems_body}",
        card_id="provider-problems",
        css="provider-problems-card",
    ).replace(
        "</header>",
        (_provider_action_button(provider_id, 'rechecks', 'Recheck affected packages', disabled=status == 'RETIRED') if groups else "") + "</header>",
        1,
    )
    collection_summary = (
        f"<div>{_provider_status_badge(latest_run_status)}</div>"
        f"<span>{_optional_count_label(latest_run.get('package_count'), ' packages')} · "
        f"{_optional_count_label(latest_run.get('artifact_count'), ' files')} · "
        f"{_timestamp_markup(latest_run.get('finished_at') or latest_run.get('started_at'))}</span>"
        if latest_run else "<span class='muted-value'>No collection run recorded yet.</span>"
    )
    latest_run_error = str(latest_run.get("error_code") or latest_run.get("error_detail") or "").strip()
    sync_facts = (
        "<dl class='provider-health-facts provider-sync-facts'>"
        f"<div><dt>Catalog sync</dt><dd>{_timestamp_markup(provider.get('lastCatalogSync'))}</dd></div>"
        f"<div><dt>Updates in latest run</dt><dd>{_provider_update_count(latest_run) if latest_run else '—'}</dd></div>"
        + (f"<div><dt>Latest error</dt><dd>{html.escape(latest_run_error)}</dd></div>" if latest_run_error else "")
        + "</dl>"
    )
    previous_checks = _count_label(len(previous_health), 'previous check', 'previous checks')
    checks_section = _section_card(
        "Checks",
        f"<div class='provider-latest-summary'><div>{health_summary}</div><span>{_timestamp_markup(latest_health.get('checked_at') or provider.get('lastHealthCheck'))}</span></div>"
        f"{schedule}"
        f"<details class='admin-disclosure' id='provider-health-details'><summary>View check details</summary><div class='disclosure-body'>{latest_health_table}</div></details>"
        f"<p class='provider-card-link'><a class='section-link' href='#provider-health-history' data-technical-open='health'>Health check history <span class='disclosure-meta'>· {previous_checks}</span></a></p>",
        card_id="provider-checks", css="provider-state-card",
    )
    syncs_section = _section_card(
        "Syncs",
        f"<div class='provider-latest-summary'>{collection_summary}</div>{sync_facts}"
        f"<p class='provider-card-link'><a class='section-link' href='#provider-collection-history' data-technical-open='syncs'>Collection history <span class='disclosure-meta'>· {_count_label(len(runs), 'run')}</span></a></p>",
        card_id="provider-syncs", css="provider-state-card",
    )
    packages_section = _section_card(
        "Packages",
        f"<div class='filter-bar provider-filter-bar'>{_quick_select_filter('provider-package-filter', [('all', 'All'), ('broken', 'Issues'), ('available', 'Available')], 'broken' if groups else 'all', label='Package status')}<label class='filter-search'><span class='sr-only'>Search packages</span><input id='provider-package-search' type='search' placeholder='Search packages' autocomplete='off'></label><label><span class='sr-only'>Package page size</span><select id='provider-package-page-size' data-admin-dropdown><option value='25'>25 per page</option><option value='50'>50 per page</option></select></label><p class='results-count'>{len(packages)} catalog entries</p></div>{empty_packages}{package_table}<div class='provider-pagination' id='provider-package-pagination' aria-live='polite'></div>",
        card_id="provider-packages",
    )

    # --- Technical details: rarely needed lists behind one switcher ------------
    health_panel = (
        f"<p class='table-help'>Up to 10 previous checks from the last 30 days.</p><ol class='provider-health-history' data-row-limit='5'>{rows_health}</ol>"
        if previous_health else "<p class='empty'>No previous health checks recorded.</p>"
    )
    syncs_panel = (
        f"<p class='table-help'>Last 10 runs · Catalog sync {_timestamp_markup(provider.get('lastCatalogSync'))}</p>{run_table}"
        f"<h3 class='provider-technical-heading'>Releases</h3><p class='provider-technical-text'>{release_summary}</p>"
        "<p class='table-help'>Each region keeps its own provider release.</p>"
    )
    history_panel = f"<p class='table-help'>Last 10 actions; older audit records are retained.</p>{audit_table}"
    previews_panel = (
        "<p class='table-help'>When on, the scheduler temporarily downloads this provider's maps during the nightly "
        "preview window to draw comparison tiles for the public Map styles page, then deletes the downloads.</p>"
        f"{preview_table}"
    )
    attribution_panel = (
        "<h3 class='provider-technical-heading'>Attribution</h3>"
        f"<dl class='provider-information-list'><div><dt>Provider ID</dt><dd><code>{html.escape(provider_id)}</code></dd></div><div><dt>Adapter</dt><dd><code>{html.escape(str(provider.get('adapterId') or '—'))}</code></dd></div><div><dt>Website</dt><dd>{_provider_url(provider.get('website'))}</dd></div><div><dt>License</dt><dd>{html.escape(str(provider.get('license') or '—'))}</dd></div><div><dt>Attribution</dt><dd>{html.escape(str(provider.get('attribution') or '—'))}</dd></div><div><dt>License URL</dt><dd>{_provider_url(provider.get('licenseUrl'))}</dd></div></dl>"
        f"<h3 class='provider-technical-heading'>Original links</h3>{source_table}"
    )
    technical_panels: list[tuple[str, str, str, str, int | None]] = [
        ("history", "History", "provider-history", history_panel, len(audits)),
        ("health", "Health checks", "provider-health-history", health_panel, len(previous_health)),
        ("syncs", "Syncs", "provider-collection-history", syncs_panel, len(runs)),
        ("previews", "Preview layers", "provider-preview-layers", previews_panel, len(preview_layers)),
    ]
    if download_sources:
        source_counts = f"{_status_pill('neutral', f'Main maps · {main_sources}')} {_status_pill('neutral', f'Contours · {contour_sources}')}"
        technical_panels.append((
            "sources", "Download links", "provider-download-sources",
            f"<div class='filter-bar provider-filter-bar'>{_quick_select_filter('provider-source-filter', [('all', 'All'), ('broken', 'Broken')], 'all', label='Source status')}<label class='filter-search'><span class='sr-only'>Search source URLs</span><input id='provider-source-search' type='search' placeholder='Search source URLs' autocomplete='off'></label><label><span class='sr-only'>Source page size</span><select id='provider-source-page-size' data-admin-dropdown><option value='25'>25 per page</option><option value='50'>50 per page</option></select></label><p class='results-count'>{source_counts}</p></div>{download_source_table}<div class='provider-pagination' id='provider-source-pagination' aria-live='polite'></div>",
            len(download_sources),
        ))
    technical_panels.append(("attribution", "Attribution", "provider-attribution", attribution_panel, None))
    technical_section = _provider_technical_tabs(technical_panels, topics=(
        "History, health checks, syncs and releases, preview layers, "
        + ("download links, " if download_sources else "") + "attribution and original links"
    ))
    preview_button = _provider_preview_button(provider_id, status, previews_enabled)
    content = f"""
      {_admin_header(user, csrf_token, active='providers')}
      <main class='dashboard provider-detail' id='main-content'>
        <p class='back-link'><a href='/admin/providers'>{_admin_icon('arrow-left')} Providers</a></p>
        <div class='heading-row'><div><h1>{html.escape(name)}</h1></div><div class='provider-heading-status'>{_provider_status_badge(status)}</div></div>
        <section class='provider-action-bar' data-provider-id='{html.escape(provider_id, quote=True)}' aria-label='Provider actions'>
          {_provider_action_button(provider_id, 'check', 'Check provider health')}
          {_provider_action_button(provider_id, 'collect', 'Refresh catalog', secondary=True)}
          {state_button}
          {preview_button}
          <details class='provider-action-overflow'><summary>More</summary><div>{_provider_action_button(provider_id, 'retire', 'Retire provider', secondary=True, disabled=status == 'RETIRED')}</div></details>
          {activation_note}
          <p class='admin-action-status' id='provider-action-status' aria-live='polite'></p>
        </section>
        {summary_card}
        {problems_section}
        {packages_section}
        <div class='provider-state-grid'>{checks_section}{syncs_section}</div>
        {technical_section}
      </main>
      <script nonce="{_ADMIN_NONCE_PLACEHOLDER}">window.terentoAdminCsrf = {_admin_json(csrf_token)};{_provider_detail_script()}</script>
    """
    return _layout(name, content, sections={"provider": detail, "collection": runs, "history": audits})


def _map_statistics_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    has_event_data = bool(rows)

    def row_count(row: dict[str, Any], key: str) -> int | None:
        if key not in row or row.get(key) is None:
            return None
        try:
            value = int(row[key])
        except (TypeError, ValueError):
            return None
        return value if value >= 0 else None

    def count(event_type: str, outcome: str | None = None, purpose: str | None = None) -> int | None:
        values = [
            row_count(row, "operation_count")
            for row in rows
            if row.get("event_type") == event_type
            and (outcome is None or row.get("outcome") == outcome)
            and (purpose is None or (row.get("acquisition_purpose") or "unknown") == purpose)
        ]
        return sum(value for value in values if value is not None) if all(value is not None for value in values) else None

    downloads = count("DOWNLOAD_SUCCEEDED", "SUCCEEDED")
    failed_downloads = count("DOWNLOAD_FAILED", "FAILED")
    download_attempts = downloads + failed_downloads if downloads is not None and failed_downloads is not None else None
    installs = count("INSTALL_SUCCEEDED", "SUCCEEDED")
    failed_installs = count("INSTALL_FAILED", "FAILED")
    install_attempts = installs + failed_installs if installs is not None and failed_installs is not None else None
    successful_updates = count("MAP_UPDATE_SUCCEEDED", "SUCCEEDED")
    failed_updates = count("MAP_UPDATE_FAILED", "FAILED")
    updates = successful_updates + failed_updates if successful_updates is not None and failed_updates is not None else None
    event_counts = [row_count(row, "event_count") for row in rows]
    event_count = sum(value for value in event_counts if value is not None) if all(value is not None for value in event_counts) else None
    return {
        "hasEventData": has_event_data,
        "eventGroupCount": len(rows),
        # An empty result from a successful full query is a measured zero
        # population. Rates remain unavailable because their denominator is 0.
        "eventCount": event_count,
        "completedDownloads": downloads,
        "failedDownloads": failed_downloads,
        "downloadAttempts": download_attempts,
        "downloadPurposes": {
            purpose: {"succeeded": count("DOWNLOAD_SUCCEEDED", "SUCCEEDED", purpose),
                      "failed": count("DOWNLOAD_FAILED", "FAILED", purpose)}
            for purpose in ("install", "update", "unknown")
        },
        "downloadSuccessRate": (downloads / download_attempts * 100) if download_attempts else None,
        "completedInstalls": installs,
        "failedInstalls": failed_installs,
        "installAttempts": install_attempts,
        "installSuccessRate": (installs / install_attempts * 100) if install_attempts else None,
        "completedMapUpdates": successful_updates,
        "failedMapUpdates": failed_updates,
        "mapUpdates": updates,
        "mapUpdateSuccessRate": (successful_updates / updates * 100) if updates else None,
    }


_EVENT_TYPE_LABELS = {
    "DOWNLOAD_STARTED": "Download started",
    "DOWNLOAD_PROCESSING": "Checking / unpacking",
    "DOWNLOAD_CANCELLED": "Download cancelled",
    "DOWNLOAD_INTERRUPTED": "Download interrupted",
    "DOWNLOAD_SUCCEEDED": "Download succeeded",
    "DOWNLOAD_FAILED": "Download failed",
    "INSTALL_SUCCEEDED": "Install succeeded",
    "INSTALL_FAILED": "Install failed",
    "MAP_UPDATE_SUCCEEDED": "Map update succeeded",
    "MAP_UPDATE_FAILED": "Map update failed",
}
_PROVIDER_LABELS = {
    "freizeitkarte": "Freizeitkarte", "opentopomap": "OpenTopoMap", "maprando": "MapRando",
    "bbbike": "BBBike", "custom": "Custom .img",
}


def _map_statistics_rows(rows: list[dict[str, Any]], providers: dict[str, str] | None = None) -> str:
    """Event detail rows with human labels; raw codes stay in title attributes."""
    if not rows:
        return "<tr><td colspan='8' class='muted-value'>No map events in this period.</td></tr>"
    names = {**_PROVIDER_LABELS, **(providers or {})}
    markup: list[str] = []
    for row in rows:
        operation_label = _optional_count_label(row.get("operation_count"))
        event_label = _optional_count_label(row.get("event_count"))
        region_name = str(row.get("region_display_name") or "").strip()
        if not region_name:
            region_name = _admin_region_display_name(
                row.get("canonical_region_id"),
                row.get("region_country"),
                row.get("region"),
                row.get("map_package_name"),
            )
        provider_id = str(row.get("provider_id") or "")
        event_type = str(row.get("event_type") or "")
        map_id = str(row.get("map_package_id") or "")
        map_name = str(row.get("display_name") or "").strip() or (map_id or "—")
        markup.append(
            f"<tr><td title='{html.escape(provider_id, quote=True)}'>{html.escape(names.get(provider_id, provider_id or '—'))}</td>"
            f"<td title='{html.escape(map_id, quote=True)}'>{html.escape(map_name)}</td>"
            f"<td>{html.escape(region_name)}</td>"
            f"<td title='{html.escape(event_type, quote=True)}'>{html.escape(_EVENT_TYPE_LABELS.get(event_type, event_type.replace('_', ' ').title() or '—'))}</td>"
            f"<td class='column-status'>{html.escape(_admin_event_outcome_label(row.get('outcome')))}</td>"
            f"<td class='column-number numeric' title='Counted results'>{operation_label}</td>"
            f"<td class='column-number numeric' title='Raw event records'>{event_label}</td>"
            f"<td class='column-date'>{_timestamp_markup(row.get('last_occurred_at'))}</td></tr>"
        )
    return "".join(markup)


def map_statistics_page(
    statistics: dict[str, Any], providers: list[dict[str, Any]], user: dict[str, Any],
    csrf_token: str, *, selected_filters: dict[str, str] | None = None,
) -> bytes:
    rows = list(statistics.get("rows") or [])
    summary = statistics.get("summary") if isinstance(statistics.get("summary"), dict) else _map_statistics_summary(rows)
    all_time_summary = (
        statistics.get("allTimeSummary")
        if isinstance(statistics.get("allTimeSummary"), dict)
        else summary
    )
    statistics = dict(statistics)
    selected = selected_filters or {}
    event_detail_open = " open" if selected.get("eventId") else ""
    has_event_data = bool(rows)
    has_all_time_data = bool(all_time_summary.get("hasEventData", has_event_data)) or has_event_data
    selected_period = str(
        selected.get("period")
        or (statistics.get("filters") or {}).get("period")
        or "all"
    ).strip().lower()
    if selected_period not in ADMIN_PERIODS:
        selected_period = "all"
    event_status = "No matching event groups"
    provider_names = {str(provider.get("id") or ""): str(provider.get("name") or provider.get("id") or "") for provider in providers}
    provider_options = "".join(
        f"<option value='{html.escape(str(provider.get('id') or ''), quote=True)}'>{html.escape(str(provider.get('name') or provider.get('id') or ''))}</option>"
        for provider in providers
    )
    detail_rows = list(statistics.get("detailRows") or (rows[:25] if "detailRows" not in statistics else []))
    detail_total = int(statistics.get("detailTotal") if statistics.get("detailTotal") is not None else len(detail_rows))
    detail_page = int(statistics.get("detailPage") or 1)
    detail_page_size = int(statistics.get("detailPageSize") or 25)
    detail_pages = max(1, (detail_total + detail_page_size - 1) // detail_page_size)
    detail_start = min(detail_total, (detail_page - 1) * detail_page_size + 1) if detail_total else 0
    detail_end = min(detail_total, detail_page * detail_page_size)
    detail_event_counts = [_optional_nonnegative_int(row.get("event_count")) for row in detail_rows]
    detail_event_count = (
        sum(count for count in detail_event_counts if count is not None)
        if all(count is not None for count in detail_event_counts) else None
    )
    if detail_rows:
        detail_event_label = (
            f"{detail_event_count} event record{'s' if detail_event_count != 1 else ''}"
            if detail_event_count is not None else "— event records"
        )
        event_status = (
            f"{len(detail_rows)} event group{'s' if len(detail_rows) != 1 else ''} · "
            f"{detail_event_label}"
        )

    # --- Tiles: the selected period; the filter bar names it, so no scope chips
    # (owner decision 2026-10-06). ---------------------------------------------
    def tile(label: str, value_key: str, failed_key: str, rate_key: str, tile_id: str) -> str:
        rate = summary.get(rate_key)
        secondary = (
            f"Failed {_admin_error_counter(summary.get(failed_key), data_stat=failed_key)} · "
            f"<strong data-stat='{rate_key}'>{html.escape(_format_rate(rate))}</strong>"
        )
        return (
            f"<div class='map-statistics-tile' id='{tile_id}'>"
            + _metric_tile(label, summary.get(value_key), secondary=secondary,
                           data_stat=value_key)
            + "</div>"
        )

    metrics_section = (
        "<section class='admin-card map-statistics-metrics' id='map-statistics-metrics' aria-label='Map statistics summary'>"
        + _metric_row([
            tile("Downloads", "completedDownloads", "failedDownloads", "downloadSuccessRate", "map-statistics-downloads"),
            tile("Installs", "completedInstalls", "failedInstalls", "installSuccessRate", "map-statistics-installs"),
            tile("Updates", "completedMapUpdates", "failedMapUpdates", "mapUpdateSuccessRate", "map-statistics-updates"),
        ], label="Map statistics for the selected period")
        + "</section>"
    )
    statistics_period_filter = _quick_select_filter(
        "map-statistics-range",
        [(value, ADMIN_PERIOD_LABELS[value]) for value in ADMIN_PERIODS],
        selected_period, label="Time range", name="period",
    )
    detail_query = {
        key: value for key, value in selected.items()
        if key not in {"detailPage", "detailPageSize"} and value
    }
    detail_query["detailPageSize"] = str(detail_page_size)

    def detail_page_url(page: int) -> str:
        return "/admin/map-statistics?" + urlencode({**detail_query, "detailPage": page})

    event_pagination = ""
    if detail_pages > 1:
        previous = (
            f"<a class='secondary-button' href='{html.escape(detail_page_url(detail_page - 1), quote=True)}'>Previous</a>"
            if detail_page > 1 else ""
        )
        following = (
            f"<a class='secondary-button' href='{html.escape(detail_page_url(detail_page + 1), quote=True)}'>Next</a>"
            if detail_page < detail_pages else ""
        )
        event_pagination = (
            "<div class='provider-pagination' aria-label='Event pages'>"
            f"{previous}<span>Showing {detail_start}–{detail_end} of {detail_total}</span>{following}</div>"
        )
    event_table = f"""<div class='table-wrap provider-table-wrap'><table class='admin-table'><caption class='sr-only'>Map operation events</caption><thead><tr><th scope='col'>Provider</th><th scope='col'>Map</th><th scope='col'>Region</th><th scope='col'>Event</th><th scope='col' class='column-status'>Outcome</th><th scope='col' class='column-number'>Results</th><th scope='col' class='column-number'>Events</th><th scope='col' class='column-date'>Last activity</th></tr></thead><tbody id='map-statistics-rows'>{_map_statistics_rows(detail_rows, provider_names)}</tbody></table></div>{event_pagination}"""
    has_active_filters = any(
        selected.get(key) for key in ("provider", "map", "region", "eventType", "outcome", "eventId")
    ) or selected_period != "all"
    trend = list(statistics.get("trend") or [])
    bucket = str(statistics.get("bucket") or "day")
    chart_time_zone = str(statistics.get("timeZone") or "UTC")
    trends = (
        "<section class='overview-primary-grid map-statistics-trends' aria-label='Activity trends'>"
        + _section_card(
            "Downloads",
            _overview_trend_chart(trend, bucket, chart_time_zone, metric='downloads', chart_id='maps-downloads',
                                  counted=frozenset(),
                                  has_activity=bool((summary.get('completedDownloads') or 0) + (summary.get('failedDownloads') or 0))),
            card_id="map-download-trend",
            # Same chart cards as the Dashboard: period totals top right, a
            # legend without numbers (owner decision 2026-10-06).
            totals=_period_totals(summary, "completedDownloads", "failedDownloads", "downloadSuccessRate",
                                  label="Downloads in this period") if has_event_data else "",
            css="overview-panel overview-chart-panel",
        )
        + _section_card(
            "Installs",
            _overview_trend_chart(trend, bucket, chart_time_zone, chart_id='maps-installs', counted=frozenset(),
                                  has_activity=bool((summary.get('completedInstalls') or 0) + (summary.get('failedInstalls') or 0) + (summary.get('mapUpdates') or 0))),
            card_id="map-install-trend",
            totals=_period_totals(summary, "completedInstalls", "failedInstalls", "installSuccessRate",
                                  label="Installs in this period") if has_event_data else "",
            css="overview-panel overview-chart-panel",
        )
        + "</section>"
    )
    coverage = f"""
        <section class='map-statistics-coverage-layout' id='map-statistics-coverage' aria-label='Installs by country'>
          {_section_card('Countries', "<div class='map-statistics-world-map' id='map-statistics-world-map' role='group' aria-label='World map showing successful installs by country'><div class='world-map-controls' role='group' aria-label='Map navigation'><button type='button' data-map-zoom='in' aria-label='Zoom in'>+</button><button type='button' data-map-zoom='out' aria-label='Zoom out'>−</button><button type='button' data-map-zoom='reset'>Reset map</button><span id='world-map-zoom-status' role='status'>100%</span></div><div class='world-map-svg' id='world-map-svg' tabindex='0' aria-label='Map viewport. Use arrow keys to pan, plus and minus to zoom, or drag the map.'></div><div class='world-map-tooltip' id='world-map-tooltip' role='status' aria-live='polite' hidden></div></div><div class='world-map-legend' aria-label='Installation coverage legend'><span>0</span><i class='world-map-legend-gradient' aria-hidden='true'></i><span id='world-map-legend-max'>Most</span></div>", card_id='map-statistics-world-map-card', css='provider-card map-statistics-world-map-card')}
          {_section_card('Top countries', "<div class='table-wrap provider-table-wrap'><table class='admin-table popular-maps-table' data-own-mobile-layout><caption class='sr-only'>Top countries</caption><thead><tr><th scope='col'>Country</th><th scope='col' class='column-number'>Installs</th></tr></thead><tbody id='map-rows'></tbody></table></div>", card_id='top-countries', css='provider-card map-statistics-popularity', mobile_collapse=True)}
        </section>"""
    stream_buttons = "".join(
        f"<button type='button' class='quick-filter{' active' if value == 'installs' else ''}' data-provider-stream='{value}' aria-pressed='{'true' if value == 'installs' else 'false'}'>{label}</button>"
        for value, label in (("installs", "Installs"), ("updates", "Updates"), ("downloads", "Downloads"))
    )
    provider_table = _section_card(
        "Providers",
        f"<div class='filter-bar map-statistics-card-filter'><div class='quick-filter-group' role='group' aria-label='Provider stream'>{stream_buttons}</div></div>"
        "<div class='table-wrap provider-table-wrap' tabindex='0' role='region' aria-label='Provider table'><table class='admin-table mobile-record-table'><caption class='sr-only'>Providers for the selected stream</caption>"
        "<thead><tr><th scope='col'>Provider</th><th scope='col' class='column-number'>Successful</th><th scope='col' class='column-number'>Failed</th><th scope='col' class='column-number'>Rate</th><th scope='col' class='column-date' id='provider-stream-date'>Last success</th></tr></thead>"
        "<tbody id='provider-statistic-rows'></tbody></table></div>",
        card_id="map-statistics-provider-table",
        css="provider-card map-statistics-provider-table", mobile_collapse=True,
    )
    ranking = _section_card(
        "Top maps",
        "<div class='filter-bar map-statistics-card-filter' role='search'><label class='filter-search'><span class='sr-only'>Search maps</span><input type='search' id='all-maps-search' placeholder='Search maps or providers' autocomplete='off'></label></div><div class='table-wrap provider-table-wrap'><table class='admin-table popular-maps-table' data-own-mobile-layout><caption class='sr-only'>Top maps</caption><thead><tr><th scope='col'>Map</th><th scope='col' class='column-number'>Installs</th></tr></thead><tbody id='all-map-rows'></tbody></table></div><div class='provider-pagination' id='all-maps-pagination' aria-live='polite'><button type='button' id='all-maps-prev'>Previous</button><span id='all-maps-page' role='status'></span><button type='button' id='all-maps-next'>Next</button></div>",
        card_id="maps-by-provider", css="provider-card map-statistics-ranking",
        mobile_collapse=True,
    )
    events = (
        f"<section class='admin-card provider-card map-events-card'><details class='admin-disclosure' id='map-statistics-event-detail'{event_detail_open}>"
        f"<summary id='map-statistics-event-summary'>Events <span class='disclosure-meta'>· {event_status}</span></summary>"
        f"<div class='disclosure-body' id='map-statistics-event-body'>{event_table}</div></details></section>"
    )
    empty_notice = "" if has_event_data else _section_card(
        "No activity", _empty_state("empty", "No map activity for this scope."),
        card_id="map-statistics-empty", css="map-statistics-empty",
    )
    content = f"""
      {_admin_header(user, csrf_token, active='map-statistics')}
      <main class='dashboard map-statistics-page' id='main-content'>
        <div class='heading-row'><div><h1>Maps</h1></div></div>
        <form class='filter-bar map-statistics-filter-bar' id='map-statistics-filters' role='search' method='get' action='/admin/map-statistics'><input type='hidden' name='timeZone' id='map-statistics-timezone' value='{html.escape(chart_time_zone, quote=True)}'>{statistics_period_filter}<label><span class='sr-only'>Provider</span><select id='map-statistics-provider' data-admin-dropdown name='provider'><option value=''>All providers</option>{provider_options}</select></label><details class='admin-disclosure filter-disclosure' id='map-statistics-more-filters'><summary>More filters</summary><div class='disclosure-body'><label><span class='sr-only'>Map ID</span><input id='map-statistics-map' name='map' type='search' placeholder='Map ID'></label><label><span class='sr-only'>Region</span><input id='map-statistics-region' name='region' type='search' placeholder='Region'></label><label><span class='sr-only'>Event type</span><select id='map-statistics-event' data-admin-dropdown name='eventType'><option value=''>All events</option>{''.join(f"<option value='{code}'>{label}</option>" for code, label in _EVENT_TYPE_LABELS.items() if code.endswith(('SUCCEEDED', 'FAILED')))}{''.join(f"<option value='{code}'>{label}</option>" for code, label in _EVENT_TYPE_LABELS.items() if not code.endswith(('SUCCEEDED', 'FAILED')))}</select></label><label><span class='sr-only'>Outcome</span><select id='map-statistics-outcome' data-admin-dropdown name='outcome'><option value=''>All outcomes</option><option value='SUCCEEDED'>Succeeded</option><option value='FAILED'>Failed</option><option value='UNKNOWN'>Unknown</option></select></label><button type='submit'>Apply</button></div></details><p class='results-count' id='map-statistics-status' aria-live='polite'>{event_status}</p>{"<a class='secondary-button filter-clear' href='/admin/map-statistics?period=all'>Clear</a>" if has_active_filters else ""}</form>
        {metrics_section if has_all_time_data else ""}
        {empty_notice}
        {"" if not has_event_data else coverage + provider_table + ranking + events}
        {trends}
      </main>
      <link rel="stylesheet" href="/admin/map-assets/leaflet-1.9.4.css"><link rel="stylesheet" href="/admin/map-assets/coverage-map-v1.css"><script nonce="{_ADMIN_NONCE_PLACEHOLDER}" src="/admin/map-assets/leaflet-1.9.4.js"></script><script nonce="{_ADMIN_NONCE_PLACEHOLDER}" src="/admin/map-assets/coverage-map-v1.js?v=20260913-coverage-sidebar-3"></script><script nonce="{_ADMIN_NONCE_PLACEHOLDER}">window.terentoMapStatistics = {_admin_json(statistics)};window.terentoAdminProviders = {_admin_json(providers)};window.terentoMapStatisticsFilters = {_admin_json(selected)};window.terentoWorldMapSvg = {_admin_json(WORLD_MAP_SVG)};window.terentoWorldMapCountryAliases = {_admin_json(WORLD_MAP_COUNTRY_ALIASES)};{_map_statistics_script()}</script>
    """
    # Maps shows provider names only (filter options); provider health and
    # collection clocks are not part of this page's freshness revision.
    provider_labels = [(provider.get("id"), provider.get("name")) for provider in providers]
    return _layout("Maps", content, revisions={**statistics_revisions(statistics), **section_revisions({"providers": provider_labels})})


def _provider_detail_script() -> str:
    return r"""(() => {
      const csrf = window.terentoAdminCsrf;
      const status = document.querySelector('#provider-action-status');
      document.querySelectorAll('[data-provider-action]').forEach((button) => {
        button.addEventListener('click', async () => {
          const action = button.dataset.providerAction;
          const id = button.dataset.providerId;
          if (action === 'retire' && !window.confirm('Retire this provider? Historical events and packages will be retained.')) return;
          let reason = '';
          if (action === 'retire' || action === 'state') reason = window.prompt('Reason for this provider status change (optional):', '') || '';
          let downloadReason = '';
          if (action === 'downloads' && button.dataset.downloadsEnabled !== 'true') {
            const answer = window.prompt('Why disable downloads for this map? This note stays in Admin.', '');
            if (answer === null) return;
            downloadReason = answer.trim();
            if (!downloadReason) { if (status) status.textContent = 'Enter a reason to disable downloads.'; return; }
          }
          const body = action === 'previews' ? JSON.stringify({enabled: button.dataset.previewsEnabled === 'true'}) : action === 'health-schedule' ? JSON.stringify({intervalHours: Number(document.getElementById('provider-health-interval').value)}) : action === 'downloads' ? JSON.stringify({packageId: button.dataset.packageId, enabled: button.dataset.downloadsEnabled === 'true', reason: downloadReason}) : action === 'rechecks' ? JSON.stringify(button.dataset.packageId ? {packageId: button.dataset.packageId} : {}) : action === 'state' ? JSON.stringify({status: button.dataset.providerStatus, reason}) : action === 'retire' ? JSON.stringify({reason}) : '{}';
          const original = button.textContent;
          button.disabled = true;
          if (status) status.textContent = `${original}…`;
          try {
            const response = await fetch(`/admin/providers/${encodeURIComponent(id)}/${action}`, {method: 'POST', credentials: 'same-origin', headers: {'Content-Type': 'application/json', 'X-CSRF-Token': csrf}, body});
            const payload = await response.json().catch(() => ({}));
            if (!response.ok) throw new Error(payload.error || `Action failed (${response.status})`);
            if (action === 'rechecks') { sawActiveRecheck = true; if (status) status.textContent = 'Check queued. Results will appear below.'; button.disabled = false; pollRechecks(); return; }
            if (status) status.textContent = 'Saved. Refreshing…';
            window.location.reload();
          } catch (error) { button.disabled = false; if (status) status.textContent = error.message || 'Provider action failed.'; }
        });
      });
      let recheckTimer;
      let sawActiveRecheck = false;
      async function pollRechecks() {
        const bar = document.querySelector('.provider-action-bar');
        const progress = document.getElementById('provider-recheck-progress');
        if (!bar || !progress) return;
        clearTimeout(recheckTimer);
        try {
          const response = await fetch(`/admin/providers/${encodeURIComponent(bar.dataset.providerId)}/rechecks`, {credentials:'same-origin'});
          if (!response.ok) throw new Error('Check status unavailable. Refresh this page to retry.');
          const payload = await response.json();
          const job = payload.jobs?.[0];
          if (!job) return;
          const active = ['QUEUED','RUNNING'].includes(job.state);
          progress.textContent = `Last check: ${job.state}. ${(job.results || []).length} artifacts checked. ` + (job.results || []).map(r => `${r.packageId}: ${r.message}`).join(' ');
          if (active) { sawActiveRecheck = true; recheckTimer = setTimeout(pollRechecks, 3000); }
          else if (sawActiveRecheck) window.location.reload();
        } catch (error) { progress.textContent = error instanceof SyntaxError ? 'Check status unavailable. Refresh this page to retry.' : error.message; }
      }
      pollRechecks();
      document.querySelectorAll('[data-show-problems]').forEach((link) => link.addEventListener('click', () => {
        const filter = document.querySelector('#provider-package-filter');
        if (filter) { filter.value = 'broken'; filter.dispatchEvent(new Event('change')); }
      }));
      document.querySelectorAll('[data-copy-diagnostic]').forEach(button => button.addEventListener('click', async () => {
        try { await navigator.clipboard.writeText(button.dataset.copyDiagnostic); button.textContent = 'Copied'; }
        catch { button.textContent = 'Copy unavailable'; }
      }));
      const setupPagination = ({rowsSelector, searchSelector, filterSelector, pageSizeSelector, paginationSelector, noun}) => {
        let rows = [...document.querySelectorAll(rowsSelector)];
        const search = document.querySelector(searchSelector);
        const filter = document.querySelector(filterSelector);
        const pageSizeControl = document.querySelector(pageSizeSelector);
        const pagination = document.querySelector(paginationSelector);
        if (!pagination) return;
        if (!rows.length) { pagination.hidden = true; return; }
        pagination.hidden = false;
        const storageKey = `terento:provider:${location.pathname}:${noun}`;
        try {
          const saved = JSON.parse(sessionStorage.getItem(storageKey) || '{}');
          if (search && typeof saved.search === 'string') search.value = saved.search;
          if (filter && [...filter.options].some(o => o.value === saved.filter)) filter.value = saved.filter;
          if (pageSizeControl && ['25','50'].includes(saved.size)) pageSizeControl.value = saved.size;
        } catch {}
        let page = 0;
        const refresh = () => {
          try { sessionStorage.setItem(storageKey, JSON.stringify({search:search?.value,filter:filter?.value,size:pageSizeControl?.value})); } catch {}
          const pageSize = Number(pageSizeControl?.value || 25) === 50 ? 50 : 25;
          const query = (search?.value || '').trim().toLocaleLowerCase();
          const brokenOnly = filter?.value === 'broken';
          const visible = rows.filter((row) => {
            const matchesSearch = !query || (row.dataset[`${noun}Search`] || '').includes(query);
            const matchesFilter = filter?.value === 'available' ? row.dataset.packageState === 'AVAILABLE' : !brokenOnly || row.dataset[`${noun}Broken`] === 'true';
            return matchesSearch && matchesFilter;
          });
          const pages = Math.max(1, Math.ceil(visible.length / pageSize));
          page = Math.min(page, pages - 1);
          rows.forEach((row) => { row.hidden = true; });
          visible.slice(page * pageSize, (page + 1) * pageSize).forEach((row) => { row.hidden = false; });
          if (!visible.length) {
            pagination.innerHTML = `<span class="muted-value">No matching ${noun}s.</span>`;
            return;
          }
          const start = page * pageSize + 1;
          const end = Math.min((page + 1) * pageSize, visible.length);
          pagination.innerHTML = `<button type="button" data-page="previous" aria-label="Previous ${noun}s" ${page === 0 ? 'disabled' : ''}>Previous</button><span>Showing ${start}–${end} of ${visible.length} · page ${page + 1} of ${pages}</span><button type="button" data-page="next" aria-label="Next ${noun}s" ${page >= pages - 1 ? 'disabled' : ''}>Next</button>`;
          pagination.querySelector('[data-page="previous"]')?.addEventListener('click', () => { page -= 1; refresh(); });
          pagination.querySelector('[data-page="next"]')?.addEventListener('click', () => { page += 1; refresh(); });
        };
        search?.addEventListener('input', () => { page = 0; refresh(); });
        rows[0]?.closest('table')?.addEventListener('admin:table-sorted', () => { rows = [...document.querySelectorAll(rowsSelector)]; page = 0; refresh(); });
        filter?.addEventListener('change', () => { page = 0; refresh(); });
        pageSizeControl?.addEventListener('change', () => { page = 0; refresh(); });
        refresh();
      };
      setupPagination({rowsSelector: '#provider-download-source-rows tr[data-source-search]', searchSelector: '#provider-source-search', filterSelector: '#provider-source-filter', pageSizeSelector: '#provider-source-page-size', paginationSelector: '#provider-source-pagination', noun: 'source'});
      setupPagination({rowsSelector: '#provider-package-rows tr[data-package-search]', searchSelector: '#provider-package-search', filterSelector: '#provider-package-filter', pageSizeSelector: '#provider-package-page-size', paginationSelector: '#provider-package-pagination', noun: 'package'});
      // Technical details: one switcher shows one panel at a time (ARIA tabs).
      const technical = document.getElementById('provider-technical-disclosure');
      const tabs = [...document.querySelectorAll('[data-technical-tab]')];
      const selectTab = (tab, focus) => {
        tabs.forEach((other) => {
          const active = other === tab;
          other.classList.toggle('active', active);
          other.setAttribute('aria-selected', active ? 'true' : 'false');
          other.tabIndex = active ? 0 : -1;
          const panel = document.getElementById(other.getAttribute('aria-controls'));
          if (panel) panel.hidden = !active;
        });
        if (focus) tab.focus();
      };
      tabs.forEach((tab, index) => {
        tab.addEventListener('click', () => selectTab(tab, false));
        tab.addEventListener('keydown', (event) => {
          const next = {ArrowRight: index + 1, ArrowLeft: index - 1, Home: 0, End: tabs.length - 1}[event.key];
          if (next === undefined) return;
          event.preventDefault();
          selectTab(tabs[(next + tabs.length) % tabs.length], true);
        });
      });
      const openTechnical = (key) => {
        const tab = tabs.find((item) => item.dataset.technicalTab === key);
        if (!technical || !tab) return false;
        technical.open = true;
        selectTab(tab, false);
        technical.closest('section')?.scrollIntoView({block: 'start'});
        return true;
      };
      document.querySelectorAll('[data-technical-open]').forEach((link) => link.addEventListener('click', (event) => {
        if (openTechnical(link.dataset.technicalOpen)) event.preventDefault();
      }));
      const hashTab = tabs.find((tab) => location.hash === `#${tab.getAttribute('aria-controls')}`);
      if (hashTab) openTechnical(hashTab.dataset.technicalTab);
      // Long lists start short: the first rows stay visible, "Show N more" reveals the rest.
      document.querySelectorAll('[data-row-limit]').forEach((list) => {
        const limit = Number(list.dataset.rowLimit) || 5;
        if (list.children.length <= limit) return;
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'secondary-button provider-show-more';
        let expanded = false;
        const apply = () => {
          const items = [...list.children];
          items.forEach((item, position) => { item.hidden = !expanded && position >= limit; });
          button.textContent = expanded ? 'Show fewer' : `Show ${items.length - limit} more`;
          button.setAttribute('aria-expanded', expanded ? 'true' : 'false');
        };
        button.addEventListener('click', () => { expanded = !expanded; apply(); });
        (list.closest('.table-wrap') || list).after(button);
        list.closest('table')?.addEventListener('admin:table-sorted', apply);
        apply();
      });
    })();"""


def _map_statistics_script() -> str:
    return r"""(() => {
      const payload = window.terentoMapStatistics || {rows: []};
      const rows = Array.isArray(payload.rows) ? payload.rows : [];
      const providers = window.terentoAdminProviders || [];
      const filters = window.terentoMapStatisticsFilters || {};
      const form = document.querySelector('#map-statistics-filters');
      const range = document.querySelector('#map-statistics-range');
      const provider = document.querySelector('#map-statistics-provider');
      const map = document.querySelector('#map-statistics-map');
      const region = document.querySelector('#map-statistics-region');
      const event = document.querySelector('#map-statistics-event');
      const outcome = document.querySelector('#map-statistics-outcome');
      const moreFilters = document.querySelector('#map-statistics-more-filters');
      const worldMap = document.querySelector('#map-statistics-world-map');
      const worldMapSvg = document.querySelector('#world-map-svg');
      const worldMapTooltip = document.querySelector('#world-map-tooltip');
      const worldMapLegendMax = document.querySelector('#world-map-legend-max');
      const allMapsSearch = document.querySelector('#all-maps-search');
      const allMapsPagination = document.querySelector('#all-maps-pagination');
      const eventDetail = document.querySelector('#map-statistics-event-detail');
      const providerName = Object.fromEntries(providers.map((item) => [item.id, item.name || item.id]));
      const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, (character) => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[character]));
      const humanize = (value) => String(value || '—').replace(/[-_]+/g, ' ').replace(/\b\w/g, (character) => character.toUpperCase());
      const operations = (row) => {
        if (row.operation_count === null || row.operation_count === undefined) return null;
        const value = Number(row.operation_count);
        return Number.isFinite(value) && value >= 0 ? value : null;
      };
      const countValue = (value) => value === null || value === undefined ? '—' : String(value);
      const addValue = (target, key, value) => { target[key] = target[key] === null || value === null ? null : target[key] + value; };
      const addOperation = (target, key, row) => addValue(target, key, operations(row));
      const formatRate = (value) => value === null || value === undefined ? '—' : `${Number(value).toFixed(Number(value) % 1 ? 1 : 0)}%`;
      const formatTimestamp = (value) => {
        if (!value) return '—';
        if (typeof window.TerentoAdminTime?.format === 'function') return window.TerentoAdminTime.format(value);
        const normalized = typeof value === 'string' ? value.trim().replace(/^(\d{4}-\d{2}-\d{2})(\d{2}:\d{2})/, '$1T$2') : value;
        const date = new Date(normalized);
        return Number.isNaN(date.getTime()) ? String(value) : date.toISOString().slice(0, 16).replace('T', ' ');
      };
      const countryAliases = window.terentoWorldMapCountryAliases || {};
      const regionCountryAliases = {CANADAEAST:'ca',CANADAWEST:'ca',USMIDWEST:'us',USNORTHEAST:'us',USPACIFIC:'us',USSOUTH:'us',USWEST:'us'};
      const countryNames = {};
      Object.entries(countryAliases).forEach(([key, code]) => { if (key.length > 3 && !countryNames[code]) countryNames[code] = humanize(key.toLowerCase()); });
      if (typeof Intl.DisplayNames === 'function') {
        const displayNames = new Intl.DisplayNames(['en'], {type: 'region'});
        Object.values(countryAliases).forEach((code) => { countryNames[code] = displayNames.of(code.toUpperCase()) || countryNames[code]; });
      }
      const countryCode = (row) => {
        for (const candidate of [row.region_country, row.canonical_region_id, row.region_identity, row.region, row.region_display_name]) {
          const token = String(candidate || '').normalize('NFKD').replace(/[\u0300-\u036f]/g, '').replace(/[^A-Za-z0-9]+/g, '').toUpperCase();
          const resolved = countryAliases[token] || regionCountryAliases[token] || (/^[A-Z]{2}$/.test(token) ? token.toLowerCase() : null);
          if (resolved) return resolved;
        }
        return null;
      };
      const knownProviderIds = new Set(providers.map((item) => String(item.id || '')).filter(Boolean));
      const eligibleMain = (row) => operations(row) > 0 && row.map_package_id && knownProviderIds.has(String(row.provider_id || '')) && (!row.component_kind || row.component_kind === 'main');
      // Provider dates follow the provider's own Successful count: any positive
      // main-component operation, including custom maps without a catalog package.
      const datedMain = (row) => operations(row) > 0 && (!row.component_kind || row.component_kind === 'main');
      const installRows = rows.filter((row) => row.event_type === 'INSTALL_SUCCEEDED' && row.outcome === 'SUCCEEDED' && eligibleMain(row));
      let coverageMap = null;
      const countryCoverage = () => {
        const byCountry = {};
        installRows.forEach((row) => {
          const code = countryCode(row);
          if (!code) return;
          const providerId = row.provider_id || 'unknown';
          byCountry[code] ||= {code, name: countryNames[code], count: 0, providers: {}};
          addOperation(byCountry[code], 'count', row);
          byCountry[code].providers[providerId] ||= {id: providerId, count: 0};
          addOperation(byCountry[code].providers[providerId], 'count', row);
        });
        return Object.values(byCountry).sort((a, b) => (b.count ?? -1) - (a.count ?? -1) || (a.name || a.code).localeCompare(b.name || b.code));
      };
      const showWorldMapTooltip = (item, code) => {
        if (!worldMapTooltip) return;
        const providerLines = item?.providers ? Object.values(item.providers).sort((a,b) => (b.count ?? -1) - (a.count ?? -1)).map((entry) => `<div class="world-map-provider-line"><span>${escapeHtml(providerName[entry.id] || entry.id)}</span><strong>${countValue(entry.count)}</strong></div>`).join('') : '';
        worldMapTooltip.innerHTML = `<strong>${escapeHtml(item?.name || countryNames[code] || code.toUpperCase())}</strong><span class="world-map-tooltip-total">${countValue(item?.count)} completed installs</span>${providerLines}`;
        worldMapTooltip.hidden = false;
      };
      const renderWorldMap = () => {
        if (!worldMapSvg || typeof window.TerentoCoverageMap !== 'function') return;
        coverageMap ||= new window.TerentoCoverageMap(worldMapSvg, {
          svg: window.terentoWorldMapSvg, names: countryNames,
          onCountry: (item, code) => { if (code) showWorldMapTooltip(item, code); else if (worldMapTooltip) worldMapTooltip.hidden = true; },
          onZoom: (zoom, initial) => { const status = document.querySelector('#world-map-zoom-status'); if (status) status.textContent = `${Math.round(Math.pow(2, zoom - initial) * 100)}%`; }
        });
        const items = countryCoverage().filter((item) => coverageMap.codes.has(item.code));
        coverageMap.update(items);
        const total = items.some((item) => item.count === null) ? null : items.reduce((sum, item) => sum + item.count, 0);
        // No visible count line (owner decision 2026-10-06); the map's accessible
        // name still states empty or partially unavailable coverage.
        if (worldMap) worldMap.setAttribute('aria-label', `World map showing successful installs by country${total === null ? '; country coverage is partially unavailable' : items.length ? '' : '; no country activity'}`);
        if (worldMapLegendMax) worldMapLegendMax.textContent = String(Math.max(0, ...items.map((item) => item.count || 0))) || 'Most';
        if (worldMap) worldMap.dataset.countryCount = String(items.length);
      };
      document.querySelectorAll('[data-map-zoom]').forEach((button) => button.addEventListener('click', () => coverageMap?.zoom(button.dataset.mapZoom)));
      const providerStreams = {
        installs: {success: 'installs', failed: 'failedInstalls', last: 'lastInstall', date: 'Last install'},
        updates: {success: 'completedUpdates', failed: 'failedUpdates', last: 'lastUpdate', date: 'Last update'},
        downloads: {success: 'downloads', failed: 'failedDownloads', last: 'lastDownload', date: 'Last download'},
      };
      let providerStream = 'installs';
      try { const saved = sessionStorage.getItem('terento.admin.maps.providerStream'); if (providerStreams[saved]) providerStream = saved; } catch (_) { /* optional */ }
      const renderProviders = () => {
        const selected = String(filters.provider || '').toLowerCase();
        const scoped = selected ? providers.filter((item) => String(item.id || '').toLowerCase() === selected) : providers;
        const byProvider = Object.fromEntries(scoped.map((item) => [item.id, {downloads:0,failedDownloads:0,installs:0,failedInstalls:0,completedUpdates:0,failedUpdates:0,lastInstall:null,lastUpdate:null,lastDownload:null}]));
        rows.forEach((row) => {
          const id = row.provider_id || 'unknown';
          byProvider[id] ||= {downloads:0,failedDownloads:0,installs:0,failedInstalls:0,completedUpdates:0,failedUpdates:0,lastInstall:null,lastUpdate:null,lastDownload:null};
          // Last download follows the Downloads total population (all purposes);
          // a zero or unknown operation count cannot advance it.
          if (row.event_type === 'DOWNLOAD_SUCCEEDED' && row.outcome === 'SUCCEEDED') { addOperation(byProvider[id], 'downloads', row); if ((operations(row) || 0) > 0 && String(row.last_occurred_at || '') > String(byProvider[id].lastDownload || '')) byProvider[id].lastDownload = row.last_occurred_at; }
          if (row.event_type === 'DOWNLOAD_FAILED' && row.outcome === 'FAILED') addOperation(byProvider[id], 'failedDownloads', row);
          if (row.event_type === 'INSTALL_SUCCEEDED' && row.outcome === 'SUCCEEDED') { addOperation(byProvider[id], 'installs', row); if (datedMain(row) && String(row.last_occurred_at || '') > String(byProvider[id].lastInstall || '')) byProvider[id].lastInstall = row.last_occurred_at; }
          if (row.event_type === 'INSTALL_FAILED' && row.outcome === 'FAILED') addOperation(byProvider[id], 'failedInstalls', row);
          if (row.event_type === 'MAP_UPDATE_SUCCEEDED' && row.outcome === 'SUCCEEDED') { addOperation(byProvider[id], 'completedUpdates', row); if (datedMain(row) && String(row.last_occurred_at || '') > String(byProvider[id].lastUpdate || '')) byProvider[id].lastUpdate = row.last_occurred_at; }
          if (row.event_type === 'MAP_UPDATE_FAILED' && row.outcome === 'FAILED') addOperation(byProvider[id], 'failedUpdates', row);
        });
        const rate = (success, failed) => success !== null && failed !== null && success + failed ? success / (success + failed) * 100 : null;
        const stream = providerStreams[providerStream];
        const labels = ['Provider','Successful','Failed','Rate',stream.date];
        const body = document.querySelector('#provider-statistic-rows');
        const dateHeader = document.querySelector('#provider-stream-date');
        if (dateHeader) {
          // Keep the shared sort button: rename its label, not the header.
          const sortButton = dateHeader.querySelector?.('button');
          if (sortButton && sortButton.firstChild) { sortButton.firstChild.textContent = stream.date; sortButton.setAttribute('aria-label', stream.date); }
          else dateHeader.textContent = stream.date;
        }
        document.querySelectorAll('[data-provider-stream]').forEach((button) => {
          const active = button.dataset.providerStream === providerStream;
          button.classList.toggle('active', active);
          button.setAttribute('aria-pressed', active ? 'true' : 'false');
        });
        if (!body) return;
        // Downloads · Failed, Installs · Failed and Updates · Failed stay independent;
        // one stream is shown at a time.
        body.innerHTML = Object.entries(byProvider).map(([id, item]) => {
          const success = item[stream.success], failed = item[stream.failed];
          const values = [providerName[id] || id, success, failed, formatRate(rate(success, failed)), stream.last ? formatTimestamp(item[stream.last]) : '—'];
          const empty = success === 0 && failed === 0;
          return `<tr><td>${escapeHtml(countValue(values[0]))}</td>${values.slice(1).map((value, index) => `<td data-label="${labels[index + 1]}"${index < 3 ? ` data-empty-group="${empty}"` : ''} class="${index === 3 ? 'column-date' : 'column-number numeric'}">${escapeHtml(countValue(value))}</td>`).join('')}</tr>`;
        }).join('');
        // Re-rendered rows start unsorted, so no header claims a sort order.
        body.closest?.('table')?.querySelectorAll('th[aria-sort]').forEach((th) => { th.setAttribute('aria-sort', 'none'); const mark = th.querySelector('.sort-indicator'); if (mark) mark.dataset.sort = 'none'; });
      };
      window.terentoRenderProviderStream = (stream) => { if (providerStreams[stream]) { providerStream = stream; renderProviders(); } };
      document.querySelectorAll('[data-provider-stream]').forEach((button) => button.addEventListener('click', () => {
        providerStream = providerStreams[button.dataset.providerStream] ? button.dataset.providerStream : 'installs';
        try { sessionStorage.setItem('terento.admin.maps.providerStream', providerStream); } catch (_) { /* optional */ }
        renderProviders();
      }));
      const byMap = {};
      installRows.forEach((row) => {
        const providerId = String(row.provider_id || '');
        const regionIdentity = row.region_identity || row.canonical_region_id || row.region || 'UNKNOWN';
        const key = `${regionIdentity}\u0000${providerId}`;
        byMap[key] ||= {regionIdentity, regionName:row.region_display_name || humanize(row.region),provider:providerId,country:countryCode(row),installs:0,lastInstall:null,lastUpdate:null};
        addOperation(byMap[key], 'installs', row);
        if (String(row.last_occurred_at || '') > String(byMap[key].lastInstall || '')) byMap[key].lastInstall = row.last_occurred_at;
      });
      const allMapItems = Object.values(byMap).filter((item) => item.installs > 0).sort((a,b) => b.installs - a.installs || a.regionName.localeCompare(b.regionName) || a.provider.localeCompare(b.provider));
      const mapRow = (item, providerDetail = false) => {
        const label = item.regionName || '—';
        // Top maps names are plain text, not country links (owner decision 2026-10-06).
        // The count names its unit for screen readers: at <=760 px the list
        // hides its column header and reads as compact rows.
        const detail = providerDetail ? `${providerName[item.provider] || item.provider} · ${formatTimestamp(item.lastInstall)}` : formatTimestamp(item.lastInstall);
        return `<tr class="popular-map-row"><td data-label="${providerDetail ? 'Map' : 'Country'}"><div class="popular-map-name-content"><span class="popular-map-name">${escapeHtml(label)}</span><small class="popular-map-detail">${escapeHtml(detail)}</small></div></td><td data-label="Installs" data-sort-value="${item.installs}" class="column-number numeric popular-map-count"><strong>${item.installs}</strong><span class="sr-only"> installs</span></td></tr>`;
      };
      const topBody = document.querySelector('#map-rows');
      if (topBody) topBody.innerHTML = countryCoverage().slice(0,30).map((item) => `<tr class="popular-map-row"><td data-label="Country"><button type="button" class="region-map-link" data-map-country="${escapeHtml(item.code)}">${escapeHtml(item.name || item.code.toUpperCase())}</button></td><td data-label="Installs" class="column-number numeric popular-map-count"><strong>${countValue(item.count)}</strong></td></tr>`).join('') || '<tr><td colspan="2" class="muted-value">No country activity.</td></tr>';
      // Top countries fills the height of the Countries card beside it (owner
      // decision 2026-10-06): at least 10 rows, more while they fit. A
      // size-contained card cannot grow the shared row, so it overflows instead.
      const fitTopCountries = () => {
        const card = typeof topBody?.closest === 'function' ? topBody.closest('.map-statistics-popularity') : null;
        if (!card) return;
        const rows = [...(topBody.rows || [])];
        rows.forEach((row) => { row.hidden = false; });
        if (typeof getComputedStyle === 'function' && String(getComputedStyle(card).contain || '').includes('size')) {
          for (let index = rows.length - 1; index >= 10 && card.scrollHeight > card.clientHeight; index -= 1) rows[index].hidden = true;
        } else {
          rows.forEach((row, index) => { row.hidden = index >= 10; });
        }
      };
      fitTopCountries();
      if (typeof ResizeObserver === 'function' && topBody) {
        const countriesCard = document.querySelector('#map-statistics-world-map-card');
        if (countriesCard) new ResizeObserver(() => fitTopCountries()).observe(countriesCard);
      }
      let page = 1;
      const renderRanking = () => {
        const query = String(allMapsSearch?.value || '').toLowerCase().trim();
        const matches = allMapItems.filter((item) => `${item.regionName} ${providerName[item.provider] || item.provider}`.toLowerCase().includes(query));
        const pages = Math.max(1, Math.ceil(matches.length / 10)); page = Math.min(page, pages);
        const body = document.querySelector('#all-map-rows'); if (body) body.innerHTML = matches.slice((page-1)*10,page*10).map((item) => mapRow(item,true)).join('') || '<tr><td colspan="2" class="muted-value">No maps match.</td></tr>';
        const summary = document.querySelector('#all-maps-page'); if (summary) summary.textContent = `${matches.length} ${matches.length === 1 ? 'map' : 'maps'} · page ${page} of ${pages}`;
        const previous = document.querySelector('#all-maps-prev'); const next = document.querySelector('#all-maps-next');
        if (previous) previous.disabled = page <= 1; if (next) next.disabled = page >= pages;
        if (allMapsPagination) allMapsPagination.hidden = matches.length <= 10;
        document.querySelectorAll('[data-map-country]').forEach((button) => {
          button.onmouseenter = button.onfocus = () => coverageMap?.highlight(button.dataset.mapCountry);
          button.onmouseleave = button.onblur = () => coverageMap?.highlight(null);
          button.onclick = () => coverageMap?.highlight(button.dataset.mapCountry, true);
        });
      };
      allMapsSearch?.addEventListener('input', () => { page = 1; renderRanking(); });
      document.querySelector('#all-maps-prev')?.addEventListener('click', () => { page--; renderRanking(); });
      document.querySelector('#all-maps-next')?.addEventListener('click', () => { page++; renderRanking(); });
      if (range) range.value = filters.period || 'all';
      if (provider && filters.provider) provider.value = filters.provider;
      if (map) map.value = filters.map || '';
      if (region) region.value = filters.region || '';
      if (event) event.value = filters.eventType || '';
      if (outcome) outcome.value = filters.outcome || '';
      if (moreFilters && (filters.map || filters.region || filters.eventType || filters.outcome || filters.eventId)) moreFilters.open = true;
      [range, provider].forEach((control) => control?.addEventListener('change', () => form?.requestSubmit()));
      // Charts and period boundaries use the selected time zone (ADM-08): the
      // form carries it and a different zone reloads the server-side buckets.
      const zoneInput = document.querySelector('#map-statistics-timezone');
      const syncZone = () => {
        const zone = window.TerentoAdminTime?.timeZone?.();
        if (!zone || !zoneInput) return;
        zoneInput.value = zone;
        const current = new URL(window.location.href);
        if ((current.searchParams.get('timeZone') || 'UTC') === zone) return;
        current.searchParams.set('timeZone', zone);
        window.location.replace(current.toString());
      };
      window.addEventListener('terento-admin-timezone-ready', () => { syncZone(); renderProviders(); renderRanking(); });
      window.addEventListener('terento-admin-timezone-change', () => { syncZone(); renderProviders(); renderRanking(); });
      renderProviders(); renderWorldMap(); renderRanking();
      if (filters.eventId && eventDetail) { eventDetail.open = true; eventDetail.scrollIntoView?.({block:'start'}); eventDetail.querySelector('summary')?.focus({preventScroll:true}); }
    })();"""


def _display_identity(identity: str, row: dict[str, Any] | None = None) -> tuple[str, str]:
    clean = re.sub(
        r"^(?:Identity pending|Identity unresolved|Identity not identifiable|Identity resolved)\s*[·•]\s*",
        "",
        identity.strip(),
        flags=re.IGNORECASE,
    ).strip()
    if row:
        model, variant, _ = _identity_parts({**row, "compatibility_identity": clean})
        if model != "—":
            return model, variant
    model, variant, _ = _identity_parts({"model": clean, "compatibility_identity": clean})
    return model, variant


def _known_variant_description(row: dict) -> str:
    return variant_label(row) or "—"


def _identification_label(device: dict) -> str:
    model, variant, _ = _identity_parts(device)
    return model + (" · " + variant if variant != "—" else "")


def _identification_badge(state: str, label: str) -> str:
    kind = {'approved': 'success', 'rejected': 'danger', 'pending': 'warning', 'missing': 'unknown', 'shared': 'info'}[state]
    return _status_pill(kind, label, value=state.upper())


def _identification_summary(mappings: list[dict]) -> str:
    if not mappings:
        return _identification_badge('missing', 'No source')
    labels = (
        ('PENDING', 'pending', 'Needs review'),
        ('APPROVED', 'approved', 'Approved'),
        ('REJECTED', 'rejected', 'Rejected'),
    )
    return "<span class='identification-badges'>" + ''.join(
        _identification_badge(style, label)
        for state, style, label in labels
        if any(mapping.get('status') == state for mapping in mappings)
    ) + '</span>'


def _identity_mapping_markup(device: dict, csrf_token: str, *, code_models: dict | None = None) -> str:
    groups: dict[tuple[str, str], list[dict]] = {}
    for mapping in device.get("identityMappings", []):
        groups.setdefault((mapping['kind'], mapping['value']), []).append(mapping)
    if not groups:
        return "<div class='admin-card identification-empty'><h2>No source reported</h2><p>No imported source identity is available for this model.</p></div>"
    labels = {'RETAIL_SKU': 'Retail product code', 'XML_PART_NUMBER': 'Watch product code', 'USB': 'USB connection code'}
    decisions = {'PENDING': 'Needs review', 'APPROVED': 'Approved', 'REJECTED': 'Rejected'}
    label = html.escape(_identification_label(device))
    map_label, _ = _admin_map_capability(device.get('mapCapable'))
    map_fact = f"<span>Maps: {html.escape(map_label)}</span>" if device.get('mapCapable') is not None else ''
    items: list[str] = []
    technical_items: list[str] = []
    technical_number = 0
    for (kind, value), group in sorted(groups.items(), key=lambda item: (not any(m['status'] == 'PENDING' for m in item[1]), ({'XML_PART_NUMBER': 0, 'USB': 1, 'RETAIL_SKU': 2}.get(item[0][0], 3), item[0][1]))):
        peers = (code_models or {}).get((kind, value), {})
        others = [(key, peer) for key, peer in peers.items() if str(key) != str(device['id'])]
        other_models = ''
        if others:
            links = ''.join(
                f"<li><a href='/admin/device-identification?{urlencode({'device': key})}'>{html.escape(peer['label'])}</a>"
                f"{_identification_summary(peer['mappings'])}</li>"
                for key, peer in others
            )
            other_models = f"<section class='identification-step identification-other-models'><h3>Same code</h3><ul>{links}</ul></section>"
        for mapping_index, mapping in enumerate(sorted(group, key=lambda m: m['status'] != 'PENDING')):
            raw_source = str(mapping['source_url'])
            source_host = (urlsplit(raw_source).hostname or '').removeprefix('www.')
            source_link = (
                f'<a class="section-link" href="{html.escape(raw_source, quote=True)}" target="_blank" rel="noopener noreferrer">Open {html.escape(source_host or "source")}&nbsp;{_admin_icon("external")}</a>'
                if raw_source.startswith('https://') else '<span class="identification-source-unavailable">Source link unavailable</span>'
            )
            names = html.escape('; '.join(mapping.get('source_names') or [])) or 'No model name supplied'
            current_decision = ''
            if mapping['status'] != 'PENDING':
                reviewed = f" · {_timestamp_markup(mapping.get('reviewed_at'))}" if mapping.get('reviewed_at') else ''
                reason = html.escape(str(mapping.get('review_reason') or 'No reason recorded'))
                current_decision = (
                    "<p class='identification-existing-decision'><strong>Current decision:</strong> "
                    f"{_identification_badge(mapping['status'].lower(), decisions[mapping['status']])}"
                    f"<span>{reason}{reviewed}</span></p>"
                )
            items.append(f"""<article class='admin-card identity-mapping-source'>
            <div class='identification-compare'>
            <section class='identification-step'><h3>Source says</h3><strong class='identification-reported-name'>{names}</strong><div class='identification-source-link'>{source_link}</div></section>
            <span class='identification-compare-arrow' aria-hidden='true'>{_admin_icon('arrows-left-right')}</span>
            <section class='identification-step identification-match'><h3>Catalog model</h3><strong>{label}</strong>{map_fact}</section>
            </div>
            {other_models if mapping_index == 0 else ''}
            <section class='identification-step identification-confirm'><h3>Confirm</h3>{current_decision}
            <form method='post' action='/admin/devices/identity-mapping' class='admin-async-action identity-mapping-review'>
            <input type='hidden' name='csrf_token' value='{html.escape(csrf_token, quote=True)}'>
            <input type='hidden' name='mapping_id' value='{int(mapping['id'])}'>
            <input type='hidden' name='return_to' value='/admin/device-identification?device={quote(str(device['id']), safe='')}'>
            <label>Decision note<textarea name='reason' required maxlength='1000' rows='2' placeholder='Name the source evidence that supports this decision.'></textarea></label>
            <div class='identification-decision-actions'><button type='submit' name='status' value='APPROVED'>Approve match</button><button class='secondary-button' type='submit' name='status' value='REJECTED'>Reject match</button></div>
            <p class='admin-action-status' role='status' aria-live='polite'></p></form></section></article>""")

            technical_number += 1
            history = ''.join(
                '<li>' + html.escape(f"{entry['previous_status']} → {entry['new_status']} · {entry['reason']} · {'administrator ' + str(entry['reviewed_by']) if entry['reviewed_by'] is not None else 'catalog import'} · {entry['created_at']}") + '</li>'
                for entry in mapping.get('history') or []
            ) or '<li>No previous decisions</li>'
            technical_items.append(
                f"<section><h4>Source {technical_number}</h4><dl class='model-information-list'>"
                f"<div><dt>Code type</dt><dd>{html.escape(labels.get(kind, kind))}</dd></div>"
                f"<div><dt>Raw code</dt><dd><code>{html.escape(value)}</code></dd></div>"
                f"<div><dt>Catalog model ID</dt><dd><code>{html.escape(str(device['id']))}</code></dd></div>"
                f"<div><dt>Mapping ID</dt><dd><code>{int(mapping['id'])}</code></dd></div>"
                f"<div><dt>Source URL</dt><dd><code>{html.escape(raw_source)}</code></dd></div>"
                f"<div><dt>Source revision</dt><dd>{html.escape(str(mapping.get('source_version') or 'Unavailable'))}</dd></div>"
                f"</dl><h4>Decision history</h4><ul>{history}</ul></section>"
            )
    mappings = device.get('identityMappings') or []
    missing = [name for kind, name in [('XML_PART_NUMBER', 'watch product code'), ('USB', 'USB connection code')] if not any(mapping['kind'] == kind for mapping in mappings)]
    missing_note = f"<p><strong>Missing imported sources:</strong> {html.escape(' and '.join(missing))}.</p>" if missing else ''
    technical = (
        "<details class='admin-card admin-disclosure identification-technical'><summary>Technical details</summary><div class='disclosure-body'>"
        + missing_note
        + "<p>Each decision updates only its imported source link. It does not change installations, installation permission or public compatibility.</p>"
        + ''.join(technical_items)
        + "</div></details>"
    )
    return "<div class='identity-mappings'>" + ''.join(items) + technical + '</div>'


def _identification_state(mappings: list[dict]) -> str:
    """List state for Model sources: needs review, approved, rejected or no source."""
    if not mappings:
        return "missing"
    statuses = {str(mapping.get("status") or "") for mapping in mappings}
    if "PENDING" in statuses:
        return "pending"
    if "APPROVED" in statuses:
        return "approved"
    return "rejected"


def device_identification_page(devices: list[dict], user: dict, csrf_token: str, *, device_id: str = "", query: str = "") -> bytes:
    selected = next((d for d in devices if str(d.get('id')) == device_id), None)
    code_models: dict = {}
    for device in devices:
        for mapping in device.get('identityMappings') or []:
            peer = code_models.setdefault((mapping['kind'], mapping['value']), {}).setdefault(str(device['id']), {'label': _identification_label(device), 'mappings': []})
            peer['mappings'].append(mapping)
    ordered = sorted(devices, key=lambda d: (not any(m['status'] == 'PENDING' for m in d.get('identityMappings') or []), _identification_label(d).casefold()))
    state_labels = {"pending": "Needs review", "approved": "Approved", "rejected": "Rejected", "missing": "No source"}
    counts = {state: 0 for state in state_labels}
    rows: list[str] = []
    listed_states: list[str] = []
    for device in ordered:
        label = _identification_label(device)
        mappings = device.get('identityMappings') or []
        state = _identification_state(mappings)
        counts[state] += 1
        searchable = ' '.join([label] + [str(m['value']) for m in mappings])
        if query and query.casefold() not in searchable.casefold():
            continue
        codes = ", ".join(dict.fromkeys(str(m['value']) for m in mappings)) or "—"
        hosts = ", ".join(dict.fromkeys(
            (urlsplit(str(m.get('source_url') or '')).hostname or '').removeprefix('www.') or '—' for m in mappings
        )) or "—"
        href = f"/admin/device-identification?{urlencode({'device': device['id']})}"
        listed_states.append(state)
        # The model name opens its review; the State column sorts by queue order.
        rows.append(
            f"<tr data-source-state='{state}'><td><a class='identification-choice' href='{html.escape(href, quote=True)}'><strong>{html.escape(label)}</strong></a></td>"
            f"<td><code>{html.escape(codes)}</code></td><td>{html.escape(hosts)}</td>"
            f"<td class='column-status' data-sort-value='{list(state_labels).index(state)}'>{_identification_summary(mappings)}</td></tr>"
        )
    pending_models = counts["pending"]
    back_nav = ""
    if selected:
        pending_queue = [
            d for d in ordered
            if any(m['status'] == 'PENDING' for m in d.get('identityMappings') or []) and str(d.get('id')) != str(selected.get('id'))
        ]
        position = next((index for index, d in enumerate(ordered) if str(d.get('id')) == str(selected.get('id'))), 0)
        next_device = next((d for d in pending_queue if ordered.index(d) > position), pending_queue[0] if pending_queue else None)
        next_link = (
            f"<a class='identification-next-link' href='/admin/device-identification?{urlencode({'device': next_device['id']})}'>Next in queue&nbsp;{_admin_icon('arrow-right')}</a>"
            if next_device else ""
        )
        # Owner decision 2026-10-06: the detail keeps its workflow; each source
        # is one Admin card, Technical details is a separate card, and the
        # cards are spaced by --admin-card-gap.
        back_nav = f"<nav class='back-link identification-workspace-nav' aria-label='Model sources queue'><a href='/admin/device-identification'>{_admin_icon('arrow-left')} Model sources</a>{next_link}</nav>"
        content = (
            f"<section class='identification-workspace' aria-label='Source review'>{_identity_mapping_markup(selected, csrf_token, code_models=code_models)}</section>"
            f"<p class='identification-model-detail-link'><a class='section-link' href='/admin/devices/{quote(str(selected['id']), safe='')}'>View model details and installation evidence&nbsp;{_admin_icon('arrow-right')}</a></p>"
        )
    else:
        if query and not rows:
            empty = f"<div class='admin-card identification-empty'><h2>No matching models.</h2><p>No model or code matches “{html.escape(query)}”. Try a shorter model name or clear the search.</p><a class='section-link' href='/admin/device-identification'>Clear search</a></div>"
        elif not devices:
            empty = "<div class='admin-card identification-empty'><h2>No models available</h2><p>Run the device catalog collection, then return here to review its sources.</p><a class='section-link' href='/admin/devices'>Open device catalog</a></div>"
        else:
            empty = ""
        invalid = "<p class='identification-not-found' role='alert'>This model is unavailable. Search the catalog below and select an existing model.</p>" if device_id else ''
        # Needs review is preselected when any listed model needs review.
        default_state = 'pending' if 'pending' in listed_states else 'all'
        chips = "".join(
            f"<button type='button' class='quick-filter{' active' if state == default_state else ''}' data-source-filter='{state}' aria-pressed='{'true' if state == default_state else 'false'}'>{label}</button>"
            for state, label in (("all", "All"), *state_labels.items())
        )
        shown = len(listed_states) if default_state == 'all' else listed_states.count(default_state)
        # Installations filter-bar design (owner decision 2026-10-06): quick
        # filters, the server-side search (?q=), the result count and Clear,
        # which shows only when a filter differs from its default.
        filter_bar = (
            "<form method='get' action='/admin/device-identification' class='filter-bar admin-filter-bar identification-filter-bar' id='identification-filters' role='search'>"
            f"<div class='quick-filter-group' role='group' aria-label='Model source state' data-default-filter='{default_state}'>{chips}</div>"
            "<label class='filter-search' for='identification-search'><span class='sr-only'>Find a model or code</span>"
            f"<input id='identification-search' type='search' name='q' enterkeyhint='search' autocomplete='off' placeholder='Search models or codes' value='{html.escape(query, quote=True)}'></label>"
            "<button class='secondary-button identification-search-submit' type='submit'>Search</button>"
            f"<p class='results-count' id='identification-results-count' aria-live='polite'>{_count_label(shown, 'model')}</p>"
            f"<a class='secondary-button filter-clear' href='/admin/device-identification' data-filter-clear data-has-query='{'true' if query else 'false'}' aria-label='Clear model source filters'{'' if query else ' hidden'}>Clear</a>"
            "</form>"
        ) if devices else ""
        table = (
            "<div class='table-wrap provider-table-wrap identification-table-wrap'><table class='admin-table identification-table'><caption class='sr-only'>Catalog models and their imported Garmin code sources</caption>"
            "<thead><tr><th scope='col'>Model</th><th scope='col'>Garmin code</th><th scope='col'>Source</th><th scope='col' class='column-status'>State</th></tr></thead>"
            f"<tbody id='identification-rows'>{''.join(rows)}</tbody></table></div>"
            "<p class='admin-empty' id='identification-filter-empty' data-state='filtered' hidden>No models for this filter.</p>"
            "<div class='provider-pagination' id='identification-pagination' aria-live='polite' hidden><button type='button' data-source-page='previous'>Previous</button><span></span><button type='button' data-source-page='next'>Next</button></div>"
        ) if rows else ""
        content = (
            f"{invalid}"
            # One summary card with plain numbers: no scope chips or icons. Needs
            # review stays neutral: a source decision changes no installation,
            # permission or public compatibility, so nothing is failing.
            "<section class='admin-card installation-kpis identification-kpis' aria-label='Model source summary'>"
            + _metric_row([
                _metric_tile("Needs review", pending_models),
                _metric_tile("Approved", counts["approved"]),
                _metric_tile("Rejected", counts["rejected"]),
                _metric_tile("No source", counts["missing"]),
            ], label="Model source states")
            + "</section>"
            + f"<section class='identification-list' id='identification-list' aria-label='Models'>{filter_bar}{table or empty}</section>"
        )
    body = _admin_header(user, csrf_token, active='device-identification') + f"<main id='main-content' class='dashboard identification-page'>{back_nav}<h1>Model sources</h1>" + content + '</main>'
    return _layout('Model sources', body + _script_tag(_identification_review_script()), sections={'identification': devices})


def _identification_review_script() -> str:
    return r"""(() => {
      let rows = [...document.querySelectorAll('#identification-rows tr[data-source-state]')];
      const chips = [...document.querySelectorAll('[data-source-filter]')];
      const pagination = document.querySelector('#identification-pagination');
      const filterEmpty = document.querySelector('#identification-filter-empty');
      const count = document.querySelector('#identification-results-count');
      const clear = document.querySelector('#identification-filters [data-filter-clear]');
      const defaultState = document.querySelector('#identification-filters [data-default-filter]')?.dataset.defaultFilter || 'all';
      const hasQuery = clear?.dataset.hasQuery === 'true';
      let state = chips.find(chip => chip.getAttribute('aria-pressed') === 'true')?.dataset.sourceFilter || 'all';
      let page = 0;
      const pageSize = 25;
      const refreshList = () => {
        const matching = rows.filter(row => state === 'all' || row.dataset.sourceState === state);
        const pages = Math.max(1, Math.ceil(matching.length / pageSize));
        page = Math.min(page, pages - 1);
        rows.forEach(row => { row.hidden = true; });
        matching.slice(page * pageSize, (page + 1) * pageSize).forEach(row => { row.hidden = false; });
        chips.forEach(chip => { const active = chip.dataset.sourceFilter === state; chip.classList.toggle('active', active); chip.setAttribute('aria-pressed', active ? 'true' : 'false'); });
        if (filterEmpty) filterEmpty.hidden = matching.length > 0 || !rows.length;
        if (count) count.textContent = `${matching.length} ${matching.length === 1 ? 'model' : 'models'}`;
        if (clear) clear.hidden = !hasQuery && state === defaultState;
        if (pagination) {
          pagination.hidden = matching.length <= pageSize;
          const label = pagination.querySelector('span');
          if (label) label.textContent = `Showing ${page * pageSize + 1}–${Math.min(matching.length, (page + 1) * pageSize)} of ${matching.length} · page ${page + 1} of ${pages}`;
          pagination.querySelector('[data-source-page="previous"]').disabled = page === 0;
          pagination.querySelector('[data-source-page="next"]').disabled = page >= pages - 1;
        }
      };
      chips.forEach(chip => chip.addEventListener('click', () => { state = chip.dataset.sourceFilter; page = 0; refreshList(); }));
      // Clear reloads without ?q= when a search is active; otherwise it only
      // returns the state filter to its default.
      clear?.addEventListener('click', event => { if (hasQuery) return; event.preventDefault(); state = defaultState; page = 0; refreshList(); });
      pagination?.querySelector('[data-source-page="previous"]')?.addEventListener('click', () => { page -= 1; refreshList(); });
      pagination?.querySelector('[data-source-page="next"]')?.addEventListener('click', () => { page += 1; refreshList(); });
      rows[0]?.closest('table')?.addEventListener('admin:table-sorted', () => { rows = [...document.querySelectorAll('#identification-rows tr[data-source-state]')]; page = 0; refreshList(); });
      if (rows.length) refreshList();
      document.querySelectorAll('.identity-mapping-review').forEach(form => {
        form.addEventListener('submit', async event => {
          event.preventDefault();
          if (form.dataset.submitting === 'true') return;
          const payload = new URLSearchParams(new FormData(form, event.submitter));
          const controls = [...form.querySelectorAll('button,input,select,textarea')];
          const status = form.querySelector('.admin-action-status');
          const controller = new AbortController();
          const timeout = setTimeout(() => controller.abort(), 20000);
          form.dataset.submitting = 'true';
          form.setAttribute('aria-busy', 'true');
          controls.forEach(control => control.disabled = true);
          status.dataset.error = 'false';
          status.textContent = 'Saving source decision…';
          try {
            const response = await fetch(form.action, {method:'POST', body:payload,
              credentials:'same-origin', signal:controller.signal});
            if (!response.ok) throw new Error('save');
            if (response.redirected && new URL(response.url).pathname === '/admin/login') {
              status.textContent = 'Your session expired. Open this page in another tab to sign in, then retry. Your text is kept here.';
              status.dataset.error = 'true';
              return;
            }
            if (!response.redirected) throw new Error('save');
            window.location.assign(response.url);
          } catch (_) {
            status.dataset.error = 'true';
            status.textContent = 'Could not confirm the save. Your text is kept here. Check your connection and the current decision in another tab before retrying.';
          } finally {
            clearTimeout(timeout);
            controls.forEach(control => control.disabled = false);
            form.dataset.submitting = 'false';
            form.removeAttribute('aria-busy');
          }
        });
      });
    })();"""


def _identity_presentation_candidates(assessment: dict) -> list[dict]:
    """Prefer explicitly observed features over less-specific catalog rows.

    This narrows operator suggestions only. The authoritative assessment retains
    every candidate and never treats an unknown feature as a negative fact.
    """
    candidates = [c for c in assessment.get("candidates", [])
                  if not c.get("conflict") and c.get("checks")
                  and not any(k.get("state") == "CONFLICT" for k in c["checks"])]
    for feature_name in ("inreach", "solar"):
        explicit = [c for c in candidates if any(
            f.get("name") == feature_name and f.get("expected") is True
            and any(e.get("source") == "model text" and e.get("value") is True for e in f.get("evidence", []))
            for k in c["checks"] for f in k.get("features", []))]
        if explicit:
            candidates = explicit
    return candidates


def _identity_recommendation(results: list[dict[str, Any]]) -> dict | None:
    """Recommend only a single non-conflicting target shared by every report."""
    choices = []
    for result in results:
        assessment = result.get("current_identity_assessment") or result.get("identity_assessment") or {}
        possible = _identity_presentation_candidates(assessment)
        if len(possible) != 1:
            return None
        choices.append(possible[0])
    return choices[0] if choices and len({c["deviceId"] for c in choices}) == 1 else None


def _identity_assessments(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [r.get("current_identity_assessment") or r.get("identity_assessment") or {} for r in results]


def _identity_selected_id(results: list[dict[str, Any]]) -> str | None:
    return next((str(r.get("canonical_device_model_id")).strip() for r in results
                 if str(r.get("canonical_device_model_id") or "").strip()), None)


def _identity_candidate(results: list[dict[str, Any]], device_id: str | None = None) -> dict[str, Any] | None:
    target = device_id or _identity_selected_id(results)
    if target:
        for assessment in _identity_assessments(results):
            candidate = next((c for c in assessment.get("candidates", []) if c.get("deviceId") == target), None)
            if candidate:
                return candidate
        # A selected catalog ID must not borrow the facts of a different
        # suggested candidate when an old assessment lacks that ID.
        return None
    return _identity_recommendation(results)


def _identity_check(candidate: dict[str, Any] | None, name: str) -> dict[str, Any]:
    return next((check for check in (candidate or {}).get("checks", []) if check.get("name") == name), {})


def _identity_feature(candidate: dict[str, Any] | None, name: str) -> dict[str, Any]:
    return next((feature for check in (candidate or {}).get("checks", [])
                 for feature in check.get("features", []) if feature.get("name") == name), {})


def _identity_conflict_lines(
    results: list[dict[str, Any]], selected_id: str | None,
    identity_devices: list[dict[str, Any]] | None = None,
) -> list[str]:
    """Render every concrete selected-model conflict across all result rows."""
    if not selected_id:
        return []
    devices = {
        str(device.get("id") or device.get("device_id") or ""): device
        for device in identity_devices or []
    }
    selected_device = devices.get(str(selected_id))
    selected_label = _identity_device_label(selected_device) if selected_device else "selected catalog model"
    field_labels = {
        "model": "Model", "size": "Case size", "screen": "Display",
        "solar": "Solar", "inreach": "inReach", "xmlPartNumber": "Product mapping",
        "usb": "USB mapping",
    }
    lines: list[str] = []
    seen: set[tuple[str, str, str, str, str]] = set()
    for result_index, result in enumerate(results, start=1):
        assessment = result.get("current_identity_assessment") or result.get("identity_assessment") or {}
        candidate = next((item for item in assessment.get("candidates", [])
                          if str(item.get("deviceId") or "") == str(selected_id)), None)
        if not candidate:
            continue
        result_id = str(result.get("event_id") or "").strip()
        result_label = f"Diagnostic result {result_id}" if result_id else f"Diagnostic result {result_index}"

        def add(field: str, reported: Any, source: Any, *, mapping_models: list[str] | None = None) -> None:
            reported_text = "Not reported" if reported is None or reported == "" else str(reported)
            source_text = str(source or "reported data")
            mappings_text = ", ".join(mapping_models or [])
            key = (result_label, field, reported_text, source_text, mappings_text)
            if key in seen:
                return
            seen.add(key)
            line = (f"{result_label}: {field_labels.get(field, field)}: reported "
                    f"{reported_text} from {source_text}; selected model {selected_label}.")
            if mappings_text:
                line += f" Approved mapping models for this code: {mappings_text}."
            lines.append(line)

        for check in candidate.get("checks", []):
            name = str(check.get("name") or "")
            if (check.get("state") == "CONFLICT" and name == "model"
                    and check.get("observedState", check.get("state")) == "CONFLICT"):
                for evidence in check.get("evidence") or []:
                    if evidence.get("value") != check.get("expected"):
                        add(name, evidence.get("value"), evidence.get("source"))
            if check.get("state") == "CONFLICT" and name in {"size", "screen"}:
                for evidence in check.get("evidence") or []:
                    if evidence.get("value") != check.get("expected"):
                        add(name, evidence.get("value"), evidence.get("source"))
            if check.get("state") == "CONFLICT" and name not in {"model", "size", "screen", "xmlPartNumber", "usb"}:
                for evidence in check.get("evidence") or []:
                    add(name, evidence.get("value"), evidence.get("source"))
            if check.get("state") == "CONFLICT" and name in {"xmlPartNumber", "usb"}:
                mapping_models = [
                    _identity_device_label(devices.get(str(evidence.get("deviceId") or "")))
                    for evidence in check.get("evidence") or []
                    if str(evidence.get("deviceId") or "") in devices
                ]
                add(name, check.get("value"), check.get("codeKind") or name,
                    mapping_models=[label for label in mapping_models if label != "selected catalog model"])
            for feature in check.get("features") or []:
                if feature.get("state") == "CONFLICT":
                    for evidence in feature.get("evidence") or []:
                        if evidence.get("value") != feature.get("expected"):
                            add(str(feature.get("name") or "feature"), evidence.get("value"), evidence.get("source"))
    return lines


def _identity_source_label(evidence: list[dict[str, Any]] | None) -> str:
    sources = [str(item.get("source") or "") for item in evidence or []]
    has_catalog = any(source.startswith("catalog specification:") for source in sources)
    has_mapping = any(":" in source and source.split(":", 1)[0] in {"USB", "XML_PART_NUMBER", "RETAIL_SKU"} for source in sources)
    if has_catalog and has_mapping:
        return "From catalog / mapping"
    if has_catalog:
        return "From catalog"
    if has_mapping:
        return "From mapping"
    return "Reported" if evidence else "Not confirmed"


def _identity_evidence_values(check: dict[str, Any]) -> list[Any]:
    return list(dict.fromkeys(item.get("value") for item in check.get("evidence", [])
                             if item.get("value") is not None))


def _identity_value(value: Any, *, suffix: str = "") -> str:
    if value is None or value == "":
        return "Not reported"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return f"{value}{suffix}"


def _identity_fact_markup(label: str, value: str, state: str, source: str) -> str:
    icon = _admin_icon({"match": "circle-check", "conflict": "circle-exclamation"}.get(state, "question"))
    return (f"<article class='identity-fact identity-fact-{state}'>"
            f"<div class='identity-fact-heading'><span class='identity-fact-icon' aria-hidden='true'>{icon}</span><span>{html.escape(label)}</span></div>"
            f"<strong>{html.escape(value)}</strong><small>{html.escape(source)}</small></article>")


def _identity_observations_markup(
    results: list[dict[str, Any]], identity_devices: list[dict[str, Any]] | None = None,
) -> str:
    selected_id = _identity_selected_id(results)
    candidate = _identity_candidate(results, selected_id)
    assessments = _identity_assessments(results)
    def fact_records(name: str) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for assessment in assessments:
            records.extend(assessment.get("facts", {}).get(name, []) or [])
        return records

    def fact_values(name: str) -> list[Any]:
        values: list[Any] = []
        for record in fact_records(name):
            value = record.get("value")
            if value is not None and value not in values:
                values.append(value)
        return values

    reported_values = list(dict.fromkeys(
        str(result.get(field)).strip() for result in results
        for field in ("raw_mtp_model", "garmin_model_description", "model")
        if str(result.get(field) or "").strip()
    ))
    if not reported_values:
        reported_values = [str(value).strip() for value in fact_values("model") if str(value).strip()]
    reported = reported_values[0] if reported_values else "Not reported"
    reported_markup = "<p class='identity-reported-device'><strong>Reported device:</strong> " + html.escape(reported) + "</p>"
    if len(reported_values) > 1:
        reported_markup += "<p class='identity-reported-also'>Also reported: " + html.escape(" / ".join(reported_values[1:])) + "</p>"

    model_check = _identity_check(candidate, "model")
    model_values = [str(value) for value in _identity_evidence_values(model_check)] if candidate else [str(value) for value in fact_values("model")]
    model_observed_state = model_check.get("observedState", model_check.get("state"))
    model_state = ("conflict" if model_observed_state == "CONFLICT" else "match" if model_observed_state == "MATCH" else "missing") if candidate else ("match" if model_values else "missing")
    model_source = _identity_source_label(model_check.get("evidence")) if candidate else ("Reported" if model_values else "Not confirmed")
    facts = [_identity_fact_markup("Model", " / ".join(model_values) if model_values else "Not reported", model_state, model_source)]
    size_check = _identity_check(candidate, "size")
    size_values = _identity_evidence_values(size_check) if candidate else fact_values("caseSizeMm")
    size_from_catalog = bool(candidate and not size_values and size_check.get("expected") is not None and size_check.get("state") != "CONFLICT")
    facts.append(_identity_fact_markup("Case size", _identity_value(size_values[0] if size_values else size_check.get("expected") if size_from_catalog else None, suffix=" mm"),
                                       ("conflict" if size_check.get("state") == "CONFLICT" else "match" if size_check.get("state") == "MATCH" or size_from_catalog else "missing") if candidate else ("match" if size_values else "missing"),
                                       "From catalog" if size_from_catalog else _identity_source_label(size_check.get("evidence")) if candidate else ("Reported" if size_values else "Not confirmed")))
    screen_check = _identity_check(candidate, "screen")
    screen_values = _identity_evidence_values(screen_check) if candidate else fact_values("screenTechnology")
    screen_from_catalog = bool(candidate and not screen_values and screen_check.get("expected") and screen_check.get("state") != "CONFLICT")
    facts.append(_identity_fact_markup("Display", _identity_value(screen_values[0] if screen_values else screen_check.get("expected") if screen_from_catalog else None),
                                       ("conflict" if screen_check.get("state") == "CONFLICT" else "match" if screen_check.get("state") == "MATCH" or screen_from_catalog else "missing") if candidate else ("match" if screen_values else "missing"),
                                       "From catalog" if screen_from_catalog else _identity_source_label(screen_check.get("evidence")) if candidate else ("Reported" if screen_values else "Not confirmed")))
    for label, feature_name in (("Solar", "solar"), ("inReach", "inreach")):
        feature = _identity_feature(candidate, feature_name)
        fact_name = "inReach" if feature_name == "inreach" else feature_name
        values = _identity_evidence_values(feature) if candidate else fact_values(fact_name)
        from_catalog = bool(candidate and not values and feature.get("expected") is not None and feature.get("state") != "CONFLICT")
        feature_value = values[0] if values else feature.get("expected") if from_catalog else None
        facts.append(_identity_fact_markup(label, _identity_value(feature_value),
                                           "conflict" if feature.get("state") == "CONFLICT" else "match" if from_catalog or feature.get("state") == "MATCH" else "missing" if candidate else ("match" if values else "missing"),
                                           "From catalog" if from_catalog else _identity_source_label(feature.get("evidence")) if candidate else ("Reported" if values else "Not confirmed")))
    code_checks = [_identity_check(candidate, "xmlPartNumber"), _identity_check(candidate, "usb")]
    code_lines = []
    code_states = []
    for label, check in (("Product", code_checks[0]), ("USB", code_checks[1])):
        kind = "RETAIL_SKU" if label == "Product" and check.get("codeKind") == "RETAIL_SKU" else "XML_PART_NUMBER" if label == "Product" else "USB"
        value = check.get("value") if candidate else next((record.get("value") for record in fact_records("codes") if record.get("kind") == kind), None)
        if value is None:
            code_lines.append(f"{label}: Not reported")
        else:
            status = ("mapped" if check.get("state") == "MATCH" else "mapping not confirmed" if check.get("state") != "CONFLICT" else "conflict") if candidate else "received"
            code_lines.append(f"{label}: {value} · {status}")
        code_states.append(check.get("state"))
    code_state = "conflict" if "CONFLICT" in code_states else "match" if "MATCH" in code_states else "missing" if candidate else ("match" if any("Not reported" not in line for line in code_lines) else "missing")
    code_source = "From mapping" if candidate and code_state == "match" else "Reported" if any(check.get("value") is not None for check in code_checks) or fact_values("codes") else "Not confirmed"
    facts.append(_identity_fact_markup("Device codes", " · ".join(code_lines), code_state, code_source))
    selected_device = next((device for device in identity_devices or []
                            if str(device.get("id") or device.get("device_id") or "") == str(selected_id or "")), None)
    selection_label = _identity_device_label(selected_device) if selected_device else (
        _identity_device_label(candidate) if candidate else "No catalog model selected"
    )
    recommendation_label = "Suggested model" if not selected_id else "Selected catalog model"
    status = "Confirmed by administrator" if any(
        isinstance((result.get("identity_decision") or {}).get("decision"), dict)
        for result in results
    ) else "Assigned catalog model" if selected_id else "Suggested model" if candidate else "Select catalog variant"
    if any(assessment.get("candidates") and not _identity_candidate([result]) for result, assessment in zip(results, assessments)):
        status = "Select variant"
    return ("<div class='identity-review-facts'>" + reported_markup
            + "<div class='identity-facts' aria-label='Identity facts'>" + "".join(facts) + "</div>"
            + f"<div class='identity-selected-model'><strong>{html.escape(selection_label)}</strong><small>{html.escape(status)}</small></div>"
            + "</div>")


def _identity_checks_markup(
    results: list[dict[str, Any]], identity_devices: list[dict[str, Any]] | None = None,
) -> str:
    assigned = _identity_selected_id(results)
    candidate = _identity_candidate(results, assigned)
    decision = {}
    for result in results:
        value = (result.get("identity_decision") or {}).get("decision")
        if isinstance(value, dict):
            decision = value
            break
    selected_id = assigned or (str(candidate.get("deviceId")) if candidate else None)
    conflict_lines = _identity_conflict_lines(results, selected_id, identity_devices)
    candidate_conflict = bool(conflict_lines) or bool(candidate and (candidate.get("conflict") or any(
        check.get("state") == "CONFLICT" for check in candidate.get("checks", []))))
    if candidate_conflict:
        title = "Conflicting assignment"
        details = (" " + "<br>".join(html.escape(line) for line in conflict_lines)) if conflict_lines else ""
        action = ("A regular Confirm is blocked for this selection. Use the explicit manual assignment action "
                  "if the report is known to be wrong." + details)
    elif decision.get("decisionType") == "MANUAL_ASSIGNMENT":
        title, action = "Manual assignment", "The reported conflict and the administrator's choice remain in the audit."
    elif decision.get("deviceId"):
        title, action = "Confirmed by administrator", "The selected catalog model is saved for this diagnostic result."
    elif assigned:
        title, action = "Assigned catalog model", "The existing catalog assignment is shown below. Use Edit only if it needs correction."
    elif candidate:
        title, action = "Review model assignment", "Review the compact facts and confirm the suggested model, or use Edit to choose another variant."
    else:
        title, action = "Select catalog variant", "Missing evidence remains visible, but it does not prevent an explicit catalog selection."
    return ("<section class='identity-summary identity-outcome'><h3>" + title + "</h3><p>" + action + "</p>"
            + _identity_observations_markup(results, identity_devices)
            + "</section>")


def _identity_device_label(device: dict[str, Any] | None) -> str:
    if not device:
        return "No catalog model selected"
    model, variant, _ = _identity_parts(device)
    parts = [part for part in (model, variant if variant != "—" else "") if part]
    screen = device.get("screen_technology") or device.get("screenTechnology")
    if screen and not any(str(screen).casefold() in part.casefold() for part in parts):
        parts.append(str(screen))
    solar = device.get("solar")
    if not any(re.search(r"\bSolar:\s*(?:Yes|No|Not confirmed)\b", part, re.IGNORECASE) for part in parts):
        parts.append("Solar: Yes" if solar is True else "Solar: No" if solar is False else "Solar: Not confirmed")
    inreach = device.get("inreach", device.get("inReach"))
    if not any(re.search(r"\binReach:\s*(?:Yes|No|Not confirmed)\b", part, re.IGNORECASE) for part in parts):
        parts.append("inReach: Yes" if inreach is True else "inReach: No" if inreach is False else "inReach: Not confirmed")
    return " · ".join(parts) or "Unknown Garmin model"


def _identity_device_options(devices: list[dict[str, Any]] | None, current_id: Any = None, *, properties_only: bool = False) -> tuple[str, str]:
    """Render one keyboard-friendly picker while preserving exact catalog IDs."""
    current = str(current_id or "").strip()
    current_label = current or "No canonical device selected"
    options: list[str] = []
    for device in devices or []:
        device_id = str(device.get("device_id") or device.get("id") or "").strip()
        if not device_id:
            continue
        label = _identity_device_label(device)
        if device_id == current:
            current_label = label
        options.append(
            f"<button type='button' class='identity-picker-option' role='option' data-identity-device-id='{html.escape(device_id, quote=True)}' data-identity-device-label='{html.escape(label, quote=True)}'>{html.escape(label)}</button>"
        )
    return "".join(options), current_label



def _identity_picker_template(devices: list[dict[str, Any]] | None) -> str:
    """The full catalog picker, rendered once per page for every dialog."""
    options, _ = _identity_device_options(devices)
    return f"<template id='identity-picker-catalog'>{options}</template>" if options else ""

def _operation_state(results: list[dict[str, Any]], *, resolved: bool) -> str:
    if resolved:
        return "resolved"
    workflow = str(results[0].get("diagnostic_workflow_status") or "").strip().upper() if results else ""
    if _operation_issue(results):
        return {
            "UNDER_REVIEW": "under-review",
            "IN_PROGRESS": "in-progress",
        }.get(workflow, "in-progress")
    if workflow == "UNDER_REVIEW":
        return "under-review"
    if _operation_is_problematic(results):
        return "open"
    if _identity_is_pending(results):
        return "identity-pending"
    return "history"


def _is_unambiguous_legacy_result(result: dict[str, Any]) -> bool:
    """Mirror terento_fresh_result_classification's legacy write rule (migration 069)."""
    if result.get("write_started") is not None:
        return False
    schema_version = result.get("schema_version")
    if schema_version is not None:
        return schema_version in (1, 2)
    return result.get("app_build") is None and result.get("release_label") is None


def _result_classification(result: dict[str, Any]) -> str:
    outcome = str(result.get("phase_outcome") or "").strip().upper()
    finishing = str(result.get("automatic_finishing_result") or "").strip().upper()
    if outcome == "SUCCEEDED" and finishing == "VERIFIED":
        return "SUCCESS"
    if outcome == "FAILED":
        write_started = result.get("write_started")
        if write_started is True or write_started == 1 or _is_unambiguous_legacy_result(result):
            return "FAILURE"
        if write_started is False or write_started == 0:
            return "NOT_STARTED"
        return "UNKNOWN"
    if outcome == "NOT_STARTED":
        return "NOT_STARTED"
    return "UNKNOWN"


def _operation_result(results: list[dict[str, Any]]) -> str:
    classifications = {_result_classification(result) for result in results}
    if len(classifications) != 1:
        return "UNKNOWN"
    classification = next(iter(classifications))
    # A pre-write (writeStarted=false) result is "Blocked before writing", never
    # a failed installation attempt, for preflight and download stages alike
    # (ADM-13). It can still be an open problem that needs review.
    return {
        "SUCCESS": "SUCCEEDED",
        "FAILURE": "FAILED",
        "NOT_STARTED": "NOT_STARTED",
        "UNKNOWN": "UNKNOWN",
    }.get(classification, "UNKNOWN")


def _operation_write_started(results: list[dict[str, Any]]) -> bool:
    return any(
        result.get("write_started") is True or result.get("write_started") == 1
        for result in results
    )


def _operation_counts_as_installation_attempt(results: list[dict[str, Any]]) -> bool:
    """Count only a verified result or a failure after writing began."""
    result = _operation_result(results)
    if result == "SUCCEEDED":
        return True
    if result == "FAILED":
        return _operation_write_started(results) or all(
            _is_unambiguous_legacy_result(item) for item in results
        )
    return False


def _operation_text(results: list[dict[str, Any]], field: str, *, fallback: str = "—") -> str:
    values = []
    for result in results:
        value = str(result.get(field) or "").strip()
        if value and value not in values:
            values.append(value)
    return ", ".join(values) if values else fallback


def _operation_region_label(results: list[dict[str, Any]]) -> str:
    """Render result regions through the shared human-readable resolver."""
    values: list[str] = []
    for result in results:
        label = _admin_region_display_name(
            result.get("canonical_region_id"),
            result.get("region_country"),
            result.get("region"),
            result.get("map_package_name"),
        )
        if label != "—" and label not in values:
            values.append(label)
    return ", ".join(values) if values else "—"


def _operation_map_label(results: list[dict[str, Any]]) -> str:
    """Keep each reported region paired with its actual provider in the summary."""
    providers = {'freizeitkarte': 'Freizeitkarte', 'opentopomap': 'OpenTopoMap',
                 'maprando': 'MapRando', 'bbbike': 'BBBike', 'custom': 'Custom import'}
    labels = []
    for row in results:
        provider = str(row.get('provider') or row.get('provider_id') or '').strip()
        region = _operation_region_label([row])
        label = ' · '.join(part for part in (region if region != '—' else '', providers.get(provider, provider)) if part)
        if label and label not in labels:
            labels.append(label)
    return ', '.join(labels) if labels else 'Map not recorded'


def _diagnostic_heading(outcome: Any, *, update: bool = False) -> str:
    operation = 'Map update' if update else 'Installation'
    suffix = {'FAILED': 'failed', 'SUCCEEDED': 'succeeded', 'NOT_STARTED': 'blocked before writing',
              'BLOCKED': 'blocked', 'INCOMPLETE': 'incomplete'}.get(str(outcome or '').upper(), 'result unknown')
    return operation + ' ' + suffix


def _operation_issue(results: list[dict[str, Any]]) -> str | None:
    for result in results:
        try:
            value = _normalise_github_issue_reference(result.get("linked_github_issue"))
        except ValueError:
            value = None
        if value:
            return value
    return None


def _github_issue_link(value: Any) -> str:
    try:
        issue = _normalise_github_issue_reference(value)
    except ValueError:
        issue = None
    if not issue:
        return "<span class='muted-value'>—</span>"
    number = issue[1:]
    return (
        f"<a class='github-issue' href='https://github.com/VooZ2/terento/issues/{number}' "
        f"target='_blank' rel='noreferrer' aria-label='Open GitHub issue {number}'>"
        f"#{number} {_admin_icon('external')}</a>"
    )


def _sanitised_issue_value(value: Any, *, max_length: int | None = None) -> str:
    """Sanitise one allowlisted report value before Markdown or URL encoding."""
    text = str(value or "")[:_ADMIN_TEXT_INPUT_LIMIT]
    text = re.sub(r"[\x00-\x1f\x7f]+", " ", text).strip()
    # This is report text, not HTML. Remove angle brackets directly instead of
    # attempting to parse HTML with a backtracking regular expression.
    text = text.replace("<", "[redacted markup]").replace(">", "[redacted markup]")
    text = re.sub(r"(?i)\b(?:ghp|github_pat)_[A-Za-z0-9_\-]+", "[redacted token]", text)
    text = re.sub(r"(?i)\bBearer\s+[^\s,;]+", "Bearer [redacted]", text)
    text = re.sub(
        r"(?i)\b(authorization|proxy-authorization|cookie|set-cookie)\s*:\s*[^\s,;]+(?:\s+[^\s,;]+)?",
        lambda match: f"{match.group(1)}: [redacted]",
        text,
    )
    text = re.sub(
        r"(?i)([?&](?:token|access_token|api_key|apikey|secret)=)[^&\s]+",
        lambda match: f"{match.group(1)}[redacted]",
        text,
    )
    text = re.sub(
        r"(?i)[?&](?:title|body)=[^&\s]+",
        "[redacted query value]",
        text,
    )
    text = re.sub(
        r"(?i)\b(token|access[_ -]?token|api[_ -]?key|apikey|secret|password|cookie|authorization)\s*[:=]\s*\S+",
        lambda match: f"{match.group(1)}=[redacted]",
        text,
    )
    text = re.sub(r"\b[A-Z][A-Z0-9_]{2,}\s*=\s*\S+", "[redacted environment value]", text)
    text = re.sub(
        r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
        "[redacted email]",
        text,
    )
    text = re.sub(r"(?i)/Users/[^/\s]+(?:/[^\s]*)?", "/Users/<redacted>/[redacted]", text)
    text = re.sub(
        r"(?i)(?:/private|/var/folders|/home|/Volumes)/(?:[^\s]+)",
        "[redacted path]",
        text,
    )
    text = re.sub(
        r"(?i)\b[A-Z]:[\\/]Users[\\/][^\\/\s]+(?:[\\/][^\s]*)?",
        "[redacted path]",
        text,
    )
    text = re.sub(
        r"(?i)\b(serial(?:[_ -]?number)?|unit[_ -]?id|device[_ -]?id|user[_ -]?id|account[_ -]?id)\s*[:=]\s*\S+",
        lambda match: f"{match.group(1)}=[redacted]",
        text,
    )
    text = re.sub(r"\s+", " ", text).strip()
    if max_length is not None:
        text = text[:max_length]
    return text


def _markdown_issue_value(value: Any, *, max_length: int | None = None) -> str:
    text = _sanitised_issue_value(value, max_length=max_length)
    return re.sub(r"([\\`*_{}\[\]<>#+!|])", r"\\\1", text)


def _operation_report_value(results: list[dict[str, Any]], *fields: str) -> str:
    for field in fields:
        value = _operation_text(results, field, fallback="")
        if value:
            return _markdown_issue_value(value)
    return ""


def _operation_report_boolean(results: list[dict[str, Any]], field: str) -> str:
    values: list[str] = []
    for result in results:
        if field not in result or result.get(field) is None:
            continue
        label = "Yes" if bool(result.get(field)) else "No"
        if label not in values:
            values.append(label)
    return ", ".join(values)


def _github_issue_report(
    identity: str,
    results: list[dict[str, Any]],
    *,
    device: dict[str, Any] | None = None,
    admin_note: str | None = None,
) -> tuple[str, str]:
    """Build a public report exclusively from explicitly allowlisted fields."""
    model, variant = _display_identity(identity)
    first = results[0] if results else {}
    device = device or {}
    result = _markdown_issue_value(_operation_result(results))
    stage = _operation_report_value(results, "failure_stage")
    code = _operation_report_value(results, "failure_code")
    native_code = _operation_report_value(results, "native_failure_code")
    model_value = _markdown_issue_value(model)
    variant_value = _markdown_issue_value(variant) if variant != "—" else ""
    title_stage = _sanitised_issue_value(_operation_text(results, "failure_stage", fallback=""))
    title_code = _sanitised_issue_value(_operation_text(results, "failure_code", fallback=""))
    title_model = _sanitised_issue_value(model)
    title_variant = _sanitised_issue_value(variant) if variant != "—" else ""
    model_variant = " · ".join(value for value in (title_model, title_variant) if value)
    title = (
        f"[Install][{title_stage.title()}] {model_variant}"
        if result == "FAILED" and title_stage else
        f"[Installation failure] {model_variant}"
        if result == "FAILED" else
        f"[Installation anomaly] {model_variant}"
    )
    if title_code:
        title += f" — {title_code}"

    family = _markdown_issue_value(
        device.get("familyName") or device.get("family_name") or device.get("family")
        or _operation_text(results, "family", fallback="")
    )
    part_number = _markdown_issue_value(device.get("partNumber") or device.get("part_number"))
    sections: list[tuple[str, list[tuple[str, str]]]] = [
        ("Summary", [
            ("Result", result),
            ("Failure stage", stage),
            ("Error category", _operation_report_value(results, "error_category")),
            ("Error code", code),
        ]),
        ("Device", [
            ("Model", model_value),
            ("Variant", variant_value),
            ("Family", family),
            ("Part number", part_number),
            ("Firmware", _operation_report_value(results, "firmware_version")),
            ("Raw MTP model", _operation_report_value(results, "raw_mtp_model")),
        ]),
        ("Installation", [
            ("Operation", "Map installation"),
            ("Map", _operation_report_value(results, "provider")),
            ("Region", _operation_report_value(results, "region")),
            ("Map version", _operation_report_value(results, "map_release")),
            ("App version", _operation_report_value(results, "release_label", "terento_version")),
            ("Build", _operation_report_value(results, "app_build")),
            ("Timestamp", _operation_report_value(results, "occurred_at")),
        ]),
        ("Failure details", [
            ("Write started", _operation_report_boolean(results, "write_started")),
            ("Transfer progress", _operation_report_value(results, "transfer_progress_bucket")),
            ("Object created", _operation_report_boolean(results, "remote_object_created")),
            ("Cleanup attempted", _operation_report_boolean(results, "cleanup_attempted")),
            ("Cleanup succeeded", _operation_report_boolean(results, "cleanup_succeeded")),
            ("Transport", _operation_report_value(results, "transport")),
            ("Reported transport category (may be inferred)", native_code),
        ]),
        ("Reference", [
            ("Diagnostic ID", _markdown_issue_value(_operation_key(first))),
            ("Installation ID", _operation_report_value(results, "event_id")),
        ]),
    ]
    rendered_sections: list[str] = []
    for heading, fields in sections:
        rows = [f"- {label}: {value}" for label, value in fields if value]
        if rows:
            rendered_sections.append(f"## {heading}\n\n" + "\n".join(rows))
    for number, item in enumerate(results, 1):
        source = 'Custom import' if item.get('provider') == 'custom' else _markdown_issue_value(item.get('provider')) or 'unavailable'
        context = item.get('failure_context') or {}
        stage = item.get('optional_component_failure_stage') if isinstance(context, dict) and context.get('componentKind') == 'contours' else item.get('failure_stage')
        rows = [f'- Source: {source}', f'- Failure stage: {_markdown_issue_value(stage) or "unavailable"}']
        if item.get('provider') == 'custom':
            rows.extend(['- Acquisition: manually imported IMG', '- Original file provenance: not tracked'])
        for key, label in (('failure_context', 'Failure'), ('original_failure_context', 'Original failure')):
            if key == 'original_failure_context' and item.get(key) is None:
                rows.append('- Original failure context: unavailable')
            else:
                rows.extend(f'- {label} {name.lower()}: {_markdown_issue_value(str(value))}' for name, value in _failure_context_fields(item, key, technical=item.get(key) is not None))
        rendered_sections.append(f'## {_failure_result_label(item, number)} diagnostics\n\n' + '\n'.join(rows))
    if result == "FAILED":
        rendered_sections.append(
            "## Detailed diagnostics\n\n"
            "This administrator summary contains uploaded outcome fields, not the local Finishing trace. "
            "The transport category may be inferred from the application failure; it is not a raw native return code. "
            "For the detailed sequence, use Report issue in the failing app (beta.10 build 15 or later) "
            "and review the copied report before sharing. Earlier reports cannot be expanded retroactively."
        )
    note = _markdown_issue_value(admin_note, max_length=GITHUB_ADMIN_NOTE_MAX_LENGTH)
    if note:
        rendered_sections.append(f"## Admin note\n\n{note}")
    return _sanitised_issue_value(title, max_length=180), "\n\n".join(rendered_sections)


def _github_issue_url(
    identity: str,
    results: list[dict[str, Any]],
    *,
    device: dict[str, Any] | None = None,
    admin_note: str | None = None,
) -> tuple[str, bool]:
    title, body = _github_issue_report(identity, results, device=device, admin_note=admin_note)
    candidate = GITHUB_NEW_ISSUE_URL + "?" + urlencode({"title": title, "body": body})
    if len(candidate) > GITHUB_ISSUE_URL_MAX_LENGTH:
        return GITHUB_NEW_ISSUE_URL, False
    return candidate, True


# Every <details> in the installation dialog and the update report uses this one
# disclosure presentation (owner decision 2026-10-06).
DIAGNOSTIC_DISCLOSURE_CLASS = "admin-disclosure diagnostic-disclosure"


def _github_issue_controls(issue_title: str, issue_body: str, *, issue: str | None,
                           csrf_token: str, identifier: str, return_to: str,
                           action: str = "/admin/diagnostics/issue",
                           identifier_name: str = "operation_key") -> str:
    """Shared review-first controls; report producers supply sanitized allowlisted text."""
    candidate = GITHUB_NEW_ISSUE_URL + "?" + urlencode({"title": issue_title, "body": issue_body})
    issue_prefilled = len(candidate) <= GITHUB_ISSUE_URL_MAX_LENGTH
    issue_url = candidate if issue_prefilled else GITHUB_NEW_ISSUE_URL
    return f"""
        <div class='github-actions'><a class='secondary-button' href='{html.escape(issue_url, quote=True)}' data-github-create data-issue-title='{html.escape(issue_title, quote=True)}' data-issue-body='{html.escape(issue_body, quote=True)}' data-prefilled='{'true' if issue_prefilled else 'false'}' data-url-limit='{GITHUB_ISSUE_URL_MAX_LENGTH}' target='_blank' rel='noreferrer'>Prepare GitHub issue</a><button class='secondary-button' type='button' data-copy-issue-report>Copy issue report</button><span class='copy-status' data-copy-status role='status' aria-live='polite'>{'Report is too large to prefill; copy it instead.' if not issue_prefilled else ''}</span></div>
        <details class='{DIAGNOSTIC_DISCLOSURE_CLASS} github-issue-preview'><summary>Preview issue report</summary><div class='disclosure-body'><label>Title<input value='{html.escape(issue_title, quote=True)}' readonly data-issue-preview-title></label><label>Body<textarea rows='8' readonly data-issue-preview-body>{html.escape(issue_body)}</textarea></label><label>Admin note <span class='optional-label'>Optional · maximum {GITHUB_ADMIN_NOTE_MAX_LENGTH} characters</span><textarea rows='3' maxlength='{GITHUB_ADMIN_NOTE_MAX_LENGTH}' data-issue-note></textarea></label></div></details>
        <details class='{DIAGNOSTIC_DISCLOSURE_CLASS} github-link-disclosure'><summary>Link or manage an existing issue</summary><div class='disclosure-body'><form method='post' action='{html.escape(action, quote=True)}' class='github-link-form admin-async-action'>
          <input type='hidden' name='csrf_token' value='{html.escape(csrf_token, quote=True)}'>
          <input type='hidden' name='{html.escape(identifier_name, quote=True)}' value='{html.escape(identifier, quote=True)}'>
          <input type='hidden' name='return_to' value='{html.escape(return_to, quote=True)}'>
          <label>{'Change' if issue else 'Link'} issue <span class='optional-label'>e.g. #32</span><input name='linked_github_issue' placeholder='#32' inputmode='numeric' pattern='#?[0-9]{{1,10}}'></label>
          <button type='submit' class='secondary-button'>{'Change linked issue' if issue else 'Link issue'}</button>
        </form>
        {f"<form method='post' action='{html.escape(action, quote=True)}' class='github-remove-form admin-async-action' data-confirm='Unlink this GitHub issue from this diagnostic?'><input type='hidden' name='csrf_token' value='{html.escape(csrf_token, quote=True)}'><input type='hidden' name='{html.escape(identifier_name, quote=True)}' value='{html.escape(identifier, quote=True)}'><input type='hidden' name='return_to' value='{html.escape(return_to, quote=True)}'><input type='hidden' name='linked_github_issue' value=''><button type='submit' class='secondary-button'>Unlink issue</button></form>" if issue else ''}</div></details>"""


def _installation_explanation(results: list[dict[str, Any]]) -> tuple[str, str]:
    outcome = _operation_result(results)
    if outcome == 'SUCCEEDED':
        return 'The installation succeeded.', 'No failure action is required.'
    first = next((row for row in results if row.get('failure_code') or row.get('failure_stage')), results[0])
    code = str(first.get('failure_code') or '')
    stage = str(first.get('failure_stage') or '')
    specific = {
        'INSTALL_BLOCKED_EXISTING_MAP_CONFLICT': ('An existing map conflicts with this installation.', 'Review installed maps in Terento before trying again. Do not remove unknown device files.'),
        'INSTALL_FAILED_PREFLIGHT_MTP_READ': ('Terento could not read the device before installation.', 'Reconnect the device and rescan it in Terento.'),
        'INSTALL_FAILED_MANIFEST': ('The local ownership record could not be saved.', 'Review the installed map and local diagnostic report before retrying.'),
        'INSTALL_FAILED_CLEANUP': ('Cleanup did not complete.', 'Inspect the device in Terento and review the local diagnostic report. Do not remove unknown files.'),
        'INSTALL_BLOCKED_UNKNOWN_INSTALL_SIZE': ('The required installation size could not be established.', 'Recheck the provider package before retrying.'),
        'INSTALL_BLOCKED_TRANSACTION_ALREADY_RUNNING': ('Another device operation is running.', 'Wait for that operation to finish, then retry in Terento.'),
        'INSTALL_BLOCKED_TERENTO_DEVICE_SCOPE': ('Device authorization did not permit installation.', 'Review the exact model and its authorization result in Terento.'),
    }
    if code in specific:
        return specific[code]
    if stage == 'extract':
        return 'The map package could not be extracted.', 'Check available Mac storage and the provider package before retrying.'
    reason = normalize_failure_reason(first.get('error_category'), failure_stage=stage, failure_code=code)
    return {
        'verification': ('The transferred map did not pass device verification. The failed check does not establish the root cause.', 'Reconnect and inspect the installed-map status in Terento. Review the local diagnostic report before retrying.'),
        'source_validation': ('The map package did not pass source validation.', 'Recheck the provider package before retrying.'),
        'acquisition': ('The map could not be downloaded or prepared.', 'Check the provider package and Mac connection before retrying.'),
        'storage': ('The reported failure concerns device storage.', 'Review the available space in Terento. Keep existing working maps until a safe installation is possible.'),
        'device_disconnected': ('The device disconnected during installation.', 'Reconnect and inspect its map status in Terento before retrying.'),
        'transport': ('The map could not be written to the device.', 'Reconnect and inspect its map status in Terento. Review the local diagnostic report if the failure repeats.'),
    }.get(reason, ('The installation did not complete. This report does not establish the cause.', 'Review the technical details and request the local Terento diagnostic report. Prepare an issue with the available evidence.'))


def _diagnostic_outcome_sections(reason_markup: str, action_markup: str, safety_rows: str) -> str:
    """Shared What happened / Next action summary and Safety facts (escaped markup in)."""
    return (
        "<section class='diagnostic-section diagnostic-outcome'><h3>What happened</h3>"
        f"<p>{reason_markup}</p>"
        f"<p class='diagnostic-next-action'><strong>Next action</strong><span>{action_markup}</span></p></section>"
        "<section class='diagnostic-section diagnostic-safety'><h3>Safety facts</h3>"
        f"<dl class='diagnostic-detail-summary'>{safety_rows}</dl></section>"
    )


def _diagnostic_review_administration(forms: str) -> str:
    """Resolve/reopen and workflow forms in one collapsed disclosure; omitted when empty."""
    if not forms.strip():
        return ""
    return (
        f"<details class='{DIAGNOSTIC_DISCLOSURE_CLASS} diagnostic-review-administration'><summary>Review administration</summary>"
        "<div class='disclosure-body'><p class='table-help'>Resolving marks the diagnostic as reviewed; it does not repair the map or change the original result.</p>"
        f"<div class='diagnostic-review-forms'>{forms}</div></div></details>"
    )


def _identity_review_form(
    operation_key: str,
    results: list[dict[str, Any]],
    *,
    csrf_token: str,
    identity_devices: list[dict[str, Any]] | None,
    return_to: str,
    id_suffix: str,
    catalog_template: bool = False,
    inline: bool = False,
    result_label: str = "",
) -> str:
    """The one Device identity form, shared by the diagnostic dialog and the
    Identity review queue. It posts one exact result to
    ``/admin/diagnostics/identity`` with the same fields everywhere.

    ``inline`` (the queue) names a preselected model as the suggestion, keeps a
    whole-catalog picker behind ``Pick model`` and confirms in place.
    """
    first = results[0]
    recommendation = _identity_recommendation(results)
    selection_id = str(first.get("canonical_device_model_id") or (recommendation or {}).get("deviceId") or "").strip()
    picker_devices = identity_devices or []
    if not selection_id:
        candidate_ids = {
            str(candidate.get("deviceId") or "").strip()
            for assessment in _identity_assessments(results)
            for candidate in _identity_presentation_candidates(assessment)
            if str(candidate.get("deviceId") or "").strip()
        }
        if candidate_ids:
            picker_devices = [
                device for device in picker_devices
                if str(device.get("id") or device.get("device_id") or "").strip() in candidate_ids
            ]
    # When the picker would list the whole catalog, the page renders it once in
    # a <template> and the dialog clones it on open (DES-01 interim fix).
    use_page_catalog = catalog_template and picker_devices is identity_devices
    options, current_label = _identity_device_options(
        [] if use_page_catalog else picker_devices, selection_id,
    )
    if use_page_catalog and selection_id:
        _, current_label = _identity_device_options(
            [device for device in identity_devices or []
             if str(device.get("device_id") or device.get("id") or "").strip() == selection_id],
            selection_id,
        )
    selected_candidate = _identity_candidate(results, selection_id or None)
    conflict_lines = _identity_conflict_lines(results, selection_id, identity_devices)
    selection_conflict = bool(conflict_lines) or bool(selected_candidate and (selected_candidate.get("conflict") or any(
        check.get("state") == "CONFLICT" for check in selected_candidate.get("checks", []))))
    conflict_detail = " ".join(conflict_lines) if conflict_lines else (
        "The selected model conflicts with reported information." if selection_conflict else ""
    )
    # The queue keeps every picker closed until Edit / Pick model, so each
    # pending item stays one compact row.
    picker_hidden = bool(selection_id) or inline
    search_id = f"identity-search-{id_suffix}"
    canonical_id = f"identity-canonical-{id_suffix}"
    selection_term = (
        "Suggested model" if inline and not first.get("canonical_device_model_id")
        else "Selected model"
    )
    empty_selection = "No suggestion" if inline else "No model selected"
    empty_attribute = f" data-identity-empty='{empty_selection}'" if inline else ""
    edit_label = "Pick model" if inline and not selection_id else "Edit"
    edit_hidden = not selection_id and not inline
    for_result = f"<p class='identity-review-for'>{html.escape(result_label)}</p>" if result_label else ""
    inline_attribute = " data-identity-inline" if inline else ""
    return f"""
      <form method='post' action='/admin/diagnostics/identity' class='diagnostic-action-form identity-review-form admin-async-action' data-identity-form{inline_attribute}>
        <input type='hidden' name='csrf_token' value='{html.escape(csrf_token, quote=True)}'>
        <input type='hidden' name='operation_key' value='{html.escape(operation_key, quote=True)}'>
        <input type='hidden' name='return_to' value='{html.escape(return_to, quote=True)}'>
        {for_result}<dl class='identity-selection'><div><dt>{selection_term}</dt><dd data-identity-selection{empty_attribute}>{html.escape(current_label) if selection_id else empty_selection}</dd></div></dl>
        <div class='identity-picker' data-canonical-device-wrap{' hidden' if picker_hidden else ''}>
          <label for='{search_id}'>Find a catalog model<input id='{search_id}' type='search' data-identity-search role='combobox' aria-expanded='{'false' if picker_hidden else 'true'}' aria-controls='{canonical_id}-options' placeholder='Search model, size or variant' autocomplete='off' value='{html.escape(current_label if selection_id else '', quote=True)}'></label>
          <input type='hidden' name='canonical_device_model_id' id='{canonical_id}' value='{html.escape(selection_id, quote=True)}'>
          <div class='identity-search-results' id='{canonical_id}-options' data-identity-results{" data-identity-catalog='page'" if use_page_catalog else ""} role='listbox' aria-label='Matching Garmin catalog models'>{options}</div>
        </div>
        {f"<p class='identity-conflict-warning' data-identity-conflict role='alert'>{html.escape(conflict_detail)} Use the explicit manual assignment action if this is the intended correction.</p>" if conflict_detail else ""}
        <div class='identity-review-actions'><button type='button' class='secondary-button' data-identity-edit{' hidden' if edit_hidden else ''}>{edit_label}</button><button type='submit' name='identity_action' value='ASSIGN' data-identity-confirm>Confirm</button><button type='submit' name='identity_action' value='MANUAL_ASSIGN' class='secondary-button' data-manual-confirm{' hidden' if not selection_conflict else ''}>Confirm manual assignment</button></div>
        <p class='admin-action-status' data-identity-status role='status' aria-live='polite'></p>
      </form>"""


def _diagnostic_detail_dialog(
    identity: str,
    operation_key: str,
    results: list[dict[str, Any]],
    *,
    resolved: bool,
    csrf_token: str,
    identity_devices: list[dict[str, Any]] | None,
    canonical_device_model_id: str | None = None,
    return_to: str | None = None,
    catalog_template: bool = False,
) -> str:
    first = results[0]
    dialog_id = "diagnostic-detail-" + hashlib.sha256(operation_key.encode("utf-8")).hexdigest()[:16]
    model, variant = _display_identity(identity)
    catalog_device = next((d for d in identity_devices or []
                           if (d.get('id') or d.get('device_id')) == first.get('canonical_device_model_id')), None)
    if catalog_device:
        model, variant, _ = _identity_parts(catalog_device)
    issue = _operation_issue(results)
    result_label = _operation_result(results)
    state = _operation_state(results, resolved=resolved)
    identity_pending = _identity_is_pending(results)
    return_to = return_to or _diagnostics_url({
        "compatibility_identity": identity,
        "canonical_device_model_id": canonical_device_model_id,
    })
    technical = "".join(
        _diagnostic_technical_details(result, index)
        for index, result in enumerate(results, start=1)
    )
    resolution = ""
    if resolved:
        resolution = "".join(
            part for part in (
                f" · {html.escape(str(first.get('resolution_reason') or 'Resolved'))}" if first.get("resolution_reason") else "",
                f" · {_timestamp_markup(first.get('resolved_at'))}" if first.get("resolved_at") else "",
                f" · by {html.escape(str(first.get('resolved_by_username')))}" if first.get("resolved_by_username") else "",
            )
        )
    if resolved:
        lifecycle_action = f"""
          <form method='post' action='/admin/diagnostics/reopen' class='diagnostic-action-form admin-async-action'>
            <input type='hidden' name='csrf_token' value='{html.escape(csrf_token, quote=True)}'>
            <input type='hidden' name='operation_key' value='{html.escape(operation_key, quote=True)}'>
            <input type='hidden' name='return_to' value='{html.escape(return_to, quote=True)}'>
            <button type='submit' class='secondary-button'>Reopen diagnostic</button>
          </form>"""
    elif state in {"open", "in-progress", "under-review"}:
        lifecycle_action = f"""
          <form method='post' action='/admin/diagnostics/resolve' class='diagnostic-action-form admin-async-action' data-confirm='Mark this error as resolved? The installation will remain failed in history and statistics.'>
            <input type='hidden' name='csrf_token' value='{html.escape(csrf_token, quote=True)}'>
            <input type='hidden' name='operation_key' value='{html.escape(operation_key, quote=True)}'>
            <input type='hidden' name='return_to' value='{html.escape(return_to, quote=True)}'>
            <h4>Resolve diagnostic</h4>
            <label>Reason<select name='resolution_reason' required><option value='FIXED'>Fixed</option><option value='HISTORICAL_SUPERSEDED'>Historical / superseded</option><option value='DUPLICATE'>Duplicate</option><option value='IDENTITY_CORRECTED'>Identity corrected</option><option value='NOT_TERENTO_ISSUE'>Not a Terento issue</option><option value='OTHER'>Other</option></select></label>
            <label>Resolution note <span class='optional-label'>Optional</span><textarea name='resolution_note' rows='3'></textarea></label>
            <button type='submit'>Resolve diagnostic</button>
          </form>"""
    else:
        lifecycle_action = ""
    identity_form = _identity_review_form(
        operation_key, results, csrf_token=csrf_token, identity_devices=identity_devices,
        return_to=return_to, id_suffix=dialog_id, catalog_template=catalog_template,
    )
    identity_section = (
        f"<section class='diagnostic-section diagnostic-identity-section' aria-labelledby='{dialog_id}-identity-title'>"
        f"<h3 id='{dialog_id}-identity-title'>Device identity</h3>{identity_form}</section>"
    )
    report_device = next((
        device for device in (identity_devices or [])
        if str(device.get("id") or device.get("device_id") or "") == str(canonical_device_model_id or "")
    ), None)
    issue_title, issue_body = _github_issue_report(identity, results, device=report_device)
    issue_controls = _github_issue_controls(issue_title, issue_body, issue=issue,
        csrf_token=csrf_token, identifier=operation_key, return_to=return_to)
    issue_form = f"<section class='diagnostic-section diagnostic-issue-section github-review'><h3>GitHub issue</h3><p class='github-current'>{_github_issue_link(issue) if issue else 'No linked issue'}</p><p class='table-help'>Review the report before sharing. A closed linked issue resolves this diagnostic after synchronization; the installation result stays in history.</p><div class='github-issue-controls'>{issue_controls}</div></section>"
    workflow_form = ""
    if not resolved and issue:
        workflow_value = {
            "in-progress": "IN_PROGRESS",
            "under-review": "UNDER_REVIEW",
        }.get(state, "IN_PROGRESS")
        workflow_form = f"""
      <form method='post' action='/admin/diagnostics/workflow' class='diagnostic-action-form diagnostic-workflow-form admin-async-action'>
        <input type='hidden' name='csrf_token' value='{html.escape(csrf_token, quote=True)}'>
        <input type='hidden' name='operation_key' value='{html.escape(operation_key, quote=True)}'>
        <input type='hidden' name='return_to' value='{html.escape(return_to, quote=True)}'>
        <h4>GitHub issue workflow</h4>
        <p class='table-help'>The linked issue stays in Review Queue until GitHub reports it as closed.</p>
        <label>Status<select name='diagnostic_workflow_status' required><option value='IN_PROGRESS'{" selected" if workflow_value == "IN_PROGRESS" else ""}>In progress</option><option value='UNDER_REVIEW'{" selected" if workflow_value == "UNDER_REVIEW" else ""}>Under review</option></select></label>
        <button type='submit' class='secondary-button'>Save workflow status</button>
      </form>"""
    review_state = ""
    if resolved:
        review_state = f"<div><dt>Review state</dt><dd>{_diagnostic_state_badge('RESOLVED')}{resolution}</dd></div>"
    elif state in {"open", "in-progress", "under-review"}:
        identity_badge = f" {_diagnostic_state_badge('IDENTITY_PENDING')}" if identity_pending else ""
        state_badge = _diagnostic_state_badge(state.replace("-", "_"))
        review_state = f"<div><dt>Review state</dt><dd>{state_badge}{identity_badge}</dd></div>"
    elif identity_pending:
        review_state = f"<div><dt>Review state</dt><dd>{_diagnostic_state_badge('IDENTITY_PENDING')}</dd></div>"
    reason, next_action = _installation_explanation(results)
    if identity_pending:
        next_action += ' Assign the exact catalog model in Device identity below.'
    safety = "".join(f"<div><dt>{label}</dt><dd>{html.escape(_operation_report_boolean(results, field) or 'Unknown')}</dd></div>"
        for label, field in (("Write started", "write_started"), ("Cleanup attempted", "cleanup_attempted"), ("Cleanup succeeded", "cleanup_succeeded")))
    failure_summary = _diagnostic_outcome_sections(html.escape(reason), html.escape(next_action), safety)
    technical_details = f"<details class='{DIAGNOSTIC_DISCLOSURE_CLASS} diagnostic-technical-section'><summary>Technical details</summary><div class='disclosure-body'><p class='diagnostic-id'>Diagnostic ID: <code>{html.escape(operation_key)}</code></p><div class='technical-copy-actions'><button type='button' class='secondary-button' data-copy-diagnostic-id='{html.escape(operation_key, quote=True)}'>Copy diagnostic ID</button><button type='button' class='secondary-button' data-copy-technical-report data-report='{html.escape(issue_body, quote=True)}'>Copy technical report</button><span class='copy-status' data-copy-status role='status' aria-live='polite'></span></div>{technical}</div></details>"
    administration = _diagnostic_review_administration(f"{lifecycle_action}{workflow_form}")
    model_markup = html.escape(model)
    if first.get('canonical_device_model_id'):
        model_markup = f"<a href='{html.escape(_device_detail_url(first['canonical_device_model_id']), quote=True)}'>{model_markup}</a>"
    return f"""
      <dialog class='diagnostic-detail-dialog' id='{dialog_id}' aria-labelledby='{dialog_id}-title'>
        <div class='diagnostic-detail-inner'>
          <div class='device-dialog-header'><div><h2 id='{dialog_id}-title'>{_diagnostic_heading(result_label)}</h2></div><button class='dialog-close' type='button' data-close-dialog aria-label='Close diagnostic detail'>{_admin_icon('close')}</button></div>
          <dl class='diagnostic-detail-summary'>
            <div><dt>Operation</dt><dd>Map installation</dd></div>
            <div><dt>Device</dt><dd>{model_markup}</dd></div>
            <div><dt>Variant</dt><dd>{html.escape(variant)}</dd></div>
            <div><dt>Date</dt><dd>{_timestamp_markup(first.get('occurred_at'))}</dd></div>
            <div><dt>Map / region</dt><dd>{html.escape(_operation_map_label(results))}</dd></div>
            <div><dt>Result</dt><dd>{_diagnostic_result(result_label)}</dd></div>
            <div><dt>App version</dt><dd>{html.escape(_admin_app_version_label(first.get('release_label') or first.get('terento_version'), first.get('app_build')))}</dd></div>
            {review_state}
          </dl>
          {failure_summary}
          {issue_form}
          <div class='diagnostic-disclosure-stack'>{administration}{technical_details}</div>
          {identity_section}
        </div>
      </dialog>"""


def _detail_rows(items: list[tuple[str, Any, bool]]) -> str:
    rows: list[str] = []
    for label, value, is_markup in items:
        if value is None or value == "" or value == "—":
            continue
        rendered = str(value) if is_markup else html.escape(str(value))
        rows.append(f"<div><dt>{html.escape(label)}</dt><dd>{rendered}</dd></div>")
    return "".join(rows)


def _usb_identity_details(identities: list[dict[str, Any]] | None) -> str:
    values: list[str] = []
    for identity in identities or []:
        vendor = identity.get("vendorId")
        product = identity.get("productId")
        if vendor is None or product is None:
            continue
        try:
            values.append(f"VID 0x{int(vendor):04X} · PID 0x{int(product):04X}")
        except (TypeError, ValueError):
            continue
    return ", ".join(values)


def _device_information_markup(device: dict[str, Any]) -> str:
    """Catalog facts first; absence stays unknown and is never inferred from a name."""
    def feature(key: str) -> str:
        value = device.get(key)
        return "Available" if value is True else "Not included" if value is False else "Not confirmed"

    size = device.get("caseSizeMm")
    facts = _detail_rows([(label, f"<bdi>{html.escape(str(value))}</bdi>", True) for label, value in [
        ("Watch size", f"{size} mm" if size else "Not confirmed"),
        ("Display", device.get("screenTechnology") or "Not confirmed"),
        ("Solar charging", feature("solar")),
        ("inReach", feature("inReach")),
    ]])
    evidence = device.get("specificationEvidence") or {}
    more = _detail_rows([
        ("Dimensions", (evidence.get("physical_size") or {}).get("value"), False),
        ("Screen size", (evidence.get("display_size") or {}).get("value"), False),
        ("Resolution", (evidence.get("display_resolution") or {}).get("value"), False),
        ("Family", device.get("familyName") or device.get("family"), False),
    ])
    more = ("<details class='device-extra-specifications admin-disclosure'><summary>More specifications</summary>"
            f"<dl class='model-information-list'>{more}</dl></details>") if more else ""
    source_url = str(device.get("specificationSource") or "")
    try:
        source = urlsplit(source_url)
        official_source = source.scheme == "https" and (source.hostname == "garmin.com" or (source.hostname or "").endswith(".garmin.com"))
    except ValueError:
        official_source = False
    source_link = (f"<a class='device-specification-link' href='{html.escape(source_url, quote=True)}' "
                   f"target='_blank' rel='noopener noreferrer'>View Garmin specifications {_admin_icon('external')}</a>") if official_source else ""
    note = ("<p class='device-information-note'>Not confirmed means the catalog does not yet have a verified value.</p>"
            if not size or not device.get("screenTechnology") or any(device.get(key) is None for key in ("solar", "inReach")) else "")
    return (f"<dl class='device-key-facts'>{facts}</dl>"
            f"{note}"
            f"<div class='device-information-more'>{more}{source_link}</div>")


def device_detail_page(
    device: dict[str, Any], user: dict[str, Any], csrf_token: str, *,
    operations: list[dict[str, Any]] | None = None,
    resolved_operations: list[dict[str, Any]] | None = None,
    identity_devices: list[dict[str, Any]] | None = None,
    origin: str = "devices",
    requested_state: str | None = None,
    update_history: dict[str, Any] | None = None,
    open_problem_count: int | None = None,
) -> bytes:
    device_id = str(device.get("id") or "").strip()
    model, variant, _ = _identity_parts(device)
    identity = " · ".join(part for part in (model, variant if variant != "—" else "") if part)

    def matches(event: dict[str, Any]) -> bool:
        return str(event.get("canonical_device_model_id") or "").strip() == device_id

    active_events = [
        event for event in (operations or [])
        if matches(event)
        and not _is_preinstall_download_operation([event])
    ]
    resolved_events = [
        event for event in (resolved_operations or [])
        if matches(event)
        and not _is_preinstall_download_operation([event])
    ]
    active_groups = _group_operations(active_events)
    resolved_groups = _group_operations(resolved_events)
    history = [(key, results, False) for key, results in active_groups.items()]
    history.extend((key, results, True) for key, results in resolved_groups.items())
    history.sort(key=lambda item: _timestamp_iso(item[1][0].get("occurred_at")), reverse=True)

    stats = device.get("installationStats") or {}
    attempts = int(stats.get("attempts") or 0)
    successful = int(stats.get("successful") or 0)
    failed = int(stats.get("failed") or 0)
    open_errors = (
        int(open_problem_count) if open_problem_count is not None
        else _open_problem_operation_count(active_events)
    )
    status = calculate_compatibility_status(
        successful_install_count=successful,
        recognized_map_capable_evidence=device.get("observedMapCapability") is True,
    )
    status_value = device.get("evidenceStatus") or (status.value if status else "")
    last_activity = _timestamp_markup(stats.get("lastEvidenceAt")) if stats.get("lastEvidenceAt") else "—"
    publication = device.get("publicCompatibility") or {}
    map_label, map_kind = _admin_map_capability(device.get("mapCapable"))
    authorization_label, authorization_kind, _ = _admin_installation_authorization_code(
        device.get("installationAuthorization")
    )
    provenance = _status_pill("neutral", "Historical catalog entry") if _is_historical_catalog(device) else ""
    if variant == "Historical":
        variant = "—"
    status_line = (
        f"<div class='model-status-line'>{provenance}"
        f"<span><strong>Maps</strong> {_admin_status_badge(map_label, f'map-{map_kind}')}</span>"
        f"<span><strong>Install policy</strong> {_admin_status_badge(authorization_label, f'authorization-{authorization_kind}')}</span>"
        f"<span><strong>Evidence</strong> {_status_badge(status_value)}</span>"
        "</div>"
    )
    image_url = (device.get("image") or {}).get("url")
    image = (
        f"<img class='model-page-image' src='{html.escape(str(image_url), quote=True)}' alt='' loading='eager'>"
        if image_url else ""
    )
    back_href = "/admin/installations" if origin == "installations" else "/admin/devices"
    back_label = "Back to Installations" if origin == "installations" else "Back to Devices"
    detail_url = _device_detail_url(device_id, origin=origin)
    public_link = (
        f"<a class='secondary-button model-public-link' href='https://terento.app/compatibility/' target='_blank' rel='noreferrer'>View public page {_admin_icon('external')}</a>"
        if publication.get("published") else ""
    )
    alert = (
        f"<aside class='model-review-alert' role='status'><span><strong>{open_errors} installation {'problem needs' if open_errors == 1 else 'problems need'} review.</strong> Resolved failures remain in the historical failed count.</span><a href='#installations' data-filter-open-errors>Review open problems</a></aside>"
        if open_errors else ""
    )

    rows_markup: list[str] = []
    dialogs: list[str] = []
    for index, (operation_key, results, resolved) in enumerate(history):
        first = results[0]
        result = _operation_result(results)
        issue = _operation_issue(results)
        is_open_error = not resolved and _result_is_open_problem(results)
        is_resolved_error = resolved and result == "FAILED"
        region = _operation_text(results, "region", fallback="")
        map_release = _operation_text(results, "map_release", fallback="")
        map_names = list(dict.fromkeys(
            _admin_map_display_name(item.get('region')) for item in results if item.get('region')
        ))
        map_copy = html.escape(', '.join(map_names) or "Map not recorded")
        providers_in_operation = {str(item.get('provider') or '') for item in results}
        regions_in_operation = {str(item.get('region') or '') for item in results}
        if len(providers_in_operation) == len(regions_in_operation) == 1 and providers_in_operation <= {'freizeitkarte', 'opentopomap', 'maprando'} and region:
            href = '/admin/map-statistics?' + urlencode({'provider': next(iter(providers_in_operation)), 'region': region, 'period': 'all'})
            map_copy = f"<a href='{html.escape(href, quote=True)}' title='View map statistics'>{map_copy}</a>"
        if map_release:
            map_copy += f"<small>{html.escape(region)} · {html.escape(map_release)}</small>"
        if result in {"FAILED", "NOT_STARTED"} and (resolved or is_open_error or result == "FAILED"):
            error_state = _diagnostic_state_badge(
                "RESOLVED" if resolved else _operation_state(results, resolved=False).replace("-", "_")
            )
            error_markup = error_state + f"<small>{html.escape(_diagnostic_error_reason(results, resolved=resolved))}</small>"
        else:
            error_markup = "<span class='muted-value'>No error</span>"
        release = _admin_app_version_label(
            first.get("release_label") or first.get("terento_version"),
            first.get("app_build"),
        )
        release_markup = html.escape(release) if release != "—" else "<span class='muted-value'>—</span>"
        dialog_id = "diagnostic-detail-" + hashlib.sha256(operation_key.encode("utf-8")).hexdigest()[:16]
        rows_markup.append(
            f"<tr data-diagnostic-state='{'resolved-error' if is_resolved_error else 'open' if is_open_error else 'history'}' data-review-open='{'true' if is_open_error else 'false'}' data-review-resolved='{'true' if is_resolved_error else 'false'}' data-diagnostic-result='{html.escape(result.lower(), quote=True)}' data-has-issue='{'true' if issue else 'false'}'>"
            f"<td class='column-date' data-label='Date'>{_timestamp_markup(first.get('occurred_at'))}</td>"
            f"<td class='history-map' data-label='Map'>{map_copy}</td>"
            f"<td class='column-status' data-label='Result'>{_diagnostic_result(result)}</td>"
            f"<td class='history-error' data-label='Error'>{error_markup}</td>"
            f"<td data-label='GitHub issue'>{_github_issue_link(issue)}</td>"
            f"<td data-label='App version'>{release_markup}</td>"
            f"<td class='column-status' data-label='Action'><button type='button' class='secondary-button diagnostic-review' data-dialog-id='{dialog_id}' aria-label='Inspect installation {index + 1}'>Inspect</button></td>"
            "</tr>"
        )
        dialogs.append(_diagnostic_detail_dialog(
            identity, operation_key, results, resolved=resolved,
            csrf_token=csrf_token, identity_devices=identity_devices,
            canonical_device_model_id=device_id, return_to=detail_url + "#installations",
            catalog_template=True,
        ))
    history_rows = "".join(rows_markup) or "<tr><td colspan='7' class='empty'>No installation history for this device.</td></tr>"
    history_pagination = "" if len(history) <= 25 else f"""
          <div class='provider-pagination' id='diagnostic-history-pagination' aria-live='polite'><label>Rows <select id='diagnostic-history-page-size' data-admin-dropdown aria-label='Rows per installation history page'><option value='25' selected>25</option><option value='50'>50</option></select></label><button type='button' data-history-page='previous' disabled>Previous</button><span>Showing 1–25 of {len(history)} · page 1 of {(len(history) + 24) // 25}</span><button type='button' data-history-page='next'>Next</button></div>
    """

    public_copy = (
        f"Shown as {html.escape(status.value.title() if status else 'Unavailable')}."
        if publication.get("published") else
        "Not shown."
    )
    public_form = ""
    if publication.get("eligible"):
        action = "UNPUBLISH" if publication.get("published") else "PUBLISH"
        confirm = (
            " data-confirm='This device will no longer appear on the public compatibility page.'"
            if action == "UNPUBLISH" else ""
        )
        public_form = f"""<form method='post' action='/admin/devices/public-compatibility' class='admin-async-action'{confirm}>
          <input type='hidden' name='csrf_token' value='{html.escape(csrf_token, quote=True)}'><input type='hidden' name='device_id' value='{html.escape(device_id, quote=True)}'><input type='hidden' name='publication_action' value='{action}'><input type='hidden' name='return_to' value='{html.escape(detail_url, quote=True)}'>
          <button type='submit' class='{'secondary-button' if action == 'UNPUBLISH' else ''}'>{'Remove from public compatibility' if action == 'UNPUBLISH' else 'Approve and publish'}</button>
        </form>"""

    lifecycle = (
        "Historical" if device.get("recordSource") == "HISTORICAL_REVIEWED" else
        "Inactive" if device.get("active") is False else
        "Retired from retail" if device.get("retailRetired") else "Current retail"
    )
    catalog_source = (
        "Historical reviewed registry" if device.get("recordSource") == "HISTORICAL_REVIEWED" else
        "Garmin retail catalog"
    )
    catalog = device.get("catalog") or {}
    device_info = _device_information_markup(device)
    all_events = active_events + resolved_events
    firmware = ", ".join(sorted({str(item.get("firmware_version")).strip() for item in all_events if item.get("firmware_version")}))
    raw_models = ", ".join(sorted({str(item.get("raw_mtp_model")).strip() for item in all_events if item.get("raw_mtp_model")}))
    transports = ", ".join(sorted({str(item.get("transport")).strip() for item in all_events if item.get("transport")}))
    technical_rows = _detail_rows([
        ("Catalog ID", device_id, False),
        ("Catalog variant", variant, False),
        ("Retail part number", device.get("partNumber"), False),
        ("USB identity", _usb_identity_details(device.get("usbIdentities")), False),
        ("Firmware", firmware, False),
        ("Raw MTP model", raw_models, False),
        ("XML model description", ", ".join(sorted({str(e["garmin_model_description"]) for e in all_events if e.get("garmin_model_description")})), False),
        ("XML part number", ", ".join(sorted({str(e["garmin_model_part_number"]) for e in all_events if e.get("garmin_model_part_number")})), False),
        ("Transport", transports, False),
        ("Specification source", device.get("specificationSource"), False),
        ("Catalog source", catalog_source, False),
        ("Catalog status", lifecycle, False),
        ("Last synced", _timestamp_markup(catalog.get("lastSeenAt")) if catalog.get("lastSeenAt") else None, True),
    ])
    if not technical_rows:
        technical_rows = "<p class='diagnostic-technical-empty'>Detailed technical data is not available for this record.</p>"

    last_report = stats.get("lastEvidenceAt")
    statistics_section = "" if not history and not attempts and not failed else (
        "<section class='admin-card admin-kpi-panel diagnostic-model-metrics model-statistics' aria-labelledby='model-installation-kpis-title'>"
        "<header class='admin-card-head'><h2 id='model-installation-kpis-title'>Installs</h2></header>"
        + _metric_row([
            _metric_tile("Attempts", attempts, data_stat="attempts",
                         hint="Each map result counts once, including custom .img."),
            _metric_tile("Successful", successful, data_stat="successful"),
            _metric_tile("Failed", failed, failure=True, data_stat="failed"),
            _metric_tile("Open problems", open_errors, failure=True, data_stat="openProblems",
                         hint="Installs (operations) with an unresolved failure and no linked GitHub issue"),
            _metric_tile("Last report", format_timestamp(last_report) if last_report else None, fmt="text",
                         value_html=_timestamp_markup(last_report) if last_report else None,
                         data_stat="lastReport"),
        ], label="Model installation statistics")
        + "</section>"
    )
    history_section = "<section class='diagnostics-detail-section model-page-section compact-empty-state' id='installations' aria-labelledby='installation-history-title'><h2 id='installation-history-title'>Installation history</h2><p class='empty'>No installation history for this device.</p></section>" if not history else f"""
        <section class='diagnostics-detail-section model-page-section' id='installations' aria-labelledby='installation-history-title'>
          <div class='section-heading'><div><h2 id='installation-history-title'>Installation history</h2></div></div>
          <form class='filter-bar diagnostic-filter-bar' id='diagnostic-filters'><div class='quick-filter-group' role='group' aria-label='Quick history filters'><button type='button' class='quick-filter active' data-history-filter='all' aria-pressed='true'>All</button><button type='button' class='quick-filter' data-history-filter='failed' aria-pressed='false'>Failed</button><button type='button' class='quick-filter' data-history-filter='open' aria-pressed='false'>Open problems</button><button type='button' class='quick-filter' data-history-filter='blocked' aria-pressed='false' title='Blocked before writing'>Blocked</button><button type='button' class='quick-filter' data-history-filter='succeeded' aria-pressed='false'>Successful</button></div><details class='admin-disclosure filter-disclosure history-more-filters'><summary>More filters</summary><div class='disclosure-body'><label><span class='sr-only'>Filter installation history</span><select id='diagnostic-state-filter' data-admin-dropdown><option value='all'>All</option><option value='succeeded'>Successful</option><option value='failed'>Failed</option><option value='blocked'>Blocked</option><option value='open'>Open problems</option><option value='resolved-errors'>Resolved errors</option></select></label></div></details><button type='button' class='secondary-button filter-clear' data-filter-clear aria-label='Clear diagnostic filters' hidden>Clear</button></form>
          <p class='results-count' id='diagnostic-results-count' aria-live='polite'></p>
          <div class='table-wrap diagnostic-list-wrap'><table class='diagnostic-list-table model-history-table mobile-record-table'><caption class='sr-only'>Installation history for this exact model and variant</caption><thead><tr><th scope='col' class='column-date'>Date</th><th scope='col'>Map</th><th scope='col' class='column-status'>Result</th><th scope='col'>Error</th><th scope='col'>GitHub issue</th><th scope='col'>App version</th><th scope='col' class='column-status'>Action</th></tr></thead><tbody id='diagnostic-rows'>{history_rows}</tbody></table></div>
          {history_pagination}
        </section>
    """
    administration_section = f"""
        <details class='model-page-section model-administration admin-disclosure'><summary id='administration-title'>Administration</summary><div class='administration-grid'>
          <article class='administration-card'><section class='administration-setting'><h3>Install policy</h3><dl class='administration-facts'><div><dt>Install policy</dt><dd>{html.escape(authorization_label)}</dd></div><div><dt>Public compatibility</dt><dd>{public_copy}</dd></div></dl><p class='table-help'>Install policy follows catalog Maps.</p>{public_form}</section><section class='administration-setting'><h3>Support metadata</h3><p class='table-help'>Review metadata only; it never changes write access.</p><form method='post' action='/admin/devices/authorization' class='admin-async-action' data-authorization-form data-current-support-status='{html.escape(str(device.get('supportStatus') or 'NOT_EVALUATED'), quote=True)}'><input type='hidden' name='csrf_token' value='{html.escape(csrf_token, quote=True)}'><input type='hidden' name='device_id' value='{html.escape(device_id, quote=True)}'><input type='hidden' name='return_to' value='{html.escape(detail_url, quote=True)}'><label>Support status<select name='support_status'><option value='SUPPORTED'{' selected' if device.get('supportStatus') == 'SUPPORTED' else ''}>Supported</option><option value='UNSUPPORTED'{' selected' if device.get('supportStatus') == 'UNSUPPORTED' else ''}>Unsupported</option><option value='NOT_EVALUATED'{' selected' if device.get('supportStatus') == 'NOT_EVALUATED' else ''}>Not evaluated</option></select></label><button type='submit'>Save support metadata</button></form></section></article>
        </div></details>
    """
    information_sections = f"""
        <div class='model-information-columns device-overview-sections'>
        <details class='model-page-section device-information-section admin-disclosure'><summary id='device-information-title'>Device information</summary>{device_info}</details>
        <details class='model-technical-details admin-disclosure'><summary>Technical details</summary><dl class='model-information-list'>{technical_rows}</dl></details>
        </div>
    """
    from .update_diagnostics import update_history_markup, update_summary_markup
    update_summary = update_summary_markup(device.get('update_statistics') or {}, device_id)
    updates = update_history_markup(update_history or {'device_id': device_id, 'rows': []}, base_url=detail_url, embedded=True)
    active_header = "evidence" if origin == "installations" else "devices"
    content = f"""
      {_admin_header(user, csrf_token, active=active_header)}
      <main class='dashboard model-detail-page' id='main-content'>
        <p class='back-link'><a href='{back_href}'>{_admin_icon('arrow-left')} {back_label}</a></p>
        <header class='model-page-header'>{image}<div class='model-page-heading'><h1>{html.escape(model)}{f' · <span>{html.escape(variant)}</span>' if variant != '—' else ''}</h1>{status_line}</div>{public_link}</header>
        <div class='model-evidence-grid'><div class='model-evidence-summary'>{statistics_section}{update_summary}{alert}{administration_section}{information_sections}</div><div class='model-evidence-history'>{history_section}{updates}</div></div>
        {''.join(dialogs)}{_identity_picker_template(identity_devices) if dialogs else ''}
      </main>
      <script nonce="{_ADMIN_NONCE_PLACEHOLDER}">{_diagnostics_script()}</script>
    """
    return _layout(f"{model} {variant}", content, sections={"device": device, "diagnostics": operations, "resolved": resolved_operations})


def diagnostics_page(
    rows: list[dict[str, Any]], user: dict[str, Any], csrf_token: str,
    *, identity: str,
    operations: list[dict[str, Any]] | None = None,
    resolved_operations: list[dict[str, Any]] | None = None,
    identity_devices: list[dict[str, Any]] | None = None,
    canonical_device_model_id: str | None = None,
    unresolved_only: bool = False,
    open_problem_count: int | None = None,
) -> bytes:
    identity = identity.strip()
    canonical_device_model_id = str(canonical_device_model_id or "").strip() or None

    def matches(value: dict[str, Any]) -> bool:
        if unresolved_only:
            return (
                not str(value.get("canonical_device_model_id") or "").strip()
                and str(value.get("compatibility_identity") or value.get("model") or "").strip() == identity
            )
        if canonical_device_model_id:
            return str(value.get("canonical_device_model_id") or "").strip() == canonical_device_model_id
        return str(value.get("compatibility_identity") or value.get("model") or "").strip() == identity

    model_row = next(
        (row for row in rows if matches(row)),
        None,
    )
    active_events = [
        event for event in (operations or [])
        if matches(event)
        and not _is_preinstall_download_operation([event])
    ]
    resolved_events = [
        event for event in (resolved_operations or [])
        if matches(event)
        and not _is_preinstall_download_operation([event])
    ]
    active_groups = _group_operations(active_events)
    resolved_groups = _group_operations(resolved_events)
    active_diagnostics = {
        key: results for key, results in active_groups.items()
        if _operation_is_problematic(results) or _operation_issue(results)
    }
    diagnostic_groups = [(key, results, False) for key, results in active_groups.items()]
    diagnostic_groups.extend((key, results, True) for key, results in resolved_groups.items())
    diagnostic_groups.sort(key=lambda item: _timestamp_iso(item[1][0].get("occurred_at")), reverse=True)
    model, variant = _display_identity(identity, model_row)
    result_summary = _diagnostic_summary_by_identity(active_events, resolved_events)
    attempts = sum(item["attempts"] for item in result_summary.values())
    successes = sum(item["successful"] for item in result_summary.values())
    failures = sum(item["failed"] for item in result_summary.values())
    if model_row:
        attempts = int(model_row.get("attempted_install_count") or 0)
        successes = int(model_row.get("successful_install_count") or 0)
        failures = int(model_row.get("failed_install_count") or 0)
    errors = (
        int(open_problem_count) if open_problem_count is not None
        else _open_problem_operation_count(active_events)
    )
    status = _row_compatibility_status(model_row) if model_row else None
    # Quick filters like the device Installation history (no <select>, owner
    # decision 2026-10-06); every former select value stays one click away.
    quick_filters = "".join(
        f"<button type='button' class='quick-filter{' active' if value == 'all' else ''}' data-history-filter='{value}' "
        f"aria-pressed='{'true' if value == 'all' else 'false'}'>{label}</button>"
        for value, label in (
            ("all", "All"), ("failed", "Failed"), ("open", "Open problems"),
            ("identity-pending", "Identity review"), ("resolved", "Resolved"),
            ("with-issue", "With issue"), ("succeeded", "Successful"),
        )
    )
    filters = (
        f"<div class='quick-filter-group' role='group' aria-label='Quick history filters'>{quick_filters}</div>"
        "<button type='button' class='secondary-button filter-clear' data-filter-clear aria-label='Clear diagnostic filters' hidden>Clear</button>"
    )
    rows_markup: list[str] = []
    dialogs: list[str] = []
    for index, (operation_key, results, resolved) in enumerate(diagnostic_groups):
        first = results[0]
        state = _operation_state(results, resolved=resolved)
        result = _operation_result(results)
        issue = _operation_issue(results)
        identity_pending = _identity_is_pending(results)
        review_badge = _diagnostic_state_badge(
            "RESOLVED" if resolved else state.replace("-", "_")
            if state in {"open", "in-progress", "under-review"}
            else "IDENTITY_PENDING" if identity_pending else "NONE"
        )
        if state in {"open", "in-progress", "under-review"} and identity_pending:
            review_badge += " " + _diagnostic_state_badge("IDENTITY_PENDING")
        dialog_id = "diagnostic-detail-" + hashlib.sha256(operation_key.encode("utf-8")).hexdigest()[:16]
        rows_markup.append(
            f"<tr data-diagnostic-state='{state}' data-review-open='{'true' if state in {'open', 'in-progress', 'under-review', 'identity-pending'} else 'false'}' data-review-resolved='{'true' if resolved else 'false'}' data-identity-pending='{'true' if identity_pending else 'false'}' data-diagnostic-result='{html.escape(result.lower(), quote=True)}' data-has-issue='{'true' if issue else 'false'}'>"
            f"<td class='column-date' data-label='Date'>{_timestamp_markup(first.get('occurred_at'))}</td>"
            f"<td class='history-map' data-label='Map'>{html.escape(_operation_text(results, 'region'))}</td>"
            f"<td class='column-status' data-label='Result'>{_diagnostic_result(result)}</td>"
            f"<td data-label='GitHub issue'>{_github_issue_link(issue)}</td>"
            f"<td class='column-status' data-label='Review'>{review_badge}</td>"
            f"<td class='column-status' data-label='Action'><button type='button' class='secondary-button diagnostic-review' data-dialog-id='{dialog_id}' aria-label='Inspect installation {index + 1}'>Inspect</button></td>"
            "</tr>"
        )
        dialogs.append(_diagnostic_detail_dialog(
            identity, operation_key, results, resolved=resolved,
            csrf_token=csrf_token, identity_devices=identity_devices,
            canonical_device_model_id=canonical_device_model_id,
            catalog_template=True,
        ))
    rows_body = "".join(rows_markup) or "<tr><td colspan='6' class='empty'>No installation history for this model.</td></tr>"
    content = f"""
      {_admin_header(user, csrf_token, active='installations')}
      <main class='dashboard diagnostics-page' id='main-content'>
        <p class='back-link'><a href='/admin/installations'>{_admin_icon('arrow-left')} Installations</a></p>
        <div class='heading-row'><div><h1>{html.escape(model)}{f' · {html.escape(variant)}' if variant != '—' else ''}</h1></div><a class='section-link identity-review-all-link' href='{IDENTITY_REVIEW_PATH}'>Review all pending identities&nbsp;{_admin_icon('arrow-right')}</a></div>
        <section class='admin-card admin-kpi-panel diagnostic-model-metrics model-statistics' aria-labelledby='diagnostic-installation-kpis-title'>
          <header class='admin-card-head'><h2 id='diagnostic-installation-kpis-title'>Installs</h2></header>
          {_metric_row([
            # Same Installs card as the device page: no scope chips under the
            # numbers and Evidence as a normal status pill (owner decision 2026-10-06).
            _metric_tile("Attempts", attempts, data_stat="attempts"),
            _metric_tile("Successful", successes, data_stat="successful"),
            _metric_tile("Failed", failures, failure=True, data_stat="failed"),
            _metric_tile("Open problems", errors, failure=True, data_stat="openProblems",
                         hint="Installs (operations) with an unresolved failure and no linked GitHub issue"),
            _metric_tile("Evidence", status.value.title() if status else "Unavailable", fmt="text",
                         value_html=_status_badge(status.value if status else ''), data_stat="evidence"),
        ], label="Model installation statistics")}
        </section>
        <section class='diagnostics-detail-section model-page-section' id='installations' aria-labelledby='diagnostic-list-title'>
          <div class='section-heading'><div><h2 id='diagnostic-list-title'>Installation history</h2></div></div>
          <form class='filter-bar diagnostic-filter-bar' id='diagnostic-filters'{' hidden' if len(diagnostic_groups) <= 1 else ''}>{filters}</form>
          <p class='results-count' id='diagnostic-results-count' aria-live='polite'></p>
          <div class='table-wrap diagnostic-list-wrap'><table class='diagnostic-list-table mobile-record-table'><caption class='sr-only'>Installation and diagnostic records for exact model and variant</caption><thead><tr><th scope='col' class='column-date'>Date</th><th scope='col'>Map</th><th scope='col' class='column-status'>Result</th><th scope='col'>GitHub issue</th><th scope='col' class='column-status'>Review</th><th scope='col' class='column-status'>Action</th></tr></thead><tbody id='diagnostic-rows'>{rows_body}</tbody></table></div>
        </section>
        {''.join(dialogs)}{_identity_picker_template(identity_devices) if dialogs else ''}
      </main>
      <script nonce="{_ADMIN_NONCE_PLACEHOLDER}">{_diagnostics_script()}</script>
    """
    return _layout("Installation details", content, sections={"model": model_row, "diagnostics": active_events, "resolved": resolved_operations})


def github_issue_queue_page(
    operations: list[dict[str, Any]] | None,
    identity_devices: list[dict[str, Any]] | None,
    user: dict[str, Any],
    csrf_token: str,
    *, update_diagnostics: list[dict[str, Any]] | None = None,
) -> bytes:
    """Render the active linked-issue queue separately from closed diagnostics."""
    def has_valid_issue(event: dict[str, Any]) -> bool:
        try:
            return bool(_normalise_github_issue_reference(event.get("linked_github_issue")))
        except ValueError:
            return False

    groups = _group_operation_tasks([event for event in (operations or []) if has_valid_issue(event)])
    queue: list[tuple[str, list[dict[str, Any]]]] = []
    for operation_key, results in groups.items():
        if _operation_issue(results):
            queue.append((operation_key, results))
    queue.sort(
        key=lambda item: max(_timestamp_iso(result.get("occurred_at")) for result in item[1]),
        reverse=True,
    )
    rows_markup: list[str] = []
    dialogs: list[str] = []
    for index, (operation_key, results) in enumerate(queue):
        first = results[0]
        identity = str(first.get("compatibility_identity") or first.get("model") or "Unknown device")
        model, variant = _display_identity(identity, first)
        issue = _operation_issue(results)
        state = _operation_state(results, resolved=False)
        result = _operation_result(results)
        dialog_id = "diagnostic-detail-" + hashlib.sha256(operation_key.encode("utf-8")).hexdigest()[:16]
        rows_markup.append(
            f"<tr><td>{_github_issue_link(issue)}</td>"
            f"<td><strong>{html.escape(model)}</strong><small class='table-secondary'>{html.escape(variant) if variant != '—' else ''}</small></td>"
            f"<td>{html.escape(_operation_text(results, 'region'))}</td>"
            f"<td class='column-status'>{_diagnostic_result(result)}</td>"
            f"<td class='column-status'>{_diagnostic_state_badge(state)}</td>"
            f"<td class='column-date'>{_timestamp_markup(max((result.get('occurred_at') for result in results), key=_timestamp_iso))}</td>"
            f"<td class='column-status'><button type='button' class='secondary-button diagnostic-review' data-dialog-id='{dialog_id}' aria-label='Inspect GitHub issue {index + 1}'>Inspect</button></td></tr>"
        )
        dialogs.append(_diagnostic_detail_dialog(
            identity,
            operation_key,
            results,
            resolved=False,
            csrf_token=csrf_token,
            identity_devices=identity_devices,
            canonical_device_model_id=first.get("canonical_device_model_id"),
            return_to="/admin/review/github-issues",
            catalog_template=True,
        ))
    from .update_diagnostics import _update_identity
    update_queue = [row for row in (update_diagnostics or []) if has_valid_issue(row) and row.get('diagnostic_status') != 'RESOLVED']
    for row in update_queue:
        model_markup, variant, _ = _update_identity(row)
        href = '/admin/update-diagnostics?' + urlencode({'diagnosticId': str(row['event_id'])})
        rows_markup.append(f"<tr><td>{_github_issue_link(row.get('linked_github_issue'))}</td><td>{model_markup}<small class='table-secondary'>{html.escape(variant)}</small></td><td>Map update · {html.escape(str(row.get('region') or 'Unknown'))}</td><td>{_diagnostic_result(row.get('outcome'))}</td><td>{_diagnostic_state_badge(row.get('diagnostic_workflow_status') or 'OPEN')}</td><td>{_timestamp_markup(row.get('occurred_at'))}</td><td><a class='secondary-button' href='{html.escape(href, quote=True)}'>Inspect update</a></td></tr>")
    rows = "".join(rows_markup) or (
        "<tr><td colspan='7' class='empty'>No active GitHub review tasks are waiting for resolution.</td></tr>"
    )
    content = f"""
      {_admin_header(user, csrf_token, active='overview')}
      <main class='dashboard diagnostics-page' id='main-content'>
        <p class='back-link'><a href='/admin'>{_admin_icon('arrow-left')} Dashboard</a></p>
        <div class='heading-row'><div><h1>GitHub issues</h1></div></div>
        <section class='diagnostics-detail-section admin-card' aria-labelledby='github-issue-queue-title'>
          <div class='section-heading'><div><h2 id='github-issue-queue-title'>Tasks</h2>{_scope_chip('now')}<span class='table-help'>{_count_label(len(queue) + len(update_queue), 'task')}</span></div></div>
          <div class='table-wrap diagnostic-list-wrap'><table class='admin-table diagnostic-list-table'><caption class='sr-only'>GitHub issues linked to active diagnostics</caption><thead><tr><th scope='col'>Issue</th><th scope='col'>Device</th><th scope='col'>Map / region</th><th scope='col' class='column-status'>Result</th><th scope='col' class='column-status'>State</th><th scope='col' class='column-date'>Last activity</th><th scope='col' class='column-status'>Action</th></tr></thead><tbody>{rows}</tbody></table></div>
        </section>
        {''.join(dialogs)}{_identity_picker_template(identity_devices) if dialogs else ''}
      </main>
      <script nonce="{_ADMIN_NONCE_PLACEHOLDER}">{_diagnostics_script()}</script>
    """
    return _layout("GitHub issues", content, sections={"queue": operations, "updates": update_diagnostics})


IDENTITY_REVIEW_PATH = "/admin/review/identity"
_IDENTITY_CHECK_LABELS = {
    "model": "model", "size": "size", "screen": "display",
    "xmlPartNumber": "product code", "usb": "USB code",
}


def _reported_identity(value: dict[str, Any]) -> str:
    """The reported identity text that groups unresolved evidence (Installations row key)."""
    return str(value.get("compatibility_identity") or value.get("model") or "Unknown").strip() or "Unknown"


def _identity_review_anchor(identity: str) -> str:
    return "identity-" + hashlib.sha256(identity.strip().encode("utf-8")).hexdigest()[:12]


def _identity_review_url(identity: str | None = None) -> str:
    return IDENTITY_REVIEW_PATH + (f"#{_identity_review_anchor(identity)}" if identity else "")


def _identity_pending_reason(results: list[dict[str, Any]]) -> str:
    """Short, received-facts-only reason why no exact catalog model is assigned."""
    assessments = [assessment for assessment in _identity_assessments(results) if assessment]
    if not assessments:
        return "Not assessed"
    recommendation = _identity_recommendation(results)
    if recommendation:
        missing = list(dict.fromkeys(
            _IDENTITY_CHECK_LABELS[str(check.get("name"))]
            for check in recommendation.get("checks", [])
            if check.get("state") == "MISSING" and str(check.get("name")) in _IDENTITY_CHECK_LABELS
        ))
        return f"One match · {', '.join(missing)} not confirmed" if missing else "One match · needs confirmation"
    possible = {
        str(candidate.get("deviceId"))
        for assessment in assessments
        for candidate in _identity_presentation_candidates(assessment)
        if candidate.get("deviceId")
    }
    if len(possible) > 1:
        return f"{len(possible)} possible models"
    if any(assessment.get("candidates") for assessment in assessments):
        return "Reported details conflict with the catalog"
    return "No catalog match"


def _identity_review_groups(
    operations: list[dict[str, Any]],
) -> list[tuple[str, list[tuple[str, list[tuple[str, list[dict[str, Any]]]]]]]]:
    """Group pending work by reported identity, then by install operation.

    The unit is the Needs attention one: an install operation (operation ID,
    or the event for legacy rows) with at least one identity-pending result.
    Each pending result keeps its own exact key for the identity form.
    """
    by_identity: dict[str, list[dict[str, Any]]] = {}
    for event in operations:
        by_identity.setdefault(_reported_identity(event), []).append(event)

    def latest(rows: list[dict[str, Any]]) -> str:
        return max(_timestamp_iso(row.get("occurred_at")) for row in rows)

    groups = []
    for identity, events in by_identity.items():
        tasks = []
        for task_key, task_events in _group_operation_tasks(events).items():
            pending = [
                (result_key, rows) for result_key, rows in _group_operations(task_events).items()
                if _identity_is_pending(rows)
            ]
            if pending:
                tasks.append((task_key, pending))
        tasks.sort(key=lambda task: latest([row for _, rows in task[1] for row in rows]), reverse=True)
        if tasks:
            groups.append((identity, tasks))
    groups.sort(key=lambda group: latest([row for _, rows in group[1][0][1] for row in rows]), reverse=True)
    return groups


def _identity_review_item(
    identity: str, task_key: str, pending: list[tuple[str, list[dict[str, Any]]]], number: int, *,
    csrf_token: str, identity_devices: list[dict[str, Any]] | None,
) -> str:
    rows = [row for _, result_rows in pending for row in result_rows]
    first_key, first_rows = pending[0]
    detail_href = (
        _diagnostics_url({"compatibility_identity": identity})
        + "#diagnostic-detail-" + hashlib.sha256(first_key.encode("utf-8")).hexdigest()[:16]
    )
    forms = "".join(
        _identity_review_form(
            result_key, result_rows, csrf_token=csrf_token, identity_devices=identity_devices,
            return_to=IDENTITY_REVIEW_PATH,
            id_suffix="identity-review-" + hashlib.sha256(result_key.encode("utf-8")).hexdigest()[:16],
            catalog_template=True, inline=True,
            result_label=_operation_map_label(result_rows) if len(pending) > 1 else "",
        )
        for result_key, result_rows in pending
    )
    reason = _identity_pending_reason(first_rows) if len(pending) == 1 else "; ".join(dict.fromkeys(
        _identity_pending_reason(result_rows) for _, result_rows in pending
    ))
    return (
        f"<li class='identity-review-item' data-identity-review-item data-operation='{html.escape(task_key, quote=True)}'>"
        "<div class='identity-review-facts'>"
        f"<span class='identity-review-date'>{_timestamp_markup(max((row.get('occurred_at') for row in rows), key=_timestamp_iso))}</span>"
        f"<span class='identity-review-map'>{html.escape(_operation_map_label(rows))}</span>"
        f"<span class='identity-review-result'>{_diagnostic_result(_operation_result(rows))}</span>"
        "<span class='identity-review-why'>"
        f"<span class='identity-review-reason'>{html.escape(reason)}</span>"
        f"<a class='section-link identity-review-details' href='{html.escape(detail_href, quote=True)}' "
        f"aria-label='Details for installation {number}'>Details</a>"
        "</span></div>"
        f"<div class='identity-review-decision'>{forms}</div>"
        "</li>"
    )


def identity_review_page(
    operations: list[dict[str, Any]] | None,
    user: dict[str, Any],
    csrf_token: str,
    *, identity_devices: list[dict[str, Any]] | None = None,
) -> bytes:
    """Every installation operation whose identity is pending, confirmable in place."""
    total = 0
    if operations is None:
        body = _unavailable_card("Identity review", "identity-review-list", retry_href=IDENTITY_REVIEW_PATH)
        summary = ""
    else:
        groups = _identity_review_groups(operations)
        total = sum(len(tasks) for _, tasks in groups)
        done = _empty_state("empty", "No installations wait for identity review.")
        cards: list[str] = []
        number = 0
        for identity, tasks in groups:
            model, variant = _display_identity(identity)
            anchor = _identity_review_anchor(identity)
            items = []
            for task_key, pending in tasks:
                number += 1
                items.append(_identity_review_item(
                    identity, task_key, pending, number,
                    csrf_token=csrf_token, identity_devices=identity_devices,
                ))
            variant_text = variant if variant not in {"—", "Historical"} else "Variant not reported"
            cards.append(
                f"<section class='admin-card identity-review-group' id='{anchor}' aria-labelledby='{anchor}-title' data-identity-review-group>"
                "<header class='admin-card-head'>"
                f"<h2 id='{anchor}-title'>{html.escape(model)}<small>{html.escape(variant_text)}</small></h2>"
                f"<span class='table-help' data-identity-review-group-count>{_count_label(len(tasks), 'installation')}</span>"
                f"<a class='admin-card-action section-link' href='{html.escape(_diagnostics_url({'compatibility_identity': identity}), quote=True)}'>"
                f"All installations&nbsp;{_admin_icon('arrow-right')}</a>"
                "</header>"
                f"<ol class='identity-review-items'>{''.join(items)}</ol>"
                "</section>"
            )
        if cards:
            body = (
                "<div class='identity-review-groups'>" + "".join(cards) + "</div>"
                + f"<div class='admin-card identity-review-done' data-identity-review-done hidden>{done}</div>"
                + "<template id='identity-review-confirmed'><p class='identity-review-confirmed' tabindex='-1'>"
                + _status_pill("success", "Confirmed")
                + " <a class='section-link' data-identity-confirmed-link href='/admin/devices'>Open model</a></p></template>"
                + _identity_picker_template(identity_devices)
            )
        else:
            body = f"<div class='admin-card identity-review-done'>{done}</div>"
        summary = (
            f"<p class='page-meta identity-review-summary'>{_scope_chip('now')}"
            f"<span data-identity-review-count>{_count_label(total, 'installation')}</span></p>"
        )
    content = f"""
      {_admin_header(user, csrf_token, active='overview')}
      <main class='dashboard identity-review-page' id='main-content'>
        <p class='back-link'><a href='/admin'>{_admin_icon('arrow-left')} Dashboard</a></p>
        <div class='heading-row'><div><h1>Identity review</h1></div>{summary}</div>
        {body}
      </main>
      <script nonce="{_ADMIN_NONCE_PLACEHOLDER}">{_diagnostics_script()}</script>
    """
    return _layout("Identity review", content, sections={"identityReview": operations})


def _admin_map_capability(value: Any) -> tuple[str, str]:
    if value is True:
        return "Yes", "yes"
    if value is False:
        return "No", "no"
    return "Unknown", "unknown"


def _admin_installation_authorization(map_capable: Any, active: Any = True) -> tuple[str, str, str]:
    _, authorization = installation_authorization_for_row({
        "active": active is True,
        "map_capable": map_capable,
    })
    return _admin_installation_authorization_code(authorization)


def _admin_installation_authorization_code(value: Any) -> tuple[str, str, str]:
    status = str(value or "PENDING").upper()
    labels = {
        "APPROVED": ("Approved", "approved", "APPROVED"),
        "BLOCKED": ("Blocked", "blocked", "BLOCKED"),
        "PENDING": ("Pending", "pending", "PENDING"),
    }
    return labels.get(status, ("Pending", "pending", "PENDING"))


def _admin_device_payload(
    rows: list[dict[str, Any]], sync: dict[str, Any] | None,
) -> dict[str, Any]:
    def sync_count(key: str) -> int | None:
        value = (sync or {}).get(key)
        return int(value) if value is not None else None

    devices: list[dict[str, Any]] = []
    for row in rows:
        attempts = int(row.get("attempted_install_count") or 0)
        successful = int(row.get("successful_install_count") or 0)
        failed = int(row.get("failed_install_count") or 0)
        asset_url = row.get("asset_url")
        if not (
            row.get("asset_status") == "AVAILABLE"
            and isinstance(asset_url, str)
            and asset_url.startswith("https://api.terento.app/assets/devices/")
        ):
            asset_url = None
        source_image_url = _official_source_image_url(row.get("source_image_url"))
        stored_map_capable = row.get("map_capable")
        classified_map_capable = classify_map_capable(
            row.get("canonical_model") or row.get("model"),
            row.get("manufacturer") or "Garmin",
        )
        map_capable = classified_map_capable
        if map_capable is None and successful > 0:
            # A verified successful installation is model/variant-specific
            # evidence that the catalog classifier has not learned yet.
            map_capable = True
        # Evidence follows the stored catalog Maps fact and observed verified
        # successes only; the model-name classifier never sets it (ADM-12).
        evidence_successes = int(row.get("compatibility_successful_install_count", successful) or 0)
        evidence_status = calculate_compatibility_status(
            successful_install_count=evidence_successes,
            recognized_map_capable_evidence=stored_map_capable is True or evidence_successes > 0,
        )
        authorization_label, _, authorization_code = _admin_installation_authorization(
            row.get("map_capable"),
            row.get("active"),
        )
        public_identity = str(row.get("public_compatibility_identity") or "").strip()
        public_review_status = str(row.get("public_review_status") or "PENDING").upper()
        public_enabled = bool(row.get("public_statistics_enabled", False))
        public_eligible = bool(public_identity and evidence_status)
        public_published = bool(
            public_eligible
            and public_review_status == "APPROVED"
            and public_enabled
        )
        if asset_url and not (source_image_url and row.get("asset_scope") == "GENERIC"):
            image = {"url": asset_url, "origin": "controlled", "status": "AVAILABLE"}
        elif source_image_url:
            image = {"url": source_image_url, "origin": "garmin-source", "status": "SOURCE"}
        else:
            image = generic_fallback_image()
        usb_identities = row.get("usb_identities") or []
        devices.append({
            "id": row.get("device_id"),
            "manufacturer": row.get("manufacturer") or "Garmin",
            "family": row.get("family_canonical_name"),
            "familyName": row.get("family_name"),
            "model": row.get("model"),
            "canonicalModel": row.get("canonical_model"),
            "variant": _known_variant_description(row),
            "caseSizeMm": row.get("case_size_mm"),
            "displayType": row.get("display_type"),
            "identityMappings": row.get("identity_mappings") or [],
            "screenTechnology": row.get("screen_technology"),
            "solar": row.get("solar"), "inReach": row.get("inreach"),
            "specificationSource": row.get("specification_source"),
            "specificationEvidence": row.get("specification_evidence") or {},
            "partNumber": row.get("part_number"),
            "productURL": row.get("product_url"),
            "active": bool(row.get("active", True)),
            "mapCapable": stored_map_capable,
            "observedMapCapability": map_capable,
            "supportStatus": str(row.get("support_status") or "NOT_EVALUATED").upper(),
            "installationAuthorization": authorization_code,
            "installationAuthorizationLabel": authorization_label,
            "evidenceStatus": evidence_status.value if evidence_status else None,
            "publicCompatibility": {
                "eligible": public_eligible,
                "published": public_published,
                "reviewStatus": public_review_status,
                "statisticsEnabled": public_enabled,
                "compatibilityIdentity": public_identity or None,
                "displayName": row.get("public_display_name"),
            },
            "recordSource": str(row.get("record_source") or "CURRENT_RETAIL").upper(),
            "collectorManaged": bool(row.get("collector_managed", True)),
            # Missing from Garmin's current category for the retirement threshold;
            # the row stays active, so authorization keeps the catalog Maps value.
            "retailRetired": bool(row.get("collector_managed", True)) and int(
                row.get("consecutive_missed_collections") or 0) >= RETAIL_RETIREMENT_MISSED_RUNS,
            "asset": {"status": "AVAILABLE", "url": asset_url} if asset_url else {"status": "MISSING"},
            "sourceAsset": {"url": source_image_url, "scope": "MODEL"} if source_image_url else None,
            "image": image,
            "usbIdentities": usb_identities,
            "installationStats": {
                "attempts": attempts,
                "successful": successful,
                "failed": failed,
                "successRate": round(successful * 100 / attempts, 1) if attempts else None,
                "firstSuccessfulAt": _timestamp_iso(row.get("first_success")) or None,
                "lastSuccessfulAt": _timestamp_iso(row.get("last_success")) or None,
                "lastEvidenceAt": _timestamp_iso(row.get("last_evidence")) or None,
            },
            "catalog": {
                "firstSeenAt": _timestamp_iso(row.get("first_seen_at")) or None,
                "createdAt": _timestamp_iso(row.get("created_at")) or None,
                "updatedAt": _timestamp_iso(row.get("updated_at")) or None,
                "lastSeenAt": _timestamp_iso(row.get("last_seen_at")) or None,
                "newInLatestSync": bool(
                    sync and row.get("first_seen_collection_run_id") == sync.get("id")
                ),
                "firstSeenSyncId": row.get("first_seen_collection_run_id"),
                "lastSeenSyncId": row.get("last_seen_collection_run_id"),
            },
        })

    attempts = sum(device["installationStats"]["attempts"] for device in devices)
    successful = sum(device["installationStats"]["successful"] for device in devices)
    eligible_map_models = sum(
        device["active"] is True and device["mapCapable"] is True
        for device in devices
    )
    map_models_with_success = sum(
        device["active"] is True
        and device["mapCapable"] is True
        and device["installationStats"]["successful"] > 0
        for device in devices
    )
    return {
        "schemaVersion": 1,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "models": len(devices),
            "mapCapable": sum(device["mapCapable"] is True for device in devices),
            "approved": sum(device["installationAuthorization"] == "APPROVED" for device in devices),
            "successful": successful,
            "installAttempts": attempts,
            "successfulInstalls": successful,
            "successRate": round(successful * 100 / attempts, 1) if attempts else None,
            "eligibleMapModels": eligible_map_models,
            "mapModelsWithSuccess": map_models_with_success,
            "mapModelCoverageRate": (
                round(map_models_with_success * 100 / eligible_map_models, 1)
                if eligible_map_models else None
            ),
            "newThisSync": sync_count("records_added"),
        },
        "sync": {
            "id": sync.get("id") if sync else None,
            "status": sync.get("status") if sync else None,
            "startedAt": _timestamp_iso(sync.get("started_at")) or None if sync else None,
            "completedAt": _timestamp_iso(
                sync.get("finished_at") or sync.get("completed_at")
            ) or None if sync else None,
            "recordsTotalBefore": sync_count("records_total_before"),
            "recordsTotalAfter": sync_count("records_total_after"),
            "recordsAdded": sync_count("records_added"),
            "recordsUpdated": sync_count("records_updated"),
        },
        "devices": devices,
    }


def _admin_status_badge(label: str, kind: str) -> str:
    pill_kind = {
        "map-yes": "success", "map-no": "danger", "map-unknown": "unknown",
        "authorization-approved": "success", "authorization-blocked": "danger",
        "authorization-pending": "warning",
        "publication-published": "success", "publication-pending": "warning",
        "publication-unavailable": "neutral",
    }.get(kind, "neutral")
    return _status_pill(pill_kind, label, value=kind)


def _admin_device_row(device: dict[str, Any], index: int) -> str:
    model, variant, _ = _identity_parts(device)
    provenance = _historical_catalog_indicator() if _is_historical_catalog(device) else ""
    variant = "—" if variant == "Historical" else variant or "—"
    family = str(device.get("familyName") or device.get("family") or "")
    map_label, map_kind = _admin_map_capability(device.get("mapCapable"))
    authorization_label, authorization_kind, _ = _admin_installation_authorization_code(
        device.get("installationAuthorization")
    )
    evidence_status = str(device.get("evidenceStatus") or "").upper()
    stats = device["installationStats"]
    catalog = device["catalog"]
    search = " ".join(str(value or "") for value in (
        model, device.get("canonicalModel"), family, variant,
        device.get("caseSizeMm"), device.get("partNumber"), device.get("displayType"),
    )).strip()
    image_url = (device.get("image") or {}).get("url") or device.get("asset", {}).get("url")
    image = (
        f"<img class='device-thumb' src='{html.escape(image_url, quote=True)}' alt='' loading='lazy'>"
        if image_url else
        "<span class='device-thumb device-thumb-placeholder' aria-hidden='true'></span>"
    )
    new_badge = "<span class='new-badge'>New</span>" if catalog.get("newInLatestSync") else ""
    last_success = _timestamp_markup(stats.get("lastSuccessfulAt")) if stats.get("lastSuccessfulAt") else "—"
    detail_url = _device_detail_url(device.get("id"), origin="devices")
    return f"""<tr data-device-index='{index}' data-device-url='{html.escape(detail_url, quote=True)}' data-search='{html.escape(search, quote=True)}' data-model='{html.escape(model.lower(), quote=True)}' data-updated='{html.escape(str(catalog.get('updatedAt') or ''), quote=True)}' data-installs='{stats['attempts']}' data-evidence='{html.escape(str(stats.get('lastSuccessfulAt') or ''), quote=True)}' data-status='{html.escape(evidence_status.lower())}'>
      <td><a class='device-model-button' href='{html.escape(detail_url, quote=True)}'>{image}<span class='device-model-copy'><strong>{html.escape(model)}</strong>{provenance}{new_badge}</span></a></td>
      <td>{html.escape(variant)}</td>
      <td class='column-status' title='Observed map capability: {html.escape(_admin_map_capability(device.get("observedMapCapability"))[0], quote=True)}'>{_admin_status_badge(map_label, f'map-{map_kind}')}</td>
      <td class='column-status'>{_admin_status_badge(authorization_label, f'authorization-{authorization_kind}')}</td>
      <td class='column-status'>{_status_badge(evidence_status)}</td>
      <td class='column-number numeric'>{stats['attempts']}</td>
      <td class='column-number numeric'>{stats['successful']}</td>
      <td class='column-date'>{last_success}</td>
    </tr>"""


def devices_page(
    rows: list[dict[str, Any]], sync: dict[str, Any] | None,
    user: dict[str, Any], csrf_token: str,
) -> bytes:
    payload = _admin_device_payload(rows, sync)
    summary = payload["summary"]
    sync_data = payload["sync"]
    completed = _timestamp_markup(sync_data["completedAt"]) if sync_data["completedAt"] else "No successful sync recorded"
    sync_line = (
        f"<button type='button' class='summary-filter-link' id='device-show-new'>{sync_data['recordsAdded']} new</button> · {sync_data['recordsUpdated']} updated"
        if sync_data["id"] is not None and sync_data["recordsAdded"] is not None
        else ("Counts unavailable for this historical run" if sync_data["id"] is not None else "No sync recorded")
    )
    family_values = sorted({
        str(device.get("familyName") or device.get("family") or "").strip()
        for device in payload["devices"]
        if str(device.get("familyName") or device.get("family") or "").strip()
    }, key=str.casefold)
    family_options = "".join(
        f"<option value='{html.escape(value, quote=True)}'>{html.escape(value)}</option>"
        for value in family_values
    )
    rows_html = "".join(
        _admin_device_row(device, index)
        for index, device in enumerate(payload["devices"])
    )
    payload_json = _admin_json({**payload, "csrfToken": csrf_token})
    mobile_sort_options = "".join(
        f"<option value='{key}:{direction}'>{label} · {suffix}</option>"
        for key, label in [("model", "Model"), ("variant", "Variant"), ("maps", "Maps"),
                           ("authorization", "Install policy"), ("status", "Evidence"),
                           ("attempts", "Attempts"), ("success", "Successful"), ("evidence", "Last success")]
        for direction, suffix in [("ascending", "ascending"), ("descending", "descending")]
    )
    table_header = _device_table_header()
    table_columns = _device_table_columns()
    devices = payload["devices"]
    verified_models = sum(device.get("evidenceStatus") == "VERIFIED" for device in devices)
    pending_policy = sum(device.get("installationAuthorization") == "PENDING" and device.get("active") is not False for device in devices)
    # The rate is its own span so it can wrap under the count in a narrow tile.
    covered_value = (f"{summary['mapModelsWithSuccess']:,}/{summary['eligibleMapModels']:,}"
                     f" <span class='admin-metric-rate'>({html.escape(_format_rate(summary['mapModelCoverageRate']))})</span>")
    map_filters = "".join(
        f"<button type='button' class='quick-filter{' active' if value == 'yes' else ''}' data-device-map-filter='{value}' "
        f"aria-pressed='{'true' if value == 'yes' else 'false'}'>{label}</button>"
        for value, label in (("all", "All"), ("yes", "Maps: Yes"), ("no", "Maps: No"), ("unknown", "Maps: Unknown"))
    )
    sync_status = f" · {html.escape(str(sync_data['status'] or '').title())}" if sync_data['status'] else ""
    sync_meta = "" if not devices else (
        f"<p class='page-meta device-summary-sync'><strong>Last sync</strong> {completed} · {sync_line}{sync_status}</p>"
    )
    device_list = "<section class='compact-empty-state' aria-labelledby='device-list-title'><h2 id='device-list-title'>No devices</h2><p>No Garmin device records are available. Run or check the latest catalog sync.</p></section>" if not rows_html else f"""
        <section class="admin-card installation-kpis device-summary-strip" aria-label="Device catalog summary">
          {_metric_row([
              # Same tiles as Installations: no scope chips (owner decision 2026-10-06).
              _metric_tile("Models", summary['models']),
              _metric_tile("Maps: Yes", summary['mapCapable']),
              _metric_tile("Verified", verified_models),
              _metric_tile("Covered", summary['mapModelsWithSuccess'], value_html=covered_value, data_stat="covered",
                           hint="Active Maps: Yes models with at least one verified installation"),
              # A positive count uses the failure tone (owner decision 2026-10-06).
              _metric_tile("Pending policy", pending_policy, failure=True),
          ], label="Device catalog summary")}
        </section>
        <section class="evidence-section" aria-label="Device catalog">
          <form class="filter-bar admin-filter-bar device-filter-bar" id="device-filters" role="search">
            <div class="quick-filter-group" role="group" aria-label="Filter by map capability">{map_filters}</div>
            <label hidden><span class="sr-only">Filter by map capability</span><select id="device-map"><option value="yes" selected>Maps: Yes</option><option value="no">Maps: No</option><option value="unknown">Maps: Unknown</option><option value="all">All maps</option></select></label>
            <label class="filter-search"><span class="sr-only">Search devices</span><input id="device-search" type="search" placeholder="Search devices" autocomplete="off"></label>
            <details class="admin-disclosure filter-disclosure" id="device-more-filters"><summary>More filters</summary><div class="disclosure-body">
              <label><span class="sr-only">Filter by family</span><select id="device-family" data-admin-dropdown><option value="all">All families</option>{family_options}</select></label>
              <label><span class="sr-only">Filter by install policy</span><select id="device-support" data-admin-dropdown><option value="all">All policies</option><option value="APPROVED">Approved</option><option value="BLOCKED">Blocked</option><option value="PENDING">Pending</option></select></label>
              <label><span class="sr-only">Filter by evidence</span><select id="device-status" data-admin-dropdown><option value="all">All evidence</option><option value="TESTING">Testing</option><option value="TESTED">Tested</option><option value="SUPPORTED">Supported</option><option value="VERIFIED">Verified</option><option value="unavailable">Unavailable</option></select></label>
            </div></details>
            <label class="device-mobile-sort"><span class="sr-only">Sort devices</span><select id="device-mobile-sort" data-admin-dropdown>{mobile_sort_options}</select></label>
            <p class="results-count" id="device-results-count" aria-live="polite">{_count_label(summary['mapCapable'], 'result')}</p>
            <button type="button" class="secondary-button filter-clear" data-filter-clear aria-label="Clear device filters" hidden>Clear</button>
          </form>
          <div class="device-sticky-header" id="device-sticky-header" aria-hidden="true"><div class="device-sticky-header-scroll"><table class="admin-table" role="presentation">{table_columns}{table_header.replace('<button type="button"', '<button type="button" tabindex="-1"')}</table></div></div>
          <div class="table-wrap device-table-wrap"><table class="admin-table"><caption class="sr-only">Device catalog and Terento installation evidence</caption>{table_columns}{table_header}<tbody id="device-rows">{rows_html}</tbody></table></div>
          <div class="device-pagination" id="device-pagination" hidden><button type="button" id="device-previous">Previous</button><span id="device-page-status"></span><button type="button" id="device-next">Next</button></div>
        </section>
    """
    content = f"""
      {_admin_header(user, csrf_token, active="devices")}
      <main class="dashboard devices-page" id="main-content">
        <div class="heading-row installation-heading"><div><h1>Devices</h1></div>{sync_meta}</div>
        {device_list}
      </main>
      <script nonce="{_ADMIN_NONCE_PLACEHOLDER}">const terentoAdminDevices = {payload_json};{_devices_script()}</script>
    """
    return _layout("Devices", content, sections={"devices": payload})


def _device_table_header() -> str:
    return """<thead><tr><th scope="col" class="column-text" aria-sort="ascending"><button type="button" class="device-sort-button" data-device-sort="model" aria-label="Model">Model <span aria-hidden="true">↑</span></button></th><th scope="col" class="column-text" aria-sort="none"><button type="button" class="device-sort-button" data-device-sort="variant" aria-label="Variant">Variant <span class="sort-indicator" aria-hidden="true" data-sort="none"></span></button></th><th scope="col" class="column-status" aria-sort="none"><button type="button" class="device-sort-button" data-device-sort="maps" aria-label="Maps" title="Stored catalog map capability">Maps <span class="sort-indicator" aria-hidden="true" data-sort="none"></span></button></th><th scope="col" class="column-status" aria-sort="none"><button type="button" class="device-sort-button" data-device-sort="authorization" aria-label="Install policy" title="Install policy">Install policy <span class="sort-indicator" aria-hidden="true" data-sort="none"></span></button></th><th scope="col" class="column-status" aria-sort="none"><button type="button" class="device-sort-button" data-device-sort="status" aria-label="Evidence" title="Compatibility evidence">Evidence <span class="sort-indicator" aria-hidden="true" data-sort="none"></span></button></th><th scope="col" class="column-number" aria-sort="none"><button type="button" class="device-sort-button" data-device-sort="attempts" aria-label="Install attempts" title="Install attempts">Attempts <span class="sort-indicator" aria-hidden="true" data-sort="none"></span></button></th><th scope="col" class="column-number" aria-sort="none"><button type="button" class="device-sort-button" data-device-sort="success" aria-label="Successful installations" title="Successful installations">Successful <span class="sort-indicator" aria-hidden="true" data-sort="none"></span></button></th><th scope="col" class="column-date" aria-sort="none"><button type="button" class="device-sort-button" data-device-sort="evidence" aria-label="Last successful installation" title="Last successful installation">Last success <span class="sort-indicator" aria-hidden="true" data-sort="none"></span></button></th></tr></thead>"""


def _device_table_columns() -> str:
    return """<colgroup class="device-table-columns"><col class="device-column-model"><col class="device-column-variant"><col class="device-column-maps"><col class="device-column-authorization"><col class="device-column-status"><col class="device-column-attempts"><col class="device-column-successful"><col class="device-column-last-success"></colgroup>"""


def _campaign_hint(text: str, hint_id: str = "") -> str:
    """One short muted help line saying when to use a control (markup allowed)."""
    id_attribute = f" id='{html.escape(hint_id, quote=True)}'" if hint_id else ""
    return f"<p class='campaign-hint'{id_attribute}>{text}</p>"


def _campaign_text_input(input_id: str, *, placeholder: str, hint_id: str, extra: str = "") -> str:
    return (
        f"<input id='{input_id}' type='text' maxlength='{MAX_VALUE_LENGTH}' autocomplete='off' "
        f"spellcheck='false' autocapitalize='none' placeholder='{html.escape(placeholder, quote=True)}' "
        f"aria-describedby='{hint_id}'{extra}>"
    )


def _campaign_choice(select_id: str, options: list[tuple[str, str]], selected: str, *, label: str) -> str:
    """A single-choice quick-filter group in the Installations filter-bar style."""
    return (
        "<div class='filter-bar admin-filter-bar campaign-choice'>"
        + _quick_select_filter(select_id, options, selected, label=label)
        + "</div>"
    )


def _campaign_row(label: str, control: str, *, label_for: str = "", label_id: str = "") -> str:
    if label_for:
        label_markup = f"<label class='campaign-label' for='{label_for}'>{label}</label>"
    else:
        label_markup = f"<span class='campaign-label' id='{label_id}'>{label}</span>"
    return (
        f"<div class='campaign-row'><div class='campaign-row-label'>{label_markup}</div>"
        f"<div class='campaign-row-control'>{control}</div></div>"
    )


def campaign_links_page(user: dict[str, Any], csrf_token: str) -> bytes:
    """Local campaign link builder (docs/admin-behavior-contract.md, Campaign links).

    Every vocabulary comes from ``campaign_links.py``: the page renders the
    channel, destination and campaign choices from it and the script embeds the
    same constants. The builder never stores or posts anything.
    """
    default_channel = CHANNELS[0]
    default_campaign = CAMPAIGN_SUGGESTIONS[0]
    default_url = build_campaign_url(destination="home", channel=default_channel.key, campaign=default_campaign)
    channel_choice = _campaign_choice(
        "campaign-channel", [(channel.key, channel.label) for channel in CHANNELS], default_channel.key,
        label="Where will you share this link?",
    )
    medium_choice = _campaign_choice(
        "campaign-medium",
        [(value, "Other…" if value == "other" else label) for value, label in MEDIUM_OPTIONS],
        OTHER_CHANNEL_DEFAULT_MEDIUM, label="Medium",
    )
    destination_choice = _campaign_choice(
        "campaign-destination", [*DESTINATION_OPTIONS, ("other", "Other page…")], "home", label="Destination",
    )
    campaign_choice = _campaign_choice(
        "campaign-name-choice",
        [*((value, value.replace("_", " ").capitalize()) for value in CAMPAIGN_SUGGESTIONS), ("custom", "Custom…")],
        default_campaign, label="Campaign",
    )
    source_suggestions = "".join(
        f"<option value='{html.escape(value, quote=True)}'></option>" for value, _ in SOURCE_OPTIONS if value != "other"
    )
    note = (
        f"<div class='campaign-note' role='note'>{_admin_icon('info')}<div>"
        "<p class='campaign-note-title'>When to use campaign links</p><ul>"
        "<li>Use one whenever you post a terento.app link outside the site.</li>"
        "<li>Pick the channel where you post it, so each place is always counted the same way.</li>"
        "<li>Use the same campaign name for every post in one effort.</li>"
        "</ul></div></div>"
    )
    other_fields = (
        "<div class='campaign-reveal' id='campaign-other-fields' hidden>"
        "<div class='campaign-subfield'><label class='campaign-sublabel' for='campaign-source'>Source</label>"
        + _campaign_text_input(
            "campaign-source", placeholder="linkedin", hint_id="campaign-source-hint",
            extra=" list='campaign-source-suggestions'",
        )
        + f"<datalist id='campaign-source-suggestions'>{source_suggestions}</datalist>"
        + _campaign_hint("The site or app as one word. Reuse an existing name when there is one.", "campaign-source-hint")
        + "</div><div class='campaign-subfield'><span class='campaign-sublabel' id='campaign-medium-label'>Medium</span>"
        + medium_choice
        + _campaign_hint("Community for forums and groups, social for feeds, referral for other websites.")
        + "<div class='campaign-subfield' id='campaign-medium-custom-wrap' hidden>"
        "<label class='campaign-sublabel' for='campaign-medium-custom'>Custom medium</label>"
        + _campaign_text_input("campaign-medium-custom", placeholder="partner", hint_id="campaign-medium-custom-hint")
        + _campaign_hint("Only when none of the mediums above fits.", "campaign-medium-custom-hint")
        + "</div></div></div>"
    )
    destination_fields = (
        "<div class='campaign-reveal' id='campaign-destination-fields' hidden>"
        "<div class='campaign-subfield'><label class='campaign-sublabel' for='campaign-destination-custom'>terento.app page</label>"
        "<input id='campaign-destination-custom' type='text' inputmode='url' autocomplete='off' spellcheck='false' "
        "autocapitalize='none' placeholder='/guides/install-garmin-maps-mac/' aria-describedby='campaign-destination-custom-hint'>"
        + _campaign_hint("Only terento.app pages. A path such as /about/ is enough.", "campaign-destination-custom-hint")
        + "</div></div>"
    )
    campaign_fields = (
        "<div class='campaign-reveal' id='campaign-name-fields' hidden>"
        "<div class='campaign-subfield'><label class='campaign-sublabel' for='campaign-name-custom'>Campaign name</label>"
        + _campaign_text_input("campaign-name-custom", placeholder="winter_update", hint_id="campaign-name-custom-hint")
        + _campaign_hint(
            "Lowercase letters, numbers, _ and -; spaces become _."
            "<span id='campaign-name-normalized' class='campaign-normalized' hidden> Used as <strong></strong></span>",
            "campaign-name-custom-hint",
        )
        + "</div></div>"
    )
    form = (
        "<form id='campaign-link-form' class='campaign-form' novalidate>"
        + _campaign_row(
            "Where will you share this link?",
            channel_choice
            + _campaign_hint("Sets the source and medium, so one place is always counted the same way.", "campaign-channel-hint")
            + other_fields,
            label_id="campaign-channel-label",
        )
        + _campaign_row(
            "Destination",
            destination_choice
            + _campaign_hint(
                "The page people land on. Download for install posts, Compatibility for device questions.",
                "campaign-destination-hint",
            )
            + destination_fields,
            label_id="campaign-destination-label",
        )
        + _campaign_row(
            "Campaign",
            campaign_choice
            + _campaign_hint("Names the effort, not the place. Reuse it on every channel for that effort.", "campaign-name-hint")
            + campaign_fields,
            label_id="campaign-name-label",
        )
        + _campaign_row(
            "Where exactly <span class='campaign-optional'>(optional)</span>",
            _campaign_text_input("campaign-content", placeholder="r_garmin", hint_id="campaign-content-hint")
            + _campaign_hint(
                f"<span id='campaign-content-example'>{html.escape(default_channel.content_hint)}</span>. "
                "Tells posts on the same channel apart.",
                "campaign-content-hint",
            ),
            label_for="campaign-content",
        )
        + "<details class='admin-disclosure campaign-more' id='campaign-more'><summary>More options</summary>"
        "<div class='disclosure-body'>"
        + _campaign_row(
            "Term <span class='campaign-optional'>(optional)</span>",
            _campaign_text_input("campaign-term", placeholder="garmin_maps", hint_id="campaign-term-hint")
            + _campaign_hint("Rarely needed: only for paid search keywords. Leave empty for posts.", "campaign-term-hint"),
            label_for="campaign-term",
        )
        + "</div></details></form>"
    )
    result = (
        "<div class='campaign-result'>"
        "<label class='campaign-label' for='generated-url'>Campaign link</label>"
        "<div class='campaign-url-row'>"
        "<textarea id='generated-url' class='campaign-url' rows='1' readonly "
        "placeholder='Complete the choices above' aria-describedby='campaign-summary campaign-message'>"
        f"{html.escape(default_url)}</textarea>"
        "<button id='copy-link' type='button' class='copy-button'>Copy link</button></div>"
        "<p class='campaign-summary' id='campaign-summary'>Umami will show: "
        f"<span id='campaign-summary-values'>source <strong>{html.escape(default_channel.source)}</strong> · "
        f"medium <strong>{html.escape(default_channel.medium)}</strong> · "
        f"campaign <strong>{html.escape(default_campaign)}</strong></span></p>"
        "<p class='campaign-message' id='campaign-message' role='status' aria-live='polite' data-state=''>"
        f"<span class='campaign-message-icon' data-icon='incomplete'>{_admin_icon('circle-exclamation')}</span>"
        f"<span class='campaign-message-icon' data-icon='copied'>{_admin_icon('circle-check')}</span>"
        f"<span class='campaign-message-icon' data-icon='failed'>{_admin_icon('x-circle')}</span>"
        "<span id='campaign-message-text'></span></p>"
        "</div>"
    )
    card = _section_card(
        "Campaign link builder", note + form + result, card_id="campaign-builder", css="campaign-card",
        totals="<p class='campaign-local'>Built in this browser. Nothing is saved.</p>",
    )
    content = f"""
      {_admin_header(user, csrf_token, active="campaigns")}
      <main class="dashboard campaign-page" id="main-content">
        <div class="heading-row"><div><h1>Campaign links</h1></div></div>
        {card}
      </main>
      <script nonce="{_ADMIN_NONCE_PLACEHOLDER}">{_campaign_links_script()}</script>
    """
    return _layout("Campaign links", content)


def account_page(user: dict[str, Any], csrf_token: str, *, error: str | None = None, success: str | None = None) -> bytes:
    notice = _error(error) if error else (f"<p class='success'>{html.escape(success or '')}</p>" if success else "")
    return _layout(
        "Account",
        f"""
        {_admin_header(user, csrf_token, active="account")}
        <main class="auth-card account" id="main-content"><h1>Account</h1>{notice}
          <form method="post" action="/admin/account">
            <input type="hidden" name="csrf_token" value="{html.escape(csrf_token)}">
            <label>Username<input name="username" value="{html.escape(str(user['username']))}" autocomplete="username" required></label>
            <label>Current password<input type="password" name="current_password" autocomplete="current-password" required></label>
            <label>New password <small>(leave blank to keep it)</small><input type="password" name="new_password" autocomplete="new-password" minlength="14"></label>
            <label>Confirm new password<input type="password" name="new_password_confirmation" autocomplete="new-password" minlength="14"></label>
            <button type="submit">Save changes</button>
          </form>
        </main>
        """,
    )


def _statistics_row(
    row: dict[str, Any],
    diagnostic_summary: dict[str, int] | None = None,
    *, catalog_device: dict[str, Any] | None = None,
) -> str:
    model, variant, identity = _identity_parts(row)
    if catalog_device is not None:
        # Exact catalog identity drives display; original reported identity remains searchable.
        model, variant, _ = _identity_parts(catalog_device)
    summary = diagnostic_summary or {}
    attempted = int(row.get("attempted_install_count", summary.get("attempts", 0)) or 0)
    successful = int(row.get("successful_install_count", summary.get("successful", 0)) or 0)
    failed = int(row.get("failed_install_count", summary.get("failed", 0)) or 0)
    open_errors = int(summary.get("open_errors") or 0)
    status_value = _row_compatibility_status(row)
    status = status_value.value if status_value else ""
    search_text = " ".join((model, variant, str(row.get("family") or ""), identity)).strip()
    activity = max((_timestamp_iso(row.get(key)) for key in ("last_success", "last_failure", "last_evidence")), default="")
    diagnostics_url = _model_detail_url(row)
    pending_count = int(summary.get("identity_pending") or 0)
    model_cell = html.escape(model)
    if _is_historical_catalog(catalog_device if catalog_device is not None else row):
        model_cell += " " + _historical_catalog_indicator()
    if variant == "Historical":
        variant = "—"
    model_cell = (
        f"<a class='device-model-button' href='{html.escape(diagnostics_url, quote=True)}'>"
        f"{model_cell}</a>"
    )
    if pending_count:
        # The badge opens the Identity review queue at this reported identity;
        # the model link keeps its own destination.
        model_cell += (
            f" <a class='identity-pending-indicator' href='{html.escape(_identity_review_url(_reported_identity(row)), quote=True)}'"
            f" aria-label='Identity review: {pending_count} pending'>"
            "Identity review</a>"
        )
    open_errors_markup = _admin_error_counter(
        open_errors,
        href=_model_detail_url(row, state="open") if open_errors else None,
        aria_label=f"View {open_errors} open {'problem' if open_errors == 1 else 'problems'}",
    )
    cells = (
        ("", model_cell),
        ("", html.escape(variant)),
        ("column-status", _status_badge(status)),
        ("column-number numeric", html.escape(str(attempted))),
        ("column-number numeric", html.escape(str(successful))),
        ("column-number numeric", _admin_error_counter(failed)),
        ("column-number numeric", open_errors_markup),
        ("column-date", _timestamp_markup(row.get("last_success"))),
    )
    return (
        f"<tr class='evidence-model-row' data-search='{html.escape(search_text, quote=True)}' data-model='{html.escape(model, quote=True)}' data-variant='{html.escape(variant if variant != '—' else '', quote=True)}' data-identity='{html.escape(_identity_group_key(row), quote=True)}' data-successful-count='{successful}' data-failed-count='{failed}' data-last-success='{_timestamp_iso(row.get('last_success'))}' data-status='{html.escape(status.lower(), quote=True)}' data-activity='{html.escape(activity, quote=True)}' data-attempts='{attempted}' data-errors='{open_errors}' data-identity-pending='{pending_count}' data-failed='{str(failed > 0).lower()}' data-successful='{str(successful > 0).lower()}' data-diagnostics-url='{html.escape(diagnostics_url, quote=True)}'>"
        + "".join(f"<td class='{css_class}'>{cell}</td>" if css_class else f"<td>{cell}</td>" for css_class, cell in cells)
        + f"</tr>"
    )


def _status_badge(value: str) -> str:
    """Evidence pill: Testing neutral, Tested/Supported info, Verified success."""
    try:
        status = CompatibilityStatus(str(value).upper())
    except ValueError:
        return _status_pill("neutral", "Unavailable", value="UNAVAILABLE", title="Compatibility evidence unavailable")
    kind = {"TESTING": "neutral", "TESTED": "info", "SUPPORTED": "info", "VERIFIED": "success"}.get(status.value, "neutral")
    return _status_pill(kind, status.value.title(), value=status.value, title=STATUS_PUBLIC_COPY[status])


def _device_last_success_comparator_script() -> str:
    return r"""(a, b, direction, textCompare) => {
        const timestamp = (device) => device.installationStats.lastSuccessfulAt
          ? Date.parse(device.installationStats.lastSuccessfulAt) : null;
        const aValue = timestamp(a);
        const bValue = timestamp(b);
        if (aValue === null) return bValue === null ? textCompare(a.id, b.id) : 1;
        if (bValue === null) return -1;
        const comparison = aValue - bValue;
        return (direction === 'descending' ? -comparison : comparison) || textCompare(a.id, b.id);
      }"""


def _table_filter_state_script() -> str:
    return r"""let saved = {};
      try { saved = JSON.parse(sessionStorage.getItem(storageKey) || '{}'); } catch (_) { saved = {}; }
      const restoreSelect = (control, key, fallback) => {
        const value = parameters.has(key) ? parameters.get(key) : saved[key];
        control.value = [...control.options].some(option => option.value === value) ? value : fallback;
      };"""


def _devices_script() -> str:
    script = r"""(() => {
      const devices = terentoAdminDevices.devices || [];
      const body = document.querySelector('#device-rows');
      const form = document.querySelector('#device-filters');
      const search = document.querySelector('#device-search');
      const family = document.querySelector('#device-family');
      const map = document.querySelector('#device-map');
      const support = document.querySelector('#device-support');
      const status = document.querySelector('#device-status');
      const sortButtons = [...document.querySelectorAll('[data-device-sort]')];
      const mapFilters = [...document.querySelectorAll('[data-device-map-filter]')];
      const clear = form?.querySelector('[data-filter-clear]');
      const count = document.querySelector('#device-results-count');
      const pagination = document.querySelector('#device-pagination');
      const previous = document.querySelector('#device-previous');
      const next = document.querySelector('#device-next');
      const pageStatus = document.querySelector('#device-page-status');
      const showNewButton = document.querySelector('#device-show-new');
      const tableScroll = document.querySelector('.device-table-wrap');
      const stickyHeaderScroll = document.querySelector('.device-sticky-header-scroll');
      const stickyHeaderTable = stickyHeaderScroll?.querySelector('table');
      if (!body || !form || !search || !family || !map || !support || !status || !count) return;

      const pageSize = 50;
      let page = 0;
      let sortKey = 'model';
      let sortDirection = 'ascending';
      let showNew = false;
      let publicationReview = false;
      const storageKey = 'terento.admin.devices.filters';
      const parameters = new URLSearchParams(window.location.search);
      __TABLE_FILTER_STATE__
      search.value = parameters.has('search') ? parameters.get('search') : (saved.search || '');
      restoreSelect(family, 'family', 'all');
      // The Maps quick filter comes only from an explicit ?maps= link; a plain
      // visit opens at the Maps: Yes default instead of the previous visit's choice.
      map.value = [...map.options].some((option) => option.value === parameters.get('maps')) ? parameters.get('maps') : 'yes';
      restoreSelect(support, 'authorization', 'all');
      restoreSelect(status, 'status', 'all');
      sortKey = parameters.get('sort') || saved.sort || 'model';
      sortDirection = parameters.get('direction') || saved.direction || 'ascending';
      publicationReview = parameters.get('review') === 'publication';
      // Needs attention → Maps unknown opens active models only.
      const activeOnly = parameters.get('active') === '1';
      if (publicationReview) { search.value = ''; family.value = 'all'; map.value = 'all'; support.value = 'all'; status.value = 'all'; }
      showNew = parameters.get('new') === '1';
      const mapValue = (device) => device.mapCapable === true ? 'yes' : device.mapCapable === false ? 'no' : 'unknown';
      const deviceSearch = (device) => [device.id, device.model, device.canonicalModel, device.family, device.familyName, device.variant, device.caseSizeMm, device.partNumber, device.displayType].filter(Boolean).join(' ').toLocaleLowerCase();
      const textCompare = (a, b) => String(a || '').localeCompare(String(b || ''), undefined, {sensitivity: 'base', numeric: true});
      const statusOrder = {unavailable: 0, TESTING: 1, TESTED: 2, SUPPORTED: 3, VERIFIED: 4};
      const mapOrder = {unknown: 0, no: 1, yes: 2};
      const authorizationOrder = {PENDING: 0, BLOCKED: 1, APPROVED: 2};
      const compareLastSuccess = __TERENTO_LAST_SUCCESS_COMPARATOR__;
      const sortValue = (device, key) => ({
        model: device.model,
        variant: device.variant,
        maps: mapOrder[mapValue(device)],
        authorization: authorizationOrder[device.installationAuthorization || 'PENDING'],
        status: statusOrder[device.evidenceStatus || 'unavailable'],
        attempts: Number(device.installationStats.attempts || 0),
        success: Number(device.installationStats.successful || 0),
        evidence: device.installationStats.lastSuccessfulAt ? Date.parse(device.installationStats.lastSuccessfulAt) : null,
      })[key];
      const compareDevices = (a, b) => {
        if (sortKey === 'evidence') return compareLastSuccess(a, b, sortDirection, textCompare);
        const aValue = sortValue(a, sortKey);
        const bValue = sortValue(b, sortKey);
        if (aValue === null || aValue === undefined || aValue === '') return bValue === null || bValue === undefined || bValue === '' ? textCompare(a.id, b.id) : 1;
        if (bValue === null || bValue === undefined || bValue === '') return -1;
        const comparison = typeof aValue === 'number' && typeof bValue === 'number' ? aValue - bValue : textCompare(aValue, bValue);
        return (sortDirection === 'descending' ? -comparison : comparison) || textCompare(a.id, b.id);
      };
      const updateSortHeaders = () => sortButtons.forEach((button) => {
        const active = button.dataset.deviceSort === sortKey;
        const header = button.closest('th');
        const indicator = button.querySelector('span');
        if (header) header.setAttribute('aria-sort', active ? sortDirection : 'none');
        if (indicator) indicator.dataset.sort = active ? sortDirection : 'none';
      });
      const saveState = () => {
        const state = {
          search: search.value, family: family.value,
          authorization: support.value, status: status.value,
          sort: sortKey, direction: sortDirection,
        };
        try { sessionStorage.setItem(storageKey, JSON.stringify(state)); } catch (_) { /* optional */ }
        const query = new URLSearchParams();
        if (search.value) query.set('search', search.value);
        query.set('maps', map.value);
        if (family.value !== 'all') query.set('family', family.value);
        if (support.value !== 'all') query.set('authorization', support.value);
        if (status.value !== 'all') query.set('status', status.value);
        if (sortKey !== 'model') query.set('sort', sortKey);
        if (sortDirection !== 'ascending') query.set('direction', sortDirection);
        if (showNew) query.set('new', '1');
        if (publicationReview) query.set('review', 'publication');
        if (activeOnly) query.set('active', '1');
        history.replaceState(null, '', `${window.location.pathname}?${query.toString()}`);
      };
      const matching = () => {
        const query = search.value.trim().toLocaleLowerCase();
        return devices.filter((device) => {
          if (publicationReview && !(device.publicCompatibility?.eligible && ['TESTED', 'SUPPORTED', 'VERIFIED'].includes(device.evidenceStatus) && !device.publicCompatibility?.published && device.publicCompatibility?.reviewStatus !== 'REJECTED')) return false;
          if (showNew) return device.catalog?.newInLatestSync === true;
          if (activeOnly && device.active === false) return false;
          const matchesSearch = !query || deviceSearch(device).includes(query);
          const matchesFamily = family.value === 'all' || family.value === (device.familyName || device.family);
          const matchesMap = map.value === 'all' || mapValue(device) === map.value;
          const matchesAuthorization = support.value === 'all' || (device.installationAuthorization || 'PENDING') === support.value;
          const matchesStatus = status.value === 'all' || (device.evidenceStatus || 'unavailable') === status.value;
          return matchesSearch && matchesFamily && matchesMap && matchesAuthorization && matchesStatus;
        }).sort(compareDevices);
      };
      const refresh = () => {
        const visible = matching();
        const totalPages = Math.max(1, Math.ceil(visible.length / pageSize));
        page = Math.min(page, totalPages - 1);
        const pageRows = visible.slice(page * pageSize, (page + 1) * pageSize);
        const rowsById = new Map([...body.querySelectorAll('tr[data-device-index]')].map((row) => {
          const device = devices[Number(row.dataset.deviceIndex)];
          return [device && device.id, row];
        }));
        rowsById.forEach((row) => { row.hidden = true; });
        pageRows.forEach((device) => {
          const row = rowsById.get(device.id);
          if (!row) return;
          row.hidden = false;
          body.appendChild(row);
        });
        count.textContent = `${visible.length} ${publicationReview ? 'awaiting publication review' : visible.length === 1 ? 'result' : 'results'}`;
        pagination.hidden = visible.length <= pageSize;
        pageStatus.textContent = `Page ${page + 1} of ${totalPages}`;
        previous.disabled = page === 0;
        next.disabled = page >= totalPages - 1;
        mapFilters.forEach((button) => {
          const active = button.dataset.deviceMapFilter === map.value;
          button.classList.toggle('active', active);
          button.setAttribute('aria-pressed', active ? 'true' : 'false');
        });
        if (clear) clear.hidden = !(search.value.trim() || family.value !== 'all' || map.value !== 'yes'
          || support.value !== 'all' || status.value !== 'all' || sortKey !== 'model'
          || sortDirection !== 'ascending' || showNew || publicationReview);
        saveState();
      };
      const reset = () => { showNew = false; publicationReview = false; page = 0; refresh(); };
      const mobileSort = document.querySelector('#device-mobile-sort');
      if (mobileSort) {
        mobileSort.value = `${sortKey}:${sortDirection}`;
        mobileSort.addEventListener('change', () => { [sortKey, sortDirection] = mobileSort.value.split(':'); updateSortHeaders(); page = 0; refresh(); });
      }
      form.addEventListener('terento-admin-clear-filters', () => {
        search.value = '';
        family.value = 'all';
        map.value = 'yes';
        support.value = 'all';
        status.value = 'all';
        sortKey = 'model';
        sortDirection = 'ascending';
        if (mobileSort) mobileSort.value = 'model:ascending';
        showNew = false;
        publicationReview = false;
        page = 0;
        updateSortHeaders();
        refresh();
      });
      form.addEventListener('submit', (event) => event.preventDefault());
      [search, family, map, support, status].forEach((control) => control.addEventListener(control === search ? 'input' : 'change', reset));
      mapFilters.forEach((button) => button.addEventListener('click', () => {
        map.value = button.dataset.deviceMapFilter;
        map.dispatchEvent(new Event('change', {bubbles: true}));
      }));
      sortButtons.forEach((button) => button.addEventListener('click', () => {
        const key = button.dataset.deviceSort;
        if (sortKey === key) sortDirection = sortDirection === 'ascending' ? 'descending' : 'ascending';
        else { sortKey = key; sortDirection = 'ascending'; }
        updateSortHeaders();
        if (mobileSort) mobileSort.value = `${sortKey}:${sortDirection}`;
        reset();
      }));
      showNewButton?.addEventListener('click', () => {
        search.value = '';
        family.value = 'all';
        map.value = 'all';
        support.value = 'all';
        status.value = 'all';
        showNew = true;
        page = 0;
        refresh();
      });
      previous.addEventListener('click', () => { page -= 1; refresh(); });
      next.addEventListener('click', () => { page += 1; refresh(); });
      body.addEventListener('click', (event) => {
        const row = event.target.closest('tr[data-device-index]');
        if (!row || event.target.closest('a,button,input,select,textarea')) return;
        window.location.assign(row.dataset.deviceUrl);
      });
      body.addEventListener('keydown', (event) => {
        if (event.key !== 'Enter' && event.key !== ' ') return;
        const row = event.target.closest('tr[data-device-index]');
        if (!row || event.target.closest('a,button')) return;
        event.preventDefault();
        window.location.assign(row.dataset.deviceUrl);
      });
      const syncStickyHeader = () => {
        if (tableScroll && stickyHeaderTable) {
          stickyHeaderTable.style.transform = `translateX(${-tableScroll.scrollLeft}px)`;
        }
      };
      tableScroll?.addEventListener('scroll', syncStickyHeader, {passive: true});
      updateSortHeaders();
      refresh();
      syncStickyHeader();
    })();"""
    return script.replace("__TABLE_FILTER_STATE__", _table_filter_state_script()).replace(
        "__TERENTO_LAST_SUCCESS_COMPARATOR__",
        _device_last_success_comparator_script(),
    )


def _campaign_links_config() -> str:
    """The contract constants the browser builder uses, from ``campaign_links.py``."""
    config = {
        "destinations": DESTINATIONS,
        "channels": {
            channel.key: {"source": channel.source, "medium": channel.medium, "contentHint": channel.content_hint}
            for channel in CHANNELS
        },
        "maxLength": MAX_VALUE_LENGTH,
    }
    return json.dumps(config, sort_keys=True).replace("<", "\\u003c")


def _campaign_links_script() -> str:
    return r"""(() => {
      const config = __CAMPAIGN_CONFIG__;
      const utmKeys = new Set(['utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term']);
      const form = document.querySelector('#campaign-link-form');
      if (!form) return;
      const byId = (id) => document.getElementById(id);
      const controls = {
        channel: byId('campaign-channel'),
        otherFields: byId('campaign-other-fields'),
        source: byId('campaign-source'),
        medium: byId('campaign-medium'),
        mediumCustom: byId('campaign-medium-custom'),
        mediumCustomWrap: byId('campaign-medium-custom-wrap'),
        destination: byId('campaign-destination'),
        destinationFields: byId('campaign-destination-fields'),
        destinationCustom: byId('campaign-destination-custom'),
        campaignChoice: byId('campaign-name-choice'),
        campaignFields: byId('campaign-name-fields'),
        campaignCustom: byId('campaign-name-custom'),
        campaignNormalized: byId('campaign-name-normalized'),
        content: byId('campaign-content'),
        contentExample: byId('campaign-content-example'),
        term: byId('campaign-term'),
        more: byId('campaign-more'),
        output: byId('generated-url'),
        copy: byId('copy-link'),
        summary: byId('campaign-summary'),
        summaryValues: byId('campaign-summary-values'),
        message: byId('campaign-message'),
        messageText: byId('campaign-message-text')
      };
      // Mirrors campaign_links.normalize_value exactly.
      const normalizeValue = (value) => {
        let text = String(value || '').normalize('NFKD').replace(/[̀-ͯ]/g, '').trim().toLowerCase();
        text = text.replace(/\s+/g, '_').replace(/[^a-z0-9_-]/g, '').replace(/[-_]{2,}/g, (match) => match[0]);
        return text.replace(/^[-_]+|[-_]+$/g, '');
      };
      const destinationUrl = () => {
        if (controls.destination.value !== 'other') return config.destinations[controls.destination.value] || null;
        const value = controls.destinationCustom.value.trim();
        if (!value || value.startsWith('//')) return null;
        if (value.startsWith('/')) return `https://terento.app${value}`;
        try {
          const parsed = new URL(value);
          if (parsed.protocol !== 'https:' || parsed.hostname !== 'terento.app' || parsed.username || parsed.password || (parsed.port && parsed.port !== '443')) return null;
          return `https://terento.app${parsed.pathname || '/'}${parsed.search}${parsed.hash}`;
        } catch (_) {
          return null;
        }
      };
      // Mirrors campaign_links.channel_source_medium.
      const channelSourceMedium = () => {
        const channel = config.channels[controls.channel.value];
        if (!channel) return { source: '', medium: '' };
        if (controls.channel.value !== 'other') return { source: channel.source, medium: channel.medium };
        const medium = controls.medium.value === 'other' ? controls.mediumCustom.value : controls.medium.value;
        return { source: normalizeValue(controls.source.value), medium: normalizeValue(medium) };
      };
      const campaignValue = () => normalizeValue(
        controls.campaignChoice.value === 'custom' ? controls.campaignCustom.value : controls.campaignChoice.value
      );
      const evaluate = () => {
        const base = destinationUrl();
        const { source, medium } = channelSourceMedium();
        const campaign = campaignValue();
        const content = normalizeValue(controls.content.value);
        const term = normalizeValue(controls.term.value);
        let problem = '';
        if (!source) problem = 'Add a source for Other to build the link.';
        else if (!medium) problem = 'Add a custom medium to build the link.';
        else if (!base) problem = controls.destinationCustom.value.trim()
          ? 'Use a terento.app page, for example /about/.'
          : 'Add the terento.app page to build the link.';
        else if (!campaign) problem = 'Name the campaign to build the link.';
        else if ([source, medium, campaign, content, term].some((value) => value.length > config.maxLength)) {
          problem = `Keep each value to ${config.maxLength} characters; Umami ignores longer values.`;
        }
        if (problem) return { problem };
        const parsed = new URL(base);
        const existing = [...parsed.searchParams.entries()].filter(([key]) => !utmKeys.has(key.toLowerCase()));
        parsed.search = new URLSearchParams(existing).toString();
        parsed.searchParams.append('utm_source', source);
        parsed.searchParams.append('utm_medium', medium);
        parsed.searchParams.append('utm_campaign', campaign);
        if (content) parsed.searchParams.append('utm_content', content);
        if (term) parsed.searchParams.append('utm_term', term);
        return { url: parsed.toString(), source, medium, campaign, content, term };
      };
      const buildUrl = () => {
        const result = evaluate();
        return result.problem ? null : result;
      };
      window.TerentoCampaignLinkBuilder = { normalizeValue, buildUrl, config };
      const reveal = (wrapper, visible) => { wrapper.hidden = !visible; };
      const setMessage = (state, text) => {
        controls.message.dataset.state = state;
        controls.messageText.textContent = text;
      };
      let copyTimer = 0;
      // Grow the read-only link field to show the whole URL; keep the scroll
      // position so a shorter field never moves the control under the pointer.
      const fitOutput = () => {
        const { scrollX, scrollY } = window;
        controls.output.style.height = 'auto';
        controls.output.style.height = `${controls.output.scrollHeight + 2}px`;
        window.scrollTo(scrollX, scrollY);
      };
      const setOutput = (value) => {
        if (controls.output.value === value && controls.output.style.height) return;
        controls.output.value = value;
        fitOutput();
      };
      const refresh = () => {
        const isOther = controls.channel.value === 'other';
        reveal(controls.otherFields, isOther);
        reveal(controls.mediumCustomWrap, isOther && controls.medium.value === 'other');
        reveal(controls.destinationFields, controls.destination.value === 'other');
        reveal(controls.campaignFields, controls.campaignChoice.value === 'custom');
        const channel = config.channels[controls.channel.value];
        if (channel) controls.contentExample.textContent = channel.contentHint;
        const typed = controls.campaignCustom.value;
        const normalized = normalizeValue(typed);
        controls.campaignNormalized.hidden = !typed.trim() || normalized === typed;
        controls.campaignNormalized.querySelector('strong').textContent = normalized || '—';
        const result = evaluate();
        window.clearTimeout(copyTimer);
        if (result.problem) {
          setOutput('');
          controls.copy.disabled = true;
          controls.summary.hidden = true;
          setMessage('incomplete', result.problem);
          return;
        }
        setOutput(result.url);
        controls.copy.disabled = false;
        controls.summary.hidden = false;
        const parts = [['source', result.source], ['medium', result.medium], ['campaign', result.campaign], ['content', result.content], ['term', result.term]]
          .filter(([, value]) => value);
        controls.summaryValues.replaceChildren(...parts.flatMap(([name, value], index) => {
          const strong = document.createElement('strong');
          strong.textContent = value;
          return [document.createTextNode(`${index ? ' · ' : ''}${name} `), strong];
        }));
        setMessage('', '');
      };
      const copyText = async (value) => {
        if (navigator.clipboard && window.isSecureContext) {
          try {
            await navigator.clipboard.writeText(value);
            return;
          } catch (_) {
            // Fall back to selecting the read-only field below.
          }
        }
        controls.output.focus();
        controls.output.select();
        if (!document.execCommand('copy')) throw new Error('copy unavailable');
      };
      const focusOnReveal = (select, value, input) => select.addEventListener('change', () => {
        if (select.value === value) input.focus();
      });
      focusOnReveal(controls.channel, 'other', controls.source);
      focusOnReveal(controls.medium, 'other', controls.mediumCustom);
      focusOnReveal(controls.destination, 'other', controls.destinationCustom);
      focusOnReveal(controls.campaignChoice, 'custom', controls.campaignCustom);
      form.addEventListener('submit', (event) => event.preventDefault());
      form.addEventListener('input', refresh);
      form.addEventListener('change', refresh);
      // Show the canonical value once the operator leaves a free-text field.
      [controls.source, controls.mediumCustom, controls.campaignCustom, controls.content, controls.term].forEach((input) => {
        input.addEventListener('blur', () => {
          const normalized = normalizeValue(input.value);
          if (normalized !== input.value) {
            input.value = normalized;
            refresh();
          }
        });
      });
      controls.copy.addEventListener('click', async () => {
        const result = buildUrl();
        if (!result) return;
        try {
          await copyText(result.url);
          setMessage('copied', 'Link copied.');
          window.clearTimeout(copyTimer);
          copyTimer = window.setTimeout(() => setMessage('', ''), 2400);
        } catch (_) {
          controls.output.focus();
          controls.output.select();
          setMessage('failed', 'Copy failed. The link is selected; copy it with your keyboard.');
        }
      });
      window.addEventListener('resize', fitOutput);
      if (controls.term.value && controls.more) controls.more.open = true;
      refresh();
    })();""".replace("__CAMPAIGN_CONFIG__", _campaign_links_config())


def _dashboard_script() -> str:
    return """(() => {
      const form = document.querySelector('#evidence-filters');
      const search = document.querySelector('#evidence-search');
      const status = document.querySelector('#evidence-status');
      const sort = document.querySelector('#evidence-sort');
      const quickFilters = [...document.querySelectorAll('[data-installation-filter]')];
      const body = document.querySelector('#evidence-rows');
      const count = document.querySelector('#results-count');
      const clear = document.querySelector('[data-filter-clear]');
      const table = document.querySelector('#installation-table');
      const empty = document.querySelector('#installation-empty');
      const pagination = document.querySelector('#installation-pagination');
      const pageSize = document.querySelector('#installation-page-size');
      const previousPage = pagination?.querySelector('[data-installation-page="previous"]');
      const nextPage = pagination?.querySelector('[data-installation-page="next"]');
      const pageSummary = pagination?.querySelector('span');
      if (!form || !search || !status || !sort || !body || !count || !quickFilters.length) return;
      const rows = [...body.querySelectorAll('tr')];
      let page = 1;
      const storageKey = 'terento.admin.installations.filters';
      const parameters = new URLSearchParams(window.location.search);
      __TABLE_FILTER_STATE__
      search.value = parameters.has('search') ? parameters.get('search') : (saved.search || '');
      const quickFilterValues = quickFilters.map((button) => button.dataset.installationFilter);
      // The quick filter comes only from an explicit ?state= link; a plain visit
      // opens at All instead of restoring the previous visit's quick filter.
      let selectedQuickFilter = parameters.get('state') || 'all';
      if (!quickFilterValues.includes(selectedQuickFilter)) selectedQuickFilter = 'all';
      restoreSelect(status, 'status', 'all');
      const legacySort = {attempts:'attempts:descending', errors:'errors:descending', model:'model:ascending'};
      const requestedSort = parameters.get('sort') || saved.sort;
      if (legacySort[requestedSort]) saved.sort = legacySort[requestedSort];
      if (legacySort[parameters.get('sort')]) parameters.set('sort', legacySort[parameters.get('sort')]);
      restoreSelect(sort, 'sort', 'latest');
      const sortButtons = [...document.querySelectorAll('[data-installation-sort]')];
      const textCompare = (a, b) => String(a).localeCompare(String(b), undefined, {numeric:true, sensitivity:'base'});
      const statusOrder = __STATUS_ORDER__;
      const sortValue = (row, key) => {
        const raw = row.dataset[key];
        if (raw === undefined || raw === '') return null;
        if (key === 'status') { const rank = statusOrder.indexOf(raw); return rank < 0 ? null : rank; }
        if (['activity', 'lastSuccess'].includes(key)) { const stamp = Date.parse(raw); return Number.isFinite(stamp) ? stamp : null; }
        if (['attempts','successfulCount','failedCount','errors'].includes(key)) { const n = Number(raw); return Number.isFinite(n) ? n : null; }
        return raw;
      };
      const refresh = (resetPage = false) => {
        if (resetPage) page = 1;
        const searchQuery = search.value.trim().toLocaleLowerCase();
        const selectedStatus = status.value;
        const visible = rows.filter((row) => {
          const matchesSearch = !searchQuery || row.dataset.search.toLocaleLowerCase().includes(searchQuery);
          const matchesStatus = selectedStatus === 'all' || row.dataset.status === selectedStatus;
          const matchesQuick = selectedQuickFilter === 'all'
            || (selectedQuickFilter === 'failed' && row.dataset.failed === 'true')
            || (selectedQuickFilter === 'open' && Number(row.dataset.errors || 0) > 0)
            || (selectedQuickFilter === 'identity-pending' && Number(row.dataset.identityPending || 0) > 0)
            || (selectedQuickFilter === 'successful' && row.dataset.successful === 'true');
          return matchesSearch && matchesStatus && matchesQuick;
        });
        const [key, direction] = sort.value === 'latest' ? ['activity','descending'] : sort.value.split(':');
        visible.sort((a, b) => {
          const av = sortValue(a, key), bv = sortValue(b, key);
          const tie = textCompare(a.dataset.identity, b.dataset.identity);
          if (av === null) return bv === null ? tie : 1;
          if (bv === null) return -1;
          const order = typeof av === 'number' ? av - bv : textCompare(av, bv);
          return (direction === 'descending' ? -order : order) || tie;
        });
        sortButtons.forEach(button => {
          const active = button.dataset.installationSort === key;
          button.closest('th').setAttribute('aria-sort', active ? direction : 'none');
          button.querySelector('span').dataset.sort = active ? direction : 'none';
        });
        const size = pageSize && Number(pageSize.value) === 50 ? 50 : 25;
        const pages = Math.max(1, Math.ceil(visible.length / size));
        page = Math.min(Math.max(page, 1), pages);
        const startIndex = (page - 1) * size;
        const pageRows = visible.slice(startIndex, startIndex + size);
        rows.forEach((row) => { row.hidden = true; });
        pageRows.forEach((row) => { row.hidden = false; body.appendChild(row); });
        count.textContent = `${visible.length} ${visible.length === 1 ? 'variant' : 'variants'}`;
        empty.hidden = visible.length > 0;
        table.hidden = visible.length === 0;
        if (pagination) {
          pagination.hidden = visible.length <= size;
          const start = visible.length ? startIndex + 1 : 0;
          const end = visible.length ? Math.min(visible.length, startIndex + size) : 0;
          pageSummary.textContent = `Showing ${start}–${end} of ${visible.length} · page ${page} of ${pages}`;
          previousPage.disabled = page <= 1;
          nextPage.disabled = page >= pages;
        }
        quickFilters.forEach((button) => {
          const active = button.dataset.installationFilter === selectedQuickFilter;
          button.classList.toggle('active', active);
          button.setAttribute('aria-pressed', active ? 'true' : 'false');
        });
        const hasActiveFilters = Boolean(search.value.trim()) || status.value !== 'all'
          || selectedQuickFilter !== 'all' || sort.value !== 'latest';
        form.hidden = rows.length <= 1 && !hasActiveFilters;
        clear.hidden = !hasActiveFilters;
        const state = {search: search.value, status: status.value, sort: sort.value};
        try { sessionStorage.setItem(storageKey, JSON.stringify(state)); } catch (_) { /* optional */ }
        const stateQuery = new URLSearchParams();
        if (search.value) stateQuery.set('search', search.value);
        if (selectedQuickFilter !== 'all') stateQuery.set('state', selectedQuickFilter);
        if (status.value !== 'all') stateQuery.set('status', status.value);
        if (sort.value !== 'latest') stateQuery.set('sort', sort.value);
        history.replaceState(null, '', stateQuery.size ? `${window.location.pathname}?${stateQuery}` : window.location.pathname);
      };
      sortButtons.forEach(button => button.addEventListener('click', () => {
        const key = button.dataset.installationSort;
        sort.value = key + ':' + (sort.value === key + ':ascending' ? 'descending' : 'ascending');
        refresh(true);
      }));
      form.addEventListener('submit', (event) => event.preventDefault());
      form.addEventListener('terento-admin-clear-filters', () => {
        search.value = '';
        status.value = 'all';
        sort.value = 'latest';
        selectedQuickFilter = 'all';
        refresh(true);
      });
      quickFilters.forEach((button) => button.addEventListener('click', () => {
        selectedQuickFilter = button.dataset.installationFilter || 'all';
        refresh(true);
      }));
      search.addEventListener('input', () => refresh(true));
      [status, sort, pageSize].filter(Boolean).forEach((control) => control.addEventListener('change', () => refresh(true)));
      previousPage?.addEventListener('click', () => { page -= 1; refresh(); });
      nextPage?.addEventListener('click', () => { page += 1; refresh(); });
      refresh();
    })();""".replace("__TABLE_FILTER_STATE__", _table_filter_state_script()).replace("__STATUS_ORDER__", _admin_json([status.value.lower() for status in CANONICAL_STATUS_ORDER]))


def _client_issue_note_sanitizer_script() -> str:
    """Return the browser sanitizer used before note preview and URL creation."""
    return r"""(value) => value
          .slice(0, 500)
          .replace(/[\u0000-\u001f\u007f]+/g, ' ')
          .replace(/[<>]/g, '[redacted markup]')
          .replace(/\b(?:ghp|github_pat)_[A-Za-z0-9_-]+/gi, '[redacted token]')
          .replace(/\bBearer\s+[^\s,;]+/gi, 'Bearer [redacted]')
          .replace(/\b(?:Authorization|Proxy-Authorization|Cookie|Set-Cookie)\s*:\s*[^\s,;]+(?:\s+[^\s,;]+)?/gi, '[redacted header]')
          .replace(/([?&](?:token|access_token|api_key|apikey|secret)=)[^&\s]+/gi, '$1[redacted]')
          .replace(/[?&](?:title|body)=[^&\s]+/gi, '[redacted query value]')
          .replace(/\b(?:token|access[_ -]?token|api[_ -]?key|apikey|secret|password|cookie|authorization)\s*[:=]\s*\S+/gi, '[redacted credential]')
          .replace(/\b[A-Z][A-Z0-9_]{2,}\s*=\s*\S+/g, '[redacted environment value]')
          .replace(/\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/gi, '[redacted email]')
          .replace(/\/Users\/[^/\s]+(?:\/[^\s]*)?/gi, '[redacted path]')
          .replace(/(?:\/private|\/var\/folders|\/home|\/Volumes)\/[^\s]+/gi, '[redacted path]')
          .replace(/\b[A-Z]:[\\/]Users[\\/][^\\/\s]+(?:[\\/][^\s]*)?/gi, '[redacted path]')
          .replace(/\b(?:serial(?:[_ -]?number)?|unit[_ -]?id|device[_ -]?id|user[_ -]?id|account[_ -]?id)\s*[:=]\s*\S+/gi, '[redacted private identifier]')
          .replace(/\s+/g, ' ')
          .trim()
          .replace(/([\\`*_{}\[\]<>#+!|])/g, '\\$1')"""


def _diagnostics_script() -> str:
    script = r"""(() => {
      const filter = document.querySelector('#diagnostic-state-filter');
      const quickFilters = [...document.querySelectorAll('[data-history-filter]')];
      const body = document.querySelector('#diagnostic-rows');
      const count = document.querySelector('#diagnostic-results-count');
      const pagination = document.querySelector('#diagnostic-history-pagination');
      const pageSize = document.querySelector('#diagnostic-history-page-size');
      let rows = body ? [...body.querySelectorAll('tr[data-diagnostic-state]')] : [];
      const dialogs = [...document.querySelectorAll('.diagnostic-detail-dialog')];
      let page = 1;
      let lastFocused = null;
      const filterValues = filter ? [...filter.options].map((option) => option.value) : [];
      const quickValues = quickFilters.map((button) => button.dataset.historyFilter);
      const validFilters = new Set([...filterValues, ...quickValues]);
      let selectedFilter = new URLSearchParams(window.location.search).get('state') || filter?.value || quickValues[0] || 'all';
      if (!validFilters.has(selectedFilter)) selectedFilter = 'all';
      if (filter && filterValues.includes(selectedFilter)) filter.value = selectedFilter;
      const clear = document.querySelector('#diagnostic-filters [data-filter-clear]');
      const syncFilterControls = () => {
        if (filter && filterValues.includes(selectedFilter)) filter.value = selectedFilter;
        if (clear) clear.hidden = selectedFilter === 'all';
        quickFilters.forEach((button) => {
          const active = button.dataset.historyFilter === selectedFilter;
          button.classList.toggle('active', active);
          button.setAttribute('aria-pressed', active ? 'true' : 'false');
        });
      };
      const refresh = () => {
          if (!count || !body) return;
          const selected = selectedFilter;
          const matching = rows.filter((row) => {
            const matches = selected === 'all'
            || (selected === 'succeeded' && row.dataset.diagnosticResult === 'succeeded')
            || (selected === 'open' && row.dataset.reviewOpen === 'true')
            || (selected === 'resolved' && row.dataset.reviewResolved === 'true')
            || (selected === 'resolved-errors' && row.dataset.reviewResolved === 'true' && row.dataset.diagnosticResult === 'failed')
            || (selected === 'identity-pending' && row.dataset.identityPending === 'true')
            || (selected === 'failed' && row.dataset.diagnosticResult === 'failed')
            || (selected === 'blocked' && row.dataset.diagnosticResult === 'not_started')
            || (selected === 'with-issue' && row.dataset.hasIssue === 'true');
          return matches;
        });
        // No "N records" line (owner decision 2026-10-06); only an empty result says so.
        count.textContent = matching.length ? '' : selected === 'failed' ? 'No failed installations for this model' : 'No records match these filters';
        syncFilterControls();
        if (!pagination || !pageSize) {
          rows.forEach((row) => { row.hidden = !matching.includes(row); });
          return;
        }
        const size = Number(pageSize.value) === 50 ? 50 : 25;
        const pages = Math.max(1, Math.ceil(matching.length / size));
        page = Math.min(Math.max(page, 1), pages);
        const startIndex = (page - 1) * size;
        const visible = new Set(matching.slice(startIndex, startIndex + size));
        rows.forEach((row) => { row.hidden = !visible.has(row); });
        const start = matching.length ? startIndex + 1 : 0;
        const end = matching.length ? Math.min(matching.length, startIndex + size) : 0;
        const summary = pagination.querySelector('span');
        if (summary) summary.textContent = matching.length ? `Showing ${start}–${end} of ${matching.length} · page ${page} of ${pages}` : 'Change the filter to view installation history';
        const previous = pagination.querySelector('[data-history-page="previous"]');
        const next = pagination.querySelector('[data-history-page="next"]');
        if (previous) previous.disabled = page <= 1;
        if (next) next.disabled = page >= pages;
      };
      const close = (dialog) => {
        if (!dialog) return;
        if (typeof dialog.close === 'function') dialog.close(); else dialog.removeAttribute('open');
        lastFocused?.focus();
      };
      const open = (dialog, trigger) => {
        if (!dialog) return;
        lastFocused = trigger;
        dialog.dispatchEvent(new Event('terento-dialog-open'));
        if (typeof dialog.showModal === 'function') dialog.showModal(); else dialog.setAttribute('open', '');
        dialog.querySelector('button, input, select, textarea')?.focus();
      };
      body?.closest('table')?.addEventListener('admin:table-sorted', () => { rows = [...body.querySelectorAll('tr[data-diagnostic-state]')]; page = 1; refresh(); });
      document.querySelector('[data-filter-open-errors]')?.addEventListener('click', () => {
        selectedFilter = 'open';
        refresh();
      });
      quickFilters.forEach((button) => button.addEventListener('click', () => {
        selectedFilter = button.dataset.historyFilter || 'all';
        page = 1;
        refresh();
      }));
      document.querySelector('#diagnostic-filters')?.addEventListener('terento-admin-clear-filters', () => {
        selectedFilter = 'all';
        page = 1;
        const parameters = new URLSearchParams(window.location.search);
        parameters.delete('state');
        const query = parameters.toString();
        history.replaceState(null, '', query ? `${window.location.pathname}?${query}` : window.location.pathname);
        refresh();
      });
      document.querySelectorAll('[data-source-field]').forEach((select) => {
        const renderOriginal = () => {
          const output = select.form?.querySelector('[data-source-original]');
          if (output) output.textContent = select.selectedOptions[0]?.dataset.originalValue || 'Not reported';
        };
        select.addEventListener('change', renderOriginal);
        renderOriginal();
      });
      document.querySelectorAll('form[data-confirm]').forEach((form) => form.addEventListener('submit', (event) => {
        if (!window.confirm(form.dataset.confirm || 'Continue?')) event.preventDefault();
      }));
      document.querySelectorAll('[data-authorization-form]').forEach((form) => form.addEventListener('submit', (event) => {
        const current = form.dataset.currentSupportStatus;
        const next = form.querySelector('select[name="support_status"]')?.value;
        if (current !== next
          && !window.confirm('Change support metadata? This does not change native map-write authorization, compatibility evidence, or installation history.')) {
          event.preventDefault();
        }
      }));
      const pluralInstallations = (count) => `${count} ${count === 1 ? 'installation' : 'installations'}`;
      const refreshIdentityReviewCounts = () => {
        const open = (scope) => [...scope.querySelectorAll('[data-identity-review-item]')].filter((item) => item.dataset.identityConfirmed !== 'true').length;
        document.querySelectorAll('[data-identity-review-group]').forEach((group) => {
          const count = group.querySelector('[data-identity-review-group-count]');
          if (count) count.textContent = pluralInstallations(open(group));
        });
        const remaining = open(document);
        const total = document.querySelector('[data-identity-review-count]');
        if (total) total.textContent = pluralInstallations(remaining);
        const done = document.querySelector('[data-identity-review-done]');
        if (done) done.hidden = remaining > 0;
      };
      const markIdentityConfirmed = (form) => {
        const deviceId = form.querySelector('input[name="canonical_device_model_id"]')?.value || '';
        const label = form.querySelector('[data-identity-selection]')?.textContent.trim() || 'Open model';
        const notice = document.getElementById('identity-review-confirmed')?.content.firstElementChild?.cloneNode(true)
          || Object.assign(document.createElement('p'), {textContent: 'Confirmed'});
        const link = notice.querySelector('[data-identity-confirmed-link]');
        if (link) {
          link.href = `/admin/devices/${encodeURIComponent(deviceId)}?from=installations#installations`;
          link.textContent = label;
        }
        notice.setAttribute('role', 'status');
        form.dataset.identityConfirmed = 'true';
        form.hidden = true;
        form.after(notice);
        const item = form.closest('[data-identity-review-item]');
        if (item && !item.querySelector('[data-identity-form]:not([data-identity-confirmed])')) item.dataset.identityConfirmed = 'true';
        refreshIdentityReviewCounts();
        notice.focus();
      };
      document.querySelectorAll('form.admin-async-action').forEach((form) => form.addEventListener('submit', async (event) => {
        if (event.defaultPrevented) return;
        event.preventDefault();
        if (form.dataset.submitting === 'true') return;
        const formData = new FormData(form);
        // FormData(form) omits the clicked submit button. Identity Review
        // uses named Confirm buttons for the normal and manual paths.
        if (event.submitter?.name) formData.append(event.submitter.name, event.submitter.value);
        const payload = new URLSearchParams();
        formData.forEach((value, key) => payload.append(key, String(value)));
        const controls = [...form.querySelectorAll('button,input,select,textarea')];
        const submit = form.querySelector('button[type="submit"]');
        const originalLabel = submit?.textContent || '';
        let status = form.querySelector('.admin-action-status');
        if (!status) {
          status = document.createElement('p');
          status.className = 'admin-action-status';
          status.setAttribute('role', 'status');
          status.setAttribute('aria-live', 'polite');
          form.appendChild(status);
        }
        form.dataset.submitting = 'true';
        controls.forEach((control) => {
          control.dataset.preSubmitDisabled = control.disabled ? 'true' : 'false';
          control.disabled = true;
        });
        if (submit) submit.textContent = 'Saving…';
        status.textContent = 'Saving…';
        try {
          const response = await fetch(form.action, {
            method: 'POST',
            body: payload,
            credentials: 'same-origin',
            headers: {'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8'},
            redirect: 'follow',
          });
          if (!response.ok) {
            let payload = {};
            try { payload = await response.json(); } catch (_) {}
            const safeIdentityText = (value, fallback = 'Not reported') => {
              if (value === null || value === undefined || value === '') return fallback;
              if (typeof value === 'boolean') return value ? 'Yes' : 'No';
              return String(value).replace(/[\u0000-\u001f\u007f]/g, ' ').slice(0, 200);
            };
            const identityFieldLabels = {
              model: 'Model', caseSizeMm: 'Case size', screenTechnology: 'Display',
              solar: 'Solar', inReach: 'inReach', USB: 'USB mapping',
              XML_PART_NUMBER: 'Product mapping', RETAIL_SKU: 'Retail SKU mapping',
            };
            const identityConflictMessage = (responsePayload) => {
              const conflicts = responsePayload?.details?.conflicts;
              if (!Array.isArray(conflicts) || !conflicts.length) {
                return 'The selected model conflicts with reported information. Confirm manual assignment if this is the intended correction.';
              }
              const lines = conflicts.map((detail, index) => {
                const field = identityFieldLabels[detail?.field] || safeIdentityText(detail?.field, 'Identity field');
                const source = safeIdentityText(detail?.source, 'reported data');
                const reported = safeIdentityText(detail?.reported);
                const selected = safeIdentityText(detail?.selectedModel || detail?.selected, 'selected catalog model');
                const result = detail?.result || {};
                const resultLabel = result.eventId ? `Diagnostic result ${safeIdentityText(result.eventId)}` : `Diagnostic result ${index + 1}`;
                const mappings = Array.isArray(detail?.mappingModels) && detail.mappingModels.length
                  ? ` Approved mapping models for this code: ${detail.mappingModels.map((value) => safeIdentityText(value, 'Unknown model')).join(', ')}.`
                  : '';
                return `${resultLabel}: ${field}: reported ${reported} from ${source}; selected model ${selected}.${mappings}`;
              });
              return `The selected model conflicts with reported information. ${lines.join(' ')} Use manual assignment to confirm it.`;
            };
            const messages = {
              missing_model_selection: 'Choose a specific catalog model before confirming.',
              canonical_device_not_found: 'That catalog model is no longer available. Choose another model.',
              diagnostic_not_found: 'This diagnostic result is no longer available. Reload the review queue.',
              identity_conflict_manual_required: identityConflictMessage(payload),
              invalid_diagnostic_record: 'This diagnostic result identifier is invalid. Reload the review queue.',
            };
            const message = messages[payload.error] || (form.matches('[data-identity-form]')
              ? 'The identity review could not be saved. Your selection is kept; check the current record and retry.'
              : `Save failed (${response.status})`);
            const error = new Error(message);
            error.identityCode = payload.error;
            throw error;
          }
          const signedOut = response.redirected && /^\/admin\/(login|setup)\b/.test(new URL(response.url).pathname);
          if (form.matches('[data-identity-inline]') && !signedOut) {
            // Identity review queue: confirm in place instead of leaving the queue.
            markIdentityConfirmed(form);
          } else if (response.redirected) {
            window.location.assign(response.url);
          } else {
            window.location.reload();
          }
        } catch (error) {
          controls.forEach((control) => {
            control.disabled = control.dataset.preSubmitDisabled === 'true';
            delete control.dataset.preSubmitDisabled;
          });
          if (submit) submit.textContent = originalLabel;
          status.textContent = error?.message || 'Could not save. Check the values and try again.';
          if (form.matches('[data-identity-form]') && error?.identityCode === 'identity_conflict_manual_required') {
            const manual = form.querySelector('[data-manual-confirm]');
            if (manual) manual.hidden = false;
          }
          delete form.dataset.submitting;
          submit?.focus();
        }
      }));
      const copyText = async (value, status) => {
        try {
          await navigator.clipboard.writeText(value);
          if (status) status.textContent = 'Copied';
        } catch (_) {
          if (status) status.textContent = 'Copy failed';
        }
      };
      document.querySelectorAll('[data-github-create]').forEach((link) => {
        const container = link.closest('.github-issue-controls, .github-review');
        const note = container?.querySelector('[data-issue-note]');
        const preview = container?.querySelector('[data-issue-preview-body]');
        const status = container?.querySelector('[data-copy-status]');
        const sanitiseNote = __TERENTO_CLIENT_ISSUE_NOTE_SANITIZER__;
        const sync = () => {
          const noteValue = sanitiseNote(note?.value || '');
          const body = link.dataset.issueBody + (noteValue ? `\n\n## Admin note\n\n${noteValue}` : '');
          const candidate = `https://github.com/VooZ2/terento/issues/new?${new URLSearchParams({title: link.dataset.issueTitle, body})}`;
          const limit = Number(link.dataset.urlLimit || 7000);
          const prefilled = candidate.length <= limit;
          link.href = prefilled ? candidate : 'https://github.com/VooZ2/terento/issues/new';
          link.dataset.prefilled = prefilled ? 'true' : 'false';
          link.textContent = prefilled ? 'Prepare GitHub issue' : 'Copy report to continue';
          if (status) status.textContent = prefilled ? '' : 'Report is too large to prefill; copy it instead.';
          if (preview) preview.value = body;
          return body;
        };
        note?.addEventListener('input', sync);
        link.addEventListener('click', (event) => {
          const body = sync();
          if (link.dataset.prefilled === 'false') {
            event.preventDefault();
            copyText(`${link.dataset.issueTitle}\n\n${body}`, status);
          }
        });
        container?.querySelector('[data-copy-issue-report]')?.addEventListener('click', () => {
          copyText(`${link.dataset.issueTitle}\n\n${sync()}`, status);
        });
        sync();
      });
      document.querySelectorAll('[data-copy-diagnostic-id]').forEach((button) => button.addEventListener('click', () => {
        copyText(button.dataset.copyDiagnosticId, button.parentElement?.querySelector('[data-copy-status]'));
      }));
      document.querySelectorAll('[data-copy-technical-report]').forEach((button) => button.addEventListener('click', () => {
        copyText(button.dataset.report, button.parentElement?.querySelector('[data-copy-status]'));
      }));
      ['input', 'change'].forEach((eventName) => filter?.addEventListener(eventName, () => { selectedFilter = filter.value; page = 1; refresh(); }));
      pageSize?.addEventListener('change', () => { page = 1; refresh(); });
      pagination?.querySelector('[data-history-page="previous"]')?.addEventListener('click', () => { page = Math.max(1, page - 1); refresh(); });
      pagination?.querySelector('[data-history-page="next"]')?.addEventListener('click', () => { page += 1; refresh(); });
      document.querySelectorAll('.diagnostic-review').forEach((button) => button.addEventListener('click', () => open(document.getElementById(button.dataset.dialogId), button)));
      document.querySelectorAll('[data-close-dialog]').forEach((button) => button.addEventListener('click', () => close(button.closest('dialog'))));
      // One Device identity binding for dialog forms and the inline Identity review queue.
      const bindIdentityForm = (form, dialog) => {
        const wrap = form.querySelector('[data-canonical-device-wrap]');
        const search = form.querySelector('[data-identity-search]');
        const canonical = form.querySelector('input[name="canonical_device_model_id"]');
        const selection = form.querySelector('[data-identity-selection]');
        const results = form.querySelector('[data-identity-results]');
        const edit = form.querySelector('[data-identity-edit]');
        const confirm = form.querySelector('[data-identity-confirm]');
        const pageCatalog = results?.dataset.identityCatalog === 'page';
        const optionSource = pageCatalog
          ? [...(document.getElementById('identity-picker-catalog')?.content.querySelectorAll('[data-identity-device-id]') || [])]
          : (results ? [...results.querySelectorAll('[data-identity-device-id]')] : []);
        const choices = optionSource.map((option) => ({
          id: option.dataset.identityDeviceId,
          label: option.dataset.identityDeviceLabel || option.textContent.trim(),
        }));
        const normalize = value => value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
        const clearStaleSelectionState = () => {
          form.querySelector('[data-identity-conflict]')?.setAttribute('hidden', '');
          form.querySelector('[data-manual-confirm]')?.setAttribute('hidden', '');
        };
        const sync = () => {
          const hasSelection = Boolean(canonical?.value);
          if (confirm) confirm.disabled = !hasSelection;
          if (selection) selection.textContent = hasSelection
            ? (search?.value || canonical.value)
            : (selection.dataset.identityEmpty || 'No model selected');
          if (search) search.setAttribute('aria-expanded', wrap?.hidden ? 'false' : 'true');
        };
        const render = (query = '') => {
          if (!results) return [];
          const matches = choices.filter(choice => normalize(choice.label).includes(normalize(query.trim())));
          results.replaceChildren(...matches.map(choice => {
            const button = document.createElement('button');
            button.type = 'button';
            button.className = 'identity-picker-option';
            button.setAttribute('role', 'option');
            button.dataset.identityDeviceId = choice.id;
            button.dataset.identityDeviceLabel = choice.label;
            button.textContent = choice.label;
            button.addEventListener('click', () => {
              clearStaleSelectionState();
              if (canonical) canonical.value = choice.id;
              if (search) search.value = choice.label;
              if (results) results.hidden = true;
              if (edit) { edit.hidden = false; edit.textContent = 'Edit'; }
              const term = form.querySelector('.identity-selection dt');
              if (term) term.textContent = 'Selected model';
              sync();
              search?.focus();
            });
            return button;
          }));
          results.hidden = false;
          if (!matches.length) {
            const empty = document.createElement('p');
            empty.className = 'identity-picker-empty';
            empty.setAttribute('role', 'status');
            empty.textContent = 'No catalog models match this search.';
            results.append(empty);
          }
          return matches;
        };
        edit?.addEventListener('click', () => {
          clearStaleSelectionState();
          if (wrap) wrap.hidden = false;
          if (results) results.hidden = false;
          render('');
          search?.focus();
          sync();
        });
        search?.addEventListener('input', () => {
          clearStaleSelectionState();
          const selected = choices.find(choice => choice.id === canonical?.value);
          if (!selected || normalize(search.value) !== normalize(selected.label)) {
            if (canonical) canonical.value = '';
            form.querySelector('[data-manual-confirm]')?.setAttribute('hidden', '');
          }
          if (wrap) wrap.hidden = false;
          render(search.value);
          sync();
        });
        search?.addEventListener('keydown', (event) => {
          const visible = results ? [...results.querySelectorAll('[data-identity-device-id]')] : [];
          if (event.key === 'ArrowDown' && visible.length) { event.preventDefault(); visible[0].focus(); }
          if (event.key === 'ArrowUp' && visible.length) { event.preventDefault(); visible[visible.length - 1].focus(); }
          if (event.key === 'Escape' && wrap) { wrap.hidden = Boolean(canonical?.value); if (results) results.hidden = true; sync(); }
        });
        // Bind the initial choices too, before any search input or Edit action.
        // A page-level catalog is cloned only when its dialog first opens; an
        // inline (queue) page-catalog picker renders when Edit / Pick model opens it.
        if (pageCatalog && dialog) {
          let rendered = false;
          dialog.addEventListener('terento-dialog-open', () => { if (!rendered) { rendered = true; render(search?.value || ''); if (wrap?.hidden && results) results.hidden = true; } });
        } else if (!pageCatalog) {
          render('');
        }
        sync();
      };
      dialogs.forEach((dialog) => {
        dialog.addEventListener('click', (event) => { if (event.target === dialog) close(dialog); });
        dialog.addEventListener('cancel', () => window.setTimeout(() => lastFocused?.focus(), 0));
        dialog.addEventListener('keydown', (event) => {
          if (event.key === 'Escape') {
            event.preventDefault();
            close(dialog);
            return;
          }
          if (event.key !== 'Tab') return;
          const focusable = [...dialog.querySelectorAll('button,select,input,textarea,a,summary')]
            .filter((element) => !element.disabled && element.offsetParent !== null);
          if (!focusable.length) return;
          const first = focusable[0];
          const last = focusable[focusable.length - 1];
          if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
          else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
        });
        dialog.querySelectorAll('[data-identity-form]').forEach((form) => bindIdentityForm(form, dialog));
      });
      document.querySelectorAll('[data-identity-form][data-identity-inline]').forEach((form) => bindIdentityForm(form, null));
      // A Details link may target one diagnostic dialog by its id.
      const linkedDialog = window.location.hash ? document.getElementById(decodeURIComponent(window.location.hash.slice(1))) : null;
      if (linkedDialog?.matches('dialog.diagnostic-detail-dialog')) open(linkedDialog, null);
      refresh();
    })();"""
    return script.replace(
        "__TERENTO_CLIENT_ISSUE_NOTE_SANITIZER__",
        _client_issue_note_sanitizer_script(),
    )


def _admin_timezone_script() -> str:
    return r"""(() => {
      const topbar = document.querySelector('.admin-topbar');
      const select = document.querySelector('#admin-timezone');
      const filter = document.querySelector('.device-filter-bar');
      const updateLayoutMetrics = () => {
        if (topbar) document.documentElement.style.setProperty('--admin-topbar-height', `${Math.ceil(topbar.getBoundingClientRect().height)}px`);
        if (filter) document.documentElement.style.setProperty('--device-filter-height', `${Math.ceil(filter.getBoundingClientRect().height)}px`);
      };
      updateLayoutMetrics();
      if (typeof ResizeObserver === 'function') {
        const observer = new ResizeObserver(updateLayoutMetrics);
        if (topbar) observer.observe(topbar);
        if (filter) observer.observe(filter);
      }
      window.addEventListener('resize', updateLayoutMetrics, { passive: true });
      if (!select) return;
      const storageKey = 'terento.admin.timeZone';
      const browserTimeZone = (() => {
        try { return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'; } catch (_) { return 'UTC'; }
      })();
      const isValidTimeZone = (value) => {
        try {
          new Intl.DateTimeFormat('en-GB', { timeZone: value }).format();
          return true;
        } catch (_) {
          return false;
        }
      };
      const commonTimeZones = [
        'Europe/Vilnius', 'Europe/Riga', 'Europe/Warsaw', 'Europe/Berlin',
        'Europe/London', 'America/New_York', 'America/Los_Angeles',
        'America/Toronto', 'Asia/Tokyo', 'Asia/Singapore', 'Australia/Sydney'
      ];
      const timeZones = ['browser', 'UTC', browserTimeZone, ...commonTimeZones]
        .filter((value, index, values) => values.indexOf(value) === index)
        .filter((value) => value === 'browser' || isValidTimeZone(value));
      const readStoredTimeZone = () => {
        try { return localStorage.getItem(storageKey) || 'browser'; } catch (_) { return 'browser'; }
      };
      const storedTimeZone = readStoredTimeZone();
      const selectedTimeZone = timeZones.includes(storedTimeZone) ? storedTimeZone : 'browser';
      const activeTimeZone = () => select.value === 'browser' ? browserTimeZone : select.value;
      const format = (value) => {
        if (!value) return '—';
        const normalizedValue = typeof value === 'string'
          ? value.trim().replace(/^(\d{4}-\d{2}-\d{2})(\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?)$/, '$1T$2')
          : value;
        const date = new Date(normalizedValue);
        if (Number.isNaN(date.getTime())) return String(value);
        try {
          const parts = Object.fromEntries(
            new Intl.DateTimeFormat('en-CA', {
              year: 'numeric', month: '2-digit', day: '2-digit',
              hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
              timeZone: activeTimeZone()
            }).formatToParts(date)
              .filter((part) => part.type !== 'literal')
              .map((part) => [part.type, part.value])
          );
          return `${parts.year}-${parts.month}-${parts.day} ${parts.hour}:${parts.minute}`;
        } catch (_) {
          return date.toISOString().slice(0, 16).replace('T', ' ');
        }
      };
      const render = () => {
        const zone = activeTimeZone();
        document.querySelectorAll('[data-admin-timestamp]').forEach((element) => {
          element.textContent = format(element.dataset.adminTimestamp);
          element.title = `${element.textContent} · ${zone}`;
          if (element.closest('.download-timeline')) element.setAttribute('aria-label', element.title);
        });
        document.querySelectorAll('.download-timeline').forEach((timeline) => {
          const times = [...timeline.querySelectorAll('[data-admin-timestamp]')];
          const dates = new Set(times.map(el => format(el.dataset.adminTimestamp).slice(0, 10)));
          if (dates.size === 1) times.forEach(el => { el.setAttribute('aria-label', el.title); el.textContent = format(el.dataset.adminTimestamp).slice(11); });
        });
        select.title = select.value === 'browser' ? `Automatic browser time zone: ${browserTimeZone}` : zone;
        select.setAttribute('aria-label', `Time zone: ${select.value === 'browser' ? `Automatic (${browserTimeZone})` : select.value}`);
      };
      select.replaceChildren(...timeZones.map((value) => {
        const option = document.createElement('option');
        option.value = value;
        option.textContent = value === 'browser' ? `Auto · ${browserTimeZone}` : value;
        return option;
      }));
      select.value = selectedTimeZone;
      window.TerentoAdminTime = { format, render, timeZone: activeTimeZone };
      select.addEventListener('change', () => {
        try { localStorage.setItem(storageKey, select.value); } catch (_) { /* local preference is optional */ }
        render();
        window.dispatchEvent(new Event('terento-admin-timezone-change'));
      });
      render();
      window.dispatchEvent(new Event('terento-admin-timezone-ready'));
    })();"""


ADMIN_STYLES = ADMIN_BRAND_TOKENS_CSS + """
:root{--admin-control-height:40px;--admin-control-radius:var(--radius-control);--admin-control-padding-x:10px;--admin-control-font-size:13px;--admin-topbar-height:68px;--max-width:1440px}
*{box-sizing:border-box}
[hidden]{display:none!important}
html{min-width:0}
body{margin:0;min-width:0;background:var(--off-white);color:var(--graphite);font-family:var(--font-ui);font-size:15px;line-height:1.5;-webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility}
a{color:inherit}
a:focus-visible,button:focus-visible,input:focus-visible,select:focus-visible,textarea:focus-visible{outline:var(--admin-focus-ring);outline-offset:3px}
button,input,select,textarea{font-family:var(--font-ui);font-size:var(--admin-control-font-size);line-height:1.3}
input:not([type="hidden"]):not([type="checkbox"]):not([type="radio"]),select,textarea{min-height:var(--admin-control-height);padding:8px var(--admin-control-padding-x);border:1px solid var(--border);border-radius:var(--admin-control-radius);background:var(--surface);color:var(--graphite);font-weight:500}
select{padding-right:28px;color-scheme:light}
textarea{min-height:78px;resize:vertical}
input::placeholder,textarea::placeholder{color:var(--admin-placeholder);opacity:1;font-weight:400}
input:disabled,select:disabled,textarea:disabled,button:disabled{cursor:not-allowed;background:var(--surface-muted);border-color:color-mix(in srgb,var(--border) 78%,var(--surface-muted));color:var(--secondary);opacity:1}
button{cursor:pointer}
.admin-action-dialog button:not(.secondary-button),.auth-card button:not(.link-button),.copy-button,.model-administration button[type="submit"],.identity-mapping-review button[type="submit"]{min-height:var(--admin-control-height);padding:8px 12px;border:0;border-radius:var(--admin-control-radius);background:var(--interactive);color:var(--interactive-primary-text);font-weight:700}
.admin-action-dialog button:not(.secondary-button):hover,.auth-card button:not(.link-button):hover,.copy-button:hover,.model-administration button[type="submit"]:hover{background:var(--interactive-hover)}
.admin-topbar{position:sticky;top:0;z-index:30;border-bottom:1px solid color-mix(in srgb,var(--border) 78%,transparent);background:var(--off-white);box-shadow:0 1px 0 color-mix(in srgb,var(--graphite) 4%,transparent)}
.admin-topbar-inner{width:min(calc(100% - 48px),var(--max-width));min-height:68px;margin:0 auto;display:grid;grid-template-columns:minmax(300px,1fr) max-content minmax(335px,1fr);align-items:center;gap:16px}
.admin-header-zone{min-width:0}
.admin-header-left{display:flex;align-items:center;justify-self:start;gap:9px}
.admin-brand{display:inline-flex;align-items:center;gap:10px;text-decoration:none;color:var(--graphite);font-family:var(--font-brand);font-size:20px;font-weight:700;letter-spacing:-.02em}
.admin-brand img{width:25px;height:29px;object-fit:contain}
.admin-badge{display:inline-flex;align-items:center;min-height:22px;padding:3px 8px;border:1px solid color-mix(in srgb,var(--sky) 48%,var(--border));border-radius:999px;color:var(--interactive);font-family:var(--font-ui);font-size:11px;font-weight:700;letter-spacing:.04em;text-transform:uppercase}
.admin-section-nav{display:flex;align-items:center;justify-content:center;gap:4px;justify-self:center;color:var(--secondary);font-size:13px;font-weight:650}
.admin-section-nav a,.admin-nav a,.link-button{display:inline-flex;align-items:center;min-height:32px;padding:6px 8px;border:1px solid transparent;border-radius:var(--admin-control-radius);background:none;text-decoration:none;color:var(--secondary);font-weight:650;transition:background-color .15s ease,border-color .15s ease,color .15s ease}
.admin-section-nav a:hover,.admin-nav a:hover,.link-button:hover,.admin-section-nav a:active,.admin-nav a:active,.link-button:active{background:color-mix(in srgb,var(--sky) 12%,transparent);color:var(--interactive)}
.admin-section-nav a.active{background:color-mix(in srgb,var(--sky) 13%,var(--off-white));border-color:color-mix(in srgb,var(--sky) 28%,var(--border));color:var(--interactive);box-shadow:none}
.admin-nav{display:flex;align-items:center;justify-self:end;min-width:0;gap:8px;color:var(--secondary);font-size:13px;white-space:nowrap}
.admin-nav form{display:flex;align-items:center;margin:0}
.admin-user{padding:6px 0;color:var(--graphite);font-weight:650;white-space:nowrap}
.timezone-control{display:flex;align-items:center;gap:7px;color:var(--secondary);font-size:11px;font-weight:650;white-space:nowrap}
.timezone-control select{width:clamp(150px,17vw,205px);min-height:var(--admin-control-height);padding:8px var(--admin-control-padding-x);border:1px solid var(--border);border-radius:var(--admin-control-radius);background:var(--surface);color:var(--graphite);font-size:var(--admin-control-font-size)}
.admin-website-link{white-space:nowrap}
.admin-header-left .admin-website-link{min-height:30px;padding:5px 7px;color:var(--secondary);font-size:12px;font-weight:650;text-decoration:none}
.dashboard{width:min(calc(100% - 48px),var(--max-width));margin:0 auto;padding:40px 0 64px}
.heading-row{display:flex;align-items:flex-end;justify-content:space-between;gap:32px;margin-bottom:28px}
h1,h2{margin:0;font-family:var(--font-ui);letter-spacing:-.015em;text-wrap:balance}
h1{font-size:clamp(32px,3.5vw,44px);line-height:1.06}
h2{font-size:22px;line-height:1.15}
.evidence-section{margin-top:2px}
.section-heading{display:flex;align-items:end;justify-content:space-between;gap:20px;margin-bottom:14px}
.table-help,.results-count{margin:0;color:var(--secondary);font-size:12px}
#diagnostic-results-count:empty{display:none}
.filter-bar{display:flex;align-items:stretch;gap:8px;flex-wrap:wrap;margin:0 0 10px;padding:8px;background:var(--surface-muted);border:1px solid var(--border);border-radius:var(--radius-card)}
.filter-bar label{display:flex;align-items:stretch;margin:0}
.filter-bar input,.filter-bar select{height:var(--admin-control-height);min-height:var(--admin-control-height);padding:8px var(--admin-control-padding-x);border-radius:var(--admin-control-radius);font:600 var(--admin-control-font-size)/1.2 var(--font-ui)}
.filter-bar .filter-search{flex:1 1 310px}
.filter-bar input{width:100%}
.filter-bar select{min-width:150px}
.filter-bar input::placeholder{color:var(--admin-placeholder);font-weight:500}
.filter-bar .results-count{align-self:center;margin:0 4px 0 auto;white-space:nowrap}
.filter-bar .filter-clear{align-self:center;flex:0 0 auto;white-space:nowrap}
.table-wrap{max-height:none;overflow-x:auto;overflow-y:visible;background:var(--surface);border:1px solid var(--border);border-radius:var(--radius-card)}
table{border-collapse:collapse;width:100%;min-width:1060px}
th,td{padding:10px 14px;border-bottom:1px solid color-mix(in srgb,var(--border) 78%,transparent);text-align:left;white-space:nowrap;vertical-align:middle}
thead th{background:var(--surface);box-shadow:0 1px 0 var(--border);color:var(--secondary);font-size:11px;font-weight:750;letter-spacing:.07em;text-transform:uppercase}
tbody tr:last-child td{border-bottom:0}
tbody tr[hidden]{display:none}
td:first-child{font-weight:650}
td.column-number,td.column-date,.numeric{font-variant-numeric:tabular-nums}
.muted-value{color:var(--secondary)}
.error-count{display:inline-flex;align-items:center;justify-content:center;min-width:24px;min-height:24px;padding:2px 7px;border:1px solid color-mix(in srgb,var(--danger) 35%,var(--border));border-radius:999px;color:var(--danger);font-weight:700}
.evidence-table-wrap table{min-width:760px}.evidence-model-row{cursor:pointer}.evidence-model-row:hover{background:color-mix(in srgb,var(--surface-muted) 52%,var(--surface))}.evidence-model-row:focus-visible{outline:var(--admin-focus-ring);outline-offset:-3px}.evidence-model-row td.column-number{font-variant-numeric:tabular-nums}.error-count{text-decoration:none}.identity-pending-indicator{display:inline-flex;align-items:center;margin-left:6px;padding:3px 6px;border:1px solid var(--border);border-radius:999px;color:var(--secondary);font-size:10px;font-weight:700;white-space:nowrap}.back-link{margin:0 0 20px;color:var(--interactive);font-size:13px;font-weight:700}.back-link a{text-underline-offset:3px}.diagnostic-model-metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin:0 0 30px}.diagnostic-model-metrics article{min-height:82px;padding:14px 16px;background:var(--surface);border:1px solid var(--border);border-radius:var(--radius-card)}.diagnostic-model-metrics span{display:block;color:var(--secondary);font-size:12px;font-weight:650}.diagnostic-model-metrics strong{display:block;margin-top:4px;font-family:var(--font-brand);font-size:25px;line-height:1.15}
.diagnostic-model-metrics .admin-metric-value{margin-top:0;font:600 24px/32px var(--font-ui)}.diagnostic-filter-bar{justify-content:flex-start}.diagnostic-list-wrap{max-height:min(70vh,720px)}.diagnostic-list-table{min-width:920px}.diagnostic-list-table th,.diagnostic-list-table td{white-space:normal;overflow-wrap:anywhere}.diagnostic-list-table td:first-child{white-space:nowrap}.diagnostic-list-table tbody tr:hover{background:color-mix(in srgb,var(--surface-muted) 52%,var(--surface))}.diagnostic-list-table .github-issue,.github-current .github-issue{color:var(--interactive);font-weight:700;white-space:nowrap}.diagnostic-detail-dialog{width:min(1160px,calc(100% - 32px));max-height:min(900px,calc(100% - 32px));padding:0;border:0;border-radius:var(--radius-card);background:var(--surface);color:var(--graphite);box-shadow:0 24px 80px color-mix(in srgb,var(--graphite) 24%,transparent)}.diagnostic-detail-dialog::backdrop{background:color-mix(in srgb,var(--graphite) 34%,transparent)}.diagnostic-detail-inner{max-height:min(900px,calc(100vh - 32px));padding:24px;overflow:auto}.diagnostic-detail-summary{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:0 24px;margin:0;border-top:1px solid var(--border)}.diagnostic-detail-summary div{display:grid;grid-template-columns:minmax(95px,.8fr) minmax(0,1.2fr);gap:12px;padding:9px 0;border-bottom:1px solid color-mix(in srgb,var(--border) 72%,transparent)}.diagnostic-detail-summary dt{color:var(--secondary);font-size:12px}.diagnostic-detail-summary dd{margin:0;overflow-wrap:anywhere;font-size:13px;font-weight:650;text-align:right}.diagnostic-actions-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;margin-top:22px}.diagnostic-action-form{min-width:0;padding:14px;background:var(--surface-muted);border-radius:var(--radius-control)}.diagnostic-action-form h4{margin:0 0 10px;font-size:13px}.diagnostic-action-form label{display:block;margin:10px 0;color:var(--graphite);font-size:12px;font-weight:650}.diagnostic-action-form input,.diagnostic-action-form select,.diagnostic-action-form textarea{display:block;width:100%;margin-top:5px;min-height:36px;padding:7px 9px;border:1px solid var(--border);border-radius:var(--radius-control);background:var(--surface);color:var(--graphite);font-size:12px}.diagnostic-action-form textarea{resize:vertical}.diagnostic-action-form button{margin-top:6px}.identity-summary{font-size:14px;line-height:1.5}.identity-summary h4{font:600 22px/1.3 var(--font-ui);margin:8px 0;text-wrap:balance}.identity-review-form input,.identity-review-form select,.identity-review-form button{min-height:40px}.identity-selection{margin:8px 0;color:var(--secondary);font-size:11px}.identity-selection code{color:var(--graphite);font-family:var(--font-mono);overflow-wrap:anywhere}.github-review{overflow-wrap:anywhere}.github-current{margin:0 0 8px;font-size:13px}.github-actions{margin:0 0 4px}.github-link-form{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:end;gap:10px}.github-link-form label{margin:0}.github-link-form button{white-space:nowrap}.github-remove-form{display:inline-block;margin:8px 0 0}
.diagnostic-action-form input,.diagnostic-action-form select,.diagnostic-action-form textarea{min-height:var(--admin-control-height);padding:8px var(--admin-control-padding-x);border-radius:var(--admin-control-radius)}.github-issue-controls{margin-top:12px}
.diagnostic-id{font-size:11px!important;color:var(--secondary)!important}.diagnostic-id code{overflow-wrap:anywhere;font-size:10px;color:var(--secondary)}.diagnostic-technical-details{margin:10px 0 0;padding:9px 11px;background:var(--surface-muted);border-radius:var(--radius-control)}.diagnostic-technical-details>summary{cursor:pointer;color:var(--secondary);font-size:12px;font-weight:700}.diagnostic-technical-details dl{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:0 18px;margin:10px 0 0}.diagnostic-technical-details dl div{min-width:0;display:flex;justify-content:space-between;gap:12px;padding:5px 0;border-top:1px solid color-mix(in srgb,var(--border) 72%,transparent)}.diagnostic-technical-details dt{min-width:0;overflow-wrap:anywhere;color:var(--secondary);font-size:11px}.diagnostic-technical-details dd{min-width:0;margin:0;text-align:right;font:500 11px var(--font-mono);overflow-wrap:anywhere}
.empty{margin:0 0 20px;padding:16px 18px;background:var(--surface);border:1px solid var(--border);border-radius:var(--radius-card);color:var(--secondary)}
.auth-card{width:min(480px,calc(100% - 48px));margin:8vh auto;padding:32px;background:var(--surface);border:1px solid var(--border);border-radius:var(--radius-card);box-shadow:0 16px 44px color-mix(in srgb,var(--graphite) 8%,transparent)}
.auth-card .admin-brand{margin-bottom:28px}
.auth-card h1{font-size:34px}
.auth-card form{margin-top:24px}
.auth-card label{display:block;margin:16px 0;color:var(--graphite);font-weight:650}
.auth-card label small{color:var(--secondary);font-weight:400}
.auth-card input{display:block;width:100%;margin-top:7px}
.auth-card button:not(.link-button){margin-top:8px}
.error,.success{margin:16px 0;padding:11px 13px;border-radius:var(--radius-control);font-size:13px}
.error{background:var(--error-surface);color:var(--error-text)}
.success{background:var(--success-bg);color:var(--success-text)}
.account{margin-top:48px}
.campaign-card .admin-card-head{margin-bottom:16px}
.campaign-local{margin:0 0 0 auto;color:var(--secondary);font-size:var(--admin-type-helper-size);line-height:var(--admin-type-helper-line)}
.campaign-note{display:flex;align-items:flex-start;gap:10px;margin:0 0 20px;padding:12px 14px;border:1px solid var(--status-supported-border);border-radius:var(--radius-control);background:var(--status-supported-surface);color:var(--graphite);font-size:13px;line-height:20px}
.campaign-note>.admin-icon{flex:0 0 auto;width:16px;height:16px;margin-top:2px;color:var(--status-supported-text)}
.campaign-note-title{margin:0 0 2px;font-weight:650}
.campaign-note ul{margin:0;padding-left:18px}
.campaign-form{display:grid;gap:20px;margin:0}
.campaign-row{display:grid;grid-template-columns:minmax(160px,220px) minmax(0,1fr);gap:8px 24px;align-items:start;min-width:0}
.campaign-row-label{min-width:0;padding-top:12px}
.campaign-row-control{display:grid;gap:6px;min-width:0}
.campaign-label{display:block;margin:0;color:var(--graphite);font-size:var(--admin-type-control-size);font-weight:650;line-height:20px}
.campaign-optional{color:var(--secondary);font-weight:500}
.campaign-hint{margin:0;color:var(--secondary);font-size:var(--admin-type-helper-size);line-height:var(--admin-type-helper-line)}
.campaign-card .campaign-choice{width:fit-content;max-width:100%;margin:0}
.campaign-card .campaign-choice .quick-filter-group{flex-wrap:wrap;overflow:visible}
.campaign-reveal{display:grid;gap:12px;margin-top:6px;padding:2px 0 2px 14px;border-left:2px solid var(--border)}
.campaign-subfield{display:grid;gap:6px;min-width:0}
.campaign-sublabel{display:block;color:var(--graphite);font-size:12px;font-weight:650;line-height:18px}
.campaign-form input[type='text'],.campaign-url{width:100%;max-width:480px;height:var(--admin-control-height);min-height:var(--admin-control-height);box-sizing:border-box;padding:8px var(--admin-control-padding-x);border:1px solid var(--border);border-radius:var(--admin-control-radius);background:var(--surface);color:var(--graphite);font-family:var(--font-ui);font-size:var(--admin-control-font-size);font-weight:500;line-height:1.3}
.campaign-normalized strong{font-weight:650;color:var(--graphite)}
.campaign-card .campaign-more{margin:0}
.campaign-card .campaign-more.admin-disclosure>summary{width:fit-content;padding-left:18px}
.campaign-card .campaign-more.admin-disclosure>summary::before{left:0}
.campaign-card .campaign-more.admin-disclosure>.disclosure-body{margin:8px 0 0;padding:0}
.campaign-result{display:grid;gap:8px;margin-top:20px;padding-top:20px;border-top:1px solid var(--border)}
.campaign-url-row{display:flex;align-items:flex-start;gap:8px;min-width:0}
.campaign-url-row .campaign-url{display:block;flex:1 1 auto;max-width:none;height:auto;resize:none;overflow:auto;background:var(--surface-muted);font-family:var(--font-mono);font-size:13px;font-weight:400;line-height:22px;white-space:pre-wrap;word-break:break-all}
.campaign-url-row .campaign-url::placeholder{font-family:var(--font-ui)}
.campaign-url-row .copy-button{flex:0 0 auto;display:inline-flex;align-items:center;justify-content:center;padding:8px 16px;white-space:nowrap}
.copy-button:disabled{cursor:not-allowed;opacity:.45}
.campaign-summary{margin:0;color:var(--secondary);font-size:13px;line-height:20px;overflow-wrap:anywhere}
.campaign-summary strong{color:var(--graphite);font-weight:650}
.campaign-message{display:flex;align-items:center;gap:6px;min-height:20px;margin:0;font-size:13px;font-weight:600;line-height:20px}
.campaign-message[data-state='']{min-height:0}
.campaign-message-icon{display:none}
.campaign-message-icon .admin-icon{width:14px;height:14px}
.campaign-message[data-state='incomplete']{color:var(--status-warning-text)}
.campaign-message[data-state='copied']{color:var(--status-success-text)}
.campaign-message[data-state='failed']{color:var(--status-error-text)}
.campaign-message[data-state='incomplete'] [data-icon='incomplete'],.campaign-message[data-state='copied'] [data-icon='copied'],.campaign-message[data-state='failed'] [data-icon='failed']{display:inline-flex}
@media(max-width:760px){
  .campaign-row{grid-template-columns:minmax(0,1fr);gap:6px}
  .campaign-row-label{padding-top:0}
  .campaign-card .campaign-choice{width:auto}
  .campaign-form input[type='text']{max-width:none}
  .campaign-url-row{flex-direction:column}
  .campaign-url-row .copy-button{width:100%;min-height:44px}
  .campaign-local{flex-basis:100%;margin:0}
}
.optional-label{color:var(--secondary);font-size:10px;font-weight:700;letter-spacing:.06em;text-transform:uppercase}
.info-control{display:inline-flex;align-items:center;justify-content:center;width:19px;height:19px;min-height:19px;padding:0;border:0;border-radius:50%;background:transparent;color:var(--interactive);font-size:17px;line-height:1}
.info-control:hover{border-color:var(--interactive);background:var(--success-bg)}
.copy-status{min-width:54px;color:var(--interactive);font-size:12px;font-weight:700}
.admin-action-status{margin:8px 0 0;color:var(--interactive);font-size:12px;font-weight:700}.admin-async-action [disabled]{cursor:wait;opacity:.68}
.provider-action-bar button{display:inline-flex;align-items:center;justify-content:center;min-height:var(--admin-control-height);padding:8px 12px;border:0;border-radius:var(--admin-control-radius);background:var(--interactive);color:var(--interactive-primary-text);font-weight:700;text-decoration:none}.provider-action-bar button:hover{background:var(--interactive-hover)}.provider-action-bar button.secondary-button{border:1px solid var(--border);background:var(--surface);color:var(--graphite)}.provider-action-bar button.secondary-button:hover{border-color:var(--interactive);background:var(--surface-muted);color:var(--interactive)}
.provider-table-wrap table{min-width:980px}.provider-name-link{display:flex;flex-direction:column;gap:2px;text-decoration:none}.provider-name-link:hover strong{text-decoration:underline}.provider-name-link small{color:var(--secondary);font:500 11px var(--font-mono)}.provider-table-wrap code{font:500 11px var(--font-mono);overflow-wrap:anywhere}.provider-error{display:block;max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--danger);font-size:12px}.provider-table-wrap .numeric{text-align:right;font-variant-numeric:tabular-nums}.provider-action-bar{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin:0 0 20px;padding:12px;background:var(--surface);border:1px solid var(--border);border-radius:var(--radius-card)}.provider-action-bar .admin-action-status{flex:1 1 180px;margin:0}.provider-activation-note{flex:1 1 100%;margin:2px 0 0;padding:9px 11px;border:1px solid var(--status-tested-border);border-radius:var(--radius-control);background:var(--status-tested-surface);color:var(--status-tested-text);font-size:12px;line-height:1.45}.provider-heading-status{display:flex;align-items:center;gap:7px;flex-wrap:wrap}.provider-metrics{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:10px;margin:0 0 24px}.provider-metrics article{min-width:0;min-height:84px;padding:14px 16px;background:var(--surface);border:1px solid var(--border);border-radius:var(--radius-card)}.provider-metrics article>span{display:block;color:var(--secondary);font-size:12px;font-weight:650}.provider-metrics article>strong{display:block;margin-top:6px;font-family:var(--font-brand);font-size:20px;line-height:1.15}.provider-metrics article>strong .admin-timestamp{font-size:15px}.provider-card{margin-top:24px;padding:22px 24px;background:var(--surface);border:1px solid var(--border);border-radius:var(--radius-card)}.provider-card .section-heading{margin-bottom:16px}.provider-card .section-heading h2{font-size:20px}.provider-information-list{margin:0;border-top:1px solid var(--border)}.provider-information-list div{display:grid;grid-template-columns:minmax(150px,.45fr) minmax(0,1.55fr);gap:18px;padding:10px 0;border-bottom:1px solid color-mix(in srgb,var(--border) 72%,transparent)}.provider-information-list dt{color:var(--secondary);font-size:12px}.provider-information-list dd{margin:0;overflow-wrap:anywhere;font-size:13px;font-weight:650;text-align:right}.provider-information-list a,.provider-url-cell a{color:var(--interactive);text-underline-offset:3px}.provider-package-broken{background:color-mix(in srgb,var(--error-surface) 35%,var(--surface))}.provider-package-broken small{display:block;margin-top:3px;color:var(--danger);font-size:10px}.provider-component-list{display:flex;gap:5px;flex-wrap:wrap}.provider-component{display:inline-flex;align-items:center;gap:4px;white-space:nowrap}.provider-dashboard-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:24px}.provider-dashboard-grid .provider-card{min-width:0}.map-statistics-filter-bar label{flex:0 1 auto}.map-statistics-filter-bar input,.map-statistics-filter-bar select{min-width:130px}.map-statistics-filter-bar .results-count{flex:1 1 120px}
:is(.device-summary-sync,.provider-summary-sync) strong{color:var(--graphite);font-weight:750}
:is(.device-summary-sync,.provider-summary-sync){text-align:right;white-space:nowrap}
.test-data-page{padding-top:30px}.test-data-card{margin-top:0}.test-data-metrics{grid-template-columns:repeat(3,minmax(0,1fr));margin:0 0 20px}.test-data-release-labels{margin:0;color:var(--secondary);font-size:12px;line-height:18px}.test-data-release-labels code{color:var(--graphite);font:500 11px var(--font-mono);overflow-wrap:anywhere}.test-data-danger-zone{display:grid;grid-template-columns:minmax(0,1fr) minmax(320px,.95fr);align-items:start;gap:24px;margin-top:22px;padding-top:20px;border-top:1px solid var(--border)}.test-data-danger-zone h3{margin:0;font-size:var(--admin-type-subsection-size);line-height:var(--admin-type-subsection-line)}.test-data-danger-zone .table-help{max-width:460px;margin:6px 0 0}.admin-danger-form{display:grid;gap:10px;padding:14px;background:var(--error-surface);border:1px solid var(--status-error-border);border-radius:var(--radius-card)}.admin-danger-form label{display:grid;gap:6px;color:var(--graphite);font-size:12px;font-weight:650}.admin-danger-form code{font:500 11px var(--font-mono)}.admin-danger-form input{width:100%;min-height:var(--admin-control-height);box-sizing:border-box;padding:8px var(--admin-control-padding-x);border:1px solid var(--status-error-border);border-radius:var(--admin-control-radius);background:var(--surface);color:var(--graphite);font:500 var(--admin-control-font-size)/1.2 var(--font-mono)}.admin-danger-form input:focus{border-color:var(--danger);outline:3px solid var(--danger);outline-offset:1px}.danger-button{min-height:var(--admin-control-height);padding:8px 12px;border:0;border-radius:var(--admin-control-radius);background:var(--danger);color:var(--interactive-primary-text);font:600 var(--admin-type-button-size)/var(--admin-type-button-line) var(--font-ui)}.danger-button:hover{background:color-mix(in srgb,var(--danger) 86%,var(--graphite))}
@media(max-width:760px){.test-data-danger-zone{grid-template-columns:1fr;gap:16px}}
.evidence-table-wrap table{table-layout:fixed}.evidence-table-wrap .evidence-column-model{width:24%}.evidence-table-wrap .evidence-column-variant{width:14%}.evidence-table-wrap .evidence-column-status{width:12%}.evidence-table-wrap .evidence-column-attempts{width:7%}.evidence-table-wrap .evidence-column-successful{width:9%}.evidence-table-wrap .evidence-column-failed{width:7%}.evidence-table-wrap .evidence-column-open-errors{width:11%}.evidence-table-wrap .evidence-column-last-success{width:16%}
/* Same filter bar as Installations (owner decision 2026-10-06); it stays sticky above the table. */
.device-filter-bar{position:sticky;top:var(--admin-topbar-height);z-index:22;align-items:stretch}
.device-table-wrap{overflow:visible}
.device-sticky-header{display:none}
.device-table-wrap table,.device-sticky-header table{min-width:0;table-layout:fixed}
.device-column-model{width:20%}.device-column-variant{width:18%}.device-column-maps{width:9%}.device-column-authorization{width:14%}.device-column-status{width:11%}.device-column-attempts{width:9%}.device-column-successful{width:8%}.device-column-last-success{width:11%}
.device-table-wrap thead{position:static}
.device-table-wrap thead th{position:sticky;top:calc(var(--admin-topbar-height) + var(--device-filter-height, 54px));z-index:21}
.device-table-wrap th,.device-table-wrap td{white-space:normal;overflow-wrap:anywhere}
.device-sort-button{display:inline-flex;align-items:center;gap:5px;width:auto;min-height:0;margin:0;padding:0;border:0;background:transparent;color:inherit;font:inherit;letter-spacing:inherit;text-transform:inherit;white-space:nowrap;cursor:pointer}
.device-sort-button:hover{color:var(--graphite)}.device-sort-button:focus-visible{outline:var(--admin-focus-ring);outline-offset:1px}
.device-sort-button span{min-width:10px;color:var(--secondary);font-size:12px;opacity:.2;transition:color .15s ease,opacity .15s ease}.device-sort-button:hover span,.device-sort-button:focus-visible span{opacity:.6}.device-table-wrap th[aria-sort="ascending"] .device-sort-button,.device-table-wrap th[aria-sort="descending"] .device-sort-button{color:var(--graphite);font-weight:800}.device-table-wrap th[aria-sort="ascending"] .device-sort-button span,.device-table-wrap th[aria-sort="descending"] .device-sort-button span{color:var(--interactive);opacity:1}
table th[aria-sort="ascending"]>.device-sort-button,table th[aria-sort="descending"]>.device-sort-button{color:var(--graphite)}
/* Header labels wrap instead of overlapping a neighbour or widening the table (owner decision 2026-10-06). */
table th>.device-sort-button{white-space:normal;text-align:inherit}
table th[aria-sort="ascending"]>.device-sort-button span,table th[aria-sort="descending"]>.device-sort-button span{color:var(--interactive);opacity:1}
.device-table-wrap td:nth-child(3),.device-table-wrap td:nth-child(4),.device-table-wrap td:nth-child(5),.device-table-wrap td:nth-child(6),.device-table-wrap td:nth-child(7),.device-table-wrap td:nth-child(8){white-space:nowrap}
.device-table-wrap tbody td{padding-top:6px;padding-bottom:6px}
.device-table-wrap tbody tr{cursor:pointer}
.device-table-wrap tbody tr:hover{background:color-mix(in srgb,var(--surface-muted) 52%,var(--surface))}
.device-table-wrap tbody tr:focus-visible{outline:var(--admin-focus-ring);outline-offset:-3px}
.device-model-button{display:flex;align-items:center;gap:10px;width:100%;padding:0;border:0;background:none;color:inherit;text-align:left;text-decoration:none}
.device-model-button strong{display:block;font-weight:700}
.device-model-copy{display:flex;align-items:center;gap:8px;min-width:0}
.historical-catalog-indicator{position:relative;display:inline-flex;align-items:center;justify-content:center;flex:0 0 18px;width:18px;height:18px;color:var(--secondary);font-weight:400}
.historical-catalog-indicator .catalog-archive-icon{width:16px;height:16px}
.historical-catalog-tooltip{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip-path:inset(50%);white-space:nowrap}
.historical-catalog-indicator:hover .historical-catalog-tooltip,.device-model-button:focus-visible .historical-catalog-tooltip{z-index:5;top:50%;left:calc(100% + 6px);transform:translateY(-50%);width:max-content;height:auto;max-width:220px;padding:6px 8px;margin:0;overflow:visible;clip-path:none;white-space:normal;background:var(--surface);border:1px solid var(--border);border-radius:6px;color:var(--secondary);font-size:12px;line-height:18px}
.device-model-copy strong{min-width:0;overflow-wrap:anywhere}
.device-thumb{display:block;width:38px;height:38px;flex:0 0 38px;object-fit:contain;border-radius:var(--radius-control);background:var(--surface-muted)}
.device-thumb-placeholder{position:relative;border:1px solid var(--border)}
.device-thumb-placeholder:before{content:"";position:absolute;inset:0;margin:auto;width:18px;height:18px;background:var(--sky);-webkit-mask:var(--fa-image) center/contain no-repeat;mask:var(--fa-image) center/contain no-repeat}
.new-badge{display:inline-flex;align-items:center;min-height:20px;padding:2px 7px;border:1px solid color-mix(in srgb,var(--lichen) 65%,var(--border));border-radius:999px;background:var(--new-badge-surface);color:var(--new-badge-text);font-size:10px;font-weight:750;letter-spacing:.06em;white-space:nowrap;text-transform:uppercase}
.summary-filter-link{margin:0;padding:0;border:0;background:none;color:var(--interactive);font:inherit;font-weight:750;text-decoration:underline;text-underline-offset:3px}
.admin-state{display:inline-flex;align-items:center;min-height:26px;padding:5px 9px;border:1px solid transparent;border-radius:999px;font-size:11px;font-weight:750;line-height:1;white-space:nowrap}
.admin-state-map-yes,.admin-state-authorization-approved,.admin-state-publication-published{background:var(--status-success-surface);border-color:var(--status-success-border);color:var(--status-success-text)}
.admin-state-map-no,.admin-state-authorization-blocked{background:var(--status-error-surface);border-color:var(--status-error-border);color:var(--status-error-text)}
.admin-state-map-unknown,.admin-state-authorization-pending,.admin-state-publication-pending,.admin-state-publication-unavailable{background:var(--surface-muted);border-color:var(--border);color:var(--secondary)}
.numeric{font-variant-numeric:tabular-nums}
.device-pagination{display:flex;align-items:center;justify-content:center;gap:16px;margin:14px 0 0;color:var(--secondary);font-size:13px}
.device-pagination button,.dialog-close{min-height:34px;padding:7px 11px;border:1px solid var(--border);border-radius:var(--radius-control);background:var(--surface);color:var(--interactive);font-weight:700}
.device-pagination button:hover:not(:disabled),.dialog-close:hover{border-color:var(--interactive);background:var(--success-bg)}
.device-pagination button:disabled{cursor:not-allowed;opacity:.45}
.device-dialog{width:min(780px,calc(100% - 32px));max-height:calc(100% - 32px);padding:0;border:0;border-radius:var(--radius-card);background:var(--surface);color:var(--graphite);box-shadow:0 24px 80px color-mix(in srgb,var(--graphite) 24%,transparent)}
.device-dialog::backdrop{background:color-mix(in srgb,var(--graphite) 34%,transparent)}
.device-dialog-inner{padding:20px}
.device-dialog-header{display:flex;align-items:flex-start;justify-content:space-between;gap:18px;margin-bottom:16px}
.device-dialog-header h2{display:flex;align-items:center;gap:10px;flex-wrap:wrap;font-size:25px}
.dialog-close{width:36px;min-height:36px;padding:0;font-size:20px;line-height:1}
.identity-checks-table th:nth-child(1){width:24%}.identity-checks-table th:nth-child(2){width:20%}.identity-checks-table th:nth-child(3){width:56%}
.device-dialog .admin-timestamp{white-space:nowrap}
.model-page-header{display:grid;grid-template-columns:auto minmax(0,1fr) auto;align-items:center;gap:20px;margin:0 0 24px}.model-page-image{width:96px;height:96px;object-fit:contain;border-radius:var(--radius-card);background:var(--surface)}.model-page-heading h1 span{color:var(--secondary);font-size:.55em;font-weight:500;letter-spacing:-.01em}.model-public-link{align-self:start;text-decoration:none}.model-statistics{grid-template-columns:repeat(5,minmax(0,1fr));margin-bottom:20px}.model-review-alert{display:flex;align-items:center;justify-content:space-between;gap:18px;margin:0 0 26px;padding:12px 14px;border:1px solid color-mix(in srgb,var(--stone) 48%,var(--border));border-radius:var(--radius-control);background:color-mix(in srgb,var(--stone) 9%,var(--surface));font-size:13px}.model-review-alert a{color:var(--interactive);font-weight:750;white-space:nowrap}.model-page-section{scroll-margin-top:calc(var(--admin-topbar-height) + 18px);margin-top:34px}.model-history-table{min-width:980px}.model-history-table th:nth-child(1){width:15%}.model-history-table th:nth-child(2){width:16%}.model-history-table th:nth-child(3){width:11%}.model-history-table th:nth-child(4){width:23%}.model-history-table th:nth-child(5){width:12%}.model-history-table th:nth-child(6){width:15%}.model-history-table th:nth-child(7){width:8%}.history-map small,.history-error small{display:block;margin-top:3px;color:var(--secondary);font-size:10px}.administration-grid article{padding:18px;border:1px solid var(--border);border-radius:var(--radius-card);background:var(--surface)}.administration-grid h3{margin:0 0 12px;font:700 17px var(--font-brand)}
.administration-card{display:grid;gap:0}
.administration-setting{display:grid;gap:12px}
.administration-setting+.administration-setting{margin-top:24px;padding-top:24px;border-top:1px solid var(--border)}
.administration-setting>h3{margin:0}
.administration-facts{display:grid;gap:8px;margin:0}
.administration-facts>div{display:flex;flex-wrap:wrap;justify-content:space-between;gap:4px 16px}
.administration-facts dt{color:var(--secondary);font-size:13px;font-weight:500}
.administration-facts dd{margin:0;color:var(--graphite);font-size:14px;font-weight:700;text-align:end}
.administration-setting .table-help{margin:0;font-size:13px}
.administration-setting form label{display:grid;gap:6px;color:var(--graphite);font-size:13px;font-weight:600}.administration-grid p{color:var(--secondary);font-size:13px}.administration-grid form{display:grid;gap:10px}.administration-grid label{color:var(--secondary);font-size:12px;font-weight:650}.administration-grid label select,.administration-grid label textarea{display:block;width:100%;margin-top:5px}.model-information-list{margin:0;border:1px solid var(--border);border-radius:var(--radius-card);background:var(--surface)}.model-information-list div{display:grid;grid-template-columns:minmax(170px,.7fr) minmax(0,1.3fr);gap:18px;padding:10px 14px;border-bottom:1px solid color-mix(in srgb,var(--border) 72%,transparent)}.model-information-list div:last-child{border-bottom:0}.model-information-list dt{color:var(--secondary);font-size:12px}.model-information-list dd{margin:0;overflow-wrap:anywhere;font-size:13px;font-weight:650;text-align:right}.model-technical-details{margin-top:18px;padding:0;border:1px solid var(--border);border-radius:var(--radius-card);background:var(--surface)}.model-technical-details>summary{cursor:pointer;color:var(--interactive);font-weight:750}.model-technical-details .model-information-list{margin-top:12px}.github-actions{display:flex;align-items:center;gap:8px;flex-wrap:wrap}.github-issue-preview{margin:10px 0}.github-issue-preview>summary{cursor:pointer;color:var(--interactive);font-size:12px;font-weight:750}.github-issue-preview input,.github-issue-preview textarea{font-family:var(--font-mono)!important}.technical-copy-actions{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin:8px 0}.diagnostic-technical-empty{margin:10px 0;color:var(--secondary);font-size:12px}
.secondary-button{display:inline-flex;align-items:center;justify-content:center;gap:6px;min-height:32px;padding:6px 10px;border:1px solid var(--border);border-radius:var(--radius-control);background:var(--surface);color:var(--interactive);font-size:12px;font-weight:700;text-decoration:none}
.secondary-button:hover{border-color:var(--interactive);background:var(--success-bg)}
.sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}
.page-meta{margin:0;color:var(--secondary);font-size:12px;white-space:nowrap}.installation-heading{align-items:flex-end}
.admin-kpi-grid{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:10px;margin:0 0 12px}.admin-kpi-grid article{min-width:0;min-height:84px;padding:14px 16px;background:var(--surface);border:1px solid var(--border);border-radius:var(--radius-card)}.admin-kpi-grid article>span{display:block;color:var(--secondary);font-size:12px;font-weight:650}.admin-kpi-grid article>strong{display:block;margin-top:6px;color:var(--graphite);font-family:var(--font-brand);font-size:25px;line-height:1.15;font-variant-numeric:tabular-nums}
.map-statistics-empty{margin:0 0 18px;padding:28px 24px;border:1px dashed var(--border);border-radius:var(--radius-card);background:var(--surface);text-align:center}.map-statistics-empty h2{font-size:20px}.map-statistics-empty p{margin:8px 0 0;color:var(--secondary);font-size:13px}.map-events-card{margin-top:24px}
.admin-disclosure{margin:0}.admin-disclosure>summary{cursor:pointer;color:var(--interactive);font-size:13px;font-weight:750;list-style-position:inside;text-underline-offset:3px}.admin-disclosure>summary:hover{text-decoration:underline}.admin-disclosure>summary:focus-visible{outline:var(--admin-focus-ring);outline-offset:3px}.disclosure-body{margin-top:14px}.filter-disclosure{align-self:stretch;min-width:130px;position:relative}.filter-disclosure>summary{display:flex;align-items:center;justify-content:center;height:var(--admin-control-height);padding:8px 10px;border:1px solid var(--border);border-radius:var(--admin-control-radius);background:var(--surface);color:var(--graphite);font-size:var(--admin-control-font-size);font-weight:650;list-style:none;text-decoration:none}.filter-disclosure>summary::-webkit-details-marker{display:none}.filter-disclosure .disclosure-body{display:flex;gap:8px;flex-wrap:wrap;position:absolute;z-index:5;margin-top:7px;padding:8px;border:1px solid var(--border);border-radius:var(--radius-control);background:var(--surface);box-shadow:0 14px 34px color-mix(in srgb,var(--graphite) 14%,transparent)}.filter-disclosure .disclosure-body label{display:flex}.filter-disclosure .disclosure-body input,.filter-disclosure .disclosure-body select{min-width:140px}.inline-filter-row{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin:0 0 12px}.inline-filter-row label{display:flex;flex:1 1 220px}.inline-filter-row select{flex:0 1 170px}.provider-pagination{display:flex;align-items:center;justify-content:center;gap:14px;min-height:34px;margin-top:12px;color:var(--secondary);font-size:12px;text-align:center}.provider-pagination button{min-height:34px;padding:7px 11px;border:1px solid var(--border);border-radius:var(--radius-control);background:var(--surface);color:var(--interactive);font:700 12px var(--font-ui)}.provider-pagination button:hover:not(:disabled){border-color:var(--interactive);background:var(--success-bg)}.provider-pagination button:disabled{cursor:not-allowed;opacity:.45}.provider-latest-summary{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:12px 14px;border-radius:var(--radius-control);background:var(--surface-muted);color:var(--secondary);font-size:12px}.provider-latest-summary>div{display:flex;align-items:center;gap:8px;flex-wrap:wrap}.provider-action-overflow{position:relative}.provider-action-overflow>summary{display:inline-flex;align-items:center;justify-content:center;min-height:var(--admin-control-height);padding:8px 12px;border:1px solid var(--border);border-radius:var(--admin-control-radius);background:var(--surface);color:var(--graphite);cursor:pointer;font-size:13px;font-weight:700;list-style:none}.provider-action-overflow>summary::-webkit-details-marker{display:none}.provider-action-overflow>summary:hover{border-color:var(--interactive);color:var(--interactive)}.provider-action-overflow>div{position:absolute;z-index:4;right:0;top:calc(100% + 7px);min-width:180px;padding:7px;border:1px solid var(--border);border-radius:var(--radius-control);background:var(--surface);box-shadow:0 14px 34px color-mix(in srgb,var(--graphite) 14%,transparent)}.provider-action-overflow button{width:100%}.provider-package-name{display:block;font-weight:700}.provider-package-id{display:block;margin-top:2px;color:var(--secondary)!important;font-size:10px!important}.provider-package-broken td:last-child{color:var(--danger)}.provider-issue-count{white-space:nowrap}.provider-issue-count.is-positive{color:var(--danger)}.audit-technical-details{margin-top:5px}.audit-technical-details summary{cursor:pointer;color:var(--interactive);font-size:11px;font-weight:700}.audit-technical-details code{display:block;margin-top:5px;max-width:300px;overflow:auto;white-space:pre-wrap;font:500 10px var(--font-mono);color:var(--secondary)}.provider-information-list dd{text-align:left}.provider-section .provider-table-wrap table{min-width:820px}.provider-detail .provider-table-wrap table{min-width:760px}
.provider-health-checks,.provider-health-facts{margin:12px 0}.provider-health-checks>div,.provider-health-facts>div{display:flex;align-items:baseline;justify-content:space-between;gap:12px;padding:7px 0;border-bottom:1px solid var(--border)}.provider-health-checks dt,.provider-health-facts dt{color:var(--secondary)}.provider-health-checks dd,.provider-health-facts dd{margin:0;text-align:right;overflow-wrap:anywhere}.provider-current-health p{overflow-wrap:anywhere}.provider-health-history{list-style:none;padding:0;margin:0}.provider-health-history li{padding:10px 0;border-bottom:1px solid var(--border)}.provider-health-history li>div{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap}.provider-health-history small{display:block;margin-top:4px;color:var(--secondary)}.provider-health-history p{margin:4px 0 0;font-size:12px;overflow-wrap:anywhere}.provider-health-schedule{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin:14px 0;font-size:12px}.provider-health-schedule label{flex-basis:100%;font-weight:700}.provider-download-control{display:grid;justify-items:start;gap:7px;margin-top:10px;text-align:left;white-space:normal}.provider-download-control strong,.provider-download-control small{font-size:11px;overflow-wrap:anywhere}
@media(max-width:1100px){.admin-topbar-inner{display:flex;flex-wrap:wrap;gap:12px}.admin-header-left{flex:0 0 auto}.admin-section-nav{order:3;flex-basis:100%;margin-left:0}.admin-nav{flex:1 1 auto;justify-content:flex-end}.admin-kpi-grid{grid-template-columns:repeat(3,minmax(0,1fr))}.provider-metrics{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:700px){.admin-kpi-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.installation-heading{align-items:flex-start}.page-meta{white-space:normal}.provider-latest-summary{align-items:flex-start;flex-direction:column;gap:6px}.filter-disclosure .disclosure-body{position:static;margin-top:8px;box-shadow:none}.map-statistics-filter-bar .filter-disclosure{width:100%}.map-statistics-filter-bar .filter-disclosure>summary{justify-content:flex-start}}
@media(max-width:480px){.admin-kpi-grid{grid-template-columns:1fr}.admin-kpi-grid article{min-height:70px;padding:12px}.inline-filter-row{align-items:stretch;flex-direction:column}.inline-filter-row label,.inline-filter-row select{width:100%;flex-basis:auto}.provider-pagination{gap:8px;font-size:11px}.provider-pagination span{max-width:130px}.provider-action-overflow>div{position:static;margin-top:7px}.provider-action-overflow>summary{width:100%}}
@media(max-width:760px){.admin-topbar-inner,.dashboard{width:min(calc(100% - 32px),var(--max-width))}.admin-topbar-inner{display:flex;flex-wrap:wrap;gap:12px}.admin-header-left{flex:0 0 auto}.admin-section-nav{order:3;flex-basis:100%;margin-left:0}.admin-nav{flex:1 1 auto;justify-content:flex-end}.heading-row{align-items:flex-start;flex-direction:column;gap:12px}.diagnostic-model-metrics{grid-template-columns:repeat(2,minmax(0,1fr))}.filter-bar{align-items:stretch}.filter-bar label,.filter-bar select,.filter-bar input{flex:1 1 170px}.filter-bar .results-count{width:100%;margin:2px 4px 0}.campaign-fields{grid-template-columns:1fr}.campaign-field-wide{grid-column:auto}.attribution-preview{grid-template-columns:1fr}.diagnostic-detail-summary{grid-template-columns:1fr}.diagnostic-actions-grid{grid-template-columns:1fr}.github-review{min-width:0}}
@media(max-width:980px){.admin-topbar-inner{display:flex;flex-wrap:wrap;gap:12px}.admin-header-left{flex:0 0 auto}.admin-section-nav{order:3;flex-basis:100%;margin-left:0}.admin-nav{flex:1 1 auto;justify-content:flex-end}}
@media(max-width:560px){.admin-topbar-inner{align-items:flex-start;flex-direction:column;padding:14px 0}.admin-header-left,.admin-section-nav,.admin-nav{width:100%}.admin-section-nav{order:0;overflow:auto;justify-content:flex-start}.admin-section-nav a{white-space:nowrap}.admin-nav{justify-content:space-between;gap:10px;flex-wrap:wrap}.timezone-control{width:100%;justify-content:space-between}.timezone-control select{width:auto;flex:1}.dashboard{padding-top:28px}.diagnostic-model-metrics{gap:8px}.diagnostic-model-metrics article{padding:12px}.auth-card{width:calc(100% - 32px);padding:24px}.section-heading{align-items:flex-start;flex-direction:column;gap:4px}.campaign-card{padding:16px}.campaign-preset-row{align-items:stretch;flex-direction:column;gap:8px}.campaign-preset-row .campaign-label,.campaign-preset-row select{flex:none}.campaign-preset-row select{width:100%;height:var(--admin-control-height);margin-left:0}.generated-url-row{grid-template-columns:1fr}.copy-button{width:100%}.copy-status{min-height:18px}.device-dialog-inner,.diagnostic-detail-inner{padding:18px}.diagnostic-technical-details dl{grid-template-columns:1fr}.github-link-form{grid-template-columns:1fr}.github-link-form button{width:100%}}
@media(max-width:560px){.admin-section-nav{overflow:visible;flex-wrap:wrap}}
@media(max-width:760px){:is(.device-summary-sync,.provider-summary-sync){text-align:left;white-space:normal}}
@media(max-width:560px){.device-filter-bar .results-count{margin-left:0}.device-dialog-inner{padding:18px}}
@media(max-width:1100px){.device-sticky-header{display:block;position:sticky;top:calc(var(--admin-topbar-height) + var(--device-filter-height, 54px));z-index:21;overflow:hidden;border:1px solid var(--border);border-bottom:0;background:var(--surface)}.device-sticky-header-scroll{overflow:hidden}.device-sticky-header table,.device-table-wrap table{min-width:1050px}.device-sticky-header th{position:static}.device-table-wrap{overflow-x:auto;overflow-y:hidden}.device-table-wrap thead{display:none}.model-statistics{grid-template-columns:repeat(3,minmax(0,1fr))}}
@media(max-width:760px){.model-page-header{grid-template-columns:auto minmax(0,1fr)}.model-public-link{grid-column:1/-1;width:max-content}.model-statistics{grid-template-columns:repeat(2,minmax(0,1fr))}.model-review-alert{align-items:flex-start;flex-direction:column}.model-information-list div{grid-template-columns:1fr;gap:3px}.model-information-list dd{text-align:left}}
@media(max-width:1100px){.provider-metrics{grid-template-columns:repeat(2,minmax(0,1fr))}.provider-dashboard-grid{grid-template-columns:1fr}}
@media(max-width:900px){.map-statistics-coverage-layout{grid-template-columns:1fr}.map-statistics-world-map{min-height:0}.map-statistics-world-map-card .section-heading .table-help{text-align:start}}
@media(max-width:560px){.provider-card{padding:18px 16px}.provider-metrics{grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.provider-metrics article{padding:12px}.provider-information-list div{grid-template-columns:1fr;gap:3px}.provider-information-list dd{text-align:left}.provider-action-bar{align-items:stretch;flex-direction:column}.provider-action-bar button{width:100%}.provider-action-bar .admin-action-status{flex-basis:auto}.map-statistics-filter-bar label,.map-statistics-filter-bar input,.map-statistics-filter-bar select{width:100%;min-width:0}.map-statistics-filter-bar .results-count{width:100%;margin-left:4px}}
@media(max-height:760px){.device-dialog-inner{max-height:calc(100vh - 32px);overflow:auto}.device-dialog-header{position:sticky;top:-1px;z-index:2;padding-bottom:10px;background:var(--surface)}}
.overview-page{padding-top:30px}.overview-heading{align-items:flex-end;margin-bottom:20px}.overview-period-form{margin:0}.overview-period-form select{min-width:154px}.overview-panel{margin-top:12px;padding:18px 20px;border:1px solid var(--border);border-radius:var(--radius-card);background:var(--surface)}.overview-panel .section-heading{margin-bottom:10px}.overview-empty-state{margin:0;padding:12px 0;color:var(--secondary);font-weight:650}.overview-attention-list,.overview-activity-list{list-style:none;margin:0;padding:0}.overview-attention-item{display:grid;grid-template-columns:auto minmax(0,1fr) auto;align-items:start;gap:10px;padding:10px 0;border-top:1px solid color-mix(in srgb,var(--border) 75%,transparent)}.overview-attention-item:first-child{border-top:0;padding-top:3px}.overview-attention-item div{display:grid;gap:2px;min-width:0}.overview-attention-item a{color:var(--graphite);text-decoration:none}.overview-attention-item a:hover{text-decoration:underline;text-underline-offset:3px}.overview-attention-item strong{font-size:14px}.overview-attention-item span{color:var(--secondary);font-size:12px;overflow:hidden;text-overflow:ellipsis}.overview-attention-item small{color:var(--secondary);font-size:11px}.overview-detail-link,.section-link{color:var(--interactive);font-size:12px;font-weight:700;white-space:nowrap;text-decoration:none}.overview-detail-link:hover,.section-link:hover{text-decoration:underline;text-underline-offset:3px}.overview-activity-item{display:grid;grid-template-columns:126px minmax(0,1fr) max-content;align-items:center;gap:10px;padding:8px 0;border-top:1px solid color-mix(in srgb,var(--border) 75%,transparent)}.overview-activity-item:first-child{border-top:0;padding-top:3px}.overview-activity-item>time{color:var(--secondary);font-size:11px;white-space:nowrap}.overview-activity-item .map-activity-copy{display:grid;min-width:0}.overview-activity-label{font-size:13px;font-weight:750}.overview-activity-item .map-activity-copy>span:not(.overview-activity-label){overflow:hidden;text-overflow:ellipsis;color:var(--secondary);font-size:12px;white-space:nowrap}.overview-activity-provider{color:var(--secondary);font-size:11px;white-space:nowrap}.overview-activity-failed .overview-activity-label,.overview-activity-not-started .overview-activity-label{color:var(--danger)}.overview-chart-note{margin:12px 0 0;color:var(--secondary);font-size:11px}.admin-section-nav{flex-wrap:wrap}
.quick-filter-group{display:flex;align-items:center;gap:4px;flex:0 0 auto;flex-wrap:wrap}.quick-filter{min-height:var(--admin-control-height);padding:8px 10px;border:1px solid transparent;border-radius:var(--admin-control-radius);background:transparent;color:var(--secondary);font-weight:650}.quick-filter:hover{border-color:var(--border);color:var(--interactive)}.quick-filter.active{border-color:color-mix(in srgb,var(--sky) 45%,var(--border));background:var(--surface);color:var(--interactive);box-shadow:0 1px 1px color-mix(in srgb,var(--graphite) 5%,transparent)}
.map-statistics-coverage-layout{display:grid;grid-template-columns:minmax(0,3fr) minmax(280px,1fr);gap:16px;margin-top:16px}.map-statistics-coverage-layout>.provider-card{min-width:0;margin-top:0}.map-statistics-popularity{grid-template-columns:minmax(0,1fr)}.map-statistics-popularity .provider-card{margin-top:0}.table-secondary{display:block;margin-top:3px;color:var(--secondary);font-size:11px;font-weight:500}
.map-statistics-world-map{position:relative;min-height:300px;padding:8px 0 0;overflow:hidden;border:1px solid var(--border);border-radius:var(--radius-control);background:var(--surface-muted)}.world-map-svg{width:100%;padding:0 8px}.world-map-svg svg{display:block;width:100%;height:auto;overflow:visible}.world-map-country{stroke:color-mix(in srgb,var(--interactive) 42%,var(--border));stroke-width:.65;vector-effect:non-scaling-stroke;cursor:help;outline:none;transition:filter .12s ease,stroke-width .12s ease}.world-map-country:hover,.world-map-country:focus{filter:brightness(.86);stroke:var(--interactive);stroke-width:1.5}.world-map-tooltip{position:absolute;z-index:2;top:12px;right:12px;min-width:170px;max-width:240px;padding:10px 12px;border:1px solid color-mix(in srgb,var(--interactive) 28%,var(--border));border-radius:var(--radius-control);background:color-mix(in srgb,var(--surface) 94%,transparent);box-shadow:0 8px 24px color-mix(in srgb,var(--graphite) 14%,transparent);font-size:12px;pointer-events:none}.world-map-tooltip strong,.world-map-tooltip-total{display:block}.world-map-tooltip-total{margin-top:2px;color:var(--secondary)}.world-map-provider-line{display:flex;justify-content:space-between;gap:16px;margin-top:7px;padding-top:6px;border-top:1px solid var(--border)}.world-map-provider-line+ .world-map-provider-line{margin-top:5px;padding-top:5px}.world-map-provider-line span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.world-map-provider-line strong{font-variant-numeric:tabular-nums}.world-map-legend{display:flex;align-items:center;gap:8px;margin:8px 2px 0;color:var(--secondary);font-size:11px;font-variant-numeric:tabular-nums}.world-map-legend-gradient{display:block;flex:1;height:8px;border-radius:999px;background:linear-gradient(90deg,var(--surface),color-mix(in srgb,var(--sky) 50%,var(--interactive)));border:1px solid var(--border)}.map-statistics-world-map-card .section-heading{align-items:flex-start}.map-statistics-world-map-card .section-heading .table-help{padding-top:3px;text-align:right}
.overview-chart-wrap{overflow-x:auto}.overview-trend-chart{display:block;width:100%;min-width:520px;height:auto;min-height:180px}.overview-trend-chart text{fill:var(--secondary);font:500 11px var(--font-ui)}.overview-chart-note{font-size:12px;color:var(--secondary);margin:10px 0 0}.provider-metrics{grid-template-columns:repeat(4,minmax(0,1fr))}.map-statistics-provider-table{display:block}.model-statistics article>.info-control{display:inline-flex;margin-top:6px;vertical-align:middle}.history-more-filters{min-width:130px}.history-more-filters .disclosure-body{min-width:170px}
@media(max-width:760px){.overview-heading{align-items:flex-start;flex-direction:column;gap:12px}.overview-period-form,.overview-period-form select{width:100%}.overview-activity-item{grid-template-columns:1fr max-content;gap:3px 8px}.overview-activity-item>time{grid-column:1/-1}.overview-activity-provider{grid-column:2;grid-row:2}.overview-activity-item .map-activity-copy{grid-column:1;grid-row:2}}
@media(max-width:560px){.overview-panel{padding:16px}.overview-attention-item{grid-template-columns:auto minmax(0,1fr)}.overview-detail-link{grid-column:2}}
@media(max-width:700px){.provider-metrics{grid-template-columns:repeat(2,minmax(0,1fr))}}
.overview-primary-grid{display:grid;gap:12px;grid-template-columns:repeat(2,minmax(0,1fr))}.overview-primary-grid .overview-panel{min-width:0}.overview-activity-item{grid-template-columns:minmax(0,1fr) max-content}.overview-activity-item>time{grid-column:2;grid-row:1 / span 2}.overview-activity-item .overview-activity-label{grid-column:1}.overview-activity-item .map-activity-copy>span:not(.overview-activity-label){grid-column:1}.inline-filter-row{justify-content:flex-start}.inline-filter-row label{flex:0 1 260px}.inline-filter-row select{flex:0 0 170px}
.system-health-page{padding-top:30px}
.health-check-wrap{border:0;border-radius:0;background:transparent}
.health-check-wrap table.health-check-table{width:100%;min-width:0;table-layout:fixed}
.health-check-wrap table.health-weekly-table{table-layout:auto}
.health-check-table th,.health-check-table td{padding:10px 12px;vertical-align:middle}
.health-check-table th:first-child,.health-check-table td:first-child{padding-left:0}
.health-check-table thead td{background:var(--surface);box-shadow:0 1px 0 var(--border)}
.health-check-table tbody tr.system-health-row:nth-last-child(2):has(+ .health-details-row[hidden])>*{border-bottom:0}
.health-col-check{width:220px}.health-col-status{width:128px}.health-col-when{width:168px}.health-col-more{width:108px}
.health-group-table .health-col-more{width:auto}
.health-check-name{color:var(--graphite);font-size:13px;font-weight:650;line-height:20px;text-transform:none;letter-spacing:0;white-space:normal;overflow-wrap:anywhere}
.health-check-name .table-secondary{margin-top:2px;color:var(--secondary);font-size:12px;font-weight:400;line-height:18px;white-space:normal}
.health-check-reason{white-space:normal;overflow-wrap:anywhere}
.system-health-cause,.system-health-action{display:block;margin:0;font-size:13px;line-height:20px}
.system-health-cause{color:var(--graphite)}
.health-check-reason .system-health-action{margin-top:2px;font-size:12px;line-height:18px}
span.system-health-action{color:var(--secondary)}
a.system-health-action{display:inline;color:var(--interactive);font-weight:650;white-space:normal;text-underline-offset:3px}
.health-check-table td.system-health-when{color:var(--secondary);font-size:12px;white-space:nowrap;text-align:left!important}
.health-check-table thead .column-date{text-align:left!important}
.health-check-more{text-align:right}
.health-group-table .health-check-more{text-align:left}
.health-details-toggle{display:inline-flex;align-items:center;gap:6px;min-height:32px;padding:4px 10px;border:1px solid var(--border);border-radius:var(--admin-control-radius);background:var(--surface);color:var(--interactive);cursor:pointer;font:650 12px/1 var(--font-ui)}
.health-details-toggle:hover{border-color:var(--interactive)}
.health-details-toggle:focus-visible{outline:var(--admin-focus-ring);outline-offset:2px}
.health-details-toggle .admin-icon{width:10px;height:10px;transition:transform .15s ease}
.health-details-toggle[aria-expanded="true"] .admin-icon{transform:rotate(180deg)}
.health-check-table .health-details-row td[colspan]{padding:0 0 12px;font-weight:400;text-align:left!important;white-space:normal}
.health-details-body{padding:12px 14px;border-radius:var(--radius-control);background:var(--surface-muted);font-size:12px;line-height:1.55;overflow-wrap:anywhere}
.health-details-body>:last-child,.health-details-body .system-health-description>:last-child{margin-bottom:0}
.health-details-action{margin:0 0 10px}
.health-check-table tbody tr.system-health-row:has(+ .health-details-row:not([hidden])) th,.health-check-table tbody tr.system-health-row:has(+ .health-details-row:not([hidden])) td{border-bottom:0}
.health-check-table tr[hidden]{display:none!important}
.health-weekly-table th[scope='row']{color:var(--graphite);font-size:13px;font-weight:650;text-transform:none;letter-spacing:0}
.health-technical-disclosure>summary{display:flex;flex-wrap:wrap;align-items:center;gap:4px 10px;cursor:pointer;list-style:none}
.health-technical-disclosure>summary::-webkit-details-marker{display:none}
.health-technical-disclosure>summary:focus-visible{outline:var(--admin-focus-ring);outline-offset:3px;border-radius:var(--radius-control)}
.health-technical-disclosure>summary>h2{margin:0;color:var(--graphite);font:600 17px/24px var(--font-ui)}
.health-technical-disclosure>summary:hover>h2{color:var(--interactive)}
.health-technical-chevron{display:inline-flex;color:var(--interactive)}
.health-technical-chevron .admin-icon{width:12px;height:12px}
.health-technical-disclosure[open] .health-technical-chevron{transform:rotate(90deg)}
.health-technical-body{margin-top:12px}
.health-technical-switcher{margin:0}
.health-technical-panel{margin-top:12px}
.health-technical-panel:focus-visible{outline:var(--admin-focus-ring);outline-offset:3px}
.health-panel-summary{display:flex;flex-wrap:wrap;align-items:center;gap:8px 12px;margin:0 0 4px}
.health-panel-note{color:var(--secondary);font-size:12px}
.health-panel-summary .section-link{margin-left:auto}
.system-health-catalog-when{color:var(--secondary)}
.system-health-description p{margin:0 0 10px;color:var(--secondary);font-size:12px;line-height:1.55}.indexnow-status-note,.indexnow-error{color:var(--secondary);font-size:11px;line-height:1.55}.indexnow-details{margin:14px 0;font-size:11px}.indexnow-details div{display:grid;grid-template-columns:minmax(150px,auto) minmax(0,1fr);gap:10px;padding:5px 0;border-top:1px solid var(--border)}.indexnow-details dt{font-weight:750;color:var(--graphite)}.indexnow-details dd{margin:0;color:var(--secondary);overflow-wrap:anywhere}.indexnow-url-preview{margin:0 0 10px;padding-left:18px;color:var(--secondary);font-size:11px}.indexnow-url-preview code{font:500 10px var(--font-mono);overflow-wrap:anywhere}
@media(max-width:900px){.overview-primary-grid{grid-template-columns:1fr}}
@media(max-width:760px){.overview-activity-item{grid-template-columns:1fr max-content}.overview-activity-item>time{grid-column:2;grid-row:1 / span 2}.overview-activity-item .map-activity-copy{grid-column:1;grid-row:1 / span 2}.overview-activity-item .map-activity-copy>span:not(.overview-activity-label){white-space:normal}}
@media(max-width:480px){.inline-filter-row label,.inline-filter-row select{flex-basis:auto}}
.provider-action-bar{padding:0 0 4px;background:transparent;border:0;border-radius:0}

/* Shared Admin typography and density contract. Keep page-specific layout
   rules above this block; this is the final type hierarchy consumed by every
   authenticated Admin view. */
:root{
  --admin-type-eyebrow-size:12px;--admin-type-eyebrow-line:16px;
  --admin-type-page-title-size:clamp(32px,3.5vw,44px);--admin-type-page-title-line:1.06;
  --admin-type-section-title-size:22px;--admin-type-section-title-line:26px;
  --admin-type-subsection-size:15px;--admin-type-subsection-line:20px;
  --admin-type-description-size:15px;--admin-type-description-line:22px;
  --admin-type-body-size:15px;--admin-type-body-line:22px;
  --admin-type-label-size:12px;--admin-type-label-line:16px;
  --admin-type-kpi-value-size:30px;--admin-type-kpi-value-line:30px;
  --admin-type-support-size:12px;--admin-type-support-line:17px;
  --admin-type-table-header-size:11px;--admin-type-table-header-line:16px;
  --admin-type-table-primary-size:13px;--admin-type-table-primary-line:18px;
  --admin-type-table-meta-size:12px;--admin-type-table-meta-line:17px;
  --admin-type-control-size:13px;--admin-type-control-line:18px;
  --admin-type-button-size:13px;--admin-type-button-line:18px;
  --admin-type-badge-size:11px;--admin-type-badge-line:15px;
  --admin-type-helper-size:12px;--admin-type-helper-line:18px;
  --admin-type-technical-size:11px;--admin-type-technical-line:16px;
  --admin-control-font-size:var(--admin-type-control-size)
}
body{font-size:var(--admin-type-body-size);line-height:var(--admin-type-body-line)}
h1{font-size:var(--admin-type-page-title-size);line-height:var(--admin-type-page-title-line)}
h2,.provider-card .section-heading h2,.attribution-preview h2,.map-statistics-empty h2,.device-dialog-header h2{font-size:var(--admin-type-section-title-size);line-height:var(--admin-type-section-title-line)}
.table-help,.results-count,.page-meta,.overview-chart-note{font-size:var(--admin-type-helper-size);line-height:var(--admin-type-helper-line)}
button,input,select,textarea{font-size:var(--admin-type-control-size);line-height:var(--admin-type-control-line)}
.filter-bar input,.filter-bar select,.filter-disclosure>summary,.quick-filter,.provider-action-overflow>summary,.secondary-button,.copy-button,.provider-pagination button,.device-pagination button,.admin-action-dialog button:not(.link-button),.auth-card button:not(.link-button),.model-administration button[type="submit"]{font-size:var(--admin-type-button-size);line-height:var(--admin-type-button-line)}
.admin-section-nav,.admin-nav,.admin-section-nav a,.admin-nav a,.link-button{font-size:var(--admin-type-control-size);line-height:var(--admin-type-control-line)}

.admin-kpi-grid article>span,.provider-metrics article>span,.diagnostic-model-metrics article>span{font-size:var(--admin-type-label-size);line-height:var(--admin-type-label-line)}
.admin-kpi-grid article>strong,.provider-metrics article>strong,.diagnostic-model-metrics article>strong,.model-statistics article>strong{font-size:var(--admin-type-kpi-value-size);line-height:var(--admin-type-kpi-value-line)}
.overview-period-form{margin:0;padding:6px}
.overview-period-form label{display:flex}
.overview-period-form select{height:var(--admin-control-height);min-height:var(--admin-control-height);min-width:154px;padding:8px var(--admin-control-padding-x);border-radius:var(--admin-control-radius);font:600 var(--admin-control-font-size)/1.2 var(--font-ui)}
.overview-chart-panel{padding-top:16px;padding-bottom:16px}
.overview-chart-panel .section-heading{margin-bottom:6px}
.overview-chart-wrap{max-width:780px;margin:0 auto}
.overview-download-panel{padding-top:16px;padding-bottom:16px}
.overview-download-panel .section-heading{margin-bottom:6px}
.overview-chart-download-dmg{fill:var(--interactive);background:var(--interactive)}
.overview-chart-download-zip{fill:var(--status-success-text);background:var(--status-success-text)}
.overview-chart-download-marker line{stroke-width:2;stroke-dasharray:4 3}.overview-chart-download-marker text{stroke:none;font-size:10px;font-weight:700}.overview-chart-download-release line{stroke:var(--interactive)}.overview-chart-download-release text{fill:var(--interactive)}.overview-chart-download-boundary line{stroke:var(--secondary)}.overview-chart-download-boundary text{fill:var(--secondary)}
.overview-trend-chart{display:block;width:100%;height:260px;max-width:760px;min-height:0;margin:0 auto}
.overview-trend-mobile{display:none}
@media(min-width:901px) and (max-width:1100px),(max-width:700px){
  .overview-trend-desktop{display:none}
  .overview-trend-mobile{display:block;min-width:0;width:100%;height:auto;aspect-ratio:360/220}
  .overview-chart-wrap{width:100%;min-width:0;overflow:visible}
  .overview-trend-mobile text{font-size:13px}
}
@media(max-width:760px){
}
@media(max-width:560px){.overview-attention-actions{grid-column:2;justify-content:flex-start;flex-wrap:wrap}}
.device-information-section .model-information-list{max-width:780px}
.device-information-section .model-information-list div{grid-template-columns:150px minmax(0,1fr);gap:16px}
.device-information-section .model-information-list dd{text-align:left}
.diagnostic-detail-dialog{width:min(1160px,calc(100% - 32px));max-height:min(82vh,760px)}
.diagnostic-detail-inner{max-height:min(82vh,760px)}

table{font-size:var(--admin-type-table-primary-size);line-height:var(--admin-type-table-primary-line)}
table th,table td{padding:8px 12px;font-size:var(--admin-type-table-primary-size);line-height:var(--admin-type-table-primary-line)}
table thead th{font-size:var(--admin-type-table-header-size);line-height:var(--admin-type-table-header-line)}
table td small,.table-secondary,.provider-name-link small,.provider-package-id,.history-map small,.history-error small{font-size:var(--admin-type-table-meta-size);line-height:var(--admin-type-table-meta-line)}
table code,.provider-table-wrap code,.audit-technical-details code{font-size:var(--admin-type-technical-size);line-height:var(--admin-type-technical-line)}
.device-table-wrap tbody td{padding:7px 12px;font-size:var(--admin-type-table-primary-size);line-height:var(--admin-type-table-primary-line)}
.device-table-wrap th{font-size:var(--admin-type-table-header-size);line-height:var(--admin-type-table-header-line)}
.device-model-button strong,.provider-name-link strong,.provider-package-name{font-size:var(--admin-type-table-primary-size);line-height:var(--admin-type-table-primary-line)}
.provider-error,.provider-activation-note,.incomplete-state{font-size:var(--admin-type-helper-size);line-height:var(--admin-type-helper-line)}
.provider-information-list dt,.model-information-list dt,.administration-grid label{font-size:var(--admin-type-label-size);line-height:var(--admin-type-helper-line)}
.provider-information-list dd,.model-information-list dd{font-size:var(--admin-type-table-primary-size);line-height:20px}
.provider-information-list a,.provider-url-cell a{font-size:var(--admin-type-table-meta-size);line-height:var(--admin-type-table-meta-line)}

.admin-state,.new-badge,.identity-pending-indicator{min-height:24px;padding:4px 7px;font-size:var(--admin-type-badge-size);line-height:var(--admin-type-badge-line)}
.admin-disclosure>summary,.provider-action-overflow>summary{font-size:var(--admin-type-control-size);line-height:var(--admin-type-control-line)}
.administration-grid h3{font-size:var(--admin-type-subsection-size);line-height:var(--admin-type-subsection-line)}

.filter-bar{padding:6px;gap:7px}
.provider-card{margin-top:20px;padding:18px 20px}
.provider-card .section-heading{margin-bottom:12px}
.provider-information-list div,.model-information-list div{padding:8px 0}
.provider-dashboard-grid{gap:16px}
.diagnostic-model-metrics{margin-bottom:24px}
.model-page-header{margin-bottom:20px}
.model-page-section{margin-top:28px}
.model-technical-details{margin-top:16px}
.secondary-button,.provider-pagination button,.device-pagination button{min-height:var(--admin-control-height);padding:8px 10px}
.provider-pagination button,.device-pagination button{display:inline-flex;align-items:center;justify-content:center;margin:0;text-align:center;text-decoration:none;white-space:nowrap;-webkit-appearance:none;appearance:none}
.github-actions>.secondary-button{display:inline-flex;align-items:center;justify-content:center;margin:0;align-self:stretch;text-align:center;text-decoration:none;white-space:normal}
.github-actions>.copy-status{flex-basis:100%}
.identity-search-results{display:grid;gap:4px;max-height:240px;overflow-y:auto;margin:8px 0}
.identity-search-results[hidden]{display:none}
.identity-search-results>button.secondary-button{display:block;width:100%;min-height:44px;margin:0;text-align:left;white-space:normal;overflow-wrap:anywhere}
.provider-action-overflow>summary{min-height:var(--admin-control-height);padding:8px 12px}
.provider-action-bar{gap:7px}
.disclosure-body{margin-top:12px}

@media(max-width:760px){
  .provider-card{padding:16px}
  .table-help,.results-count,.page-meta{line-height:16px}
  .device-information-section .model-information-list div{grid-template-columns:1fr;gap:2px}
}

/* Admin audit: one UI type family, visible actions, responsive navigation. */
h1,h2,h3,h4,.administration-grid h3,.admin-kpi-grid article>strong,.provider-metrics article>strong,.diagnostic-model-metrics article>strong{font-family:var(--font-ui);letter-spacing:-.015em}
:root{--admin-type-page-title-size:clamp(28px,3vw,36px);--admin-type-page-title-line:1.2;--admin-type-section-title-size:20px;--admin-type-section-title-line:26px}
.admin-topbar-inner{display:flex;flex-wrap:wrap;gap:8px 16px;padding:10px 0}
.admin-skip-link{position:fixed;z-index:100;top:8px;left:8px;padding:9px 12px;border-radius:var(--radius-control);background:var(--graphite);color:var(--surface);font-weight:700;transform:translateY(-150%)}
.admin-skip-link:focus{transform:none;outline:var(--admin-focus-ring);outline-offset:2px}
.admin-section-nav{flex:1 1 100%;order:3;min-width:0;justify-content:flex-start}
.admin-nav{margin-inline-start:auto;flex:0 1 auto;min-width:0}
.admin-header-left{flex:0 0 auto}
.diagnostic-action-form button[type='submit']{min-height:var(--admin-control-height);padding:8px 12px;border:1px solid transparent;border-radius:var(--admin-control-radius);background:var(--interactive);color:var(--interactive-primary-text);font-weight:600}
.diagnostic-action-form button[type='submit']:hover{background:var(--interactive-hover)}
.diagnostic-action-form button.secondary-button,.model-administration button.secondary-button{background:var(--surface);color:var(--interactive);border:1px solid var(--border)}

.model-status-line{display:flex;align-items:center;gap:8px 16px;flex-wrap:wrap;margin-top:8px}.model-status-line>span{display:inline-flex;align-items:center;gap:6px;color:var(--secondary);font-size:12px}.model-status-line strong{color:var(--graphite);font-size:12px}.compact-empty-state{margin-top:20px;padding:18px 20px;border:1px solid var(--border);border-radius:var(--radius-card);background:var(--surface)}.compact-empty-state h2{margin:0 0 4px}.compact-empty-state p{margin:0;color:var(--secondary)}.diagnostic-identity-state{margin:12px 0;padding:10px 12px;border-left:3px solid var(--warning);background:var(--surface-muted);font-size:13px}
.overview-primary-grid{align-items:stretch}.overview-primary-grid>.overview-panel{min-height:0}
.model-administration>summary,.device-information-section>summary{margin-bottom:12px}
.model-administration,.device-information-section{padding:0;border:1px solid var(--border);border-radius:var(--radius-card);background:var(--surface)}
/* Freshness notice: a compact info status floating inside the content width;
   Refresh is a secondary action beside the text (admin-behavior-contract.md). */
.admin-live-update{position:fixed;left:50%;bottom:max(16px,env(safe-area-inset-bottom));z-index:40;transform:translateX(-50%);display:flex;align-items:center;gap:10px;width:max-content;max-width:min(calc(100% - 48px),640px);margin:0;padding:6px 6px 6px 12px;border:1px solid var(--status-supported-border);border-radius:var(--radius-control);background:var(--surface);color:var(--graphite);box-shadow:0 4px 16px color-mix(in srgb,var(--graphite) 14%,transparent);font:500 13px/18px var(--font-ui)}
.admin-live-update[hidden]{display:none}
.admin-live-update[data-tone='warning']{border-color:var(--status-tested-border)}
.admin-live-update-icon{display:inline-flex;flex:0 0 auto;color:var(--status-supported-text)}
.admin-live-update[data-tone='warning'] .admin-live-update-icon{color:var(--status-warning-text)}
.admin-live-update-icon .admin-icon,.admin-live-update-dismiss .admin-icon{width:16px;height:16px;margin:0;color:inherit}
.admin-live-update-text{min-width:0}
.admin-live-update .admin-live-update-refresh{flex:0 0 auto;min-height:32px;padding:6px 12px}
.admin-live-update-dismiss{display:inline-flex;flex:0 0 auto;align-items:center;justify-content:center;width:32px;height:32px;padding:0;border:0;border-radius:var(--radius-control);background:transparent;color:var(--secondary)}
.admin-live-update-dismiss:hover{background:var(--surface-muted);color:var(--graphite)}
@media(max-width:760px){.admin-section-nav{flex-basis:100%;order:3}.admin-nav{margin-inline-start:auto}}
@media(max-width:560px){.admin-header-left{width:auto}.admin-nav{width:100%;justify-content:space-between}.admin-section-nav{overflow:visible}}
/* Phone layouts share the same controls and data as desktop. */
#admin-menu-panel,.mobile-filter-options{display:contents}
.admin-nav .admin-mobile-website,.filter-bar .device-mobile-sort{display:none}
@media(max-width:760px){
  :root{--admin-control-height:44px;--admin-control-font-size:16px;--admin-topbar-height:64px}
  .admin-topbar-inner{min-height:64px;flex-direction:row;align-items:center;flex-wrap:nowrap;gap:8px;padding:8px 0}
  .admin-header-left{width:auto;min-width:0;flex:1 1 auto}
  .admin-header-left>.admin-badge,.admin-header-left>.admin-website-link{display:none}
  .admin-brand{gap:6px;font-size:19px}.admin-brand img{width:22px;height:26px}
  #admin-menu-toggle{flex:0 0 auto;min-height:44px;padding:8px 12px}
  #admin-menu-panel{display:block;position:absolute;top:100%;left:0;right:0;max-height:calc(100dvh - 64px);overflow-y:auto;overscroll-behavior:contain;padding:12px 16px 20px;background:var(--surface);border-bottom:1px solid var(--border);box-shadow:0 8px 16px color-mix(in srgb,var(--graphite) 12%,transparent)}
  .admin-topbar:not(.admin-mobile-ready) .admin-topbar-inner{flex-wrap:wrap}
  .admin-topbar:not(.admin-mobile-ready) #admin-menu-panel{position:static;max-height:none;flex-basis:100%}
  main.dashboard{width:100%;max-width:100%;margin:0;padding:20px 16px 32px}.heading-row{margin-bottom:16px}.overview-heading{gap:10px}.overview-period-form{padding:0;border:0;background:none}
  .overview-attention-panel{margin-top:0}.overview-attention-item{gap:6px 10px;padding:12px 0}.overview-detail-link{min-height:36px;display:inline-flex;align-items:center}
  .overview-attention-item span,.overview-activity-item .map-activity-copy>span:not(.overview-activity-label){white-space:normal;overflow:visible;overflow-wrap:anywhere}
  .installation-kpis,.model-statistics,.diagnostic-model-metrics,.provider-metrics{grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}
  .admin-kpi-grid article{min-width:0;padding:12px;min-height:80px}.installation-kpis article:last-child{grid-column:1/-1}
  .installation-kpis{margin-bottom:12px}
  .admin-filter-bar,.filter-bar{min-width:0;max-width:100%;gap:8px}.admin-filter-bar{align-items:stretch}
  .filter-bar label,.filter-search{min-width:0!important;max-width:100%;flex:1 1 100%}
  .filter-bar .filter-clear{width:100%}
  input:not([type='checkbox']):not([type='radio']),select,textarea{font-size:16px!important;max-width:100%;min-width:0;min-height:44px}
  .quick-filter-group{min-width:0;max-width:100%;display:flex;flex-wrap:wrap;overflow-x:visible;flex-basis:100%}
  .quick-filter{flex:0 0 auto;min-height:44px;font-size:13px}
  .mobile-filter-options{display:grid;grid-template-columns:1fr;gap:8px;width:100%}
  .mobile-filter-toggle{width:100%;text-align:left}
  #overview-attention-title{scroll-margin-top:80px}
  .model-page-header{gap:12px;grid-template-columns:auto minmax(0,1fr)}.model-page-image{width:64px;height:64px}.model-page-heading h1{font-size:24px}
  .model-review-alert{gap:8px;align-items:flex-start}.model-review-alert a{min-height:44px;display:flex;align-items:center}
  .provider-action-bar{display:grid;grid-template-columns:1fr 1fr}.provider-action-bar button{width:100%;min-height:44px}.provider-action-overflow{width:100%}.provider-action-bar>p{grid-column:1/-1}
  details>summary{min-height:44px;align-content:center;line-height:1.45}summary:focus-visible{outline:var(--admin-focus-ring);outline-offset:3px}
  .diagnostic-detail-dialog{width:calc(100% - 32px);max-width:none;max-height:calc(100dvh - 16px);margin:auto;border-radius:var(--radius-card)}
  .diagnostic-detail-inner{padding:16px;max-height:calc(100dvh - 16px);overflow:auto;overscroll-behavior:contain}
  .diagnostic-detail-inner>.device-dialog-header{position:sticky;top:-16px;z-index:2;background:var(--surface);padding:12px 0;flex-direction:row;align-items:flex-start;gap:10px}
  .diagnostic-detail-inner .dialog-close{width:44px;min-width:44px;height:44px}
  .diagnostic-detail-summary,.diagnostic-actions-grid{grid-template-columns:1fr}.diagnostic-detail-summary div{grid-template-columns:minmax(80px,.7fr) minmax(0,1fr)}
  .diagnostic-action-form button{min-height:44px}.diagnostic-detail-summary dd{text-align:right}
  .auth-card{margin:24px 16px;max-width:calc(100% - 32px);padding:20px}.auth-card button{min-height:44px}
  .admin-live-update{display:grid;grid-template-columns:auto minmax(0,1fr) auto;gap:2px 10px;left:16px;right:16px;transform:none;width:auto;max-width:none;padding:4px 4px 10px 12px}
  .admin-live-update .admin-live-update-refresh{grid-column:2;grid-row:2;justify-self:start;min-height:44px}
  .admin-live-update-dismiss{grid-column:3;grid-row:1;width:44px;height:44px}
}
@media(max-width:760px){.filter-bar .device-mobile-sort{display:block}.device-filter-bar{position:static}.device-sticky-header{display:none!important}.table-wrap{min-width:0;max-width:100%}.diagnostic-list-wrap{max-height:none}.table-wrap:has(.mobile-record-table){border:0;background:transparent;overflow:visible;border-radius:0}table.mobile-record-table{display:block;min-width:0!important;width:100%;border:0;table-layout:auto}.mobile-record-table colgroup,.mobile-record-table thead{display:none}.mobile-record-table tbody{display:grid;width:100%;gap:12px}.mobile-record-table tbody tr{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px 16px;padding:16px;background:var(--surface);border:1px solid var(--border);border-radius:var(--radius-card);min-width:0}.mobile-record-table tbody td{display:block;width:auto!important;min-width:0;padding:0!important;border:0!important;text-align:left!important;white-space:normal!important;overflow-wrap:anywhere;font-size:13px}.mobile-record-table td a{min-height:44px;display:inline-flex;align-items:center}.mobile-record-table td .provider-name-link{align-items:flex-start}.mobile-record-table td[data-label='']::before{display:none}.mobile-record-table tbody td::before{content:attr(data-label);display:block;margin-bottom:5px;font-size:11px;line-height:1.35;font-weight:600;color:var(--secondary)}.mobile-record-table tbody td:first-child{grid-column:1/-1;font-weight:650}.mobile-record-table tbody td:has(button){grid-column:1/-1}.mobile-record-table td button{min-height:44px;width:100%}.device-model-button{min-height:44px}.device-thumb{width:40px;height:48px}.device-model-copy{min-width:0}.device-model-copy strong{white-space:normal}.provider-pagination,.device-pagination{display:flex;flex-wrap:wrap;gap:8px}.provider-pagination button,.device-pagination button{min-height:44px}.provider-pagination>span{flex:1 1 100%;order:3}.map-statistics-filter-bar .filter-disclosure{width:100%}.map-statistics-filter-bar .filter-disclosure>summary{justify-content:flex-start}.map-statistics-filter-bar .filter-disclosure .disclosure-body{position:static;margin-top:8px;box-shadow:none}}
@media(max-width:760px){.map-statistics-provider-table .mobile-record-table td[data-empty-group='true']{display:none!important}}

/* Full labels and values remain readable at every admin width. */
.overview-attention-item span,.overview-activity-item .map-activity-copy>span:not(.overview-activity-label),.device-model-copy strong,.provider-error{white-space:normal;overflow:visible;text-overflow:clip;overflow-wrap:anywhere;max-width:none}
.overview-panel,.system-health-row,.provider-card,.campaign-card,.admin-kpi-grid article,.provider-metrics article{min-width:0;overflow-wrap:anywhere}
.overview-attention-item .overview-attention-actions{display:inline-flex;align-items:center;justify-content:flex-end;gap:8px}.overview-review-dismiss-form{display:inline-flex;margin:0}.overview-dismiss-button{display:inline-flex;align-items:center;justify-content:center;min-width:32px;min-height:32px;padding:0;border:1px solid var(--border);border-radius:var(--radius-control);background:var(--surface-muted);color:var(--graphite);font-size:20px;line-height:1;cursor:pointer}.overview-dismiss-button:hover{border-color:var(--interactive);color:var(--interactive)}.overview-dismiss-button:focus-visible{outline:var(--admin-focus-ring);outline-offset:2px}.overview-review-notice{display:flex;align-items:center;gap:8px;margin:0 0 10px;padding:9px 12px;border:1px solid var(--border);border-radius:var(--radius-control);background:var(--surface-muted);color:var(--graphite);font-size:13px}.overview-review-notice form{display:inline-flex;margin:0}
.section-heading>div,.heading-row>div,.provider-latest-summary>div,.device-model-copy{min-width:0}
.diagnostic-technical-details pre,.model-technical-details pre,.device-dialog pre,.diagnostic-detail-dialog pre{white-space:pre-wrap;overflow-wrap:anywhere;max-width:100%}
.diagnostic-list-wrap{max-height:none}
@media(min-width:701px){
  .table-wrap table,.device-sticky-header table{width:100%;table-layout:auto}
  .evidence-table-wrap table,.device-table-wrap table,.device-sticky-header table{min-width:960px}
  .evidence-table-wrap th:first-child,.evidence-table-wrap td:first-child{white-space:nowrap!important;overflow:hidden;text-overflow:ellipsis}
  .table-wrap th,.device-sticky-header th{white-space:nowrap;overflow-wrap:normal}
  .table-wrap td{overflow-wrap:break-word}
  .table-wrap .admin-timestamp,.device-sticky-header .admin-timestamp{white-space:normal}
  .model-history-table th:nth-child(4){width:20%}.model-history-table th:nth-child(7){width:11%}
  .device-table-wrap th button,.device-sticky-header th button{min-width:0;width:100%;white-space:normal;text-align:left;justify-content:flex-start}
  .provider-history-wrap th:nth-child(1){width:14%}.provider-history-wrap th:nth-child(2){width:10%}
  .provider-history-wrap th:nth-child(3){width:26%}.provider-history-wrap th:nth-child(4){width:6%}
  .provider-history-wrap th:nth-child(5){width:10%}.provider-history-wrap th:nth-child(6){width:10%}
  .provider-history-wrap th:nth-child(7){width:24%}
  .provider-source-table th:nth-child(1){width:14%}.provider-source-table th:nth-child(2){width:50%}.provider-source-table th:nth-child(3){width:12%}.provider-source-table th:nth-child(4){width:24%}
  .provider-package-table{min-width:640px!important}.provider-package-table th:nth-child(1){width:49%}.provider-package-table th:nth-child(2){width:18%}.provider-package-table th:nth-child(3){width:16%}.provider-package-table th:nth-child(4){width:17%}.provider-package-table td{vertical-align:top}.provider-package-table details{margin-top:8px;font-weight:400}
  .provider-run-table th:nth-child(1){width:5%}.provider-run-table th:nth-child(2),.provider-run-table th:nth-child(3){width:14%}.provider-run-table th:nth-child(4){width:20%}.provider-run-table th:nth-child(5){width:13%}.provider-run-table th:nth-child(6),.provider-run-table th:nth-child(7){width:8%}.provider-run-table th:nth-child(8){width:18%}
  .provider-component{white-space:normal;flex-wrap:wrap}.provider-component-list{min-width:0}
  .overview-trend-chart{min-width:0}
  .diagnostic-detail-dialog,.device-dialog{max-height:calc(100dvh - 48px);overflow:hidden}
  .diagnostic-detail-inner,.device-dialog-inner{max-height:calc(100dvh - 48px);overflow-y:auto;overscroll-behavior:contain}
  .diagnostic-detail-inner>.device-dialog-header,.device-dialog-inner>.device-dialog-header{position:sticky;top:-24px;z-index:2;background:var(--surface);padding:12px 0}
}

/* Shared diagnostic hierarchy for installation dialogs and update reports. */
.diagnostic-detail-dialog{width:min(960px,calc(100% - 32px))}.diagnostic-outcome{margin-block:24px}.diagnostic-issue-section{margin-block:24px}.diagnostic-issue-section h3{font-size:16px;margin-block:0 8px}.github-link-disclosure>summary{min-height:40px;cursor:pointer}.diagnostic-secondary-grid .diagnostic-actions-grid{grid-template-columns:1fr}.diagnostic-secondary-grid .diagnostic-action-form{background:var(--surface-muted)}.diagnostic-outcome h3{margin-block:24px 8px;font-size:16px}.diagnostic-outcome p{margin-block:8px;max-width:75ch}.github-actions{display:flex;flex-wrap:wrap;gap:12px}.github-issue-preview label{display:block;margin-block:12px}.github-issue-preview :is(input,textarea){display:block;width:100%;min-height:40px}.diagnostic-secondary-disclosure>summary{min-height:40px}.github-issue-preview>summary{min-height:40px;cursor:pointer}.github-issue-preview textarea{resize:vertical}.diagnostic-outcome .diagnostic-detail-summary{margin-block-start:12px}
/* Admin audit: consistent page hierarchy, disclosures and connected diagnostics. */
main.dashboard{padding-top:30px}
main.dashboard>.heading-row{align-items:flex-start}
main.dashboard>.heading-row h1{margin:0}
.admin-disclosure:not(.filter-disclosure)>summary{position:relative;list-style:none;padding:10px 14px 10px 36px;margin:0;min-height:44px;line-height:24px;font-size:13px;font-weight:650}
.admin-disclosure:not(.filter-disclosure)>summary::-webkit-details-marker{display:none}
.admin-disclosure:not(.filter-disclosure)>summary::before{content:'';position:absolute;left:13px;top:50%;width:10px;height:10px;background:currentColor;-webkit-mask:var(--fa-chevron-right) center/contain no-repeat;mask:var(--fa-chevron-right) center/contain no-repeat;transform:translateY(-50%);transform-origin:center}
.admin-disclosure[open]:not(.filter-disclosure)>summary::before{transform:translateY(-50%) rotate(90deg)}
.admin-disclosure[open]:not(.filter-disclosure)>summary{margin-bottom:0}
.model-information-columns>details,details.overview-panel,details.model-page-section{padding:0;min-height:0}
.provider-component-list{display:grid!important;grid-template-columns:1fr!important;gap:6px!important;min-width:200px}.provider-component-list>span{display:grid;grid-template-columns:90px max-content;align-items:center;gap:8px}
.overview-chart-grid{stroke:var(--border);stroke-width:1}.overview-chart-axis-label{fill:var(--secondary);font-size:11px}
.model-information-columns{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;align-items:start;margin-top:16px}
.model-information-columns>details{margin:0;min-width:0}
.model-information-columns .model-information-list{max-width:none;margin-top:14px}
.model-information-columns .model-information-list div{padding:10px 12px;gap:4px 16px;grid-template-columns:minmax(100px,1fr) minmax(0,3fr)}
.model-information-columns .device-information-section .model-information-list div{grid-template-columns:minmax(100px,1fr) minmax(0,3fr)}
.model-information-columns .model-information-list dt,.model-information-columns .model-information-list dd{min-width:0;text-align:left;overflow-wrap:anywhere}
.model-information-columns.device-overview-sections{grid-template-columns:minmax(0,1fr)}
.model-detail-page details:is(.model-administration,.device-information-section,.model-technical-details).admin-disclosure{padding:0}

.model-detail-page details:is(.model-administration,.device-information-section,.model-technical-details).admin-disclosure[open]>summary{margin-bottom:16px}
.device-information-section{container-type:inline-size}.device-key-facts{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:24px;margin:0}.device-key-facts>div{min-width:0}.device-key-facts dt{color:var(--secondary);font-size:13px;line-height:20px}.device-key-facts dd{margin:6px 0 0;font-size:16px;line-height:24px;font-weight:600;overflow-wrap:anywhere}@container(min-width:720px){.device-key-facts{grid-template-columns:repeat(4,minmax(0,1fr))}}
.device-information-note{margin:24px 0 0;color:var(--secondary);font-size:13px;line-height:20px;text-wrap:pretty}.device-information-more{display:flex;flex-wrap:wrap;align-items:start;gap:12px 24px;margin-top:16px}.device-extra-specifications{flex:1 1 320px;min-width:0}.device-specification-link{display:inline-flex;align-items:center;gap:6px;min-height:40px;max-width:100%;font-size:13px;line-height:20px;text-wrap:pretty}.device-specification-link svg{flex:none}
.device-overview-sections .admin-disclosure:not([open])>summary:dir(rtl)::before{transform:translateY(-50%) rotate(135deg)}
.device-overview-sections .device-extra-specifications .model-information-list{border:0;border-radius:0;background:transparent}.device-overview-sections .device-extra-specifications .model-information-list div{padding-inline:0;grid-template-columns:minmax(0,1fr) minmax(0,2fr);text-align:start}.device-overview-sections .device-extra-specifications :is(dt,dd){text-align:start}
@media(max-width:700px){.device-overview-sections .admin-disclosure:not(.filter-disclosure)>summary,.device-specification-link{min-height:44px}}
.world-map-controls{display:flex;align-items:center;gap:8px;padding:4px 10px 10px}
.world-map-controls button{min-height:40px;min-width:40px;padding:6px 10px;border-radius:var(--admin-control-radius);background:var(--surface);color:var(--interactive);border:1px solid var(--border)}
.world-map-controls span{font-size:12px;color:var(--secondary)}
.world-map-svg{height:420px;min-height:300px;touch-action:none;cursor:grab;overflow:hidden;user-select:none;-webkit-user-select:none}.world-map-svg *{user-select:none;-webkit-user-select:none;-webkit-user-drag:none}
.world-map-svg:active{cursor:grabbing}
.world-map-svg:focus-visible{outline:var(--admin-focus-ring);outline-offset:-2px}
.world-map-svg svg{fill:var(--surface)}.world-map-svg.leaflet-container{padding:0;background:var(--surface-muted);font-family:var(--font-ui)}.world-map-svg .leaflet-control-attribution{font-size:10px;background:var(--surface);color:var(--secondary)}
.world-map-svg svg path{vector-effect:non-scaling-stroke}
.world-map-country.is-region-highlight{fill:var(--interactive)!important;stroke:var(--graphite);stroke-width:2}
.region-map-link{display:inline;padding:0;border:0;border-radius:0;background:none;color:var(--interactive);text-align:left;text-decoration:underline;text-underline-offset:3px;white-space:normal;font:inherit;cursor:pointer}
.region-map-link:hover{background:none;color:var(--graphite)}
.map-statistics-coverage-layout{align-items:stretch;grid-template-columns:minmax(0,3fr) minmax(300px,1fr)}
@media(max-width:1100px){.map-statistics-coverage-layout{grid-template-columns:minmax(0,1fr)}}
.system-health-row[hidden]{display:none}
.test-data-activity-caption{display:block;width:100%;max-width:100%;box-sizing:border-box;white-space:normal;overflow-wrap:anywhere;text-align:left;padding:12px;font-size:13px;font-weight:650}
[id]{scroll-margin-top:calc(var(--admin-topbar-height,100px) + 16px)}
.world-map-tooltip{top:64px}
@media(max-width:900px){.model-information-columns{grid-template-columns:1fr}.model-information-columns .device-information-section .model-information-list div{grid-template-columns:minmax(100px,1fr) minmax(0,3fr)}}
@media(max-width:760px){main.dashboard{padding-top:20px}.model-information-columns .model-information-list div{grid-template-columns:1fr}}
@media(max-width:900px){table.health-check-table:not(.health-weekly-table),table.health-check-table:not(.health-weekly-table)>tbody{display:block;width:100%}.health-check-table:not(.health-weekly-table) colgroup,.health-check-table:not(.health-weekly-table) thead{display:none}.health-check-table tr.system-health-row{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:center;gap:6px 12px;padding:12px 0;border-bottom:1px solid color-mix(in srgb,var(--border) 78%,transparent)}.health-check-table tbody tr.system-health-row:last-child,.health-check-table tbody tr.system-health-row:nth-last-child(2):has(+ .health-details-row[hidden]){border-bottom:0}.health-check-table tr.system-health-row>*{display:block;min-width:0;padding:0!important;border:0!important}.health-check-table tr.system-health-row>.column-status{justify-self:end}.health-check-table tr.system-health-row>.health-check-reason{grid-column:1/-1}.health-check-table tr.system-health-row>.health-check-more{justify-self:end}.health-check-table tr.health-details-row{display:block;border-bottom:1px solid color-mix(in srgb,var(--border) 78%,transparent)}.health-check-table tr.health-details-row>td[colspan]{display:block;padding:0 0 12px!important;border:0!important}.health-check-table tbody tr.system-health-row:has(+ .health-details-row:not([hidden])){border-bottom:0}.health-details-toggle{min-height:44px}.health-panel-summary .section-link{margin-left:0}}
@media(min-width:901px) and (max-width:1100px){.health-col-check{width:170px}.health-col-when{width:150px}.health-col-more{width:104px}}
/* Admin UI standard: one navigation hierarchy, one control rhythm, concentric surfaces. */
body{font-family:var(--font-ui);text-wrap:pretty}
h1,h2,h3,h4{font-family:var(--font-ui);letter-spacing:-.015em;text-wrap:balance}
.admin-section-nav{align-items:center;gap:16px}
.admin-nav-group{display:flex;align-items:center;gap:4px;min-width:0}
.admin-section-nav details{position:relative;flex:0 0 auto}
.admin-section-nav details>summary{display:inline-flex;align-items:center;min-height:34px;padding:7px 9px;border-radius:var(--admin-control-radius);color:var(--secondary);cursor:pointer;font-size:var(--admin-type-control-size);font-weight:650;list-style:none;white-space:nowrap}
.admin-section-nav details>summary::-webkit-details-marker{display:none}
.admin-section-nav details>summary::after{content:'';display:inline-block;width:10px;height:10px;margin-inline-start:6px;background:var(--secondary);-webkit-mask:var(--fa-chevron-down) center/contain no-repeat;mask:var(--fa-chevron-down) center/contain no-repeat}
.admin-section-nav details>summary:hover,.admin-section-nav details>summary.active{background:var(--surface-muted);color:var(--interactive)}
.admin-tools-popover{display:grid;gap:2px;position:absolute;z-index:25;top:calc(100% + 7px);left:0;right:auto;min-width:190px;padding:7px;border:1px solid var(--border);border-radius:var(--radius-control);background:var(--surface);box-shadow:0 14px 34px color-mix(in srgb,var(--graphite) 16%,transparent)}
.admin-tools-popover a{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:8px 9px;color:var(--graphite);font-size:12px;font-weight:650;text-decoration:none}
.admin-tools-popover a:hover,.admin-tools-popover a.active{background:var(--surface-muted);color:var(--interactive)}
.admin-tools-popover a.active{border-radius:6px}
.admin-user.active{padding:6px 8px;border-radius:var(--admin-control-radius);background:var(--surface-muted);color:var(--interactive)}
.filter-clear{align-self:center;flex:0 0 auto;min-width:58px}
.filter-bar .filter-clear{margin-left:0}
.admin-icon{display:inline-block;width:1em;height:1em;flex:0 0 auto;vertical-align:-.15em;fill:currentColor}
.sort-indicator{display:inline-block;width:.65em;height:1em;vertical-align:-.15em;background:currentColor;-webkit-mask:var(--fa-sort) center/contain no-repeat;mask:var(--fa-sort) center/contain no-repeat;opacity:.55}
.sort-indicator[data-sort="ascending"]{-webkit-mask-image:var(--fa-sort-up);mask-image:var(--fa-sort-up);opacity:1}
.sort-indicator[data-sort="descending"]{-webkit-mask-image:var(--fa-sort-down);mask-image:var(--fa-sort-down);opacity:1}
.device-table-wrap tbody tr,.evidence-model-row{cursor:default}
.device-model-button{border-radius:6px}
.device-model-button:focus-visible{outline:var(--admin-focus-ring);outline-offset:3px}
.device-column-model{width:20%}.device-column-variant{width:16%}.device-column-attempts{width:9%}.device-column-successful{width:10%}
.info-control{position:relative}
.info-control::before{content:'';position:absolute;inset:-10px}
.overview-panel,.provider-card,.campaign-card{border-radius:var(--radius-card)}
.table-wrap,.filter-bar{border-radius:var(--radius-card)}
button,.copy-button,.secondary-button{transition:background-color .15s ease,border-color .15s ease,color .15s ease,transform .12s ease}
button:active:not(:disabled),.copy-button:active{transform:scale(.96)}
.filter-bar button:active,.world-map-controls button:active{transform:none}
.filter-bar label,.inline-filter-row label{display:flex;flex-direction:column;gap:6px}
.inline-filter-row label>.sr-only{position:static;width:auto;height:auto;margin:0;overflow:visible;clip:auto;clip-path:none;white-space:normal;font-size:12px;font-weight:650;color:var(--secondary)}
.filter-bar label>input,.filter-bar label>select,.inline-filter-row label>input,.inline-filter-row label>select{flex:none}
.inline-filter-row{align-items:flex-end}
.inline-filter-row label{min-width:0}
.inline-filter-row label>input,.inline-filter-row label>select{width:100%;height:var(--admin-control-height)}
@media(max-width:700px){.inline-filter-row{align-items:stretch}.inline-filter-row label{flex-basis:auto}}
.filter-bar>.filter-disclosure{align-self:flex-end}
.filter-bar>.filter-clear{align-self:flex-end}
.filter-bar>.results-count{align-self:flex-end;min-height:var(--admin-control-height);display:flex;align-items:center;white-space:normal}
@media(max-width:700px){
  .filter-bar input,.filter-bar select{font-weight:400}
  .filter-bar .device-mobile-sort{display:flex;flex-direction:column;gap:6px}
  .filter-bar .device-mobile-sort select{width:100%;margin:0}
}
/* Compact coverage lists keep names, counts and activity readable in the sidebar. */
.map-statistics-popularity .table-wrap{border:0;border-radius:0;overflow:visible}
.map-statistics-popularity .table-wrap .admin-table{display:block;width:100%;min-width:0;table-layout:fixed}
.map-statistics-popularity .table-wrap .admin-table thead{position:absolute;display:block;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap}
.map-statistics-popularity .table-wrap .admin-table tbody{display:grid;gap:0;width:100%}
.map-statistics-popularity .table-wrap .admin-table tbody tr{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:4px 12px;padding:8px 0;background:none;border:0;border-bottom:1px solid var(--border);border-radius:0;min-width:0}
.map-statistics-popularity .table-wrap .admin-table tbody tr:last-child{border-bottom:0}
.map-statistics-popularity .table-wrap .admin-table tbody tr[hidden]{display:none}.map-statistics-popularity .table-wrap .admin-table tbody tr:has(+tr[hidden]){border-bottom:0}
@media(min-width:1101px){.map-statistics-coverage-layout>.map-statistics-popularity{contain:size;overflow:hidden}}
.map-statistics-popularity .table-wrap .admin-table td{display:block;width:auto!important;min-width:0;padding:0!important;border:0!important;white-space:normal;overflow-wrap:anywhere;text-align:left!important;font-size:13px}
.map-statistics-popularity .table-wrap .admin-table td.popular-map-count{grid-column:2;grid-row:1;align-self:start;text-align:right!important;white-space:nowrap}
.map-statistics-popularity .table-wrap .admin-table td[colspan]{grid-column:1/-1}
.map-statistics-popularity .table-wrap .admin-table td::before{display:none}
.map-statistics-popularity .table-wrap .admin-table td.popular-map-count::after{content:none}
.map-statistics-popularity .table-secondary,.map-statistics-popularity code{white-space:normal;overflow-wrap:anywhere;font-size:11px}
.map-statistics-page .popular-map-name-content{display:grid;min-width:0;gap:2px}
.map-statistics-page .popular-map-name{min-width:0;line-height:1.35;overflow-wrap:anywhere}
.map-statistics-page .popular-map-detail{display:block;min-width:0;color:var(--secondary);font-size:11px;font-weight:400;line-height:1.35;overflow-wrap:anywhere}
.map-statistics-popularity .table-wrap .region-map-link{position:relative;display:inline-flex;width:auto;max-width:100%;min-height:0;padding:0;align-items:flex-start;color:inherit;font-weight:400;line-height:1.35;text-align:left;text-decoration:none;white-space:normal;overflow-wrap:anywhere}
.map-statistics-popularity .table-wrap .region-map-link::after{content:'';position:absolute;inset:0;min-width:44px;min-height:44px}
.map-statistics-popularity .region-map-link:hover,.map-statistics-popularity .region-map-link:focus-visible{text-decoration:underline}
.map-statistics-world-map-card .section-heading{flex-wrap:wrap}
.map-statistics-world-map-card .map-statistics-world-map{padding:0;min-height:0}
.map-statistics-world-map-card .world-map-svg{height:auto;min-height:0;aspect-ratio:900 / 365}
.map-statistics-world-map-card .world-map-controls{position:absolute;z-index:3;top:8px;left:8px;padding:0;gap:6px}
.map-statistics-world-map-card .world-map-controls span{padding:4px 6px;border-radius:var(--admin-control-radius);background:var(--surface)}
@media(max-width:700px){.map-statistics-world-map-card .world-map-controls{position:static;padding:8px;gap:4px}.map-statistics-world-map-card .world-map-controls button{padding:6px 8px;white-space:nowrap}.map-statistics-world-map-card .world-map-controls span{padding:4px}}
.map-statistics-popularity .table-wrap th{white-space:normal;overflow-wrap:normal}
@media(max-width:700px){.world-map-controls button{min-width:44px;min-height:44px}}
@media(max-width:700px){
  .filter-clear{width:100%;min-height:44px}
}
/* Information hierarchy: summaries first, complete evidence on demand. */
.identity-outcome{padding:16px;background:var(--off-white);border-radius:var(--radius-card);margin:12px 0}
.identity-outcome h3{margin:0 0 8px;font-size:16px}.identity-outcome p{margin:4px 0}
.diagnostic-id code{overflow-wrap:anywhere}
.overview-activity-item:has(>.download-history){display:block}
/* Model sources (owner decision 2026-10-06, admin-behavior-contract.md "Model sources"): one summary card, the Installations filter bar, a sortable table, and a detail made of Admin cards spaced by --admin-card-gap. */
.identification-page>h1{margin:0 0 20px;text-wrap:balance}.identification-page>h1+*{margin-top:0}.identification-page summary{cursor:pointer;min-height:44px;align-content:center}.identification-page :is(input,textarea)::placeholder{color:var(--admin-placeholder,var(--secondary));opacity:1}.identification-page :is(a,button,input,textarea,select,summary):focus-visible{outline:var(--admin-focus-ring);outline-offset:3px}.identification-page :is(a,p,strong,dd){overflow-wrap:anywhere}.identification-page .section-link{color:var(--graphite);text-decoration:underline;text-underline-offset:3px}
.identification-list>.filter-bar{margin-top:0}.identification-table-wrap table{min-width:640px}.identification-table td .identification-choice{display:inline;padding:0;border:0;background:none;color:inherit;text-decoration:none}.identification-table td .identification-choice:hover strong{text-decoration:underline}.identification-badges{display:flex;flex-wrap:wrap;gap:6px}.identification-list .admin-empty{margin:12px 0 0}.identification-list>.provider-pagination{margin-top:12px}
.identification-empty h2{margin:0 0 6px;font:600 18px/26px var(--font-ui)}.identification-empty p{margin:0 0 10px;max-width:75ch;line-height:1.5}.identification-not-found{margin:0;color:var(--error-text);background:var(--error-surface);padding:16px;border-radius:var(--radius-card)}
.identification-workspace-nav{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:4px 12px}.identification-workspace-nav a{display:inline-flex;align-items:center;gap:4px;min-height:32px;text-underline-offset:3px}
.identification-workspace-nav,.identification-workspace,.identification-model-detail-link{max-width:960px}
.identification-workspace .identity-mappings{display:grid;gap:var(--admin-card-gap);margin:0;padding:0}.identification-workspace .admin-card{margin:0}
.identification-workspace .identity-mapping-source{display:grid;gap:16px}
.identification-workspace h3{margin:0 0 6px;font:600 14px/20px var(--font-ui);color:var(--secondary)}.identification-workspace h4{margin:0 0 8px;font:600 14px/20px var(--font-ui)}.identification-workspace p{max-width:75ch;line-height:1.5}
.identification-step{min-width:0}.identification-compare{display:grid;grid-template-columns:minmax(0,1fr) auto minmax(0,1fr);gap:12px;align-items:stretch}.identification-compare>.identification-step{min-width:0;padding:12px 14px;border:1px solid var(--border);border-radius:var(--radius-control);background:var(--surface)}.identification-compare-arrow{align-self:center;color:var(--secondary);font-size:18px}
.identification-reported-name,.identification-match>strong{display:block;font-size:16px;line-height:24px}.identification-source-link{margin-top:6px;font-size:13px}.identification-source-unavailable{color:var(--secondary);font-size:13px}.identification-match{display:grid;align-content:start;gap:0}.identification-match>span{margin-top:6px;color:var(--secondary);font-size:13px}
.identification-other-models ul{display:grid;margin:0;padding:0;list-style:none}.identification-other-models li{display:flex;align-items:center;justify-content:space-between;gap:12px;min-height:44px;padding:6px 0;border-top:1px solid var(--border)}.identification-other-models li:last-child{border-bottom:1px solid var(--border)}
.identification-confirm{padding:16px;border-radius:var(--radius-control);background:var(--surface-muted)}.identification-existing-decision{display:flex;flex-wrap:wrap;align-items:center;gap:6px 8px;margin:0 0 12px;font-size:13px}.identification-existing-decision>span:last-child{flex:1 1 100%;color:var(--secondary)}
.identification-workspace .identity-mapping-review{display:grid;grid-template-columns:1fr;gap:12px}.identification-workspace .identity-mapping-review label{display:grid;gap:6px;font-size:14px;font-weight:600}.identification-workspace .identity-mapping-review textarea{width:100%;min-width:0;font:inherit;border-radius:var(--admin-control-radius,var(--radius-control))}
.identification-decision-actions{display:flex;align-items:center;gap:8px;flex-wrap:wrap}.identification-decision-actions button{min-height:44px}.identity-mapping-review .identification-decision-actions button.secondary-button{color:var(--interactive);background:var(--surface);border:1px solid var(--border)}.identity-mapping-review .identification-decision-actions button.secondary-button:hover{background:var(--surface-muted)}
.identification-workspace .admin-action-status:empty{display:none}.identification-workspace .admin-action-status{margin:0;color:var(--graphite);font-size:13px}.identification-workspace .admin-action-status[data-error="true"]{color:var(--error-text)}
.identification-workspace .identification-technical{padding:0}.identification-page .identification-workspace .identification-technical>.disclosure-body{display:grid;gap:16px;padding:4px 20px 18px}.identification-page .identification-technical .model-information-list{border:0;border-top:1px solid var(--border);border-radius:0;background:none}.identification-technical .disclosure-body>p{margin:0}.identification-technical .disclosure-body>section{padding-top:16px;border-top:1px solid var(--border)}.identification-technical .model-information-list{margin:0}.identification-technical ul{margin:8px 0 0;padding-inline-start:20px}
.identification-model-detail-link{margin:0;font-size:13px;font-weight:700}
@media(max-width:760px){.identification-compare{grid-template-columns:minmax(0,1fr)}.identification-compare-arrow{display:none}.identification-other-models li{align-items:flex-start;flex-direction:column;gap:4px;padding:8px 0}.identification-confirm{padding:14px}.identification-decision-actions{display:grid;grid-template-columns:1fr}.identification-decision-actions button{width:100%}.identification-page :is(input,textarea){font-size:16px!important}.identification-filter-bar .identification-search-submit{flex:1 1 100%}}

.download-history{margin:0;font-size:13px}.download-history>summary{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:3px 16px;list-style:none;cursor:pointer;min-height:44px;align-content:center}.download-history>summary::-webkit-details-marker{display:none}.download-history>summary .overview-activity-label::before{content:'';display:inline-block;width:8px;height:10px;margin-right:8px;background:var(--interactive);-webkit-mask:var(--fa-chevron-right) center/contain no-repeat;mask:var(--fa-chevron-right) center/contain no-repeat;transform-origin:center}.download-history[open]>summary .overview-activity-label::before{transform:rotate(90deg)}.download-history>summary>time{grid-column:2;grid-row:1 / span 2;align-self:center;color:var(--secondary);font-size:12px;white-space:nowrap}.overview-activity-item .download-history .download-context{grid-column:1;grid-row:2;display:block;margin-left:18px;color:var(--secondary);font-size:12px;font-weight:400;overflow-wrap:anywhere}.download-history>summary:focus-visible{outline:var(--admin-focus-ring);outline-offset:3px;border-radius:4px}.download-history[open]>.download-timeline{margin-top:6px;margin-left:18px}.download-elapsed{font-variant-numeric:tabular-nums}@media(max-width:480px){.download-history>summary{gap:3px 8px}.download-history>summary>time{font-size:11px}}

.download-timeline{display:flex;flex-wrap:wrap;gap:8px 16px;list-style:none;padding:0;margin:0 0 4px;font-size:13px}
.download-timeline li{display:flex;align-items:center;flex-wrap:wrap;gap:4px}.download-timeline li+li::before{content:'';display:inline-block;width:10px;height:10px;margin-right:8px;background:var(--secondary);-webkit-mask:var(--fa-arrow-right) center/contain no-repeat;mask:var(--fa-arrow-right) center/contain no-repeat}
.download-timeline .admin-icon,.download-timeline .download-phase-icon{width:14px;height:14px;flex:none}.download-timeline time{font-size:12px;font-variant-numeric:tabular-nums;position:static}
@media(max-width:700px){.download-history summary{min-height:44px}}

@media(prefers-reduced-motion:reduce){
  *,*::before,*::after{scroll-behavior:auto!important;animation-duration:.01ms!important;animation-iteration-count:1!important;transition-duration:.01ms!important}
}

/* One compact geometry for plain and expandable map events. */
.map-activity-row,.map-activity-row:first-child{padding:8px 0;min-width:0}.map-activity-row>.map-activity-copy,.map-activity-row>time{grid-row:1}
.map-activity-row>.map-activity-copy,.map-activity-row .download-history>summary{min-height:44px;align-content:center;row-gap:3px;line-height:1.4}
.map-activity-row>.map-activity-copy{grid-template-columns:minmax(0,1fr)}
.map-activity-row .download-history>summary{padding:0;margin:0;column-gap:10px;font-weight:400}
.map-activity-row .overview-activity-label{display:flex;align-items:center;gap:7px;font-size:13px;font-weight:750;line-height:1.4}
.map-activity-row .overview-activity-label>a{color:var(--interactive);text-underline-offset:3px}
.map-activity-row .overview-activity-label .download-phase-icon{width:14px;height:14px;flex:0 0 14px}
.map-activity-row .download-history>summary .overview-activity-label::before{content:none}
.map-activity-row .download-history>summary .overview-activity-label::after{content:'';display:inline-block;width:8px;height:10px;margin-left:5px;background:var(--secondary);-webkit-mask:var(--fa-chevron-right) center/contain no-repeat;mask:var(--fa-chevron-right) center/contain no-repeat;transform-origin:center}
.map-activity-row .download-history[open]>summary .overview-activity-label::after{transform:rotate(90deg)}
.map-activity-row>.map-activity-copy>span:not(.overview-activity-label),.map-activity-row .download-history .download-context{margin:0 0 0 21px;font-size:12px;font-weight:400;line-height:1.4;color:var(--secondary)}
.map-activity-row .download-history[open]>.download-timeline{margin:6px 0 0 21px}
.map-activity-row>time,.map-activity-row .download-history>summary>time{font-size:12px;font-variant-numeric:tabular-nums}
.map-activity-info .overview-activity-label{color:var(--interactive)}
.map-activity-success .overview-activity-label{color:var(--success-text)}
.map-activity-error .overview-activity-label{color:var(--danger)}
.map-activity-warning .overview-activity-label{color:var(--status-tested-text)}
.map-activity-neutral .overview-activity-label{color:var(--secondary)}
@media(max-width:480px){.map-activity-row{grid-template-columns:minmax(0,1fr)}.map-activity-row>time{grid-column:1;grid-row:3;margin-left:21px}.map-activity-row .download-history>summary{grid-template-columns:minmax(0,1fr)}.map-activity-row .download-history>summary>time{grid-column:1;grid-row:3;margin-left:21px}.map-activity-row>.map-activity-copy{grid-row:1}}

/* Map statistics compact summary, popularity views, and table alignment. */
.admin-table th.column-number,.admin-table td.column-number,.admin-table th.numeric,.admin-table td.numeric{text-align:right}
.admin-table th.column-status,.admin-table td.column-status{text-align:left}
.admin-table th.column-date,.admin-table td.column-date{text-align:right}
.popularity-search-label{display:block;margin:0 0 6px;color:var(--secondary);font-size:12px;font-weight:650}
.map-statistics-ranking>input{width:100%;min-width:0;margin:0 0 12px}
.map-statistics-ranking .popular-maps-table{min-width:0}
.map-statistics-ranking .popular-map-count{text-align:right!important}
.map-statistics-page>.admin-disclosure,.map-statistics-page>.map-events-card{margin-top:16px}
.map-statistics-trends{margin-top:16px}
@media(max-width:700px){.map-statistics-ranking>input{min-height:44px}}
@media(min-width:761px){
  .diagnostic-list-table :is(th,td).column-number,.diagnostic-list-table :is(th,td).column-date{text-align:right}
  .diagnostic-list-table :is(th,td).column-status{text-align:left}
}
@media(max-width:760px){
  .filter-bar>.results-count{width:auto;flex:1 1 180px;margin-left:0}
  .filter-bar>.filter-clear{width:auto;flex:0 0 auto}
  /* Phone filter bars: More filters and Filters and sorting split one row; an
     open panel lays out full width below that row; the result count is one
     tight line, with Clear beside it when shown. */
  .filter-bar>.results-count{min-height:0;align-self:center}
  .filter-bar>.filter-clear{align-self:center}
  .filter-bar>.filter-disclosure .disclosure-body{position:static;margin-top:8px;box-shadow:none}
  .filter-bar>.mobile-filter-toggle,.filter-bar>.filter-disclosure:has(~.mobile-filter-toggle:not([hidden])){flex:0 0 calc(50% - 4px);width:auto;min-width:0;align-self:flex-start}
  .filter-bar>.mobile-filter-toggle{text-align:center}
  .filter-bar:has(>.mobile-filter-toggle:not([hidden]))>.filter-search{flex-basis:100%}
  .filter-bar>.filter-disclosure:has(~.mobile-filter-toggle:not([hidden])) .disclosure-body{width:calc(200% + 8px)}
  /* Top maps reads like Top countries: name with provider · date below on the
     left, the count on the right, no per-row labels or cards. */
  .map-statistics-ranking .table-wrap{border:0;border-radius:0;background:none;overflow:visible}
  .map-statistics-ranking .popular-maps-table{display:block;width:100%;min-width:0;border:0}
  .map-statistics-ranking .popular-maps-table thead{display:none}
  .map-statistics-ranking .popular-maps-table tbody{display:grid;width:100%}
  .map-statistics-ranking .popular-maps-table tbody tr{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:baseline;gap:4px 12px;padding:8px 0;background:none;border:0;border-bottom:1px solid var(--border);min-width:0}
  .map-statistics-ranking .popular-maps-table tbody tr:last-child{border-bottom:0}
  .map-statistics-ranking .popular-maps-table td{display:block;width:auto!important;min-width:0;padding:0!important;border:0!important;text-align:left!important;white-space:normal;overflow-wrap:anywhere;font-size:13px}
  .map-statistics-ranking .popular-maps-table td.popular-map-count{text-align:right!important;white-space:nowrap}
  .map-statistics-ranking .popular-maps-table td[colspan]{grid-column:1/-1}
  .map-statistics-popularity .table-wrap .popular-maps-table tbody tr{align-items:baseline}
  .map-statistics-popularity .table-wrap .popular-maps-table td.popular-map-count{align-self:baseline}
}

/* Admin scrollbars are visually hidden without changing the scroll surface. */
.admin-shell :where(
  .table-wrap,
  .overview-chart-wrap,
  .identity-search-results,
  #admin-menu-panel,
  .admin-section-nav,
  .quick-filter-group,
  .diagnostic-detail-inner,
  .device-dialog-inner,
  .generated-url,
  .device-table-wrap,
  .provider-detail .provider-history-wrap,
  .map-statistics-popularity,
  .audit-technical-details code
){scrollbar-width:none;-ms-overflow-style:none}
.admin-shell :where(
  .table-wrap,
  .overview-chart-wrap,
  .identity-search-results,
  #admin-menu-panel,
  .admin-section-nav,
  .quick-filter-group,
  .diagnostic-detail-inner,
  .device-dialog-inner,
  .generated-url,
  .device-table-wrap,
  .provider-detail .provider-history-wrap,
  .map-statistics-popularity,
  .audit-technical-details code
)::-webkit-scrollbar{display:none;width:0;height:0}

/* Shared KPI and error-counter presentation across the operational views. */
.admin-kpi-panel{display:block;margin-top:0;margin-bottom:0}
.overview-page>.admin-kpi-panel{margin-top:16px}
.overview-page>.heading-row+.overview-panel{margin-top:0}
.overview-page>.overview-panel{margin-top:16px}
.overview-attention-item{padding-block:6px}
.overview-primary-grid{gap:16px;margin-top:16px}
.overview-activity-panel{margin-top:16px}
.overview-activity-device{display:inline;overflow-wrap:anywhere;color:inherit;font:inherit;text-decoration:underline;text-underline-offset:3px}
.overview-activity-device:hover{text-decoration:underline;text-underline-offset:3px}
.dashboard>.heading-row{margin-bottom:20px}
.system-health-page .heading-row+.filter-bar{margin-top:0}
.provider-table-wrap td.column-status .table-secondary{display:block;min-width:0;overflow-wrap:anywhere;white-space:normal}
.provider-detail .provider-action-bar{margin-bottom:12px}
.provider-detail .provider-state-grid{margin-top:4px}
.map-statistics-page>.map-statistics-coverage-layout{margin-top:16px}
.installation-kpis+.evidence-section{margin-top:16px}
:is(.device-summary-sync,.provider-summary-sync){font-size:var(--admin-type-helper-size)}
.admin-error-counter{color:var(--graphite)!important;font:inherit;font-variant-numeric:tabular-nums}
.admin-error-counter.is-positive{color:var(--danger)!important}
.error-count{display:inline-flex;align-items:center;justify-content:center;min-width:0;min-height:0;padding:0;border:0;border-radius:0;color:inherit;font-weight:inherit;text-decoration:none}
.error-count:hover .admin-error-counter,.error-count:focus-visible .admin-error-counter{text-decoration:underline;text-underline-offset:3px}
.admin-table th.column-number>button,.admin-table th.column-number>.device-sort-button{justify-content:flex-end;text-align:end}
.admin-table th.column-status>button,.admin-table th.column-status>.device-sort-button{justify-content:center;text-align:center}
.admin-table th.column-date>button,.admin-table th.column-date>.device-sort-button{justify-content:flex-end;text-align:end}
.admin-table td.column-number,.admin-table th.column-number{font-variant-numeric:tabular-nums}
@media(min-width:761px){.evidence-table-wrap th.column-number,.evidence-table-wrap td.column-number,.evidence-table-wrap th.column-date,.evidence-table-wrap td.column-date{text-align:right!important}.evidence-table-wrap th.column-number>.device-sort-button,.evidence-table-wrap th.column-date>.device-sort-button{width:100%;justify-content:flex-end;text-align:end}.evidence-table-wrap th.column-status,.evidence-table-wrap td.column-status{text-align:left}.evidence-table-wrap th.column-status>.device-sort-button{justify-content:flex-start;text-align:start}.evidence-table-wrap td.column-date,.evidence-table-wrap td.column-date .admin-timestamp{white-space:nowrap}}
.device-table-wrap th.column-number>.device-sort-button,.device-sticky-header th.column-number>.device-sort-button{width:100%}
.device-table-wrap th.column-status>.device-sort-button,.device-sticky-header th.column-status>.device-sort-button{width:100%}
.device-table-wrap th.column-date>.device-sort-button,.device-sticky-header th.column-date>.device-sort-button{width:100%}
@media(max-width:700px){.admin-kpi-panel{padding:16px}}

/* Identity Review is a compact fact summary, not a repeated evidence form. */
.identity-review-form{grid-column:auto}
.identity-picker-heading{display:flex;align-items:center;justify-content:space-between;gap:12px}
.identity-picker-heading h4{margin:0}
.identity-reported-device{margin:0 0 4px;font-size:14px}
.identity-reported-also{margin:0 0 12px;color:var(--secondary);font-size:12px;overflow-wrap:anywhere}
.identity-facts{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin:14px 0}
.identity-fact{min-width:0;padding:10px 11px;border:1px solid var(--border);border-radius:var(--radius-control);background:var(--surface)}
.identity-fact-heading{display:flex;align-items:center;gap:6px;color:var(--secondary);font-size:11px;font-weight:700}
.identity-fact-icon{display:inline-flex;align-items:center;justify-content:center;width:16px;height:16px}
.identity-fact strong{display:block;margin-top:5px;overflow-wrap:anywhere;font-size:13px;line-height:1.35}
.identity-fact small{display:block;margin-top:5px;color:var(--secondary);font-size:10px}
.identity-fact-match{border-color:var(--status-success-border);background:var(--status-success-surface)}
.identity-fact-match .identity-fact-icon{color:var(--status-success-text)}
.identity-fact-conflict{border-color:var(--status-error-border);background:var(--status-error-surface)}
.identity-fact-conflict .identity-fact-icon{color:var(--status-error-text)}
.identity-fact-missing{border-color:var(--border);background:var(--surface-muted)}
.identity-fact-missing .identity-fact-icon{color:var(--secondary)}
.identity-selected-model{display:grid;gap:3px;margin-top:12px;padding:12px 14px;border-left:3px solid var(--interactive);background:var(--surface-muted)}
.identity-selected-model strong{overflow-wrap:anywhere}.identity-selected-model small{color:var(--secondary);font-size:11px}
.identity-picker{margin-top:10px}.identity-picker[hidden]{display:none}
.identity-search-results{display:grid;gap:4px;max-height:260px;margin-top:6px;overflow:auto;padding:4px;border:1px solid var(--border);border-radius:var(--radius-control);background:var(--surface)}
.identity-picker-option{display:block;width:100%;min-height:38px;margin:0;padding:8px 10px;border:0;border-radius:6px;background:transparent;color:var(--graphite);font:inherit;font-size:12px;text-align:left;white-space:normal;overflow-wrap:anywhere}
.identity-picker-option:hover{background:var(--surface-muted)}.identity-picker-option:focus-visible{background:var(--surface-muted);outline:var(--admin-focus-ring);outline-offset:-3px}
.identity-picker-empty{margin:8px;color:var(--secondary);font-size:12px}
.identity-review-actions{display:flex;flex-wrap:wrap;gap:8px;margin-top:10px}.identity-review-actions button[disabled]{opacity:.55;cursor:not-allowed}
.identity-conflict-warning{margin:10px 0;padding:9px 11px;border:1px solid var(--status-error-border);border-radius:var(--radius-control);background:var(--status-error-surface);color:var(--status-error-text);font-size:12px;overflow-wrap:anywhere}
@media(max-width:700px){.identity-facts{grid-template-columns:repeat(2,minmax(0,1fr))}.identity-review-actions{display:grid;grid-template-columns:1fr}.identity-review-actions button{width:100%;min-height:44px}}
@media(max-width:480px){.identity-facts{grid-template-columns:1fr}}
"""


ADMIN_STYLES += """
.table-wrap td[colspan]{grid-column:1/-1;text-align:center!important;white-space:normal;padding:24px 14px}
.table-wrap td[colspan]::before{display:none!important}
.admin-disclosure:not(.filter-disclosure)>summary:hover{background:var(--surface-muted);text-decoration:none}
.admin-disclosure:not(.filter-disclosure)>.disclosure-body{margin:0;padding:0 14px 14px}
.model-information-columns>details{padding:0}
.model-information-columns>details>*:not(summary){margin:0 14px 14px}
.provider-card:has(>.admin-disclosure){padding:0}
.provider-card:has(>.admin-disclosure)>:not(details){margin:14px}
details.provider-card.admin-disclosure{padding:0}
details.provider-card.admin-disclosure>*:not(summary){margin:0 14px 14px}
.system-health-row[hidden]{display:none}
.model-administration>.administration-grid{padding:0 14px 14px}
.map-statistics-provider-table .admin-table{table-layout:fixed;width:100%;min-width:560px}
.map-statistics-provider-table .admin-table th{white-space:normal;overflow-wrap:normal}
.map-statistics-provider-table .admin-table th:first-child{width:15%}
.map-statistics-provider-table .admin-table th,.map-statistics-provider-table .admin-table td{padding-inline:7px}
.map-statistics-provider-table .admin-table td{white-space:normal;overflow-wrap:anywhere}
.map-statistics-provider-table .admin-table .column-date{width:142px;overflow-wrap:normal;white-space:nowrap}
/* Rows: Needs attention | Activity, then First run | App downloads. Cards in a row stretch to one height; a lone last card spans the row so no grid cell stays empty. */
.overview-composition-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));align-items:stretch;gap:16px;margin-top:16px}
.overview-composition-grid>.overview-panel{min-width:0;margin:0}.overview-composition-grid>.overview-panel:last-child:nth-child(odd){grid-column:1/-1}
.overview-heading+.overview-primary-grid{margin-top:0}
.overview-activity-list{min-height:0;max-block-size:350px;overflow-y:auto;overscroll-behavior:contain;scrollbar-gutter:stable;padding-inline-end:6px}
.map-activity-row>time{grid-row:1}
@media(max-width:480px){.overview-activity-item{grid-template-columns:minmax(0,1fr)}.overview-activity-item>time{grid-column:1;grid-row:auto;margin-left:21px}}
.model-evidence-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));align-items:start;gap:16px}
.model-evidence-summary,.model-evidence-history{min-width:0}
.model-evidence-summary{display:grid;align-content:start;gap:16px}
.model-evidence-summary>.model-statistics,.model-evidence-summary>.model-review-alert,.model-evidence-summary>.model-page-section,.model-evidence-summary>.model-information-columns{margin:0}
.model-evidence-history>.model-page-section{margin-top:0}
@media(min-width:901px) and (max-width:1023px){
  .model-evidence-history .table-wrap:has(.mobile-record-table){border:0;background:transparent;overflow:visible;border-radius:0}
  .model-evidence-history table.mobile-record-table{display:block;min-width:0!important;width:100%;border:0;table-layout:auto}
  .model-evidence-history .mobile-record-table colgroup,.model-evidence-history .mobile-record-table thead{display:none}
  .model-evidence-history .mobile-record-table tbody{display:grid;width:100%;gap:12px}
  .model-evidence-history .mobile-record-table tbody tr{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px 16px;padding:16px;background:var(--surface);border:1px solid var(--border);border-radius:var(--radius-card);min-width:0}
  .model-evidence-history .mobile-record-table tbody td{display:block;width:auto!important;min-width:0;padding:0!important;border:0!important;text-align:left!important;white-space:normal!important;overflow-wrap:anywhere;font-size:13px}
  .model-evidence-history .mobile-record-table tbody td::before{content:attr(data-label);display:block;margin-bottom:5px;color:var(--secondary);font-size:11px;line-height:1.35;font-weight:600}
  .model-evidence-history .mobile-record-table tbody td:first-child,.model-evidence-history .mobile-record-table tbody td:has(button){grid-column:1/-1}
  .model-evidence-history .mobile-record-table td button{width:100%;min-height:44px}
}
@media(max-width:900px){.overview-composition-grid{grid-template-columns:minmax(0,1fr)}.model-evidence-grid{grid-template-columns:minmax(0,1fr)}.diagnostic-secondary-grid{grid-template-columns:minmax(0,1fr)}}
@media(max-width:760px){
  .admin-section-nav{display:flex;flex-direction:column;align-items:stretch;gap:4px;width:100%}
  .admin-nav-group{display:flex;flex-direction:column;align-items:stretch;gap:4px;width:100%}
  .admin-section-nav a,.admin-nav>a,.admin-nav .link-button{display:flex;align-items:center;justify-content:flex-start;min-height:44px;width:100%;padding:10px;font-size:14px}
  .admin-section-nav>.admin-tools-menu{width:100%}
  .admin-section-nav details>summary{width:100%;min-height:44px;padding:8px 10px}
  .admin-tools-popover{position:static;min-width:0;margin-top:4px}
  .admin-nav{width:100%;display:flex;flex-direction:column;align-items:stretch;gap:4px;margin:8px 0 0;padding-top:8px;border-top:1px solid var(--border)}
  .admin-nav .timezone-control{width:100%}.timezone-control select{width:100%;max-width:none;font-size:16px}
  .admin-nav form{width:100%;margin:0}.admin-nav button{min-height:44px;width:100%;text-align:left}.admin-nav .admin-mobile-website{display:flex}
}
.disclosure-meta{color:var(--secondary);font-weight:400}
.provider-problem h3{margin:0;font-size:16px}.provider-card>.section-heading button[data-provider-action]{min-height:var(--admin-control-height);padding:8px 12px;border:0;border-radius:var(--admin-control-radius);background:var(--interactive);color:var(--interactive-primary-text);font-weight:700}.provider-problem{padding-block:16px;border-block-end:1px solid var(--border)}.provider-problem p{margin-block:6px}.provider-problem-actions{display:flex;gap:12px;flex-wrap:wrap;align-items:center;margin-block-start:14px}.provider-state-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px;align-items:start}
.provider-state-grid>.provider-card{min-width:0}
@media(max-width:700px){.provider-state-grid{grid-template-columns:minmax(0,1fr)}.mobile-record-table td[colspan]{display:block!important;width:100%}}
"""

ADMIN_STYLES += """
/* Shared component kit (docs/admin-behavior-contract.md). Tokens only. */
.admin-scope-chip{display:inline-flex;align-items:center;min-height:20px;padding:1px 8px;border:1px solid var(--status-neutral-border);border-radius:999px;background:var(--status-neutral-surface);color:var(--status-neutral-text);font:600 12px/16px var(--font-ui);white-space:nowrap}
.admin-scope-chip[data-scope="period"]{border-color:var(--status-supported-border);background:var(--selected-tint);color:var(--status-supported-text)}
.admin-pill{display:inline-flex;align-items:center;gap:4px;min-height:24px;padding:3px 8px;border:1px solid var(--status-neutral-border);border-radius:999px;background:var(--status-neutral-surface);color:var(--status-neutral-text);font:600 12px/16px var(--font-ui);letter-spacing:0;text-transform:none;white-space:nowrap;vertical-align:middle}
.admin-pill .admin-icon{width:14px;height:14px}
.admin-pill-success{border-color:var(--status-success-border);background:var(--status-success-surface);color:var(--status-success-text)}
.admin-pill-danger{border-color:var(--status-error-border);background:var(--status-error-surface);color:var(--status-error-text)}
.admin-pill-warning{border-color:var(--status-tested-border);background:var(--status-tested-surface);color:var(--status-warning-text)}
.admin-pill-info,.admin-pill-progress{border-color:var(--status-supported-border);background:var(--status-supported-surface);color:var(--status-supported-text)}
.admin-card{min-width:0;margin-top:16px;padding:16px 20px;border:1px solid var(--border);border-radius:var(--radius-card);background:var(--surface)}
.admin-card-head{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin:0 0 12px}
.admin-card-head>h2,.admin-card-head>h3{margin:0;color:var(--graphite);font:600 17px/24px var(--font-ui)}
.admin-card-head>.admin-card-action,.admin-card-head>button{margin-left:auto}
.admin-card-head>button[data-provider-action]{min-height:var(--admin-control-height);padding:8px 12px;border:0;border-radius:var(--radius-control);background:var(--interactive);color:var(--interactive-primary-text);font-weight:700}
.admin-card-head>button[data-provider-action]:hover{background:var(--interactive-hover)}
.admin-metric-row{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin-top:16px}
.admin-card .admin-metric-row,.heading-row+.admin-metric-row{margin-top:0}
.admin-metric{display:flex;flex-direction:column;gap:4px;min-width:0;padding:14px 16px;border:1px solid var(--border);border-radius:var(--radius-card);background:var(--surface);color:var(--graphite);text-decoration:none}
.admin-card .admin-metric{padding:4px 0;border:0;border-radius:0;background:transparent}
.admin-metric-label{display:flex;align-items:center;gap:6px;color:var(--secondary);font:500 14px/20px var(--font-ui)}
.admin-metric-value{display:flex;align-items:center;gap:6px;color:var(--graphite);font:600 24px/32px var(--font-ui);font-variant-numeric:tabular-nums}
.admin-metric-value .admin-icon{width:18px;height:18px}
.admin-metric[data-kind="text"] .admin-metric-value{font-size:15px;line-height:22px;font-weight:600}
.admin-metric[data-tone="danger"] .admin-metric-value{color:var(--danger)}
.admin-metric[data-state="unknown"] .admin-metric-value,.admin-metric[data-state="unavailable"] .admin-metric-value{color:var(--secondary)}
.admin-metric-meta{display:flex;flex-wrap:wrap;align-items:center;gap:6px;color:var(--secondary);font-size:12px;line-height:16px}
.admin-metric-secondary{font-variant-numeric:tabular-nums}
.admin-metric-link:hover{background:var(--surface-muted)}
.admin-metric-link:focus-visible{outline:var(--admin-focus-ring);outline-offset:-3px}
.admin-empty{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin:8px 0;color:var(--secondary);font-size:14px;line-height:20px}
.admin-card-unavailable{border-style:dashed}
.system-health-catalogs{display:grid;gap:6px;margin:0 0 8px;padding:0;list-style:none}
.provider-problem-group{border-top:1px solid var(--border)}
.provider-problem-group:first-of-type{border-top:0}
.provider-problem-group>summary{display:flex;flex-wrap:wrap;align-items:center;gap:8px;min-height:44px;cursor:pointer}
.provider-problem-reason{font-weight:600}
.provider-problem-group-body{padding:0 0 12px}
.provider-problem-group-actions{display:flex;gap:8px;margin:0 0 8px}
.provider-problem-list{display:grid;gap:0;margin:0;padding:0;list-style:none}
.provider-problem-list>.provider-problem{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:6px 16px;align-items:center;padding:10px 0;border-top:1px solid var(--border)}
.provider-problem-list>.provider-problem small{display:block;color:var(--secondary);font-size:12px}
.provider-problem-list .provider-problem-actions{margin:0}
.provider-row-menu{position:relative}
.provider-row-menu>summary{display:inline-flex;align-items:center;justify-content:center;min-width:36px;min-height:36px;border:1px solid var(--border);border-radius:var(--radius-control);list-style:none;cursor:pointer}
.provider-row-menu>summary::-webkit-details-marker{display:none}
.provider-row-menu-body.is-floating{position:fixed;right:auto;z-index:60}
.provider-row-menu-body{position:absolute;z-index:5;right:0;display:grid;gap:6px;min-width:200px;padding:8px;border:1px solid var(--border);border-radius:var(--radius-control);background:var(--surface);box-shadow:0 4px 16px color-mix(in srgb,var(--graphite) 14%,transparent);text-align:start}
@media(max-width:760px){.provider-problem-list>.provider-problem{grid-template-columns:minmax(0,1fr)}}
.admin-metric-failed{white-space:nowrap}.admin-metric-failed.is-positive{color:var(--danger);font-weight:600}
.overview-card-totals{display:flex;flex-wrap:wrap;align-items:center;justify-content:flex-end;gap:8px;margin-inline-start:auto}
.overview-card-total{display:inline-flex;align-items:baseline;gap:4px;box-sizing:border-box;height:24px;padding:0 8px;border:1px solid var(--border);border-radius:8px;background:var(--surface-muted);font-size:var(--admin-type-label-size);line-height:22px}
.overview-card-total strong{color:var(--graphite);font-size:16px;line-height:22px;font-weight:700;font-variant-numeric:tabular-nums}
.overview-card-total strong.is-positive{color:var(--danger)}
.overview-card-total small{color:var(--secondary);font-size:var(--admin-type-support-size);line-height:22px}
@media(max-width:560px){.overview-card-totals{flex-basis:100%;justify-content:flex-start;margin-inline-start:0}}
.overview-attention-rows{display:grid;gap:2px;margin:0;padding:0;list-style:none}
.overview-attention-row>a{display:grid;grid-template-columns:18px minmax(0,1fr) auto 14px;align-items:center;gap:10px;min-height:40px;padding:6px 8px;border-radius:var(--radius-control);color:var(--graphite);text-decoration:none}
.overview-attention-row>a:hover{background:var(--surface-muted)}
.overview-attention-row>a:focus-visible{outline:var(--admin-focus-ring);outline-offset:-3px}
.overview-attention-row>a>.admin-icon:first-child{width:16px;height:16px;color:var(--secondary)}
.overview-attention-row strong{font-variant-numeric:tabular-nums;font-weight:600}
.overview-attention-row[data-state="active"]>a>.admin-icon:first-child,.overview-attention-row[data-state="active"] strong{color:var(--danger)}
.overview-attention-row[data-state="unavailable"] strong{color:var(--secondary)}
.overview-attention-item .admin-pill{align-self:start}
.overview-all-time{display:flex;flex-wrap:wrap;align-items:center;gap:6px 10px;margin:10px 0 0;color:var(--secondary);font-size:13px}
.overview-all-time strong{color:var(--graphite);font-variant-numeric:tabular-nums;font-weight:600}
.overview-all-time>.section-link{margin-left:auto}
.admin-legend{display:flex;flex-wrap:wrap;gap:6px 16px;margin:8px 0 0;padding:0;list-style:none;color:var(--secondary);font-size:12px;line-height:16px}
.admin-legend li{display:inline-flex;align-items:center;gap:6px}
.admin-legend i{display:inline-block;width:12px;height:12px;border:1px solid var(--border);border-radius:3px}
.admin-legend strong{color:var(--graphite);font-weight:600;font-variant-numeric:tabular-nums}
/* Chart palette (owner decision 2026-10-05): one definition. */
.overview-chart-success{fill:var(--interactive);background:var(--interactive)}
.overview-chart-custom{fill:var(--lichen-dark);background:var(--lichen-dark)}
.overview-chart-failed{fill:var(--danger);background:var(--danger)}
.overview-chart-update{fill:var(--stone-dark);background:var(--stone-dark)}
.overview-chart-update-failed{fill:var(--danger)}
.overview-chart-download-success{fill:var(--interactive);background:var(--interactive)}
.overview-chart-download-failed{fill:var(--danger);background:var(--danger)}
.admin-legend i.overview-chart-update-failed{border-color:var(--danger);background:repeating-linear-gradient(45deg,var(--danger) 0 4px,var(--surface) 4px 6px)}
.overview-chart-group:focus{outline:none}
.overview-chart-group:focus-visible rect{stroke:var(--graphite);stroke-width:2}
"""

# Support reports (contracts/SUPPORT_REPORT_CONTRACT.md).
ADMIN_STYLES += """
.support-report-filters{margin:0 0 12px}
.support-report-filters a.quick-filter{display:inline-flex;align-items:center;text-decoration:none}
.support-report-table code,.support-report-page h1 code{font-family:var(--font-mono);font-size:inherit}
.support-report-table{min-width:760px}
.support-report-table td{white-space:normal;overflow-wrap:anywhere}
.support-report-table td.column-date,.support-report-table td.column-status{white-space:nowrap}
.support-report-table th:nth-child(1){width:104px}.support-report-table th:nth-child(2){width:112px}
.support-report-table th:nth-child(5){width:124px}.support-report-table th:nth-child(7){width:104px}
.support-report-has-message,.support-report-meta,.support-report-optional{color:var(--secondary);font-size:12px}
.support-report-grid{display:grid;grid-template-columns:minmax(0,1.6fr) minmax(280px,1fr);gap:16px;align-items:start}
.support-report-main,.support-report-side{display:grid;gap:16px;min-width:0}
.support-report-message{white-space:pre-wrap;overflow-wrap:anywhere;margin:0}
.support-report-title{margin:0 0 8px;overflow-wrap:anywhere}
.support-report-form{display:grid;gap:8px;margin:0 0 14px}
.support-report-form:last-child{margin-bottom:0}
.support-report-form label{display:grid;gap:4px;font-size:13px;font-weight:600}
.support-report-form textarea,.support-report-form input{width:100%;min-height:var(--admin-control-height);font:inherit;font-weight:400}
.support-report-form button{justify-self:start}
.support-report-links,.support-report-history,.support-report-list{display:grid;gap:8px;margin:0;padding:0;list-style:none;font-size:13px}
.support-report-history p{margin:4px 0 0;color:var(--secondary);white-space:pre-wrap;overflow-wrap:anywhere}
.support-report-trace{max-height:320px;overflow:auto;margin:0;padding:10px;border:1px solid var(--border);border-radius:var(--radius-control);background:var(--surface-muted);font-family:var(--font-mono);font-size:12px;line-height:18px;white-space:pre-wrap;overflow-wrap:anywhere}
.support-report-technical h3{margin:14px 0 6px;font-size:13px}
@media(max-width:900px){.support-report-grid{grid-template-columns:minmax(0,1fr)}}
.support-report-form button.support-report-primary{min-height:var(--admin-control-height);padding:8px 12px;border:0;border-radius:var(--admin-control-radius);background:var(--interactive);color:var(--interactive-primary-text);font-weight:700}
/* Admin review fixes 2026-10-06 (admin-behavior-contract.md, Responsive and layout invariants). */
.overview-chart-panel,.overview-download-panel{display:flex;flex-direction:column}
.overview-chart-panel>.overview-chart-wrap,.overview-download-panel>.overview-chart-wrap{width:100%}
.overview-chart-panel>.overview-all-time,.overview-download-panel>.overview-all-time{margin-top:auto;padding-top:10px}
.overview-download-all-time>.overview-chart-note{margin:0 0 0 auto}
.overview-chart-values{min-height:20px;margin:8px 0 0;font-size:12px}
.overview-chart-values:empty{display:none}
/* First run journey (owner 2026-10-10): three steps on one row at every width;
   label, number, share, bar and change share rows so numbers keep one baseline. */
.funnel-journey{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));grid-template-rows:auto auto auto auto auto;column-gap:16px;margin:4px 0 0;padding:0;list-style:none}
.funnel-step{display:grid;grid-row:span 5;grid-template-rows:subgrid;min-width:0;align-items:end}
.funnel-step-label{color:var(--secondary);font:500 13px/18px var(--font-ui);overflow-wrap:anywhere;align-self:start}
.funnel-step-value{color:var(--graphite);font:600 var(--admin-type-kpi-value-size,28px)/1.15 var(--font-ui);font-variant-numeric:tabular-nums}
.funnel-step-share{grid-row:3;color:var(--secondary);font:500 12px/16px var(--font-ui)}
.funnel-step-bar{grid-row:4;display:block;height:8px;margin:6px 0 4px;border-radius:4px;background:var(--surface-muted)}
.funnel-step-bar>i{display:block;height:100%;min-width:3px;border-radius:4px;background:var(--interactive)}
.funnel-step-delta{grid-row:5;color:var(--secondary);font:400 12px/16px var(--font-ui);font-variant-numeric:tabular-nums}
.funnel-dropoff{display:flex;flex-wrap:wrap;align-items:center;gap:6px;margin:10px 0 0;color:var(--secondary);font:400 13px/18px var(--font-ui)}
.funnel-dropoff strong{color:var(--danger);font-weight:600}
.funnel-dropoff svg{width:12px;height:12px}
.funnel-trend{margin:14px 0 0}
.funnel-trend h3{margin:0 0 6px;color:var(--secondary);font:600 12px/16px var(--font-ui)}
.funnel-trend-bars{display:flex;align-items:flex-end;gap:2px;height:56px;margin:0;padding:0;list-style:none;border-bottom:1px solid var(--border)}
.funnel-trend-bars li{display:flex;flex:1 1 0;flex-direction:column-reverse;height:100%;min-width:2px;border-radius:2px 2px 0 0;cursor:default}
.funnel-trend-bars li:focus-visible{outline:2px solid var(--admin-focus-color);outline-offset:2px}
.funnel-trend-connected{display:block;background:var(--interactive)}
.funnel-trend-never{display:block;background:var(--danger)}
.funnel-trend-axis{display:flex;justify-content:space-between;margin-top:4px;color:var(--secondary);font:400 11px/14px var(--font-ui)}
.funnel-trend-legend{display:flex;flex-wrap:wrap;gap:12px;margin:6px 0 0;padding:0;list-style:none;font-size:12px}
.funnel-trend-legend li{display:inline-flex;align-items:center;gap:6px}
.funnel-trend-legend i{display:inline-block;width:10px;height:10px;border-radius:2px}
.funnel-hint{display:block;color:var(--secondary);font:400 12px/16px var(--font-ui)}
.funnel-models{grid-column:1/-1;display:grid;row-gap:2px;margin:2px 0 4px 12px;padding:0;list-style:none;font-size:12px}
.overview-funnel-bars .funnel-models li{display:flex;grid-column:auto;flex-wrap:wrap;align-items:baseline;gap:8px}
.funnel-models a{color:var(--interactive);font-weight:500}
.funnel-model-status{padding:0 6px;border:1px solid var(--status-neutral-border);border-radius:999px;background:var(--status-neutral-surface);color:var(--status-neutral-text);font-size:11px;line-height:16px}
.overview-funnel-bars .funnel-models strong{margin-left:auto;font-weight:600;color:var(--graphite);font-variant-numeric:tabular-nums}
/* Labels keep their full width (one aligned label column via subgrid); the bar
   track takes what is left and shrinks first, down to 24 px. */
.overview-funnel-breakdown{display:grid;grid-template-columns:minmax(0,max-content) minmax(24px,1fr) minmax(24px,auto);column-gap:8px;row-gap:12px;margin:12px 0 0}
.overview-funnel-group{display:grid;grid-template-columns:subgrid;grid-column:1/-1;min-width:0}
.overview-funnel-group>*{grid-column:1/-1}
.overview-funnel-group h3{margin:0 0 6px;color:var(--secondary);font:600 12px/16px var(--font-ui)}
.overview-funnel-note{margin:-2px 0 6px;font:400 12px/16px var(--font-ui)}
.overview-funnel-bars{display:grid;grid-template-columns:subgrid;row-gap:4px;margin:0;padding:0;list-style:none;font-size:13px}
.overview-funnel-bars li{display:grid;grid-template-columns:subgrid;grid-column:1/-1;align-items:center;min-width:0}
.overview-funnel-label{min-width:0;overflow-wrap:anywhere}
.overview-funnel-bar{display:block;height:8px;border-radius:4px;background:var(--surface-muted)}
.overview-funnel-bar>i{display:block;height:100%;min-width:3px;border-radius:4px;background:var(--status-neutral-text)}
.overview-funnel-bars strong{color:var(--graphite);font-variant-numeric:tabular-nums;font-weight:600;text-align:right}
/* Owner 2026-10-07: beside App downloads (two-column Dashboard, >900 px) a wide
   First run card lays its groups out in two balanced columns without splitting a
   group; each group aligns its own label column. Below the container threshold
   the half columns cannot fit label, bar and count, so the breakdown stays one
   column (also at 900 px and narrower). */
.overview-funnel-panel{container:overview-funnel/inline-size}
@media(min-width:901px){@container overview-funnel (min-width:620px){
  .overview-funnel-breakdown{display:block;columns:2;column-gap:24px}
  .overview-funnel-group{display:block;break-inside:avoid;padding-bottom:12px}
  .overview-funnel-group:last-child{padding-bottom:0}
  .overview-funnel-bars{grid-template-columns:minmax(0,max-content) minmax(24px,1fr) minmax(24px,auto);column-gap:8px}
}}
.overview-chart-values>span{display:inline-flex;align-items:center;gap:6px}
.overview-chart-values-date{color:var(--graphite)}
.overview-trend-chart .overview-chart-group{cursor:pointer}
/* Model installation history: compact table rows at >=1024 px (cards below). The GitHub issue column shows only when a row has an issue. */
@media(min-width:1024px){
  .model-evidence-grid{grid-template-columns:minmax(0,2fr) minmax(0,3fr)}
  .model-evidence-history .model-history-table{min-width:0;width:100%;table-layout:fixed}
  .model-evidence-history .model-history-table th,.model-evidence-history .model-history-table td{padding:8px 6px;font-size:12px;line-height:16px;vertical-align:middle;white-space:normal;overflow-wrap:anywhere}
  .model-evidence-history .model-history-table th:nth-child(1){width:16%}.model-evidence-history .model-history-table th:nth-child(2){width:16%}
  .model-evidence-history .model-history-table th:nth-child(3){width:20%}.model-evidence-history .model-history-table th:nth-child(4){width:21%}
  .model-evidence-history .model-history-table th:nth-child(5){width:10%}.model-evidence-history .model-history-table th:nth-child(6){width:11%}
  .model-evidence-history .model-history-table th:nth-child(7){width:13%}
  .model-evidence-history .model-history-table .column-date{text-align:left;overflow-wrap:normal}
  .model-evidence-history .model-history-table th{overflow-wrap:normal}
  .model-evidence-history .model-history-table .diagnostic-review{white-space:nowrap}
  .model-evidence-history .model-history-table:not(:has(td[data-label='GitHub issue'] a)) :is(th,td):nth-child(5){display:none}
  .model-evidence-history .model-history-table td.column-status:last-child{text-align:right}
  .model-evidence-history .model-history-table .diagnostic-review{min-height:32px;padding:4px 8px}
}
@media(max-width:600px){
  .map-statistics-metrics>.admin-metric-row{grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}
  .map-statistics-metrics .admin-metric{min-width:0}
  .map-statistics-metrics .admin-metric-value{font-size:20px;line-height:26px}
  .map-statistics-metrics .admin-metric-meta{flex-wrap:wrap;font-size:11px}
  .map-statistics-metrics .admin-metric-label{font-size:12px}
  [data-mobile-collapse][data-mobile-collapsed]>:not(.admin-card-head){display:none}
  [data-mobile-collapse][data-mobile-collapsed]>.admin-card-head{margin-bottom:0}
}
.overview-trend-chart .overview-chart-group.is-selected rect{stroke:var(--graphite);stroke-width:2}
/* Card spacing belongs to the containing layout, not both grid and card (admin-behavior-contract.md,
   Responsive and layout invariants). Separate cards, tables and sections keep one vertical gap:
   --admin-card-gap, 24px, 16px at 700px and narrower. A filter bar directly above its own table keeps
   12px; rows inside one table or list are not cards. Block stacks put the gap on the following block
   only; card grids own their gap and their children carry no block margins, so the two never add up. */
:root{--admin-card-gap:24px;--admin-filter-table-gap:12px}
main.dashboard:not(.overview-page)>:not(.heading-row,.back-link,.model-page-header,.provider-action-bar,h1){margin-bottom:0}
main.dashboard:not(.overview-page)>:not(.heading-row,.back-link,.model-page-header,.provider-action-bar,h1)+*,
main.overview-page>.overview-primary-grid+.overview-composition-grid,
.model-evidence-grid>.model-evidence-history>*+*{margin-top:var(--admin-card-gap)}
:is(.overview-primary-grid,.overview-composition-grid,.model-evidence-grid,.model-evidence-summary,.model-information-columns,.map-statistics-coverage-layout,.provider-dashboard-grid,.provider-state-grid,.provider-technical-grid,.support-report-grid,.support-report-main,.support-report-side,.diagnostic-secondary-grid){gap:var(--admin-card-gap)}
main.dashboard :is(.overview-primary-grid,.overview-composition-grid,.model-evidence-grid,.model-evidence-summary,.model-information-columns,.map-statistics-coverage-layout,.provider-dashboard-grid,.provider-state-grid,.provider-technical-grid,.support-report-grid,.support-report-main,.support-report-side,.diagnostic-secondary-grid)>*{margin-top:0;margin-bottom:0}
.filter-bar:has(~.table-wrap){margin-bottom:var(--admin-filter-table-gap)}
@media(max-width:1100px) and (min-width:761px){.device-sticky-header{border-radius:var(--radius-card) var(--radius-card) 0 0}.device-table-wrap{border-top:0;border-top-left-radius:0;border-top-right-radius:0}}
@media(max-width:700px){
  :root{--admin-card-gap:16px}
  main.overview-page{display:grid;grid-template-columns:minmax(0,1fr);gap:var(--admin-card-gap)}
  .overview-page>.overview-heading{margin:0}
  main.overview-page>.overview-primary-grid+.overview-composition-grid{margin-top:0}
  .admin-kpi-grid,.installation-kpis,.model-statistics,.diagnostic-model-metrics,.provider-metrics{gap:12px}
}
"""

# Device detail Update history mirrors Installation history (owner decision
# 2026-10-06): link quick filters look like the button quick filters, and the
# six-column table fits the history column at >=1024 px (record cards below).
ADMIN_STYLES += """
.update-history-filters a.quick-filter{display:inline-flex;align-items:center;text-decoration:none}
.update-history-inspect{white-space:nowrap}
.model-evidence-history>.model-page-section+#updates{margin-top:16px}
@media(min-width:1024px){
  .model-evidence-history .update-history-table{min-width:0;width:100%;table-layout:fixed}
  .model-evidence-history .update-history-table th,.model-evidence-history .update-history-table td{padding:8px 6px;font-size:12px;line-height:16px;vertical-align:middle;white-space:normal;overflow-wrap:anywhere}
  .model-evidence-history .update-history-table th{overflow-wrap:normal}
  .model-evidence-history .update-history-table th>.device-sort-button{max-width:100%;flex-wrap:wrap;white-space:normal;text-align:left}
  .model-evidence-history .update-history-table .admin-pill{max-width:100%;white-space:normal}
  .model-evidence-history .update-history-table th:nth-child(1){width:16%}.model-evidence-history .update-history-table th:nth-child(2){width:17%}
  .model-evidence-history .update-history-table th:nth-child(3){width:29%}.model-evidence-history .update-history-table th:nth-child(4){width:12%}
  .model-evidence-history .update-history-table th:nth-child(5){width:13%}.model-evidence-history .update-history-table th:nth-child(6){width:13%}
  .model-evidence-history .update-history-table .column-date{text-align:left;overflow-wrap:normal}
  .model-evidence-history .update-history-table:not(:has(td[data-label='GitHub issue'] a)) :is(th,td):nth-child(4){display:none}
  .model-evidence-history .update-history-table td.column-status:last-child{text-align:right}
  .model-evidence-history .update-history-inspect{min-height:32px;padding:4px 8px}
}
@media(max-width:760px){.update-history-table tbody td:last-child{grid-column:1/-1}.update-history-table .update-history-inspect{width:100%}}
@media(min-width:901px) and (max-width:1023px){.model-evidence-history .update-history-table tbody td:last-child{grid-column:1/-1}.model-evidence-history .update-history-inspect{width:100%}}
"""

# Tools → Update reports (owner decision 2026-10-06): the list follows the
# Installations layout (one KPI card, the filter bar, then the table) and the
# detail page uses the full content width. Scoped to this page only.
ADMIN_STYLES += """
.update-diagnostics-page .update-report-filters a.quick-filter{display:inline-flex;align-items:center;text-decoration:none}
.update-diagnostics-page .update-report-filters>.filter-clear{display:inline-flex;align-items:center;text-decoration:none}
.update-diagnostics-page .update-report-list>.results-count{margin:0}
.update-diagnostics-page .update-report-table .column-date{text-align:left}
.update-diagnostics-page .update-report-table :is(th,td).column-status:last-child{text-align:right}
.update-diagnostics-page .provider-pagination>a{display:inline-flex;align-items:center;justify-content:center;min-height:var(--admin-control-height);margin:0;text-decoration:none;white-space:nowrap}
.update-diagnostics-page .update-report-card{padding:24px}
.update-diagnostics-page .update-report-card>h2+.diagnostic-detail-summary{margin-top:-9px;border-top:0}
.update-diagnostics-page .update-report-status>h2{margin:0 0 4px}
.update-diagnostics-page .update-report-status>p{margin:0;max-width:75ch}
.update-diagnostics-page .update-provider-action{margin:16px 0 0}
.update-diagnostics-page .update-identity-section>.table-help{margin:8px 0 0;max-width:75ch}
@media(min-width:761px){.update-diagnostics-page .update-report-table .update-history-inspect{min-height:32px;padding:4px 10px}}
@media(max-width:760px){.update-diagnostics-page .provider-pagination>a{min-height:44px}}
@media(max-width:560px){.update-diagnostics-page .update-report-card{padding:18px 16px}}
"""

# Identity review queue and the tidied reported-identity page (owner decision
# 2026-10-06, admin-behavior-contract.md "Identity review"). One scoped block.
ADMIN_STYLES += """
.identity-review-summary{display:inline-flex;align-items:center;gap:8px}
.identity-review-groups{display:grid;gap:var(--admin-card-gap)}
.identity-review-group .admin-card-head>h2{display:flex;flex-wrap:wrap;align-items:baseline;gap:4px 10px;min-width:0;overflow-wrap:anywhere}
.identity-review-group .admin-card-head>h2>small{color:var(--secondary);font:500 13px/18px var(--font-ui)}
.identity-review-group .admin-card-head{margin-bottom:4px}
.identity-review-items{margin:0;padding:0;list-style:none}
.identity-review-item{display:grid;grid-template-columns:minmax(0,1fr);gap:10px 24px;padding:14px 0;border-top:1px solid var(--border)}
.identity-review-item:first-child{border-top:0}
.identity-review-facts{display:flex;flex-wrap:wrap;align-items:center;gap:6px 12px;min-width:0;font-size:13px;line-height:18px}
.identity-review-date{color:var(--secondary);font-variant-numeric:tabular-nums;white-space:nowrap}
.identity-review-map{color:var(--graphite);font-weight:600;overflow-wrap:anywhere}
.identity-review-why{display:flex;flex-basis:100%;flex-wrap:wrap;align-items:center;gap:4px 12px}
.identity-review-reason{color:var(--secondary);font-size:12px;line-height:16px}
.identity-review-details{display:inline-flex;align-items:center;min-height:32px}
.identity-review-decision{display:grid;gap:10px;min-width:0}
.identity-review-decision .identity-review-form{display:flex;flex-wrap:wrap;align-items:center;gap:8px 12px;padding:0;background:transparent}
.identity-review-decision .identity-review-form[hidden]{display:none}
.identity-review-decision .identity-review-for{flex-basis:100%;margin:0;color:var(--secondary);font-size:12px;line-height:16px}
.identity-review-decision .identity-selection{flex:1 1 220px;min-width:0;margin:0}
.identity-review-decision .identity-selection div{display:grid;gap:2px}
.identity-review-decision .identity-selection dt{color:var(--secondary);font-size:12px;line-height:16px;font-weight:600}
.identity-review-decision .identity-selection dd{margin:0;color:var(--graphite);font-size:14px;line-height:20px;font-weight:700;overflow-wrap:anywhere}
.identity-review-decision .identity-picker,.identity-review-decision .identity-conflict-warning{flex-basis:100%;order:3;margin:0}
.identity-review-decision .identity-picker label{margin:0}
.identity-review-decision .identity-review-actions{flex:0 0 auto;margin:0}
.identity-review-decision .identity-review-actions button{margin:0}
.identity-review-decision .admin-action-status{flex-basis:100%;order:4;margin:0}
.identity-review-decision .admin-action-status:empty{display:none}
.identity-review-confirmed{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin:0;font-size:13px}
.identity-review-confirmed:focus-visible{outline:var(--admin-focus-ring);outline-offset:3px;border-radius:var(--admin-control-radius)}
.identity-review-item[data-identity-confirmed='true'] .identity-review-facts{color:var(--secondary)}
.identity-review-done[hidden]{display:none}
a.identity-pending-indicator{text-decoration:none;vertical-align:middle}
a.identity-pending-indicator:hover{border-color:var(--interactive);color:var(--interactive)}
.identity-review-link{display:inline-flex;align-items:center;gap:4px;text-decoration:none;white-space:nowrap}
.identity-review-all-link{display:inline-flex;align-items:center;gap:4px;align-self:center}
.diagnostic-model-metrics .admin-metric .admin-pill{display:inline-flex;width:auto;max-width:100%;margin:0}
.diagnostic-model-metrics .admin-metric .admin-pill>span{display:inline;margin:0;color:inherit;font:inherit}
@media(min-width:900px){
  .identity-review-item{grid-template-columns:minmax(0,5fr) minmax(0,6fr);align-items:start}
}
@media(max-width:700px){
  .identity-review-all-link{align-self:flex-start}
  .identity-review-decision .identity-review-actions{display:flex;flex-basis:100%;gap:8px}
  .identity-review-decision .identity-review-actions button{flex:1 1 0;width:auto;min-width:0}
}
"""


def _fa_mask_css() -> str:
    """CSS custom properties holding Font Awesome icons as data: masks for
    pseudo-element markers (chevrons, timeline arrows, placeholders)."""
    def url(name: str) -> str:
        view_box, path = _FA_ICONS[name]
        svg = f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='{view_box}'><path d='{path}'/></svg>"
        return 'url("data:image/svg+xml,' + quote(svg, safe="/:=' ") + '")'
    names = ("chevron-down", "chevron-right", "arrow-right", "image", "sort", "sort-up", "sort-down", "check")
    return ":root{" + ";".join(f"--fa-{name}:{url(name)}" for name in names) + "}\n"


ADMIN_STYLES += """
/* Diagnostic detail (installation dialog and update report): one section rhythm,
   one disclosure style, compact review forms and Device identity last
   (owner decision 2026-10-06). Scoped so global card spacing stays untouched. */
:is(.diagnostic-detail-dialog,.update-diagnostics-page) .diagnostic-section{margin:24px 0 0}
:is(.diagnostic-detail-dialog,.update-diagnostics-page) .diagnostic-section>h3{margin:0 0 8px;color:var(--graphite);font:650 var(--admin-type-subsection-size)/var(--admin-type-subsection-line) var(--font-ui)}
:is(.diagnostic-detail-dialog,.update-diagnostics-page) .diagnostic-outcome>p{margin:0;max-width:75ch;font-size:var(--admin-type-body-size);line-height:var(--admin-type-body-line)}
:is(.diagnostic-detail-dialog,.update-diagnostics-page) .diagnostic-outcome>.diagnostic-next-action{display:grid;gap:2px;margin-top:12px}
:is(.diagnostic-detail-dialog,.update-diagnostics-page) .diagnostic-next-action>strong{color:var(--secondary);font-size:var(--admin-type-label-size);line-height:var(--admin-type-label-line);font-weight:650}
:is(.diagnostic-detail-dialog,.update-diagnostics-page) .diagnostic-safety>.diagnostic-detail-summary{margin:0}
:is(.diagnostic-detail-dialog,.update-diagnostics-page) .diagnostic-issue-section>.github-current{margin:0 0 2px;font-size:var(--admin-type-table-primary-size);line-height:var(--admin-type-table-primary-line);font-weight:650}
:is(.diagnostic-detail-dialog,.update-diagnostics-page) .diagnostic-issue-section>.table-help{margin:0;max-width:75ch}
:is(.diagnostic-detail-dialog,.update-diagnostics-page) .github-issue-controls{margin-top:12px}
:is(.diagnostic-detail-dialog,.update-diagnostics-page) .github-actions{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin:0 0 12px}
:is(.diagnostic-detail-dialog,.update-diagnostics-page) .github-actions>.copy-status:empty{display:none}
:is(.diagnostic-detail-dialog,.update-diagnostics-page) .diagnostic-disclosure{min-width:0;margin:0;padding:0;border:1px solid var(--border);border-radius:var(--radius-card);background:var(--surface)}
:is(.diagnostic-detail-dialog,.update-diagnostics-page) .diagnostic-disclosure+.diagnostic-disclosure{margin-top:8px}
:is(.diagnostic-detail-dialog,.update-diagnostics-page) .diagnostic-disclosure .diagnostic-disclosure{margin-top:12px}
:is(.diagnostic-detail-dialog,.update-diagnostics-page) .diagnostic-disclosure>summary{display:block;min-height:44px;margin:0;padding:10px 16px 10px 38px;border-radius:calc(var(--radius-card) - 1px);color:var(--interactive);font:650 var(--admin-type-control-size)/24px var(--font-ui);cursor:pointer}
:is(.diagnostic-detail-dialog,.update-diagnostics-page) .diagnostic-disclosure>summary::before{left:16px}
:is(.diagnostic-detail-dialog,.update-diagnostics-page) .diagnostic-disclosure[open]>summary{border-bottom-left-radius:0;border-bottom-right-radius:0}
:is(.diagnostic-detail-dialog,.update-diagnostics-page) .diagnostic-disclosure>summary .disclosure-meta{color:var(--secondary);font-weight:500}
:is(.diagnostic-detail-dialog,.update-diagnostics-page) .diagnostic-disclosure>.disclosure-body{margin:0;padding:4px 16px 16px}
:is(.diagnostic-detail-dialog,.update-diagnostics-page) .diagnostic-disclosure-stack{display:grid;gap:8px;margin-top:24px}
:is(.diagnostic-detail-dialog,.update-diagnostics-page) .diagnostic-disclosure-stack:empty{display:none}
:is(.diagnostic-detail-dialog,.update-diagnostics-page) .diagnostic-disclosure-stack>.diagnostic-disclosure{margin:0}
:is(.diagnostic-detail-dialog,.update-diagnostics-page) .diagnostic-disclosure .table-help{margin:0 0 12px}
:is(.diagnostic-detail-dialog,.update-diagnostics-page) .github-issue-preview label{display:block;margin:0 0 12px;color:var(--graphite);font-size:var(--admin-type-label-size);line-height:var(--admin-type-label-line);font-weight:650}
:is(.diagnostic-detail-dialog,.update-diagnostics-page) .github-issue-preview label:last-child{margin-bottom:0}
:is(.diagnostic-detail-dialog,.update-diagnostics-page) .github-issue-preview :is(input,textarea){display:block;width:100%;margin-top:6px}
:is(.diagnostic-detail-dialog,.update-diagnostics-page) .github-link-disclosure>.disclosure-body{display:flex;flex-wrap:wrap;align-items:flex-end;gap:12px}
:is(.diagnostic-detail-dialog,.update-diagnostics-page) .github-link-form{display:flex;flex-wrap:nowrap;align-items:flex-end;gap:12px;margin:0}
:is(.diagnostic-detail-dialog,.update-diagnostics-page) .github-link-form label{flex:0 1 240px;min-width:0;margin:0;color:var(--graphite);font-size:var(--admin-type-label-size);line-height:var(--admin-type-label-line);font-weight:650}
:is(.diagnostic-detail-dialog,.update-diagnostics-page) .github-link-form input{display:block;width:100%;margin-top:6px;min-height:var(--admin-control-height)}
:is(.diagnostic-detail-dialog,.update-diagnostics-page) :is(.github-link-form,.github-remove-form) button{width:auto;margin:0}
:is(.diagnostic-detail-dialog,.update-diagnostics-page) .github-remove-form{display:block;margin:0}
:is(.diagnostic-detail-dialog,.update-diagnostics-page) .diagnostic-technical-section .technical-copy-actions{margin:0 0 12px}
:is(.diagnostic-detail-dialog,.update-diagnostics-page) .diagnostic-technical-section .diagnostic-id{margin:0 0 8px}
:is(.diagnostic-detail-dialog,.update-diagnostics-page) .diagnostic-technical-details>.disclosure-body>dl{margin:0}
:is(.diagnostic-detail-dialog,.update-diagnostics-page) .diagnostic-review-forms{display:grid;gap:16px}
:is(.diagnostic-detail-dialog,.update-diagnostics-page) .diagnostic-review-forms>.diagnostic-action-form{display:flex;flex-wrap:wrap;align-items:flex-end;gap:12px 16px;margin:0;padding:0;border-radius:0;background:none}
:is(.diagnostic-detail-dialog,.update-diagnostics-page) .diagnostic-review-forms>.diagnostic-action-form+.diagnostic-action-form{padding-top:16px;border-top:1px solid var(--border)}
:is(.diagnostic-detail-dialog,.update-diagnostics-page) .diagnostic-review-forms>.diagnostic-action-form>:is(h3,h4,p,dl,.admin-action-status){flex:1 0 100%;margin:0}
:is(.diagnostic-detail-dialog,.update-diagnostics-page) .diagnostic-review-forms>.diagnostic-action-form>:is(h3,h4){color:var(--graphite);font:650 var(--admin-type-table-primary-size)/var(--admin-type-table-primary-line) var(--font-ui)}
:is(.diagnostic-detail-dialog,.update-diagnostics-page) .diagnostic-review-forms>.diagnostic-action-form>label{flex:1 1 220px;margin:0}
:is(.diagnostic-detail-dialog,.update-diagnostics-page) .diagnostic-review-forms>.diagnostic-action-form>button{flex:0 0 auto;margin:0}
:is(.diagnostic-detail-dialog,.update-diagnostics-page) .diagnostic-review-forms textarea{height:var(--admin-control-height)}
:is(.diagnostic-detail-dialog,.update-diagnostics-page) .diagnostic-review-forms .admin-action-status:empty{display:none}
.diagnostic-detail-dialog .identity-review-form{margin:0;padding:0;border-radius:0;background:none}
.diagnostic-detail-dialog .identity-review-form>.identity-selection{display:block;margin:0;border-top:1px solid var(--border);color:var(--graphite);font-size:inherit}
.diagnostic-detail-dialog .identity-selection>div{display:grid;grid-template-columns:minmax(95px,.4fr) minmax(0,1.6fr);gap:12px;padding:9px 0;border-bottom:1px solid color-mix(in srgb,var(--border) 72%,transparent)}
.diagnostic-detail-dialog .identity-selection dt{color:var(--secondary);font-size:var(--admin-type-label-size)}
.diagnostic-detail-dialog .identity-selection dd{margin:0;overflow-wrap:anywhere;font-size:var(--admin-type-table-primary-size);font-weight:650;text-align:right}
.diagnostic-detail-dialog .identity-review-form .identity-picker{margin-top:12px}
.diagnostic-detail-dialog .identity-review-form .identity-picker label{display:block;margin:0;color:var(--graphite);font-size:var(--admin-type-label-size);font-weight:650}
.diagnostic-detail-dialog .identity-review-form .identity-review-actions{margin-top:12px}
.diagnostic-detail-dialog .identity-review-form .identity-review-actions button{margin:0}
.diagnostic-detail-dialog .identity-review-form .admin-action-status:empty{display:none}
@media(max-width:700px){
  :is(.diagnostic-detail-dialog,.update-diagnostics-page) .diagnostic-review-forms>.diagnostic-action-form>button,:is(.diagnostic-detail-dialog,.update-diagnostics-page) .github-link-disclosure :is(form,label,button){flex:1 1 100%;width:100%}
  :is(.diagnostic-detail-dialog,.update-diagnostics-page) .github-link-form{flex-wrap:wrap}
  .diagnostic-detail-dialog .identity-selection>div{grid-template-columns:minmax(80px,.7fr) minmax(0,1fr)}
}
"""


ADMIN_STYLES += _fa_mask_css()
# Above the labelled-record breakpoint, tables fit their card instead of
# scrolling sideways behind a fixed minimum width; header labels wrap
# (owner decision 2026-10-06). Devices keeps its width for the sticky header.
ADMIN_STYLES += "@media(min-width:761px){.table-wrap:not(.device-table-wrap)>table{min-width:0}.evidence-table-wrap>table{table-layout:fixed}}\n"
# Provider detail (owner decision 2026-10-06, admin-behavior-contract.md
# "Providers and collection history"): one summary card, Checks and Syncs as
# equal-height halves that stack when details open or the row is narrow, and
# one full-width Technical details card whose switcher shows one panel.
ADMIN_STYLES += """
.provider-kpis>.admin-metric-row{grid-template-columns:repeat(5,minmax(0,1fr))}
.provider-detail .provider-state-grid{grid-template-columns:repeat(2,minmax(0,1fr));align-items:stretch}
.provider-detail .provider-state-grid:has(#provider-health-details[open]){grid-template-columns:minmax(0,1fr)}
.provider-state-card{display:flex;flex-direction:column}
.provider-state-card>.provider-latest-summary{font-size:var(--admin-type-table-primary-size);line-height:var(--admin-type-table-primary-line)}
.provider-state-card :is(p,dt,dd,li){font-size:var(--admin-type-table-primary-size);line-height:var(--admin-type-table-primary-line)}
.provider-state-card .table-help,.provider-state-card small{font-size:var(--admin-type-helper-size);line-height:var(--admin-type-helper-line)}
.provider-state-card .provider-health-facts{margin:12px 0 0}
.provider-state-card .provider-health-facts dd .table-secondary{display:inline;margin-left:6px}
.provider-state-card>details{margin-top:12px}
.provider-state-card>.provider-card-link{margin:auto 0 0;padding-top:12px}
.provider-card-link .section-link{font-size:var(--admin-type-control-size);font-weight:650}
.provider-health-schedule{display:flex;align-items:center;gap:8px 12px;flex-wrap:wrap;margin:12px 0 0}
.provider-health-schedule label{flex:0 0 auto;margin:0;color:var(--graphite);font:600 var(--admin-type-control-size)/var(--admin-type-control-line) var(--font-ui)}
.provider-health-schedule select,.provider-health-schedule button{box-sizing:border-box;height:var(--admin-control-height);min-height:var(--admin-control-height);margin:0}
.provider-health-schedule select{min-width:150px;padding:0 var(--admin-control-padding-x);border:1px solid var(--border);border-radius:var(--admin-control-radius);background:var(--surface);color:var(--graphite);font:600 var(--admin-control-font-size)/1.2 var(--font-ui);cursor:pointer}
.provider-health-schedule select:hover:not(:disabled){border-color:color-mix(in srgb,var(--interactive) 45%,var(--border))}
.provider-health-schedule select:focus-visible{outline:var(--admin-focus-ring);outline-offset:3px}
.provider-health-schedule select:disabled{background:var(--surface-muted);color:var(--secondary);cursor:not-allowed}
.provider-health-schedule button{padding:0 12px;font:600 var(--admin-type-button-size)/1 var(--font-ui)}
.provider-technical-disclosure>summary{display:flex;flex-wrap:wrap;align-items:center;gap:4px 10px;cursor:pointer;list-style:none}
.provider-technical-disclosure>summary::-webkit-details-marker{display:none}
.provider-technical-disclosure>summary:focus-visible{outline:var(--admin-focus-ring);outline-offset:3px;border-radius:var(--radius-control)}
.provider-technical-disclosure>summary>h2{margin:0;color:var(--graphite);font:600 17px/24px var(--font-ui)}
.provider-technical-disclosure>summary:hover>h2{color:var(--interactive)}
.provider-technical-disclosure>summary>.disclosure-meta{font-size:var(--admin-type-table-primary-size);line-height:var(--admin-type-table-primary-line)}
.provider-technical-chevron{display:inline-flex;color:var(--interactive)}
.provider-technical-chevron .admin-icon{width:12px;height:12px}
.provider-technical-disclosure[open] .provider-technical-chevron{transform:rotate(90deg)}
.provider-technical-body{margin-top:12px}
.provider-technical-switcher{margin:0}
.provider-tab-count{margin-left:2px;color:var(--secondary);font-weight:500;font-variant-numeric:tabular-nums}
.provider-technical-panel{margin-top:12px}
.provider-technical-panel:focus-visible{outline:var(--admin-focus-ring);outline-offset:3px}
.provider-technical-panel>.filter-bar:first-child{margin-top:var(--admin-card-gap)}
.provider-technical-panel>.table-help:first-child{margin-top:0}
.provider-technical-heading{margin:20px 0 8px;color:var(--graphite);font:600 var(--admin-type-subsection-size)/var(--admin-type-subsection-line) var(--font-ui)}
.provider-technical-panel>.provider-technical-heading:first-child{margin-top:0}
.provider-technical-text{margin:0 0 4px;font-size:var(--admin-type-table-primary-size);line-height:var(--admin-type-table-primary-line)}
.provider-technical-panel .results-count .admin-pill+.admin-pill{margin-left:4px}
.provider-show-more{display:block;margin:12px auto 0}
.provider-technical-card .table-wrap td{white-space:normal;overflow-wrap:anywhere;vertical-align:top}
.provider-technical-card .audit-technical-details code{max-height:16em}
.provider-technical-card .table-wrap td.column-date,.provider-technical-card .table-wrap td.column-number{overflow-wrap:normal}
.provider-technical-card .provider-reason-cell{min-width:220px}
.provider-technical-card .provider-url-cell{min-width:200px}
.catalog-release-changes{margin:4px 0 0;padding-left:18px}
.catalog-release-changes li{margin:2px 0}
.catalog-release-more{margin-top:4px}
.catalog-release-more>summary{font-size:var(--admin-type-helper-size)}
.catalog-release-more>.catalog-release-changes{columns:3 15em;column-gap:24px}
.catalog-release-more>.catalog-release-changes li{break-inside:avoid}
@media(min-width:1200px){.provider-technical-card .table-wrap td.column-date .admin-timestamp{white-space:nowrap}}
@media(max-width:1100px){.provider-kpis>.admin-metric-row{grid-template-columns:repeat(3,minmax(0,1fr))}}
@media(max-width:1180px){.provider-detail .provider-state-grid{grid-template-columns:minmax(0,1fr)}}
@media(max-width:760px){
  .provider-technical-card .mobile-record-table td:is(.provider-reason-cell,.provider-url-cell),.provider-technical-card .mobile-record-table td:has(.audit-technical-details[open]){grid-column:1/-1;min-width:0}
  .provider-technical-card .mobile-record-table td.is-empty{display:none}
  .provider-technical-card .audit-technical-details code{max-width:100%}
}
@media(max-width:700px){
  .provider-health-schedule label{flex-basis:100%}
  .provider-health-schedule select{flex:1 1 150px}
}
"""

# One-card KPI rows (owner decision 2026-10-07, admin-behavior-contract.md
# "Responsive and layout invariants"): at <=760 px a summary card's tiles fit
# two rows: five or three tiles use three columns (3 + 2, or one row), four or
# two use two (2 + 2, or one row). The shared auto-fit grid would otherwise
# stack one tile per row. Each tile spans three shared subgrid rows (label,
# value, secondary line), so numbers sit on one baseline under labels that may
# wrap, and a parenthesised rate wraps under its count instead of overflowing.
ADMIN_STYLES += """
@media(max-width:760px){
  :is(.installation-kpis,.admin-kpi-panel)>.admin-metric-row{grid-template-columns:repeat(3,minmax(min-content,1fr));row-gap:0}
  :is(.installation-kpis,.admin-kpi-panel)>.admin-metric-row:has(>:nth-child(2):last-child,>:nth-child(4):last-child){grid-template-columns:repeat(2,minmax(min-content,1fr))}
  :is(.installation-kpis,.admin-kpi-panel)>.admin-metric-row>.admin-metric{display:grid;grid-row:span 3;grid-template-rows:subgrid;align-content:start;row-gap:4px;padding:4px 0 8px}
  :is(.installation-kpis,.admin-kpi-panel)>.admin-metric-row .admin-metric-label{align-self:start}
  :is(.installation-kpis,.admin-kpi-panel)>.admin-metric-row .admin-metric-value{flex-wrap:wrap;gap:0 6px;margin-top:0}
  /* Devices: Covered spans two columns so Pending policy sits under Verified, and the
     rate is half size on the same line as covered/eligible (owner decision 2026-10-07). */
  .device-summary-strip>.admin-metric-row>.admin-metric:has([data-stat='covered']){grid-column:span 2}
  .device-summary-strip [data-stat='covered']{flex-wrap:nowrap;align-items:baseline}
  .device-summary-strip [data-stat='covered'] .admin-metric-rate{font-size:.5em}
}
"""

# Filter dropdown (docs/admin-behavior-contract.md, "Shared component kit").
# One block scoped to the component classes: the hidden native select keeps
# sizing the field through the existing rules; the button paints over it and
# the listbox popover opens below the field.
ADMIN_DROPDOWN_STYLES = """
.admin-dropdown{position:relative;display:inline-grid;min-width:0;max-width:100%}
.admin-dropdown>select{grid-area:1/1;opacity:0;pointer-events:none}
.filter-bar label>.admin-dropdown,.inline-filter-row label>.admin-dropdown{flex:none}
.inline-filter-row label>.admin-dropdown,.inline-filter-row .admin-dropdown>select{width:100%}
.overview-period-form .admin-dropdown{flex:1 1 auto}
.admin-dropdown>button.admin-dropdown-button{position:absolute;inset:0;display:flex;align-items:center;gap:8px;box-sizing:border-box;width:100%;height:100%;min-width:0;min-height:0;margin:0;padding:0 var(--admin-control-padding-x);border:1px solid var(--border);border-radius:var(--admin-control-radius);background:var(--surface);color:var(--graphite);line-height:1.2;text-align:left;cursor:pointer;opacity:1;transform:none}
.admin-dropdown>button.admin-dropdown-button:hover:not(:disabled){border-color:color-mix(in srgb,var(--interactive) 45%,var(--border));background:var(--surface)}
.admin-dropdown>button.admin-dropdown-button[aria-expanded="true"]{border-color:var(--interactive)}
.admin-dropdown>button.admin-dropdown-button:focus-visible{outline:var(--admin-focus-ring);outline-offset:3px}
.admin-dropdown>button.admin-dropdown-button:disabled{border-color:color-mix(in srgb,var(--border) 78%,var(--surface-muted));background:var(--surface-muted);color:var(--secondary);cursor:not-allowed;opacity:1}
.admin-dropdown .admin-dropdown-value{flex:1 1 auto;min-width:0;max-width:none;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.admin-dropdown .admin-dropdown-chevron{flex:none;width:10px;height:10px;max-width:none;background:var(--secondary);-webkit-mask:var(--fa-chevron-down) center/contain no-repeat;mask:var(--fa-chevron-down) center/contain no-repeat}
.admin-dropdown>button[aria-expanded="true"] .admin-dropdown-chevron{background:var(--interactive);transform:rotate(180deg)}
.admin-dropdown-list{position:fixed;z-index:50;top:0;left:0;box-sizing:border-box;width:max-content;max-height:320px;margin:0;padding:4px;overflow-y:auto;overscroll-behavior:contain;border:1px solid var(--border);border-radius:var(--radius-control);background:var(--surface);color:var(--graphite);font-family:var(--font-ui);font-size:var(--admin-control-font-size);line-height:1.3;box-shadow:0 16px 44px color-mix(in srgb,var(--graphite) 8%,transparent)}
.admin-dropdown-list[hidden]{display:none}
.admin-dropdown-option{display:flex;align-items:center;gap:8px;min-height:32px;padding:6px 12px 6px 8px;border-radius:calc(var(--radius-control) - 4px);font-weight:500;cursor:pointer;user-select:none}
.admin-dropdown-option.is-active{background:var(--surface-muted)}
.admin-dropdown-option[aria-selected="true"]{background:var(--selected-tint);font-weight:650}
.admin-dropdown-list.is-keyboard .admin-dropdown-option.is-active{outline:var(--admin-focus-ring);outline-offset:-3px}
.admin-dropdown-option[aria-disabled="true"]{color:var(--secondary);cursor:not-allowed}
.admin-dropdown-option-text{min-width:0;overflow-wrap:anywhere}
.admin-dropdown-check{flex:none;width:12px;height:12px;background:var(--interactive);-webkit-mask:var(--fa-check) center/contain no-repeat;mask:var(--fa-check) center/contain no-repeat;visibility:hidden}
.admin-dropdown-option[aria-selected="true"] .admin-dropdown-check{visibility:visible}
.admin-dropdown-group{padding:8px 8px 4px;color:var(--secondary);font-size:11px;font-weight:750;letter-spacing:.07em;text-transform:uppercase}
@media(max-width:760px){.admin-dropdown-option{min-height:44px}}
"""
ADMIN_STYLES += ADMIN_DROPDOWN_STYLES

def _error(message: str | None) -> str:
    return f"<p class='error'>{html.escape(message)}</p>" if message else ""


def _success(message: str | None) -> str:
    return f"<p class='success'>{html.escape(message)}</p>" if message else ""


def _script_tag(code: str) -> str:
    """A template-owned inline script carrying the per-response nonce placeholder."""
    return f'<script nonce="{_ADMIN_NONCE_PLACEHOLDER}">{code}</script>'


def _layout(title: str, content: str, *, sections: dict[str, Any] | None = None, revisions: dict[str, str] | None = None) -> bytes:
    if 'id="main-content"' in content or "id='main-content'" in content:
        revisions = revisions if revisions is not None else section_revisions(sections or {})
        revision = html.escape(json.dumps(revisions, sort_keys=True), quote=True)
        content = re.sub(r'(<main\b)', lambda match: match[0] + f' data-admin-revisions="{revision}"', content, count=1)
        content += _script_tag(_admin_freshness_script() + _admin_mobile_script() + _admin_filter_clear_script() + _admin_quick_select_script() + _admin_row_menu_script() + _admin_disclosure_script() + _admin_chart_values_script() + _admin_table_sort_script() + _admin_mobile_collapse_script() + _admin_dropdown_script())
    # Scripts get the nonce at their template site; the assembled body is never
    # post-processed, so data that slipped through escaping gets no nonce.
    content = f"{content}{_script_tag(_admin_timezone_script())}"
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow"><title>{html.escape(title)} · Terento</title><style>{ADMIN_STYLES}</style></head><body class="admin-shell">{content}</body></html>""".encode("utf-8")


def _admin_table_sort_script() -> str:
    """Every Admin data table sorts by any column (owner decision 2026-10-06).

    Tables that already sort themselves (Devices, Installations) and ranking
    lists whose header is visually hidden are left alone. Values come from ``data-sort-value``, then ``<time datetime>``, then
    numbers, then text; empty or ``—`` cells always sort last. A row made of one
    spanning cell stays attached to the row above it. Scripts that paginate
    rows listen for ``admin:table-sorted`` and re-read the row order.
    """
    return r"""(() => {
      const owned = 'thead [data-device-sort], thead [data-installation-sort], thead .sort-indicator, thead button, thead input, thead select';
      const collator = new Intl.Collator('en', {numeric: true, sensitivity: 'base'});
      const valueOf = (cell) => {
        if (!cell) return null;
        if (cell.dataset.sortValue !== undefined && cell.dataset.sortValue !== '') {
          const number = Number(cell.dataset.sortValue);
          return Number.isFinite(number) ? number : cell.dataset.sortValue;
        }
        const time = cell.querySelector('time[datetime]');
        if (time) { const at = Date.parse(time.getAttribute('datetime')); if (Number.isFinite(at)) return at; }
        const text = (cell.textContent || '').replace(/\s+/g, ' ').trim();
        if (!text || text === '—' || /^—\s/.test(text)) return null;
        const numeric = text.replace(/[,\u00a0\s]/g, '').replace(/%$/, '');
        if (/^-?\d+(\.\d+)?$/.test(numeric)) return Number(numeric);
        return text;
      };
      const compare = (a, b) => (typeof a === 'number' && typeof b === 'number') ? a - b : collator.compare(String(a), String(b));
      document.querySelectorAll('main table').forEach((table) => {
        if (!table.tHead || !table.tBodies.length || table.getAttribute('role') === 'presentation' || table.querySelector(owned)) return;
        // A visually hidden header (ranking lists such as Top countries) gets
        // no invisible sort buttons in the keyboard order.
        const headStyle = getComputedStyle(table.tHead);
        if (headStyle.clip.startsWith('rect(0') || (headStyle.position === 'absolute' && parseFloat(headStyle.height) <= 1)) return;
        const headerRow = table.tHead.rows[table.tHead.rows.length - 1];
        if (!headerRow) return;
        const headers = [...headerRow.cells];
        headers.forEach((th, index) => {
          const label = (th.textContent || '').trim();
          if (!label || th.colSpan > 1) return;
          // A column whose header is only screen-reader text (e.g. row Actions) is not sortable.
          const visible = th.cloneNode?.(true);
          visible?.querySelectorAll?.('.sr-only').forEach((node) => node.remove());
          if (visible && !(visible.textContent || '').trim()) return;
          const button = document.createElement('button');
          button.type = 'button';
          button.className = 'device-sort-button';
          button.setAttribute('aria-label', label);
          button.append(...th.childNodes);
          const indicator = document.createElement('span');
          indicator.className = 'sort-indicator';
          indicator.setAttribute('aria-hidden', 'true');
          indicator.dataset.sort = 'none';
          button.append(' ', indicator);
          th.append(button);
          th.setAttribute('aria-sort', 'none');
          button.addEventListener('click', () => {
            const direction = th.getAttribute('aria-sort') === 'ascending' ? 'descending' : 'ascending';
            headers.forEach((other) => {
              if (!other.hasAttribute('aria-sort')) return;
              other.setAttribute('aria-sort', other === th ? direction : 'none');
              const mark = other.querySelector('.sort-indicator');
              if (mark) mark.dataset.sort = other === th ? direction : 'none';
            });
            const body = table.tBodies[0];
            const groups = [];
            [...body.rows].forEach((row) => {
              const attached = row.cells.length === 1 && row.cells[0].colSpan > 1;
              if (attached && groups.length) groups[groups.length - 1].push(row);
              else groups.push([row]);
            });
            const keyed = groups.map((group, order) => ({group, order, value: valueOf(group[0].cells[index])}));
            keyed.sort((a, b) => {
              if (a.value === null || b.value === null) return (a.value === null) - (b.value === null) || a.order - b.order;
              const result = compare(a.value, b.value);
              return (direction === 'descending' ? -result : result) || a.order - b.order;
            });
            body.append(...keyed.flatMap((item) => item.group));
            table.dispatchEvent(new CustomEvent('admin:table-sorted', {bubbles: true}));
          });
        });
      });
    })();"""


def _admin_chart_values_script() -> str:
    """Tap, click or keyboard focus on a chart bucket fills the chart's value
    strip (date, every series and total); no hover is required."""
    return r"""(() => {
      const show = (group) => {
        const wrap = group.closest('.overview-chart-wrap');
        const strip = wrap && wrap.querySelector('[data-chart-values-strip]');
        if (!strip) return;
        let data;
        try { data = JSON.parse(group.dataset.chartValues || ''); } catch { return; }
        wrap.querySelectorAll('.overview-chart-group.is-selected').forEach((node) => node.classList.remove('is-selected'));
        group.classList.add('is-selected');
        const parts = [];
        const date = document.createElement('strong');
        date.className = 'overview-chart-values-date';
        date.textContent = String(data.date || '');
        parts.push(date);
        (data.values || []).forEach(([name, label, value]) => {
          const item = document.createElement('span');
          const swatch = document.createElement('i');
          if (/^[a-z-]+$/.test(String(name))) swatch.className = 'overview-chart-' + name;
          swatch.setAttribute('aria-hidden', 'true');
          const count = document.createElement('strong');
          count.textContent = value === null || value === undefined ? '—' : Number(value).toLocaleString('en-US');
          item.append(swatch, document.createTextNode(String(label) + ' '), count);
          parts.push(item);
        });
        if (data.total !== null && data.total !== undefined) {
          const total = document.createElement('span');
          const count = document.createElement('strong');
          count.textContent = Number(data.total).toLocaleString('en-US');
          total.append(document.createTextNode('Total '), count);
          parts.push(total);
        }
        strip.replaceChildren(...parts);
      };
      const target = (event) => event.target instanceof Element ? event.target.closest('.overview-chart-group[data-chart-values]') : null;
      document.addEventListener('click', (event) => { const group = target(event); if (group) show(group); });
      document.addEventListener('focusin', (event) => { const group = target(event); if (group) show(group); });
      document.addEventListener('keydown', (event) => {
        const group = target(event);
        if (group && (event.key === 'Enter' || event.key === ' ')) { event.preventDefault(); show(group); }
      });
    })();"""


def _admin_mobile_collapse_script() -> str:
    """Long cards marked ``data-mobile-collapse`` start collapsed at ≤600 px;
    the Show/Hide button and links into the card reopen them."""
    return r"""(() => {
      const narrow = matchMedia('(max-width: 600px)');
      const set = (card, open) => {
        const button = card.querySelector('[data-mobile-collapse-toggle]');
        card.toggleAttribute('data-mobile-collapsed', !open);
        if (!button) return;
        button.setAttribute('aria-expanded', String(open));
        button.firstChild.textContent = open ? 'Hide' : 'Show';
      };
      const adapt = () => {
        document.querySelectorAll('[data-mobile-collapse]').forEach((card) => {
          const button = card.querySelector('[data-mobile-collapse-toggle]');
          if (button) button.hidden = !narrow.matches;
          if (!narrow.matches) set(card, true);
          else if (!card.dataset.mobileCollapseReady) set(card, false);
          card.dataset.mobileCollapseReady = narrow.matches ? 'true' : '';
        });
      };
      const reveal = () => {
        let id;
        try { id = decodeURIComponent(location.hash.slice(1)); } catch { return; }
        const target = id && document.getElementById(id);
        const card = target && target.closest('[data-mobile-collapse]');
        if (card) set(card, true);
      };
      document.addEventListener('click', (event) => {
        const button = event.target instanceof Element ? event.target.closest('[data-mobile-collapse-toggle]') : null;
        const card = button && button.closest('[data-mobile-collapse]');
        if (card) set(card, card.hasAttribute('data-mobile-collapsed'));
      });
      narrow.addEventListener('change', adapt);
      window.addEventListener('terento-admin-content-changed', adapt);
      window.addEventListener('hashchange', reveal);
      adapt();
      reveal();
    })();"""


def _admin_disclosure_script() -> str:
    return r"""(() => {
      const reveal = () => {
        let id;
        try { id = decodeURIComponent(location.hash.slice(1)); } catch { return; }
        if (!id) return;
        const target = document.getElementById(id);
        if (!target) return;
        let node = target;
        while (node) { if (node.tagName === 'DETAILS') node.open = true; node = node.parentElement; }
        target.scrollIntoView({block:'start'});
      };
      window.addEventListener('hashchange', reveal);
      document.addEventListener('click', (event) => {
        const anchor = event.target.closest('a[href^="#"]');
        if (anchor && anchor.hash === location.hash) reveal();
      });
      reveal();
    })();"""


def _admin_mobile_script() -> str:
    return r"""(() => {
      const narrow = matchMedia('(max-width: 760px)');
      const header = document.querySelector('.admin-topbar');
      const toggle = document.querySelector('#admin-menu-toggle');
      const panel = document.querySelector('#admin-menu-panel');
      if (header && toggle && panel) {
        header.classList.add('admin-mobile-ready');
        const close = (focus = false) => {
          toggle.setAttribute('aria-expanded', 'false');
          panel.hidden = narrow.matches;
          if (focus) toggle.focus();
        };
        const adapt = () => { toggle.hidden = !narrow.matches; close(); };
        toggle.addEventListener('click', () => {
          const open = toggle.getAttribute('aria-expanded') !== 'true';
          toggle.setAttribute('aria-expanded', String(open)); panel.hidden = !open;
        });
        document.addEventListener('keydown', event => {
          if (event.key === 'Escape' && narrow.matches && !panel.hidden) close(true);
        });
        document.addEventListener('click', event => {
          if (narrow.matches && !header.contains(event.target)) close();
        });
        document.addEventListener('focusin', event => { if (narrow.matches && !header.contains(event.target)) close(); });
        panel.addEventListener('click', event => { if (event.target.closest('a')) close(); });
        narrow.addEventListener('change', adapt); adapt();
      }
      const forms = document.querySelectorAll('#evidence-filters, #device-filters');
      forms.forEach(form => {
        const labels = [...form.children].filter(e => e.tagName === 'LABEL' && !e.hidden && !e.classList.contains('filter-search'));
        if (!labels.length) return;
        const extra = document.createElement('div'); extra.className = 'mobile-filter-options'; extra.id = form.id + '-extra';
        const button = document.createElement('button'); button.type = 'button'; button.className = 'mobile-filter-toggle secondary-button';
        button.textContent = 'Filters and sorting'; button.setAttribute('aria-controls', extra.id);
        form.insertBefore(button, labels[0]); form.insertBefore(extra, labels[0]); labels.forEach(label => extra.append(label));
        const adapt = () => { extra.hidden = narrow.matches; button.hidden = !narrow.matches; button.setAttribute('aria-expanded', 'false'); };
        button.addEventListener('click', () => { extra.hidden = !extra.hidden; button.setAttribute('aria-expanded', String(!extra.hidden)); });
        const update = () => {
          const active = [...extra.querySelectorAll('select')].filter(control => !control.id.includes('sort') && control.value !== 'all').length;
          button.textContent = active ? `Filters and sorting · ${active} active` : 'Filters and sorting';
        };
        form.addEventListener('change', update); update();
        narrow.addEventListener('change', adapt); adapt();
      });
      const labelTables = () => {
        document.querySelectorAll('main table').forEach(table => {
          if (table.closest('.device-sticky-header')) return;
          const headers = [...table.querySelectorAll('thead th')];
          if (!headers.length) return;
          // Tables with their own narrow layout (Health checks, the Top countries
          // and Top maps ranking lists) keep the semantic roles but not the
          // record-card styling.
          if (!table.hasAttribute('data-own-mobile-layout')) table.classList.add('mobile-record-table');
          table.setAttribute('role', 'table');
          table.querySelectorAll('tbody').forEach(body => body.setAttribute('role', 'rowgroup'));
          table.querySelectorAll('tbody tr').forEach(row => {
            if (!row.hasAttribute('role')) row.setAttribute('role', 'row');
            [...row.cells].forEach((cell, i) => {
              if (!cell.dataset.label) cell.dataset.label = cell.colSpan > 1 ? '' : (headers[i]?.getAttribute('aria-label') || headers[i]?.textContent || '').replace(/[↕↑↓]/g, '').trim();
              cell.setAttribute('role', 'cell');
            });
          });
        });
      };
      labelTables();
      const main = document.querySelector('main');
      if (main) new MutationObserver(labelTables).observe(main, {childList:true, subtree:true});
    })();"""


def _admin_quick_select_script() -> str:
    """Keep ``_quick_select_filter`` buttons and their hidden select in sync."""
    return r"""(() => {
      document.querySelectorAll('[data-quick-select]').forEach((group) => {
        const select = document.getElementById(group.dataset.quickSelect);
        if (!select) return;
        const buttons = [...group.querySelectorAll('[data-quick-value]')];
        const sync = () => buttons.forEach((button) => {
          const active = button.dataset.quickValue === select.value;
          button.classList.toggle('active', active);
          button.setAttribute('aria-pressed', active ? 'true' : 'false');
        });
        buttons.forEach((button) => button.addEventListener('click', () => {
          if (select.value === button.dataset.quickValue) return;
          select.value = button.dataset.quickValue;
          sync();
          select.dispatchEvent(new Event('input', {bubbles: true}));
          select.dispatchEvent(new Event('change', {bubbles: true}));
        }));
        select.addEventListener('change', sync);
        select.form?.addEventListener('change', sync);
        select.form?.addEventListener('terento-admin-clear-filters', () => setTimeout(sync));
        sync();
      });
    })();"""


def _admin_row_menu_script() -> str:
    """Row action menus open above the table's clipping box.

    Tables scroll horizontally, so their wrappers clip absolutely positioned
    popovers. An open ``.provider-row-menu`` body is placed with fixed
    coordinates below its button, or above it when the viewport has no room
    below; one menu is open at a time and it closes on Escape, an outside
    click, scroll or resize.
    """
    return r"""(() => {
      const menus = () => [...document.querySelectorAll('details.provider-row-menu')];
      const place = (menu) => {
        const body = menu.querySelector('.provider-row-menu-body');
        const trigger = menu.querySelector('summary');
        if (!body || !trigger) return;
        body.classList.add('is-floating');
        const anchor = trigger.getBoundingClientRect();
        const width = Math.max(body.offsetWidth, 200);
        const height = body.offsetHeight;
        const gap = 6;
        const below = window.innerHeight - anchor.bottom - gap;
        const top = below >= height || anchor.top - gap < height ? anchor.bottom + gap : anchor.top - gap - height;
        const left = Math.min(Math.max(8, anchor.right - width), window.innerWidth - width - 8);
        body.style.top = `${Math.max(8, top)}px`;
        body.style.left = `${Math.max(8, left)}px`;
      };
      const closeAll = (except) => menus().forEach((menu) => { if (menu !== except && menu.open) menu.open = false; });
      document.addEventListener('toggle', (event) => {
        const target = event.target;
        if (!(target instanceof HTMLElement) || target.tagName !== 'DETAILS') return;
        if (target.matches('details.provider-row-menu')) {
          if (target.open) { closeAll(target); place(target); }
          return;
        }
        // A disclosure inside an open menu changes its height: place it again.
        const parent = target.closest('details.provider-row-menu');
        if (parent?.open) place(parent);
      }, true);
      document.addEventListener('click', (event) => {
        if (!event.target.closest?.('details.provider-row-menu')) closeAll(null);
      });
      document.addEventListener('keydown', (event) => {
        if (event.key !== 'Escape') return;
        const open = menus().find((menu) => menu.open);
        if (open) { open.open = false; open.querySelector('summary')?.focus(); }
      });
      const closeOnMove = (event) => {
        const open = menus().find((menu) => menu.open);
        if (open && !(event?.target instanceof Node && open.contains(event.target))) closeAll(null);
      };
      window.addEventListener('scroll', closeOnMove, {passive: true, capture: true});
      window.addEventListener('resize', () => closeAll(null), {passive: true});
    })();"""


def _admin_filter_clear_script() -> str:
    return r"""(() => {
      document.querySelectorAll('[data-filter-clear]').forEach((button) => {
        button.addEventListener('click', () => {
          const form = button.closest('form');
          if (!form) return;
          form.dispatchEvent(new CustomEvent('terento-admin-clear-filters'));
          form.dispatchEvent(new CustomEvent('change'));
        });
      });
    })();"""


def _admin_dropdown_script() -> str:
    """Admin filter dropdown (owner decision 2026-10-06).

    Native ``<select>`` popups cannot be styled and macOS draws them over the
    field, so every filter ``select[data-admin-dropdown]`` is enhanced with a
    combobox button and a listbox popover that opens below the field (above
    only when there is no room below) and never covers it. The native select
    stays in the DOM, labelled, as the source of truth: picking an option sets
    its value and dispatches bubbling ``input`` and ``change`` events, and
    programmatic value changes, option changes and ``disabled`` are mirrored.
    Selects in forms that post data are never marked.
    """
    return r"""(() => {
      const GAP = 4, MARGIN = 8;
      const descriptors = ['value', 'selectedIndex'].map((key) => [key, Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, key)]);
      const instances = new Set();
      let counter = 0, current = null, frame = 0;
      const nameOf = (select) => {
        const explicit = (select.getAttribute('aria-label') || '').trim();
        if (explicit) return explicit;
        const label = select.labels && select.labels[0];
        if (label) {
          const copy = label.cloneNode(true);
          copy.querySelectorAll('select, .admin-dropdown').forEach((node) => node.remove());
          const text = copy.textContent.replace(/\s+/g, ' ').trim();
          if (text) return text;
        }
        return (select.title || '').trim();
      };
      // Only typography follows the hidden native select. Horizontal padding is
      // owned by the stylesheet (--admin-control-padding-x): copying the select's
      // padding inline let a zero or theme-reset native padding (for example a
      // WebKit menulist) push the selected text against the field's left edge.
      const copyFont = (state) => {
        const style = getComputedStyle(state.select);
        ['fontFamily', 'fontSize', 'fontWeight', 'letterSpacing'].forEach((key) => { state.button.style[key] = style[key]; });
      };
      const sync = (state) => {
        const option = state.select.selectedOptions[0];
        state.value.textContent = option ? option.label : '';
        state.button.disabled = state.select.matches(':disabled');
        if (current === state) {
          if (state.button.disabled) close(state, false);
          else state.options.forEach((entry) => entry.item.setAttribute('aria-selected', String(entry.index === state.select.selectedIndex)));
        }
      };
      const render = (state) => {
        const {select, list} = state;
        list.replaceChildren();
        state.options = [];
        let group = null, container = list;
        [...select.options].forEach((option, index) => {
          if (option.hidden) return;
          const parent = option.parentElement && option.parentElement.tagName === 'OPTGROUP' ? option.parentElement : null;
          if (parent !== group) {
            group = parent; container = list;
            if (parent) {
              container = document.createElement('div');
              container.setAttribute('role', 'group');
              container.setAttribute('aria-label', parent.label);
              const heading = document.createElement('div');
              heading.className = 'admin-dropdown-group';
              heading.setAttribute('aria-hidden', 'true');
              heading.textContent = parent.label;
              container.append(heading);
              list.append(container);
            }
          }
          const item = document.createElement('div');
          item.className = 'admin-dropdown-option';
          item.id = `${list.id}-option-${index}`;
          item.setAttribute('role', 'option');
          item.setAttribute('aria-selected', String(index === select.selectedIndex));
          const disabled = option.disabled || Boolean(parent && parent.disabled);
          if (disabled) item.setAttribute('aria-disabled', 'true');
          const check = document.createElement('span');
          check.className = 'admin-dropdown-check';
          check.setAttribute('aria-hidden', 'true');
          const text = document.createElement('span');
          text.className = 'admin-dropdown-option-text';
          text.textContent = option.label;
          item.append(check, text);
          container.append(item);
          state.options.push({item, index, disabled, text: option.label.trim().toLowerCase()});
        });
      };
      const place = (state) => {
        const {button, list} = state;
        const rect = button.getBoundingClientRect();
        const viewportWidth = document.documentElement.clientWidth, viewportHeight = window.innerHeight;
        if (rect.bottom < 0 || rect.top > viewportHeight || (!rect.width && !rect.height)) { close(state, false); return; }
        list.style.minWidth = `${Math.round(rect.width)}px`;
        list.style.maxWidth = `${Math.max(Math.round(rect.width), viewportWidth - 2 * MARGIN)}px`;
        list.style.maxHeight = '';
        const height = list.offsetHeight, width = list.offsetWidth;
        const below = viewportHeight - rect.bottom - GAP - MARGIN, above = rect.top - GAP - MARGIN;
        let top;
        if (height <= below || below >= above) {
          if (height > below) list.style.maxHeight = `${Math.max(below, 0)}px`;
          top = rect.bottom + GAP;
          list.dataset.placement = 'below';
        } else {
          if (height > above) list.style.maxHeight = `${above}px`;
          top = rect.top - GAP - Math.min(height, above);
          list.dataset.placement = 'above';
        }
        let left = rect.left;
        if (left + width > viewportWidth - MARGIN) left = Math.max(MARGIN, viewportWidth - MARGIN - width);
        list.style.left = `${Math.round(left)}px`;
        list.style.top = `${Math.round(top)}px`;
      };
      const reveal = (state, item) => {
        const list = state.list;
        if (item.offsetTop < list.scrollTop) list.scrollTop = item.offsetTop - GAP;
        else if (item.offsetTop + item.offsetHeight > list.scrollTop + list.clientHeight) list.scrollTop = item.offsetTop + item.offsetHeight - list.clientHeight + GAP;
      };
      const activate = (state, position) => {
        const entries = state.options;
        if (!entries.length) return;
        state.active = Math.max(0, Math.min(entries.length - 1, position));
        entries.forEach((entry, index) => entry.item.classList.toggle('is-active', index === state.active));
        const item = entries[state.active].item;
        state.button.setAttribute('aria-activedescendant', item.id);
        reveal(state, item);
      };
      const enabledFrom = (state, start, direction) => {
        for (let index = start; index >= 0 && index < state.options.length; index += direction) {
          if (!state.options[index].disabled) return index;
        }
        return -1;
      };
      const move = (state, target, direction) => {
        const limit = Math.max(0, Math.min(state.options.length - 1, target));
        let next = enabledFrom(state, limit, direction);
        if (next < 0) next = enabledFrom(state, limit, -direction);
        if (next >= 0) activate(state, next);
      };
      const typeahead = (state, character) => {
        clearTimeout(state.typeTimer);
        state.typed += character.toLowerCase();
        state.typeTimer = setTimeout(() => { state.typed = ''; }, 600);
        const repeated = state.typed.split('').every((value) => value === state.typed[0]);
        const search = repeated ? state.typed[0] : state.typed;
        const count = state.options.length;
        const start = repeated ? state.active + 1 : Math.max(state.active, 0);
        for (let offset = 0; offset < count; offset++) {
          const index = (start + offset) % count;
          const entry = state.options[index];
          if (!entry.disabled && entry.text.startsWith(search)) { activate(state, index); return; }
        }
      };
      const open = (state, keyboard, position) => {
        if (state.button.disabled) return;
        if (current && current !== state) close(current, false);
        render(state);
        if (!state.options.length) return;
        copyFont(state);
        ['fontSize', 'fontFamily'].forEach((key) => { state.list.style[key] = state.button.style[key]; });
        state.list.classList.toggle('is-keyboard', keyboard);
        state.list.hidden = false;
        state.button.setAttribute('aria-expanded', 'true');
        current = state;
        place(state);
        if (current !== state) return;
        const selected = state.options.findIndex((entry) => entry.index === state.select.selectedIndex);
        if (position === 'first') move(state, 0, 1);
        else if (position === 'last') move(state, state.options.length - 1, -1);
        else if (selected >= 0) activate(state, selected);
        else move(state, 0, 1);
      };
      const close = (state, focus) => {
        state.list.hidden = true;
        state.list.classList.remove('is-keyboard');
        state.button.setAttribute('aria-expanded', 'false');
        state.button.removeAttribute('aria-activedescendant');
        if (current === state) current = null;
        if (focus) state.button.focus();
      };
      const choose = (state, entry) => {
        if (!entry || entry.disabled) return;
        const select = state.select;
        close(state, true);
        if (select.selectedIndex === entry.index) return;
        select.selectedIndex = entry.index;
        select.dispatchEvent(new Event('input', {bubbles: true}));
        select.dispatchEvent(new Event('change', {bubbles: true}));
      };
      const printable = (event) => event.key.length === 1 && !event.ctrlKey && !event.metaKey && !event.altKey;
      const onKey = (state, event) => {
        const key = event.key, isOpen = current === state;
        if (!isOpen) {
          if (['Enter', ' ', 'ArrowDown', 'ArrowUp', 'Home', 'End'].includes(key) || printable(event)) {
            event.preventDefault();
            state.keyAt = performance.now();
            open(state, true, key === 'Home' ? 'first' : key === 'End' ? 'last' : null);
            if (printable(event) && key !== ' ') typeahead(state, key);
          }
          return;
        }
        state.list.classList.add('is-keyboard');
        const active = state.options[state.active];
        if (key === 'ArrowDown') move(state, state.active + 1, 1);
        else if (key === 'ArrowUp' && event.altKey) choose(state, active);
        else if (key === 'ArrowUp') move(state, state.active - 1, -1);
        else if (key === 'Home') move(state, 0, 1);
        else if (key === 'End') move(state, state.options.length - 1, -1);
        else if (key === 'PageDown') move(state, state.active + 10, 1);
        else if (key === 'PageUp') move(state, state.active - 10, -1);
        else if (key === 'Enter' || (key === ' ' && !state.typed)) { state.keyAt = performance.now(); choose(state, active); }
        else if (key === 'Escape') { event.stopPropagation(); close(state, true); }
        else if (key === 'Tab') { close(state, false); return; }
        else if (printable(event)) typeahead(state, key);
        else return;
        event.preventDefault();
      };
      const enhance = (select) => {
        if (select.dataset.adminDropdownReady === 'true') return;
        select.dataset.adminDropdownReady = 'true';
        const id = `admin-dropdown-${++counter}`;
        const name = document.createElement('span');
        name.id = `${id}-name`; name.hidden = true; name.textContent = nameOf(select);
        const wrapper = document.createElement('span');
        wrapper.className = 'admin-dropdown';
        const button = document.createElement('button');
        button.type = 'button'; button.id = `${id}-button`; button.className = 'admin-dropdown-button';
        button.setAttribute('role', 'combobox');
        button.setAttribute('aria-haspopup', 'listbox');
        button.setAttribute('aria-expanded', 'false');
        button.setAttribute('aria-controls', `${id}-list`);
        button.setAttribute('aria-labelledby', name.id);
        const value = document.createElement('span');
        value.className = 'admin-dropdown-value';
        const chevron = document.createElement('span');
        chevron.className = 'admin-dropdown-chevron';
        chevron.setAttribute('aria-hidden', 'true');
        button.append(value, chevron);
        const list = document.createElement('div');
        list.id = `${id}-list`; list.className = 'admin-dropdown-list'; list.hidden = true;
        list.setAttribute('role', 'listbox');
        list.setAttribute('aria-labelledby', name.id);
        select.before(wrapper);
        wrapper.append(select, name, button);
        (select.closest('dialog') || document.body).append(list);
        select.tabIndex = -1;
        select.setAttribute('aria-hidden', 'true');
        const state = {select, wrapper, button, value, list, options: [], active: -1, typed: '', typeTimer: 0, keyAt: 0};
        instances.add(state);
        descriptors.forEach(([key, descriptor]) => {
          if (!descriptor || !descriptor.set) return;
          Object.defineProperty(select, key, {
            configurable: true, enumerable: descriptor.enumerable,
            get() { return descriptor.get.call(this); },
            set(next) { descriptor.set.call(this, next); sync(state); },
          });
        });
        select.addEventListener('change', () => sync(state));
        select.addEventListener('input', () => sync(state));
        select.addEventListener('focus', () => { if (!button.disabled) button.focus(); });
        select.form?.addEventListener('reset', () => setTimeout(() => sync(state)));
        new MutationObserver(() => sync(state)).observe(select, {subtree: true, childList: true, characterData: true, attributes: true, attributeFilter: ['disabled', 'selected', 'label', 'hidden']});
        button.addEventListener('click', (event) => {
          if (event.detail === 0 && performance.now() - state.keyAt < 500) return;
          if (current === state) close(state, true);
          else open(state, event.detail === 0, null);
        });
        button.addEventListener('keydown', (event) => onKey(state, event));
        button.addEventListener('keyup', (event) => { if (event.key === ' ') event.preventDefault(); });
        button.addEventListener('focusout', (event) => {
          if (current === state && !list.contains(event.relatedTarget)) close(state, false);
        });
        list.addEventListener('mousedown', (event) => event.preventDefault());
        list.addEventListener('mousemove', (event) => {
          const item = event.target instanceof Element ? event.target.closest('[role="option"]') : null;
          const position = state.options.findIndex((entry) => entry.item === item);
          if (position < 0 || position === state.active) return;
          list.classList.remove('is-keyboard');
          activate(state, position);
        });
        list.addEventListener('click', (event) => {
          const item = event.target instanceof Element ? event.target.closest('[role="option"]') : null;
          choose(state, state.options.find((entry) => entry.item === item));
        });
        copyFont(state);
        sync(state);
      };
      const scan = () => {
        instances.forEach((state) => {
          if (state.select.isConnected) return;
          if (current === state) current = null;
          state.list.remove();
          instances.delete(state);
        });
        document.querySelectorAll('select[data-admin-dropdown]').forEach(enhance);
      };
      const refresh = () => {
        frame = 0;
        instances.forEach(copyFont);
        if (current) place(current);
      };
      document.addEventListener('pointerdown', (event) => {
        if (current && !current.wrapper.contains(event.target) && !current.list.contains(event.target)) close(current, false);
      }, true);
      window.addEventListener('resize', () => { if (!frame) frame = requestAnimationFrame(refresh); });
      document.addEventListener('scroll', (event) => { if (current && event.target !== current.list && !frame) frame = requestAnimationFrame(refresh); }, true);
      window.addEventListener('terento-admin-content-changed', scan);
      new MutationObserver(scan).observe(document.body, {childList: true, subtree: true});
      scan();
    })();"""


def _admin_freshness_script() -> str:
    """Freshness notice (docs/admin-behavior-contract.md, "Freshness notice").

    The open page re-reads its own URL every two minutes while visible and
    compares the section revisions it rendered with the fresh ones. Only a
    changed revision, a failed check or an expired session shows the compact
    notice: status icon and text, a secondary Refresh action and Dismiss.
    """
    icons = json.dumps({key: _admin_icon(name) for key, name in (("info", "info"), ("warning", "alert"), ("close", "close"))})
    return r"""(() => {
      if (!document.querySelector('[data-admin-revisions]') || document.querySelector('#admin-live-update')) return;
      const icons = __ADMIN_LIVE_ICONS__;
      const notice = document.createElement('div');
      notice.id = 'admin-live-update'; notice.className = 'admin-live-update';
      notice.setAttribute('role', 'status'); notice.setAttribute('aria-live', 'polite'); notice.hidden = true;
      const icon = document.createElement('span'); icon.className = 'admin-live-update-icon';
      const message = document.createElement('span'); message.className = 'admin-live-update-text';
      const refresh = document.createElement('button');
      refresh.type = 'button'; refresh.className = 'secondary-button admin-live-update-refresh'; refresh.textContent = 'Refresh';
      const dismiss = document.createElement('button');
      dismiss.type = 'button'; dismiss.className = 'admin-live-update-dismiss';
      dismiss.setAttribute('aria-label', 'Dismiss notice'); dismiss.innerHTML = icons.close;
      notice.append(icon, message, refresh, dismiss);
      const topbar = document.querySelector('.admin-topbar');
      if (topbar) topbar.after(notice); else document.body.append(notice);
      let dirty = false, generation = 0, running = false, pending = null, shownKey = '', dismissedKey = '';
      const read = node => JSON.parse(node?.dataset.adminRevisions || '{}');
      // One notice, three states. Dismiss hides the current state until a
      // different one (for example a further change) arrives.
      const show = (tone, text, key) => {
        shownKey = key;
        if (key === dismissedKey) { notice.hidden = true; return; }
        notice.setAttribute('data-tone', tone);
        icon.innerHTML = icons[tone];
        message.textContent = text;
        notice.hidden = false;
      };
      const hide = () => { shownKey = ''; dismissedKey = ''; notice.hidden = true; };
      const update = () => {
        if (!pending) { hide(); return; }
        const shown = read(document.querySelector('[data-admin-revisions]'));
        const changed = Object.keys(pending).filter(key => pending[key] !== shown[key]).sort();
        if (!changed.length) { hide(); return; }
        show('info', 'New data is available for this page.', 'changed:' + changed.map(key => key + '=' + pending[key]).join(','));
      };
      dismiss.addEventListener('click', () => { dismissedKey = shownKey; notice.hidden = true; });
      document.addEventListener('input', event => {
        if (event.target.closest('form[method="post"]')) dirty = true;
      });
      document.addEventListener('change', event => {
        if (event.target.closest('form[method="post"]')) dirty = true;
      });
      refresh.addEventListener('click', () => {
        if (!dirty || window.confirm('Refresh and discard unsaved edits?')) window.location.reload();
      });
      window.addEventListener('terento-admin-content-changed', () => { generation++; pending = null; update(); });
      window.addEventListener('terento-admin-sections-rendered', event => {
        generation++;
        const current = document.querySelector('[data-admin-revisions]');
        current.dataset.adminRevisions = JSON.stringify({...read(current), ...event.detail});
        update();
      });
      window.addEventListener('popstate', () => { generation++; });
      const check = async () => {
        if (document.hidden || running) return;
        const current = document.querySelector('[data-admin-revisions]');
        if (!current || current.getAttribute('aria-busy') === 'true') return;
        running = true;
        const url = window.location.href, started = generation;
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 15000);
        const stale = () => document.hidden || generation !== started || window.location.href !== url || document.querySelector('[data-admin-revisions]') !== current;
        try {
          const response = await fetch(url, {credentials:'same-origin', cache:'no-store', signal:controller.signal});
          if (stale()) return;
          if ((response.redirected && new URL(response.url).pathname === '/admin/login') || response.status === 401 || response.status === 403) {
            show('warning', 'Your session expired. Refresh to sign in.', 'session'); return;
          }
          if (!response.ok) throw new Error('Unavailable');
          const next = new DOMParser().parseFromString(await response.text(), 'text/html').querySelector('[data-admin-revisions]');
          if (stale()) return;
          if (!next) throw new Error('Missing snapshot');
          pending = read(next); update();
        } catch (_) {
          if (!stale()) show('warning', 'Live check unavailable. Refresh to try again.', 'unavailable');
        } finally { clearTimeout(timeout); running = false; }
      };
      // Lighter freshness polling (ADM-27): every two minutes while visible,
      // plus one check when the tab becomes visible again.
      setInterval(check, 120000);
      document.addEventListener('visibilitychange', () => { if (!document.hidden) check(); });
    })();""".replace("__ADMIN_LIVE_ICONS__", icons)


def _decode_base64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
