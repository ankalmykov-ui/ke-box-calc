from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from psycopg.types.json import Jsonb

from ..db import get_conn
from .models import (
    MaterialCreate,
    MaterialPriceInput,
    OrganizationCreate,
    ReceiptCreate,
    ReversalCreate,
    SiteCreate,
    WarehouseCreate,
    WriteoffConfirm,
)


class WarehouseError(RuntimeError):
    pass


class WarehouseNotFound(WarehouseError):
    pass


class WarehouseConflict(WarehouseError):
    pass


class InsufficientStock(WarehouseConflict):
    pass


def _one(conn, sql: str, params: tuple = ()) -> dict:
    row = conn.execute(sql, params).fetchone()
    if not row:
        raise WarehouseNotFound("Запись не найдена")
    return row


def _lock(conn, key: str) -> None:
    conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (key,))


def _warehouse_context(conn, warehouse_id: UUID) -> dict:
    return _one(
        conn,
        """
        SELECT w.id AS warehouse_id, s.id AS site_id, s.organization_id
        FROM warehouses w
        JOIN sites s ON s.id = w.site_id
        WHERE w.id = %s AND w.is_active AND s.is_active
        """,
        (warehouse_id,),
    )


def _insert_material_price(
    conn,
    *,
    organization_id: UUID,
    material_id: UUID,
    req: MaterialPriceInput,
) -> dict:
    price = conn.execute(
        """
        INSERT INTO material_price_history(
            material_id, unit_code, currency_code, price_per_unit,
            valid_from, valid_to, source_name
        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING *
        """,
        (
            material_id,
            req.unit_code.strip().lower(),
            req.currency_code.strip().upper(),
            req.price_per_unit,
            req.valid_from,
            req.valid_to,
            req.source_name,
        ),
    ).fetchone()
    conn.execute(
        """
        INSERT INTO audit_log(
            organization_id, actor, action, entity_type, entity_id, after_data
        ) VALUES (%s, %s, 'material.price.recorded', 'material_price', %s, %s)
        """,
        (
            organization_id,
            req.recorded_by,
            price["id"],
            Jsonb(
                {
                    "material_id": str(material_id),
                    "unit_code": req.unit_code.strip().lower(),
                    "currency_code": req.currency_code.strip().upper(),
                    "price_per_unit": str(req.price_per_unit),
                    "valid_from": req.valid_from.isoformat(),
                    "source_name": req.source_name,
                }
            ),
        ),
    )
    return price


def _document_payload(conn, document_id: UUID, *, replay: bool = False) -> dict:
    document = _one(
        conn,
        """
        SELECT id, organization_id, warehouse_id, document_type, status,
               idempotency_key, source_system, source_reference, reason,
               created_by, created_at, posted_at, reversal_of_document_id, snapshot
        FROM stock_documents
        WHERE id = %s
        """,
        (document_id,),
    )
    document["lines"] = conn.execute(
        """
        SELECT id, material_id, lot_id, roll_id, movement_kind, quantity,
               unit_code, base_quantity_kg, unit_price, currency_code, source_line_no
        FROM stock_movements
        WHERE document_id = %s
        ORDER BY source_line_no
        """,
        (document_id,),
    ).fetchall()
    document["idempotent_replay"] = replay
    return document


def create_organization(req: OrganizationCreate) -> dict:
    with get_conn() as conn, conn.transaction():
        try:
            return conn.execute(
                """
                INSERT INTO organizations(code, name)
                VALUES (%s, %s)
                RETURNING id, code, name, is_active, created_at
                """,
                (req.code.strip(), req.name.strip()),
            ).fetchone()
        except Exception as exc:
            if getattr(exc, "sqlstate", None) == "23505":
                raise WarehouseConflict("Организация с таким кодом уже существует") from exc
            raise


def list_organizations(*, code: str | None = None) -> list[dict]:
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT id, code, name, is_active, created_at
            FROM organizations
            WHERE (%s::text IS NULL OR code = %s::text)
            ORDER BY name, code
            """,
            (code, code),
        ).fetchall()


def create_site(req: SiteCreate) -> dict:
    with get_conn() as conn, conn.transaction():
        try:
            return conn.execute(
                """
                INSERT INTO sites(organization_id, code, name)
                VALUES (%s, %s, %s)
                RETURNING id, organization_id, code, name, is_active, created_at
                """,
                (req.organization_id, req.code.strip(), req.name.strip()),
            ).fetchone()
        except Exception as exc:
            if getattr(exc, "sqlstate", None) == "23505":
                raise WarehouseConflict("Площадка с таким кодом уже существует") from exc
            if getattr(exc, "sqlstate", None) == "23503":
                raise WarehouseNotFound("Организация не найдена") from exc
            raise


def create_warehouse(req: WarehouseCreate) -> dict:
    with get_conn() as conn, conn.transaction():
        try:
            return conn.execute(
                """
                INSERT INTO warehouses(site_id, code, name)
                VALUES (%s, %s, %s)
                RETURNING id, site_id, code, name, is_active, created_at
                """,
                (req.site_id, req.code.strip(), req.name.strip()),
            ).fetchone()
        except Exception as exc:
            if getattr(exc, "sqlstate", None) == "23505":
                raise WarehouseConflict("Склад с таким кодом уже существует") from exc
            if getattr(exc, "sqlstate", None) == "23503":
                raise WarehouseNotFound("Площадка не найдена") from exc
            raise


def create_material(req: MaterialCreate) -> dict:
    with get_conn() as conn, conn.transaction():
        try:
            material = conn.execute(
                """
                INSERT INTO materials(
                    organization_id, code, name, technological_designation,
                    material_type, gsm, color, surface_type, manufacturer, supplier,
                    procurement_status, classification_status, source_name, valid_from
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s
                )
                RETURNING *
                """,
                (
                    req.organization_id,
                    req.code.strip(),
                    req.name.strip(),
                    req.technological_designation,
                    req.material_type,
                    req.gsm,
                    req.color,
                    req.surface_type,
                    req.manufacturer,
                    req.supplier,
                    req.procurement_status,
                    req.classification_status,
                    req.source_name,
                    req.valid_from,
                ),
            ).fetchone()

            for identifier in req.external_identifiers:
                conn.execute(
                    """
                    INSERT INTO material_external_identifiers(
                        organization_id, material_id, source_system,
                        external_code, external_variant
                    ) VALUES (%s, %s, %s, %s, %s)
                    """,
                    (
                        req.organization_id,
                        material["id"],
                        identifier.source_system,
                        identifier.external_code,
                        identifier.external_variant,
                    ),
                )

            for width in req.widths:
                conn.execute(
                    """
                    INSERT INTO material_widths(
                        material_id, width_mm, status, valid_from, source_name
                    ) VALUES (%s, %s, %s, %s, %s)
                    """,
                    (
                        material["id"],
                        width.width_mm,
                        width.status,
                        width.valid_from,
                        width.source_name,
                    ),
                )

            prices = [
                _insert_material_price(
                    conn,
                    organization_id=req.organization_id,
                    material_id=material["id"],
                    req=price,
                )
                for price in req.prices
            ]

            material["external_identifiers"] = [x.model_dump() for x in req.external_identifiers]
            material["widths"] = [x.model_dump() for x in req.widths]
            material["prices"] = prices
            return material
        except Exception as exc:
            if getattr(exc, "sqlstate", None) == "23505":
                raise WarehouseConflict("Материал или внешний идентификатор уже существует") from exc
            if getattr(exc, "sqlstate", None) == "23503":
                raise WarehouseNotFound("Организация не найдена") from exc
            raise


def list_materials(organization_id: UUID, *, include_inactive: bool = False) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT m.*,
                   COALESCE((
                       SELECT jsonb_agg(jsonb_build_object(
                           'source_system', mei.source_system,
                           'external_code', mei.external_code,
                           'external_variant', mei.external_variant
                       ) ORDER BY mei.created_at)
                       FROM material_external_identifiers mei
                       WHERE mei.material_id = m.id
                   ), '[]'::jsonb) AS external_identifiers,
                   COALESCE((
                       SELECT jsonb_agg(jsonb_build_object(
                           'width_mm', mw.width_mm,
                           'status', mw.status,
                           'valid_from', mw.valid_from
                       ) ORDER BY mw.width_mm, mw.valid_from DESC)
                       FROM material_widths mw
                       WHERE mw.material_id = m.id
                   ), '[]'::jsonb) AS widths,
                   (
                       SELECT jsonb_build_object(
                           'id', mph.id,
                           'unit_code', mph.unit_code,
                           'currency_code', mph.currency_code,
                           'price_per_unit', mph.price_per_unit,
                           'valid_from', mph.valid_from,
                           'source_name', mph.source_name
                       )
                       FROM material_price_history mph
                       WHERE mph.material_id = m.id
                         AND mph.valid_from <= now()
                         AND (mph.valid_to IS NULL OR mph.valid_to >= now())
                       ORDER BY mph.valid_from DESC, mph.created_at DESC
                       LIMIT 1
                   ) AS latest_price
            FROM materials m
            WHERE m.organization_id = %s AND (%s OR m.is_active)
            ORDER BY m.name, m.gsm, m.code
            """,
            (organization_id, include_inactive),
        ).fetchall()
        return rows


def record_material_price(material_id: UUID, req: MaterialPriceInput) -> dict:
    with get_conn() as conn, conn.transaction():
        material = _one(
            conn,
            """
            SELECT id, organization_id
            FROM materials
            WHERE id = %s AND is_active
            """,
            (material_id,),
        )
        return _insert_material_price(
            conn,
            organization_id=material["organization_id"],
            material_id=material_id,
            req=req,
        )


def create_receipt(req: ReceiptCreate) -> dict:
    with get_conn() as conn, conn.transaction():
        context = _warehouse_context(conn, req.warehouse_id)
        idempotency_lock = f"stock-doc:{context['organization_id']}:{req.idempotency_key}"
        _lock(conn, idempotency_lock)
        existing = conn.execute(
            """
            SELECT id, document_type FROM stock_documents
            WHERE organization_id = %s AND idempotency_key = %s
            """,
            (context["organization_id"], req.idempotency_key),
        ).fetchone()
        if existing:
            if existing["document_type"] != "receipt":
                raise WarehouseConflict("Ключ идемпотентности уже использован другим документом")
            return _document_payload(conn, existing["id"], replay=True)

        document = conn.execute(
            """
            INSERT INTO stock_documents(
                organization_id, warehouse_id, document_type, status,
                idempotency_key, source_system, source_reference, reason,
                created_by, posted_at, snapshot
            )
            VALUES (%s, %s, 'receipt', 'posted', %s, %s, %s, %s, %s, now(), %s)
            RETURNING id
            """,
            (
                context["organization_id"],
                req.warehouse_id,
                req.idempotency_key,
                req.source_system,
                req.source_reference,
                req.reason,
                req.created_by,
                Jsonb(req.model_dump(mode="json")),
            ),
        ).fetchone()

        for line_no, line in enumerate(req.lines, start=1):
            material = _one(
                conn,
                "SELECT id FROM materials WHERE id = %s AND organization_id = %s AND is_active",
                (line.material_id, context["organization_id"]),
            )
            lot = conn.execute(
                """
                INSERT INTO material_lots(warehouse_id, material_id, lot_code, received_at)
                VALUES (%s, %s, %s, now())
                ON CONFLICT (warehouse_id, material_id, lot_code)
                DO UPDATE SET status = material_lots.status
                RETURNING id
                """,
                (req.warehouse_id, material["id"], line.lot_code),
            ).fetchone()

            roll_id = None
            if line.roll_code:
                roll = conn.execute(
                    """
                    INSERT INTO material_rolls(lot_id, roll_code, width_mm)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (lot_id, roll_code)
                    DO NOTHING
                    RETURNING id, width_mm
                    """,
                    (lot["id"], line.roll_code, line.width_mm),
                ).fetchone()
                if not roll:
                    existing_roll = conn.execute(
                        """
                        SELECT id, width_mm
                        FROM material_rolls
                        WHERE lot_id = %s AND roll_code = %s
                        """,
                        (lot["id"], line.roll_code),
                    ).fetchone()
                    raise WarehouseConflict(
                        "Рулон уже зарегистрирован поступлением: "
                        f"{line.roll_code}, ширина {existing_roll['width_mm']} мм"
                    )
                roll_id = roll["id"]

            conn.execute(
                """
                INSERT INTO stock_movements(
                    document_id, warehouse_id, material_id, lot_id, roll_id,
                    movement_kind, quantity, unit_code, base_quantity_kg,
                    unit_price, currency_code, source_line_no
                )
                VALUES (%s, %s, %s, %s, %s, 'receipt', %s, %s, %s, %s, %s, %s)
                """,
                (
                    document["id"],
                    req.warehouse_id,
                    line.material_id,
                    lot["id"],
                    roll_id,
                    line.quantity,
                    line.unit_code,
                    line.base_quantity_kg,
                    line.unit_price,
                    line.currency_code.upper(),
                    line_no,
                ),
            )

        conn.execute(
            """
            INSERT INTO audit_log(
                organization_id, actor, action, entity_type, entity_id, reason, after_data
            ) VALUES (%s, %s, 'stock.receipt.posted', 'stock_document', %s, %s, %s)
            """,
            (
                context["organization_id"],
                req.created_by,
                document["id"],
                req.reason,
                Jsonb({"line_count": len(req.lines)}),
            ),
        )
        return _document_payload(conn, document["id"])


def _position_balance(conn, warehouse_id: UUID, material_id: UUID, lot_id: UUID, roll_id: UUID | None) -> Decimal:
    row = conn.execute(
        """
        SELECT COALESCE(SUM(base_quantity_kg), 0) AS balance_kg
        FROM stock_movements
        WHERE warehouse_id = %s
          AND material_id = %s
          AND lot_id = %s
          AND roll_id IS NOT DISTINCT FROM %s
        """,
        (warehouse_id, material_id, lot_id, roll_id),
    ).fetchone()
    return Decimal(row["balance_kg"])


def confirm_writeoff(req: WriteoffConfirm) -> dict:
    with get_conn() as conn, conn.transaction():
        context = _warehouse_context(conn, req.warehouse_id)
        idempotency_lock = f"stock-doc:{context['organization_id']}:{req.idempotency_key}"
        _lock(conn, idempotency_lock)
        existing = conn.execute(
            """
            SELECT id, document_type FROM stock_documents
            WHERE organization_id = %s AND idempotency_key = %s
            """,
            (context["organization_id"], req.idempotency_key),
        ).fetchone()
        if existing:
            if existing["document_type"] != "writeoff":
                raise WarehouseConflict("Ключ идемпотентности уже использован другим документом")
            return _document_payload(conn, existing["id"], replay=True)

        indexed_lines = list(enumerate(req.lines, start=1))
        lock_keys = sorted(
            {
                f"stock:{req.warehouse_id}:{line.material_id}:{line.lot_id}:{line.roll_id or '-'}"
                for _, line in indexed_lines
            }
        )
        for key in lock_keys:
            _lock(conn, key)

        requested_by_position: dict[tuple, Decimal] = {}
        for _, line in indexed_lines:
            lot = _one(
                conn,
                """
                SELECT ml.id
                FROM material_lots ml
                JOIN materials m ON m.id = ml.material_id
                WHERE ml.id = %s AND ml.warehouse_id = %s
                  AND ml.material_id = %s AND m.organization_id = %s
                """,
                (line.lot_id, req.warehouse_id, line.material_id, context["organization_id"]),
            )
            if line.roll_id:
                _one(
                    conn,
                    "SELECT id FROM material_rolls WHERE id = %s AND lot_id = %s",
                    (line.roll_id, lot["id"]),
                )
            key = (line.material_id, line.lot_id, line.roll_id)
            requested_by_position[key] = requested_by_position.get(key, Decimal("0")) + Decimal(
                line.base_quantity_kg
            )

        balances_before: dict[str, str] = {}
        for (material_id, lot_id, roll_id), requested_kg in requested_by_position.items():
            balance = _position_balance(conn, req.warehouse_id, material_id, lot_id, roll_id)
            balances_before[f"{material_id}:{lot_id}:{roll_id or '-'}"] = str(balance)
            if balance < requested_kg:
                raise InsufficientStock(
                    f"Недостаточный остаток: доступно {balance} кг, требуется {requested_kg} кг"
                )

        request_snapshot: dict[str, Any] = req.model_dump(mode="json")
        request_snapshot["balances_before_kg"] = balances_before
        document = conn.execute(
            """
            INSERT INTO stock_documents(
                organization_id, warehouse_id, document_type, status,
                idempotency_key, source_system, reason, created_by, posted_at, snapshot
            )
            VALUES (%s, %s, 'writeoff', 'posted', %s, 'ke-box-calc', %s, %s, now(), %s)
            RETURNING id
            """,
            (
                context["organization_id"],
                req.warehouse_id,
                req.idempotency_key,
                req.reason,
                req.confirmed_by,
                Jsonb(request_snapshot),
            ),
        ).fetchone()

        for line_no, line in indexed_lines:
            conn.execute(
                """
                INSERT INTO stock_movements(
                    document_id, warehouse_id, material_id, lot_id, roll_id,
                    movement_kind, quantity, unit_code, base_quantity_kg,
                    unit_price, currency_code, source_line_no
                )
                VALUES (%s, %s, %s, %s, %s, 'writeoff', %s, %s, %s, %s, %s, %s)
                """,
                (
                    document["id"],
                    req.warehouse_id,
                    line.material_id,
                    line.lot_id,
                    line.roll_id,
                    -line.quantity,
                    line.unit_code,
                    -line.base_quantity_kg,
                    line.unit_price,
                    line.currency_code.upper(),
                    line_no,
                ),
            )

        conn.execute(
            """
            INSERT INTO writeoff_transactions(
                stock_document_id, order_reference, layout_variant_reference,
                calculation_snapshot_id, confirmed_by, request_snapshot
            ) VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                document["id"],
                req.order_reference,
                req.layout_variant_reference,
                req.calculation_snapshot_id,
                req.confirmed_by,
                Jsonb(request_snapshot),
            ),
        )
        conn.execute(
            """
            INSERT INTO audit_log(
                organization_id, actor, action, entity_type, entity_id, reason, after_data
            ) VALUES (%s, %s, 'stock.writeoff.confirmed', 'stock_document', %s, %s, %s)
            """,
            (
                context["organization_id"],
                req.confirmed_by,
                document["id"],
                req.reason,
                Jsonb({"line_count": len(req.lines), "balances_before_kg": balances_before}),
            ),
        )
        return _document_payload(conn, document["id"])


def reverse_writeoff(document_id: UUID, req: ReversalCreate) -> dict:
    with get_conn() as conn, conn.transaction():
        original = _one(
            conn,
            """
            SELECT * FROM stock_documents
            WHERE id = %s AND document_type = 'writeoff'
            """,
            (document_id,),
        )
        _lock(conn, f"stock-doc:{original['organization_id']}:{req.idempotency_key}")
        _lock(conn, f"stock-reversal:{document_id}")

        existing_key = conn.execute(
            """
            SELECT id, document_type, reversal_of_document_id FROM stock_documents
            WHERE organization_id = %s AND idempotency_key = %s
            """,
            (original["organization_id"], req.idempotency_key),
        ).fetchone()
        if existing_key:
            if (
                existing_key["document_type"] != "reversal"
                or existing_key["reversal_of_document_id"] != document_id
            ):
                raise WarehouseConflict("Ключ идемпотентности уже использован другим документом")
            return _document_payload(conn, existing_key["id"], replay=True)

        prior_reversal = conn.execute(
            "SELECT id FROM stock_documents WHERE reversal_of_document_id = %s",
            (document_id,),
        ).fetchone()
        if prior_reversal:
            raise WarehouseConflict("Списание уже сторнировано")
        if original["status"] != "posted":
            raise WarehouseConflict("Сторнировать можно только проведённое списание")

        movements = conn.execute(
            """
            SELECT * FROM stock_movements
            WHERE document_id = %s
            ORDER BY source_line_no
            """,
            (document_id,),
        ).fetchall()
        reversal = conn.execute(
            """
            INSERT INTO stock_documents(
                organization_id, warehouse_id, document_type, status,
                idempotency_key, source_system, reason, created_by, posted_at,
                reversal_of_document_id, snapshot
            )
            VALUES (%s, %s, 'reversal', 'posted', %s, 'ke-box-calc', %s, %s,
                    now(), %s, %s)
            RETURNING id
            """,
            (
                original["organization_id"],
                original["warehouse_id"],
                req.idempotency_key,
                req.reason,
                req.reversed_by,
                document_id,
                Jsonb(req.model_dump(mode="json")),
            ),
        ).fetchone()

        for movement in movements:
            conn.execute(
                """
                INSERT INTO stock_movements(
                    document_id, warehouse_id, material_id, lot_id, roll_id,
                    movement_kind, quantity, unit_code, base_quantity_kg,
                    unit_price, currency_code, source_line_no
                ) VALUES (%s, %s, %s, %s, %s, 'reversal', %s, %s, %s, %s, %s, %s)
                """,
                (
                    reversal["id"],
                    movement["warehouse_id"],
                    movement["material_id"],
                    movement["lot_id"],
                    movement["roll_id"],
                    -movement["quantity"],
                    movement["unit_code"],
                    -movement["base_quantity_kg"],
                    movement["unit_price"],
                    movement["currency_code"],
                    movement["source_line_no"],
                ),
            )

        conn.execute("UPDATE stock_documents SET status = 'reversed' WHERE id = %s", (document_id,))
        conn.execute(
            "UPDATE writeoff_transactions SET status = 'reversed' WHERE stock_document_id = %s",
            (document_id,),
        )
        conn.execute(
            """
            INSERT INTO audit_log(
                organization_id, actor, action, entity_type, entity_id, reason, after_data
            ) VALUES (%s, %s, 'stock.writeoff.reversed', 'stock_document', %s, %s, %s)
            """,
            (
                original["organization_id"],
                req.reversed_by,
                reversal["id"],
                req.reason,
                Jsonb({"reversal_of_document_id": str(document_id)}),
            ),
        )
        return _document_payload(conn, reversal["id"])


def list_balances(warehouse_id: UUID, *, include_zero: bool = False) -> list[dict]:
    with get_conn() as conn:
        _warehouse_context(conn, warehouse_id)
        return conn.execute(
            """
            SELECT sb.warehouse_id, sb.material_id, m.code AS material_code,
                   m.name AS material_name, m.gsm, sb.lot_id, ml.lot_code,
                   sb.roll_id, mr.roll_code, mr.width_mm, sb.balance_kg,
                   sb.last_movement_at
            FROM stock_balances sb
            JOIN materials m ON m.id = sb.material_id
            LEFT JOIN material_lots ml ON ml.id = sb.lot_id
            LEFT JOIN material_rolls mr ON mr.id = sb.roll_id
            WHERE sb.warehouse_id = %s AND (%s OR sb.balance_kg <> 0)
            ORDER BY m.name, ml.lot_code, mr.roll_code
            """,
            (warehouse_id, include_zero),
        ).fetchall()
