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
    admin_bootstrap_secret: str | None = None
    admin_session_ttl_seconds: int = 28_800
    public_compatibility_stats_enabled: bool = False
    operations_ingest_secret: str | None = None

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
            admin_bootstrap_secret=os.environ.get("ADMIN_BOOTSTRAP_SECRET") or None,
            admin_session_ttl_seconds=_positive_int("ADMIN_SESSION_TTL_SECONDS", 28_800),
            public_compatibility_stats_enabled=_boolean("PUBLIC_COMPATIBILITY_STATS_ENABLED", False),
            operations_ingest_secret=_optional_secret("OPERATIONS_INGEST_SECRET"),
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


def _boolean(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise RuntimeError(f"{name} must be a boolean")


def _optional_secret(name: str) -> str | None:
    value = os.environ.get(name, "").strip()
    if not value:
        return None
    if len(value) < 32 or len(value) > 512:
        raise RuntimeError(f"{name} must contain 32–512 characters")
    return value
