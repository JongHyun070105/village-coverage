from __future__ import annotations

from copy import deepcopy

import pytest

from backend.optimization import _vulnerability_points, derive_trip_costs, evaluate_scenarios
from backend.settings import BALANCED_SCENARIO_WEIGHTS
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


def test_balanced_preserves_maximum_service_volume_and_prioritizes_area_count(tmp_path) -> None:
    areas, providers, connection = build_fixture(tmp_path)
    results = evaluate_scenarios(areas, providers, connection, 500_000)["scenario_results"]
    assert results["balanced"]["served_units"] == results["efficiency"]["served_units"]
    assert results["balanced"]["covered_villages"] >= results["efficiency"]["covered_villages"]
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
    hub_id, trips = derive_trip_costs(areas, connection)
    required = sum(225_000 + trips[area["id"]].cost_won for area in areas)
    result = evaluate_scenarios(areas, providers, connection, required)["scenario_results"][
        "minimum_coverage"
    ]
    assert result["required_budget_won"] == required
    assert result["minimum_coverage_met"]
    assert result["covered_villages"] == len(areas)
    assert result["uncovered_villages"] == 0
    connection.close()


def test_budget_and_demand_inputs_are_fail_closed_but_capacity_gap_is_reported(tmp_path) -> None:
    areas, providers, connection = build_fixture(tmp_path)
    with pytest.raises(ValueError, match="nonnegative"):
        evaluate_scenarios(areas, providers, connection, -1)
    infeasible = evaluate_scenarios(
        areas, [{"id": "one", "capacity_per_month": 2}], connection, 2_000_000
    )["scenario_results"]["minimum_coverage"]
    assert infeasible["guarantee_capacity_feasible"] is False
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
    assert result["guarantee_capacity_feasible"] is False
    assert result["required_budget_won"] is None
    assert result["additional_budget_won"] is None
    assert result["minimum_coverage_met"] is False
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
