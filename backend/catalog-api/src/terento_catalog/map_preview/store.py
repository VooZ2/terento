"""Database bookkeeping for map style previews (migration 073)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

LAYER_STATUSES = {"AVAILABLE", "NOT_COVERED", "PENDING", "FAILED"}


class PreviewDatabase:
    def __init__(self, database: Any) -> None:
        self.database = database

    # Lease -----------------------------------------------------------------
    def acquire_lease(self, owner: str, seconds: int) -> bool:
        """Take or renew the renderer lease.

        Live renderers renew a short lease, so a lease reaching further ahead
        than one renewal period was left by a renderer that held it for a
        whole window and is taken over.
        """
        with self.database.connection() as c:
            row = c.execute(
                """UPDATE map_preview_lease SET owner=%s, lease_until=now() + make_interval(secs => %s)
                   WHERE id=1 AND (lease_until < now() OR owner=%s
                                   OR lease_until > now() + make_interval(secs => %s))
                   RETURNING id""",
                (owner, seconds, owner, seconds + 60),
            ).fetchone()
        return bool(row)

    def release_lease(self, owner: str) -> None:
        with self.database.connection() as c:
            c.execute("UPDATE map_preview_lease SET owner=NULL, lease_until='epoch' WHERE id=1 AND owner=%s", (owner,))

    # Providers ---------------------------------------------------------------
    def enabled_providers(self) -> set[str]:
        with self.database.connection() as c:
            rows = c.execute(
                "SELECT id FROM map_provider WHERE preview_enabled AND status='ACTIVE'"
            ).fetchall()
        return {row["id"] for row in rows}

    def provider_preview_states(self) -> dict[str, bool]:
        with self.database.connection() as c:
            rows = c.execute("SELECT id, preview_enabled FROM map_provider").fetchall()
        return {row["id"]: bool(row["preview_enabled"]) for row in rows}

    def set_preview_enabled(self, provider_id: str, enabled: bool, admin_user_id: int, request_id: str | None) -> dict:
        if type(enabled) is not bool:
            raise ValueError("invalid_preview_control")
        with self.database.connection() as c:
            row = c.execute(
                "UPDATE map_provider SET preview_enabled=%s, updated_at=now() WHERE id=%s AND status <> 'RETIRED' RETURNING id",
                (enabled, provider_id),
            ).fetchone()
            if not row:
                raise LookupError("provider_not_found")
            self.database._insert_admin_audit(
                c, admin_user_id=admin_user_id,
                action="provider.previews_enabled" if enabled else "provider.previews_disabled",
                provider_id=provider_id, request_id=request_id, details={"enabled": enabled},
            )
        return {"previewEnabled": enabled}

    # Layers ------------------------------------------------------------------
    def layers(self) -> dict[tuple[str, str], dict[str, Any]]:
        with self.database.connection() as c:
            rows = c.execute("SELECT * FROM map_preview_layer").fetchall()
        return {(row["area_id"], row["style_id"]): dict(row) for row in rows}

    def provider_layers(self, provider_id: str) -> list[dict[str, Any]]:
        with self.database.connection() as c:
            rows = c.execute(
                "SELECT * FROM map_preview_layer WHERE provider_id=%s ORDER BY area_id, style_id",
                (provider_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def save_layer(
        self,
        area_id: str,
        style_id: str,
        provider_id: str,
        status: str,
        *,
        package_id: str | None = None,
        package_version: str | None = None,
        tile_count: int | None = None,
        bytes_: int | None = None,
        rendered_at: datetime | None = None,
        retry_after: timedelta | None = None,
        retry_not_before: datetime | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
        keep_rendered: bool = False,
    ) -> None:
        if status not in LAYER_STATUSES:
            raise ValueError("invalid_preview_layer_status")
        if retry_not_before is None and retry_after is not None:
            retry_not_before = datetime.now(timezone.utc) + retry_after
        with self.database.connection() as c:
            if keep_rendered:
                # A failed refresh keeps the published tiles and their facts.
                c.execute(
                    """INSERT INTO map_preview_layer (area_id, style_id, provider_id, status, attempted_at,
                           retry_not_before, error_code, error_message)
                       VALUES (%s,%s,%s,%s,now(),%s,%s,%s)
                       ON CONFLICT (area_id, style_id) DO UPDATE SET attempted_at=now(),
                           retry_not_before=EXCLUDED.retry_not_before, error_code=EXCLUDED.error_code,
                           error_message=EXCLUDED.error_message""",
                    (area_id, style_id, provider_id, status, retry_not_before, error_code, (error_message or "")[:500] or None),
                )
                return
            c.execute(
                """INSERT INTO map_preview_layer (area_id, style_id, provider_id, status, package_id, package_version,
                       tile_count, bytes, rendered_at, attempted_at, retry_not_before, error_code, error_message)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,now(),%s,%s,%s)
                   ON CONFLICT (area_id, style_id) DO UPDATE SET provider_id=EXCLUDED.provider_id,
                       status=EXCLUDED.status, package_id=EXCLUDED.package_id,
                       package_version=EXCLUDED.package_version, tile_count=EXCLUDED.tile_count,
                       bytes=EXCLUDED.bytes, rendered_at=EXCLUDED.rendered_at, attempted_at=now(),
                       retry_not_before=EXCLUDED.retry_not_before, error_code=EXCLUDED.error_code,
                       error_message=EXCLUDED.error_message,
                       release=CASE WHEN EXCLUDED.status='AVAILABLE' THEN map_preview_layer.release ELSE NULL END""",
                (area_id, style_id, provider_id, status, package_id, package_version, tile_count, bytes_,
                 rendered_at, retry_not_before, error_code, (error_message or "")[:500] or None),
            )

    def mark_released(self, release: str, layers: list[tuple[str, str]], layer_count: int, total_bytes: int) -> None:
        with self.database.connection() as c:
            for area_id, style_id in layers:
                c.execute(
                    "UPDATE map_preview_layer SET release=%s WHERE area_id=%s AND style_id=%s AND status='AVAILABLE'",
                    (release, area_id, style_id),
                )
            c.execute(
                """INSERT INTO map_preview_release (id, layer_count, bytes) VALUES (%s,%s,%s)
                   ON CONFLICT (id) DO NOTHING""",
                (release, layer_count, total_bytes),
            )

    # Bounds and scores ---------------------------------------------------------
    def package_bounds(self) -> dict[tuple[str, str], tuple[float, float, float, float]]:
        with self.database.connection() as c:
            rows = c.execute("SELECT * FROM map_preview_package_bounds").fetchall()
        return {
            (row["package_id"], row["package_version"]): (row["west"], row["south"], row["east"], row["north"])
            for row in rows
        }

    def save_bounds(self, package_id: str, package_version: str, bounds: tuple[float, float, float, float]) -> None:
        west, south, east, north = bounds
        with self.database.connection() as c:
            c.execute(
                """INSERT INTO map_preview_package_bounds (package_id, package_version, west, south, east, north)
                   VALUES (%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (package_id, package_version) DO UPDATE SET west=EXCLUDED.west,
                       south=EXCLUDED.south, east=EXCLUDED.east, north=EXCLUDED.north, inspected_at=now()""",
                (package_id, package_version, west, south, east, north),
            )

    def scores(self) -> dict[str, float | None]:
        with self.database.connection() as c:
            rows = c.execute("SELECT area_id, diff_score FROM map_preview_area_score").fetchall()
        return {row["area_id"]: row["diff_score"] for row in rows}

    def save_score(self, area_id: str, score: float | None) -> None:
        with self.database.connection() as c:
            c.execute(
                """INSERT INTO map_preview_area_score (area_id, diff_score) VALUES (%s,%s)
                   ON CONFLICT (area_id) DO UPDATE SET diff_score=EXCLUDED.diff_score, computed_at=now()""",
                (area_id, None if score is None else max(0.0, min(1.0, float(score)))),
            )
