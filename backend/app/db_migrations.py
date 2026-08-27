from __future__ import annotations

import hashlib
import os
from pathlib import Path

from .db import DatabaseNotConfigured, get_conn


MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"
AUTO_APPLY_MIGRATIONS_ENV = "AUTO_APPLY_MIGRATIONS"
MIGRATION_LOCK_KEY = "ke-box-calc:schema-migrations"


class MigrationError(RuntimeError):
    pass


def migration_files() -> list[Path]:
    return sorted(MIGRATIONS_DIR.glob("[0-9][0-9][0-9][0-9]_*.sql"))


def _checksum(sql: str) -> str:
    return hashlib.sha256(sql.encode("utf-8")).hexdigest()


def should_apply_migrations_on_startup() -> bool:
    return os.getenv(AUTO_APPLY_MIGRATIONS_ENV, "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _lock_migrations(conn) -> None:
    # Transaction-scoped locks are safe with pooled Neon connections and make
    # concurrent serverless cold starts serialize before inspecting the ledger.
    conn.execute(
        "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
        (MIGRATION_LOCK_KEY,),
    )


def apply_migrations() -> list[str]:
    files = migration_files()
    if not files:
        raise MigrationError(f"Миграции не найдены: {MIGRATIONS_DIR}")

    applied: list[str] = []
    with get_conn() as conn:
        with conn.transaction():
            _lock_migrations(conn)
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version TEXT PRIMARY KEY,
                    checksum TEXT NOT NULL,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )

        for path in files:
            version = path.stem
            sql = path.read_text(encoding="utf-8")
            checksum = _checksum(sql)

            try:
                with conn.transaction():
                    _lock_migrations(conn)
                    existing = conn.execute(
                        "SELECT checksum FROM schema_migrations WHERE version = %s",
                        (version,),
                    ).fetchone()
                    if existing:
                        if existing["checksum"] != checksum:
                            raise MigrationError(
                                "Контрольная сумма применённой миграции изменилась: "
                                f"{version}"
                            )
                        continue

                    conn.execute(sql, prepare=False)
                    conn.execute(
                        "INSERT INTO schema_migrations(version, checksum) VALUES (%s, %s)",
                        (version, checksum),
                    )
                applied.append(version)
            except MigrationError:
                raise
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
