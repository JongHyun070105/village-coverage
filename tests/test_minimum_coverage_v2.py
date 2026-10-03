from pathlib import Path

from backend import scheduling
from backend.minimum_coverage import (
    binary_search_minimum_budget,
    classify_area_gaps,
    minimum_coverage_comparison,
)
from scripts.run_stress_tests import generate_scenario_data

THRESHOLD = 1_234_567


def monotone_probe(budget: int) -> dict:
    met = budget >= THRESHOLD
    return {"minimum_coverage_met": met, "optimality_proven": True,
            "solver_status": "OPTIMAL"}


def test_binary_search_finds_minimum_within_tolerance():
    result = binary_search_minimum_budget(monotone_probe, lower_won=0, upper_won=5_000_000)
    assert result["status"] == "FOUND_WITHIN_TOLERANCE"
    assert THRESHOLD <= result["minimum_budget_won"] <= THRESHOLD + 10_000
    assert result["money_alone_insufficient"] is False
    assert len(result["probes"]) <= 18


def test_unproven_failures_only_yield_an_upper_bound():
    def probe(budget: int) -> dict:
        met = budget >= THRESHOLD
        return {"minimum_coverage_met": met, "optimality_proven": False,
                "solver_status": "TIME_LIMIT" if not met else "FEASIBLE"}

    result = binary_search_minimum_budget(probe, lower_won=0, upper_won=5_000_000)
    assert result["status"] == "UPPER_BOUND_ONLY"
    assert result["minimum_budget_won"] is None
    assert result["upper_bound_won"] >= THRESHOLD


def test_relaxation_proof_makes_a_failed_probe_conclusive():
    def probe(budget: int) -> dict:
        met = budget >= THRESHOLD
        return {
            "minimum_coverage_met": met, "optimality_proven": False,
            "minimum_frequency_met_areas": 3 if met else 2, "unmet_minimum_frequency_areas":
            0 if met else 1,
            "decomposition": {"stage_a_status": "OPTIMAL",
                              "stage_a_components": {"met_count": 3 if met else 2}},
        }

    result = binary_search_minimum_budget(probe, lower_won=0, upper_won=5_000_000)
    assert result["status"] == "FOUND_WITHIN_TOLERANCE"


def test_money_cannot_fix_a_gap_at_the_upper_bound():
    result = binary_search_minimum_budget(
        lambda _b: {"minimum_coverage_met": False, "optimality_proven": True},
        lower_won=0, upper_won=10_000_000,
    )
    assert result["status"] == "NOT_MET_AT_UPPER_BOUND"
    assert result["money_alone_insufficient"] is True


def plan_with(breakdown: dict, **extra) -> dict:
    return {"feasibility_breakdown": breakdown, **extra}


def test_non_monetary_reasons_are_classified():
    plan = plan_with({
        "a1": {"primary_reason": "NO_COMPATIBLE_PROVIDER", "secondary_reasons": [],
               "money_resolvable": False},
        "a2": {"primary_reason": "MONEY_SHORTAGE", "secondary_reasons": [],
               "money_resolvable": True},
        "a3": {"primary_reason": "ROUTE_UNAVAILABLE", "secondary_reasons":
               ["TIME_WINDOW_CONFLICT"], "money_resolvable": False},
    })
    rows = {row["area_id"]: row for row in classify_area_gaps(plan)}
    assert rows["a1"]["non_monetary_codes"] == ["NO_PROVIDER"]
    assert rows["a2"]["money_resolvable"] is True and rows["a2"]["non_monetary_codes"] == []
    assert rows["a3"]["non_monetary_codes"] == ["NO_ROUTE", "TIME_WINDOW"]
    comparison = minimum_coverage_comparison(
        plan={**plan, "required_budget_status": "INFEASIBLE",
              "required_budget_reason": "PROVIDER_CAPACITY_OR_TIME"},
        budget_won=1_000_000, legacy_estimate_won=None, legacy_status="NOT_PROVEN")
    assert comparison["money_alone_insufficient"] is True
    assert comparison["money_alone_message"] == "예산 증액만으로는 해결되지 않습니다."
    assert comparison["non_monetary_scope"] == "BLOCKING"
    unproven = minimum_coverage_comparison(
        plan=plan, budget_won=1_000_000, legacy_estimate_won=None, legacy_status="NOT_PROVEN")
    assert unproven["money_alone_insufficient"] is None
    assert unproven["non_monetary_scope"] == "UNVERIFIED"


def test_theoretical_and_schedule_feasible_costs_are_kept_separate():
    plan = plan_with({}, required_budget_won=3_500_000, required_budget_status="CALCULATED",
                     money_only_minimum_won=3_100_000)
    comparison = minimum_coverage_comparison(
        plan=plan, budget_won=3_000_000, legacy_estimate_won=4_600_000,
        legacy_status="CALCULATED")
    assert comparison["theoretical_minimum_cost"]["value_won"] == 3_100_000
    assert comparison["schedule_feasible_minimum_cost"]["value_won"] == 3_500_000
    assert comparison["difference_won"] == 400_000
    assert comparison["additional_budget_needed_won"] == 500_000
    assert comparison["money_alone_insufficient"] is False
    assert comparison["non_monetary_scope"] == "BINDING_AT_CURRENT_BUDGET"
    assert comparison["legacy_monthly_estimate"]["value_won"] == 4_600_000


def test_unproven_schedule_cost_is_not_shown_as_a_number():
    plan = plan_with({}, required_budget_won=None, required_budget_status="NOT_PROVEN",
                     money_only_minimum_won=5)
    comparison = minimum_coverage_comparison(
        plan=plan, budget_won=1, legacy_estimate_won=5, legacy_status="CALCULATED")
    assert comparison["schedule_feasible_minimum_cost"]["value_won"] is None
    assert comparison["difference_won"] is None


def test_all_providers_declining_is_reported_as_non_monetary(tmp_path: Path):
    areas, providers, connection, budget, policy, fallback, _ = generate_scenario_data(
        16, 3, "A", 20261002, tmp_path / "decline.sqlite")
    for provider in providers:
        provider["availability"] = []
    try:
        plan = scheduling.generate_provider_schedule(
            areas, providers, connection, budget * 10, "minimum_coverage", policy,
            allow_route_fallback=fallback, max_solver_seconds=1.0, route_strategy="decomposed")
    finally:
        connection.close()
    assert plan["served_units"] == 0
    assert plan["minimum_coverage_met"] is False
    comparison = minimum_coverage_comparison(
        plan=plan, budget_won=budget * 10, legacy_estimate_won=None,
        legacy_status="NOT_PROVEN")
    assert comparison["money_alone_insufficient"] is True
    codes = {item["code"] for item in comparison["non_monetary_failures"]}
    assert codes & {"NO_PROVIDER", "NO_CAPACITY", "TIME_WINDOW"}
