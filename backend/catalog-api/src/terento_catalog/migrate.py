from __future__ import annotations

import re
from pathlib import Path

from .config import Settings
from .db import Database, migration_directory


def apply_migrations(database: Database, directory: Path | None = None) -> list[str]:
    migration_path = directory or migration_directory()
    files = [
        file
        for file in sorted(migration_path.glob("*.sql"))
        if not file.name.startswith("._")
    ]
    if not files:
        raise RuntimeError(f"no SQL migrations found in {migration_path}")

    with database.connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version TEXT PRIMARY KEY,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        applied = {
            row["version"]
            for row in connection.execute(
                "SELECT version FROM schema_migrations"
            ).fetchall()
        }
        installed: list[str] = []
        for file in files:
            version = _migration_version(file)
            if version in applied:
                continue
            for statement in _statements(file.read_text(encoding="utf-8")):
                connection.execute(statement)
            connection.execute(
                "INSERT INTO schema_migrations (version) VALUES (%s)",
                (version,),
            )
            installed.append(version)
    return installed


def _migration_version(path: Path) -> str:
    match = re.match(r"^(\d+)_.*\.sql$", path.name)
    if not match:
        raise RuntimeError(f"migration filename must start with a number: {path.name}")
    return match.group(1)


def _statements(sql: str) -> list[str]:
    """Split SQL statements without treating semicolons in quoted text as delimiters."""

    statements: list[str] = []
    current: list[str] = []
    in_single_quote = False
    in_double_quote = False
    in_line_comment = False
    in_block_comment = False
    index = 0

    while index < len(sql):
        char = sql[index]
        next_char = sql[index + 1] if index + 1 < len(sql) else ""

        if in_line_comment:
            current.append(char)
            if char == "\n":
                in_line_comment = False
            index += 1
            continue

        if in_block_comment:
            current.append(char)
            if char == "*" and next_char == "/":
                current.append(next_char)
                in_block_comment = False
                index += 2
            else:
                index += 1
            continue

        if in_single_quote:
            current.append(char)
            if char == "'":
                if next_char == "'":
                    current.append(next_char)
                    index += 2
                    continue
                in_single_quote = False
            index += 1
            continue

        if in_double_quote:
            current.append(char)
            if char == '"':
                if next_char == '"':
                    current.append(next_char)
                    index += 2
                    continue
                in_double_quote = False
            index += 1
            continue

        if char == "-" and next_char == "-":
            current.extend((char, next_char))
            in_line_comment = True
            index += 2
            continue

        if char == "/" and next_char == "*":
            current.extend((char, next_char))
            in_block_comment = True
            index += 2
            continue

        if char == "'":
            in_single_quote = True
            current.append(char)
            index += 1
            continue

        if char == '"':
            in_double_quote = True
            current.append(char)
            index += 1
            continue

        if char == ";":
            statement = "".join(current).strip()
            if statement:
                statements.append(statement)
            current = []
        else:
            current.append(char)
        index += 1

    statement = "".join(current).strip()
    if statement:
        statements.append(statement)
    return statements


def main() -> None:
    settings = Settings.from_env()
    database = Database(
        settings.database_url,
        connect_timeout_seconds=settings.database_connect_timeout_seconds,
    )
    installed = apply_migrations(database)
    print("Applied migrations: " + (", ".join(installed) if installed else "none"))


if __name__ == "__main__":
    main()
