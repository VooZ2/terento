from __future__ import annotations

import argparse
import json
import logging
from dataclasses import dataclass

from .collectors.freizeitkarte.range_zip import (
    HTTPRangeFetcher,
    ZipRangeError,
    ZipRangeInspector,
)
from .config import Settings
from .db import Database

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class SizeBackfillResult:
    processed: int = 0
    measured: int = 0
    known_install_size: int = 0
    unknown_install_size: int = 0
    changed: int = 0
    failed: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "processed": self.processed,
            "measured": self.measured,
            "knownInstallSize": self.known_install_size,
            "unknownInstallSize": self.unknown_install_size,
            "changed": self.changed,
            "failed": self.failed,
        }


def backfill_sizes(
    database: Database,
    *,
    inspector: ZipRangeInspector | None = None,
    dry_run: bool = False,
) -> SizeBackfillResult:
    inspector = inspector or ZipRangeInspector(HTTPRangeFetcher())
    result = SizeBackfillResult()

    for target in database.map_size_targets():
        version_id = target["id"]
        source_url = target.get("source_url")
        if not source_url:
            LOGGER.warning("map version %s has no source URL", version_id)
            result = _increment(result, processed=1, failed=1)
            continue

        try:
            measurement = inspector.inspect(
                source_url,
                expected_payload_path=target.get("install_payload_path") or "gmapsupp.img",
            )
        except ZipRangeError as exc:
            LOGGER.warning("size backfill failed for map version %s: %s", version_id, exc)
            if not dry_run:
                # Preserve all known size values. The warning is operational
                # state, not a replacement for a failed measurement.
                database.update_map_size_metadata(
                    version_id=version_id,
                    download_size_bytes=None,
                    install_size_bytes=None,
                    install_payload_path=None,
                    measurement_method="zip-range-error",
                    warning=str(exc),
                )
            result = _increment(result, processed=1, failed=1)
            continue

        changed = False
        if not dry_run:
            changed = database.update_map_size_metadata(
                version_id=version_id,
                download_size_bytes=measurement.download_size_bytes,
                install_size_bytes=measurement.install_size_bytes,
                install_payload_path=measurement.payload_path,
                measurement_method=measurement.method,
                warning=measurement.warning,
            )
        result = _increment(
            result,
            processed=1,
            measured=1,
            known_install_size=1 if measurement.install_size_bytes is not None else 0,
            unknown_install_size=1 if measurement.install_size_bytes is None else 0,
            changed=1 if changed else 0,
        )

    return result


def _increment(result: SizeBackfillResult, **changes: int) -> SizeBackfillResult:
    values = {
        "processed": result.processed,
        "measured": result.measured,
        "known_install_size": result.known_install_size,
        "unknown_install_size": result.unknown_install_size,
        "changed": result.changed,
        "failed": result.failed,
    }
    for key, value in changes.items():
        values[key] += value
    return SizeBackfillResult(**values)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Measure Freizeitkarte ZIP and Garmin IMG sizes using HTTP Range"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="measure provider metadata without writing PostgreSQL",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = Settings.from_env()
    result = backfill_sizes(
        Database(
            settings.database_url,
            connect_timeout_seconds=settings.database_connect_timeout_seconds,
        ),
        dry_run=args.dry_run,
    )
    print(json.dumps(result.as_dict(), sort_keys=True))


if __name__ == "__main__":
    main()
