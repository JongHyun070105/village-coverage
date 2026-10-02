"""Tests for minimum coverage feasibility breakdown and human explanations (§17)."""

from __future__ import annotations

from backend.feasibility import (
    FEASIBILITY_REASONS,
    canonicalize_feasibility_reason,
    explain_area_feasibility,
)
from backend.scheduling import generate_provider_schedule
from tests.test_scheduling import build_fixture


def test_explain_area_feasibility_covers_all_canonical_reasons() -> None:
    for code in FEASIBILITY_REASONS:
        explanation = explain_area_feasibility(code, service_type="laundry")
        assert explanation["primary_reason"] == code
        assert isinstance(explanation["secondary_reasons"], list)
        assert isinstance(explanation["money_resolvable"], bool)
        assert isinstance(explanation["suggested_action"], str)
        assert len(explanation["suggested_action"]) > 0
        assert isinstance(explanation["reason_explanation"], str)
        assert len(explanation["reason_explanation"]) > 0

        # Invariant: MONEY_SHORTAGE is the ONLY money_resolvable condition
        if code == "MONEY_SHORTAGE":
            assert explanation["money_resolvable"] is True
            assert "예산" in explanation["suggested_action"]
        else:
            assert explanation["money_resolvable"] is False


def test_feasibility_legacy_code_mapping_to_canonical() -> None:
    assert canonicalize_feasibility_reason("BUDGET") == "MONEY_SHORTAGE"
    assert canonicalize_feasibility_reason("PROVIDER_CAPACITY") == "PROVIDER_CAPACITY_SHORTAGE"
    assert canonicalize_feasibility_reason("NO_SUPPORTED_PROVIDER") == "NO_COMPATIBLE_PROVIDER"
    assert canonicalize_feasibility_reason("REQUESTED_TIME_WINDOW") == "TIME_WINDOW_CONFLICT"
    assert canonicalize_feasibility_reason("MAX_TRAVEL_TIME") == "ROUTE_UNAVAILABLE"
    assert canonicalize_feasibility_reason("SERVICE_NOT_ALLOWED") == "SERVICE_NOT_SUPPORTED"
    assert canonicalize_feasibility_reason("NEEDS_SURVEY") == "INSUFFICIENT_EVIDENCE"


def test_schedule_plan_includes_area_level_feasibility_breakdown(tmp_path) -> None:
    areas, providers, connection, budget = build_fixture(tmp_path, budget=500_000)
    # Area demands 3 rounds, but provider max_monthly_rounds is 2, creating an unserved gap
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
        assert "feasibility_breakdown" in plan
        breakdown = plan["feasibility_breakdown"]
        assert "area-1" in breakdown
        area_info = breakdown["area-1"]
        valid_reasons = set(FEASIBILITY_REASONS) | {"DEMAND_BELOW_MINIMUM"}
        assert area_info["primary_reason"] in valid_reasons
        assert "money_resolvable" in area_info
        assert "suggested_action" in area_info
        assert "reason_explanation" in area_info
    finally:
        connection.close()
