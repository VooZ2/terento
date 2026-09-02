from __future__ import annotations

import logging

from .config import Settings
from .db import Database
from .http_api import CatalogService, serve
from .asset_storage import AssetStorage


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = Settings.from_env()
    serve(
        CatalogService(
            Database(
                settings.database_url,
                connect_timeout_seconds=settings.database_connect_timeout_seconds,
            ),
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
