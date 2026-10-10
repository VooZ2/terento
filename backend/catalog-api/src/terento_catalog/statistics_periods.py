"""Selected-period windows for the Admin statistics read models.

The period set and its trend grid are owned by
``contracts/STATISTICS_CONTRACT.md``. ``today`` is the current calendar day in
the request's time zone: it starts at local midnight and runs until now. The
rolling periods end now and start a fixed duration earlier; ``all`` has no
start. This module has no database or HTTP dependencies.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# Picker order (owner request 2026-10-07): Today first.
ADMIN_PERIODS: tuple[str, ...] = ("today", "24h", "7d", "30d", "all")

ADMIN_PERIOD_LABELS: dict[str, str] = {
    "today": "Today",
    "24h": "Last 24 hours",
    "7d": "Last 7 days",
    "30d": "Last 30 days",
    "all": "All time",
}

# One trend grid per period; ``all`` is adapted to the observed span by the
# read models.
PERIOD_BUCKETS: dict[str, str] = {
    "today": "hour",
    "24h": "hour",
    "7d": "day",
    "30d": "week",
    "all": "month",
}


def all_time_bucket(span: timedelta) -> str:
    """The ``all`` trend grid for an observed span: day, week or month."""
    return "day" if span <= timedelta(days=14) else "week" if span <= timedelta(days=60) else "month"


_ROLLING_PERIODS: dict[str, timedelta] = {
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
}


def _zone(time_zone: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(str(time_zone or "UTC"))
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def local_day_start(now: datetime, time_zone: str | None = "UTC") -> datetime:
    """Return local midnight of ``now``'s calendar day in ``time_zone``, in UTC.

    An unknown zone falls back to UTC. Where a DST change skips local
    midnight, the day starts at its first existing local instant; where a
    change repeats midnight, it starts at the first occurrence.
    """
    zone = _zone(time_zone)
    local = _utc(now).astimezone(zone)
    midnight = datetime(local.year, local.month, local.day, tzinfo=zone)
    return midnight.astimezone(timezone.utc)


def period_start(
    period: str, *, now: datetime, time_zone: str | None = "UTC",
) -> datetime | None:
    """Return the inclusive UTC start of ``period`` ending at ``now``.

    ``all`` has no start (``None``). Unknown periods raise ``ValueError``;
    callers validate or fall back first, exactly as before ``today`` existed.
    """
    if period == "today":
        return local_day_start(now, time_zone)
    if period == "all":
        return None
    duration = _ROLLING_PERIODS.get(period)
    if duration is None:
        raise ValueError(f"unknown statistics period: {period!r}")
    return _utc(now) - duration
