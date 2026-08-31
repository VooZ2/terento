from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

from .collect import collect_once, collect_provider_once
from .collect_devices import collect_devices_once
from .config import Settings
from .db import Database
from .provider_catalog import OpenTopoMapProviderAdapter

LOGGER = logging.getLogger(__name__)
WEEKDAYS = {
    "MON": 0,
    "TUE": 1,
    "WED": 2,
    "THU": 3,
    "FRI": 4,
    "SAT": 5,
    "SUN": 6,
}


def run_schedule(database: Database, schedule_utc: str) -> None:
    weekday, hour, minute = _parse_schedule(schedule_utc)
    while True:
        now = datetime.now(timezone.utc)
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if weekday is None:
            if target <= now:
                target += timedelta(days=1)
        else:
            days_until_target = (weekday - now.weekday()) % 7
            if days_until_target == 0 and target <= now:
                days_until_target = 7
            target += timedelta(days=days_until_target)
        wait_seconds = max(1, (target - now).total_seconds())
        LOGGER.info("next metadata collection at %s", target.isoformat())
        time.sleep(wait_seconds)
        run_collection_cycle(database)


def run_collection_cycle(database: Database) -> None:
    """Run independent weekly metadata jobs without cross-provider blocking."""

    jobs = (
        ("Freizeitkarte", lambda: collect_once(database)),
        (
            "OpenTopoMap",
            lambda: collect_provider_once(database, OpenTopoMapProviderAdapter()),
        ),
        ("Garmin device", lambda: collect_devices_once(database)),
    )
    for label, job in jobs:
        try:
            job()
        except Exception:
            # One upstream failure must not suppress the other independent
            # provider/device metadata jobs or the next scheduled cycle.
            LOGGER.exception("scheduled %s collection failed", label)


def run_daily(database: Database, schedule_utc: str) -> None:
    """Backward-compatible alias for callers using the old scheduler name."""

    run_schedule(database, schedule_utc)


def _parse_schedule(value: str) -> tuple[int | None, int, int]:
    parts = value.strip().upper().split()
    if len(parts) == 1:
        weekday = None
        time_text = parts[0]
    elif len(parts) == 2:
        weekday = WEEKDAYS.get(parts[0])
        time_text = parts[1]
        if weekday is None:
            raise RuntimeError("COLLECTOR_SCHEDULE_UTC must start with MON-SUN")
    else:
        raise RuntimeError("COLLECTOR_SCHEDULE_UTC must use [MON-SUN ]HH:MM")
    try:
        hour_text, minute_text = time_text.split(":", 1)
        hour, minute = int(hour_text), int(minute_text)
    except (ValueError, AttributeError) as exc:
        raise RuntimeError("COLLECTOR_SCHEDULE_UTC must use [MON-SUN ]HH:MM") from exc
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise RuntimeError("COLLECTOR_SCHEDULE_UTC must use a valid UTC time")
    return weekday, hour, minute


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = Settings.from_env()
    run_schedule(
        Database(
            settings.database_url,
            connect_timeout_seconds=settings.database_connect_timeout_seconds,
        ),
        settings.collector_schedule_utc,
    )


if __name__ == "__main__":
    main()
