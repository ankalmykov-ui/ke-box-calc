from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from ke_box_calc.db.connection import get_connection


def list_materials() -> list[dict]:
    with get_connection() as connection:
        return connection.execute(
            """
            SELECT m.id, m.name, m.material_type, m.grammage_g_m2, m.width_mm,
                   m.manufacturer, m.classification_status,
                   COALESCE(SUM(sm.quantity_kg), 0) AS balance_kg,
                   p.price_rub_kg
            FROM materials m
            LEFT JOIN stock_movements sm ON sm.material_id = m.id
            LEFT JOIN material_price_versions p
              ON p.material_id = m.id AND p.valid_to IS NULL
            GROUP BY m.id, p.price_rub_kg
            ORDER BY m.material_type, m.grammage_g_m2, m.width_mm, m.name
            """
        ).fetchall()


def list_materials_for_calculation() -> list[dict]:
    with get_connection() as connection:
        return connection.execute(
            """
            SELECT m.id, m.name, m.material_type, m.grammage_g_m2, m.width_mm,
                   m.manufacturer, m.classification_status,
                   COALESCE(SUM(sm.quantity_kg), 0) AS balance_kg,
                   p.price_rub_kg
            FROM materials m
            LEFT JOIN stock_movements sm ON sm.material_id = m.id
            LEFT JOIN material_price_versions p
              ON p.material_id = m.id AND p.valid_to IS NULL
            WHERE m.classification_status <> 'rejected'
            GROUP BY m.id, p.price_rub_kg
            HAVING COALESCE(SUM(sm.quantity_kg), 0) > 0
            ORDER BY m.width_mm, m.material_type, m.grammage_g_m2, m.name
            """
        ).fetchall()


def get_materials_by_ids(material_ids: list[UUID]) -> list[dict]:
    with get_connection() as connection:
        return connection.execute(
            """
            SELECT m.id, m.name, m.grammage_g_m2, m.width_mm,
                   COALESCE(SUM(sm.quantity_kg), 0) AS balance_kg,
                   p.price_rub_kg
            FROM materials m
            LEFT JOIN stock_movements sm ON sm.material_id = m.id
            LEFT JOIN material_price_versions p
              ON p.material_id = m.id AND p.valid_to IS NULL
            WHERE m.id = ANY(%s)
            GROUP BY m.id, p.price_rub_kg
            """,
            (material_ids,),
        ).fetchall()


def add_material_with_balance(
    *,
    name: str,
    material_type: str,
    grammage_g_m2: Decimal,
    width_mm: int,
    manufacturer: str | None,
    quantity_kg: Decimal,
    price_rub_kg: Decimal | None,
    source_name: str,
) -> dict:
    with get_connection() as connection, connection.transaction():
        material = connection.execute(
            """
            INSERT INTO materials(name, material_type, grammage_g_m2, width_mm, manufacturer)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (name, width_mm) DO UPDATE SET
                material_type = EXCLUDED.material_type,
                grammage_g_m2 = EXCLUDED.grammage_g_m2,
                manufacturer = COALESCE(EXCLUDED.manufacturer, materials.manufacturer)
            RETURNING id, name, material_type, grammage_g_m2, width_mm,
                      manufacturer, classification_status
            """,
            (name, material_type, grammage_g_m2, width_mm, manufacturer),
        ).fetchone()
        document = connection.execute(
            """
            INSERT INTO stock_documents(document_type, status, source_name, posted_at)
            VALUES ('receipt', 'posted', %s, now()) RETURNING id
            """,
            (source_name,),
        ).fetchone()
        connection.execute(
            """
            INSERT INTO stock_movements(
                document_id, material_id, quantity_kg, unit_cost_rub_kg, movement_type
            ) VALUES (%s, %s, %s, %s, 'receipt')
            """,
            (document["id"], material["id"], quantity_kg, price_rub_kg),
        )
        if price_rub_kg is not None:
            connection.execute(
                "UPDATE material_price_versions SET valid_to = now() "
                "WHERE material_id = %s AND valid_to IS NULL",
                (material["id"],),
            )
            connection.execute(
                """
                INSERT INTO material_price_versions(material_id, price_rub_kg, source)
                VALUES (%s, %s, %s)
                """,
                (material["id"], price_rub_kg, source_name),
            )
        return dict(material)


def import_opening_balance(
    *,
    items: list[dict],
    source_name: str,
    source_checksum: str,
) -> dict:
    """Post one opening-balance document exactly once."""
    with get_connection() as connection, connection.transaction():
        document = connection.execute(
            """
            INSERT INTO stock_documents(
                document_type, status, source_name, source_checksum, posted_at
            )
            VALUES ('opening_balance', 'posted', %s, %s, now())
            ON CONFLICT (document_type, source_checksum) DO NOTHING
            RETURNING id
            """,
            (source_name, source_checksum),
        ).fetchone()
        if document is None:
            existing = connection.execute(
                """
                SELECT id FROM stock_documents
                WHERE document_type = 'opening_balance' AND source_checksum = %s
                """,
                (source_checksum,),
            ).fetchone()
            return {
                "status": "already_imported",
                "document_id": existing["id"],
                "items_imported": 0,
            }

        for item in items:
            material = connection.execute(
                """
                INSERT INTO materials(
                    name, material_type, grammage_g_m2, width_mm, manufacturer
                )
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (name, width_mm) DO UPDATE SET
                    material_type = EXCLUDED.material_type,
                    grammage_g_m2 = EXCLUDED.grammage_g_m2,
                    manufacturer = COALESCE(EXCLUDED.manufacturer, materials.manufacturer)
                RETURNING id
                """,
                (
                    item["name"],
                    item["material_type"],
                    item["grammage_g_m2"],
                    item["width_mm"],
                    item.get("manufacturer"),
                ),
            ).fetchone()
            connection.execute(
                """
                INSERT INTO stock_movements(
                    document_id, material_id, quantity_kg, unit_cost_rub_kg,
                    movement_type
                )
                VALUES (%s, %s, %s, %s, 'adjustment')
                """,
                (
                    document["id"],
                    material["id"],
                    item["quantity_kg"],
                    item.get("price_rub_kg"),
                ),
            )
            price = item.get("price_rub_kg")
            if price is not None:
                connection.execute(
                    """
                    UPDATE material_price_versions SET valid_to = now()
                    WHERE material_id = %s AND valid_to IS NULL
                    """,
                    (material["id"],),
                )
                connection.execute(
                    """
                    INSERT INTO material_price_versions(material_id, price_rub_kg, source)
                    VALUES (%s, %s, %s)
                    """,
                    (material["id"], price, source_name),
                )

        return {
            "status": "imported",
            "document_id": document["id"],
            "items_imported": len(items),
        }
