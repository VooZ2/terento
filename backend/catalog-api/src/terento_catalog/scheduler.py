from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

from .collect import collect_once
from .collect_devices import collect_devices_once
from .config import Settings
from .db import Database

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
        _record_heartbeat(database, status="WAITING", next_run_at=target)
        time.sleep(wait_seconds)
        started_at = datetime.now(timezone.utc)
        _record_heartbeat(database, status="RUNNING", started_at=started_at)
        try:
            collect_once(database)
        except Exception:
            # A failed provider fetch must not stop the next scheduled attempt.
            LOGGER.exception("scheduled Freizeitkarte collection failed")
            _record_heartbeat(
                database,
                status="FAILED",
                completed_at=datetime.now(timezone.utc),
                error_summary="Map catalog collection failed; see scheduler logs.",
            )
            continue
        try:
            collect_devices_once(database)
        except Exception:
            # Garmin discovery is independent from the map catalog. A failed
            # device fetch must not invalidate the successful map collection.
            LOGGER.exception("scheduled Garmin device collection failed")
            _record_heartbeat(
                database,
                status="WARNING",
                completed_at=datetime.now(timezone.utc),
                error_summary="Map catalog succeeded; Garmin device collection failed.",
            )
            continue
        _record_heartbeat(
            database,
            status="HEALTHY",
            completed_at=datetime.now(timezone.utc),
        )


def run_daily(database: Database, schedule_utc: str) -> None:
    """Backward-compatible alias for callers using the old scheduler name."""

    run_schedule(database, schedule_utc)


def _record_heartbeat(database: Database, **values: object) -> None:
    try:
        database.record_scheduler_heartbeat(**values)
    except Exception:
        # Heartbeat observability must not suppress a future scheduled run.
        LOGGER.exception("scheduler heartbeat update failed")


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
