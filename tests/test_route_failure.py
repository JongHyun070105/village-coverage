"""Tests for route matrix failure modes, fallback behaviors, and human explanations (§13)."""

from __future__ import annotations

import pytest

from backend import scheduling
from backend.feasibility import explain_area_feasibility
from backend.routing import MissingRoadLegError, optimize_multi_stop_route
from backend.travel import Route, connect, put_cached


def build_two_area_fixture(tmp_path):
    connection = connect(tmp_path / "travel.sqlite")
    base = {"id": "base", "anchor_lat": 36.5, "anchor_lng": 126.6}
    area1 = {
        "id": "area-1",
        "name": "도산리",
        "service_type": "laundry",
        "simulated_monthly_demand": 2,
        "needs_survey": False,
        "population_total": 100,
        "elderly_ratio_65": 0.4,
        "single_households_65_plus": 12,
    }
    area2 = {
        "id": "area-2",
        "name": "수하리",
        "service_type": "laundry",
        "simulated_monthly_demand": 2,
        "needs_survey": False,
        "population_total": 120,
        "elderly_ratio_65": 0.35,
        "single_households_65_plus": 15,
    }
    dest1 = {"id": area1["id"], "anchor_lat": 36.51, "anchor_lng": 126.61}
    dest2 = {"id": area2["id"], "anchor_lat": 36.52, "anchor_lng": 126.62}

    # Hub round-trips
    put_cached(connection, base, dest1, Route("base", area1["id"], 5000, 600))
    put_cached(connection, dest1, base, Route(area1["id"], "base", 5000, 600))
    put_cached(connection, base, dest2, Route("base", area2["id"], 6000, 720))
    put_cached(connection, dest2, base, Route(area2["id"], "base", 6000, 720))

    # Inter-stop legs
    put_cached(connection, dest1, dest2, Route(area1["id"], area2["id"], 3000, 360))
    put_cached(connection, dest2, dest1, Route(area2["id"], area1["id"], 3000, 360))

    provider = {
        "provider_id": "provider-1",
        "name": "테스트 세탁",
        "base_area_id": "base",
        "supported_services": ["laundry"],
        "availability": [
            {"weekday": day, "start_time": "09:00", "end_time": "17:00"}
            for day in (
                "monday",
                "tuesday",
                "wednesday",
                "thursday",
                "friday",
                "saturday",
                "sunday",
            )
        ],
        "max_monthly_rounds": 4,
        "service_capacity": 4,
        "max_daily_hours": 6,
        "max_travel_time_minutes": 70,
        "minimum_compensation_won": 1_000_000,
    }
    budget = 5_000_000
    return [area1, area2], [provider], connection, budget


def test_missing_directed_leg_finds_alternate_multi_stop_or_falls_back(tmp_path) -> None:
    # 3 areas: depot (base-0), area-1, area-2
    # If edge (area-1 -> area-2) is missing, but (area-2 -> area-1) exists:
    base_id = "base-0"
    stops = [
        {"area_id": "area-1", "duration_minutes": 30},
        {"area_id": "area-2", "duration_minutes": 30},
    ]
    # Complete roads except (area-1, area-2) missing
    roads = {
        (base_id, "area-1"): (10_000, 600),
        ("area-1", base_id): (10_000, 600),
        (base_id, "area-2"): (10_000, 600),
        ("area-2", base_id): (10_000, 600),
        # (area-1, area-2) is intentionally omitted!
        ("area-2", "area-1"): (5_000, 300),
    }

    # Strict mode raises MissingRoadLegError
    with pytest.raises(MissingRoadLegError):
        optimize_multi_stop_route(
            base_id,
            stops,
            roads,
            available_from="09:00",
            available_until="18:00",
            max_daily_hours=8.0,
        )


def test_scheduler_handles_missing_intermediate_leg_with_hub_fallback(tmp_path) -> None:
    areas, providers, connection, budget = build_two_area_fixture(tmp_path)
    # Remove directed edge between area-1 and area-2
    connection.execute(
        "DELETE FROM travel_matrix WHERE origin_id='area-1' AND destination_id='area-2'"
    )
    connection.commit()

    # With allow_route_fallback=True, missing inter-stop leg marks matrix incomplete
    # and falls back to hub round-trips
    result = scheduling.generate_provider_schedule(
        areas, providers, connection, budget, "efficiency", allow_route_fallback=True
    )
    assert result["solver_status"] in {"OPTIMAL", "FEASIBLE"}
    assert result["route_matrix_complete"] is False
    # All executed routes are HUB_ROUND_TRIP
    for route in result["routes"]:
        assert route["route_type"] == "HUB_ROUND_TRIP"
    connection.close()


def test_scheduler_blocks_candidate_when_hub_leg_is_missing(tmp_path) -> None:
    areas, providers, connection, budget = build_two_area_fixture(tmp_path)
    # Delete hub leg from provider base to area-1
    connection.execute(
        "DELETE FROM travel_matrix WHERE (origin_id='base' AND destination_id='area-1')"
    )
    connection.commit()

    result = scheduling.generate_provider_schedule(
        areas, providers, connection, budget, "efficiency", allow_route_fallback=True
    )
    # area-1 cannot be served because the road leg from provider base is missing
    unmet_area_1 = next(item for item in result["unmet_criteria"] if item["area_id"] == "area-1")
    assert unmet_area_1["reason"] in {"ROUTE_UNAVAILABLE", "ROAD_EDGE_MISSING"}
    
    # Check feasibility explanation
    feasibility = result["feasibility_breakdown"]["area-1"]
    assert feasibility["primary_reason"] == "ROUTE_UNAVAILABLE"
    assert feasibility["money_resolvable"] is False
    assert "도로 이동시간을 확인할 수 없어" in feasibility["reason_explanation"]
    connection.close()


def test_no_straight_line_or_haversine_substitution(tmp_path) -> None:
    areas, providers, connection, budget = build_two_area_fixture(tmp_path)
    # Delete all legs for area-1
    connection.execute(
        "DELETE FROM travel_matrix WHERE origin_id='area-1' OR destination_id='area-1'"
    )
    connection.commit()

    result = scheduling.generate_provider_schedule(
        areas, providers, connection, budget, "efficiency", allow_route_fallback=True
    )
    # area-1 MUST NOT be served with fabricated straight-line distance
    served_areas = {item["area_id"] for item in result["rounds"]}
    assert "area-1" not in served_areas

    unmet_1 = next(item for item in result["unmet_criteria"] if item["area_id"] == "area-1")
    assert unmet_1["reason"] in {"ROUTE_UNAVAILABLE", "NO_ROAD_ROUTE", "ROAD_EDGE_MISSING"}
    connection.close()


def test_route_failure_human_explanation() -> None:
    explanation = explain_area_feasibility("ROUTE_UNAVAILABLE")
    assert explanation["primary_reason"] == "ROUTE_UNAVAILABLE"
    assert explanation["money_resolvable"] is False
    assert (
        explanation["reason_explanation"]
        == "도로 이동시간을 확인할 수 없어 해당 회차를 계획하지 못했습니다."
    )
    assert explanation["suggested_action"] == "도로 경로 데이터 확인 또는 인근 거점 재설정"
