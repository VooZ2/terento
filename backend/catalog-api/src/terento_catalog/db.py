from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .models import CollectedDevice, CollectedMap
from .asset_attribution import normalize_asset_source


class Database:
    def __init__(self, dsn: str, connect_timeout_seconds: int = 5) -> None:
        self.dsn = dsn
        self.connect_timeout_seconds = connect_timeout_seconds

    @contextmanager
    def connection(self) -> Iterator[Any]:
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:  # pragma: no cover - exercised in deployment
            raise RuntimeError(
                "psycopg is required for database operations; install project dependencies"
            ) from exc

        with psycopg.connect(
            self.dsn,
            connect_timeout=self.connect_timeout_seconds,
            row_factory=dict_row,
        ) as connection:
            yield connection

    def health(self) -> bool:
        with self.connection() as connection:
            connection.execute("SELECT 1")
        return True

    def insert_compatibility_event(self, event: dict[str, Any]) -> bool:
        query = """
            INSERT INTO compatibility_evidence_event (
                event_id, occurred_at, model, family, firmware_version,
                usb_vendor_id, usb_product_id, transport, provider, region,
                map_release, terento_version, macos_version, phase_outcome,
                automatic_finishing_result, error_category, deletion_token_hash
            ) VALUES (
                %(id)s, %(timestamp)s, %(model)s, %(family)s, %(firmwareVersion)s,
                %(usbVendorID)s, %(usbProductID)s, %(transport)s, %(provider)s, %(region)s,
                %(mapRelease)s, %(terentoVersion)s, %(macOSVersion)s, %(phaseOutcome)s,
                %(automaticFinishingResult)s, %(errorCategory)s, %(deletionTokenHash)s
            ) ON CONFLICT (event_id) DO NOTHING
            RETURNING event_id
        """
        values = {
            **event,
            # Swift Codable omits nil optional fields. PostgreSQL still needs
            # explicit NULL parameters for the named placeholders below.
            "family": event.get("family"),
            "firmwareVersion": event.get("firmwareVersion"),
            "errorCategory": event.get("errorCategory"),
            "deletionTokenHash": self._token_hash(event.get("deletionToken")),
        }
        with self.connection() as connection:
            inserted = connection.execute(query, values).fetchone() is not None
        return inserted

    def delete_compatibility_event(self, event_id: str, deletion_token: str) -> bool:
        query = """
            DELETE FROM compatibility_evidence_event
            WHERE event_id = %s AND deletion_token_hash = %s
            RETURNING event_id
        """
        with self.connection() as connection:
            row = connection.execute(
                query,
                (event_id, self._token_hash(deletion_token)),
            ).fetchone()
        return row is not None

    def prune_compatibility_events(self) -> int:
        with self.connection() as connection:
            result = connection.execute(
                "DELETE FROM compatibility_evidence_event WHERE received_at < now() - interval '24 months'"
            )
        return int(result.rowcount)

    @staticmethod
    def _token_hash(token: str | None) -> str | None:
        if not token:
            return None
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def compatibility_statistics(self) -> list[dict[str, Any]]:
        query = "SELECT * FROM compatibility_model_statistics ORDER BY model"
        with self.connection() as connection:
            return list(connection.execute(query).fetchall())

    def public_compatibility_statistics(self, limit: int) -> list[dict[str, Any]]:
        query = """
            SELECT public_display_name AS model,
                   attempted_install_count,
                   successful_install_count,
                   failed_install_count,
                   success_rate,
                   calculated_status,
                   last_success
            FROM compatibility_model_statistics
            WHERE public_statistics_enabled = true
              AND review_status = 'APPROVED'
            ORDER BY successful_install_count DESC, attempted_install_count DESC, public_display_name
            LIMIT %s
        """
        with self.connection() as connection:
            return list(connection.execute(query, (limit,)).fetchall())

    def admin_user_count(self) -> int:
        with self.connection() as connection:
            row = connection.execute("SELECT count(*) AS count FROM admin_user").fetchone()
        return int(row["count"])

    def create_admin_user(self, username: str, password_hash: str) -> dict[str, Any]:
        query = """
            INSERT INTO admin_user (username, password_hash)
            VALUES (%s, %s)
            RETURNING id, username, password_hash, created_at, last_login_at
        """
        with self.connection() as connection:
            return dict(connection.execute(query, (username, password_hash)).fetchone())

    def admin_user_by_username(self, username: str) -> dict[str, Any] | None:
        query = "SELECT id, username, password_hash, created_at, last_login_at FROM admin_user WHERE username = %s"
        with self.connection() as connection:
            row = connection.execute(query, (username,)).fetchone()
        return dict(row) if row else None

    def create_admin_session(
        self, user_id: int, session_hash: str, csrf_hash: str, expires_at: datetime
    ) -> None:
        with self.connection() as connection:
            connection.execute("DELETE FROM admin_session WHERE expires_at <= now()")
            connection.execute(
                "INSERT INTO admin_session (token_hash, admin_user_id, csrf_token_hash, expires_at) VALUES (%s, %s, %s, %s)",
                (session_hash, user_id, csrf_hash, expires_at),
            )
            connection.execute("UPDATE admin_user SET last_login_at = now() WHERE id = %s", (user_id,))

    def admin_session(self, session_hash: str) -> dict[str, Any] | None:
        query = """
            SELECT u.id, u.username, u.password_hash, u.created_at, u.last_login_at,
                   s.csrf_token_hash, s.expires_at
            FROM admin_session s JOIN admin_user u ON u.id = s.admin_user_id
            WHERE s.token_hash = %s AND s.expires_at > now()
        """
        with self.connection() as connection:
            row = connection.execute(query, (session_hash,)).fetchone()
        return dict(row) if row else None

    def delete_admin_session(self, session_hash: str) -> None:
        with self.connection() as connection:
            connection.execute("DELETE FROM admin_session WHERE token_hash = %s", (session_hash,))

    def update_admin_user(self, user_id: int, username: str, password_hash: str) -> dict[str, Any]:
        query = """
            UPDATE admin_user SET username = %s, password_hash = %s, updated_at = now()
            WHERE id = %s
            RETURNING id, username, password_hash, created_at, last_login_at
        """
        with self.connection() as connection:
            row = connection.execute(query, (username, password_hash, user_id)).fetchone()
        return dict(row)

    def catalog_snapshot(self) -> tuple[list[dict[str, Any]], datetime]:
        query = """
            SELECT
                p.id AS provider_id,
                p.name AS provider_name,
                p.website AS provider_website,
                p.license_information AS provider_license_information,
                p.attribution AS provider_attribution,
                p.license_url AS provider_license_url,
                m.id AS map_id,
                m.name AS map_name,
                m.region,
                m.country,
                m.identifier,
                m.managed_by_terento,
                v.version_year,
                v.version_month,
                v.raw_version,
                v.file_size_bytes,
                v.download_size_bytes,
                v.install_size_bytes,
                v.install_payload_path,
                v.size_measurement_method,
                v.size_measured_at,
                v.size_measurement_warning,
                v.source_url,
                v.release_date,
                v.checksum_sha256,
                v.updated_at AS version_updated_at
            FROM map_provider AS p
            LEFT JOIN map AS m ON m.provider_id = p.id
            LEFT JOIN LATERAL (
                SELECT mv.*
                FROM map_version AS mv
                WHERE mv.map_id = m.id
                ORDER BY mv.version_year DESC, mv.version_month DESC, mv.updated_at DESC
                LIMIT 1
            ) AS v ON TRUE
            ORDER BY p.id, m.id
        """
        updated_at_query = """
            SELECT COALESCE(MAX(changed_at), TIMESTAMPTZ 'epoch') AS updated_at
            FROM (
                SELECT updated_at AS changed_at FROM map_provider
                UNION ALL
                SELECT updated_at AS changed_at FROM map
                UNION ALL
                SELECT updated_at AS changed_at FROM map_version
            ) AS changes
        """
        with self.connection() as connection:
            rows = list(connection.execute(query).fetchall())
            updated_row = connection.execute(updated_at_query).fetchone()

        updated_at = updated_row["updated_at"]
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=timezone.utc)
        return rows, updated_at

    def upsert_collected_maps(self, records: list[CollectedMap]) -> None:
        if not records:
            raise ValueError("collector returned no records")

        provider_query = """
            INSERT INTO map_provider (
                id, name, website, license_information, attribution, license_url
            ) VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                name = EXCLUDED.name,
                website = EXCLUDED.website,
                license_information = EXCLUDED.license_information,
                attribution = EXCLUDED.attribution,
                license_url = EXCLUDED.license_url,
                updated_at = CASE
                    WHEN (
                        map_provider.name,
                        map_provider.website,
                        map_provider.license_information,
                        map_provider.attribution,
                        map_provider.license_url
                    ) IS DISTINCT FROM (
                        EXCLUDED.name,
                        EXCLUDED.website,
                        EXCLUDED.license_information,
                        EXCLUDED.attribution,
                        EXCLUDED.license_url
                    ) THEN now()
                    ELSE map_provider.updated_at
                END
        """
        map_query = """
            INSERT INTO map (
                id, provider_id, name, region, country, identifier, managed_by_terento
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                provider_id = EXCLUDED.provider_id,
                name = EXCLUDED.name,
                region = EXCLUDED.region,
                country = EXCLUDED.country,
                identifier = EXCLUDED.identifier,
                managed_by_terento = EXCLUDED.managed_by_terento,
                updated_at = CASE
                    WHEN (
                        map.provider_id,
                        map.name,
                        map.region,
                        map.country,
                        map.identifier,
                        map.managed_by_terento
                    ) IS DISTINCT FROM (
                        EXCLUDED.provider_id,
                        EXCLUDED.name,
                        EXCLUDED.region,
                        EXCLUDED.country,
                        EXCLUDED.identifier,
                        EXCLUDED.managed_by_terento
                    ) THEN now()
                    ELSE map.updated_at
                END
        """
        version_query = """
            INSERT INTO map_version (
                map_id, version_year, version_month, raw_version,
                file_size_bytes, download_size_bytes, install_size_bytes,
                install_payload_path, size_measurement_method, size_measured_at,
                size_measurement_warning, source_url, release_date, checksum_sha256,
                detected_at, updated_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now(), now()
            )
            ON CONFLICT (map_id, version_year, version_month) DO UPDATE SET
                raw_version = EXCLUDED.raw_version,
                file_size_bytes = COALESCE(EXCLUDED.file_size_bytes, map_version.file_size_bytes),
                download_size_bytes = COALESCE(
                    EXCLUDED.download_size_bytes,
                    EXCLUDED.file_size_bytes,
                    map_version.download_size_bytes,
                    map_version.file_size_bytes
                ),
                install_size_bytes = COALESCE(
                    EXCLUDED.install_size_bytes,
                    map_version.install_size_bytes
                ),
                install_payload_path = CASE
                    WHEN EXCLUDED.install_size_bytes IS NOT NULL
                    THEN EXCLUDED.install_payload_path
                    ELSE map_version.install_payload_path
                END,
                size_measurement_method = COALESCE(
                    EXCLUDED.size_measurement_method,
                    map_version.size_measurement_method
                ),
                size_measured_at = COALESCE(
                    EXCLUDED.size_measured_at,
                    map_version.size_measured_at
                ),
                size_measurement_warning = EXCLUDED.size_measurement_warning,
                source_url = EXCLUDED.source_url,
                release_date = EXCLUDED.release_date,
                checksum_sha256 = EXCLUDED.checksum_sha256,
                detected_at = now(),
                updated_at = CASE
                    WHEN (
                        map_version.raw_version,
                        map_version.file_size_bytes,
                        map_version.download_size_bytes,
                        map_version.install_size_bytes,
                        map_version.install_payload_path,
                        map_version.source_url,
                        map_version.release_date,
                        map_version.checksum_sha256
                    ) IS DISTINCT FROM (
                        EXCLUDED.raw_version,
                        COALESCE(EXCLUDED.file_size_bytes, map_version.file_size_bytes),
                        COALESCE(
                            EXCLUDED.download_size_bytes,
                            EXCLUDED.file_size_bytes,
                            map_version.download_size_bytes,
                            map_version.file_size_bytes
                        ),
                        COALESCE(EXCLUDED.install_size_bytes, map_version.install_size_bytes),
                        CASE
                            WHEN EXCLUDED.install_size_bytes IS NOT NULL
                            THEN EXCLUDED.install_payload_path
                            ELSE map_version.install_payload_path
                        END,
                        EXCLUDED.source_url,
                        EXCLUDED.release_date,
                        EXCLUDED.checksum_sha256
                    ) THEN now()
                    ELSE map_version.updated_at
                END
        """

        with self.connection() as connection:
            for record in records:
                connection.execute(
                    provider_query,
                    (
                        record.provider.id,
                        record.provider.name,
                        record.provider.website,
                        record.provider.license_information,
                        record.provider.attribution,
                        record.provider.license_url,
                    ),
                )
                connection.execute(
                    map_query,
                    (
                        record.map.id,
                        record.map.provider_id,
                        record.map.name,
                        record.map.region,
                        record.map.country,
                        record.map.identifier,
                        record.map.managed_by_terento,
                    ),
                )
                connection.execute(
                    version_query,
                    (
                        record.map.id,
                        record.version.year,
                        record.version.month,
                        record.raw_version,
                        record.file_size_bytes,
                        record.download_size_bytes,
                        record.install_size_bytes,
                        record.install_payload_path,
                        record.size_measurement_method,
                        record.size_measured_at,
                        record.size_measurement_warning,
                        record.source_url,
                        record.release_date,
                        record.checksum_sha256,
                    ),
                )

    def map_size_targets(self) -> list[dict[str, Any]]:
        query = """
            SELECT
                mv.id,
                mv.map_id,
                mv.version_year,
                mv.version_month,
                mv.source_url,
                mv.file_size_bytes,
                mv.download_size_bytes,
                mv.install_size_bytes,
                mv.install_payload_path
            FROM map_version AS mv
            JOIN map AS m ON m.id = mv.map_id
            JOIN map_provider AS p ON p.id = m.provider_id
            WHERE p.id = 'freizeitkarte'
            ORDER BY mv.map_id, mv.version_year, mv.version_month
        """
        with self.connection() as connection:
            return list(connection.execute(query).fetchall())

    def update_map_size_metadata(
        self,
        *,
        version_id: int,
        download_size_bytes: int | None,
        install_size_bytes: int | None,
        install_payload_path: str | None,
        measurement_method: str | None,
        warning: str | None,
    ) -> bool:
        if download_size_bytes is not None and download_size_bytes < 0:
            raise ValueError("download size cannot be negative")
        if install_size_bytes is not None and install_size_bytes < 0:
            raise ValueError("install size cannot be negative")
        with self.connection() as connection:
            existing = connection.execute(
                """
                SELECT file_size_bytes, download_size_bytes, install_size_bytes,
                       install_payload_path, size_measurement_method
                FROM map_version
                WHERE id = %s
                """,
                (version_id,),
            ).fetchone()
            if existing is None:
                raise ValueError(f"map version does not exist: {version_id}")

            next_download = (
                download_size_bytes
                if download_size_bytes is not None
                else existing["download_size_bytes"] or existing["file_size_bytes"]
            )
            next_install = (
                install_size_bytes
                if install_size_bytes is not None
                else existing["install_size_bytes"]
            )
            next_payload_path = (
                install_payload_path
                if install_size_bytes is not None
                else existing["install_payload_path"]
            )
            next_method = measurement_method or existing["size_measurement_method"]
            changed = (
                existing["file_size_bytes"] != next_download
                or existing["download_size_bytes"] != next_download
                or existing["install_size_bytes"] != next_install
                or existing["install_payload_path"] != next_payload_path
                or existing["size_measurement_method"] != next_method
            )
            connection.execute(
                """
                UPDATE map_version
                SET
                    file_size_bytes = COALESCE(%s, file_size_bytes),
                    download_size_bytes = COALESCE(%s, download_size_bytes, file_size_bytes),
                    install_size_bytes = COALESCE(%s, install_size_bytes),
                    install_payload_path = CASE
                        WHEN %s::bigint IS NOT NULL THEN %s
                        ELSE install_payload_path
                    END,
                    size_measurement_method = COALESCE(%s, size_measurement_method),
                    size_measured_at = CASE
                        WHEN %s::text IS NOT NULL THEN now()
                        ELSE size_measured_at
                    END,
                    size_measurement_warning = %s,
                    updated_at = CASE WHEN %s::boolean THEN now() ELSE updated_at END
                WHERE id = %s
                """,
                (
                    download_size_bytes,
                    download_size_bytes,
                    install_size_bytes,
                    install_size_bytes,
                    install_payload_path,
                    measurement_method,
                    measurement_method,
                    warning,
                    changed,
                    version_id,
                ),
            )
        return changed

    def device_catalog_snapshot(self) -> tuple[list[dict[str, Any]], datetime]:
        query = """
            SELECT
                f.id AS family_id,
                f.manufacturer AS family_manufacturer,
                f.name AS family_name,
                f.canonical_name AS family_canonical_name,
                dm.id AS device_id,
                dm.manufacturer,
                dm.model,
                dm.canonical_model,
                dm.variant,
                dm.case_size_mm,
                dm.display_type,
                dm.part_number,
                dm.product_url,
                dm.source_url,
                dm.source_image_url,
                dm.active,
                dm.first_seen_at,
                dm.last_seen_at,
                asset.asset_type,
                asset.status AS asset_status,
                asset.url AS asset_url,
                asset.sha256 AS asset_sha256,
                asset.width AS asset_width,
                asset.height AS asset_height,
                asset.mime_type AS asset_mime_type,
                asset.asset_version,
                asset.scope AS asset_scope,
                asset.attribution AS asset_attribution,
                asset.source_type AS asset_source_type,
                asset.source_brand AS asset_source_brand,
                asset.attribution_required AS asset_attribution_required,
                asset.storage_key AS asset_storage_key
            FROM device_model AS dm
            JOIN device_family AS f ON f.id = dm.family_id
            LEFT JOIN LATERAL (
                SELECT da.*
                FROM device_asset AS da
                LEFT JOIN device_model AS owner ON owner.id = da.device_model_id
                WHERE da.device_model_id = dm.id
                   OR (da.scope = 'FAMILY' AND owner.family_id = dm.family_id)
                   OR (
                       da.scope IN ('MODEL', 'MODEL_SIZE')
                       AND owner.canonical_model = dm.canonical_model
                       AND (
                           da.scope = 'MODEL'
                           OR owner.case_size_mm IS NOT DISTINCT FROM dm.case_size_mm
                       )
                   )
                   OR (da.scope = 'GENERIC' AND da.device_model_id IS NULL)
                ORDER BY
                    CASE
                        WHEN da.status = 'AVAILABLE' AND da.device_model_id = dm.id
                            AND da.scope = 'EXACT_VARIANT' THEN 0
                        WHEN da.status = 'AVAILABLE' AND da.device_model_id = dm.id
                            AND da.scope = 'MODEL_SIZE' THEN 1
                        WHEN da.status = 'AVAILABLE' AND da.device_model_id = dm.id
                            AND da.scope = 'MODEL' THEN 2
                        WHEN da.status = 'AVAILABLE' AND da.scope = 'FAMILY' THEN 3
                        WHEN da.status = 'AVAILABLE' AND da.scope = 'GENERIC' THEN 4
                        WHEN da.status = 'MISSING' THEN 10
                        ELSE 20
                    END,
                    da.updated_at DESC,
                    da.id DESC
                LIMIT 1
            ) AS asset ON TRUE
            ORDER BY dm.id
        """
        updated_at_query = """
            SELECT COALESCE(MAX(changed_at), TIMESTAMPTZ 'epoch') AS updated_at
            FROM (
                SELECT updated_at AS changed_at FROM device_family
                UNION ALL
                SELECT updated_at AS changed_at FROM device_model
                UNION ALL
                SELECT updated_at AS changed_at FROM device_asset
            ) AS changes
        """
        with self.connection() as connection:
            rows = list(connection.execute(query).fetchall())
            updated_row = connection.execute(updated_at_query).fetchone()

        updated_at = updated_row["updated_at"]
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=timezone.utc)
        return rows, updated_at

    def upsert_collected_devices(
        self,
        records: list[CollectedDevice],
        *,
        collection_complete: bool = True,
    ) -> None:
        if not records:
            raise ValueError("Garmin collector returned no records")

        family_query = """
            INSERT INTO device_family (
                id, manufacturer, name, canonical_name, source_url
            ) VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                manufacturer = EXCLUDED.manufacturer,
                name = EXCLUDED.name,
                canonical_name = EXCLUDED.canonical_name,
                source_url = EXCLUDED.source_url,
                updated_at = CASE
                    WHEN (
                        device_family.manufacturer,
                        device_family.name,
                        device_family.canonical_name,
                        device_family.source_url
                    ) IS DISTINCT FROM (
                        EXCLUDED.manufacturer,
                        EXCLUDED.name,
                        EXCLUDED.canonical_name,
                        EXCLUDED.source_url
                    ) THEN now()
                    ELSE device_family.updated_at
                END
        """
        model_query = """
            INSERT INTO device_model (
                id, family_id, manufacturer, model, canonical_model, variant,
                case_size_mm, display_type, part_number, product_url, source_url,
                source_image_url
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                family_id = EXCLUDED.family_id,
                manufacturer = EXCLUDED.manufacturer,
                model = EXCLUDED.model,
                canonical_model = EXCLUDED.canonical_model,
                variant = EXCLUDED.variant,
                case_size_mm = EXCLUDED.case_size_mm,
                display_type = EXCLUDED.display_type,
                part_number = COALESCE(EXCLUDED.part_number, device_model.part_number),
                product_url = EXCLUDED.product_url,
                source_url = EXCLUDED.source_url,
                source_image_url = EXCLUDED.source_image_url,
                active = TRUE,
                consecutive_missed_collections = 0,
                last_seen_at = now(),
                updated_at = CASE
                    WHEN (
                        device_model.family_id,
                        device_model.manufacturer,
                        device_model.model,
                        device_model.canonical_model,
                        device_model.variant,
                        device_model.case_size_mm,
                        device_model.display_type,
                        device_model.part_number,
                        device_model.product_url,
                        device_model.source_url,
                        device_model.source_image_url
                    ) IS DISTINCT FROM (
                        EXCLUDED.family_id,
                        EXCLUDED.manufacturer,
                        EXCLUDED.model,
                        EXCLUDED.canonical_model,
                        EXCLUDED.variant,
                        EXCLUDED.case_size_mm,
                        EXCLUDED.display_type,
                        COALESCE(EXCLUDED.part_number, device_model.part_number),
                        EXCLUDED.product_url,
                        EXCLUDED.source_url,
                        EXCLUDED.source_image_url
                    ) OR device_model.active = FALSE
                    THEN now()
                    ELSE device_model.updated_at
                END
        """

        seen_ids = [record.id for record in records]
        with self.connection() as connection:
            for record in records:
                connection.execute(
                    family_query,
                    (
                        record.family_id,
                        record.manufacturer,
                        record.family_name,
                        record.family_id.removeprefix("garmin-")
                        or record.family_name.lower(),
                        record.source_url,
                    ),
                )
                connection.execute(
                    model_query,
                    (
                        record.id,
                        record.family_id,
                        record.manufacturer,
                        record.model,
                        record.canonical_model,
                        record.variant,
                        record.case_size_mm,
                        record.display_type,
                        record.part_number,
                        record.product_url,
                        record.source_url,
                        record.source_image_url,
                    ),
                )

                connection.execute(
                    """
                    INSERT INTO device_asset (
                        device_model_id, asset_type, status, scope
                    ) VALUES (%s, 'product-image', 'MISSING', 'MODEL')
                    ON CONFLICT (device_model_id, asset_type, scope) DO NOTHING
                    """,
                    (record.id,),
                )

            if collection_complete:
                connection.execute(
                    """
                    UPDATE device_model
                    SET
                        consecutive_missed_collections = CASE
                            WHEN id = ANY(%s) THEN 0
                            ELSE consecutive_missed_collections + 1
                        END,
                        active = CASE
                            WHEN id = ANY(%s) THEN TRUE
                            WHEN consecutive_missed_collections + 1 >= 3 THEN FALSE
                            ELSE active
                        END,
                        updated_at = CASE
                            WHEN id <> ALL(%s)
                             AND active = TRUE
                             AND consecutive_missed_collections + 1 >= 3
                            THEN now()
                            ELSE updated_at
                        END
                    WHERE TRUE
                    """,
                    (seen_ids, seen_ids, seen_ids),
                )

    def record_device_collection_run(
        self,
        *,
        source_url: str,
        started_at: datetime,
        finished_at: datetime,
        status: str,
        discovered_count: int,
        canonical_count: int,
        warning_count: int,
        diagnostics: dict[str, Any],
    ) -> None:
        import json

        with self.connection() as connection:
            connection.execute(
                """
                INSERT INTO device_collection_run (
                    source_url, started_at, finished_at, status,
                    discovered_count, canonical_count, warning_count,
                    diagnostics_json
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                """,
                (
                    source_url,
                    started_at,
                    finished_at,
                    status,
                    discovered_count,
                    canonical_count,
                    warning_count,
                    json.dumps(diagnostics, ensure_ascii=False),
                ),
            )

    def upsert_device_asset(
        self,
        *,
        device_model_id: str | None,
        asset_type: str,
        status: str,
        scope: str,
        url: str | None = None,
        storage_key: str | None = None,
        sha256: str | None = None,
        width: int | None = None,
        height: int | None = None,
        mime_type: str | None = None,
        source_url: str | None = None,
        license_information: str | None = None,
        attribution: str | None = None,
        source_type: str | None = None,
        source_brand: str | None = None,
        attribution_required: bool | None = None,
        asset_version: int | None = None,
    ) -> None:
        allowed_statuses = {"MISSING", "PENDING_REVIEW", "AVAILABLE", "DEPRECATED"}
        allowed_scopes = {"FAMILY", "MODEL", "MODEL_SIZE", "EXACT_VARIANT", "GENERIC"}
        if status not in allowed_statuses:
            raise ValueError("unsupported device asset status")
        if scope not in allowed_scopes:
            raise ValueError("unsupported device asset scope")
        if (scope == "GENERIC") != (device_model_id is None):
            raise ValueError("GENERIC assets must not have a device model owner")
        normalize_asset_source(
            source_type,
            source_brand,
            attribution_required,
            required=status == "AVAILABLE",
        )
        if status != "AVAILABLE":
            url = None
            storage_key = None

        with self.connection() as connection:
            existing = connection.execute(
                """
                SELECT id
                FROM device_asset
                WHERE device_model_id IS NOT DISTINCT FROM %s
                  AND asset_type = %s
                  AND scope = %s
                FOR UPDATE
                """,
                (device_model_id, asset_type, scope),
            ).fetchone()
            values = (
                device_model_id,
                asset_type,
                status,
                url,
                storage_key,
                sha256,
                width,
                height,
                mime_type,
                source_url,
                license_information,
                attribution,
                source_type,
                source_brand,
                attribution_required,
                asset_version,
            )
            if existing:
                connection.execute(
                    """
                    UPDATE device_asset
                    SET status = %s,
                        url = %s,
                        storage_key = %s,
                        sha256 = %s,
                        width = %s,
                        height = %s,
                        mime_type = %s,
                        source_url = COALESCE(%s, source_url),
                        license_information = COALESCE(%s, license_information),
                        attribution = COALESCE(%s, attribution),
                        source_type = COALESCE(%s, source_type),
                        source_brand = COALESCE(%s, source_brand),
                        attribution_required = COALESCE(%s, attribution_required),
                        asset_version = COALESCE(%s, asset_version),
                        updated_at = now()
                    WHERE id = %s
                    """,
                    (*values[2:], existing["id"]),
                )
            else:
                connection.execute(
                    """
                    INSERT INTO device_asset (
                        device_model_id, asset_type, status, url, storage_key,
                        sha256, width, height, mime_type, source_url,
                        license_information, attribution, source_type, source_brand,
                        attribution_required, asset_version, scope
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (*values, scope),
                )


def migration_directory() -> Path:
    return Path(__file__).with_name("migrations")
