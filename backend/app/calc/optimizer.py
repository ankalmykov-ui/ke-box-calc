from __future__ import annotations

from dataclasses import dataclass, asdict

from .composition import PaperLayer, calculate_composition
from .grade import normalize_grade


ELIGIBLE_STATUSES = {"active", "stock_only", "temporary_no_purchase"}


@dataclass(frozen=True)
class Material:
    code_1c: str
    name: str
    gsm: float
    price_rub_t: float
    stock_kg: float | None = None
    procurement_status: str = "active"
    variant_1c: str | None = None
    supplier: str | None = None

    @property
    def key(self) -> str:
        return self.code_1c + (f"::{self.variant_1c}" if self.variant_1c else "")


@dataclass(frozen=True)
class CandidateLayer:
    role: str
    material_key: str
    corrugation_coefficient: float = 1.0


@dataclass(frozen=True)
class CompositionCandidate:
    code: str
    board_grade: str
    profile: str
    layers: tuple[CandidateLayer, ...]
    status: str = "approved"
    evidence: str = "technologist_approved"
    strength_reserve_pct: float | None = None
    lab_pass_count: int = 0


def evaluate_candidate(
    candidate: CompositionCandidate,
    materials: dict[str, Material],
    net_area_m2: float,
    quantity: int,
    edge_trim_pct: float = 0.0,
    other_waste_pct: float = 0.0,
) -> dict:
    reasons: list[str] = []
    if candidate.status != "approved":
        reasons.append(f"композиция имеет статус {candidate.status}, а не approved")

    paper_layers: list[PaperLayer] = []
    material_rows: list[dict] = []
    for layer in candidate.layers:
        material = materials.get(layer.material_key)
        if material is None:
            reasons.append(f"нет материала {layer.material_key} для слоя {layer.role}")
            continue
        if material.procurement_status not in ELIGIBLE_STATUSES:
            reasons.append(f"{material.name}: статус {material.procurement_status}")
        paper_layers.append(
            PaperLayer(
                role=layer.role,
                gsm=material.gsm,
                price_rub_t=material.price_rub_t,
                corrugation_coefficient=layer.corrugation_coefficient,
                material_name=material.name,
            )
        )
        material_rows.append({"layer": asdict(layer), "material": asdict(material)})

    if len(paper_layers) != len(candidate.layers):
        return {
            "candidate": asdict(candidate),
            "eligible": False,
            "reasons": reasons,
            "materials": material_rows,
            "calculation": None,
        }

    calc = calculate_composition(
        net_area_m2=net_area_m2,
        quantity=quantity,
        layers=paper_layers,
        edge_trim_pct=edge_trim_pct,
        other_waste_pct=other_waste_pct,
    )

    for lr, mr in zip(calc["layers"], material_rows):
        material = Material(**mr["material"])
        required = float(lr["mass_kg"])
        if material.stock_kg is not None and material.procurement_status in {"stock_only", "temporary_no_purchase"}:
            if material.stock_kg + 1e-9 < required:
                reasons.append(
                    f"{material.name}: требуется {required:.1f} кг, остаток {material.stock_kg:.1f} кг"
                )

    eligible = not reasons
    return {
        "candidate": asdict(candidate),
        "eligible": eligible,
        "reasons": reasons,
        "materials": material_rows,
        "calculation": calc,
    }


def rank_candidates(
    candidates: list[CompositionCandidate],
    materials: list[Material],
    required_board_grade: str,
    profile: str,
    net_area_m2: float,
    quantity: int,
    edge_trim_pct: float = 0.0,
    other_waste_pct: float = 0.0,
) -> dict:
    material_map = {m.key: m for m in materials}
    req_grade = normalize_grade(required_board_grade) or required_board_grade.upper().strip()
    matching = [
        c for c in candidates
        if (normalize_grade(c.board_grade) or c.board_grade.upper().strip()) == req_grade
        and c.profile.upper().strip().replace("С","C").replace("В","B").replace("Е","E") == profile.upper().strip().replace("С","C").replace("В","B").replace("Е","E")
    ]

    evaluated = [
        evaluate_candidate(c, material_map, net_area_m2, quantity, edge_trim_pct, other_waste_pct)
        for c in matching
    ]
    eligible = [r for r in evaluated if r["eligible"]]
    eligible.sort(
        key=lambda r: (
            r["calculation"]["total_cost_rub"],
            -(r["candidate"].get("strength_reserve_pct") or 0),
            -int(r["candidate"].get("lab_pass_count") or 0),
        )
    )

    for idx, row in enumerate(eligible, start=1):
        row["rank"] = idx
        row["is_recommended"] = (idx == 1)

    ineligible = [r for r in evaluated if not r["eligible"]]
    return {
        "required_board_grade": required_board_grade,
        "profile": profile,
        "net_area_m2": net_area_m2,
        "quantity": quantity,
        "matching_candidates": len(matching),
        "eligible_candidates": len(eligible),
        "recommended": eligible[0] if eligible else None,
        "ranking": eligible,
        "excluded": ineligible,
        "decision_rule": "минимальная стоимость среди утверждённых и доступных композиций; затем резерв прочности и число успешных лабораторных испытаний",
    }
