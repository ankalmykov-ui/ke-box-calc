from __future__ import annotations

import hashlib
import json
from uuid import UUID

from psycopg.types.json import Jsonb

from ..db import get_conn
from .models import (
    BctResultCreate,
    CompositionCreate,
    CompositionVersionInput,
    CostSnapshotCreate,
)


class CompositionError(RuntimeError):
    pass


class CompositionNotFound(CompositionError):
    pass


class CompositionConflict(CompositionError):
    pass


def _one(conn, sql: str, params: tuple = ()) -> dict:
    row = conn.execute(sql, params).fetchone()
    if not row:
        raise CompositionNotFound("Композиция или связанная запись не найдена")
    return row


def _lock(conn, key: str) -> None:
    conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (key,))


def _version_payload(conn, version_id: UUID) -> dict:
    version = _one(
        conn,
        """
        SELECT cv.*, cd.code, cd.name
        FROM composition_versions cv
        JOIN composition_definitions cd ON cd.id = cv.composition_definition_id
        WHERE cv.id = %s
        """,
        (version_id,),
    )
    version["layers"] = conn.execute(
        """
        SELECT layer_no, layer_role, material_id, material_code_snapshot,
               material_name_snapshot, gsm_snapshot, corrugation_coefficient
        FROM composition_layers
        WHERE composition_version_id = %s
        ORDER BY layer_no
        """,
        (version_id,),
    ).fetchall()
    return version


def _material_snapshots(conn, organization_id: UUID, req: CompositionVersionInput) -> list[dict]:
    snapshots: list[dict] = []
    for layer in sorted(req.layers, key=lambda item: item.layer_no):
        material = _one(
            conn,
            """
            SELECT id, code, name, gsm, classification_status, procurement_status
            FROM materials
            WHERE id = %s AND organization_id = %s AND is_active
            """,
            (layer.material_id, organization_id),
        )
        if req.status == "approved" and material["classification_status"] != "approved":
            raise CompositionConflict(
                f"Материал {material['code']} не классифицирован для утверждённой композиции"
            )
        if req.status == "approved" and material["procurement_status"] == "unavailable":
            raise CompositionConflict(
                f"Материал {material['code']} недоступен для утверждённой композиции"
            )
        snapshots.append(
            {
                "layer_no": layer.layer_no,
                "layer_role": layer.layer_role.strip(),
                "material_id": material["id"],
                "material_code": material["code"],
                "material_name": material["name"],
                "gsm": material["gsm"],
                "corrugation_coefficient": layer.corrugation_coefficient,
            }
        )
    return snapshots


def _signature(board_grade_code: str, profile_code: str, layers: list[dict]) -> str:
    canonical = {
        "board_grade_code": board_grade_code.strip().upper(),
        "profile_code": profile_code.strip().upper(),
        "layers": [
            {
                "layer_no": row["layer_no"],
                "layer_role": row["layer_role"],
                "material_id": str(row["material_id"]),
                "gsm": str(row["gsm"]),
                "corrugation_coefficient": str(row["corrugation_coefficient"]),
            }
            for row in layers
        ],
    }
    encoded = json.dumps(canonical, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _insert_version(
    conn,
    definition: dict,
    req: CompositionVersionInput,
) -> dict:
    _lock(conn, f"composition-version:{definition['id']}")
    previous = conn.execute(
        """
        SELECT id, version_no
        FROM composition_versions
        WHERE composition_definition_id = %s
        ORDER BY version_no DESC
        LIMIT 1
        """,
        (definition["id"],),
    ).fetchone()
    version_no = int(previous["version_no"]) + 1 if previous else 1
    layers = _material_snapshots(conn, definition["organization_id"], req)
    signature = _signature(req.board_grade_code, req.profile_code, layers)
    approved = req.status == "approved"

    version = conn.execute(
        """
        INSERT INTO composition_versions(
            organization_id, composition_definition_id, version_no,
            previous_version_id, board_grade_code, profile_code, layer_count,
            composition_signature, status, change_reason, created_by,
            approved_by, approved_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                CASE WHEN %s THEN now() ELSE NULL END)
        RETURNING id
        """,
        (
            definition["organization_id"],
            definition["id"],
            version_no,
            previous["id"] if previous else None,
            req.board_grade_code.strip().upper(),
            req.profile_code.strip().upper(),
            len(layers),
            signature,
            req.status,
            req.change_reason,
            req.created_by,
            req.approved_by if approved else None,
            approved,
        ),
    ).fetchone()

    for row in layers:
        conn.execute(
            """
            INSERT INTO composition_layers(
                organization_id, composition_version_id,
                layer_no, layer_role, material_id,
                material_code_snapshot, material_name_snapshot, gsm_snapshot,
                corrugation_coefficient
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                definition["organization_id"],
                version["id"],
                row["layer_no"],
                row["layer_role"],
                row["material_id"],
                row["material_code"],
                row["material_name"],
                row["gsm"],
                row["corrugation_coefficient"],
            ),
        )

    conn.execute(
        """
        INSERT INTO audit_log(
            organization_id, actor, action, entity_type, entity_id, reason, after_data
        ) VALUES (%s, %s, 'composition.version.created',
                  'composition_version', %s, %s, %s)
        """,
        (
            definition["organization_id"],
            req.created_by,
            version["id"],
            req.change_reason,
            Jsonb(
                {
                    "definition_id": str(definition["id"]),
                    "version_no": version_no,
                    "status": req.status,
                    "signature": signature,
                }
            ),
        ),
    )
    return _version_payload(conn, version["id"])


def create_composition(req: CompositionCreate) -> dict:
    with get_conn() as conn, conn.transaction():
        try:
            definition = conn.execute(
                """
                INSERT INTO composition_definitions(organization_id, code, name)
                VALUES (%s, %s, %s)
                RETURNING id, organization_id, code, name
                """,
                (req.organization_id, req.code.strip(), req.name.strip()),
            ).fetchone()
            return _insert_version(conn, definition, req)
        except Exception as exc:
            if isinstance(exc, CompositionError):
                raise
            if getattr(exc, "sqlstate", None) == "23505":
                raise CompositionConflict("Композиция с таким кодом уже существует") from exc
            if getattr(exc, "sqlstate", None) == "23503":
                raise CompositionNotFound("Организация или материал не найдены") from exc
            raise


def create_version(definition_id: UUID, req: CompositionVersionInput) -> dict:
    with get_conn() as conn, conn.transaction():
        definition = _one(
            conn,
            """
            SELECT id, organization_id, code, name
            FROM composition_definitions
            WHERE id = %s AND is_active
            """,
            (definition_id,),
        )
        return _insert_version(conn, definition, req)


def list_compositions(
    organization_id: UUID,
    *,
    board_grade_code: str | None = None,
    profile_code: str | None = None,
) -> list[dict]:
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT cd.id AS composition_id, cd.code, cd.name,
                   cv.id AS version_id, cv.version_no, cv.board_grade_code,
                   cv.profile_code, cv.layer_count, cv.status,
                   cv.composition_signature, cv.created_at,
                   layers.layers,
                   calc.bct_kn AS calculated_bct_kn,
                   calc.measured_at AS calculated_bct_at,
                   actual.bct_kn AS latest_actual_bct_kn,
                   actual.measured_at AS latest_actual_bct_at,
                   actual_stats.actual_bct_average_kn,
                   actual_stats.actual_bct_min_kn,
                   actual_stats.actual_bct_max_kn,
                   actual_stats.actual_bct_count,
                   cost.total_cost_rub_m2,
                   cost.price_effective_at AS cost_price_effective_at
            FROM composition_definitions cd
            JOIN LATERAL (
                SELECT *
                FROM composition_versions item
                WHERE item.composition_definition_id = cd.id
                ORDER BY item.version_no DESC
                LIMIT 1
            ) cv ON TRUE
            LEFT JOIN LATERAL (
                SELECT COALESCE(
                    jsonb_agg(
                        jsonb_build_object(
                            'layer_no', cl.layer_no,
                            'layer_role', cl.layer_role,
                            'material_id', cl.material_id,
                            'material_code', cl.material_code_snapshot,
                            'material_name', cl.material_name_snapshot,
                            'gsm', cl.gsm_snapshot,
                            'corrugation_coefficient', cl.corrugation_coefficient
                        ) ORDER BY cl.layer_no
                    ),
                    '[]'::jsonb
                ) AS layers
                FROM composition_layers cl
                WHERE cl.composition_version_id = cv.id
            ) layers ON TRUE
            LEFT JOIN LATERAL (
                SELECT bct_kn, measured_at
                FROM composition_bct_results
                WHERE composition_version_id = cv.id AND result_kind = 'calculated'
                ORDER BY measured_at DESC, created_at DESC
                LIMIT 1
            ) calc ON TRUE
            LEFT JOIN LATERAL (
                SELECT bct_kn, measured_at
                FROM composition_bct_results
                WHERE composition_version_id = cv.id AND result_kind = 'actual'
                ORDER BY measured_at DESC, created_at DESC
                LIMIT 1
            ) actual ON TRUE
            LEFT JOIN LATERAL (
                SELECT AVG(bct_kn) AS actual_bct_average_kn,
                       MIN(bct_kn) AS actual_bct_min_kn,
                       MAX(bct_kn) AS actual_bct_max_kn,
                       COUNT(*) AS actual_bct_count
                FROM composition_bct_results
                WHERE composition_version_id = cv.id AND result_kind = 'actual'
            ) actual_stats ON TRUE
            LEFT JOIN LATERAL (
                SELECT total_cost_rub_m2, price_effective_at
                FROM composition_cost_snapshots
                WHERE composition_version_id = cv.id
                ORDER BY price_effective_at DESC, calculated_at DESC
                LIMIT 1
            ) cost ON TRUE
            WHERE cd.organization_id = %s
              AND cd.is_active
              AND (%s::text IS NULL OR cv.board_grade_code = upper(%s::text))
              AND (%s::text IS NULL OR cv.profile_code = upper(%s::text))
            ORDER BY cv.board_grade_code, cv.profile_code, cd.code
            """,
            (
                organization_id,
                board_grade_code,
                board_grade_code,
                profile_code,
                profile_code,
            ),
        ).fetchall()


def record_bct(version_id: UUID, req: BctResultCreate) -> dict:
    with get_conn() as conn, conn.transaction():
        context = _one(
            conn,
            """
            SELECT cv.id, cv.organization_id
            FROM composition_versions cv
            WHERE cv.id = %s
            """,
            (version_id,),
        )
        result = conn.execute(
            """
            INSERT INTO composition_bct_results(
                composition_version_id, result_kind, bct_kn, original_value,
                original_unit, method_code, method_version, sample_count,
                measured_at, source_system, source_reference, lab_protocol,
                recorded_by, evidence
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (
                version_id,
                req.result_kind,
                req.bct_kn,
                req.original_value,
                req.original_unit,
                req.method_code,
                req.method_version,
                req.sample_count,
                req.measured_at,
                req.source_system,
                req.source_reference,
                req.lab_protocol,
                req.recorded_by,
                Jsonb(req.evidence),
            ),
        ).fetchone()
        conn.execute(
            """
            INSERT INTO audit_log(
                organization_id, actor, action, entity_type, entity_id, after_data
            ) VALUES (%s, %s, 'composition.bct.recorded',
                      'composition_bct_result', %s, %s)
            """,
            (
                context["organization_id"],
                req.recorded_by,
                result["id"],
                Jsonb(
                    {
                        "composition_version_id": str(version_id),
                        "result_kind": req.result_kind,
                        "bct_kn": str(req.bct_kn),
                    }
                ),
            ),
        )
        return result


def record_cost(version_id: UUID, req: CostSnapshotCreate) -> dict:
    with get_conn() as conn, conn.transaction():
        context = _one(
            conn,
            "SELECT id, organization_id FROM composition_versions WHERE id = %s",
            (version_id,),
        )
        result = conn.execute(
            """
            INSERT INTO composition_cost_snapshots(
                composition_version_id, total_cost_rub_m2,
                material_cost_rub_m2, conversion_cost_rub_m2,
                price_effective_at, calculation_method, source_system,
                recorded_by, breakdown
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (
                version_id,
                req.total_cost_rub_m2,
                req.material_cost_rub_m2,
                req.conversion_cost_rub_m2,
                req.price_effective_at,
                req.calculation_method,
                req.source_system,
                req.recorded_by,
                Jsonb(req.breakdown),
            ),
        ).fetchone()
        conn.execute(
            """
            INSERT INTO audit_log(
                organization_id, actor, action, entity_type, entity_id, after_data
            ) VALUES (%s, %s, 'composition.cost.recorded',
                      'composition_cost_snapshot', %s, %s)
            """,
            (
                context["organization_id"],
                req.recorded_by,
                result["id"],
                Jsonb(
                    {
                        "composition_version_id": str(version_id),
                        "total_cost_rub_m2": str(req.total_cost_rub_m2),
                        "price_effective_at": req.price_effective_at.isoformat(),
                    }
                ),
            ),
        )
        return result
