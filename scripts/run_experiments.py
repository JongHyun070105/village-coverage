#!/usr/bin/env python3
"""Reproduce the fixed pilot comparison and synthetic robustness sensitivity."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from statistics import mean
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.demand import assess_evidence  # noqa: E402
from backend.optimization import evaluate_scenarios  # noqa: E402
from backend.simulation import (  # noqa: E402
    REFERENCE_SEED,
    simulated_operating_profile,
    simulated_providers_for_seed,
)
from backend.travel import connect  # noqa: E402

BUDGETS = (4_000_000, 5_000_000, 6_000_000, 7_000_000)
ROBUSTNESS_SEEDS = tuple(range(REFERENCE_SEED, REFERENCE_SEED + 21))
ROBUSTNESS_BUDGET = 5_000_000


def _low_data_metrics(result: dict[str, Any], areas: list[dict[str, Any]]) -> tuple[int, int]:
    survey_ids = {str(area["id"]) for area in areas if area.get("needs_survey")}
    covered = sum(
        row["covered"] and row["area_id"] in survey_ids for row in result["assignments"]
    )
    return len(survey_ids), covered


def _sensitivity_row(
    budget: int, scenario: str, result: dict[str, Any], areas: list[dict[str, Any]]
) -> dict[str, Any]:
    survey_count, survey_covered = _low_data_metrics(result, areas)
    return {
        "budget_won": budget,
        "scenario": scenario,
        "service_fulfillment_rate": result["service_fulfillment_rate"],
        "served_units": result["served_units"],
        "covered_villages": result["covered_villages"],
        "unserved_villages": result["uncovered_villages"],
        "survey_required_areas": survey_count,
        "survey_required_covered": survey_covered,
        "travel_time_s": result["travel_time_s"],
        "travel_cost_won": result["travel_cost_won"],
        "additional_budget_won": result["additional_budget_won"],
        "required_budget_won": result["required_budget_won"],
        "minimum_coverage_met": result["minimum_coverage_met"],
    }


def _multi_seed_sensitivity(
    areas: list[dict[str, Any]], providers: list[dict[str, Any]], connection
) -> dict[str, Any]:
    per_seed = []
    for seed in ROBUSTNESS_SEEDS:
        synthetic_areas = [
            {**area, **simulated_operating_profile(area, seed)} for area in areas
        ]
        synthetic_providers = simulated_providers_for_seed(providers, seed)
        results = evaluate_scenarios(
            synthetic_areas, synthetic_providers, connection, ROBUSTNESS_BUDGET
        )["scenario_results"]
        efficiency = results["efficiency"]
        balanced = results["balanced"]
        minimum = results["minimum_coverage"]
        survey_count, survey_covered = _low_data_metrics(balanced, synthetic_areas)
        per_seed.append(
            {
                "seed": seed,
                "efficiency_service_fulfillment_rate": efficiency["service_fulfillment_rate"],
                "efficiency_served_units": efficiency["served_units"],
                "balanced_service_fulfillment_rate": balanced["service_fulfillment_rate"],
                "balanced_covered_areas": balanced["covered_villages"],
                "balanced_survey_required_areas": survey_count,
                "balanced_survey_required_covered": survey_covered,
                "balanced_survey_coverage_rate": round(survey_covered / survey_count, 4)
                if survey_count
                else None,
                "balanced_travel_cost_won": balanced["travel_cost_won"],
                "minimum_coverage_required_budget_won": minimum["required_budget_won"],
            }
        )
    requirements = [row["minimum_coverage_required_budget_won"] for row in per_seed]
    survey_rates = [
        row["balanced_survey_coverage_rate"]
        for row in per_seed
        if row["balanced_survey_coverage_rate"] is not None
    ]
    return {
        "scope": (
            "SIMULATED SYNTHETIC SENSITIVITY ONLY. Public pilot population, households, "
            "facility anchors, and cached road routes are fixed; synthetic observation "
            "counts, modeled service need, service type, and provider capacity vary by seed."
        ),
        "budget_won": ROBUSTNESS_BUDGET,
        "reference_seed": REFERENCE_SEED,
        "additional_seed_count": len(ROBUSTNESS_SEEDS) - 1,
        "seed_count": len(ROBUSTNESS_SEEDS),
        "seeds": list(ROBUSTNESS_SEEDS),
        "aggregate": {
            "efficiency_mean_service_fulfillment_rate": round(
                mean(row["efficiency_service_fulfillment_rate"] for row in per_seed), 4
            ),
            "balanced_mean_service_areas": round(
                mean(row["balanced_covered_areas"] for row in per_seed), 2
            ),
            "balanced_mean_survey_required_coverage_rate": round(mean(survey_rates), 4),
            "balanced_mean_travel_cost_won": round(
                mean(row["balanced_travel_cost_won"] for row in per_seed)
            ),
            "minimum_coverage_required_budget_mean_won": round(mean(requirements)),
            "minimum_coverage_required_budget_min_won": min(requirements),
            "minimum_coverage_required_budget_max_won": max(requirements),
        },
        "per_seed": per_seed,
    }


def main() -> int:
    try:
        demo = json.loads((ROOT / "data" / "demo.json").read_text(encoding="utf-8"))
        connection = connect()
    except Exception as exc:
        print(f"Experiments need demo data and a complete road cache ({type(exc).__name__}).")
        return 2

    reference_budget = 5_000_000
    reference = evaluate_scenarios(
        demo["areas"], demo["providers"], connection, reference_budget
    )
    baseline = reference["request_count_baseline"]
    balanced = reference["scenario_results"]["balanced"]
    survey_count, survey_covered = _low_data_metrics(balanced, demo["areas"])
    baseline_survey_count = baseline["survey_required_areas"]
    baseline_survey_covered = baseline["survey_required_covered"]

    budget_sensitivity = []
    for budget in BUDGETS:
        scenario_results = evaluate_scenarios(
            demo["areas"], demo["providers"], connection, budget
        )["scenario_results"]
        for scenario, metrics in scenario_results.items():
            budget_sensitivity.append(_sensitivity_row(budget, scenario, metrics, demo["areas"]))

    low_data_example = min(
        demo["areas"], key=lambda area: (int(area["demand_observation_count"]), str(area["id"]))
    )
    assessment = assess_evidence(
        observation_count=int(low_data_example["demand_observation_count"]),
        source_diversity=1,
        missingness=0.0,
        latest_observation_date=None,
    )
    area_id = str(low_data_example["id"])
    multi_seed = _multi_seed_sensitivity(demo["areas"], demo["providers"], connection)
    result = {
        "experiment_scope": (
            "SIMULATED FOR PRE-R&D; allocation demand, observations, supply, prices, and "
            "operating assumptions are synthetic. Public statistics and cached route matrix "
            "are fixed pilot inputs. No real-world effect claim is made."
        ),
        "region": demo["region"],
        "seed": demo["planning_defaults"]["seed"],
        "road_route_source": "Kakao Mobility directions road summaries cached in local SQLite.",
        "experiment_1_request_count_vs_balanced": {
            "budget_won": reference_budget,
            "survey_required_definition": "Synthetic observation count below four.",
            "request_count_baseline": {
                "served_units": baseline["served_units"],
                "covered_areas": baseline["covered_villages"],
                "survey_required_areas": baseline_survey_count,
                "survey_required_covered": baseline_survey_covered,
                "travel_cost_won": baseline["travel_cost_won"],
                "travel_time_s": baseline["travel_time_s"],
            },
            "balanced": {
                "served_units": balanced["served_units"],
                "covered_areas": balanced["covered_villages"],
                "survey_required_areas": survey_count,
                "survey_required_covered": survey_covered,
                "travel_cost_won": balanced["travel_cost_won"],
                "travel_time_s": balanced["travel_time_s"],
            },
            "request_count_service_units_by_area": baseline["service_units_by_area"],
        },
        "experiment_2_budget_sensitivity": budget_sensitivity,
        "experiment_3_low_data_protection": {
            "area_id": area_id,
            "synthetic_observation_count": low_data_example["demand_observation_count"],
            "synthetic_modeled_monthly_need": low_data_example["simulated_monthly_demand"],
            "assessment_status": assessment.status,
            "needs_survey": assessment.needs_survey,
            "request_count_baseline_allocated_units": baseline["service_units_by_area"][area_id],
            "balanced_allocated_units": next(
                row["served_units"] for row in balanced["assignments"] if row["area_id"] == area_id
            ),
        },
        "experiment_4_multi_seed_robustness": multi_seed,
        "scenario_assignments_are_deterministic": True,
    }

    json_path = ROOT / "artifacts" / "experiment_results.json"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    csv_path = ROOT / "artifacts" / "experiment_results.csv"
    columns = [
        "experiment", "seed", "budget_won", "scenario", "service_fulfillment_rate",
        "served_units", "covered_villages", "unserved_villages", "survey_required_areas",
        "survey_required_covered", "travel_time_s", "travel_cost_won",
        "additional_budget_won", "required_budget_won", "minimum_coverage_met",
    ]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writeheader()
        for row in budget_sensitivity:
            writer.writerow({"experiment": "budget_sensitivity", **row})
        for row in multi_seed["per_seed"]:
            writer.writerow(
                {
                    "experiment": "synthetic_multi_seed_robustness",
                    "seed": row["seed"],
                    "budget_won": ROBUSTNESS_BUDGET,
                    "scenario": "efficiency",
                    "service_fulfillment_rate": row["efficiency_service_fulfillment_rate"],
                    "served_units": row["efficiency_served_units"],
                }
            )
            writer.writerow(
                {
                    "experiment": "synthetic_multi_seed_robustness",
                    "seed": row["seed"],
                    "budget_won": ROBUSTNESS_BUDGET,
                    "scenario": "balanced",
                    "service_fulfillment_rate": row["balanced_service_fulfillment_rate"],
                    "covered_villages": row["balanced_covered_areas"],
                    "survey_required_areas": row["balanced_survey_required_areas"],
                    "survey_required_covered": row["balanced_survey_required_covered"],
                    "travel_cost_won": row["balanced_travel_cost_won"],
                }
            )
    connection.close()
    print(f"Wrote {json_path.relative_to(ROOT)} and {csv_path.relative_to(ROOT)}")
    print(json.dumps(multi_seed["aggregate"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
