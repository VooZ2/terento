from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

from .collect import collect_all_providers, official_provider_adapters
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
        run_collection_cycle(database, collect_device_catalog=target.weekday() == 0)


def run_collection_cycle(
    database: Database, *, collect_device_catalog: bool = True,
) -> dict[str, object]:
    """Run one isolated provider sweep plus the independent device collector."""

    outcomes = collect_all_providers(database, official_provider_adapters())
    failed_providers = sorted(
        provider_id
        for provider_id, result in outcomes.items()
        if result.get("status") != "SUCCEEDED"
    )
    device_error: str | None = None
    if collect_device_catalog:
        try:
            collect_devices_once(database)
        except Exception as exc:
            LOGGER.exception("scheduled Garmin device collection failed")
            device_error = f"{type(exc).__name__}: {str(exc)[:300]}"

    expected_provider_count = len(outcomes)
    if expected_provider_count and len(failed_providers) == expected_provider_count:
        status = "FAILED"
    elif failed_providers or device_error:
        status = "WARNING"
    else:
        status = "HEALTHY"

    problems: list[str] = []
    if failed_providers:
        problems.append("Catalog failed: " + ", ".join(failed_providers) + ".")
    if device_error:
        problems.append("Garmin device catalog failed: " + device_error)
    error_summary = " ".join(problems) or None
    _record_heartbeat(
        database,
        status=status,
        completed_at=datetime.now(timezone.utc),
        error_summary=error_summary,
    )
    return {
        "status": status,
        "providers": outcomes,
        "deviceError": device_error,
    }


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
