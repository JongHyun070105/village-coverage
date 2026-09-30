#!/usr/bin/env python3
"""Reproduce the Pre-R&D allocation comparisons from the checked-in demo inputs."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.demand import assess_evidence  # noqa: E402
from backend.optimization import (  # noqa: E402
    SERVICE_COST_WON,
    derive_trip_costs,
    evaluate_scenarios,
)
from backend.travel import connect  # noqa: E402

BUDGETS = (4_000_000, 5_000_000, 6_000_000, 7_000_000)


def naive_request_count(
    areas: list[dict[str, Any]], providers: list[dict[str, Any]], trips, budget: int
) -> dict[str, Any]:
    remaining_capacity = sum(int(provider["capacity_per_month"]) for provider in providers)
    spend = units = beneficiaries = travel_time_s = covered = 0
    by_area: dict[str, int] = {str(area["id"]): 0 for area in areas}
    for area in sorted(
        areas, key=lambda item: (-int(item["demand_observation_count"]), str(item["id"]))
    ):
        area_id = str(area["id"])
        trip_cost = trips[area_id].cost_won
        one_unit_cost = SERVICE_COST_WON[area["service_type"]]
        area_spent = 0
        while (
            by_area[area_id]
            < min(int(area["demand_observation_count"]), int(area["simulated_monthly_demand"]))
            and remaining_capacity > 0
            and spend + one_unit_cost + (trip_cost if by_area[area_id] == 0 else 0) <= budget
        ):
            incremental_trip = trip_cost if by_area[area_id] == 0 else 0
            spend += one_unit_cost + incremental_trip
            area_spent += one_unit_cost + incremental_trip
            by_area[area_id] += 1
            units += 1
            remaining_capacity -= 1
        if by_area[area_id]:
            covered += 1
            beneficiaries += by_area[area_id] * int(
                area.get("simulated_beneficiaries_per_service", 1)
            )
            travel_time_s += trips[area_id].duration_s
    low_data_ids = {str(area["id"]) for area in areas if area.get("needs_survey")}
    low_data_areas = [area for area in areas if str(area["id"]) in low_data_ids]
    low_data_covered = sum(by_area[area_id] > 0 for area_id in low_data_ids)
    return {
        "method": "Naive request-count allocation",
        "budget_won": budget,
        "budget_spent_won": spend,
        "service_units": units,
        "beneficiaries": beneficiaries,
        "covered_villages": covered,
        "uncovered_villages": len(areas) - covered,
        "travel_time_s": travel_time_s,
        "low_data_area_count": len(low_data_areas),
        "low_data_areas_covered": low_data_covered,
        "low_data_coverage_rate": round(low_data_covered / len(low_data_areas), 4)
        if low_data_areas
        else None,
        "assignments": by_area,
    }


def main() -> int:
    try:
        demo = json.loads((ROOT / "data" / "demo.json").read_text(encoding="utf-8"))
        connection = connect()
        hub_id, trips = derive_trip_costs(demo["areas"], connection)
    except Exception as exc:
        print(f"Experiments need demo data and a complete road cache ({type(exc).__name__}).")
        return 2

    experiment_one_budget = 5_000_000
    one_scenarios = evaluate_scenarios(
        demo["areas"], demo["providers"], connection, experiment_one_budget
    )
    naive = naive_request_count(demo["areas"], demo["providers"], trips, experiment_one_budget)
    balanced = one_scenarios["scenario_results"]["balanced"]
    balanced_assignments = {
        item["area_id"]: item["served_units"] for item in balanced["assignments"]
    }
    low_data_ids = {str(area["id"]) for area in demo["areas"] if area.get("needs_survey")}
    low_data_served = sum(balanced_assignments[area_id] > 0 for area_id in low_data_ids)
    balanced_comparison = {
        "method": "VillageCoverage balanced",
        "budget_won": experiment_one_budget,
        "budget_spent_won": balanced["budget_spent_won"],
        "service_units": balanced["served_units"],
        "beneficiaries": balanced["beneficiaries"],
        "covered_villages": balanced["covered_villages"],
        "uncovered_villages": balanced["uncovered_villages"],
        "travel_time_s": balanced["travel_time_s"],
        "low_data_area_count": len(low_data_ids),
        "low_data_areas_covered": low_data_served,
        "low_data_coverage_rate": round(low_data_served / len(low_data_ids), 4)
        if low_data_ids
        else None,
        "assignments": balanced_assignments,
    }

    budget_sensitivity = []
    for budget in BUDGETS:
        result = evaluate_scenarios(demo["areas"], demo["providers"], connection, budget)
        for scenario, metrics in result["scenario_results"].items():
            budget_sensitivity.append(
                {
                    "budget_won": budget,
                    "scenario": scenario,
                    "service_fulfillment_rate": metrics["service_fulfillment_rate"],
                    "served_units": metrics["served_units"],
                    "unserved_villages": metrics["uncovered_villages"],
                    "covered_villages": metrics["covered_villages"],
                    "beneficiaries": metrics["beneficiaries"],
                    "travel_time_s": metrics["travel_time_s"],
                    "travel_cost_won": metrics["travel_cost_won"],
                    "additional_budget_won": metrics["additional_budget_won"],
                    "required_budget_won": metrics["required_budget_won"],
                    "minimum_coverage_met": metrics["minimum_coverage_met"],
                }
            )

    low_data_example = min(
        demo["areas"], key=lambda area: (int(area["demand_observation_count"]), str(area["id"]))
    )
    assessment = assess_evidence(
        observation_count=int(low_data_example["demand_observation_count"]),
        source_diversity=1,
        missingness=0.0,
        latest_observation_date=None,
    )
    low_data_case = {
        "area_id": low_data_example["id"],
        "simulated_observation_count": low_data_example["demand_observation_count"],
        "modeled_service_need": low_data_example["simulated_monthly_demand"],
        "assessment_status": assessment.status,
        "needs_survey": assessment.needs_survey,
        "system_keeps_demand_separate_from_observation_count": True,
        "naive_treated_observation_count_as_demand": True,
        "naive_allocated_units": naive["assignments"][str(low_data_example["id"])],
        "balanced_allocated_units": balanced_assignments[str(low_data_example["id"])],
    }

    result = {
        "experiment_scope": (
            "SIMULATED FOR PRE-R&D; no household survey or provider operating data was collected."
        ),
        "region": demo["region"],
        "seed": demo["planning_defaults"]["seed"],
        "road_route_source": "Kakao Mobility directions road summaries cached in local SQLite.",
        "simulated_hub_area_id": hub_id,
        "experiment_1_naive_vs_villagecoverage": {
            "budget_won": experiment_one_budget,
            "low_data_definition": (
                "Synthetic observation count below four; shown as survey required."
            ),
            "naive": naive,
            "villagecoverage_balanced": balanced_comparison,
        },
        "experiment_2_budget_sensitivity": budget_sensitivity,
        "experiment_3_low_data_protection": low_data_case,
        "scenario_assignments_are_deterministic": True,
    }
    json_path = ROOT / "artifacts" / "experiment_results.json"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    csv_path = ROOT / "artifacts" / "experiment_results.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "experiment",
                "budget_won",
                "method",
                "scenario",
                "served_units",
                "service_fulfillment_rate",
                "covered_villages",
                "unserved_villages",
                "beneficiaries",
                "travel_time_s",
                "travel_cost_won",
                "additional_budget_won",
                "required_budget_won",
                "minimum_coverage_met",
            ],
        )
        writer.writeheader()
        for row in (naive, balanced_comparison):
            writer.writerow(
                {
                    "experiment": "naive_vs_balanced",
                    "budget_won": row["budget_won"],
                    "method": row["method"],
                    "served_units": row["service_units"],
                    "service_fulfillment_rate": round(
                        row["service_units"]
                        / max(sum(a["simulated_monthly_demand"] for a in demo["areas"]), 1),
                        4,
                    ),
                    "covered_villages": row["covered_villages"],
                    "unserved_villages": row["uncovered_villages"],
                    "beneficiaries": row["beneficiaries"],
                    "travel_time_s": row["travel_time_s"],
                    "travel_cost_won": "",
                }
            )
        for row in budget_sensitivity:
            writer.writerow(
                {
                    "experiment": "budget_sensitivity",
                    "budget_won": row["budget_won"],
                    "scenario": row["scenario"],
                    "served_units": row["served_units"],
                    "service_fulfillment_rate": row["service_fulfillment_rate"],
                    "covered_villages": row["covered_villages"],
                    "unserved_villages": row["unserved_villages"],
                    "beneficiaries": row["beneficiaries"],
                    "travel_time_s": row["travel_time_s"],
                    "travel_cost_won": row["travel_cost_won"],
                    "additional_budget_won": row["additional_budget_won"],
                    "required_budget_won": row["required_budget_won"],
                    "minimum_coverage_met": row["minimum_coverage_met"],
                }
            )
    connection.close()
    print(
        "Wrote reproducible experiment results: "
        f"{json_path.relative_to(ROOT)}, {csv_path.relative_to(ROOT)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
