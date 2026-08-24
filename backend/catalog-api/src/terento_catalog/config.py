from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    database_url: str
    asset_root: Path = Path("/var/lib/terento/assets")
    host: str = "0.0.0.0"
    port: int = 8000
    database_connect_timeout_seconds: int = 5
    collector_schedule_utc: str = "MON 03:00"
    compatibility_admin_username: str | None = None
    compatibility_admin_password: str | None = None

    @classmethod
    def from_env(cls) -> "Settings":
        database_url = os.environ.get("DATABASE_URL", "").strip()
        if not database_url:
            raise RuntimeError("DATABASE_URL is required")

        return cls(
            database_url=database_url,
            asset_root=Path(
                os.environ.get("TERENTO_ASSET_ROOT", "/var/lib/terento/assets")
            ),
            host=os.environ.get("CATALOG_HOST", "0.0.0.0"),
            port=_positive_int("CATALOG_PORT", 8000),
            database_connect_timeout_seconds=_positive_int(
                "CATALOG_DB_CONNECT_TIMEOUT_SECONDS", 5
            ),
            collector_schedule_utc=os.environ.get(
                "COLLECTOR_SCHEDULE_UTC", "MON 03:00"
            ),
            compatibility_admin_username=os.environ.get("COMPATIBILITY_ADMIN_USERNAME") or None,
            compatibility_admin_password=os.environ.get("COMPATIBILITY_ADMIN_PASSWORD") or None,
        )


def _positive_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
    if parsed <= 0:
        raise RuntimeError(f"{name} must be greater than zero")
    return parsed
