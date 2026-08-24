from __future__ import annotations

import json
import logging
import base64
import hmac
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from email.utils import format_datetime, parsedate_to_datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlsplit

from .asset_storage import AssetStorage
from .catalog import build_catalog, catalog_etag, serialize_catalog
from .db import Database
from .device_catalog import (
    build_device_catalog,
    device_catalog_etag,
    serialize_device_catalog,
)
from .compatibility_evidence import EvidenceValidationError, operator_page, validate_event

LOGGER = logging.getLogger(__name__)


class CatalogService:
    def __init__(
        self, database: Database, asset_storage: AssetStorage | None = None,
        compatibility_admin_username: str | None = None,
        compatibility_admin_password: str | None = None,
    ) -> None:
        self.database = database
        self.asset_storage = asset_storage
        self.compatibility_admin_username = compatibility_admin_username
        self.compatibility_admin_password = compatibility_admin_password

    def health(self) -> bool:
        return self.database.health()

    def catalog_response(self) -> tuple[bytes, str, datetime]:
        rows, updated_at = self.database.catalog_snapshot()
        body = serialize_catalog(build_catalog(rows, updated_at))
        return body, catalog_etag(body), updated_at

    def device_catalog_response(self) -> tuple[bytes, str, datetime]:
        rows, updated_at = self.database.device_catalog_snapshot()
        body = serialize_device_catalog(build_device_catalog(rows, updated_at))
        return body, device_catalog_etag(body), updated_at

    def asset_response(self, request_path: str) -> tuple[bytes, str, str] | None:
        if self.asset_storage is None:
            return None
        return self.asset_storage.read_public_path(request_path)

    def receive_compatibility_event(self, body: bytes) -> bool:
        return self.database.insert_compatibility_event(validate_event(body))

    def compatibility_statistics(self) -> list[dict[str, Any]]:
        return self.database.compatibility_statistics()

    def operator_authorized(self, authorization: str | None) -> bool:
        if not self.compatibility_admin_username or not self.compatibility_admin_password or not authorization:
            return False
        try:
            scheme, encoded = authorization.split(" ", 1)
            username, password = base64.b64decode(encoded).decode().split(":", 1)
        except (ValueError, UnicodeDecodeError):
            return False
        return scheme.lower() == "basic" and hmac.compare_digest(username, self.compatibility_admin_username) and hmac.compare_digest(password, self.compatibility_admin_password)


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
            if request_path != "/compatibility/events":
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"}, send_body=True, cache_control="no-store")
                return
            self._handle_compatibility_event()

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
            if request_path == "/internal/compatibility/":
                self._handle_operator_page(send_body=send_body)
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

        def _handle_operator_page(self, *, send_body: bool) -> None:
            client = f"operator:{self.client_address[0]}"
            now = time.monotonic()
            recent = request_times[client]
            while recent and recent[0] < now - 300:
                recent.popleft()
            if len(recent) >= 10:
                self._send_json(HTTPStatus.TOO_MANY_REQUESTS, {"error": "rate_limited"}, send_body=send_body, cache_control="no-store")
                return
            if not service.operator_authorized(self.headers.get("Authorization")):
                recent.append(now)
                self.send_response(HTTPStatus.UNAUTHORIZED)
                self.send_header("WWW-Authenticate", 'Basic realm="Terento compatibility", charset="UTF-8"')
                self._common_headers(cache_control="no-store", content_length=0)
                self.send_header("X-Robots-Tag", "noindex, nofollow")
                self.end_headers()
                return
            recent.clear()
            try:
                body = operator_page(service.compatibility_statistics())
            except Exception:
                LOGGER.exception("compatibility statistics failed")
                self._send_json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "statistics_unavailable"}, send_body=send_body, cache_control="no-store")
                return
            self.send_response(HTTPStatus.OK)
            self._common_headers(cache_control="no-store", content_type="text/html; charset=utf-8", content_length=len(body))
            self.send_header("X-Robots-Tag", "noindex, nofollow")
            self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'none'")
            self.end_headers()
            if send_body:
                self.wfile.write(body)

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
            document: dict[str, Any],
            *,
            send_body: bool,
            cache_control: str,
        ) -> None:
            body = json.dumps(document, separators=(",", ":")).encode("utf-8")
            self.send_response(status)
            self._common_headers(
                cache_control=cache_control,
                content_type="application/json; charset=utf-8",
                content_length=len(body),
            )
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
