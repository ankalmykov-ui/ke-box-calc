from dataclasses import dataclass, asdict
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
import json
import math


@dataclass(frozen=True)
class Fefco0201Rule:
    """Manual constructor override. Kept for exceptional/engineering cases."""

    glue_flap_mm: float = 37.0
    delta_l1_mm: float = 0.0
    delta_b1_mm: float = 0.0
    delta_l2_mm: float = 0.0
    delta_b2_mm: float = 0.0
    delta_top_flap_mm: float = 0.0
    delta_bottom_flap_mm: float = 0.0
    delta_body_height_mm: float = 0.0
    glue_gap_mm: float = 0.0


DATA_DIR = Path(__file__).resolve().parents[1] / "data"
PROFILE_RULES_PATH = DATA_DIR / "fefco0201_profile_rules_v0.1.json"
HISTORICAL_CALIBRATION_PATH = DATA_DIR / "fefco0201_calibration_v0.1.json"


def _round_half_up(value: float) -> int:
    return int(Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _r3(value: float) -> float:
    return round(float(value), 3)


def load_profile_rules() -> dict:
    return json.loads(PROFILE_RULES_PATH.read_text(encoding="utf-8"))


def load_historical_calibration() -> dict:
    """Historical source is diagnostic only and never drives production geometry."""
    data = json.loads(HISTORICAL_CALIBRATION_PATH.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = {**data, "production_use": False, "role": "historical_diagnostic_only"}
    return data


def _normalize_profile(profile: str, data: dict) -> str:
    raw = profile.upper().strip().replace("-", "").replace(" ", "")
    if raw in data["profiles"]:
        return raw
    aliases = data.get("profile_aliases", {})
    if raw in aliases:
        return aliases[raw]
    raise ValueError(f"Unknown corrugated board profile: {profile}")


def _balanced_half_flaps(width_mm: float) -> tuple[int, int]:
    """Integer production split of B/2 + B/2 preserving rounded total B.

    For odd integer breadths this yields, for example, 142 + 143 rather than
    independently rounding 142.5 twice to 143. This keeps the RSC rule that
    the two flap rows together consume one breadth.
    """
    total = _round_half_up(width_mm)
    first = total // 2
    second = total - first
    return first, second


def calculate_fefco0201(
    length_mm: float,
    width_mm: float,
    height_mm: float,
    rule: Fefco0201Rule | None = None,
) -> dict:
    """Explicit/manual panel-level calculation for constructor overrides."""
    if min(length_mm, width_mm, height_mm) <= 0:
        raise ValueError("L, B and H must be greater than zero")

    rule = rule or Fefco0201Rule()
    l1 = length_mm + rule.delta_l1_mm
    b1 = width_mm + rule.delta_b1_mm
    l2 = length_mm + rule.delta_l2_mm
    b2 = width_mm + rule.delta_b2_mm
    joint = rule.glue_flap_mm

    if min(l1, b1, l2, b2, joint) <= 0:
        raise ValueError("Calculated panel dimensions must be greater than zero")

    top_flap = width_mm / 2 + rule.delta_top_flap_mm
    body_height = height_mm + rule.delta_body_height_mm
    bottom_flap = width_mm / 2 + rule.delta_bottom_flap_mm
    blank_length = l1 + b1 + l2 + b2 + joint
    blank_width = top_flap + body_height + bottom_flap

    return {
        "construction": "FEFCO 0201",
        "mode": "manual_constructor_override",
        "input": {"length_mm": length_mm, "width_mm": width_mm, "height_mm": height_mm},
        "rule": asdict(rule),
        "joint": {
            "manufacturer_joint_mm": round(joint, 3),
            "glue_gap_mm": round(rule.glue_gap_mm, 3),
            "note": "Manual mode: glue gap is stored separately and is not silently subtracted from the joint."
        },
        "panels": {
            "l1_mm": round(l1, 3),
            "b1_mm": round(b1, 3),
            "l2_mm": round(l2, 3),
            "b2_mm": round(b2, 3),
            "top_flap_mm": round(top_flap, 3),
            "body_height_mm": round(body_height, 3),
            "bottom_flap_mm": round(bottom_flap, 3),
        },
        "blank": {
            "length_mm": round(blank_length, 3),
            "width_mm": round(blank_width, 3),
            "area_m2": round(blank_length * blank_width / 1_000_000, 6),
        },
    }


def calculate_fefco0201_profile(
    length_mm: float,
    width_mm: float,
    height_mm: float,
    profile: str,
    manufacturer_joint_override_mm: float | None = None,
    caliper_override_mm: float | None = None,
    glue_gap_mm: float | None = None,
) -> dict:
    """Source-priority FEFCO 0201 geometry for *inside* box dimensions.

    Primary geometry basis: EngView FEFCO 0201 main/score-to-score parameters.
    For inside dimensions EngView states:
      Lss1 = L
      Lss  = L + d
      Wss  = W + d
      Wss1 = W + d/2
      Hss  = H + d

    Profile only supplies a reference board caliper d. A measured caliper may
    override it. Historical order dimensions never alter these equations.
    """
    if min(length_mm, width_mm, height_mm) <= 0:
        raise ValueError("L, B and H must be greater than zero")

    data = load_profile_rules()
    normalized_profile = _normalize_profile(profile, data)
    p = data["profiles"][normalized_profile]

    d = float(caliper_override_mm if caliper_override_mm is not None else p["caliper_mm"])
    if d <= 0:
        raise ValueError("Board caliper must be greater than zero")

    joint = float(
        manufacturer_joint_override_mm
        if manufacturer_joint_override_mm is not None
        else data["manufacturer_joint_default_mm"]
    )
    if joint <= 0:
        raise ValueError("Manufacturer joint must be greater than zero")

    # Raw score-to-score geometry (inside dimension type), directly reflecting
    # the published EngView relationships.
    l1_raw = float(length_mm)                # Lss1
    b1_raw = float(width_mm) + d             # Wss
    l2_raw = float(length_mm) + d            # Lss
    b2_raw = float(width_mm) + d / 2.0       # Wss1
    body_raw = float(height_mm) + d          # Hss

    # RSC/0201 flap rule: opposing closing flaps are half the breadth. For
    # whole-mm production dimensions, balance the two halves so their sum is B.
    top_prod, bottom_prod = _balanced_half_flaps(width_mm)
    top_raw = float(width_mm) / 2.0
    bottom_raw = float(width_mm) / 2.0

    # Production dimensions are rounded individually to the nearest millimetre,
    # half-up, because these are the dimensions an operator/slotter actually sets.
    l1 = _round_half_up(l1_raw)
    b1 = _round_half_up(b1_raw)
    l2 = _round_half_up(l2_raw)
    b2 = _round_half_up(b2_raw)
    body = _round_half_up(body_raw)
    joint_prod = _round_half_up(joint)

    blank_length = l1 + b1 + l2 + b2 + joint_prod
    blank_width = top_prod + body + bottom_prod

    raw_blank_length = l1_raw + b1_raw + l2_raw + b2_raw + joint
    raw_blank_width = top_raw + body_raw + bottom_raw

    crease_positions = {
        "from_joint_edge_mm": [
            joint_prod,
            joint_prod + l1,
            joint_prod + l1 + b1,
            joint_prod + l1 + b1 + l2,
        ],
        "transverse_from_top_edge_mm": [top_prod, top_prod + body],
    }

    notes = [
        "Production formula is source-priority: historical order data is not used to choose or tune panel dimensions.",
        "Reference caliper is a starting value. For production-grade accuracy, measured board caliper for the actual composition/profile should override it.",
        "Manufacturer joint is a separate plant parameter. Glue application width and final glue gap are not automatically folded into it unless their dimensional relationship is explicitly approved."
    ]
    if normalized_profile == "C":
        notes.append("With d=4.02 mm and a 37 mm manufacturer joint, tech card #990 rounds to 1599×540 mm and 163/214/163 transversely.")

    return {
        "construction": "FEFCO 0201",
        "mode": "source_priority_inside_dimensions",
        "method_id": "engview_fefco0201_inside_v1",
        "input": {
            "length_mm": length_mm,
            "width_mm": width_mm,
            "height_mm": height_mm,
            "dimension_type": "inside",
            "profile": normalized_profile,
            "profile_input": profile,
        },
        "profile_rule": {
            "caliper_mm": d,
            "caliper_source": "override" if caliper_override_mm is not None else "profile_reference",
            "profile_reference_caliper_mm": p["caliper_mm"],
            "status": p["status"],
            "basis": p["basis"],
            "manufacturer_joint_mm": joint,
            "glue_gap_mm": glue_gap_mm,
            "rounding": data["rounding"],
        },
        "source_formula": {
            "l1": "Lss1 = L",
            "b1": "Wss = B + d",
            "l2": "Lss = L + d",
            "b2": "Wss1 = B + d/2",
            "body": "Hss = H + d",
            "flaps": "B/2 + B/2 (balanced to whole mm)",
        },
        "panels_raw_mm": {
            "l1": _r3(l1_raw),
            "b1": _r3(b1_raw),
            "l2": _r3(l2_raw),
            "b2": _r3(b2_raw),
            "manufacturer_joint": _r3(joint),
            "top_flap": _r3(top_raw),
            "body_height": _r3(body_raw),
            "bottom_flap": _r3(bottom_raw),
        },
        "panels": {
            "l1_mm": l1,
            "b1_mm": b1,
            "l2_mm": l2,
            "b2_mm": b2,
            "manufacturer_joint_mm": joint_prod,
            "top_flap_mm": top_prod,
            "body_height_mm": body,
            "bottom_flap_mm": bottom_prod,
        },
        "crease_positions": crease_positions,
        "blank_raw": {
            "length_mm": _r3(raw_blank_length),
            "width_mm": _r3(raw_blank_width),
        },
        "blank": {
            "length_mm": blank_length,
            "width_mm": blank_width,
            "area_m2": round(blank_length * blank_width / 1_000_000, 6),
        },
        "notes": notes,
        "production_use": True,
    }


def calculate_fefco0201_historical(*args, **kwargs):
    raise ValueError(
        "Historical calibration is intentionally disabled as a production calculation mode. "
        "Use the source-priority FEFCO 0201 formula or an explicit constructor override."
    )
