"""Measure deterministic synthetic replans after common operational changes."""

from __future__ import annotations

import argparse
import csv
import json
import sys
import tempfile
import time
from copy import deepcopy
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend import scheduling  # noqa: E402
from backend.source_snapshots import utc_now  # noqa: E402
from scripts.run_stress_tests import (  # noqa: E402
    REFERENCE_SEED,
    generate_scenario_data,
    verify_invariants,
)

CASES = ((16, 3), (50, 5))
CHANGE_NAMES = (
    "ONE_PROVIDER_DECLINES",
    "TWO_PROVIDERS_DECLINE",
    "TWENTY_PERCENT_UNAVAILABLE",
    "BUDGET_MINUS_TEN_PERCENT",
    "NEW_RESIDENT_CLAIM_REQUIRES_SURVEY",
    "NEW_VERIFIED_SURVEY_CHANGES_DEMAND",
)


def _served_areas(plan: dict[str, Any]) -> set[str]:
    return {
        str(row["area_id"])
        for row in plan.get("rounds", [])
        if int(row.get("service_units", 0)) > 0
    }


def _zero_service_count(areas: list[dict[str, Any]], plan: dict[str, Any]) -> int:
    served = _served_areas(plan)
    return sum(
        1 for area in areas
        if int(area.get("simulated_monthly_demand", 0)) > 0 and str(area["id"]) not in served
    )


def _run_plan(
    areas: list[dict[str, Any]],
    providers: list[dict[str, Any]],
    connection: Any,
    budget: int,
    policy: Any,
    fallback: bool,
    warm_start: set[tuple[str, str, str]],
    seconds: float,
) -> dict[str, Any]:
    return scheduling.generate_provider_schedule(
        areas,
        providers,
        connection,
        budget,
        "balanced",
        policy,
        allow_route_fallback=fallback,
        route_strategy="decomposed",
        warm_start_keys=warm_start,
        max_solver_seconds=seconds,
        include_timing=True,
    )


def run_case(areas_n: int, providers_n: int, seconds: float) -> list[dict[str, Any]]:
    with tempfile.TemporaryDirectory(prefix="village-coverage-replan-") as temporary:
        areas, providers, connection, budget, policy, fallback, metadata = generate_scenario_data(
            areas_n,
            providers_n,
            "A",
            REFERENCE_SEED + areas_n + providers_n,
            Path(temporary) / "routes.sqlite",
        )
        try:
            baseline_started = time.perf_counter()
            baseline = _run_plan(
                areas,
                providers,
                connection,
                budget,
                policy,
                fallback,
                set(),
                seconds,
            )
            baseline_runtime = round((time.perf_counter() - baseline_started) * 1000, 2)
            baseline_invariants = verify_invariants(
                baseline, areas, providers, budget, connection,
                allow_route_fallback=fallback,
            )
            warm_start = {
                (str(row["provider_id"]), str(row["area_id"]), str(row["scheduled_date"]))
                for row in baseline.get("rounds", [])
            }
            used_providers = sorted({str(row["provider_id"]) for row in baseline.get("rounds", [])})
            if not used_providers:
                used_providers = sorted(str(provider["provider_id"]) for provider in providers)
            rows = []
            for change_name in CHANGE_NAMES:
                changed_areas = deepcopy(areas)
                changed_providers = deepcopy(providers)
                changed_budget = budget
                if change_name == "ONE_PROVIDER_DECLINES":
                    declined = set(used_providers[:1])
                    changed_providers = [
                        provider for provider in changed_providers
                        if str(provider["provider_id"]) not in declined
                    ]
                elif change_name == "TWO_PROVIDERS_DECLINE":
                    declined = set(used_providers[:2])
                    changed_providers = [
                        provider for provider in changed_providers
                        if str(provider["provider_id"]) not in declined
                    ]
                elif change_name == "TWENTY_PERCENT_UNAVAILABLE":
                    count = max(1, (len(changed_providers) + 4) // 5)
                    declined = set(used_providers[:count])
                    changed_providers = [
                        provider for provider in changed_providers
                        if str(provider["provider_id"]) not in declined
                    ]
                elif change_name == "BUDGET_MINUS_TEN_PERCENT":
                    changed_budget = budget * 90 // 100
                elif change_name == "NEW_RESIDENT_CLAIM_REQUIRES_SURVEY":
                    changed_areas[0]["needs_survey"] = True
                    changed_areas[0]["resident_feedback_claim_count"] = 1
                elif change_name == "NEW_VERIFIED_SURVEY_CHANGES_DEMAND":
                    changed_areas[0]["simulated_monthly_demand"] = min(
                        8, int(changed_areas[0]["simulated_monthly_demand"]) + 2
                    )
                    changed_areas[0]["verified_survey_update"] = True

                started = time.perf_counter()
                error = None
                try:
                    result = _run_plan(
                        changed_areas, changed_providers, connection, changed_budget,
                        policy, fallback, warm_start, seconds,
                    )
                    check = verify_invariants(
                        result, changed_areas, changed_providers, changed_budget,
                        connection, allow_route_fallback=fallback,
                    )
                    status = str(result["solver_status"])
                except (RuntimeError, ValueError) as exc:
                    result = {}
                    check = {"passed": False, "violations": [str(exc)]}
                    status = "NOT_VERIFIABLE"
                    error = type(exc).__name__
                elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
                rows.append({
                    "areas": areas_n,
                    "providers": providers_n,
                    "change": change_name,
                    "seed": REFERENCE_SEED + areas_n + providers_n,
                    "scenario_provenance": "SYNTHETIC_SCENARIO_GENERATOR",
                    "baseline_solver_status": baseline["solver_status"],
                    "replan_solver_status": status,
                    "baseline_runtime_ms": baseline_runtime,
                    "replan_runtime_ms": elapsed_ms,
                    "baseline_cost_won": baseline["budget_spent_won"],
                    "replan_cost_won": result.get("budget_spent_won"),
                    "cost_delta_won": (
                        int(result["budget_spent_won"]) - int(baseline["budget_spent_won"])
                        if result else None
                    ),
                    "baseline_covered_areas": baseline["covered_areas"],
                    "replan_covered_areas": result.get("covered_areas"),
                    "coverage_delta_areas": (
                        int(result["covered_areas"]) - int(baseline["covered_areas"])
                        if result else None
                    ),
                    "baseline_zero_service_areas": _zero_service_count(areas, baseline),
                    "replan_zero_service_areas": (
                        _zero_service_count(changed_areas, result) if result else None
                    ),
                    "zero_service_delta_areas": (
                        _zero_service_count(changed_areas, result)
                        - _zero_service_count(areas, baseline)
                        if result else None
                    ),
                    "warm_start_compatible_candidates": result.get("warm_start", {}).get(
                        "compatible_prior_candidate_count"
                    ),
                    "baseline_invariants_passed": baseline_invariants["passed"],
                    "replan_invariants_passed": check["passed"],
                    "replan_success": bool(result) and check["passed"] and status in {
                        "OPTIMAL", "FEASIBLE", "TIME_LIMIT"
                    },
                    "error_type": error,
                    "violations": check["violations"],
                    "requested_participation_rate": metadata["requested_participation_rate"],
                })
            return rows
        finally:
            connection.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=float, default=2.0)
    parser.add_argument("--output-stem", default="replan_benchmark_v5")
    args = parser.parse_args()
    rows = [row for areas, providers in CASES for row in run_case(areas, providers, args.seconds)]
    report = {
        "generated_at": utc_now(),
        "matrix_type": "SYNTHETIC_REPLAN_BENCHMARK_V5",
        "solver_seconds_per_solve": args.seconds,
        "cases": len(rows),
        "successes": sum(row["replan_success"] for row in rows),
        "invariant_violations": sum(len(row["violations"]) for row in rows),
        "provenance": "SYNTHETIC_INPUTS_AND_SYNTHETIC_ROUTE_EDGES; NOT FIELD PERFORMANCE",
        "definitions": {
            "resident_claim": (
                "Adds a survey-required review flag and leaves numeric demand unchanged."
            ),
            "new_survey": "Simulated verified survey raises one area's demand by two units.",
            "warm_start": "Previous provider-area-date choices are passed as solver hints.",
        },
        "rows": rows,
    }
    output_dir = ROOT / "artifacts"
    output_dir.mkdir(exist_ok=True)
    json_path = output_dir / f"{args.output_stem}.json"
    csv_path = output_dir / f"{args.output_stem}.csv"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    columns = list(rows[0]) if rows else []
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            encoded = dict(row)
            encoded["violations"] = "; ".join(row["violations"])
            writer.writerow(encoded)
    print(json.dumps({key: report[key] for key in (
        "cases", "successes", "invariant_violations", "provenance"
    )}, ensure_ascii=False))
    return 0 if report["invariant_violations"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
