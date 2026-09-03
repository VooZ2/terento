from __future__ import annotations

import argparse
import hashlib
import json
import logging
from typing import Iterable

from .collectors import FreizeitkarteCollector
from .config import Settings
from .db import Database
from .provider_catalog import (
    ProviderAdapter,
    ProviderCollectionError,
    ProviderSnapshot,
    FreizeitkarteProviderAdapter,
    OpenTopoMapProviderAdapter,
    snapshot_from_freizeitkarte_records,
)

LOGGER = logging.getLogger(__name__)


def official_provider_adapters() -> tuple[ProviderAdapter, ...]:
    """Return every reviewed provider that the current release supports."""

    return (FreizeitkarteProviderAdapter(), OpenTopoMapProviderAdapter())


def snapshot_release_evidence(snapshot: ProviderSnapshot) -> tuple[str, str]:
    """Return a display release and deterministic metadata-only fingerprint."""

    packages = sorted(snapshot.packages, key=lambda item: item.id)
    dated = [
        (item.source_updated_at or item.generated_at, item.release)
        for item in packages
        if item.source_updated_at is not None or item.generated_at is not None
    ]
    latest_release = max(dated, key=lambda item: item[0])[1] if dated else max(
        (item.release for item in packages), default="unknown"
    )
    evidence = [
        {
            "id": package.id,
            "release": package.release,
            "releaseId": package.release_id,
            "version": package.version_label,
            "sourceUpdatedAt": (
                package.source_updated_at or package.generated_at
            ).isoformat() if package.source_updated_at or package.generated_at else None,
            "artifacts": [
                {
                    "id": artifact.id,
                    "sourceUpdatedAt": artifact.source_updated_at.isoformat()
                    if artifact.source_updated_at else None,
                }
                for artifact in sorted(package.artifacts, key=lambda item: item.id)
            ],
        }
        for package in packages
    ]
    fingerprint = hashlib.sha256(
        json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return latest_release, fingerprint


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
            latest_release, fingerprint = snapshot_release_evidence(snapshot)
            database.finish_catalog_collection(
                int(run_id),
                status="SUCCEEDED",
                package_count=len(snapshot.packages),
                artifact_count=sum(len(item.artifacts) for item in snapshot.packages),
                latest_release=latest_release,
                catalog_fingerprint=fingerprint,
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
            latest_release, fingerprint = snapshot_release_evidence(snapshot)
            database.finish_catalog_collection(
                int(run_id),
                status="SUCCEEDED",
                package_count=len(snapshot.packages),
                artifact_count=sum(len(item.artifacts) for item in snapshot.packages),
                latest_release=latest_release,
                catalog_fingerprint=fingerprint,
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


def collect_all_providers(
    database: Database,
    adapters: Iterable[ProviderAdapter] | None = None,
) -> dict[str, dict[str, int | str]]:
    """Collect each official provider independently and retain every outcome."""

    outcomes: dict[str, dict[str, int | str]] = {}
    for adapter in adapters or official_provider_adapters():
        provider_id = adapter.definition.id
        try:
            database.ensure_provider_definition(adapter.definition)
            outcomes[provider_id] = {
                "status": "SUCCEEDED",
                **collect_provider_once(database, adapter),
            }
        except Exception as exc:
            LOGGER.exception("scheduled %s catalog collection failed", provider_id)
            outcomes[provider_id] = {
                "status": "FAILED",
                "provider": provider_id,
                "error": type(exc).__name__,
                "detail": str(exc)[:500],
            }
    return outcomes


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
