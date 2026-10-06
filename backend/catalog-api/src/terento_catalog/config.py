from __future__ import annotations

import ipaddress
import os
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

# The production API binds only to the private Docker network and Traefik
# terminates HTTPS, so the direct peer is the proxy. X-Forwarded-For is honoured
# only when the direct peer is inside these networks (loopback and private
# ranges); a public peer's forwarded header is ignored.
DEFAULT_TRUSTED_PROXIES = (
    "127.0.0.0/8", "::1/128", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "fc00::/7",
)


@dataclass(frozen=True)
class Settings:
    database_url: str
    asset_root: Path = Path("/var/lib/terento/assets")
    host: str = "0.0.0.0"
    port: int = 8000
    database_connect_timeout_seconds: int = 5
    collector_schedule_utc: str = "03:00"
    admin_bootstrap_secret: str | None = None
    admin_session_ttl_seconds: int = 28_800
    public_compatibility_stats_enabled: bool = False
    operations_ingest_secret: str | None = None
    opentopomap_contour_mode: str = "off"
    opentopomap_contour_allowlist: tuple[str, ...] = ()
    trusted_proxies: tuple[str, ...] = DEFAULT_TRUSTED_PROXIES
    map_preview_enabled: bool = False
    map_preview_work_dir: Path = Path("/var/lib/terento/preview-work")
    map_preview_window_utc: str = "00:00-06:00"
    map_preview_refresh_days: int = 90
    map_preview_publish_minutes: int = 30
    map_preview_render_jobs: int = 1
    map_preview_max_total_bytes: int = 55 * 1000**3
    map_preview_max_source_bytes: int = 5 * 1024**3
    map_preview_min_free_bytes: int = 20 * 1000**3
    map_preview_renderer: Path = Path("/usr/local/bin/terento-preview-render")
    public_base_url: str = "https://api.terento.app"

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
                "COLLECTOR_SCHEDULE_UTC", "03:00"
            ),
            admin_bootstrap_secret=os.environ.get("ADMIN_BOOTSTRAP_SECRET") or None,
            admin_session_ttl_seconds=_positive_int("ADMIN_SESSION_TTL_SECONDS", 28_800),
            public_compatibility_stats_enabled=_boolean("PUBLIC_COMPATIBILITY_STATS_ENABLED", False),
            operations_ingest_secret=_optional_secret("OPERATIONS_INGEST_SECRET"),
            opentopomap_contour_mode=_contour_mode(),
            opentopomap_contour_allowlist=_csv("OPENTOPO_MAP_CONTOUR_ALLOWLIST"),
            map_preview_enabled=_boolean("MAP_PREVIEW_ENABLED", False),
            map_preview_work_dir=Path(
                os.environ.get("TERENTO_PREVIEW_WORK_DIR", "/var/lib/terento/preview-work")
            ),
            map_preview_window_utc=_preview_window(),
            map_preview_refresh_days=_positive_int("MAP_PREVIEW_REFRESH_DAYS", 90),
            map_preview_publish_minutes=_positive_int("MAP_PREVIEW_PUBLISH_MINUTES", 30),
            map_preview_render_jobs=min(_positive_int("MAP_PREVIEW_RENDER_JOBS", 1), 16),
            map_preview_max_total_bytes=_positive_int("MAP_PREVIEW_MAX_TOTAL_BYTES", 55 * 1000**3),
            map_preview_max_source_bytes=_positive_int("MAP_PREVIEW_MAX_SOURCE_BYTES", 5 * 1024**3),
            map_preview_min_free_bytes=_positive_int("MAP_PREVIEW_MIN_FREE_BYTES", 20 * 1000**3),
            map_preview_renderer=Path(
                os.environ.get("TERENTO_PREVIEW_RENDERER", "/usr/local/bin/terento-preview-render")
            ),
            public_base_url=_public_base_url(),
            trusted_proxies=_trusted_proxies(),
        )

    def map_preview_settings(self):
        from .map_preview.job import PreviewSettings, parse_window

        return PreviewSettings(
            enabled=self.map_preview_enabled,
            asset_root=self.asset_root,
            work_dir=self.map_preview_work_dir,
            window_utc=parse_window(self.map_preview_window_utc),
            refresh_days=self.map_preview_refresh_days,
            publish_interval=timedelta(minutes=self.map_preview_publish_minutes),
            render_jobs=self.map_preview_render_jobs,
            max_total_bytes=self.map_preview_max_total_bytes,
            max_source_bytes=self.map_preview_max_source_bytes,
            min_free_bytes=self.map_preview_min_free_bytes,
            renderer=self.map_preview_renderer,
            public_base_url=self.public_base_url,
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


def _contour_mode() -> str:
    value = os.environ.get("OPENTOPO_MAP_CONTOUR_MODE", "off").strip().lower()
    if value not in {"off", "shadow", "allowlist", "public"}:
        raise RuntimeError(
            "OPENTOPO_MAP_CONTOUR_MODE must be off, shadow, allowlist, or public"
        )
    return value


def _csv(name: str) -> tuple[str, ...]:
    return tuple(
        item.strip()
        for item in os.environ.get(name, "").split(",")
        if item.strip()
    )


def _trusted_proxies() -> tuple[str, ...]:
    """Return proxy networks whose X-Forwarded-For header is trusted.

    ``CATALOG_TRUSTED_PROXIES`` is a comma-separated list of IP addresses or
    CIDR networks; ``none`` disables forwarded-header trust entirely.
    """
    raw = os.environ.get("CATALOG_TRUSTED_PROXIES")
    if raw is None:
        return DEFAULT_TRUSTED_PROXIES
    if raw.strip().lower() == "none":
        return ()
    networks = []
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            networks.append(str(ipaddress.ip_network(item, strict=False)))
        except ValueError as exc:
            raise RuntimeError("CATALOG_TRUSTED_PROXIES must contain IP addresses or CIDR networks") from exc
    return tuple(networks)


def _preview_window() -> str:
    value = os.environ.get("MAP_PREVIEW_WINDOW_UTC", "00:00-06:00").strip()
    from .map_preview.job import parse_window

    parse_window(value)
    return value


def _public_base_url() -> str:
    value = os.environ.get("TERENTO_PUBLIC_API_URL", "https://api.terento.app").strip().rstrip("/")
    if not value.startswith("https://"):
        raise RuntimeError("TERENTO_PUBLIC_API_URL must use https")
    return value
