from __future__ import annotations

import argparse
import json
import logging

from .collectors import FreizeitkarteCollector
from .config import Settings
from .db import Database
from .provider_catalog import (
    KNOWN_PROVIDER_DEFINITIONS,
    OpenTopoMapProviderAdapter,
    ProviderAdapter,
    ProviderCollectionError,
    snapshot_from_freizeitkarte_records,
)

LOGGER = logging.getLogger(__name__)


def collect_once(database: Database, *, dry_run: bool = False) -> int:
    run_id = None if dry_run else database.begin_catalog_collection("freizeitkarte")
    try:
        records = FreizeitkarteCollector().collect()
        if not records:
            raise RuntimeError("Freizeitkarte collector returned no records")
        if not dry_run:
            database.upsert_collected_maps(records)
            # Keep the legacy tables populated for existing maintenance commands,
            # while the public API reads the provider-neutral snapshot.
            snapshot = snapshot_from_freizeitkarte_records(records)
            database.upsert_provider_snapshot(snapshot)
            database.finish_catalog_collection(
                int(run_id),
                status="SUCCEEDED",
                package_count=len(snapshot.packages),
                artifact_count=sum(len(item.artifacts) for item in snapshot.packages),
            )
    except Exception as exc:
        if run_id is not None:
            database.finish_catalog_collection(
                int(run_id),
                status="FAILED",
                error_code=type(exc).__name__,
                error_detail=str(exc)[:500],
            )
        raise

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


def collect_provider_once(
    database: Database, adapter: ProviderAdapter, *, dry_run: bool = False
) -> dict[str, int | str]:
    """Collect one known provider and persist one auditable collection run."""

    provider_id = adapter.definition.id
    run_id = None if dry_run else database.begin_catalog_collection(provider_id)
    try:
        snapshot = adapter.collect()
        if not snapshot.packages:
            raise ProviderCollectionError("provider returned no packages")
        if not dry_run:
            database.upsert_provider_snapshot(snapshot)
            database.finish_catalog_collection(
                int(run_id),
                status="SUCCEEDED",
                package_count=len(snapshot.packages),
                artifact_count=sum(len(item.artifacts) for item in snapshot.packages),
            )
        return {
            "provider": provider_id,
            "runId": int(run_id) if run_id is not None else 0,
            "packages": len(snapshot.packages),
            "artifacts": sum(len(item.artifacts) for item in snapshot.packages),
        }
    except Exception as exc:
        if run_id is not None:
            database.finish_catalog_collection(
                int(run_id),
                status="FAILED",
                error_code=type(exc).__name__,
                error_detail=str(exc)[:500],
            )
        raise


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Collect one reviewed map provider's Garmin metadata"
    )
    parser.add_argument(
        "--provider",
        choices=tuple(sorted(KNOWN_PROVIDER_DEFINITIONS)),
        default="freizeitkarte",
        help="reviewed provider adapter to collect (default: freizeitkarte)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="fetch and validate provider metadata without writing PostgreSQL",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = Settings.from_env()
    database = Database(
        settings.database_url,
        connect_timeout_seconds=settings.database_connect_timeout_seconds,
    )
    if args.provider == "freizeitkarte":
        count = collect_once(database, dry_run=args.dry_run)
        result: dict[str, int | str] = {
            "provider": "freizeitkarte",
            "packages": count,
        }
    else:
        result = collect_provider_once(
            database,
            OpenTopoMapProviderAdapter(),
            dry_run=args.dry_run,
        )
    print(json.dumps(result))


if __name__ == "__main__":
    main()
