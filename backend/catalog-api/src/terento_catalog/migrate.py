from __future__ import annotations

import argparse
import re
from pathlib import Path

from .config import Settings
from .db import Database, migration_directory


def apply_migrations(
    database: Database, directory: Path | None = None, *, target: str | None = None
) -> list[str]:
    if target not in (None, "062"):
        raise RuntimeError("only the exact --target 062 is supported")

    migration_path = directory or migration_directory()
    files = [
        file
        for file in sorted(migration_path.glob("*.sql"))
        if not file.name.startswith("._")
    ]
    if not files:
        raise RuntimeError(f"no SQL migrations found in {migration_path}")

    validate_migration_versions(files)
    if target == "062":
        expected_files = [f"{version:03d}" for version in range(1, 63)]
        actual_files = [_migration_version(file) for file in files]
        if actual_files != expected_files:
            raise RuntimeError(
                "--target 062 requires exactly one canonical migration file "
                "for every version 001 through 062, with no later files"
            )

    with database.connection() as connection:
        if target == "062":
            # Serialize competing migrators without locking application tables.
            # The target path must never create a missing history ledger.
            connection.execute("LOCK TABLE schema_migrations IN SHARE ROW EXCLUSIVE MODE")
        else:
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
        if target == "062":
            expected_applied = set(expected_files[:-1])
            if applied == expected_applied | {"062"}:
                return []
            if applied != expected_applied:
                raise RuntimeError(
                    "--target 062 requires the exact applied ledger 001 through "
                    "061; 060-only, aliases, holes, and later versions are rejected"
                )
            files = [files[-1]]

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


def validate_migration_versions(files: list[Path]) -> None:
    seen: dict[str, Path] = {}
    for file in files:
        version = _migration_version(file)
        # Numeric aliases such as 044 and 44 are also ambiguous.
        key = str(int(version))
        if key in seen:
            raise RuntimeError(f"duplicate migration version {version}: {seen[key].name}, {file.name}")
        seen[key] = file


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


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Apply Terento catalog SQL migrations")
    parser.add_argument("--target", choices=("062",), help="apply only migration 062")
    args = parser.parse_args(argv)
    settings = Settings.from_env()
    database = Database(
        settings.database_url,
        connect_timeout_seconds=settings.database_connect_timeout_seconds,
    )
    installed = apply_migrations(database, target=args.target)
    print("Applied migrations: " + (", ".join(installed) if installed else "none"))


if __name__ == "__main__":
    main()
