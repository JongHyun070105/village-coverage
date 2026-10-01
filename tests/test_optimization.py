from __future__ import annotations

from copy import deepcopy

import pytest

from backend import optimization
from backend.optimization import _vulnerability_points, derive_trip_costs, evaluate_scenarios
from backend.settings import BALANCED_SCENARIO_WEIGHTS, PlanningPolicy
from backend.travel import Route, connect, put_cached


def build_fixture(tmp_path, capacities=(100, 100, 100)):
    areas = [
        {
            "id": f"area-{index}",
            "anchor_lat": 36.5,
            "anchor_lng": 126.6 + index * 0.1,
            "simulated_monthly_demand": 8,
            "service_type": "daily_necessities",
            "elderly_ratio_65": 0.2 + index * 0.35,
            "single_households_65_plus": index * 15,
            "population_total": 100,
            "needs_survey": index == 2,
            "demand_observation_count": (8, 4, 2)[index],
        }
        for index in range(3)
    ]
    providers = [
        {"id": f"provider-{index}", "capacity_per_month": capacity}
        for index, capacity in enumerate(capacities)
    ]
    distances = {(0, 1): (10_000, 600), (1, 2): (10_000, 600), (0, 2): (20_000, 1_200)}
    connection = connect(tmp_path / "test.sqlite")
    for origin_index, origin in enumerate(areas):
        for destination_index, destination in enumerate(areas):
            if origin_index == destination_index:
                distance, duration = 0, 0
            else:
                key = tuple(sorted((origin_index, destination_index)))
                distance, duration = distances[key]
            put_cached(
                connection,
                origin,
                destination,
                Route(origin["id"], destination["id"], distance, duration),
            )
    return areas, providers, connection


def test_scenarios_obey_budget_capacity_demand_and_seed_invariants(tmp_path) -> None:
    areas, providers, connection = build_fixture(tmp_path, capacities=(2, 2, 2))
    first = evaluate_scenarios(areas, providers, connection, 600_000)
    second = evaluate_scenarios(deepcopy(areas), deepcopy(providers), connection, 600_000)
    assert first["scenario_results"] == second["scenario_results"]
    total_capacity = sum(provider["capacity_per_month"] for provider in providers)
    total_demand = sum(area["simulated_monthly_demand"] for area in areas)
    for result in first["scenario_results"].values():
        assert result["budget_spent_won"] <= 600_000
        assert result["served_units"] <= total_capacity
        assert result["served_units"] <= total_demand
        assert result["budget_remaining_won"] >= 0
        assert result["travel_time_s"] >= 0
        assert "beneficiaries" not in result
        assert all(assignment["served_units"] >= 0 for assignment in result["assignments"])
        assert (
            sum(assignment["served_units"] for assignment in result["assignments"])
            == result["served_units"]
        )
    connection.close()


def test_scenarios_report_full_demand_funding_gap_from_provider_and_hub_costs(tmp_path) -> None:
    areas, providers, connection = build_fixture(tmp_path)

    results = evaluate_scenarios(areas, providers, connection, 600_000)["scenario_results"]

    for result in results.values():
        assert result["full_demand_budget_status"] == "CALCULATED"
        assert result["full_demand_required_budget_won"] == 6_082_672
        assert result["full_demand_budget_gap_won"] == 5_482_672
        assert result["full_demand_budget_model"] == "CENTRAL_HUB_ROUND_TRIP_ESTIMATE"
    connection.close()


def test_full_demand_funding_reports_infeasible_service_supply_without_zero(tmp_path) -> None:
    areas, providers, connection = build_fixture(tmp_path)
    for provider in providers:
        provider["supported_services"] = ["laundry"]

    results = evaluate_scenarios(areas, providers, connection, 10_000_000)["scenario_results"]

    for result in results.values():
        assert result["full_demand_budget_status"] == "INFEASIBLE"
        assert result["full_demand_required_budget_won"] is None
        assert result["full_demand_budget_gap_won"] is None
        assert result["full_demand_failure_reason"] == "NO_SUPPORTED_PROVIDER"
    connection.close()


def test_full_demand_funding_distinguishes_no_provider_from_insufficient_capacity(tmp_path) -> None:
    areas, providers, connection = build_fixture(tmp_path, capacities=(1, 0, 0))

    results = evaluate_scenarios(areas, providers, connection, 10_000_000)["scenario_results"]

    for result in results.values():
        assert result["full_demand_budget_status"] == "INFEASIBLE"
        assert result["full_demand_required_budget_won"] is None
        assert result["full_demand_budget_gap_won"] is None
        assert result["full_demand_failure_reason"] == "PROVIDER_CAPACITY_OR_SERVICE_MIX"
    connection.close()


def test_full_demand_funding_reports_supported_service_with_zero_capacity(tmp_path) -> None:
    areas, providers, connection = build_fixture(tmp_path, capacities=(0, 0, 0))

    results = evaluate_scenarios(areas, providers, connection, 10_000_000)["scenario_results"]

    for result in results.values():
        assert result["full_demand_budget_status"] == "INFEASIBLE"
        assert result["full_demand_required_budget_won"] is None
        assert result["full_demand_budget_gap_won"] is None
        assert result["full_demand_failure_reason"] == "PROVIDER_CAPACITY_OR_SERVICE_MIX"
    connection.close()


def test_full_demand_funding_withholds_amount_when_optimality_is_unproven(
    tmp_path, monkeypatch
) -> None:
    areas, providers, connection = build_fixture(tmp_path)
    real_solver_factory = optimization._new_solver

    class FeasibleStatusSolver:
        def __init__(self) -> None:
            self.solver = real_solver_factory()

        def solve(self, model):
            status = self.solver.solve(model)
            if status == optimization.cp_model.OPTIMAL:
                return optimization.cp_model.FEASIBLE
            return status

        def value(self, variable):
            return self.solver.value(variable)

        def status_name(self, status):
            return self.solver.status_name(status)

    monkeypatch.setattr(optimization, "_new_solver", FeasibleStatusSolver)

    results = evaluate_scenarios(areas, providers, connection, 10_000_000)["scenario_results"]

    for result in results.values():
        assert result["full_demand_budget_status"] == "NOT_PROVEN"
        assert result["full_demand_required_budget_won"] is None
        assert result["full_demand_budget_gap_won"] is None
        assert result["full_demand_failure_reason"] == "OPTIMALITY_NOT_PROVEN"
    connection.close()


def test_balanced_scenario_returns_feasible_incumbent_without_claiming_optimality(
    tmp_path, monkeypatch
) -> None:
    areas, providers, connection = build_fixture(tmp_path)
    _, trips = derive_trip_costs(areas, connection)
    real_solver_factory = optimization._new_solver

    class FeasibleStatusSolver:
        def __init__(self) -> None:
            self.solver = real_solver_factory()

        def solve(self, model):
            status = self.solver.solve(model)
            if status == optimization.cp_model.OPTIMAL:
                return optimization.cp_model.FEASIBLE
            return status

        def value(self, variable):
            return self.solver.value(variable)

        def status_name(self, status):
            return self.solver.status_name(status)

    monkeypatch.setattr(optimization, "_new_solver", FeasibleStatusSolver)
    try:
        result = optimization._solve_scenario(
            areas, providers, trips, 500_000, "balanced", PlanningPolicy()
        )
        assert result["solver_status"] == "FEASIBLE"
        assert result["optimality_proven"] is False
        assert result["budget_spent_won"] <= 500_000
        assert sum(item["served_units"] for item in result["assignments"]) == result["served_units"]
    finally:
        connection.close()


def test_scenarios_report_hub_round_trip_distance_and_max_area_saturation(tmp_path) -> None:
    areas, providers, connection = build_fixture(tmp_path)
    _, trips = derive_trip_costs(areas, connection)
    results = evaluate_scenarios(areas, providers, connection, 500_000)["scenario_results"]

    for result in results.values():
        assert result["travel_distance_m"] == sum(
            assignment["travel_distance_m"] for assignment in result["assignments"]
        )
        for assignment in result["assignments"]:
            assert assignment["travel_distance_m"] == (
                trips[assignment["area_id"]].distance_m * assignment["served_units"]
            )
        expected_max_saturation = max(
            (
                -(-assignment["served_units"] * 10_000 // assignment["demand_units"])
                for assignment in result["assignments"]
                if assignment["demand_units"] > 0
            ),
            default=0,
        )
        assert result["max_area_demand_saturation_basis_points"] == expected_max_saturation
    connection.close()


def test_scenarios_have_distinct_policy_outcomes(tmp_path) -> None:
    areas, providers, connection = build_fixture(tmp_path)
    result = evaluate_scenarios(areas, providers, connection, 500_000)["scenario_results"]
    allocations = {
        key: tuple(item["served_units"] for item in value["assignments"])
        for key, value in result.items()
    }
    assert allocations["efficiency"] != allocations["balanced"]
    assert result["minimum_coverage"]["covered_villages"] > result["efficiency"]["covered_villages"]
    connection.close()


def test_balanced_vulnerability_scale_is_centralized_and_normalized() -> None:
    area = {
        "elderly_ratio_65": 0.5,
        "population_total": 100,
        "single_households_65_plus": 20,
        "needs_survey": True,
    }
    assert BALANCED_SCENARIO_WEIGHTS.vulnerability_points_per_share == 500
    assert _vulnerability_points(area) == 350
    assert (
        _vulnerability_points(area, elderly_priority_weight=1000, single_elderly_priority_weight=0)
        == 500
    )
    assert (
        _vulnerability_points(area, elderly_priority_weight=0, single_elderly_priority_weight=1000)
        == 200
    )


def test_balanced_preserves_maximum_service_volume_and_prioritizes_area_count(tmp_path) -> None:
    areas, providers, connection = build_fixture(tmp_path)
    results = evaluate_scenarios(areas, providers, connection, 500_000)["scenario_results"]
    assert results["balanced"]["served_units"] == results["efficiency"]["served_units"]
    assert results["balanced"]["covered_villages"] >= results["efficiency"]["covered_villages"]
    connection.close()


def test_balanced_policy_weights_change_the_selected_vulnerable_area(tmp_path) -> None:
    areas, providers, connection = build_fixture(tmp_path, capacities=(1, 0, 0))
    for area in areas:
        area["simulated_monthly_demand"] = 1
        area["needs_survey"] = False
        area["single_households_total"] = 10
        area["single_households_65_plus"] = 0
    areas[0]["elderly_ratio_65"] = 1.0
    areas[1]["elderly_ratio_65"] = 0.0
    areas[1]["single_households_65_plus"] = 10

    elderly_first = PlanningPolicy(
        elderly_priority_weight=1000,
        single_elderly_household_priority_weight=0,
        survey_required_protection_weight=0,
    )
    single_elderly_first = PlanningPolicy(
        elderly_priority_weight=0,
        single_elderly_household_priority_weight=1000,
        survey_required_protection_weight=0,
    )
    elderly_result = evaluate_scenarios(areas, providers, connection, 500_000, elderly_first)[
        "scenario_results"
    ]["balanced"]
    single_result = evaluate_scenarios(areas, providers, connection, 500_000, single_elderly_first)[
        "scenario_results"
    ]["balanced"]
    elderly_area = next(
        item["area_id"] for item in elderly_result["assignments"] if item["covered"]
    )
    single_area = next(item["area_id"] for item in single_result["assignments"] if item["covered"])
    assert elderly_area == "area-0"
    assert single_area == "area-1"
    connection.close()


def test_minimum_coverage_does_not_claim_success_below_required_budget(tmp_path) -> None:
    areas, providers, connection = build_fixture(tmp_path)
    result = evaluate_scenarios(areas, providers, connection, 300_000)["scenario_results"][
        "minimum_coverage"
    ]
    assert result["minimum_coverage_met"] is False
    assert result["uncovered_villages"] > 0
    assert result["service_gap"] == result["uncovered_villages"]
    assert result["required_budget_won"] > 300_000
    assert result["additional_budget_won"] == result["required_budget_won"] - 300_000
    connection.close()


def test_minimum_budget_achieves_all_areas_when_fully_funded(tmp_path) -> None:
    areas, providers, connection = build_fixture(tmp_path)
    _, trips = derive_trip_costs(areas, connection)
    required = sum(225_000 + trips[area["id"]].cost_won for area in areas)
    result = evaluate_scenarios(areas, providers, connection, required)["scenario_results"][
        "minimum_coverage"
    ]
    assert result["required_budget_won"] == required
    assert result["required_capacity"] == 3
    assert result["available_capacity"] == 300
    assert result["minimum_compatible_capacity"] == 3
    assert result["missing_capacity"] == 0
    assert result["additional_public_subsidy_won"] == 0
    assert result["minimum_coverage_met"]
    assert result["covered_villages"] == len(areas)
    assert result["uncovered_villages"] == 0
    connection.close()


def test_minimum_guarantee_discloses_monthly_aggregate_route_scope(tmp_path) -> None:
    areas, providers, connection = build_fixture(tmp_path)

    result = evaluate_scenarios(areas, providers, connection, 2_000_000)["scenario_results"][
        "minimum_coverage"
    ]

    assert result["minimum_coverage_met"] is True
    assert result["guarantee_scope"] == "MONTHLY_AGGREGATE_CAPACITY_ESTIMATE"
    assert result["guarantee_travel_model"] == "CENTRAL_HUB_ROUND_TRIP_ESTIMATE"
    connection.close()


def test_budget_and_demand_inputs_are_fail_closed_but_capacity_gap_is_reported(tmp_path) -> None:
    areas, providers, connection = build_fixture(tmp_path)
    with pytest.raises(ValueError, match="nonnegative"):
        evaluate_scenarios(areas, providers, connection, -1)
    infeasible = evaluate_scenarios(
        areas, [{"id": "one", "capacity_per_month": 2}], connection, 2_000_000
    )["scenario_results"]["minimum_coverage"]
    assert infeasible["guarantee_capacity_feasible"] is False
    assert infeasible["guarantee_feasible"] is False
    assert infeasible["required_capacity"] == 3
    assert infeasible["available_capacity"] == 2
    assert infeasible["missing_capacity"] == 1
    assert infeasible["required_budget_won"] is None
    assert infeasible["additional_budget_won"] is None
    assert infeasible["minimum_coverage_met"] is False
    bad_areas = deepcopy(areas)
    bad_areas[0]["simulated_monthly_demand"] = -1
    with pytest.raises(ValueError, match="negative demand"):
        evaluate_scenarios(bad_areas, providers, connection, 2_000_000)
    connection.close()


def test_zero_demand_area_makes_minimum_guarantee_not_budget_feasible(tmp_path) -> None:
    areas, providers, connection = build_fixture(tmp_path)
    areas[0]["simulated_monthly_demand"] = 0
    result = evaluate_scenarios(areas, providers, connection, 2_000_000)["scenario_results"][
        "minimum_coverage"
    ]
    assert result["guarantee_capacity_feasible"] is None
    assert result["guarantee_feasible"] is False
    assert result["required_budget_won"] is None
    assert result["additional_budget_won"] is None
    assert result["minimum_coverage_met"] is False
    connection.close()


def test_minimum_frequency_changes_guarantee_budget_and_truthful_gap(tmp_path) -> None:
    areas, providers, connection = build_fixture(tmp_path)
    _, trips = derive_trip_costs(areas, connection)
    one_visit_policy = PlanningPolicy(minimum_services_per_area=1)
    two_visit_policy = PlanningPolicy(minimum_services_per_area=2)
    one_visit_budget = evaluate_scenarios(
        areas, providers, connection, 3_000_000, one_visit_policy
    )["scenario_results"]["minimum_coverage"]["required_budget_won"]
    two_visit_budget = evaluate_scenarios(
        areas, providers, connection, 3_000_000, two_visit_policy
    )["scenario_results"]["minimum_coverage"]["required_budget_won"]
    assert two_visit_budget > one_visit_budget

    result = evaluate_scenarios(areas, providers, connection, one_visit_budget, two_visit_policy)[
        "scenario_results"
    ]["minimum_coverage"]
    assert result["minimum_services_per_area"] == 2
    assert result["minimum_coverage_met"] is False
    assert result["unmet_minimum_frequency_areas"] > 0
    assert result["service_gap"] == result["unmet_minimum_frequency_areas"]
    assert result["required_budget_won"] == two_visit_budget
    expected_two_visit_budget = sum(2 * (225_000 + trips[area["id"]].cost_won) for area in areas)
    assert two_visit_budget == expected_two_visit_budget
    assert sum(trips[area["id"]].cost_won for area in areas) < two_visit_budget
    connection.close()


def test_unmet_minimum_reason_identifies_budget_capacity_and_shared_competition(tmp_path) -> None:
    policy = PlanningPolicy(minimum_services_per_area=2)

    areas, providers, connection = build_fixture(tmp_path / "budget")
    budget_limited = evaluate_scenarios(areas, providers, connection, 1, policy)[
        "scenario_results"
    ]["balanced"]
    assert {item["constraint_reason"] for item in budget_limited["assignments"]} == {"BUDGET"}
    connection.close()

    areas, providers, connection = build_fixture(tmp_path / "capacity", capacities=(1, 0, 0))
    capacity_limited = evaluate_scenarios(areas, providers, connection, 5_000_000, policy)[
        "scenario_results"
    ]["balanced"]
    assert {item["constraint_reason"] for item in capacity_limited["assignments"]} == {
        "PROVIDER_CAPACITY"
    }
    connection.close()

    areas, providers, connection = build_fixture(tmp_path / "shared", capacities=(3, 0, 0))
    shared = evaluate_scenarios(areas, providers, connection, 5_000_000, policy)[
        "scenario_results"
    ]["minimum_coverage"]
    unmet = [item for item in shared["assignments"] if not item["minimum_frequency_met"]]
    assert unmet
    assert {item["constraint_reason"] for item in unmet} == {"SHARED_BUDGET_OR_CAPACITY"}
    connection.close()


def test_allowed_services_and_hub_travel_policy_explain_ineligible_areas(tmp_path) -> None:
    areas, providers, connection = build_fixture(tmp_path)
    areas[0]["service_type"] = "laundry"
    areas[1]["service_type"] = "daily_necessities"
    areas[2]["service_type"] = "home_repair"
    policy = PlanningPolicy(
        allowed_services=("daily_necessities", "laundry"),
        maximum_round_trip_travel_minutes=10,
    )
    scenarios = evaluate_scenarios(areas, providers, connection, 2_000_000, policy)[
        "scenario_results"
    ]
    balanced = {item["area_id"]: item for item in scenarios["balanced"]["assignments"]}
    assert balanced["area-0"]["constraint_reason"] == "MAX_TRAVEL_TIME"
    assert balanced["area-0"]["provider_assignments"] == {}
    assert balanced["area-1"]["covered"] is True
    assert balanced["area-2"]["constraint_reason"] == "SERVICE_NOT_ALLOWED"
    assert balanced["area-2"]["provider_assignments"] == {}
    assert scenarios["minimum_coverage"]["guarantee_failure_reason"] == "SERVICE_NOT_ALLOWED"
    connection.close()


def test_minimum_guarantee_reports_provider_service_mix_capacity_gap(tmp_path) -> None:
    areas, _, connection = build_fixture(tmp_path)
    areas[0]["service_type"] = "home_repair"
    areas[1]["service_type"] = "laundry"
    areas[2]["service_type"] = "home_repair"
    providers = [
        {"id": "mixed-one-round", "capacity_per_month": 1, "supported_services": None},
        {
            "id": "laundry-only",
            "capacity_per_month": 2,
            "supported_services": ["laundry"],
        },
    ]
    result = evaluate_scenarios(areas, providers, connection, 5_000_000)["scenario_results"][
        "minimum_coverage"
    ]
    assert result["guarantee_feasible"] is False
    assert result["guarantee_capacity_feasible"] is False
    assert result["guarantee_failure_reason"] == "PROVIDER_CAPACITY_OR_SERVICE_MIX"
    assert result["available_capacity"] == 3
    assert result["minimum_compatible_capacity"] == 2
    assert result["missing_capacity"] == 1
    assert result["required_budget_won"] is None
    connection.close()


def test_minimum_capacity_reassigns_flexible_provider_for_service_mix(tmp_path) -> None:
    areas, _, connection = build_fixture(tmp_path)
    areas = areas[:2]
    areas[0]["service_type"] = "laundry"
    areas[1]["service_type"] = "home_repair"
    providers = [
        {"id": "flexible", "capacity_per_month": 1, "supported_services": None},
        {
            "id": "laundry-only",
            "capacity_per_month": 1,
            "supported_services": ["laundry"],
        },
    ]

    result = evaluate_scenarios(areas, providers, connection, 5_000_000)["scenario_results"][
        "minimum_coverage"
    ]

    assert result["minimum_compatible_capacity"] == 2
    assert result["missing_capacity"] == 0
    connection.close()


def test_provider_compensation_floor_is_in_budget_and_cost_breakdown(tmp_path) -> None:
    areas, providers, connection = build_fixture(tmp_path)
    policy = PlanningPolicy(minimum_provider_compensation_won=500_000)
    results = evaluate_scenarios(areas, providers, connection, 550_000, policy)["scenario_results"]
    efficiency = results["efficiency"]
    assert efficiency["provider_minimum_compensation_won"] == 500_000
    assert efficiency["minimum_compensation_topup_won"] > 0
    assert (
        efficiency["service_cost_won"]
        + efficiency["minimum_compensation_topup_won"]
        + efficiency["travel_cost_won"]
        == efficiency["budget_spent_won"]
    )
    assert efficiency["budget_spent_won"] <= 550_000
    connection.close()


def test_provider_cost_breakdown_reconciles_to_aggregate_scenario_totals(tmp_path) -> None:
    areas, providers, connection = build_fixture(tmp_path, capacities=(2, 2, 2))
    for index, provider in enumerate(providers):
        provider["name"] = f"Synthetic Provider {index + 1}"
    results = evaluate_scenarios(areas, providers, connection, 2_500_000)["scenario_results"]

    for result in results.values():
        breakdown = result["provider_cost_breakdown"]
        assert result["provider_travel_model"] == "CENTRAL_HUB_ROUND_TRIP_ESTIMATE"
        assert len(breakdown) == len(providers)
        assert sum(item["service_rounds"] for item in breakdown) == result["served_units"]
        assert sum(item["service_cost_won"] for item in breakdown) == result["service_cost_won"]
        assert sum(item["travel_distance_m"] for item in breakdown) == result["travel_distance_m"]
        assert sum(item["travel_time_s"] for item in breakdown) == result["travel_time_s"]
        assert sum(item["travel_cost_won"] for item in breakdown) == result["travel_cost_won"]
        assert (
            sum(item["minimum_compensation_floor_won"] for item in breakdown)
            == result["provider_minimum_compensation_won"]
        )
        assert (
            sum(item["compensation_topup_won"] for item in breakdown)
            == result["minimum_compensation_topup_won"]
        )
        assert sum(item["total_cost_won"] for item in breakdown) == result["budget_spent_won"]
        assert all(
            item["compensation_paid_won"] >= item["minimum_compensation_floor_won"]
            for item in breakdown
        )
        assert all(item["provider_name"].startswith("Synthetic Provider") for item in breakdown)
    connection.close()


def test_incomplete_travel_matrix_never_uses_straight_line_distance(tmp_path) -> None:
    areas, providers, connection = build_fixture(tmp_path)
    connection.execute(
        "DELETE FROM travel_matrix WHERE origin_id = ? AND destination_id = ?", ("area-1", "area-2")
    )
    connection.commit()
    with pytest.raises(ValueError, match="directed pairs missing"):
        evaluate_scenarios(areas, providers, connection, 1_000_000)
    connection.close()
