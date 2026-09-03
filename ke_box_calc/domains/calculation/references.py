from __future__ import annotations

from ke_box_calc.db.connection import get_connection


def get_active_references() -> dict:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT reference_code, version, status, payload, source
            FROM calculation_reference_versions
            WHERE valid_to IS NULL
            ORDER BY reference_code
            """
        ).fetchall()
    return {
        row["reference_code"]: {
            "version": row["version"],
            "status": row["status"],
            "payload": row["payload"],
            "source": row["source"],
        }
        for row in rows
    }
