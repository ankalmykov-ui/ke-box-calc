from __future__ import annotations

from collections import defaultdict
from statistics import mean
from typing import Iterable

from .grade import ect_norm, normalize_grade


def summarize_lab_tests(tests: Iterable[dict]) -> list[dict]:
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for test in tests:
        composition = test.get("composition_key") or test.get("composition") or "UNLINKED"
        profile = str(test.get("profile") or "").upper().replace("С", "C").replace("В", "B").replace("Е", "E")
        grade = normalize_grade(test.get("declared_grade")) or test.get("declared_grade") or ""
        groups[(composition, profile, grade)].append(test)

    out = []
    for (composition, profile, grade), rows in groups.items():
        ects = [float(r["ect_actual"]) for r in rows if r.get("ect_actual") is not None]
        bcts = [float(r["bct_actual"]) for r in rows if r.get("bct_actual") is not None]
        norm = ect_norm(grade)
        passed_values = []
        for r in rows:
            if r.get("passed") is not None:
                passed_values.append(bool(r["passed"]))
            elif norm is not None and r.get("ect_actual") is not None:
                passed_values.append(float(r["ect_actual"]) >= norm)
        ect_avg = mean(ects) if ects else None
        reserve = ((ect_avg / norm - 1) * 100) if ect_avg is not None and norm else None
        out.append({
            "composition_key": composition,
            "profile": profile,
            "declared_grade": grade,
            "tests_count": len(rows),
            "ect_count": len(ects),
            "ect_avg": round(ect_avg, 4) if ect_avg is not None else None,
            "ect_min": min(ects) if ects else None,
            "ect_max": max(ects) if ects else None,
            "bct_count": len(bcts),
            "bct_avg": round(mean(bcts), 4) if bcts else None,
            "bct_min": min(bcts) if bcts else None,
            "bct_max": max(bcts) if bcts else None,
            "pass_count": sum(1 for x in passed_values if x),
            "pass_rate_pct": round(100 * sum(1 for x in passed_values if x) / len(passed_values), 2) if passed_values else None,
            "strength_reserve_pct": round(reserve, 2) if reserve is not None else None,
            "ect_norm": norm,
        })
    return sorted(out, key=lambda x: (x["declared_grade"], x["profile"], x["composition_key"]))


def lab_reliability_score(summary: dict) -> float:
    """0..100. Conservative score used only for ranking, never to redefine the grade norm."""
    n = int(summary.get("tests_count") or 0)
    pass_rate = summary.get("pass_rate_pct")
    reserve = summary.get("strength_reserve_pct")
    sample_score = min(n, 20) / 20 * 25
    pass_score = (float(pass_rate) / 100 * 55) if pass_rate is not None else 0
    reserve_score = max(0, min(float(reserve or 0), 20)) / 20 * 20
    return round(sample_score + pass_score + reserve_score, 2)
