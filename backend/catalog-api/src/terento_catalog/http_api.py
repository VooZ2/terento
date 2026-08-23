from __future__ import annotations

import json
import logging
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

LOGGER = logging.getLogger(__name__)


class CatalogService:
    def __init__(
        self, database: Database, asset_storage: AssetStorage | None = None
    ) -> None:
        self.database = database
        self.asset_storage = asset_storage

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


def make_handler(service: CatalogService) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "TerentoCatalog"
        sys_version = ""

        def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
            self._handle_request(send_body=True)

        def do_HEAD(self) -> None:  # noqa: N802 - stdlib handler API
            self._handle_request(send_body=False)

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
            self._send_json(
                HTTPStatus.NOT_FOUND,
                {"error": "not_found"},
                send_body=send_body,
                cache_control="no-store",
            )

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
