from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .models import CollectedDevice, CollectedMap
from .asset_attribution import normalize_asset_source
from .historical_devices import historical_device_for_event
from .map_capability import classify_map_capable


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
                event_id, occurred_at, model, compatibility_identity, variant, case_size_mm,
                display_type, canonical_device_model_id, identity_resolution_state,
                family, firmware_version,
                usb_vendor_id, usb_product_id, transport, provider, region,
                map_release, terento_version, macos_version, phase_outcome,
                automatic_finishing_result, reconnect_verified, map_visible_after_reconnect,
                error_category, deletion_token_hash, operation_id, map_result_index,
                selected_map_count, app_build, release_label, failure_stage, failure_code,
                native_failure_code, write_started, remote_object_created,
                cleanup_attempted, cleanup_succeeded, transfer_progress_bucket,
                raw_mtp_model, identity_resolution_code
            ) VALUES (
                %(id)s, %(timestamp)s, %(model)s, %(compatibilityIdentity)s, %(variant)s, %(caseSizeMm)s,
                %(displayType)s, %(canonicalDeviceId)s, %(identityResolutionState)s,
                %(family)s, %(firmwareVersion)s,
                %(usbVendorID)s, %(usbProductID)s, %(transport)s, %(provider)s, %(region)s,
                %(mapRelease)s, %(terentoVersion)s, %(macOSVersion)s, %(phaseOutcome)s,
                %(automaticFinishingResult)s, %(reconnectVerified)s, %(mapVisibleAfterReconnect)s,
                %(errorCategory)s, %(deletionTokenHash)s, %(operationId)s, %(mapResultIndex)s,
                %(selectedMapCount)s, %(appBuild)s, %(releaseLabel)s, %(failureStage)s,
                %(failureCode)s, %(nativeFailureCode)s, %(writeStarted)s,
                %(remoteObjectCreated)s, %(cleanupAttempted)s, %(cleanupSucceeded)s,
                %(transferProgressBucket)s, %(rawMTPModel)s, %(identityResolutionCode)s
            ) ON CONFLICT (event_id) DO NOTHING
            RETURNING event_id
        """
        values = {
            **event,
            # Swift Codable omits nil optional fields. PostgreSQL still needs
            # explicit NULL parameters for the named placeholders below.
            "family": event.get("family"),
            "firmwareVersion": event.get("firmwareVersion"),
            "compatibilityIdentity": event.get("compatibilityIdentity") or event["model"],
            "variant": event.get("variant"),
            "caseSizeMm": event.get("caseSizeMm"),
            "displayType": event.get("displayType"),
            "canonicalDeviceId": event.get("canonicalDeviceId"),
            "reconnectVerified": bool(event.get("reconnectVerified", False)),
            "mapVisibleAfterReconnect": bool(event.get("mapVisibleAfterReconnect", False)),
            "errorCategory": event.get("errorCategory"),
            "deletionTokenHash": self._token_hash(event.get("deletionToken")),
            "operationId": event.get("operationId"),
            "mapResultIndex": event.get("mapResultIndex"),
            "selectedMapCount": event.get("selectedMapCount"),
            "appBuild": event.get("appBuild"),
            "releaseLabel": event.get("releaseLabel"),
            "failureStage": event.get("failureStage"),
            "failureCode": event.get("failureCode"),
            "nativeFailureCode": event.get("nativeFailureCode"),
            "writeStarted": event.get("writeStarted"),
            "remoteObjectCreated": event.get("remoteObjectCreated"),
            "cleanupAttempted": event.get("cleanupAttempted"),
            "cleanupSucceeded": event.get("cleanupSucceeded"),
            "transferProgressBucket": event.get("transferProgressBucket"),
            "rawMTPModel": event.get("rawMTPModel"),
            "identityResolutionCode": event.get("identityResolutionCode"),
        }
        with self.connection() as connection:
            # The client contract remains unchanged: canonicalDeviceId is
            # optional. Resolve a reviewed historical identity server-side so
            # an installed fēnix 7 can be recorded even when retail collection
            # no longer returns it. An unknown/stale client ID is ignored
            # rather than allowing a foreign-key failure to drop the report.
            requested_id = values.get("canonicalDeviceId")
            canonical_id = None
            if requested_id:
                existing = connection.execute(
                    "SELECT id FROM device_model WHERE id = %s",
                    (requested_id,),
                ).fetchone()
                canonical_id = (existing.get("id") or requested_id) if existing else None
            historical = historical_device_for_event(event)
            if canonical_id is None and historical is not None:
                self._ensure_historical_device(connection, historical)
                canonical_id = historical.id
            values["canonicalDeviceId"] = canonical_id
            # A canonical link established by the server is a completed
            # identity resolution. Keep this internal state out of the client
            # payload contract and derive it only after canonical validation.
            values["identityResolutionState"] = "RESOLVED" if canonical_id else "UNRESOLVED"
            inserted = connection.execute(query, values).fetchone() is not None
        return inserted

    @staticmethod
    def _ensure_historical_device(connection: Any, spec: Any) -> None:
        connection.execute(
            """
            INSERT INTO device_family (id, manufacturer, name, canonical_name, source_url)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (id) DO NOTHING
            """,
            (spec.family_id, spec.manufacturer, spec.family_name, spec.canonical_model.split()[0], spec.source_url),
        )
        connection.execute(
            """
            INSERT INTO device_model (
                id, family_id, manufacturer, model, canonical_model, variant,
                case_size_mm, display_type, product_url, source_url,
                source_image_url, active, map_capable, support_status,
                record_source, collector_managed
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE, TRUE,
                       'NOT_EVALUATED', 'HISTORICAL_REVIEWED', FALSE)
            ON CONFLICT (id) DO NOTHING
            """,
            (
                spec.id, spec.family_id, spec.manufacturer, spec.model,
                spec.canonical_model, spec.variant, spec.case_size_mm,
                spec.display_type, spec.product_url, spec.source_url,
                spec.source_image_url,
            ),
        )

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

    def compatibility_operation_details(self, limit: int = 500) -> list[dict[str, Any]]:
        return self._compatibility_operation_details("ACTIVE", limit)

    def compatibility_resolved_operation_details(self, limit: int = 500) -> list[dict[str, Any]]:
        return self._compatibility_operation_details("RESOLVED", limit)

    def _compatibility_operation_details(self, diagnostic_status: str, limit: int) -> list[dict[str, Any]]:
        query = """
            SELECT
                COALESCE(operation_id::text, 'legacy:' || event_id::text) AS operation_key,
                operation_id, event_id, occurred_at, model, compatibility_identity,
                variant, firmware_version, region, map_release, terento_version,
                app_build, release_label, map_result_index, selected_map_count,
                phase_outcome, automatic_finishing_result, failure_stage, failure_code, native_failure_code,
                COALESCE(write_started, true) AS write_started,
                COALESCE(remote_object_created, false) AS remote_object_created,
                COALESCE(cleanup_attempted, false) AS cleanup_attempted,
                cleanup_succeeded, transfer_progress_bucket, error_category, transport,
                raw_mtp_model, identity_resolution_code,
                diagnostic_status, resolution_code, resolution_reason,
                resolution_note, resolved_at, resolved_by, linked_github_issue,
                admin_user.username AS resolved_by_username,
                identity_resolution_state, canonical_device_model_id
            FROM compatibility_evidence_event
            LEFT JOIN admin_user ON admin_user.id = compatibility_evidence_event.resolved_by
            WHERE diagnostic_status = %s
            ORDER BY occurred_at DESC, operation_key, map_result_index NULLS FIRST
            LIMIT %s
        """
        with self.connection() as connection:
            return list(connection.execute(query, (diagnostic_status, limit)).fetchall())

    def public_compatibility_statistics(self, limit: int) -> list[dict[str, Any]]:
        query = """
            SELECT public_display_name AS model,
                   model AS canonical_model,
                   compatibility_identity,
                   variant,
                   case_size_mm,
                   display_type,
                   canonical_device_model_id,
                   attempted_install_count,
                   successful_install_count,
                   reconnect_verified_install_count,
                   failed_install_count,
                   success_rate,
                   calculated_status,
                   last_success,
                   last_evidence,
                   recognized_map_capable_evidence
            FROM compatibility_model_statistics
            WHERE public_statistics_enabled = true
              AND review_status = 'APPROVED'
              AND calculated_status IN ('TESTING', 'TESTED', 'SUPPORTED', 'VERIFIED')
            ORDER BY successful_install_count DESC, attempted_install_count DESC, public_display_name
            LIMIT %s
        """
        with self.connection() as connection:
            return list(connection.execute(query, (limit,)).fetchall())

    def public_compatibility_models(self, limit: int) -> list[dict[str, Any]]:
        """Return an additive, evidence-first public model projection.

        This deliberately does not replace ``public_compatibility_statistics``
        because the latter is consumed by existing native/web clients.
        """
        query = """
            SELECT
                s.public_display_name AS model,
                s.model AS evidence_model,
                s.compatibility_identity,
                s.variant,
                s.case_size_mm,
                s.display_type,
                s.canonical_device_model_id,
                s.attempted_install_count,
                s.successful_install_count,
                s.reconnect_verified_install_count,
                s.failed_install_count,
                s.success_rate,
                s.calculated_status,
                s.last_success,
                s.last_evidence,
                s.recognized_map_capable_evidence,
                dm.family_id,
                f.canonical_name AS family,
                f.name AS family_name,
                dm.canonical_model,
                dm.model AS catalog_model,
                dm.source_image_url,
                asset.asset_type,
                asset.status AS asset_status,
                asset.url AS asset_url,
                asset.scope AS asset_scope,
                asset.sha256 AS asset_sha256,
                asset.mime_type AS asset_mime_type,
                asset.width AS asset_width,
                asset.height AS asset_height,
                asset.asset_version,
                asset.source_type AS asset_source_type,
                asset.source_brand AS asset_source_brand,
                asset.attribution_required AS asset_attribution_required,
                asset.storage_key AS asset_storage_key
            FROM compatibility_model_statistics AS s
            LEFT JOIN device_model AS dm
                ON dm.id = s.canonical_device_model_id
            LEFT JOIN device_family AS f
                ON f.id = dm.family_id
            LEFT JOIN LATERAL (
                SELECT da.*
                FROM device_asset AS da
                WHERE da.device_model_id = dm.id
                  AND da.status = 'AVAILABLE'
                ORDER BY
                    CASE da.scope
                        WHEN 'EXACT_VARIANT' THEN 0
                        WHEN 'MODEL_SIZE' THEN 1
                        WHEN 'MODEL' THEN 2
                        WHEN 'FAMILY' THEN 3
                        ELSE 4
                    END,
                    da.updated_at DESC,
                    da.id DESC
                LIMIT 1
            ) AS asset ON TRUE
            WHERE s.public_statistics_enabled = true
              AND s.review_status = 'APPROVED'
              AND s.calculated_status IN ('TESTING', 'TESTED', 'SUPPORTED', 'VERIFIED')
            ORDER BY s.successful_install_count DESC,
                     s.attempted_install_count DESC,
                     s.public_display_name
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

    def update_device_support_status(
        self,
        device_id: str,
        support_status: str,
        admin_user_id: int | None = None,
        reason: str | None = None,
        note: str | None = None,
    ) -> bool:
        """Update only the operator's installation authorization.

        Evidence counts/statuses are computed from compatibility events and are
        intentionally absent from this UPDATE. In particular, this method is
        never used as a device write authorization gate.
        """
        allowed = {"SUPPORTED", "UNSUPPORTED", "NOT_EVALUATED"}
        normalized = support_status.strip().upper()
        if normalized not in allowed:
            raise ValueError("unsupported support decision")
        with self.connection() as connection:
            current = connection.execute(
                "SELECT support_status FROM device_model WHERE id = %s FOR UPDATE",
                (device_id,),
            ).fetchone()
            if current is None:
                return False
            previous = str(current["support_status"])
            if previous != normalized:
                connection.execute(
                    """
                    INSERT INTO device_authorization_audit (
                        device_model_id, previous_status, new_status,
                        reason, note, changed_by
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (device_id, previous, normalized, reason, note, admin_user_id),
                )
                connection.execute(
                    """
                    UPDATE device_model
                    SET support_status = %s, updated_at = now()
                    WHERE id = %s
                    """,
                    (normalized, device_id),
                )
        return True

    def update_public_compatibility_review(
        self,
        device_id: str,
        *,
        action: str,
        admin_user_id: int | None = None,
        note: str | None = None,
    ) -> bool:
        """Publish or withdraw one exact device's evidence projection.

        This operator review changes only the legacy public-review gate. It
        never changes evidence events, calculated status, install counts, or
        device installation authorization.
        """
        normalized_action = action.strip().upper()
        if normalized_action not in {"PUBLISH", "UNPUBLISH"}:
            raise ValueError("unsupported public compatibility review action")
        note = (note or "").strip() or None
        with self.connection() as connection:
            device = connection.execute(
                """
                SELECT id, model, variant
                FROM device_model
                WHERE id = %s AND manufacturer = 'Garmin'
                FOR UPDATE
                """,
                (device_id,),
            ).fetchone()
            if device is None:
                return False
            statistics = connection.execute(
                """
                SELECT compatibility_identity, calculated_status
                FROM compatibility_model_statistics
                WHERE canonical_device_model_id = %s
                ORDER BY last_evidence DESC NULLS LAST
                LIMIT 1
                """,
                (device_id,),
            ).fetchone()
            if statistics is None:
                if normalized_action == "PUBLISH":
                    raise ValueError("compatibility evidence is required before publication")
                return True
            compatibility_identity = str(statistics["compatibility_identity"])
            if normalized_action == "PUBLISH" and str(statistics["calculated_status"] or "") not in {
                "TESTING", "TESTED", "SUPPORTED", "VERIFIED",
            }:
                raise ValueError("recognized map-capable evidence is required before publication")
            public_display_name = (
                f"{device['model']} · {device['variant']}"
                if device["variant"] else str(device["model"])
            )
            review = connection.execute(
                """
                SELECT model, review_status, public_statistics_enabled, public_display_name
                FROM compatibility_model_review
                WHERE COALESCE(NULLIF(identity_key, ''), model) = %s
                FOR UPDATE
                """,
                (compatibility_identity,),
            ).fetchone()
            new_review_status = "APPROVED" if normalized_action == "PUBLISH" else "PENDING"
            new_enabled = normalized_action == "PUBLISH"
            previous_status = str(review["review_status"]) if review else None
            previous_enabled = bool(review["public_statistics_enabled"]) if review else None
            changed = (
                review is None
                or previous_status != new_review_status
                or previous_enabled != new_enabled
                or str(review["public_display_name"] or "") != public_display_name
            )
            if review is None:
                connection.execute(
                    """
                    INSERT INTO compatibility_model_review (
                        model, identity_key, review_status,
                        public_statistics_enabled, public_display_name, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, now())
                    """,
                    (
                        compatibility_identity, compatibility_identity,
                        new_review_status, new_enabled, public_display_name,
                    ),
                )
            elif changed:
                connection.execute(
                    """
                    UPDATE compatibility_model_review
                    SET review_status = %s,
                        public_statistics_enabled = %s,
                        public_display_name = %s,
                        updated_at = now()
                    WHERE model = %s
                    """,
                    (new_review_status, new_enabled, public_display_name, review["model"]),
                )
            if changed:
                connection.execute(
                    """
                    INSERT INTO public_compatibility_review_audit (
                        device_model_id, compatibility_identity,
                        previous_review_status, new_review_status,
                        previous_public_statistics_enabled,
                        new_public_statistics_enabled,
                        public_display_name, note, changed_by
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        device_id, compatibility_identity,
                        previous_status, new_review_status,
                        previous_enabled, new_enabled,
                        public_display_name, note, admin_user_id,
                    ),
                )
        return True

    def update_diagnostic_lifecycle(
        self,
        operation_key: str,
        *,
        new_status: str,
        admin_user_id: int | None,
        resolution_reason: str | None = None,
        resolution_note: str | None = None,
        linked_github_issue: str | None = None,
    ) -> int:
        """Resolve or reopen all map-result rows belonging to one install.

        Evidence rows are never deleted. Lifecycle fields and the audit trail
        are admin-only workflow metadata and cannot authorize device writes.
        """
        allowed_statuses = {"ACTIVE", "RESOLVED"}
        allowed_reasons = {
            "FIXED", "HISTORICAL_SUPERSEDED", "DUPLICATE",
            "IDENTITY_CORRECTED", "NOT_TERENTO_ISSUE", "OTHER",
        }
        status = new_status.strip().upper()
        if status not in allowed_statuses:
            raise ValueError("unsupported diagnostic status")
        if status == "RESOLVED" and resolution_reason not in allowed_reasons:
            raise ValueError("a resolution reason is required")
        operation_key = operation_key.strip()
        if not operation_key or len(operation_key) > 160:
            raise ValueError("invalid diagnostic record")
        linked_issue = (linked_github_issue or "").strip() or None
        if linked_issue:
            issue_match = re.fullmatch(r"#?(\d{1,10})", linked_issue)
            if not issue_match:
                raise ValueError("invalid GitHub issue reference")
            linked_issue = f"#{int(issue_match.group(1))}"
        note = (resolution_note or "").strip() or None
        with self.connection() as connection:
            rows = connection.execute(
                """
                SELECT event_id, diagnostic_status
                FROM compatibility_evidence_event
                WHERE COALESCE(operation_id::text, 'legacy:' || event_id::text) = %s
                FOR UPDATE
                """,
                (operation_key,),
            ).fetchall()
            for row in rows:
                previous = str(row["diagnostic_status"])
                if previous == status:
                    continue
                if status == "RESOLVED":
                    connection.execute(
                        """
                        UPDATE compatibility_evidence_event
                        SET diagnostic_status = 'RESOLVED',
                            resolution_code = %s,
                            resolution_reason = %s,
                            resolution_note = %s,
                            linked_github_issue = COALESCE(%s, linked_github_issue),
                            resolved_at = now(),
                            resolved_by = %s
                        WHERE event_id = %s
                        """,
                        (resolution_reason, resolution_reason, note, linked_issue, admin_user_id, row["event_id"]),
                    )
                else:
                    connection.execute(
                        """
                        UPDATE compatibility_evidence_event
                        SET diagnostic_status = 'ACTIVE',
                            resolved_at = NULL,
                            resolved_by = NULL
                        WHERE event_id = %s
                        """,
                        (row["event_id"],),
                    )
                connection.execute(
                    """
                    INSERT INTO compatibility_diagnostic_lifecycle_audit (
                        event_id, previous_status, new_status,
                        resolution_reason, resolution_note,
                        linked_github_issue, changed_by
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (row["event_id"], previous, status,
                     resolution_reason, note, linked_issue, admin_user_id),
                )
            return len(rows)

    def update_diagnostic_issue(
        self,
        operation_key: str,
        *,
        linked_github_issue: str | None,
        admin_user_id: int | None = None,
    ) -> int:
        """Link or unlink a GitHub issue without changing evidence semantics."""
        operation_key = operation_key.strip()
        if not operation_key or len(operation_key) > 160:
            raise ValueError("invalid diagnostic record")
        raw_issue = (linked_github_issue or "").strip()
        if raw_issue:
            match = re.fullmatch(r"#?(\d{1,10})", raw_issue)
            if not match:
                raise ValueError("invalid GitHub issue reference")
            linked_github_issue = f"#{int(match.group(1))}"
        else:
            linked_github_issue = None
        with self.connection() as connection:
            rows = connection.execute(
                """
                SELECT event_id
                FROM compatibility_evidence_event
                WHERE COALESCE(operation_id::text, 'legacy:' || event_id::text) = %s
                FOR UPDATE
                """,
                (operation_key,),
            ).fetchall()
            for row in rows:
                connection.execute(
                    """
                    UPDATE compatibility_evidence_event
                    SET linked_github_issue = %s
                    WHERE event_id = %s
                    """,
                    (linked_github_issue, row["event_id"]),
                )
            return len(rows)

    def resolve_compatibility_identity(
        self,
        operation_key: str,
        *,
        action: str,
        canonical_device_model_id: str | None,
        admin_user_id: int | None,
        reason: str | None = None,
        note: str | None = None,
    ) -> int:
        """Apply an explicit identity review without changing outcomes."""
        allowed_actions = {"ASSIGN", "LEAVE_UNRESOLVED", "NOT_IDENTIFIABLE"}
        normalized_action = action.strip().upper()
        if normalized_action not in allowed_actions:
            raise ValueError("unsupported identity action")
        if normalized_action == "ASSIGN":
            canonical_device_model_id = (canonical_device_model_id or "").strip()
            if not canonical_device_model_id:
                raise ValueError("a canonical device is required")
        else:
            canonical_device_model_id = None
        reason = (reason or "").strip() or None
        note = (note or "").strip() or None
        operation_key = operation_key.strip()
        if not operation_key or len(operation_key) > 160:
            raise ValueError("invalid diagnostic record")
        with self.connection() as connection:
            if canonical_device_model_id is not None:
                device = connection.execute(
                    """
                    SELECT id, model, variant
                    FROM device_model
                    WHERE id = %s AND manufacturer = 'Garmin'
                    """,
                    (canonical_device_model_id,),
                ).fetchone()
                if device is None:
                    raise ValueError("canonical Garmin device not found")
                new_identity = f"{device['model']} · {device['variant']}" if device["variant"] else str(device["model"])
            else:
                new_identity = "Identity unresolved" if normalized_action == "LEAVE_UNRESOLVED" else "Identity not identifiable"
            rows = connection.execute(
                """
                SELECT event_id, compatibility_identity, canonical_device_model_id
                FROM compatibility_evidence_event
                WHERE COALESCE(operation_id::text, 'legacy:' || event_id::text) = %s
                FOR UPDATE
                """,
                (operation_key.strip(),),
            ).fetchall()
            for row in rows:
                connection.execute(
                    """
                    UPDATE compatibility_evidence_event
                    SET canonical_device_model_id = %s,
                        identity_resolution_state = %s
                    WHERE event_id = %s
                    """,
                    (canonical_device_model_id,
                     "RESOLVED" if normalized_action == "ASSIGN" else (
                         "NOT_IDENTIFIABLE" if normalized_action == "NOT_IDENTIFIABLE" else "UNRESOLVED"
                     ),
                     row["event_id"]),
                )
                connection.execute(
                    """
                    INSERT INTO compatibility_identity_resolution_audit (
                        event_id, previous_identity,
                        previous_canonical_device_model_id,
                        new_identity, new_canonical_device_model_id,
                        action, reason, note, corrected_by
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (row["event_id"], str(row["compatibility_identity"]),
                     row["canonical_device_model_id"], new_identity,
                     canonical_device_model_id, normalized_action, reason, note,
                     admin_user_id),
                )
            return len(rows)

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
                dm.map_capable,
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
            WHERE dm.collector_managed = TRUE
            ORDER BY dm.id
        """
        updated_at_query = """
            SELECT COALESCE(MAX(changed_at), TIMESTAMPTZ 'epoch') AS updated_at
            FROM (
                SELECT updated_at AS changed_at FROM device_family
                UNION ALL
                SELECT updated_at AS changed_at
                FROM device_model
                WHERE collector_managed = TRUE
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

    def admin_device_snapshot(self) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
        """Return one aggregate row per exact Garmin catalog record.

        Compatibility evidence is joined only through the canonical catalog
        device ID. Legacy/model-string joins are deliberately excluded so a
        47 mm and 51 mm variant can never inherit one another's counts.
        """
        query = """
            SELECT
                f.id AS family_id,
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
                dm.record_source,
                dm.collector_managed,
                dm.first_seen_at,
                dm.last_seen_at,
                dm.created_at,
                dm.updated_at,
                dm.map_capable,
                dm.support_status,
                dm.first_seen_collection_run_id,
                dm.last_seen_collection_run_id,
                asset.asset_type,
                asset.status AS asset_status,
                asset.url AS asset_url,
                asset.sha256 AS asset_sha256,
                asset.width AS asset_width,
                asset.height AS asset_height,
                asset.mime_type AS asset_mime_type,
                asset.asset_version,
                COALESCE(usb.identities, '[]'::jsonb) AS usb_identities,
                COALESCE(evidence.attempts, 0) AS attempted_install_count,
                COALESCE(evidence.successful, 0) AS successful_install_count,
                COALESCE(evidence.failed, 0) AS failed_install_count,
                evidence.first_success,
                evidence.last_success,
                evidence.last_evidence,
                public_review.compatibility_identity AS public_compatibility_identity,
                public_review.review_status AS public_review_status,
                COALESCE(public_review.public_statistics_enabled, false) AS public_statistics_enabled,
                public_review.public_display_name,
                latest.id AS latest_successful_sync_id,
                latest.started_at AS latest_successful_sync_started_at,
                latest.finished_at AS latest_successful_sync_finished_at,
                latest.status AS latest_successful_sync_status,
                latest.records_total_before AS latest_records_total_before,
                latest.records_total_after AS latest_records_total_after,
                latest.records_added AS latest_records_added,
                latest.records_updated AS latest_records_updated
            FROM device_model AS dm
            JOIN device_family AS f ON f.id = dm.family_id
            LEFT JOIN LATERAL (
                SELECT da.asset_type, da.status, da.url, da.sha256,
                       da.width, da.height, da.mime_type, da.asset_version
                FROM device_asset AS da
                WHERE da.device_model_id = dm.id
                  AND da.status = 'AVAILABLE'
                ORDER BY da.updated_at DESC, da.id DESC
                LIMIT 1
            ) AS asset ON TRUE
            LEFT JOIN LATERAL (
                SELECT jsonb_agg(
                    jsonb_build_object(
                        'vendorId', ui.vendor_id,
                        'productId', ui.product_id,
                        'source', ui.source,
                        'confidence', ui.confidence
                    ) ORDER BY ui.vendor_id, ui.product_id
                ) AS identities
                FROM device_usb_identity AS ui
                WHERE ui.device_model_id = dm.id
            ) AS usb ON TRUE
            LEFT JOIN LATERAL (
                SELECT
                    count(*) FILTER (WHERE o.write_started) AS attempts,
                    count(*) FILTER (WHERE o.write_started AND o.operation_succeeded) AS successful,
                    count(*) FILTER (WHERE o.write_started AND NOT o.operation_succeeded) AS failed,
                    min(o.occurred_at) FILTER (WHERE o.write_started AND o.operation_succeeded) AS first_success,
                    max(o.occurred_at) FILTER (WHERE o.write_started AND o.operation_succeeded) AS last_success,
                    max(o.occurred_at) AS last_evidence
                FROM (
                    SELECT
                        COALESCE(e.operation_id::text, 'legacy:' || e.event_id::text) AS operation_key,
                        bool_or(COALESCE(e.write_started, true)) AS write_started,
                        bool_and(e.phase_outcome = 'SUCCEEDED' AND e.automatic_finishing_result = 'VERIFIED')
                            AND count(*) = max(COALESCE(e.selected_map_count, 1)) AS operation_succeeded,
                        min(e.occurred_at) AS occurred_at
                    FROM compatibility_evidence_event AS e
                    WHERE e.canonical_device_model_id = dm.id
                      AND e.diagnostic_status = 'ACTIVE'
                    GROUP BY COALESCE(e.operation_id::text, 'legacy:' || e.event_id::text)
                ) AS o
            ) AS evidence ON TRUE
            LEFT JOIN LATERAL (
                SELECT s.compatibility_identity, s.review_status,
                       s.public_statistics_enabled, s.public_display_name,
                       s.last_evidence
                FROM compatibility_model_statistics AS s
                WHERE s.canonical_device_model_id = dm.id
                ORDER BY s.last_evidence DESC NULLS LAST
                LIMIT 1
            ) AS public_review ON TRUE
            LEFT JOIN LATERAL (
                SELECT r.*
                FROM device_collection_run AS r
                WHERE r.status = 'SUCCEEDED'
                ORDER BY r.finished_at DESC NULLS LAST, r.id DESC
                LIMIT 1
            ) AS latest ON TRUE
            ORDER BY dm.model, dm.case_size_mm NULLS LAST, dm.variant, dm.id
        """
        with self.connection() as connection:
            rows = list(connection.execute(query).fetchall())
            latest = connection.execute(
                """
                SELECT id, started_at, finished_at, status,
                       records_total_before, records_total_after,
                       records_added, records_updated
                FROM device_collection_run
                WHERE status = 'SUCCEEDED'
                ORDER BY finished_at DESC NULLS LAST, id DESC
                LIMIT 1
                """
            ).fetchone()

        sync = dict(latest) if latest else None
        return rows, sync

    def upsert_collected_devices(
        self,
        records: list[CollectedDevice],
        *,
        collection_complete: bool = True,
    ) -> dict[str, Any]:
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
                source_image_url, map_capable, record_source, collector_managed
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'CURRENT_RETAIL', TRUE)
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
                map_capable = COALESCE(device_model.map_capable, EXCLUDED.map_capable),
                record_source = 'CURRENT_RETAIL',
                collector_managed = TRUE,
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
            total_before = int(
                connection.execute("SELECT count(*) AS count FROM device_model").fetchone()["count"]
            )
            existing_rows = {
                row["id"]: row
                for row in connection.execute(
                    """
                    SELECT id, family_id, manufacturer, model, canonical_model, variant,
                           case_size_mm, display_type, part_number, product_url,
                           source_url, source_image_url, active
                    FROM device_model
                    WHERE id = ANY(%s)
                    """,
                    (seen_ids,),
                ).fetchall()
            }
            added_ids: list[str] = []
            updated_ids: list[str] = []
            for record in records:
                existing = existing_rows.get(record.id)
                if existing is None:
                    added_ids.append(record.id)
                else:
                    incoming_part_number = record.part_number or existing["part_number"]
                    incoming_values = (
                        record.family_id,
                        record.manufacturer,
                        record.model,
                        record.canonical_model,
                        record.variant,
                        record.case_size_mm,
                        record.display_type,
                        incoming_part_number,
                        record.product_url,
                        record.source_url,
                        record.source_image_url,
                    )
                    existing_values = tuple(existing[key] for key in (
                        "family_id", "manufacturer", "model", "canonical_model", "variant",
                        "case_size_mm", "display_type", "part_number", "product_url",
                        "source_url", "source_image_url",
                    ))
                    if existing["active"] is False or incoming_values != existing_values:
                        updated_ids.append(record.id)
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
                        classify_map_capable(record.canonical_model, record.manufacturer),
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
                deactivated_ids = [
                    row["id"]
                    for row in connection.execute(
                        """
                        SELECT id
                        FROM device_model
                        WHERE id <> ALL(%s)
                          AND collector_managed = TRUE
                          AND active = TRUE
                          AND consecutive_missed_collections + 1 >= 3
                        """,
                        (seen_ids,),
                    ).fetchall()
                ]
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
                    WHERE collector_managed = TRUE
                    """,
                    (seen_ids, seen_ids, seen_ids),
                )
                updated_ids.extend(
                    device_id for device_id in deactivated_ids
                    if device_id not in updated_ids
                )

            total_after = int(
                connection.execute("SELECT count(*) AS count FROM device_model").fetchone()["count"]
            )

        return {
            "records_total_before": total_before,
            "records_total_after": total_after,
            "records_added": len(added_ids),
            "records_updated": len(updated_ids),
            "added_ids": added_ids,
            "updated_ids": updated_ids,
            "seen_ids": seen_ids,
        }

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
        records_total_before: int = 0,
        records_total_after: int = 0,
        records_added: int = 0,
        records_updated: int = 0,
        added_ids: list[str] | None = None,
        seen_ids: list[str] | None = None,
    ) -> None:
        import json

        with self.connection() as connection:
            run = connection.execute(
                """
                INSERT INTO device_collection_run (
                    source_url, started_at, finished_at, status,
                    discovered_count, canonical_count, warning_count,
                    diagnostics_json, records_total_before, records_total_after,
                    records_added, records_updated
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s)
                RETURNING id
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
                    records_total_before,
                    records_total_after,
                    records_added,
                    records_updated,
                ),
            ).fetchone()
            run_id = run["id"]
            if seen_ids:
                connection.execute(
                    """
                    UPDATE device_model
                    SET last_seen_collection_run_id = %s
                    WHERE id = ANY(%s)
                    """,
                    (run_id, seen_ids),
                )
            if added_ids:
                connection.execute(
                    """
                    UPDATE device_model
                    SET first_seen_collection_run_id = COALESCE(first_seen_collection_run_id, %s)
                    WHERE id = ANY(%s)
                    """,
                    (run_id, added_ids),
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
