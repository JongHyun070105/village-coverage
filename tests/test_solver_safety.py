"""Tests for solver safety model, status mapping, and time limit handling (§12, §5)."""

from __future__ import annotations

from ortools.sat.python import cp_model

from backend import optimization, scheduling
from backend.feasibility import SOLVER_STATUS_MESSAGES, map_solver_status
from tests.test_optimization import build_fixture


def test_solver_status_explicit_mapping_and_never_upgrades_feasible() -> None:
    # 1. OPTIMAL
    status, opt_proven, time_limit = map_solver_status(cp_model.OPTIMAL, 0.5, 3.0, cp_model)
    assert status == "OPTIMAL"
    assert opt_proven is True
    assert time_limit is False

    # 2. FEASIBLE within time limit -> MUST NOT BE OPTIMAL
    status, opt_proven, time_limit = map_solver_status(cp_model.FEASIBLE, 0.5, 3.0, cp_model)
    assert status == "FEASIBLE"
    assert opt_proven is False
    assert time_limit is False

    # 3. FEASIBLE hitting time limit -> TIME_LIMIT, NOT OPTIMAL
    status, opt_proven, time_limit = map_solver_status(cp_model.FEASIBLE, 2.98, 3.0, cp_model)
    assert status == "TIME_LIMIT"
    assert opt_proven is False
    assert time_limit is True

    # 4. INFEASIBLE
    status, opt_proven, time_limit = map_solver_status(cp_model.INFEASIBLE, 0.1, 3.0, cp_model)
    assert status == "INFEASIBLE"
    assert opt_proven is False
    assert time_limit is False

    # 5. MODEL_INVALID
    status, opt_proven, time_limit = map_solver_status(cp_model.MODEL_INVALID, 0.01, 3.0, cp_model)
    assert status == "MODEL_INVALID"
    assert opt_proven is False
    assert time_limit is False

    # 6. UNKNOWN hitting time limit -> TIME_LIMIT
    status, opt_proven, time_limit = map_solver_status(cp_model.UNKNOWN, 3.0, 3.0, cp_model)
    assert status == "TIME_LIMIT"
    assert opt_proven is False
    assert time_limit is True


def test_solver_status_messages_contain_required_user_guidance() -> None:
    assert SOLVER_STATUS_MESSAGES["OPTIMAL"] == "최적성이 확인된 계획입니다."
    assert (
        SOLVER_STATUS_MESSAGES["FEASIBLE"]
        == "실행 가능한 계획을 찾았지만 최적성은 확인되지 않았습니다."
    )
    assert (
        SOLVER_STATUS_MESSAGES["TIME_LIMIT"]
        == "제한시간 내 실행 가능한 계획을 찾았으며 더 나은 계획이 존재할 수 있습니다."
    )
    assert (
        SOLVER_STATUS_MESSAGES["INFEASIBLE"]
        == "현재 조건으로 실행 가능한 계획이 없습니다."
    )


def test_scenario_solver_reproduces_feasible_and_time_limit_safely(tmp_path, monkeypatch) -> None:
    areas, providers, connection = build_fixture(tmp_path)

    # Mock solver that returns FEASIBLE with a wall time hitting the limit
    class MockTimeLimitSolver:
        def __init__(self):
            self.wall_time = 2.99
            self.objective_value = 1200000.0
            self.best_objective_bound = 1500000.0

        def solve(self, model):
            return cp_model.FEASIBLE

        def status_name(self, status):
            return "FEASIBLE"

        def value(self, var):
            return 1

    monkeypatch.setattr(optimization, "_new_solver", MockTimeLimitSolver)
    result = optimization.evaluate_scenarios(
        areas, providers, connection, 600_000, include_timing=True
    )
    efficiency = result["scenario_results"]["efficiency"]

    assert efficiency["solver_status"] == "TIME_LIMIT"
    assert efficiency["optimality_proven"] is False
    assert efficiency["time_limit_reached"] is True
    assert (
        efficiency["solver_status_message"]
        == "제한시간 내 실행 가능한 계획을 찾았으며 더 나은 계획이 존재할 수 있습니다."
    )
    assert efficiency["relative_gap"] is not None
    assert efficiency["relative_gap"] > 0
    assert efficiency["solve_time_ms"] is not None
    connection.close()


def test_provider_schedule_solver_safety_fields(tmp_path) -> None:
    from tests.test_scheduling import build_fixture as build_sched_fixture

    areas, providers, connection, budget = build_sched_fixture(tmp_path)
    result = scheduling.generate_provider_schedule(
        areas, providers, connection, budget, "efficiency", include_timing=True
    )
    assert result["solver_status"] in {"OPTIMAL", "FEASIBLE", "TIME_LIMIT"}
    assert isinstance(result["optimality_proven"], bool)
    assert isinstance(result["time_limit_reached"], bool)
    assert result["solver_status_message"] in SOLVER_STATUS_MESSAGES.values()
    assert result["solve_time_ms"] is not None
    connection.close()
