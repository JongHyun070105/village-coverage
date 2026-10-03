#!/usr/bin/env python3
"""Counterfactual tests for low-data protection and one-survey/provider changes."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend import scheduling  # noqa: E402
from backend.allocation_stage import solve_aggregate_allocation  # noqa: E402
from backend.scheduling import BALANCED_SCHEDULE_SCORE_WEIGHTS  # noqa: E402
from backend.settings import PlanningPolicy  # noqa: E402
from backend.source_snapshots import utc_now  # noqa: E402
from scripts.run_sensitivity import build_sensitivity_fixture  # noqa: E402

BUDGET_WON = 1_500_000
MAX_SOLVER_SECONDS = 2.5


def run_plan(areas, providers, connection, scenario: str) -> dict:
    return scheduling.generate_provider_schedule(
        areas,
        providers,
        connection,
        BUDGET_WON,
        scenario,
        allow_route_fallback=True,
        include_timing=True,
        max_solver_seconds=MAX_SOLVER_SECONDS,
        route_strategy="decomposed",
    )


def summary(plan: dict) -> dict:
    included = sorted({str(row["area_id"]) for row in plan.get("rounds", [])})
    return {
        "solver_status": plan.get("solver_status"),
        "optimality_proven": bool(plan.get("optimality_proven")),
        "included_area_ids": included,
        "covered_areas": len(included),
        "served_units": plan.get("served_units", 0),
        "uncovered_areas": plan.get("uncovered_areas"),
        "gross_cost_won": plan.get("budget_spent_won"),
        "required_budget_won": plan.get("required_budget_won"),
        "required_budget_status": plan.get("required_budget_status"),
        "required_budget_model": plan.get("required_budget_model"),
        "money_only_minimum_won": plan.get("money_only_minimum_won"),
        "minimum_coverage_met": bool(plan.get("minimum_coverage_met")),
        "feasibility_breakdown": plan.get("feasibility_breakdown", {}),
    }


def unmet_reasons(plan: dict) -> dict[str, int]:
    counts: dict[str, int] = {}
    for area in (plan.get("feasibility_breakdown") or {}).values():
        reason = str(area.get("primary_reason") or "UNKNOWN")
        counts[reason] = counts.get(reason, 0) + 1
    return dict(sorted(counts.items()))


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="vc-public-value-") as directory:
        areas, providers, connection = build_sensitivity_fixture(Path(directory) / "routes.sqlite")
        low_data = [area for area in areas if area.get("needs_survey")]
        known_data = [area for area in areas if not area.get("needs_survey")]
        baseline = run_plan(areas, providers, connection, "balanced")
        efficiency = run_plan(areas, providers, connection, "efficiency")
        minimum = run_plan(areas, providers, connection, "minimum_coverage")
        policy = PlanningPolicy()
        candidates, _ = scheduling._make_candidates(
            areas, providers, scheduling._route_rows(connection), policy, None,
            allow_route_fallback=True,
        )
        money_only_upper = scheduling._minimum_budget_upper_bound(candidates, providers, policy)
        money_only = solve_aggregate_allocation(
            areas=areas,
            providers=providers,
            candidates=candidates,
            budget_won=money_only_upper,
            scenario="required_budget",
            policy=policy,
            balanced_weights=BALANCED_SCHEDULE_SCORE_WEIGHTS,
            max_seconds=MAX_SOLVER_SECONDS,
        )

        # Counterfactual: mimic the unsafe request=0 treatment by omitting low-data
        # areas. It is a planning comparison, not evidence that their demand is zero.
        request_zero = run_plan(known_data, providers, connection, "efficiency")
        added_survey_plan = None
        if low_data:
            changed = [dict(area) for area in areas]
            changed_area_id = str(low_data[0]["id"])
            for area in changed:
                if str(area["id"]) == changed_area_id:
                    area["needs_survey"] = False
                    break
            added_survey_plan = run_plan(changed, providers, connection, "balanced")

        provider_drop_plan = None
        dropped_provider = None
        if len(providers) > 1:
            dropped_provider = str(providers[0]["provider_id"])
            remaining = [
                provider for provider in providers if provider["provider_id"] != dropped_provider
            ]
            provider_drop_plan = run_plan(areas, remaining, connection, "balanced")

        report = {
            "generated_at": utc_now(),
            "provenance": "SIMULATION (controlled sensitivity fixture); NOT LOCAL RESIDENT DEMAND",
            "budget_won": BUDGET_WON,
            "max_solver_seconds": MAX_SOLVER_SECONDS,
            "area_count": len(areas),
            "low_data_area_ids": sorted(str(area["id"]) for area in low_data),
            "known_data_area_count": len(known_data),
            "counterfactual_efficiency_vs_request_zero": {
                "villagecoverage_balanced": summary(baseline),
                "efficiency_only_all_areas": summary(efficiency),
                "low_data_removed_request_zero": summary(request_zero),
                "removed_low_data_area_ids": sorted(str(area["id"]) for area in low_data),
                "interpretation": (
                    "The request=0 case omits low-data areas; it does not establish zero demand. "
                    "All figures are outputs for this synthetic fixture."
                ),
            },
            "public_value_answers": {
                "areas_excluded_by_efficiency": sorted(
                    {str(area["id"]) for area in areas}
                    - {str(row["area_id"]) for row in efficiency.get("rounds", [])}
                ),
                "areas_excluded_by_villagecoverage_balanced": sorted(
                    {str(area["id"]) for area in areas}
                    - {str(row["area_id"]) for row in baseline.get("rounds", [])}
                ),
                "additional_budget_for_schedule_feasible_minimum_won": (
                    max(0, int(minimum["required_budget_won"]) - BUDGET_WON)
                    if minimum.get("required_budget_status") == "CALCULATED"
                    else None
                ),
                "money_only_vs_schedule_minimum_difference_won": (
                    minimum["required_budget_won"] - money_only["components"]["total_cost"]
                    if minimum.get("required_budget_status") == "CALCULATED"
                    and money_only.get("status") == "OPTIMAL"
                    and (money_only.get("components") or {}).get("total_cost") is not None
                    else None
                ),
                "minimum_plan_unmet_primary_reasons": unmet_reasons(minimum),
                "survey_counterfactual": {
                    "changed_area_id": str(low_data[0]["id"]) if low_data else None,
                    "covered_area_count_delta": (
                        len({row["area_id"] for row in added_survey_plan.get("rounds", [])})
                        - len({row["area_id"] for row in baseline.get("rounds", [])})
                    ) if added_survey_plan else None,
                    "included_area_ids_before": summary(baseline)["included_area_ids"],
                    "included_area_ids_after": (
                        summary(added_survey_plan)["included_area_ids"]
                        if added_survey_plan else None
                    ),
                    "scope": "SIMULATED NEEDS_SURVEY FLAG CHANGE ONLY",
                },
                "provider_decline_counterfactual": {
                    "declined_provider_id": dropped_provider,
                    "covered_area_count_delta": (
                        len({row["area_id"] for row in provider_drop_plan.get("rounds", [])})
                        - len({row["area_id"] for row in baseline.get("rounds", [])})
                    ) if provider_drop_plan else None,
                    "unmet_primary_reasons_after": (
                        unmet_reasons(provider_drop_plan) if provider_drop_plan else None
                    ),
                },
            },
            "minimum_guarantee": summary(minimum),
            "minimum_cost_comparison": {
                "theoretical_minimum_cost": {
                    "value_won": (
                        (money_only.get("components") or {}).get("total_cost")
                        if money_only.get("status") == "OPTIMAL" else None
                    ),
                    "status": money_only.get("status"),
                    "model": "AGGREGATE_ALLOCATION_WITHOUT_CALENDAR",
                },
                "schedule_feasible_minimum_cost": {
                    "value_won": minimum.get("required_budget_won"),
                    "status": minimum.get("required_budget_status"),
                    "model": minimum.get("required_budget_model"),
                },
                "difference_won": (
                    minimum["required_budget_won"] - money_only["components"]["total_cost"]
                    if minimum.get("required_budget_status") == "CALCULATED"
                    and money_only.get("status") == "OPTIMAL"
                    and (money_only.get("components") or {}).get("total_cost") is not None
                    else None
                ),
                "interpretation": (
                    "The money-only allocation is a relaxation/lower bound; the schedule figure "
                    "adds provider-date feasibility. Values are omitted unless proven."
                ),
            },
            "one_added_survey_counterfactual": {
                "changed_area_id": str(low_data[0]["id"]) if low_data else None,
                "before": summary(baseline),
                "after": summary(added_survey_plan) if added_survey_plan else None,
                "interpretation": (
                    "Only the needs_survey planning flag changed. This is a policy sensitivity "
                    "counterfactual, not a simulated measurement of how demand changed."
                ),
            },
            "provider_decline_counterfactual": {
                "declined_provider_id": dropped_provider,
                "before": summary(baseline),
                "after": summary(provider_drop_plan) if provider_drop_plan else None,
            },
        }

    output = ROOT / "artifacts" / "public_value_experiment.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {output.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
