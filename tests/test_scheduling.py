from __future__ import annotations

from copy import deepcopy

from backend.scheduling import generate_provider_schedule
from backend.travel import Route, connect, put_cached


def build_fixture(tmp_path, *, budget=1_100_000):
    connection = connect(tmp_path / "travel.sqlite")
    base = {"id": "base", "anchor_lat": 36.5, "anchor_lng": 126.6}
    area = {
        "id": "area-1",
        "name": "도산리",
        "service_type": "laundry",
        "simulated_monthly_demand": 3,
        "needs_survey": False,
        "population_total": 100,
        "elderly_ratio_65": 0.4,
        "single_households_65_plus": 12,
    }
    destination = {"id": area["id"], "anchor_lat": 36.51, "anchor_lng": 126.61}
    put_cached(connection, base, destination, Route("base", area["id"], 5000, 600))
    put_cached(connection, destination, base, Route(area["id"], "base", 5000, 600))
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
        "max_monthly_rounds": 2,
        "service_capacity": 2,
        "max_daily_hours": 6,
        "max_travel_time_minutes": 70,
        "minimum_compensation_won": 1_000_000,
    }
    return [area], [provider], connection, budget


def test_provider_schedule_assigns_eligible_rounds_with_kakao_costs_and_minimum_pay(
    tmp_path,
) -> None:
    areas, providers, connection, budget = build_fixture(tmp_path)
    try:
        result = generate_provider_schedule(areas, providers, connection, budget, "efficiency")
        assert result["solver_status"] == "OPTIMAL"
        assert result["served_units"] == 3
        assert result["covered_areas"] == 1
        assert len(result["rounds"]) == 2
        assert {round_item["provider_id"] for round_item in result["rounds"]} == {"provider-1"}
        assert all(round_item["travel_distance_m"] == 10_000 for round_item in result["rounds"])
        assert all(round_item["travel_time_s"] == 1_200 for round_item in result["rounds"])
        assert result["service_cost_won"] == 3 * 255_000
        assert result["minimum_compensation_topup_won"] == 235_000
        assert result["total_cost_won"] == (
            result["service_cost_won"]
            + result["travel_cost_won"]
            + result["minimum_compensation_topup_won"]
        )
        assert result["total_cost_won"] <= budget
        assert result["unmet_criteria"] == []
    finally:
        connection.close()


def test_provider_schedule_reports_service_availability_travel_and_budget_gaps(tmp_path) -> None:
    areas, providers, connection, _ = build_fixture(tmp_path, budget=500_000)
    try:
        too_far = deepcopy(providers)
        too_far[0]["max_travel_time_minutes"] = 5
        result = generate_provider_schedule(areas, too_far, connection, 500_000, "minimum_coverage")
        assert result["served_units"] == 0
        assert result["unmet_criteria"][0]["reason"] == "MAX_TRAVEL_TIME"

        unavailable = deepcopy(providers)
        unavailable[0]["availability"] = []
        result = generate_provider_schedule(areas, unavailable, connection, 500_000, "efficiency")
        assert result["unmet_criteria"][0]["reason"] == "PROVIDER_UNAVAILABLE"

        unsupported = deepcopy(providers)
        unsupported[0]["supported_services"] = ["home_repair"]
        result = generate_provider_schedule(areas, unsupported, connection, 500_000, "balanced")
        assert result["unmet_criteria"][0]["reason"] == "NO_SUPPORTED_PROVIDER"

        too_expensive = deepcopy(providers)
        too_expensive[0]["minimum_compensation_won"] = 1_000_000
        result = generate_provider_schedule(areas, too_expensive, connection, 500_000, "efficiency")
        assert result["served_units"] == 0
        assert result["unmet_criteria"][0]["reason"] == "BUDGET"
    finally:
        connection.close()


def test_provider_schedule_fails_closed_when_road_matrix_is_missing(tmp_path) -> None:
    areas, providers, connection, budget = build_fixture(tmp_path)
    try:
        connection.execute("DELETE FROM travel_matrix WHERE origin_id='area-1'")
        connection.commit()
        try:
            generate_provider_schedule(areas, providers, connection, budget, "efficiency")
        except ValueError as exc:
            assert "provider road route missing" in str(exc)
        else:
            raise AssertionError("missing road matrix must not produce a schedule")
    finally:
        connection.close()


def test_provider_schedule_enforces_monthly_daily_time_window_and_preferred_days(tmp_path) -> None:
    areas, providers, connection, budget = build_fixture(tmp_path)
    try:
        one_month_round = deepcopy(providers)
        one_month_round[0]["max_monthly_rounds"] = 1
        result = generate_provider_schedule(
            areas, one_month_round, connection, budget, "efficiency"
        )
        assert len(result["rounds"]) == 1
        assert result["served_units"] == 2
        assert result["unmet_criteria"][0]["reason"] == "PROVIDER_CAPACITY"

        short_day = deepcopy(providers)
        short_day[0]["max_daily_hours"] = 1
        result = generate_provider_schedule(areas, short_day, connection, budget, "efficiency")
        assert result["unmet_criteria"][0]["reason"] == "MAX_DAILY_HOURS"

        short_window = deepcopy(providers)
        for availability in short_window[0]["availability"]:
            availability["end_time"] = "10:00"
        result = generate_provider_schedule(areas, short_window, connection, budget, "efficiency")
        assert result["unmet_criteria"][0]["reason"] == "TIME_WINDOW"

        preferred = deepcopy(areas)
        preferred[0]["preferred_days"] = ["sunday"]
        sunday_unavailable = deepcopy(providers)
        sunday_unavailable[0]["availability"] = [
            row for row in sunday_unavailable[0]["availability"] if row["weekday"] != "sunday"
        ]
        result = generate_provider_schedule(
            preferred, sunday_unavailable, connection, budget, "efficiency"
        )
        assert result["unmet_criteria"][0]["reason"] == "PREFERRED_DAY_CONFLICT"
    finally:
        connection.close()


def test_provider_schedule_is_deterministic_for_same_inputs(tmp_path) -> None:
    areas, providers, connection, budget = build_fixture(tmp_path)
    try:
        first = generate_provider_schedule(areas, providers, connection, budget, "balanced")
        second = generate_provider_schedule(areas, providers, connection, budget, "balanced")
        assert first == second
    finally:
        connection.close()
