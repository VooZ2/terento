from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timezone

from .collectors.garmin import GarminCollector, GarminCollectionResult
from .config import Settings
from .db import Database

LOGGER = logging.getLogger(__name__)


def collect_devices_once(
    database: Database,
    *,
    dry_run: bool = False,
    collector: GarminCollector | None = None,
) -> GarminCollectionResult:
    started_at = datetime.now(timezone.utc)
    source_url = (collector or GarminCollector()).category_source_url
    try:
        result = (collector or GarminCollector()).collect()
    except Exception as exc:
        if not dry_run:
            _record_failure(database, source_url, started_at, exc)
        raise

    if not dry_run:
        database.upsert_collected_devices(
            result.records,
            collection_complete=result.complete,
        )
        database.record_device_collection_run(
            source_url=source_url,
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
            status="SUCCEEDED" if result.complete else "PARTIAL",
            discovered_count=result.discovered_products,
            canonical_count=result.canonical_devices,
            warning_count=len(result.warnings),
            diagnostics={"warnings": list(result.warnings)},
        )

    for warning in result.warnings:
        LOGGER.warning("Garmin collector: %s", warning)
    LOGGER.info(
        "Garmin catalog: %d products -> %d canonical devices",
        result.discovered_products,
        result.canonical_devices,
    )
    return result


def _record_failure(
    database: Database,
    source_url: str,
    started_at: datetime,
    error: Exception,
) -> None:
    try:
        database.record_device_collection_run(
            source_url=source_url,
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
            status="FAILED",
            discovered_count=0,
            canonical_count=0,
            warning_count=1,
            diagnostics={"error": str(error)},
        )
    except Exception:
        LOGGER.exception("could not record failed Garmin collection")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Collect Garmin smartwatch metadata without downloading images"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="fetch and validate Garmin metadata without writing PostgreSQL",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = Settings.from_env()
    result = collect_devices_once(
        Database(
            settings.database_url,
            connect_timeout_seconds=settings.database_connect_timeout_seconds,
        ),
        dry_run=args.dry_run,
    )
    print(
        json.dumps(
            {
                "collector": "garmin",
                "discoveredProducts": result.discovered_products,
                "canonicalDevices": result.canonical_devices,
                "warnings": len(result.warnings),
            }
        )
    )


if __name__ == "__main__":
    main()
