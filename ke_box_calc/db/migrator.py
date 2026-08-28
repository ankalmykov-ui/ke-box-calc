from __future__ import annotations

import argparse
import hashlib
from dataclasses import dataclass
from pathlib import Path

from ke_box_calc.db.connection import get_connection

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"
UP_MARKER = "-- migrate:up"
DOWN_MARKER = "-- migrate:down"
LOCK_KEY = 42002002


@dataclass(frozen=True)
class Migration:
    version: str
    path: Path
    up_sql: str
    down_sql: str
    checksum: str


def load_migrations() -> list[Migration]:
    migrations: list[Migration] = []
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        text = path.read_text(encoding="utf-8")
        if UP_MARKER not in text or DOWN_MARKER not in text:
            raise ValueError(f"Migration {path.name} must contain up and down markers")
        _, body = text.split(UP_MARKER, 1)
        up_sql, down_sql = body.split(DOWN_MARKER, 1)
        migrations.append(
            Migration(
                version=path.stem,
                path=path,
                up_sql=up_sql.strip(),
                down_sql=down_sql.strip(),
                checksum=hashlib.sha256(up_sql.strip().encode()).hexdigest(),
            )
        )
    return migrations


def _ensure_registry(connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            checksum TEXT NOT NULL,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )


def migration_status() -> list[dict]:
    migrations = load_migrations()
    with get_connection() as connection, connection.transaction():
        _ensure_registry(connection)
        applied = {
            row["version"]: row["checksum"]
            for row in connection.execute(
                "SELECT version, checksum FROM schema_migrations ORDER BY version"
            ).fetchall()
        }
    return [
        {
            "version": migration.version,
            "applied": migration.version in applied,
            "checksum_valid": applied.get(migration.version, migration.checksum)
            == migration.checksum,
        }
        for migration in migrations
    ]


def migrate_up() -> list[str]:
    applied_now: list[str] = []
    with get_connection() as connection, connection.transaction():
        connection.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK_KEY,))
        _ensure_registry(connection)
        rows = connection.execute(
            "SELECT version, checksum FROM schema_migrations"
        ).fetchall()
        applied = {row["version"]: row["checksum"] for row in rows}
        for migration in load_migrations():
            if migration.version in applied:
                if applied[migration.version] != migration.checksum:
                    raise RuntimeError(f"Checksum mismatch for {migration.version}")
                continue
            connection.execute(migration.up_sql)
            connection.execute(
                "INSERT INTO schema_migrations(version, checksum) VALUES (%s, %s)",
                (migration.version, migration.checksum),
            )
            applied_now.append(migration.version)
    return applied_now


def migrate_down() -> str | None:
    migrations = {migration.version: migration for migration in load_migrations()}
    with get_connection() as connection, connection.transaction():
        connection.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK_KEY,))
        _ensure_registry(connection)
        row = connection.execute(
            "SELECT version FROM schema_migrations ORDER BY version DESC LIMIT 1"
        ).fetchone()
        if not row:
            return None
        version = row["version"]
        migration = migrations.get(version)
        if migration is None:
            raise RuntimeError(f"Applied migration {version} is not present in the repository")
        connection.execute(migration.down_sql)
        connection.execute("DELETE FROM schema_migrations WHERE version = %s", (version,))
        return version


def main() -> None:
    parser = argparse.ArgumentParser(description="KE BOX CALC schema migration runner")
    parser.add_argument("command", choices=("up", "down", "status"))
    args = parser.parse_args()
    if args.command == "up":
        print({"applied": migrate_up()})
    elif args.command == "down":
        print({"rolled_back": migrate_down()})
    else:
        print({"migrations": migration_status()})


if __name__ == "__main__":
    main()
