from __future__ import annotations

import logging
from threading import Event, Thread

from .config import Settings
from .db import Database
from .http_api import CatalogService, serve
from .asset_storage import AssetStorage
from .github_issue_sync import run_sync


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = Settings.from_env()
    database = Database(settings.database_url, connect_timeout_seconds=settings.database_connect_timeout_seconds)
    stop = Event()
    worker = Thread(target=run_sync, args=(database, stop), daemon=True, name="github-issue-sync")
    worker.start()
    try:
        run_server(settings, database)
    finally:
        stop.set()
        worker.join(timeout=12)


def run_server(settings: Settings, database: Database) -> None:
    serve(
        CatalogService(
            database,
            asset_storage=AssetStorage(settings.asset_root),
            admin_bootstrap_secret=settings.admin_bootstrap_secret,
            admin_session_ttl_seconds=settings.admin_session_ttl_seconds,
            public_compatibility_stats_enabled=settings.public_compatibility_stats_enabled,
            operations_ingest_secret=settings.operations_ingest_secret,
        ),
        settings.host,
        settings.port,
    )


if __name__ == "__main__":
    main()
