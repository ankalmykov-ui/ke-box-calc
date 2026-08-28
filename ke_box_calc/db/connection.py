from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row

from ke_box_calc.core.config import get_settings


class DatabaseNotConfigured(RuntimeError):
    pass


@contextmanager
def get_connection() -> Iterator[psycopg.Connection]:
    database_url = get_settings().database_url
    if not database_url:
        raise DatabaseNotConfigured("DATABASE_URL is not configured")
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        yield connection


def ping_database() -> bool:
    try:
        with get_connection() as connection:
            row = connection.execute("SELECT 1 AS ok").fetchone()
            return bool(row and row["ok"] == 1)
    except (DatabaseNotConfigured, psycopg.Error):
        return False

