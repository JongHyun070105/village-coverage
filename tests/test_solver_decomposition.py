from pathlib import Path

import pytest

from backend import scheduling
from backend.allocation_stage import balanced_linear_score, objective_maxima
from backend.settings import PlanningPolicy
from scripts.run_stress_tests import generate_scenario_data, verify_invariants


@pytest.fixture
def scenario(tmp_path: Path):
    areas, providers, connection, budget, policy, fallback, _ = generate_scenario_data(
        16, 3, "A", 20261002, tmp_path / "decomposition.sqlite"
    )
    yield areas, providers, connection, budget, policy, fallback
    connection.close()


def plan(scenario, name="balanced", strategy="decomposed", budget=None, seconds=2.5):
    areas, providers, connection, default_budget, policy, fallback = scenario
    return scheduling.generate_provider_schedule(
        areas, providers, connection, default_budget if budget is None else budget, name,
        policy, allow_route_fallback=fallback, include_timing=True,
        max_solver_seconds=seconds, route_strategy=strategy, include_profile=True,
    )


def test_decomposed_plan_satisfies_hard_invariants(scenario):
    result = plan(scenario)
    areas, providers, connection, budget, _policy, fallback = scenario
    check = verify_invariants(result, areas, providers, budget, connection,
                              allow_route_fallback=fallback)
    assert check["passed"], check["violations"]
    assert result["budget_spent_won"] <= budget
    assert result["route_strategy"] == "decomposed"


def test_decomposed_optimality_is_only_claimed_when_bound_is_attained(scenario):
    result = plan(scenario)
    proof = result["decomposition"]
    assert result["optimality_proven"] == proof["optimality_proven"]
    if proof["optimality_proven"]:
        assert proof["stage_a_status"] == "OPTIMAL"
        assert proof["aggregate_bound_attained"]
        assert proof["realized_components"] == {
            name: proof["realized_components"][name] for name in proof["aggregate_components"]
        }
        assert result["solver_status"] == "OPTIMAL"
        assert result["optimality_scope"] == "ALLOCATION_MODEL_WITH_ROUND_TRIP_COSTS"
    else:
        assert result["solver_status"] != "OPTIMAL"
    # Post-solve multi-stop routing is never part of an optimality claim.
    assert result["global_route_optimality_proven"] is False


def test_efficiency_is_never_claimed_optimal_through_decomposition(scenario):
    result = plan(scenario, "efficiency")
    assert result["decomposition"]["optimality_proven"] is False
    assert result["solver_status"] in {"FEASIBLE", "TIME_LIMIT"}
    assert result["optimality_proven"] is False


def test_infeasible_pruned_stage_is_not_reported_as_global_infeasibility():
    allocation = {
        "status": "OPTIMAL",
        "targets": {("provider-00", "area-000"): {"visits": 1}},
        "components": {},
        "wall_ms": 1,
        "pair_count": 1,
    }
    proof = scheduling._decomposition_proof(
        allocation, object(), {}, "balanced", "INFEASIBLE"
    )
    assert proof["final_status"] == "UNKNOWN"
    assert proof["optimality_proven"] is False


def test_restricted_candidate_infeasibility_maps_to_unknown():
    assert scheduling._global_solver_status(
        "INFEASIBLE", candidates_restricted=True
    ) == "UNKNOWN"
    assert scheduling._global_solver_status(
        "INFEASIBLE", candidates_restricted=False
    ) == "INFEASIBLE"


def test_required_budget_optimizes_full_candidate_set(scenario, monkeypatch):
    areas, providers, connection, budget, policy, fallback = scenario

    def allocation_must_not_prune(**_kwargs):
        pytest.fail("schedule-feasible minimum budget must solve the full candidate set")

    monkeypatch.setattr(scheduling, "solve_aggregate_allocation", allocation_must_not_prune)
    result = scheduling.generate_provider_schedule(
        areas[:1], providers[:1], connection, budget, "minimum_coverage", policy,
        _required_budget_only=True, allow_route_fallback=fallback,
        max_solver_seconds=1.0, route_strategy="decomposed",
    )
    assert result["required_budget_status"] in {"CALCULATED", "NOT_PROVEN"}
    assert result.get("decomposition") is None


def test_same_inputs_give_same_decomposed_plan(scenario):
    first, second = plan(scenario), plan(scenario)
    keys = ("scheduled_date", "provider_id", "area_id", "service_units")
    assert [tuple(r.get(k) for k in keys) for r in first["rounds"]] == [
        tuple(r.get(k) for k in keys) for r in second["rounds"]
    ]
    assert first["reproducibility_fingerprint"] == second["reproducibility_fingerprint"]


def test_profile_separates_build_and_solve(scenario):
    profile = plan(scenario)["solver_profile"]
    for key in ("build_ms", "solve_ms", "candidate_variable_count", "model_variable_count",
                "model_constraint_count", "route_edge_variable_count",
                "provider_day_combinations", "solver_branches", "solver_conflicts"):
        assert key in profile
    assert profile["route_edge_variable_count"] == 0


def test_joint_profile_counts_route_edges(scenario):
    profile = plan(scenario, strategy="joint", seconds=1.0)["solver_profile"]
    assert profile["route_edge_variable_count"] > 0


def test_auto_strategy_uses_joint_only_for_small_route_models(scenario):
    large = plan(scenario, strategy="auto", seconds=1.0)
    assert large["route_strategy_requested"] == "auto"
    assert large["route_strategy"] == "decomposed"
    assert scheduling._estimated_route_arcs([]) == 0


def test_zero_budget_decomposed_plan_spends_nothing(scenario):
    result = plan(scenario, budget=0, seconds=1.0)
    assert result["budget_spent_won"] == 0
    assert result["served_units"] == 0


def test_balanced_linear_score_is_monotone_in_each_benefit():
    policy = PlanningPolicy()
    weights = scheduling.BALANCED_SCHEDULE_SCORE_WEIGHTS
    base = dict(weights=weights, policy=policy, max_units=10, area_count=5, max_survey=2000,
                max_vulnerability=100, max_travel_cost=1000)
    low, maximum = balanced_linear_score(total_units=1, covered_count=1, survey_count=0,
                                         vulnerability=10, concentration=10_000,
                                         travel_cost=500, **base)
    more_units, _ = balanced_linear_score(total_units=2, covered_count=1, survey_count=0,
                                          vulnerability=10, concentration=10_000,
                                          travel_cost=500, **base)
    cheaper, _ = balanced_linear_score(total_units=1, covered_count=1, survey_count=0,
                                       vulnerability=10, concentration=10_000,
                                       travel_cost=400, **base)
    assert more_units > low and cheaper > low
    assert 0 <= low <= maximum < 2**62


def test_objective_maxima_cover_the_full_candidate_set():
    candidates = [
        {"provider_id": "p", "scheduled_date": d, "route": {"cost_won": 10, "duration_s": 60},
         "participation_status": "OPTED_IN" if d == "2026-10-05" else "AVAILABLE"}
        for d in ("2026-10-05", "2026-10-06")
    ]
    maxima = objective_maxima(candidates, [{"simulated_monthly_demand": 3}])
    assert maxima == {"max_units": 3, "max_travel_cost": 20, "max_travel_time": 120,
                      "max_provider_days": 2, "opted_in_candidates": 1}


@pytest.mark.parametrize(("value", "expected"), [
    ("00:00", 0), ("9:05", 545), ("23:59", 1439),
])
def test_fast_minute_parser_matches_valid_clock_times(value, expected):
    assert scheduling._minute(value) == expected


@pytest.mark.parametrize("value", ["24:00", "12:60", "09:00:00", "noon", ""])
def test_fast_minute_parser_rejects_invalid_clock_times(value):
    with pytest.raises(ValueError):
        scheduling._minute(value)


def test_route_matrix_completeness_uses_directed_pairs_and_caches_results():
    complete_routes = {
        ("a", "b"): (1, 1), ("a", "c"): (1, 1),
        ("b", "a"): (1, 1), ("b", "c"): (1, 1),
        ("c", "a"): (1, 1), ("c", "b"): (1, 1),
    }
    neighbors = scheduling._route_neighbors(complete_routes)
    cache = {}
    locations = {"a", "b", "c"}
    assert scheduling._route_matrix_complete_for_locations(locations, neighbors, cache)
    assert cache[frozenset(locations)] is True

    incomplete_routes = {key: value for key, value in complete_routes.items()
                         if key != ("b", "c")}
    incomplete_neighbors = scheduling._route_neighbors(incomplete_routes)
    assert not scheduling._route_matrix_complete_for_locations(
        locations, incomplete_neighbors, {}
    )


@pytest.mark.parametrize(("aggregate_status", "expected_money_only"), [
    ("OPTIMAL", 123_456), ("FEASIBLE", None),
])
def test_large_minimum_budget_diagnostic_keeps_schedule_status_unproven(
    monkeypatch, aggregate_status, expected_money_only
):
    area = {"id": "area-a", "simulated_monthly_demand": 1}
    provider = {"provider_id": "provider-a", "minimum_compensation_won": 0}
    candidate = {
        "provider_id": "provider-a", "area_id": "area-a", "month": "2026-10",
        "service_capacity": 1, "service_type": "laundry", "route": {"cost_won": 10},
    }
    candidates = [dict(candidate) for _ in range(
        scheduling.MINIMUM_BUDGET_FULL_SCHEDULE_CANDIDATE_LIMIT + 1
    )]
    observed = {}

    def aggregate_solve(**kwargs):
        observed.update(kwargs)
        return {"status": aggregate_status, "components": {"total_cost": 123_456}}

    def full_schedule_must_not_run(*_args, **_kwargs):
        pytest.fail("large diagnostic must preserve schedule feasibility as unproven")

    monkeypatch.setattr(scheduling, "solve_aggregate_allocation", aggregate_solve)
    monkeypatch.setattr(scheduling, "generate_provider_schedule", full_schedule_must_not_run)
    result = scheduling._calculate_minimum_budget(
        [area], [provider], object(), candidates, 1_000_000, PlanningPolicy(),
        route_strategy="decomposed", max_solver_seconds=2.5,
    )

    assert result == (
        None,
        "NOT_PROVEN",
        "SCHEDULE_FEASIBILITY_NOT_PROVEN",
        expected_money_only,
    )
    assert observed["scenario"] == "required_budget"
    assert observed["max_seconds"] == pytest.approx(0.25)


def test_tight_capacity_variant_does_not_abort_native_solver(tmp_path):
    # Regression: interleaved parallel search + solution hints aborted OR-Tools
    # with "Check failed: heuristics.fixed_search != nullptr" on this scenario.
    areas, providers, connection, budget, policy, fallback, _ = generate_scenario_data(
        16, 3, "C", 20261002, tmp_path / "variant_c.sqlite"
    )
    try:
        result = scheduling.generate_provider_schedule(
            areas, providers, connection, budget, "balanced", policy,
            allow_route_fallback=fallback, max_solver_seconds=2.5, route_strategy="decomposed",
        )
    finally:
        connection.close()
    assert result["solver_status"] in {"OPTIMAL", "FEASIBLE", "TIME_LIMIT"}
