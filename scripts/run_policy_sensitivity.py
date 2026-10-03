#!/usr/bin/env python3
"""Benchmark visible policy-weight changes at +/-5, 10 and 20 percent (V4 §62)."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.sensitivity import run_policy_sensitivity_analysis  # noqa: E402
from scripts.run_sensitivity import build_sensitivity_fixture  # noqa: E402

CURRENT_DEFAULTS = (500, 500, 1000)
SENSITIVITY_CENTER = (500, 500, 500)
DIMENSIONS = ("elderly", "single_elderly", "survey_protection")


def policy_grid() -> list[tuple[str, int, int, int]]:
    # Preserve the current UI default separately. The bounded survey slider is
    # already at 1000, so its positive perturbations need a disclosed interior
    # reference point to represent real +/- changes without changing production.
    grid = [
        ("baseline_default", *CURRENT_DEFAULTS),
        ("sensitivity_center", *SENSITIVITY_CENTER),
    ]
    for index, dimension in enumerate(DIMENSIONS):
        for percent in (-20, -10, -5, 5, 10, 20):
            values = list(SENSITIVITY_CENTER)
            values[index] = round(values[index] * (100 + percent) / 100)
            grid.append((f"center_{dimension}_{percent:+d}pct", *values))
    for percent in (-20, 20):
        grid.append((f"center_all_weights_{percent:+d}pct", *(
            round(value * (100 + percent) / 100) for value in SENSITIVITY_CENTER
        )))
    return grid


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="vc-policy-sensitivity-") as directory:
        areas, providers, connection = build_sensitivity_fixture(Path(directory) / "routes.sqlite")
        try:
            result = run_policy_sensitivity_analysis(
                areas, providers, connection, 1_500_000, grid_points=policy_grid()
            )
        finally:
            connection.close()

    by_name = {row["config_name"]: row for row in result["configurations"]}
    center_result = by_name["sensitivity_center"]
    center_areas = center_result["covered_areas"] or 1
    center_cost = center_result["travel_cost_won"] or 1
    result["sensitivity_center_result"] = center_result
    for row in result["configurations"]:
        row["covered_areas_delta_from_center_pct"] = round(
            abs(row["covered_areas"] - center_result["covered_areas"]) / center_areas * 100, 2
        )
        row["travel_cost_delta_from_center_pct"] = round(
            abs(row["travel_cost_won"] - center_result["travel_cost_won"]) / center_cost * 100, 2
        )

    report = {
        "schema_version": 1,
        "provenance": "SYNTHETIC CONTROLLED FIXTURE; NOT LOCAL POLICY OUTCOME EVIDENCE",
        "protocol": {
            "current_ui_default_weights": dict(zip(DIMENSIONS, CURRENT_DEFAULTS, strict=True)),
            "sensitivity_center_weights": dict(zip(DIMENSIONS, SENSITIVITY_CENTER, strict=True)),
            "one_factor_perturbations_percent": [-20, -10, -5, 5, 10, 20],
            "joint_perturbations_percent": [-20, 20],
            "sensitivity_center_reason": (
                "The current survey-protection default is at the 1000 slider ceiling; "
                "the explicit 500/500/500 center permits both positive and negative changes."
            ),
            "primary_delta_reference": "CURRENT_UI_DEFAULT",
            "symmetric_perturbation_delta_reference": "SENSITIVITY_CENTER",
            "budget_won": 1_500_000,
            "solver_time_limit_seconds": 2.5,
        },
        **result,
    }
    output = ROOT / "artifacts" / "policy_sensitivity_v4.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"configurations={len(report['configurations'])} "
        f"sensitivity={report['sensitivity_level']}"
    )
    print(f"wrote {output.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
