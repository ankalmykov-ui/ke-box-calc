from __future__ import annotations

from dataclasses import dataclass, asdict
from itertools import product, combinations
import json
import math
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "data"


@dataclass(frozen=True)
class CorrugatorItem:
    code: str
    blank_length_mm: float
    blank_width_mm: float
    quantity: int
    profile: str
    required_board_grade: str
    blank_area_m2: float | None = None


@dataclass(frozen=True)
class CorrugatorConfig:
    working_width_mm: float = 2100
    max_streams: int = 5
    crosscut_levels: int = 2


def load_corrugator_reference() -> dict:
    return json.loads((DATA / "corrugator_v0.6.json").read_text(encoding="utf-8"))


def _candidate_stream_allocations(items: list[CorrugatorItem], max_streams: int):
    # At least one stream per included item, with total stream count bounded by equipment.
    for counts in product(range(1, max_streams + 1), repeat=len(items)):
        if sum(counts) <= max_streams:
            yield counts


def evaluate_run(items: list[CorrugatorItem], stream_counts: tuple[int, ...], roll_width_mm: float, config: CorrugatorConfig) -> dict | None:
    if not items or len(items) != len(stream_counts):
        return None
    cut_lengths = sorted({round(i.blank_length_mm, 6) for i in items})
    if len(cut_lengths) > config.crosscut_levels:
        return None
    used_width = sum(i.blank_width_mm * s for i, s in zip(items, stream_counts))
    if used_width > roll_width_mm + 1e-9 or used_width > config.working_width_mm + 1e-9:
        return None
    if sum(stream_counts) > config.max_streams:
        return None

    required_m = []
    for item, streams in zip(items, stream_counts):
        cuts_per_stream = math.ceil(item.quantity / streams)
        meters = cuts_per_stream * item.blank_length_mm / 1000
        required_m.append(meters)
    run_m = max(required_m)

    details = []
    overproduction_area = 0.0
    for item, streams in zip(items, stream_counts):
        cuts = math.floor(run_m * 1000 / item.blank_length_mm + 1e-9)
        produced = cuts * streams
        over = max(0, produced - item.quantity)
        area = item.blank_area_m2 if item.blank_area_m2 is not None else item.blank_length_mm * item.blank_width_mm / 1_000_000
        overproduction_area += over * area
        details.append({
            "code": item.code,
            "cut_length_mm": item.blank_length_mm,
            "stream_width_mm": item.blank_width_mm,
            "streams": streams,
            "ordered_qty": item.quantity,
            "produced_qty": produced,
            "overproduction_qty": over,
        })

    trim_mm = roll_width_mm - used_width
    trim_pct = trim_mm / roll_width_mm * 100 if roll_width_mm else 0
    trim_area_m2 = trim_mm / 1000 * run_m
    total_waste_m2 = trim_area_m2 + overproduction_area
    score = total_waste_m2 + run_m * 0.0005
    return {
        "roll_width_mm": roll_width_mm,
        "used_width_mm": round(used_width, 3),
        "edge_trim_mm": round(trim_mm, 3),
        "edge_trim_pct": round(trim_pct, 3),
        "run_length_m": round(run_m, 3),
        "crosscut_lengths_mm": cut_lengths,
        "levels_used": len(cut_lengths),
        "streams_total": sum(stream_counts),
        "items": details,
        "trim_area_m2": round(trim_area_m2, 4),
        "overproduction_area_m2": round(overproduction_area, 4),
        "total_waste_m2": round(total_waste_m2, 4),
        "objective_score": round(score, 6),
    }


def best_run(items: list[CorrugatorItem], roll_widths_mm: list[float], config: CorrugatorConfig | None = None) -> dict | None:
    config = config or CorrugatorConfig()
    best = None
    for roll in sorted(set(float(x) for x in roll_widths_mm if x and float(x) > 0)):
        for counts in _candidate_stream_allocations(items, config.max_streams):
            run = evaluate_run(items, counts, roll, config)
            if run is None:
                continue
            if best is None or run["objective_score"] < best["objective_score"]:
                best = run
    return best


def optimize_corrugator_group(items: list[CorrugatorItem], roll_widths_mm: list[float], config: CorrugatorConfig | None = None) -> dict:
    """Greedy group planner.

    Each launch uses one profile/common board and no more than two cross-cut lengths.
    The search considers subsets that fit the stream limit, then chooses the launch with
    the highest coverage and lowest material waste. Remaining items are planned next.
    """
    config = config or CorrugatorConfig()
    if not items:
        return {"launches": [], "unplanned": [], "summary": {"orders": 0}}
    if not roll_widths_mm:
        raise ValueError("Не переданы фактически доступные ширины рулонов")

    remaining = list(items)
    launches = []
    unplanned = []
    while remaining:
        best_choice = None
        max_subset = min(len(remaining), config.max_streams)
        for size in range(1, max_subset + 1):
            for subset_idx in combinations(range(len(remaining)), size):
                subset = [remaining[i] for i in subset_idx]
                if len({x.profile for x in subset}) > 1:
                    continue
                if len({round(x.blank_length_mm, 6) for x in subset}) > config.crosscut_levels:
                    continue
                run = best_run(subset, roll_widths_mm, config)
                if run is None:
                    continue
                coverage = sum(x.quantity for x in subset)
                # Prefer more distinct orders first, then quantity, then lower waste.
                rank = (-len(subset), -coverage, run["objective_score"])
                if best_choice is None or rank < best_choice[0]:
                    best_choice = (rank, subset_idx, run)
        if best_choice is None:
            item = remaining.pop(0)
            unplanned.append({"code": item.code, "reason": "Не найден раскрой на доступных ширинах/ручьях", **asdict(item)})
            continue
        _, subset_idx, run = best_choice
        selected = [remaining[i] for i in subset_idx]
        run["profile"] = selected[0].profile
        run["required_board_grades"] = sorted({x.required_board_grade for x in selected})
        launches.append(run)
        selected_set = set(subset_idx)
        remaining = [x for i, x in enumerate(remaining) if i not in selected_set]

    return {
        "config": asdict(config),
        "roll_widths_mm": sorted(set(float(x) for x in roll_widths_mm)),
        "launches": launches,
        "unplanned": unplanned,
        "summary": {
            "orders": len(items),
            "launches": len(launches),
            "unplanned": len(unplanned),
            "run_length_m": round(sum(x["run_length_m"] for x in launches), 3),
            "trim_area_m2": round(sum(x["trim_area_m2"] for x in launches), 3),
            "overproduction_area_m2": round(sum(x["overproduction_area_m2"] for x in launches), 3),
        },
    }
