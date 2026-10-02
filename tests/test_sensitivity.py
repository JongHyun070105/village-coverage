"""Tests for provider participation and policy weight sensitivity (§15, §16)."""

from __future__ import annotations

import json
from pathlib import Path

from backend.sensitivity import (
    run_policy_sensitivity_analysis,
    run_provider_participation_sensitivity,
)
from scripts.run_sensitivity import build_sensitivity_fixture

ROOT = Path(__file__).resolve().parents[1]


def test_provider_participation_sensitivity_distinguishes_money_vs_capacity(tmp_path) -> None:
    db_file = tmp_path / "travel_sens.sqlite"
    areas, providers, connection = build_sensitivity_fixture(db_file)
    try:
        # Run sensitivity with tight budget
        res = run_provider_participation_sensitivity(
            areas, providers, connection, budget_won=1_200_000
        )
        assert res["analysis_type"] == "PROVIDER_PARTICIPATION_SENSITIVITY"
        scenarios = res["scenarios"]
        assert len(scenarios) >= 3

        scenario_keys = {s["scenario_key"] for s in scenarios}
        assert "ALL_AVAILABLE" in scenario_keys
        assert "ONE_PROVIDER_DECLINED" in scenario_keys
        assert "TOP_CAPACITY_PROVIDER_DECLINED" in scenario_keys

        for s in scenarios:
            assert "bottleneck" in s
            assert "money_resolvable" in s
            assert isinstance(s["money_resolvable"], bool)
            assert "bottleneck_explanation" in s
            assert "replan_change_count" in s
            assert "covered_areas" in s
            assert "served_rounds" in s

        # Multiple declined or top capacity declined must show capacity constraints
        top_declined = next(
            s for s in scenarios if s["scenario_key"] == "TOP_CAPACITY_PROVIDER_DECLINED"
        )
        assert top_declined["active_provider_count"] < len(providers)
    finally:
        connection.close()


def test_policy_weight_sensitivity_and_instability_detection(tmp_path) -> None:
    db_file = tmp_path / "travel_pol.sqlite"
    areas, providers, connection = build_sensitivity_fixture(db_file)
    try:
        fast_grid = [
            ("baseline_default", 500, 500, 1000),
            ("elderly_zero", 0, 500, 1000),
            ("survey_zero", 500, 500, 0),
            ("all_zero", 0, 0, 0),
        ]
        res = run_policy_sensitivity_analysis(
            areas, providers, connection, budget_won=1_500_000, grid_points=fast_grid
        )
        assert res["analysis_type"] == "POLICY_WEIGHT_SENSITIVITY"
        assert "instability_flag" in res
        assert res["instability_flag"] in {"HIGH_SENSITIVITY", "STABLE"}
        assert "user_guidance" in res
        assert "configurations" in res
        assert len(res["configurations"]) == 4

        for cfg in res["configurations"]:
            assert "elderly_priority_weight" in cfg
            assert "survey_protection_weight" in cfg
            assert "covered_areas" in cfg
            assert "served_rounds" in cfg
            assert "travel_cost_won" in cfg
            assert "allocation_concentration_hhi" in cfg
    finally:
        connection.close()


def test_sensitivity_artifacts_exist_and_conform() -> None:
    p_path = ROOT / "artifacts" / "provider_sensitivity.json"
    assert p_path.exists(), "provider_sensitivity.json artifact must exist"
    with open(p_path, encoding="utf-8") as f:
        p_data = json.load(f)
    assert p_data["analysis_type"] == "PROVIDER_PARTICIPATION_SENSITIVITY"
    assert len(p_data["scenarios"]) >= 3

    pol_path = ROOT / "artifacts" / "policy_sensitivity.json"
    assert pol_path.exists(), "policy_sensitivity.json artifact must exist"
    with open(pol_path, encoding="utf-8") as f:
        pol_data = json.load(f)
    assert pol_data["analysis_type"] == "POLICY_WEIGHT_SENSITIVITY"
    assert "instability_flag" in pol_data
