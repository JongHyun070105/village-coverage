from __future__ import annotations

from copy import deepcopy

from backend.plan_changes import build_plan_change_explanation
from backend.provider_realism import provider_realism_profile


def test_plan_change_explanation_is_deterministic_and_reports_cost_and_service_deltas() -> None:
    previous = [
        {
            "area_id": "area-b",
            "area_name": "마을 B",
            "service_type": "laundry",
            "provider_id": "provider-1",
            "provider_name": "세탁 공급자",
            "scheduled_date": "2026-10-03",
            "service_start_time": "10:00",
            "service_units": 2,
            "total_cost_won": 300_000,
        },
        {
            "area_id": "area-a",
            "area_name": "마을 A",
            "service_type": "laundry",
            "provider_id": "provider-1",
            "provider_name": "세탁 공급자",
            "scheduled_date": "2026-10-02",
            "service_start_time": "09:00",
            "service_units": 1,
            "total_cost_won": 150_000,
        },
    ]
    revised = deepcopy(previous)
    revised[1]["scheduled_date"] = "2026-10-04"
    revised[1]["total_cost_won"] = 170_000
    revised[0]["service_units"] = 1
    revised[0]["total_cost_won"] = 160_000

    explanation = build_plan_change_explanation(
        previous,
        revised,
        reason="PROVIDER_DECLINED_OR_UNAVAILABLE",
        context=[{"round_id": "declined-round", "status": "DECLINED"}],
    )
    reversed_input = build_plan_change_explanation(
        list(reversed(previous)),
        list(reversed(revised)),
        reason="PROVIDER_DECLINED_OR_UNAVAILABLE",
        context=[{"round_id": "declined-round", "status": "DECLINED"}],
    )

    assert explanation == reversed_input
    assert explanation["change_count"] == 2
    assert explanation["service_units_delta"] == -1
    assert explanation["total_cost_delta_won"] == -120_000
    assert [change["area_id"] for change in explanation["changes"]] == ["area-a", "area-b"]
    assert all(change["change_type"] == "CHANGED" for change in explanation["changes"])


def test_provider_realism_reports_synthetic_history_without_optimizing_on_it() -> None:
    provider = {
        "supported_services": ["laundry"],
        "availability": [{"weekday": "monday"}],
        "date_availability": [],
        "max_daily_hours": 6,
        "max_monthly_rounds": 10,
        "max_travel_time_minutes": 75,
        "minimum_compensation_won": 180_000,
    }
    history = [
        {
            "status": "COMPLETED",
            "provenance": "SIMULATED FOR PRE-R&D",
            "round_provenance": "SIMULATED FOR PRE-R&D",
        },
        {
            "status": "DECLINED",
            "provenance": "SIMULATED FOR PRE-R&D",
            "round_provenance": "SIMULATED FOR PRE-R&D",
        },
    ]

    profile = provider_realism_profile(provider, history)

    assert profile["model_version"] == "PROVIDER_REALISM_V2"
    assert profile["sample_status"] == "SYNTHETIC_ONLY"
    assert profile["acceptance_rate"] == 0.5
    assert profile["decline_rate"] == 0.5
    assert profile["planner_treatment"]["operating_constraints"] == "HARD_CONSTRAINTS"
    assert profile["planner_treatment"]["historical_outcome_objective_weight"] == 0
