from __future__ import annotations

import argparse
import json
import logging

from .collectors import FreizeitkarteCollector
from .config import Settings
from .db import Database

LOGGER = logging.getLogger(__name__)


def collect_once(database: Database, *, dry_run: bool = False) -> int:
    records = FreizeitkarteCollector().collect()
    if not records:
        raise RuntimeError("Freizeitkarte collector returned no records")
    if not dry_run:
        database.upsert_collected_maps(records)

    for record in records:
        LOGGER.info(
            "Freizeitkarte %s %s-%02d download=%s install=%s source=%s",
            record.map.id,
            record.version.year,
            record.version.month,
            record.download_size_bytes if record.download_size_bytes is not None else "unknown",
            record.install_size_bytes if record.install_size_bytes is not None else "unknown",
            record.source_url,
        )
        if record.size_measurement_warning:
            LOGGER.warning(
                "Freizeitkarte %s size measurement warning: %s",
                record.map.id,
                record.size_measurement_warning,
            )
    return len(records)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Collect all official Freizeitkarte Garmin metadata"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="fetch and validate provider metadata without writing PostgreSQL",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = Settings.from_env()
    count = collect_once(
        Database(
            settings.database_url,
            connect_timeout_seconds=settings.database_connect_timeout_seconds,
        ),
        dry_run=args.dry_run,
    )
    print(json.dumps({"collector": "freizeitkarte", "records": count}))


if __name__ == "__main__":
    main()
