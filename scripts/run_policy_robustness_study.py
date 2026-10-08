#!/usr/bin/env python3
"""Run a bounded, reproducible synthetic policy comparison on the public fixture."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["VILLAGE_COVERAGE_PUBLIC_DEMO"] = "true"

from ortools import __version__ as ortools_version  # noqa: E402

from backend import optimization, travel  # noqa: E402
from backend.demand_model_v4 import estimate_area_service_demand  # noqa: E402
from backend.regions import DEFAULT_REGION_ID, select_region  # noqa: E402
from backend.simulation import (  # noqa: E402
    REFERENCE_SEED,
    simulated_operating_profile,
    simulated_providers_for_seed,
)

BUDGET_GRID = (4_000_000, 5_000_000, 7_000_000)
SEEDS = (REFERENCE_SEED, REFERENCE_SEED + 1, REFERENCE_SEED + 2)
POLICY_NAMES = {
    "efficiency": "EFFICIENCY",
    "balanced": "BALANCED",
    "underserved_first": "UNDERSERVED_FIRST",
    "minimum_coverage": "MINIMUM_GUARANTEE",
}
SUPPORTED_SERVICES = {"laundry", "daily_necessities", "home_repair"}
AS_OF = date(2026, 10, 8)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def copy_route_fixture(
    destination: Path, areas: list[dict[str, Any]]
) -> tuple[sqlite3.Connection, str, int]:
    connection = travel.connect(destination)
    count = travel.seed_public_demo_routes(connection, areas)
    rows = connection.execute(
        "SELECT origin_id, destination_id, distance_m, duration_s, routing_version "
        "FROM travel_matrix ORDER BY origin_id, destination_id"
    ).fetchall()
    fingerprint = sha256_bytes(json.dumps(rows, separators=(",", ":")).encode())
    return connection, fingerprint, count


def policy_metrics(
    result: dict[str, Any],
    areas: list[dict[str, Any]],
    providers: list[dict[str, Any]],
    budget_won: int,
) -> dict[str, Any]:
    covered = int(result["covered_villages"])
    assignments = result["assignments"]
    provider_by_id = {str(item["id"]): item for item in providers}
    provider_capacity = {
        provider_id: int(item["capacity_per_month"]) for provider_id, item in provider_by_id.items()
    }
    usage = {
        str(item["provider_id"]): int(item["service_rounds"])
        for item in result["provider_cost_breakdown"]
    }
    utilization = {
        provider_id: round(usage.get(provider_id, 0) / capacity, 4) if capacity else None
        for provider_id, capacity in sorted(provider_capacity.items())
    }
    area_by_id = {str(item["id"]): item for item in areas}
    assigned_provider_ids = {
        str(provider_id)
        for assignment in assignments
        for provider_id in assignment["provider_assignments"]
    }
    checks = {
        "budget_never_exceeded": int(result["budget_spent_won"]) <= budget_won,
        "provider_capacity_respected": all(
            usage.get(provider_id, 0) <= capacity
            for provider_id, capacity in provider_capacity.items()
        ),
        "supported_service_provider_assignments": all(
            provider_id in provider_by_id
            and area_by_id[assignment["area_id"]].get("service_type") in SUPPORTED_SERVICES
            and (
                provider_by_id[provider_id].get("supported_services") is None
                or area_by_id[assignment["area_id"]].get("service_type")
                in provider_by_id[provider_id]["supported_services"]
            )
            for assignment in assignments
            for provider_id in assignment["provider_assignments"]
        ),
        "per_area_provider_units_match_served_units": all(
            sum(int(units) for units in assignment["provider_assignments"].values())
            == int(assignment["served_units"])
            for assignment in assignments
        ),
        "coverage_count_consistent": covered == sum(bool(item["covered"]) for item in assignments),
        "served_unit_count_consistent": int(result["served_units"])
        == sum(int(item["served_units"]) for item in assignments),
        "no_unknown_provider_assignment": assigned_provider_ids <= set(provider_capacity),
    }
    if not all(checks.values()):
        raise AssertionError(f"solver integrity check failed: {checks}")
    return {
        "covered_areas": covered,
        "zero_service_areas": int(result["uncovered_villages"]),
        "served_units": int(result["served_units"]),
        "total_demand_units": int(result["total_demand_units"]),
        "budget_spent_won": int(result["budget_spent_won"]),
        "travel_cost_won": int(result["travel_cost_won"]),
        "travel_time_s": int(result["travel_time_s"]),
        "provider_utilization": utilization,
        "solver_status": result["solver_status"],
        "optimality_proven": bool(result["optimality_proven"]),
        "time_limit_reached": bool(result["time_limit_reached"]),
        "solve_time_ms": result["solve_time_ms"],
        "required_budget_won": result.get("required_budget_won"),
        "unmet_minimum_frequency_areas": int(result["unmet_minimum_frequency_areas"]),
        "full_demand_failure_reason": result.get("full_demand_failure_reason"),
        "integrity_checks": checks,
        "schedule_compatibility": "NOT_EVALUATED_BY_AGGREGATE_POLICY_COMPARATOR",
    }


def observation(month: str, frequency: int | None) -> dict[str, Any]:
    return {
        "occurred_on": f"{month}-10",
        "frequency_per_month": frequency,
        "source_type": "SYNTHETIC_SCENARIO_ASSUMPTION",
    }


def low_data_cases(area: dict[str, Any]) -> list[dict[str, Any]]:
    common = {
        "area": area,
        "service_type": "laundry",
        "as_of": AS_OF,
        "synthetic_prior_monthly": 5.0,
    }
    cases = [
        {
            "case": "A_NO_COUNT_EVIDENCE_ONLY",
            "label": "요청 횟수 미기록 + 근거 행은 있으나 빈도 없음",
            "observations": [
                observation("2026-07", None),
                observation("2026-08", None),
                observation("2026-09", None),
            ],
            "unresolved_conflicts": 0,
            "interpretation": "빈도 미기록을 0회로 바꾸지 않고 모델 게이트 결과만 기록",
        },
        {
            "case": "B_NO_COUNT_ACCESS_RISK_UNKNOWN",
            "label": "요청 횟수 미기록 + 접근성 부족 가능성은 있으나 확인 자료 없음",
            "observations": [],
            "unresolved_conflicts": 0,
            "interpretation": "접근 위험은 시나리오 가정이며 현재 공개 fixture 입력으로 확인 불가",
        },
        {
            "case": "C_SURVEY_REQUIRED_LOW_EVIDENCE",
            "label": "조사 필요 + 한 기간만 기록",
            "observations": [observation("2026-09", 1)],
            "unresolved_conflicts": 0,
            "interpretation": "최소 표본·기간 게이트가 예측 허용 여부를 결정",
        },
        {
            "case": "D_CONFLICTING_EVIDENCE",
            "label": "같은 기간에 충돌하는 기록이 있고 미해결 상태",
            "observations": [
                observation("2026-07", 1),
                observation("2026-08", 2),
                observation("2026-09", 8),
            ],
            "unresolved_conflicts": 1,
            "interpretation": "충돌 표시가 예측을 차단하는지 확인; 값을 합치거나 덮어쓰지 않음",
        },
    ]
    output = []
    for case in cases:
        result = estimate_area_service_demand(
            **common,
            observations=case["observations"],
            unresolved_conflicts=case["unresolved_conflicts"],
        )
        output.append(
            {
                "case": case["case"],
                "label": case["label"],
                "input_classification": (
                    "SYNTHETIC MODEL-LEVEL SCENARIO; NOT A RESIDENT OBSERVATION"
                ),
                "observation_rows": len(case["observations"]),
                "recorded_frequency_values": [
                    row["frequency_per_month"]
                    for row in case["observations"]
                    if row["frequency_per_month"] is not None
                ],
                "unresolved_conflicts": case["unresolved_conflicts"],
                "forecast_status": result["forecast_status"],
                "gate_reasons": result["gate_reasons"],
                "monthly_count_range": result["monthly_count_range"],
                "external_prior_provenance": (
                    result["external_prior"].get("provenance") if result["external_prior"] else None
                ),
                "synthetic_prior_monthly": result["synthetic_prior_monthly"],
                "interpretation": case["interpretation"],
            }
        )
    return output


def run_study(output_dir: Path) -> dict[str, Any]:
    data_bytes = (ROOT / "data" / "demo.json").read_bytes()
    demo = select_region(json.loads(data_bytes), DEFAULT_REGION_ID)
    baseline_areas = demo["areas"]
    output_dir.mkdir(parents=True, exist_ok=True)
    route_path = output_dir / "policy-study-routes.sqlite"
    connection, route_fingerprint, route_rows = copy_route_fixture(route_path, baseline_areas)
    try:
        records: list[dict[str, Any]] = []
        replay_determinism: dict[str, bool] = {}
        seed_inputs: dict[int, tuple[list[dict[str, Any]], list[dict[str, Any]]]] = {}
        for seed in SEEDS:
            areas = [{**area, **simulated_operating_profile(area, seed)} for area in baseline_areas]
            providers = simulated_providers_for_seed(demo["providers"], seed)
            seed_inputs[seed] = (areas, providers)
            survey_count = sum(bool(area.get("needs_survey")) for area in areas)
            underserved_signal_count = sum(bool(area.get("underserved_points")) for area in areas)
            for budget in BUDGET_GRID:
                started = time.perf_counter()
                evaluation = optimization.evaluate_scenarios(
                    areas, providers, connection, budget, include_timing=True
                )
                wall_ms = round((time.perf_counter() - started) * 1000, 2)
                for scenario, result in evaluation["scenario_results"].items():
                    metric = policy_metrics(result, areas, providers, budget)
                    row = {
                        "experiment": "POLICY_BUDGET_SEED",
                        "seed": seed,
                        "budget_won": budget,
                        "scenario": POLICY_NAMES[scenario],
                        "scenario_key": scenario,
                        "provider_count": len(providers),
                        "provider_capacity_total": sum(
                            int(provider["capacity_per_month"]) for provider in providers
                        ),
                        "survey_required_areas": survey_count,
                        "survey_required_fraction": round(survey_count / len(areas), 4),
                        "underserved_signal_areas": underserved_signal_count,
                        "evaluation_wall_ms": wall_ms,
                        **metric,
                    }
                    records.append(row)
                if seed == REFERENCE_SEED and budget == 5_000_000:
                    replay = optimization.evaluate_scenarios(
                        areas, providers, connection, budget, include_timing=False
                    )
                    replay_determinism = {
                        scenario: evaluation["scenario_results"][scenario]["assignments"]
                        == replay["scenario_results"][scenario]["assignments"]
                        for scenario in evaluation["scenario_results"]
                    }

        decline_records: list[dict[str, Any]] = []
        decline_areas, full_providers = seed_inputs[REFERENCE_SEED]
        ordered = sorted(full_providers, key=lambda provider: int(provider["capacity_per_month"]))
        decline_cases = [
            ("0_DECLINES", full_providers),
            ("1_DECLINE", ordered[1:]),
            ("MULTIPLE_DECLINES", ordered[-max(1, len(ordered) // 2) :]),
        ]
        for decline_case, providers in decline_cases:
            evaluation = optimization.evaluate_scenarios(
                decline_areas, providers, connection, 5_000_000, include_timing=True
            )
            for scenario, result in evaluation["scenario_results"].items():
                metric = policy_metrics(result, decline_areas, providers, 5_000_000)
                decline_records.append(
                    {
                        "experiment": "PROVIDER_DECLINE",
                        "decline_case": decline_case,
                        "declined_provider_count": len(full_providers) - len(providers),
                        "active_provider_count": len(providers),
                        "seed": REFERENCE_SEED,
                        "budget_won": 5_000_000,
                        "scenario": POLICY_NAMES[scenario],
                        **metric,
                        "replan_api_executed": False,
                    }
                )

        low_data = low_data_cases(baseline_areas[0])
        return {
            "schema_version": 1,
            "study_scope": (
                "SYNTHETIC POLICY ROBUSTNESS; NOT FIELD DEMAND OR SERVICE EFFECT EVIDENCE"
            ),
            "metadata": {
                "baseline_code_sha": subprocess.run(
                    ["git", "rev-parse", "HEAD"],
                    cwd=ROOT,
                    check=True,
                    capture_output=True,
                    text=True,
                ).stdout.strip(),
                "experiment_driver_sha256": sha256_bytes(Path(__file__).read_bytes()),
                "dataset_fingerprint_sha256": sha256_bytes(data_bytes),
                "route_matrix_fingerprint_sha256": route_fingerprint,
                "route_matrix_rows": route_rows,
                "route_matrix_source": "PUBLIC_DEMO_STRAIGHT_LINE_MODEL_ESTIMATE; NOT A ROAD ROUTE",
                "solver": "OR-Tools CP-SAT",
                "solver_version": ortools_version,
                "aggregate_solver_time_limit_seconds": optimization.MAX_SOLVER_SECONDS,
                "schedule_optimizer_default": "BASELINE_DECOMPOSED",
                "policy_comparator": (
                    "backend.optimization.evaluate_scenarios; monthly aggregate model"
                ),
                "region_id": demo["region_id"],
                "seed_list": list(SEEDS),
                "budget_grid_won": list(BUDGET_GRID),
                "policy_mapping": POLICY_NAMES,
                "date_as_of": AS_OF.isoformat(),
                "variable_coverage": {
                    "budget": "varied",
                    "demand_distribution": "varied by existing seeded helper",
                    "provider_capacity": "varied by existing seeded helper",
                    "provider_decline": (
                        "varied by removing synthetic providers from the aggregate model"
                    ),
                    "survey_required_fraction": "varied by seeded observation count profile",
                    "travel_cost": (
                        "reported as outcome; route matrix held fixed because no supported "
                        "travel-cost scenario input exists"
                    ),
                    "underserved_history": (
                        "fixed; demo fixture has no per-area historical delivery observations"
                    ),
                },
                "reproducibility": {
                    "scenario_assignments_identical_on_reference_replay": replay_determinism,
                    "all_reference_scenarios_deterministic": all(replay_determinism.values()),
                },
            },
            "policy_budget_seed_results": records,
            "provider_decline_results": decline_records,
            "low_data_cases": low_data,
            "limitations": [
                (
                    "All demand, capacity, prices, and provider availability are synthetic "
                    "assumptions."
                ),
                "The route matrix is a straight-line model estimate and is not a road route.",
                "The aggregate policy comparator does not schedule dated provider appointments.",
                (
                    "Provider removal is a synthetic decline condition, not a measured real "
                    "decline rate."
                ),
                (
                    "No municipality savings, real demand accuracy, or resident service "
                    "increase is established."
                ),
                (
                    "A zero frequency is not accepted by the public survey input contract; "
                    "missing frequency stays unknown and is not coerced to zero."
                ),
            ],
        }
    finally:
        connection.close()


def csv_rows(result: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for row in result["policy_budget_seed_results"]:
        rows.append(
            {
                "experiment": row["experiment"],
                "seed": row["seed"],
                "budget_won": row["budget_won"],
                "scenario": row["scenario"],
                "decline_case": "",
                "provider_count": row["provider_count"],
                "covered_areas": row["covered_areas"],
                "zero_service_areas": row["zero_service_areas"],
                "served_units": row["served_units"],
                "total_demand_units": row["total_demand_units"],
                "budget_spent_won": row["budget_spent_won"],
                "travel_cost_won": row["travel_cost_won"],
                "travel_time_s": row["travel_time_s"],
                "provider_utilization": json.dumps(row["provider_utilization"], sort_keys=True),
                "solver_status": row["solver_status"],
                "optimality_proven": row["optimality_proven"],
                "time_limit_reached": row["time_limit_reached"],
                "solve_time_ms": row["solve_time_ms"],
                "required_budget_won": row["required_budget_won"],
                "unmet_minimum_frequency_areas": row["unmet_minimum_frequency_areas"],
            }
        )
    for row in result["provider_decline_results"]:
        rows.append(
            {
                "experiment": row["experiment"],
                "seed": row["seed"],
                "budget_won": row["budget_won"],
                "scenario": row["scenario"],
                "decline_case": row["decline_case"],
                "provider_count": row["active_provider_count"],
                "covered_areas": row["covered_areas"],
                "zero_service_areas": row["zero_service_areas"],
                "served_units": row["served_units"],
                "total_demand_units": row["total_demand_units"],
                "budget_spent_won": row["budget_spent_won"],
                "travel_cost_won": row["travel_cost_won"],
                "travel_time_s": row["travel_time_s"],
                "provider_utilization": json.dumps(row["provider_utilization"], sort_keys=True),
                "solver_status": row["solver_status"],
                "optimality_proven": row["optimality_proven"],
                "time_limit_reached": row["time_limit_reached"],
                "solve_time_ms": row["solve_time_ms"],
                "required_budget_won": row["required_budget_won"],
                "unmet_minimum_frequency_areas": row["unmet_minimum_frequency_areas"],
            }
        )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=ROOT / "artifacts" / "research")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="vc-policy-robustness-") as temporary:
        result = run_study(Path(temporary))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "policy_robustness.json"
    csv_path = args.output_dir / "policy_robustness.csv"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    rows = csv_rows(result)
    fields = [
        "experiment",
        "seed",
        "budget_won",
        "scenario",
        "decline_case",
        "provider_count",
        "covered_areas",
        "zero_service_areas",
        "served_units",
        "total_demand_units",
        "budget_spent_won",
        "travel_cost_won",
        "travel_time_s",
        "provider_utilization",
        "solver_status",
        "optimality_proven",
        "time_limit_reached",
        "solve_time_ms",
        "required_budget_won",
        "unmet_minimum_frequency_areas",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    summary = {
        "output_json": str(json_path),
        "output_csv": str(csv_path),
        "policy_result_rows": len(result["policy_budget_seed_results"]),
        "provider_decline_rows": len(result["provider_decline_results"]),
        "low_data_cases": len(result["low_data_cases"]),
        "deterministic_replay": result["metadata"]["reproducibility"],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
