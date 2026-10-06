"""Run production ``Database`` methods against PostgreSQL/WASM (PGlite).

The bridge applies every real catalog migration once per test process and
then executes the exact SQL produced by ``terento_catalog.db.Database``. Each
test runs inside one outer transaction that is rolled back afterwards, while
each ``Database.connection()`` maps to a savepoint, so production commit and
rollback boundaries are preserved without leaking state between tests.

When ``CI=true`` the PGlite module is mandatory: a missing module fails the
test instead of skipping it, so CI cannot silently lose PostgreSQL coverage.
"""
from __future__ import annotations

import atexit
import json
import os
import re
import subprocess
import threading
import unittest
import uuid
from contextlib import contextmanager
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterator

from terento_catalog.db import Database, migration_directory
from terento_catalog.migrate import _statements, migration_files

TESTS = Path(__file__).resolve().parent
_PLACEHOLDER = re.compile(r"%\(([A-Za-z_][A-Za-z0-9_]*)\)s|%s|%%")


def pglite_module_path() -> str | None:
    for name in ("PGLITE_MODULE_PATH", "TERENTO_PGLITE_MODULE"):
        value = os.environ.get(name)
        if value and Path(value).exists():
            return value
    return None


def require_pglite(testcase: unittest.TestCase) -> str:
    """Return the PGlite module path, skipping locally and failing in CI."""
    module = pglite_module_path()
    if module:
        return module
    message = "PGLITE_MODULE_PATH is required for PostgreSQL regression tests"
    if os.environ.get("CI", "").strip().lower() == "true":
        testcase.fail(message + " (CI=true: PostgreSQL regressions must not be skipped)")
    testcase.skipTest(message)
    raise AssertionError("unreachable")


def node_binary() -> str:
    return os.environ.get("TERENTO_NODE_BIN") or "node"


def _encode(value: Any) -> Any:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (uuid.UUID, Decimal)):
        return str(value)
    if isinstance(value, (list, tuple)):
        return [_encode(item) for item in value]
    return value


def _decode_value(value: Any) -> Any:
    if isinstance(value, dict):
        if set(value) == {"$date"}:
            return datetime.fromisoformat(value["$date"].replace("Z", "+00:00"))
        return {key: _decode_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_decode_value(item) for item in value]
    return value


def _decode(value: Any, type_id: int) -> Any:
    value = _decode_value(value)
    if value is None:
        return None
    if type_id == 1114 and isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if type_id == 1082 and isinstance(value, datetime):
        return value.date()
    if type_id == 1700:
        return Decimal(str(value))
    if type_id == 2950:
        return uuid.UUID(str(value))
    if type_id == 2951 and isinstance(value, list):
        return [uuid.UUID(str(item)) if item is not None else None for item in value]
    return value


def convert_query(sql: str, params: Any) -> tuple[str, list[Any]]:
    """Translate psycopg placeholders into PostgreSQL ``$n`` parameters."""
    if params is None:
        return sql, []
    names: dict[str, int] = {}
    ordered: list[Any] = []
    positional = iter(list(params) if not isinstance(params, dict) else [])

    def replace(match: re.Match[str]) -> str:
        token = match.group(0)
        if token == "%%":
            return "%"
        if match.group(1):
            name = match.group(1)
            if name not in names:
                ordered.append(params[name])
                names[name] = len(ordered)
            return f"${names[name]}"
        ordered.append(next(positional))
        return f"${len(ordered)}"

    return _PLACEHOLDER.sub(replace, sql), [_encode(value) for value in ordered]


class PGliteError(RuntimeError):
    def __init__(self, message: str, code: str | None = None) -> None:
        super().__init__(message)
        self.sqlstate = code


class PGliteServer:
    """One migrated PGlite process shared by all tests in this interpreter."""

    _instance: "PGliteServer | None" = None
    _lock = threading.Lock()

    def __init__(self, module: str) -> None:
        self.process = subprocess.Popen(
            [node_binary(), str(TESTS / "pglite_server.cjs"), module],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
        )
        self.savepoints = 0
        self.timings: list[tuple[str, float]] = []
        statements = [
            "CREATE TABLE schema_migrations (version TEXT PRIMARY KEY,"
            " applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
        ]
        for file in migration_files(migration_directory()):
            statements.extend(_statements(file.read_text(encoding="utf-8")))
            statements.append(f"INSERT INTO schema_migrations (version) VALUES ('{file.name[:3]}')")
        self.request({"op": "migrate", "statements": statements})

    @classmethod
    def shared(cls, module: str) -> "PGliteServer":
        with cls._lock:
            if cls._instance is None or cls._instance.process.poll() is not None:
                cls._instance = cls(module)
                atexit.register(cls._instance.close)
            return cls._instance

    def request(self, payload: dict[str, Any]) -> dict[str, Any]:
        assert self.process.stdin and self.process.stdout
        self.process.stdin.write(json.dumps(payload) + "\n")
        self.process.stdin.flush()
        line = self.process.stdout.readline()
        if not line:
            raise PGliteError("PGlite bridge exited unexpectedly")
        response = json.loads(line)
        if not response.get("ok"):
            raise PGliteError(response.get("error") or "PGlite error", response.get("code"))
        return response

    def exec(self, sql: str) -> None:
        self.request({"op": "exec", "sql": sql})

    def query(self, sql: str, params: Any = None) -> "PGliteCursor":
        text, values = convert_query(sql, params)
        response = self.request({"op": "query", "sql": text, "params": values})
        self.timings.append((text, float(response.get("elapsedMs") or 0)))
        fields = response.get("fields") or []
        rows = [
            {field["name"]: _decode(row.get(field["name"]), int(field["type"])) for field in fields}
            for row in response.get("rows") or []
        ]
        return PGliteCursor(rows, int(response.get("affectedRows") or 0))

    def close(self) -> None:
        if self.process.poll() is None:
            try:
                self.request({"op": "close"})
            except Exception:
                pass
            self.process.wait(timeout=10)


class PGliteCursor:
    def __init__(self, rows: list[dict[str, Any]], rowcount: int) -> None:
        self._rows = rows
        self.rowcount = rowcount if rowcount else len(rows)

    def fetchone(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None

    def fetchall(self) -> list[dict[str, Any]]:
        return list(self._rows)

    def __iter__(self) -> Iterator[dict[str, Any]]:
        return iter(self._rows)


class PGliteConnection:
    def __init__(self, server: PGliteServer) -> None:
        self.server = server

    def execute(self, sql: str, params: Any = None) -> PGliteCursor:
        return self.server.query(sql, params)


class PGliteDatabase(Database):
    """Production ``Database`` whose connections are PGlite savepoints."""

    def __init__(self, server: PGliteServer) -> None:
        super().__init__("pglite://test")
        self.server = server

    @contextmanager
    def connection(self) -> Iterator[Any]:
        self.server.savepoints += 1
        name = f"terento_test_sp_{self.server.savepoints}"
        self.server.exec(f"SAVEPOINT {name}")
        try:
            yield PGliteConnection(self.server)
        except BaseException:
            self.server.exec(f"ROLLBACK TO SAVEPOINT {name}")
            self.server.exec(f"RELEASE SAVEPOINT {name}")
            raise
        else:
            self.server.exec(f"RELEASE SAVEPOINT {name}")


class PGliteTestCase(unittest.TestCase):
    """Base class: each test runs in a rolled-back transaction on migrated PostgreSQL."""

    server: PGliteServer

    def setUp(self) -> None:
        super().setUp()
        module = require_pglite(self)
        self.server = PGliteServer.shared(module)
        self.server.exec("BEGIN")
        self.addCleanup(self.server.exec, "ROLLBACK")
        self.db = PGliteDatabase(self.server)

    def sql(self, statement: str, params: Any = None) -> list[dict[str, Any]]:
        return self.server.query(statement, params).fetchall()
