from __future__ import annotations

import json
import logging
import hmac
import re
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime, parsedate_to_datetime
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit
from uuid import uuid4

from .admin import (
    AdminValidationError,
    account_page,
    campaign_links_page,
    dashboard_page,
    device_detail_page,
    diagnostics_page,
    devices_page,
    map_statistics_page,
    provider_detail_page,
    providers_page,
    _admin_device_payload,
    _normalise_github_issue_reference,
    hash_password,
    login_page,
    new_token,
    setup_page,
    token_hash,
    validate_password,
    validate_username,
    verify_password,
)
from .asset_storage import AssetStorage
from .asset_attribution import generic_fallback_image, public_asset_source
from .catalog import build_catalog, catalog_etag, serialize_catalog
from .db import Database
from .device_catalog import (
    CONTROLLED_ASSET_PREFIX,
    _official_source_image_url,
    build_device_catalog,
    device_catalog_etag,
    serialize_device_catalog,
)
from .compatibility_evidence import (
    EvidenceValidationError,
    validate_deletion_request,
    validate_event,
)
from .compatibility_status import calculate_compatibility_status
from .collect import collect_provider_once
from .map_events import (
    MapEventValidationError,
    validate_map_event,
    validate_statistics_filters,
)
from .provider_catalog import (
    KNOWN_PROVIDER_DEFINITIONS,
    FreizeitkarteProviderAdapter,
    OpenTopoMapProviderAdapter,
)
from .provider_health import check_provider as run_provider_health_check

LOGGER = logging.getLogger(__name__)


class ProviderActivationBlocked(ValueError):
    """Raised when a provider has not passed the activation evidence gate."""

    def __init__(self, gate: dict[str, Any]) -> None:
        self.gate = gate
        super().__init__("provider_activation_blocked")


class CatalogService:
    def __init__(
        self, database: Database, asset_storage: AssetStorage | None = None,
        admin_bootstrap_secret: str | None = None,
        admin_session_ttl_seconds: int = 28_800,
        public_compatibility_stats_enabled: bool = False,
    ) -> None:
        self.database = database
        self.asset_storage = asset_storage
        self.admin_bootstrap_secret = admin_bootstrap_secret
        self.admin_session_ttl_seconds = admin_session_ttl_seconds
        self.public_compatibility_stats_enabled = public_compatibility_stats_enabled

    def health(self) -> bool:
        self.database.prune_compatibility_events()
        return self.database.health()

    def catalog_response(self) -> tuple[bytes, str, datetime]:
        rows, updated_at = self.database.catalog_snapshot()
        body = serialize_catalog(build_catalog(rows, updated_at))
        return body, catalog_etag(body), updated_at

    def device_catalog_response(self) -> tuple[bytes, str, datetime]:
        rows, updated_at = self.database.device_catalog_snapshot()
        body = serialize_device_catalog(build_device_catalog(rows, updated_at))
        return body, device_catalog_etag(body), updated_at

    def admin_providers(self) -> dict[str, Any]:
        rows = {str(row["provider_id"]): row for row in self.database.provider_rows()}
        providers: list[dict[str, Any]] = []
        for provider_id, definition in KNOWN_PROVIDER_DEFINITIONS.items():
            row = rows.get(provider_id, {})
            providers.append(_provider_summary_payload(definition, row))
        for provider_id, row in rows.items():
            if provider_id not in KNOWN_PROVIDER_DEFINITIONS:
                providers.append(_provider_summary_payload(None, row))
        providers.sort(key=lambda item: (str(item["name"]).casefold(), item["id"]))
        return {"schemaVersion": 1, "providers": providers}

    def admin_provider_detail(self, provider_id: str) -> dict[str, Any] | None:
        definition = KNOWN_PROVIDER_DEFINITIONS.get(provider_id)
        detail = self.database.provider_detail(provider_id)
        if detail is None and definition is None:
            return None
        payload = _provider_detail_payload(definition, detail or {})
        if detail is not None and definition is not None:
            payload["provider"]["activationGate"] = self.provider_activation_gate(
                provider_id,
                detail=detail,
            )
        return payload

    def provider_activation_gate(
        self,
        provider_id: str,
        *,
        detail: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        definition = KNOWN_PROVIDER_DEFINITIONS.get(provider_id)
        if definition is None:
            raise LookupError("provider_not_found")
        resolved_detail = detail or self.database.provider_detail(provider_id) or {}
        runs = self.database.provider_runs(provider_id)
        return _provider_activation_gate(provider_id, resolved_detail, runs)

    def check_provider(
        self,
        provider_id: str,
        *,
        admin_user_id: int | None = None,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        definition = KNOWN_PROVIDER_DEFINITIONS.get(provider_id)
        if definition is None:
            raise LookupError("provider_not_found")
        self.database.ensure_provider_definition(definition)
        sources = self.database.provider_download_urls(provider_id)
        source_updated_at = next(
            (
                _format_json_value(row.get("source_updated_at"))
                for row in sources
                if row.get("source_updated_at") is not None
            ),
            None,
        )
        result = run_provider_health_check(
            definition,
            download_urls=[str(row["source_url"]) for row in sources],
            source_updated_at=source_updated_at,
        )
        health_id = self.database.record_provider_health(result)
        self.database.record_admin_audit(
            admin_user_id=admin_user_id,
            action="provider.health_checked",
            provider_id=provider_id,
            target=str(health_id),
            request_id=request_id,
            details={"status": result.status},
        )
        health_payload = _format_json_value(result.as_database_values())
        return {
            "schemaVersion": 1,
            "id": provider_id,
            "healthCheckId": health_id,
            "health": health_payload,
        }

    def provider_health(self, provider_id: str) -> dict[str, Any] | None:
        detail = self.admin_provider_detail(provider_id)
        if detail is None:
            return None
        return {
            "schemaVersion": 1,
            "id": provider_id,
            "health": detail.get("health"),
            "healthHistory": detail.get("healthHistory", []),
        }

    def provider_runs(self, provider_id: str) -> dict[str, Any] | None:
        if self.admin_provider_detail(provider_id) is None:
            return None
        return {
            "schemaVersion": 1,
            "id": provider_id,
            "runs": _format_json_value(self.database.provider_runs(provider_id)),
        }

    def provider_audit(self, provider_id: str) -> dict[str, Any] | None:
        if self.admin_provider_detail(provider_id) is None:
            return None
        return {
            "schemaVersion": 1,
            "id": provider_id,
            "audit": _format_json_value(self.database.audit_rows(provider_id)),
        }

    def collect_provider(
        self,
        provider_id: str,
        *,
        admin_user_id: int | None = None,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        definition = KNOWN_PROVIDER_DEFINITIONS.get(provider_id)
        if definition is None:
            raise LookupError("provider_not_found")
        self.database.ensure_provider_definition(definition)
        if provider_id == "freizeitkarte":
            adapter = FreizeitkarteProviderAdapter()
        elif provider_id == "opentopomap":
            adapter = OpenTopoMapProviderAdapter()
        else:  # pragma: no cover - guarded by the known registry
            raise LookupError("provider_adapter_not_found")
        try:
            result = _format_json_value(collect_provider_once(self.database, adapter))
        except Exception as exc:
            self.database.record_admin_audit(
                admin_user_id=admin_user_id,
                action="provider.catalog_collection_failed",
                provider_id=provider_id,
                request_id=request_id,
                details={
                    "error": type(exc).__name__,
                    "detail": str(exc)[:500],
                },
            )
            raise
        self.database.record_admin_audit(
            admin_user_id=admin_user_id,
            action="provider.catalog_collected",
            provider_id=provider_id,
            request_id=request_id,
            details=result,
        )
        return result

    def set_provider_status(
        self,
        provider_id: str,
        status: str,
        *,
        admin_user_id: int,
        request_id: str | None = None,
        reason: str | None = None,
    ) -> dict[str, Any] | None:
        definition = KNOWN_PROVIDER_DEFINITIONS.get(provider_id)
        if definition is None:
            raise LookupError("provider_not_found")
        if status not in {"ACTIVE", "PAUSED", "RETIRED"}:
            raise ValueError("invalid_provider_status")
        self.database.ensure_provider_definition(definition)
        if status == "ACTIVE":
            gate = self.provider_activation_gate(provider_id)
            if not gate["canActivate"]:
                raise ProviderActivationBlocked(gate)
        if not self.database.set_provider_status(
            provider_id,
            status,
            admin_user_id=admin_user_id,
            request_id=request_id,
            reason=reason,
        ):
            return None
        return {"id": provider_id, "status": status}

    def receive_map_event(self, body: bytes) -> tuple[dict[str, Any], bool]:
        event = validate_map_event(body)
        if event["providerId"] not in KNOWN_PROVIDER_DEFINITIONS:
            raise MapEventValidationError("unknown_provider")
        inserted = self.database.insert_map_event(event)
        return event, inserted

    def map_statistics(self, query: dict[str, str]) -> dict[str, Any]:
        filters = validate_statistics_filters(query)
        rows = self.database.map_statistics(filters)
        return {
            "schemaVersion": 1,
            "filters": query,
            "generatedAt": datetime.now(timezone.utc),
            "rows": rows,
        }

    def asset_response(self, request_path: str) -> tuple[bytes, str, str] | None:
        if self.asset_storage is None:
            return None
        return self.asset_storage.read_public_path(request_path)

    def receive_compatibility_event(self, body: bytes) -> bool:
        return self.database.insert_compatibility_event(validate_event(body))

    def delete_compatibility_event(self, body: bytes) -> bool:
        event_id, deletion_token = validate_deletion_request(body)
        return self.database.delete_compatibility_event(event_id, deletion_token)

    def compatibility_statistics(self) -> list[dict[str, Any]]:
        return self._canonicalize_statistics(self.database.compatibility_statistics())

    def compatibility_operation_details(self) -> list[dict[str, Any]]:
        return self.database.compatibility_operation_details()

    def compatibility_resolved_operation_details(self) -> list[dict[str, Any]]:
        getter = getattr(self.database, "compatibility_resolved_operation_details", None)
        return getter() if getter is not None else []

    def admin_devices(self) -> dict[str, Any]:
        rows, sync = self.database.admin_device_snapshot()
        return _admin_device_payload(rows, sync)

    def update_device_support_status(self, device_id: str, support_status: str) -> bool:
        return self.database.update_device_support_status(device_id, support_status)

    def update_device_authorization(
        self,
        device_id: str,
        support_status: str,
        *,
        admin_user_id: int | None = None,
        reason: str | None = None,
        note: str | None = None,
    ) -> bool:
        """Keep the legacy backend enum while exposing authorization in UI."""
        return self.database.update_device_support_status(
            device_id,
            support_status,
            admin_user_id=admin_user_id,
            reason=reason,
            note=note,
        )

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
        return self.database.update_diagnostic_lifecycle(
            operation_key,
            new_status=new_status,
            admin_user_id=admin_user_id,
            resolution_reason=resolution_reason,
            resolution_note=resolution_note,
            linked_github_issue=linked_github_issue,
        )

    def update_diagnostic_issue(
        self,
        operation_key: str,
        *,
        linked_github_issue: str | None,
        admin_user_id: int | None,
    ) -> int:
        return self.database.update_diagnostic_issue(
            operation_key,
            linked_github_issue=linked_github_issue,
            admin_user_id=admin_user_id,
        )

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
        return self.database.resolve_compatibility_identity(
            operation_key,
            action=action,
            canonical_device_model_id=canonical_device_model_id,
            admin_user_id=admin_user_id,
            reason=reason,
            note=note,
        )

    def update_public_compatibility_review(
        self,
        device_id: str,
        *,
        action: str,
        admin_user_id: int | None,
        note: str | None = None,
    ) -> bool:
        return self.database.update_public_compatibility_review(
            device_id,
            action=action,
            admin_user_id=admin_user_id,
            note=note,
        )

    def admin_review_summary(self) -> dict[str, int]:
        return self.database.admin_review_summary()

    def admin_is_configured(self) -> bool:
        return self.database.admin_user_count() > 0

    def setup_admin(self, username: str, password: str, bootstrap_secret: str) -> dict[str, Any]:
        if self.admin_is_configured():
            raise AdminValidationError("An administrator account already exists.")
        if not self.admin_bootstrap_secret or not hmac.compare_digest(bootstrap_secret, self.admin_bootstrap_secret):
            raise AdminValidationError("The deployment secret is incorrect.")
        return self.database.create_admin_user(validate_username(username), hash_password(password))

    def login_admin(self, username: str, password: str) -> tuple[str, str]:
        user = self.database.admin_user_by_username(username.strip())
        if not user or not verify_password(password, user["password_hash"]):
            raise AdminValidationError("Incorrect username or password.")
        session_token, csrf_token = new_token(), new_token()
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=self.admin_session_ttl_seconds)
        self.database.create_admin_session(
            int(user["id"]), token_hash(session_token), token_hash(csrf_token), expires_at
        )
        return session_token, csrf_token

    def admin_session(self, session_token: str | None) -> dict[str, Any] | None:
        if not session_token:
            return None
        return self.database.admin_session(token_hash(session_token))

    def csrf_valid(self, session: dict[str, Any], csrf_token: str | None) -> bool:
        return bool(csrf_token) and hmac.compare_digest(
            str(session["csrf_token_hash"]), token_hash(str(csrf_token))
        )

    def logout_admin(self, session_token: str | None) -> None:
        if session_token:
            self.database.delete_admin_session(token_hash(session_token))

    def update_admin_account(
        self, user: dict[str, Any], username: str, current_password: str,
        new_password: str, new_password_confirmation: str,
    ) -> dict[str, Any]:
        if not verify_password(current_password, user["password_hash"]):
            raise AdminValidationError("Current password is incorrect.")
        normalized_username = validate_username(username)
        password_hash = user["password_hash"]
        if new_password or new_password_confirmation:
            if new_password != new_password_confirmation:
                raise AdminValidationError("New passwords do not match.")
            password_hash = hash_password(validate_password(new_password))
        return self.database.update_admin_user(int(user["id"]), normalized_username, password_hash)

    def public_statistics(self, limit: int) -> list[dict[str, Any]]:
        if not self.public_compatibility_stats_enabled:
            raise LookupError("disabled")
        return self._canonicalize_statistics(self.database.public_compatibility_statistics(limit))

    def public_models(self, limit: int) -> list[dict[str, Any]]:
        if not self.public_compatibility_stats_enabled:
            raise LookupError("disabled")
        return self._canonicalize_statistics(self.database.public_compatibility_models(limit))

    @staticmethod
    def _canonicalize_statistics(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Apply the one status classifier before any consumer renders rows."""
        canonical: list[dict[str, Any]] = []
        for row in rows:
            status = calculate_compatibility_status(
                successful_install_count=int(row.get("successful_install_count") or 0),
                recognized_map_capable_evidence=(
                    row.get("recognized_map_capable_evidence") is True
                ),
            )
            canonical.append({**row, "calculated_status": status.value if status else None})
        return canonical


def make_handler(service: CatalogService) -> type[BaseHTTPRequestHandler]:
    request_times: dict[str, deque[float]] = defaultdict(deque)

    class Handler(BaseHTTPRequestHandler):
        server_version = "TerentoCatalog"
        sys_version = ""

        def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
            self._handle_request(send_body=True)

        def do_HEAD(self) -> None:  # noqa: N802 - stdlib handler API
            self._handle_request(send_body=False)

        def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
            request_path = urlsplit(self.path).path
            if request_path == "/map-events":
                self._handle_map_event()
                return
            if request_path == "/compatibility/events":
                self._handle_compatibility_event()
                return
            if re.fullmatch(r"/admin/providers/[a-z0-9][a-z0-9._-]{0,159}/(?:state|check|collect|retire)", request_path):
                self._handle_provider_post(request_path)
                return
            if request_path.startswith("/admin"):
                self._handle_admin_post(request_path)
                return
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"}, send_body=True, cache_control="no-store")

        def _handle_map_event(self) -> None:
            client = f"map-event:{self.client_address[0]}"
            if self._rate_limited(client, limit=60, window=60):
                self._send_json(
                    HTTPStatus.TOO_MANY_REQUESTS,
                    {"error": "rate_limited"},
                    send_body=True,
                    cache_control="no-store",
                )
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                length = 0
            if length <= 0 or length > 8 * 1024:
                self._send_json(
                    HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                    {"error": "invalid_size"},
                    send_body=True,
                    cache_control="no-store",
                )
                return
            content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
            if content_type != "application/json":
                self._send_json(
                    HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
                    {"error": "invalid_content_type"},
                    send_body=True,
                    cache_control="no-store",
                )
                return
            recent = request_times[client]
            recent.append(time.monotonic())
            try:
                event, inserted = service.receive_map_event(self.rfile.read(length))
            except MapEventValidationError as exc:
                self._send_json(
                    HTTPStatus.BAD_REQUEST,
                    {"error": str(exc)},
                    send_body=True,
                    cache_control="no-store",
                )
                return
            except Exception:
                LOGGER.exception("map event storage failed")
                self._send_json(
                    HTTPStatus.SERVICE_UNAVAILABLE,
                    {"error": "map_events_unavailable"},
                    send_body=True,
                    cache_control="no-store",
                )
                return
            self._send_json(
                HTTPStatus.CREATED if inserted else HTTPStatus.OK,
                {
                    "status": "stored" if inserted else "duplicate",
                    "operationId": event["operationId"],
                },
                send_body=True,
                cache_control="no-store",
            )

        def do_DELETE(self) -> None:  # noqa: N802 - stdlib handler API
            request_path = urlsplit(self.path).path
            if request_path == "/compatibility/events":
                self._handle_compatibility_event_deletion()
                return
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"}, send_body=True, cache_control="no-store")

        def _handle_request(self, *, send_body: bool) -> None:
            request_path = urlsplit(self.path).path
            if request_path == "/health":
                self._handle_health(send_body=send_body)
                return
            if request_path == "/maps/catalog.json":
                self._handle_catalog(
                    service.catalog_response,
                    send_body=send_body,
                    unavailable_error="catalog_unavailable",
                )
                return
            if request_path == "/devices/catalog.json":
                self._handle_catalog(
                    service.device_catalog_response,
                    send_body=send_body,
                    unavailable_error="device_catalog_unavailable",
                )
                return
            if request_path.startswith("/assets/devices/"):
                self._handle_asset(request_path, send_body=send_body)
                return
            if request_path == "/compatibility/public/top-models.json":
                self._handle_public_statistics(send_body=send_body)
                return
            if request_path == "/compatibility/public/models.json":
                self._handle_public_models(send_body=send_body)
                return
            if request_path == "/internal/compatibility/":
                self._redirect("/admin", send_body=send_body)
                return
            if request_path.startswith("/admin"):
                self._handle_admin_get(request_path, send_body=send_body)
                return
            self._send_json(
                HTTPStatus.NOT_FOUND,
                {"error": "not_found"},
                send_body=send_body,
                cache_control="no-store",
            )

        def _handle_compatibility_event(self) -> None:
            client = self.client_address[0]
            now = time.monotonic()
            recent = request_times[client]
            while recent and recent[0] < now - 60:
                recent.popleft()
            if len(recent) >= 30:
                self._send_json(HTTPStatus.TOO_MANY_REQUESTS, {"error": "rate_limited"}, send_body=True, cache_control="no-store")
                return
            recent.append(now)
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                length = 0
            if length <= 0 or length > 16_384:
                self._send_json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "invalid_size"}, send_body=True, cache_control="no-store")
                return
            try:
                inserted = service.receive_compatibility_event(self.rfile.read(length))
            except EvidenceValidationError as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)}, send_body=True, cache_control="no-store")
                return
            except Exception:
                LOGGER.exception("compatibility event storage failed")
                self._send_json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "evidence_unavailable"}, send_body=True, cache_control="no-store")
                return
            self._send_json(HTTPStatus.CREATED if inserted else HTTPStatus.OK, {"status": "stored" if inserted else "duplicate"}, send_body=True, cache_control="no-store")

        def _handle_compatibility_event_deletion(self) -> None:
            client = f"compatibility-delete:{self.client_address[0]}"
            if self._rate_limited(client, limit=10, window=60):
                self._send_json(HTTPStatus.TOO_MANY_REQUESTS, {"error": "rate_limited"}, send_body=True, cache_control="no-store")
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                length = 0
            if length <= 0 or length > 2048:
                self._send_json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "invalid_size"}, send_body=True, cache_control="no-store")
                return
            try:
                deleted = service.delete_compatibility_event(self.rfile.read(length))
            except EvidenceValidationError as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)}, send_body=True, cache_control="no-store")
                return
            except Exception:
                LOGGER.exception("compatibility event deletion failed")
                self._send_json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "evidence_unavailable"}, send_body=True, cache_control="no-store")
                return
            self._send_json(
                HTTPStatus.OK if deleted else HTTPStatus.NOT_FOUND,
                {"status": "deleted"} if deleted else {"error": "not_found"},
                send_body=True,
                cache_control="no-store",
            )

        def _handle_admin_get(self, request_path: str, *, send_body: bool) -> None:
            try:
                configured = service.admin_is_configured()
            except Exception:
                LOGGER.exception("admin configuration check failed")
                self._send_json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "admin_unavailable"}, send_body=send_body, cache_control="no-store")
                return
            if request_path == "/admin/setup":
                if configured:
                    self._redirect("/admin/login", send_body=send_body)
                elif not service.admin_bootstrap_secret:
                    self._send_json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "admin_bootstrap_not_configured"}, send_body=send_body, cache_control="no-store")
                else:
                    self._send_admin_html(setup_page(), send_body=send_body)
                return
            if not configured:
                self._redirect("/admin/setup", send_body=send_body)
                return
            if request_path == "/admin/login":
                self._send_admin_html(login_page(), send_body=send_body)
                return
            session_token = self._session_cookie()
            session = service.admin_session(session_token)
            if not session:
                self._redirect("/admin/login", send_body=send_body, clear_cookie=bool(session_token))
                return
            csrf_token = self._csrf_cookie()
            if not csrf_token or not service.csrf_valid(session, csrf_token):
                service.logout_admin(session_token)
                self._redirect("/admin/login", send_body=send_body, clear_cookie=True)
                return
            if request_path in {"/admin/providers.json", "/admin/providers.json/"}:
                try:
                    payload = service.admin_providers()
                except Exception:
                    LOGGER.exception("admin provider API failed")
                    self._send_json(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        {"error": "providers_unavailable"},
                        send_body=send_body,
                        cache_control="no-store",
                        noindex=True,
                    )
                    return
                self._send_json(
                    HTTPStatus.OK,
                    payload,
                    send_body=send_body,
                    cache_control="no-store",
                    noindex=True,
                )
                return
            if request_path in {"/admin/map-statistics.json", "/admin/map-statistics.json/"}:
                query = parse_qs(urlsplit(self.path).query, keep_blank_values=True)
                filters = {key: values[-1] for key, values in query.items()}
                try:
                    payload = service.map_statistics(filters)
                except MapEventValidationError as exc:
                    self._send_json(
                        HTTPStatus.BAD_REQUEST,
                        {"error": str(exc)},
                        send_body=send_body,
                        cache_control="no-store",
                        noindex=True,
                    )
                    return
                except Exception:
                    LOGGER.exception("admin map statistics failed")
                    self._send_json(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        {"error": "map_statistics_unavailable"},
                        send_body=send_body,
                        cache_control="no-store",
                        noindex=True,
                    )
                    return
                self._send_json(
                    HTTPStatus.OK,
                    payload,
                    send_body=send_body,
                    cache_control="no-store",
                    noindex=True,
                )
                return
            provider_json_match = re.fullmatch(
                r"/admin/providers/([a-z0-9][a-z0-9._-]{0,159})\.json",
                request_path,
            )
            if provider_json_match:
                provider_id = provider_json_match.group(1)
                try:
                    payload = service.admin_provider_detail(provider_id)
                except Exception:
                    LOGGER.exception("admin provider detail API failed")
                    self._send_json(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        {"error": "provider_unavailable"},
                        send_body=send_body,
                        cache_control="no-store",
                        noindex=True,
                    )
                    return
                if payload is None:
                    self._send_json(
                        HTTPStatus.NOT_FOUND,
                        {"error": "provider_not_found"},
                        send_body=send_body,
                        cache_control="no-store",
                        noindex=True,
                    )
                    return
                self._send_json(
                    HTTPStatus.OK,
                    payload,
                    send_body=send_body,
                    cache_control="no-store",
                    noindex=True,
                )
                return
            provider_match = re.fullmatch(
                r"/admin/providers/([a-z0-9][a-z0-9._-]{0,159})/(health|runs|audit)",
                request_path,
            )
            if provider_match:
                provider_id, resource = provider_match.groups()
                try:
                    payload = (
                        service.provider_health(provider_id)
                        if resource == "health"
                        else service.provider_runs(provider_id)
                        if resource == "runs"
                        else service.provider_audit(provider_id)
                    )
                except Exception:
                    LOGGER.exception("admin provider detail API failed")
                    self._send_json(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        {"error": "provider_unavailable"},
                        send_body=send_body,
                        cache_control="no-store",
                        noindex=True,
                    )
                    return
                if payload is None:
                    self._send_json(
                        HTTPStatus.NOT_FOUND,
                        {"error": "provider_not_found"},
                        send_body=send_body,
                        cache_control="no-store",
                        noindex=True,
                    )
                    return
                self._send_json(
                    HTTPStatus.OK,
                    payload,
                    send_body=send_body,
                    cache_control="no-store",
                    noindex=True,
                )
                return
            try:
                session = {**session, "admin_review_summary": service.admin_review_summary()}
            except Exception:
                LOGGER.exception("admin review summary failed")
                session = {**session, "admin_review_summary": {
                    "installationIssues": 0,
                    "identityPending": 0,
                    "readyToPublish": 0,
                    "total": 0,
                }}
            if request_path in {"/admin/providers", "/admin/providers/"}:
                try:
                    body = providers_page(service.admin_providers(), session, csrf_token)
                except Exception:
                    LOGGER.exception("admin provider page failed")
                    self._send_json(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        {"error": "providers_unavailable"},
                        send_body=send_body,
                        cache_control="no-store",
                        noindex=True,
                    )
                    return
                self._send_admin_html(body, send_body=send_body)
                return
            if request_path in {"/admin/map-statistics", "/admin/map-statistics/"}:
                query = parse_qs(urlsplit(self.path).query, keep_blank_values=True)
                selected_filters = {
                    key: values[-1]
                    for key, values in query.items()
                    if values and values[-1]
                }
                try:
                    statistics = service.map_statistics(selected_filters)
                    provider_payload = service.admin_providers()
                    body = map_statistics_page(
                        statistics,
                        provider_payload.get("providers", []),
                        session,
                        csrf_token,
                        selected_filters=selected_filters,
                    )
                except MapEventValidationError as exc:
                    self._send_json(
                        HTTPStatus.BAD_REQUEST,
                        {"error": str(exc)},
                        send_body=send_body,
                        cache_control="no-store",
                        noindex=True,
                    )
                    return
                except Exception:
                    LOGGER.exception("admin map statistics page failed")
                    self._send_json(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        {"error": "map_statistics_unavailable"},
                        send_body=send_body,
                        cache_control="no-store",
                        noindex=True,
                    )
                    return
                self._send_admin_html(body, send_body=send_body)
                return
            provider_page_match = re.fullmatch(
                r"/admin/providers/([a-z0-9][a-z0-9._-]{0,159})",
                request_path,
            )
            if provider_page_match:
                provider_id = provider_page_match.group(1)
                try:
                    detail = service.admin_provider_detail(provider_id)
                    if detail is None:
                        self._send_json(
                            HTTPStatus.NOT_FOUND,
                            {"error": "provider_not_found"},
                            send_body=send_body,
                            cache_control="no-store",
                            noindex=True,
                        )
                        return
                    runs_payload = service.provider_runs(provider_id) or {}
                    audits = service.database.audit_rows(provider_id)
                    body = provider_detail_page(
                        detail,
                        runs_payload.get("runs", []),
                        audits,
                        session,
                        csrf_token,
                    )
                except Exception:
                    LOGGER.exception("admin provider detail page failed")
                    self._send_json(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        {"error": "provider_unavailable"},
                        send_body=send_body,
                        cache_control="no-store",
                        noindex=True,
                    )
                    return
                self._send_admin_html(body, send_body=send_body)
                return
            if request_path in {"/admin/diagnostics", "/admin/diagnostics/"}:
                query = parse_qs(urlsplit(self.path).query, keep_blank_values=True)
                identity = query.get("identity", [""])[0].strip()
                canonical_device_id = query.get("canonical_device_id", [""])[0].strip()
                if not identity:
                    self._redirect("/admin", send_body=send_body)
                    return
                try:
                    statistics = service.compatibility_statistics()
                    identity_devices = service.admin_devices().get("devices", [])
                    if not canonical_device_id:
                        matching_statistic = next((
                            row for row in statistics
                            if str(row.get("compatibility_identity") or row.get("model") or "").strip() == identity
                            and row.get("canonical_device_model_id")
                        ), None)
                        canonical_device_id = str(
                            (matching_statistic or {}).get("canonical_device_model_id") or ""
                        )
                    if canonical_device_id:
                        state = query.get("state", [""])[0].strip()
                        if state not in {"", "all", "succeeded", "failed", "open", "resolved-errors"}:
                            state = ""
                        target = f"/admin/devices/{canonical_device_id}?from=installations"
                        if state:
                            target += f"&state={state}"
                        self._redirect(target + "#installations", send_body=send_body)
                        return
                    body = diagnostics_page(
                        statistics,
                        session,
                        csrf_token,
                        identity=identity,
                        operations=service.compatibility_operation_details(),
                        resolved_operations=service.compatibility_resolved_operation_details(),
                        identity_devices=identity_devices,
                        canonical_device_model_id=canonical_device_id,
                    )
                except Exception:
                    LOGGER.exception("compatibility diagnostics failed")
                    self._send_json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "diagnostics_unavailable"}, send_body=send_body, cache_control="no-store")
                    return
                self._send_admin_html(body, send_body=send_body)
                return
            if request_path in {"/admin", "/admin/"}:
                try:
                    body = dashboard_page(
                        service.compatibility_statistics(), session, csrf_token,
                        operations=service.compatibility_operation_details(),
                        resolved_operations=service.compatibility_resolved_operation_details(),
                        public_stats_enabled=service.public_compatibility_stats_enabled,
                    )
                except Exception:
                    LOGGER.exception("compatibility statistics failed")
                    self._send_json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "statistics_unavailable"}, send_body=send_body, cache_control="no-store")
                    return
                self._send_admin_html(body, send_body=send_body)
                return
            if request_path.startswith("/admin/devices/") and request_path != "/admin/devices/":
                device_id = unquote(request_path.removeprefix("/admin/devices/")).strip()
                if not device_id or "/" in device_id:
                    self._send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"}, send_body=send_body, cache_control="no-store")
                    return
                try:
                    payload = service.admin_devices()
                    device = next(
                        (item for item in payload.get("devices", []) if str(item.get("id")) == device_id),
                        None,
                    )
                    if device is None:
                        self._send_json(HTTPStatus.NOT_FOUND, {"error": "device_not_found"}, send_body=send_body, cache_control="no-store")
                        return
                    query = parse_qs(urlsplit(self.path).query, keep_blank_values=True)
                    origin = query.get("from", ["devices"])[0]
                    body = device_detail_page(
                        device, session, csrf_token,
                        operations=service.compatibility_operation_details(),
                        resolved_operations=service.compatibility_resolved_operation_details(),
                        identity_devices=payload.get("devices", []),
                        origin="installations" if origin == "installations" else "devices",
                        requested_state=query.get("state", [""])[0].strip() or None,
                    )
                except Exception:
                    LOGGER.exception("admin device detail failed")
                    self._send_json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "admin_device_unavailable"}, send_body=send_body, cache_control="no-store")
                    return
                self._send_admin_html(body, send_body=send_body)
                return
            if request_path in {"/admin/devices", "/admin/devices/"}:
                try:
                    rows, sync = service.database.admin_device_snapshot()
                    body = devices_page(rows, sync, session, csrf_token)
                except Exception:
                    LOGGER.exception("admin device catalog failed")
                    self._send_json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "admin_devices_unavailable"}, send_body=send_body, cache_control="no-store")
                    return
                self._send_admin_html(body, send_body=send_body)
                return
            if request_path in {"/admin/devices.json", "/admin/devices.json/"}:
                try:
                    self._send_json(HTTPStatus.OK, service.admin_devices(), send_body=send_body, cache_control="no-store")
                except Exception:
                    LOGGER.exception("admin device API failed")
                    self._send_json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "admin_devices_unavailable"}, send_body=send_body, cache_control="no-store")
                return
            if request_path in {"/admin/campaign-links", "/admin/campaign-links/"}:
                self._send_admin_html(campaign_links_page(session, csrf_token), send_body=send_body)
                return
            if request_path == "/admin/account":
                self._send_admin_html(account_page(session, csrf_token), send_body=send_body)
                return
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"}, send_body=send_body, cache_control="no-store")

        def _handle_provider_post(self, request_path: str) -> None:
            match = re.fullmatch(
                r"/admin/providers/([a-z0-9][a-z0-9._-]{0,159})/(state|check|collect|retire)",
                request_path,
            )
            if not match:
                self._send_json(
                    HTTPStatus.NOT_FOUND,
                    {"error": "not_found"},
                    send_body=True,
                    cache_control="no-store",
                    noindex=True,
                )
                return
            provider_id, action = match.groups()
            session_token = self._session_cookie()
            session = service.admin_session(session_token)
            if not session:
                self._send_json(
                    HTTPStatus.UNAUTHORIZED,
                    {"error": "admin_session_required"},
                    send_body=True,
                    cache_control="no-store",
                    noindex=True,
                )
                return
            body = self._read_json(allow_empty=action in {"check", "collect", "retire"})
            if body is None:
                return
            csrf_token = (
                self.headers.get("X-CSRF-Token")
                or body.pop("csrfToken", None)
                or body.pop("csrf_token", None)
            )
            if not csrf_token or not service.csrf_valid(session, csrf_token):
                self._send_json(
                    HTTPStatus.FORBIDDEN,
                    {"error": "csrf_or_session_invalid"},
                    send_body=True,
                    cache_control="no-store",
                    noindex=True,
                )
                return
            rate_key = f"admin-provider:{action}:{provider_id}:{self.client_address[0]}"
            if action in {"check", "collect"} and self._rate_limited(
                rate_key, limit=5, window=60
            ):
                self._send_json(
                    HTTPStatus.TOO_MANY_REQUESTS,
                    {"error": "rate_limited"},
                    send_body=True,
                    cache_control="no-store",
                    noindex=True,
                )
                return
            request_id = self._request_id()
            if action in {"check", "collect"}:
                request_times[rate_key].append(time.monotonic())
            try:
                if action == "state":
                    if not set(body).issubset({"status", "reason"}) or "status" not in body or not isinstance(body.get("status"), str):
                        raise ValueError("invalid_provider_status")
                    reason = body.get("reason")
                    if reason is not None and (not isinstance(reason, str) or len(reason.strip()) > 500):
                        raise ValueError("invalid_provider_reason")
                    result = service.set_provider_status(
                        provider_id,
                        body["status"].upper(),
                        admin_user_id=int(session["id"]),
                        request_id=request_id,
                        reason=reason.strip() if isinstance(reason, str) and reason.strip() else None,
                    )
                    if result is None:
                        raise LookupError("provider_not_found")
                elif action == "check":
                    if body:
                        raise ValueError("invalid_check_payload")
                    result = service.check_provider(
                        provider_id,
                        admin_user_id=int(session["id"]),
                        request_id=request_id,
                    )
                elif action == "retire":
                    if set(body) - {"reason"}:
                        raise ValueError("invalid_retire_payload")
                    reason = body.get("reason")
                    if reason is not None and (not isinstance(reason, str) or len(reason.strip()) > 500):
                        raise ValueError("invalid_provider_reason")
                    result = service.set_provider_status(
                        provider_id,
                        "RETIRED",
                        admin_user_id=int(session["id"]),
                        request_id=request_id,
                        reason=reason.strip() if isinstance(reason, str) and reason.strip() else None,
                    )
                    if result is None:
                        raise LookupError("provider_not_found")
                else:
                    if body:
                        raise ValueError("invalid_collect_payload")
                    result = service.collect_provider(
                        provider_id,
                        admin_user_id=int(session["id"]),
                        request_id=request_id,
                    )
            except ProviderActivationBlocked as exc:
                self._send_json(
                    HTTPStatus.CONFLICT,
                    {
                        "error": "provider_activation_blocked",
                        "activationGate": exc.gate,
                    },
                    send_body=True,
                    cache_control="no-store",
                    noindex=True,
                )
                return
            except LookupError as exc:
                self._send_json(
                    HTTPStatus.NOT_FOUND,
                    {"error": str(exc)},
                    send_body=True,
                    cache_control="no-store",
                    noindex=True,
                )
                return
            except ValueError as exc:
                self._send_json(
                    HTTPStatus.BAD_REQUEST,
                    {"error": str(exc)},
                    send_body=True,
                    cache_control="no-store",
                    noindex=True,
                )
                return
            except Exception:
                LOGGER.exception("admin provider action failed")
                self._send_json(
                    HTTPStatus.SERVICE_UNAVAILABLE,
                    {"error": "provider_action_unavailable"},
                    send_body=True,
                    cache_control="no-store",
                    noindex=True,
                )
                return
            self._send_json(
                HTTPStatus.OK,
                {"status": "ok", "result": result},
                send_body=True,
                cache_control="no-store",
                noindex=True,
            )

        def _handle_admin_post(self, request_path: str) -> None:
            form = self._read_form()
            if form is None:
                return
            if request_path == "/admin/setup":
                self._admin_setup(form)
                return
            if request_path == "/admin/login":
                self._admin_login(form)
                return
            session_token = self._session_cookie()
            session = service.admin_session(session_token)
            csrf_token = form.get("csrf_token")
            if not session or not service.csrf_valid(session, csrf_token):
                self._send_json(HTTPStatus.FORBIDDEN, {"error": "csrf_or_session_invalid"}, send_body=True, cache_control="no-store")
                return
            if request_path == "/admin/logout":
                service.logout_admin(session_token)
                self._redirect("/admin/login", send_body=True, clear_cookie=True)
                return
            if request_path == "/admin/account":
                try:
                    updated = service.update_admin_account(
                        session,
                        form.get("username", ""),
                        form.get("current_password", ""),
                        form.get("new_password", ""),
                        form.get("new_password_confirmation", ""),
                    )
                except AdminValidationError as exc:
                    body = account_page(session, self._csrf_cookie() or "", error=str(exc))
                    self._send_admin_html(body, send_body=True, status=HTTPStatus.BAD_REQUEST)
                    return
                body = account_page(updated, self._csrf_cookie() or "", success="Account details updated.")
                self._send_admin_html(body, send_body=True)
                return
            if request_path in {"/admin/devices/support", "/admin/devices/authorization"}:
                try:
                    device_id = form.get("device_id", "").strip()
                    support_status = form.get("support_status", "").strip().upper()
                    if not device_id or support_status not in {"SUPPORTED", "UNSUPPORTED", "NOT_EVALUATED"}:
                        raise ValueError("invalid installation authorization")
                    updated = service.update_device_authorization(
                        device_id,
                        support_status,
                        admin_user_id=int(session["id"]),
                        reason=form.get("reason", "").strip() or None,
                        note=form.get("note", "").strip() or None,
                    )
                    if not updated:
                        self._send_json(HTTPStatus.NOT_FOUND, {"error": "device_not_found"}, send_body=True, cache_control="no-store")
                        return
                except ValueError:
                    self._send_json(HTTPStatus.BAD_REQUEST, {"error": "invalid_installation_authorization"}, send_body=True, cache_control="no-store")
                    return
                self._redirect(
                    self._safe_admin_return(form.get("return_to"), "/admin/devices"),
                    send_body=True,
                )
                return
            if request_path == "/admin/devices/public-compatibility":
                try:
                    device_id = form.get("device_id", "").strip()
                    action = form.get("publication_action", "").strip().upper()
                    if not device_id or action not in {"PUBLISH", "UNPUBLISH"}:
                        raise ValueError("invalid public compatibility review")
                    updated = service.update_public_compatibility_review(
                        device_id,
                        action=action,
                        admin_user_id=int(session["id"]),
                        note=form.get("note", "").strip() or None,
                    )
                    if not updated:
                        self._send_json(HTTPStatus.NOT_FOUND, {"error": "device_not_found"}, send_body=True, cache_control="no-store")
                        return
                except ValueError:
                    self._send_json(HTTPStatus.BAD_REQUEST, {"error": "invalid_public_compatibility_review"}, send_body=True, cache_control="no-store")
                    return
                self._redirect(
                    self._safe_admin_return(form.get("return_to"), "/admin/devices"),
                    send_body=True,
                )
                return
            if request_path in {"/admin/diagnostics/resolve", "/admin/diagnostics/reopen"}:
                try:
                    operation_key = form.get("operation_key", "").strip()
                    is_resolve = request_path.endswith("/resolve")
                    linked_issue = _normalise_github_issue_reference(form.get("linked_github_issue", ""))
                    changed = service.update_diagnostic_lifecycle(
                        operation_key,
                        new_status="RESOLVED" if is_resolve else "ACTIVE",
                        admin_user_id=int(session["id"]),
                        resolution_reason=form.get("resolution_reason", "").strip() or None,
                        resolution_note=form.get("resolution_note", "").strip() or None,
                        linked_github_issue=linked_issue,
                    )
                    if not changed:
                        self._send_json(HTTPStatus.NOT_FOUND, {"error": "diagnostic_not_found"}, send_body=True, cache_control="no-store")
                        return
                except ValueError:
                    self._send_json(HTTPStatus.BAD_REQUEST, {"error": "invalid_diagnostic_lifecycle"}, send_body=True, cache_control="no-store")
                    return
                self._redirect(self._safe_admin_return(form.get("return_to"), "/admin"), send_body=True)
                return
            if request_path == "/admin/diagnostics/issue":
                try:
                    issue = _normalise_github_issue_reference(form.get("linked_github_issue", ""))
                    changed = service.update_diagnostic_issue(
                        form.get("operation_key", "").strip(),
                        linked_github_issue=issue,
                        admin_user_id=int(session["id"]),
                    )
                    if not changed:
                        self._send_json(HTTPStatus.NOT_FOUND, {"error": "diagnostic_not_found"}, send_body=True, cache_control="no-store")
                        return
                except ValueError:
                    self._send_json(HTTPStatus.BAD_REQUEST, {"error": "invalid_github_issue"}, send_body=True, cache_control="no-store")
                    return
                self._redirect(self._safe_admin_return(form.get("return_to"), "/admin"), send_body=True)
                return
            if request_path == "/admin/diagnostics/identity":
                try:
                    changed = service.resolve_compatibility_identity(
                        form.get("operation_key", "").strip(),
                        action=form.get("identity_action", "").strip().upper(),
                        canonical_device_model_id=form.get("canonical_device_model_id", "").strip() or None,
                        admin_user_id=int(session["id"]),
                        reason=form.get("identity_reason", "").strip() or None,
                        note=form.get("identity_note", "").strip() or None,
                    )
                    if not changed:
                        self._send_json(HTTPStatus.NOT_FOUND, {"error": "diagnostic_not_found"}, send_body=True, cache_control="no-store")
                        return
                except ValueError:
                    self._send_json(HTTPStatus.BAD_REQUEST, {"error": "invalid_identity_resolution"}, send_body=True, cache_control="no-store")
                    return
                self._redirect(self._safe_admin_return(form.get("return_to"), "/admin"), send_body=True)
                return
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"}, send_body=True, cache_control="no-store")

        @staticmethod
        def _safe_admin_return(value: str | None, default: str) -> str:
            target = (value or "").strip()
            if (
                target.startswith("/admin/diagnostics")
                or re.fullmatch(
                    r"/admin/devices/[A-Za-z0-9._~-]+(?:\?[^#\s]*)?(?:#[-A-Za-z0-9._~]+)?",
                    target,
                )
            ) and "//" not in target:
                return target
            return default

        def _admin_setup(self, form: dict[str, str]) -> None:
            client = f"admin-setup:{self.client_address[0]}"
            if self._rate_limited(client, limit=10, window=900):
                self._send_json(HTTPStatus.TOO_MANY_REQUESTS, {"error": "rate_limited"}, send_body=True, cache_control="no-store")
                return
            if form.get("password") != form.get("password_confirmation"):
                self._send_admin_html(setup_page(error="Passwords do not match."), send_body=True, status=HTTPStatus.BAD_REQUEST)
                return
            try:
                service.setup_admin(form.get("username", ""), form.get("password", ""), form.get("bootstrap_secret", ""))
            except AdminValidationError as exc:
                request_times[client].append(time.monotonic())
                self._send_admin_html(setup_page(error=str(exc)), send_body=True, status=HTTPStatus.BAD_REQUEST)
                return
            request_times[client].clear()
            self._redirect("/admin/login", send_body=True)

        def _admin_login(self, form: dict[str, str]) -> None:
            client = f"admin-login:{self.client_address[0]}"
            if self._rate_limited(client, limit=10, window=900):
                self._send_json(HTTPStatus.TOO_MANY_REQUESTS, {"error": "rate_limited"}, send_body=True, cache_control="no-store")
                return
            try:
                session_token, csrf_token = service.login_admin(form.get("username", ""), form.get("password", ""))
            except AdminValidationError as exc:
                request_times[client].append(time.monotonic())
                self._send_admin_html(login_page(error=str(exc)), send_body=True, status=HTTPStatus.UNAUTHORIZED)
                return
            request_times[client].clear()
            self.send_response(HTTPStatus.SEE_OTHER)
            self.send_header("Location", "/admin")
            self._set_admin_cookies(session_token, csrf_token)
            self._admin_headers(content_length=0)
            self.end_headers()

        def _handle_public_statistics(self, *, send_body: bool) -> None:
            try:
                query = parse_qs(urlsplit(self.path).query)
                limit = max(1, min(500, int(query.get("limit", ["5"])[0])))
                rows = service.public_statistics(limit)
            except (ValueError, LookupError):
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"}, send_body=send_body, cache_control="no-store")
                return
            except Exception:
                LOGGER.exception("public compatibility statistics failed")
                self._send_json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "statistics_unavailable"}, send_body=send_body, cache_control="no-store")
                return
            models = [{
                "model": row["model"],
                "canonicalModel": row.get("canonical_model"),
                "compatibilityIdentity": row.get("compatibility_identity"),
                "variant": row.get("variant"),
                "caseSizeMm": row.get("case_size_mm"),
                "displayType": row.get("display_type"),
                "canonicalDeviceId": row.get("canonical_device_model_id"),
                "attemptedInstallations": int(row["attempted_install_count"]),
                "successfulInstallations": int(row["successful_install_count"]),
                "reconnectVerifiedInstallations": int(row.get("reconnect_verified_install_count") or 0),
                "failedInstallations": int(row["failed_install_count"]),
                "successRate": float(row["success_rate"]) if row.get("success_rate") is not None else None,
                "evidenceStatus": row["calculated_status"],
                "lastSuccessfulInstallation": row["last_success"].isoformat() if isinstance(row.get("last_success"), datetime) else row.get("last_success"),
                "lastEvidence": row["last_evidence"].isoformat() if isinstance(row.get("last_evidence"), datetime) else row.get("last_evidence"),
                "mapCapable": row.get("recognized_map_capable_evidence") is True,
            } for row in rows]
            self._send_json(HTTPStatus.OK, {"schemaVersion": 2, "generatedAt": datetime.now(timezone.utc).isoformat(), "models": models}, send_body=send_body, cache_control="public, max-age=300, stale-while-revalidate=3600")

        def _handle_public_models(self, *, send_body: bool) -> None:
            try:
                query = parse_qs(urlsplit(self.path).query)
                limit = max(1, min(500, int(query.get("limit", ["500"])[0])))
                rows = service.public_models(limit)
            except (ValueError, LookupError):
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"}, send_body=send_body, cache_control="no-store")
                return
            except Exception:
                LOGGER.exception("public compatibility model projection failed")
                self._send_json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "statistics_unavailable"}, send_body=send_body, cache_control="no-store")
                return

            models = []
            for row in rows:
                image = None
                asset_url = row.get("asset_url")
                if (
                    row.get("asset_status") == "AVAILABLE"
                    and isinstance(asset_url, str)
                    and asset_url.startswith(CONTROLLED_ASSET_PREFIX)
                    and isinstance(row.get("asset_storage_key"), str)
                    and public_asset_source(row) is not None
                ):
                    image = {
                        "url": asset_url,
                        "origin": "controlled",
                        "status": "AVAILABLE",
                        "scope": row.get("asset_scope") or "MODEL",
                    }
                if image is None:
                    source_image_url = _official_source_image_url(row.get("source_image_url"))
                    if source_image_url:
                        image = {"url": source_image_url, "origin": "garmin-source", "status": "SOURCE"}
                if image is None:
                    image = generic_fallback_image()
                models.append({
                    "model": row.get("model") or row.get("evidence_model"),
                    "canonicalModel": row.get("canonical_model") or row.get("evidence_model"),
                    "family": row.get("family") or "other",
                    "familyName": row.get("family_name") or row.get("family") or "Other",
                    "compatibilityIdentity": row.get("compatibility_identity"),
                    "variant": row.get("variant"),
                    "caseSizeMm": row.get("case_size_mm"),
                    "displayType": row.get("display_type"),
                    "canonicalDeviceId": row.get("canonical_device_model_id"),
                    "attemptedInstallations": int(row.get("attempted_install_count") or 0),
                    "successfulInstallations": int(row.get("successful_install_count") or 0),
                    "reconnectVerifiedInstallations": int(row.get("reconnect_verified_install_count") or 0),
                    "failedInstallations": int(row.get("failed_install_count") or 0),
                    "successRate": float(row["success_rate"]) if row.get("success_rate") is not None else None,
                    "evidenceStatus": row.get("calculated_status"),
                    "lastSuccessfulInstallation": row["last_success"].isoformat() if isinstance(row.get("last_success"), datetime) else row.get("last_success"),
                    "lastEvidence": row["last_evidence"].isoformat() if isinstance(row.get("last_evidence"), datetime) else row.get("last_evidence"),
                    "image": image,
                })
            self._send_json(
                HTTPStatus.OK,
                {"schemaVersion": 1, "generatedAt": datetime.now(timezone.utc).isoformat(), "models": models},
                send_body=send_body,
                cache_control="public, max-age=300, stale-while-revalidate=3600",
            )

        def _read_form(self) -> dict[str, str] | None:
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                length = 0
            if length <= 0 or length > 16_384:
                self._send_json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "invalid_size"}, send_body=True, cache_control="no-store")
                return None
            content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
            if content_type != "application/x-www-form-urlencoded":
                self._send_json(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, {"error": "invalid_content_type"}, send_body=True, cache_control="no-store")
                return None
            try:
                values = parse_qs(self.rfile.read(length).decode("utf-8"), keep_blank_values=True, max_num_fields=12)
            except (UnicodeDecodeError, ValueError):
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "invalid_form"}, send_body=True, cache_control="no-store")
                return None
            return {key: items[-1] for key, items in values.items()}

        def _read_json(self, *, allow_empty: bool = False) -> dict[str, Any] | None:
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                length = 0
            if length == 0 and allow_empty:
                return {}
            if length <= 0 or length > 16_384:
                self._send_json(
                    HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                    {"error": "invalid_size"},
                    send_body=True,
                    cache_control="no-store",
                    noindex=True,
                )
                return None
            content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
            if content_type != "application/json":
                self._send_json(
                    HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
                    {"error": "invalid_content_type"},
                    send_body=True,
                    cache_control="no-store",
                    noindex=True,
                )
                return None
            try:
                document = json.loads(self.rfile.read(length))
            except (UnicodeDecodeError, json.JSONDecodeError):
                self._send_json(
                    HTTPStatus.BAD_REQUEST,
                    {"error": "invalid_json"},
                    send_body=True,
                    cache_control="no-store",
                    noindex=True,
                )
                return None
            if not isinstance(document, dict):
                self._send_json(
                    HTTPStatus.BAD_REQUEST,
                    {"error": "invalid_json_object"},
                    send_body=True,
                    cache_control="no-store",
                    noindex=True,
                )
                return None
            return document

        def _request_id(self) -> str:
            candidate = self.headers.get("X-Request-Id", "").strip()
            if re.fullmatch(r"[A-Za-z0-9._:-]{1,120}", candidate):
                return candidate
            return str(uuid4())

        def _session_cookie(self) -> str | None:
            return self._cookie_value("terento_admin_session")

        def _csrf_cookie(self) -> str | None:
            return self._cookie_value("terento_admin_csrf")

        def _cookie_value(self, name: str) -> str | None:
            cookie = SimpleCookie()
            try:
                cookie.load(self.headers.get("Cookie", ""))
            except Exception:
                return None
            morsel = cookie.get(name)
            return morsel.value if morsel else None

        def _set_admin_cookies(self, session_token: str, csrf_token: str) -> None:
            attributes = f"Max-Age={service.admin_session_ttl_seconds}; Path=/admin; Secure; HttpOnly; SameSite=Strict"
            self.send_header("Set-Cookie", f"terento_admin_session={session_token}; {attributes}")
            self.send_header("Set-Cookie", f"terento_admin_csrf={csrf_token}; {attributes}")

        def _send_admin_html(
            self, body: bytes, *, send_body: bool, status: HTTPStatus = HTTPStatus.OK
        ) -> None:
            self.send_response(status)
            self._admin_headers(content_length=len(body), body=body)
            self.end_headers()
            if send_body:
                self.wfile.write(body)

        def _admin_headers(self, *, content_length: int, body: bytes = b"") -> None:
            self._common_headers(
                cache_control="no-store",
                content_type="text/html; charset=utf-8",
                content_length=content_length,
            )
            self.send_header("X-Robots-Tag", "noindex, nofollow")
            nonce_match = re.search(rb'<script nonce="([A-Za-z0-9_-]+)">', body)
            script_policy = f"script-src 'nonce-{nonce_match.group(1).decode('ascii')}'" if nonce_match else "script-src 'none'"
            self.send_header(
                "Content-Security-Policy",
                f"default-src 'none'; {script_policy}; connect-src 'self'; style-src 'unsafe-inline' https://terento.app; font-src https://terento.app; img-src https://terento.app https://api.terento.app https://res.garmin.com data:; form-action 'self'; base-uri 'none'; frame-ancestors 'none'",
            )
            self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")

        def _redirect(
            self, location: str, *, send_body: bool, clear_cookie: bool = False
        ) -> None:
            self.send_response(HTTPStatus.SEE_OTHER)
            self.send_header("Location", location)
            if clear_cookie:
                expired = "Max-Age=0; Path=/admin; Secure; HttpOnly; SameSite=Strict"
                self.send_header("Set-Cookie", f"terento_admin_session=; {expired}")
                self.send_header("Set-Cookie", f"terento_admin_csrf=; {expired}")
            self._admin_headers(content_length=0)
            self.end_headers()

        def _rate_limited(self, key: str, *, limit: int, window: int) -> bool:
            now = time.monotonic()
            recent = request_times[key]
            while recent and recent[0] < now - window:
                recent.popleft()
            return len(recent) >= limit

        def _handle_asset(self, request_path: str, *, send_body: bool) -> None:
            try:
                asset = service.asset_response(request_path)
            except Exception:  # pragma: no cover - filesystem/deployment failure
                LOGGER.exception("asset response generation failed")
                asset = None
            if asset is None:
                self._send_json(
                    HTTPStatus.NOT_FOUND,
                    {"error": "asset_not_found"},
                    send_body=send_body,
                    cache_control="no-store",
                )
                return

            body, sha256, content_type = asset
            etag = f'"{sha256}"'
            if _not_modified(self.headers.get("If-None-Match"), etag):
                self.send_response(HTTPStatus.NOT_MODIFIED)
                self._common_headers(
                    cache_control="public, max-age=31536000, immutable",
                    content_type=content_type,
                    etag=etag,
                )
                self.end_headers()
                return
            self.send_response(HTTPStatus.OK)
            self._common_headers(
                cache_control="public, max-age=31536000, immutable",
                content_type=content_type,
                content_length=len(body),
                etag=etag,
            )
            self.end_headers()
            if send_body:
                self.wfile.write(body)

        def _handle_health(self, *, send_body: bool) -> None:
            try:
                service.health()
            except Exception:  # pragma: no cover - database availability is deployment state
                LOGGER.exception("catalog health check failed")
                self._send_json(
                    HTTPStatus.SERVICE_UNAVAILABLE,
                    {"status": "error"},
                    send_body=send_body,
                    cache_control="no-store",
                )
                return
            self._send_json(
                HTTPStatus.OK,
                {"status": "ok"},
                send_body=send_body,
                cache_control="no-store",
            )

        def _handle_catalog(
            self,
            response_factory: Any,
            *,
            send_body: bool,
            unavailable_error: str,
        ) -> None:
            try:
                body, etag, updated_at = response_factory()
            except Exception:  # pragma: no cover - database availability is deployment state
                LOGGER.exception("catalog response generation failed")
                self._send_json(
                    HTTPStatus.SERVICE_UNAVAILABLE,
                    {"error": unavailable_error},
                    send_body=send_body,
                    cache_control="no-store",
                )
                return

            last_modified = _http_date(updated_at)
            etag_header = self.headers.get("If-None-Match")
            not_modified = (
                _not_modified(etag_header, etag)
                if etag_header
                else _not_modified_since(
                    self.headers.get("If-Modified-Since"), updated_at
                )
            )
            if not_modified:
                self.send_response(HTTPStatus.NOT_MODIFIED)
                self._common_headers(
                    cache_control="public, max-age=300, stale-while-revalidate=86400",
                    etag=etag,
                    last_modified=last_modified,
                )
                self.end_headers()
                return

            self.send_response(HTTPStatus.OK)
            self._common_headers(
                cache_control="public, max-age=300, stale-while-revalidate=86400",
                etag=etag,
                last_modified=last_modified,
                content_type="application/json; charset=utf-8",
                content_length=len(body),
            )
            self.end_headers()
            if send_body:
                self.wfile.write(body)

        def _send_json(
            self,
            status: HTTPStatus,
            document: Any,
            *,
            send_body: bool,
            cache_control: str,
            noindex: bool = False,
        ) -> None:
            body = json.dumps(document, default=_format_json_value, separators=(",", ":")).encode("utf-8")
            self.send_response(status)
            self._common_headers(
                cache_control=cache_control,
                content_type="application/json; charset=utf-8",
                content_length=len(body),
            )
            if noindex:
                self.send_header("X-Robots-Tag", "noindex, nofollow")
            self.end_headers()
            if send_body:
                self.wfile.write(body)

        def _common_headers(
            self,
            *,
            cache_control: str,
            content_type: str = "application/json; charset=utf-8",
            content_length: int | None = None,
            etag: str | None = None,
            last_modified: str | None = None,
        ) -> None:
            self.send_header("Content-Type", content_type)
            if content_length is not None:
                self.send_header("Content-Length", str(content_length))
            self.send_header("Cache-Control", cache_control)
            if etag is not None:
                self.send_header("ETag", etag)
            if last_modified is not None:
                self.send_header("Last-Modified", last_modified)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")

        def log_message(self, format: str, *args: Any) -> None:
            LOGGER.info("%s - %s", self.address_string(), format % args)

    return Handler


def _provider_activation_gate(
    provider_id: str,
    detail: dict[str, Any],
    runs: list[dict[str, Any]],
) -> dict[str, Any]:
    """Return the evidence required before a known provider may be activated."""

    health = detail.get("health") if isinstance(detail.get("health"), dict) else {}
    latest_run = runs[0] if runs else {}
    packages = [
        package
        for package in detail.get("packages", [])
        if str(package.get("availability") or "").upper() != "RETIRED"
    ]
    expected_package_count = 177 if provider_id == "opentopomap" else None
    latest_package_count = _non_negative_int(latest_run.get("package_count"))
    latest_artifact_count = _non_negative_int(latest_run.get("artifact_count"))
    catalog_package_count = len(packages)
    available_package_count = sum(
        1 for package in packages
        if str(package.get("availability") or "").upper() == "AVAILABLE"
    )
    broken_artifact_count = sum(
        _non_negative_int(package.get("broken_artifact_count"))
        for package in packages
    )
    unvalidated_artifact_count = sum(
        _non_negative_int(package.get("unvalidated_artifact_count"))
        for package in packages
    )
    missing_main_artifact_count = sum(
        1
        for package in packages
        if _non_negative_int(package.get("main_artifact_count")) < 1
    )

    blockers: list[dict[str, str]] = []

    def block(code: str, message: str) -> None:
        blockers.append({"code": code, "message": message})

    health_status = str(health.get("status") or "UNKNOWN").upper()
    if health_status != "HEALTHY":
        block("health_not_healthy", f"Latest provider health is {health_status}, not HEALTHY.")
    if detail.get("last_catalog_sync") is None:
        block("catalog_not_synced", "No successful catalog sync is recorded.")

    collection_status = str(latest_run.get("status") or "NONE").upper()
    if collection_status != "SUCCEEDED":
        block("catalog_collection_not_succeeded", "No successful catalog collection is recorded.")
    if latest_package_count < 1 or latest_artifact_count < 1:
        block("catalog_collection_empty", "The latest successful collection has no packages and artifacts.")
    if expected_package_count is not None:
        if latest_package_count != expected_package_count:
            block(
                "catalog_package_count_mismatch",
                f"The latest collection has {latest_package_count} packages; {expected_package_count} are required.",
            )
        if latest_artifact_count != expected_package_count:
            block(
                "catalog_artifact_count_mismatch",
                f"The latest collection has {latest_artifact_count} artifacts; {expected_package_count} are required.",
            )
    if catalog_package_count != latest_package_count:
        block(
            "catalog_snapshot_incomplete",
            f"The stored catalog has {catalog_package_count} current packages; the latest collection has {latest_package_count}.",
        )
    if available_package_count != catalog_package_count:
        block("packages_not_available", "Every current package must be AVAILABLE.")
    if broken_artifact_count:
        block("broken_artifacts", f"{broken_artifact_count} broken artifact(s) remain.")
    if unvalidated_artifact_count:
        block("unvalidated_artifacts", f"{unvalidated_artifact_count} artifact(s) are not VALIDATED.")
    if missing_main_artifact_count:
        block("missing_main_artifacts", f"{missing_main_artifact_count} package(s) have no validated main artifact.")

    return {
        "canActivate": not blockers,
        "blockers": blockers,
        "expectedPackageCount": expected_package_count,
        "latestHealthStatus": health_status,
        "latestCollectionStatus": collection_status,
        "latestCollectionPackageCount": latest_package_count,
        "latestCollectionArtifactCount": latest_artifact_count,
        "catalogPackageCount": catalog_package_count,
        "availablePackageCount": available_package_count,
        "brokenArtifactCount": broken_artifact_count,
        "unvalidatedArtifactCount": unvalidated_artifact_count,
        "missingMainArtifactCount": missing_main_artifact_count,
        "lastCatalogSync": _format_json_value(detail.get("last_catalog_sync")),
    }


def _non_negative_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _provider_summary_payload(
    definition: Any,
    row: dict[str, Any],
) -> dict[str, Any]:
    provider_id = str(row.get("provider_id") or getattr(definition, "id", ""))
    package_count = row.get("active_package_count")
    if package_count is None and row.get("packages") is not None:
        package_count = sum(
            1
            for package in row.get("packages", [])
            if package.get("availability") == "AVAILABLE"
        )
    return {
        "id": provider_id,
        "name": row.get("provider_name") or getattr(definition, "name", provider_id),
        "adapterId": row.get("adapter_id") or getattr(definition, "adapter_id", provider_id),
        "status": row.get("status") or getattr(definition, "default_status", "ACTIVE"),
        "health": row.get("health") or "UNKNOWN",
        "website": row.get("website") or getattr(definition, "website", None),
        "license": row.get("license_information") or getattr(definition, "license", None),
        "attribution": row.get("attribution") or getattr(definition, "attribution", None),
        "licenseUrl": row.get("license_url") or getattr(definition, "license_url", None),
        "lastCatalogSync": _format_json_value(row.get("last_catalog_sync")),
        "lastHealthCheck": _format_json_value(row.get("last_checked_at")),
        "lastDownloadTest": _format_json_value(row.get("last_checked_at")),
        "lastHealthError": row.get("last_error"),
        "packageCount": int(package_count or 0),
        "brokenPackageCount": int(row.get("broken_package_count") or 0),
        "brokenUrlCount": int(row.get("broken_url_count") or 0),
    }


def _provider_detail_payload(
    definition: Any,
    detail: dict[str, Any],
) -> dict[str, Any]:
    payload = _provider_summary_payload(definition, detail)
    payload["sources"] = _format_json_value(detail.get("sources") or [])
    payload["maps"] = _format_json_value(detail.get("packages") or [])
    latest_health = detail.get("health") or {}
    payload["health"] = _format_json_value(latest_health)
    payload["healthStatus"] = latest_health.get("status") if isinstance(latest_health, dict) else "UNKNOWN"
    payload["lastHealthCheck"] = _format_json_value(latest_health.get("checked_at")) if isinstance(latest_health, dict) else None
    payload["lastDownloadTest"] = payload["lastHealthCheck"]
    payload["healthHistory"] = _format_json_value(detail.get("health_history") or [])
    return {"schemaVersion": 1, "provider": payload}


def _format_json_value(value: Any) -> Any:
    if isinstance(value, datetime):
        normalized = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return normalized.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    if hasattr(value, "isoformat") and not isinstance(value, (str, bytes)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _format_json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_format_json_value(item) for item in value]
    return value


def serve(service: CatalogService, host: str, port: int) -> None:
    server = ThreadingHTTPServer((host, port), make_handler(service))
    LOGGER.info("catalog API listening on %s:%d", host, port)
    try:
        server.serve_forever()
    finally:
        server.server_close()


def _http_date(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return format_datetime(value.astimezone(timezone.utc), usegmt=True)


def _not_modified(header: str | None, etag: str) -> bool:
    if not header:
        return False
    return any(item.strip() in (etag, "*") for item in header.split(","))


def _not_modified_since(header: str | None, updated_at: datetime) -> bool:
    if not header:
        return False
    try:
        requested = parsedate_to_datetime(header)
    except (TypeError, ValueError, IndexError, OverflowError):
        return False
    if requested.tzinfo is None:
        requested = requested.replace(tzinfo=timezone.utc)
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=timezone.utc)
    return updated_at.astimezone(timezone.utc).replace(microsecond=0) <= requested
