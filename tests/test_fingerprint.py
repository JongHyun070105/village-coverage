"""Tests for plan reproducibility fingerprint and provenance view (§21)."""

from __future__ import annotations

from copy import deepcopy

from backend.fingerprint import compute_plan_fingerprint
from backend.scheduling import generate_provider_schedule
from tests.test_scheduling import build_fixture


def test_plan_fingerprint_reproducibility_and_sensitivity() -> None:
    areas = [
        {
            "id": "area-1",
            "name": "도산리",
            "service_type": "laundry",
            "simulated_monthly_demand": 2,
            "needs_survey": False,
            "population_total": 100,
            "elderly_ratio_65": 0.4,
            "single_households_65_plus": 10,
        }
    ]
    providers = [
        {
            "provider_id": "p-1",
            "base_area_id": "base",
            "supported_services": ["laundry"],
            "max_monthly_rounds": 4,
            "service_capacity": 2,
            "max_daily_hours": 6.0,
            "max_travel_time_minutes": 60,
            "availability": [{"weekday": "monday", "start_time": "09:00", "end_time": "18:00"}],
        }
    ]
    policy_base = {
        "elderly_priority_weight": 500,
        "single_elderly_household_priority_weight": 500,
        "survey_required_protection_weight": 1000,
    }

    # 1. Same input produces exactly same fingerprint
    fp1 = compute_plan_fingerprint(
        areas=areas,
        providers=providers,
        budget_won=1_000_000,
        policy_dict=policy_base,
    )
    fp2 = compute_plan_fingerprint(
        areas=deepcopy(areas),
        providers=deepcopy(providers),
        budget_won=1_000_000,
        policy_dict=deepcopy(policy_base),
    )
    assert fp1["fingerprint"] == fp2["fingerprint"]
    assert len(fp1["fingerprint"]) == 64  # SHA-256 hex string

    # 2. Changed policy produces distinct fingerprint
    policy_changed = dict(policy_base, elderly_priority_weight=750)
    fp_pol = compute_plan_fingerprint(
        areas=areas,
        providers=providers,
        budget_won=1_000_000,
        policy_dict=policy_changed,
    )
    assert fp_pol["fingerprint"] != fp1["fingerprint"]

    # 3. Changed budget produces distinct fingerprint
    fp_budget = compute_plan_fingerprint(
        areas=areas,
        providers=providers,
        budget_won=1_500_000,
        policy_dict=policy_base,
    )
    assert fp_budget["fingerprint"] != fp1["fingerprint"]

    # 4. Changed route matrix snapshot produces distinct fingerprint
    fp_route = compute_plan_fingerprint(
        areas=areas,
        providers=providers,
        budget_won=1_000_000,
        policy_dict=policy_base,
        route_matrix_fingerprint="custom-kakao-v2",
    )
    assert fp_route["fingerprint"] != fp1["fingerprint"]


def test_schedule_plan_output_embeds_fingerprint_and_provenance(tmp_path) -> None:
    areas, providers, connection, budget = build_fixture(tmp_path)
    try:
        plan = generate_provider_schedule(
            areas,
            providers,
            connection,
            budget,
            "balanced",
            allow_route_fallback=True,
            include_timing=True,
        )
        assert "reproducibility_fingerprint" in plan
        assert len(plan["reproducibility_fingerprint"]) == 64

        assert "provenance_view" in plan
        pv = plan["provenance_view"]
        assert pv["fingerprint"] == plan["reproducibility_fingerprint"]
        assert "주민등록 인구" in pv["public_data"]
        assert "공급자" in pv["provider_model"]
        assert "Kakao" in pv["road_routing"]
        assert "정책 가중치" in pv["policy_model"]
        assert "OR-Tools" in pv["optimizer"]
        assert pv["reproducible"] is True
    finally:
        connection.close()
