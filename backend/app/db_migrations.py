from __future__ import annotations

import hashlib
from pathlib import Path

from .db import DatabaseNotConfigured, get_conn


MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"


class MigrationError(RuntimeError):
    pass


def migration_files() -> list[Path]:
    return sorted(MIGRATIONS_DIR.glob("[0-9][0-9][0-9][0-9]_*.sql"))


def _checksum(sql: str) -> str:
    return hashlib.sha256(sql.encode("utf-8")).hexdigest()


def apply_migrations() -> list[str]:
    files = migration_files()
    if not files:
        raise MigrationError(f"Миграции не найдены: {MIGRATIONS_DIR}")

    applied: list[str] = []
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version TEXT PRIMARY KEY,
                checksum TEXT NOT NULL,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        conn.commit()

        for path in files:
            version = path.stem
            sql = path.read_text(encoding="utf-8")
            checksum = _checksum(sql)
            existing = conn.execute(
                "SELECT checksum FROM schema_migrations WHERE version = %s",
                (version,),
            ).fetchone()
            if existing:
                if existing["checksum"] != checksum:
                    raise MigrationError(
                        f"Контрольная сумма применённой миграции изменилась: {version}"
                    )
                continue

            try:
                with conn.transaction():
                    conn.execute(sql, prepare=False)
                    conn.execute(
                        "INSERT INTO schema_migrations(version, checksum) VALUES (%s, %s)",
                        (version, checksum),
                    )
                applied.append(version)
            except Exception as exc:
                raise MigrationError(f"Не удалось применить миграцию {version}") from exc

    return applied


def main() -> int:
    try:
        applied = apply_migrations()
    except (DatabaseNotConfigured, MigrationError) as exc:
        print(f"migration_failed: {exc}")
        return 1

    if applied:
        print("migrations_applied: " + ", ".join(applied))
    else:
        print("migrations_applied: none (schema is current)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
