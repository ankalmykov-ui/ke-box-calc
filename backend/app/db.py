from __future__ import annotations

from contextlib import contextmanager
import os
from typing import Iterator

import psycopg
from psycopg.rows import dict_row


DATABASE_URL_ENV = "DATABASE_URL"
REQUIRED_SCHEMA_VERSION = "0003_v0_9_material_prices"


class DatabaseNotConfigured(RuntimeError):
    pass


def database_url() -> str | None:
    value = os.getenv(DATABASE_URL_ENV, "").strip()
    return value or None


@contextmanager
def get_conn() -> Iterator[psycopg.Connection]:
    """Open a short-lived PostgreSQL connection without evaluating env at import time."""
    url = database_url()
    if not url:
        raise DatabaseNotConfigured(
            "DATABASE_URL не настроен для этого окружения. Расчётные API доступны, "
            "но складские операции v0.9 отключены."
        )

    with psycopg.connect(
        url,
        row_factory=dict_row,
        connect_timeout=5,
        application_name="ke-box-calc-v0.9",
    ) as conn:
        yield conn


def schema_status() -> dict:
    """Return a safe readiness summary; never include connection details."""
    if not database_url():
        return {
            "status": "not_configured",
            "required_version": REQUIRED_SCHEMA_VERSION,
            "applied_versions": [],
        }

    try:
        with get_conn() as conn:
            exists = conn.execute(
                """
                SELECT to_regclass('public.schema_migrations') IS NOT NULL AS exists
                """
            ).fetchone()["exists"]
            if not exists:
                return {
                    "status": "migration_required",
                    "required_version": REQUIRED_SCHEMA_VERSION,
                    "applied_versions": [],
                }

            rows = conn.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            ).fetchall()
            versions = [row["version"] for row in rows]
            return {
                "status": "ready" if REQUIRED_SCHEMA_VERSION in versions else "migration_required",
                "required_version": REQUIRED_SCHEMA_VERSION,
                "applied_versions": versions,
            }
    except (psycopg.Error, OSError) as exc:
        return {
            "status": "unavailable",
            "required_version": REQUIRED_SCHEMA_VERSION,
            "applied_versions": [],
            "error_type": type(exc).__name__,
        }
