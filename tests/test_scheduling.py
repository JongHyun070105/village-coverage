from __future__ import annotations

from copy import deepcopy
from datetime import date, timedelta

import pytest

from backend import scheduling
from backend.scheduling import generate_provider_schedule
from backend.settings import PlanningPolicy
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


def test_provider_replan_excludes_only_the_declined_provider_area_service_date(tmp_path) -> None:
    areas, providers, connection, budget = build_fixture(tmp_path)
    try:
        declined_date = (scheduling.korea_today() + timedelta(days=1)).isoformat()
        result = generate_provider_schedule(
            areas,
            providers,
            connection,
            budget,
            "efficiency",
            excluded_provider_slots={
                ("provider-1", "area-1", "laundry", declined_date),
            },
        )

        assert not any(
            item["provider_id"] == "provider-1"
            and item["area_id"] == "area-1"
            and item["service_type"] == "laundry"
            and item["scheduled_date"] == declined_date
            for item in result["rounds"]
        )
        assert result["served_units"] == 3
        assert result["provider_realism"]["historical_outcomes_used_for_optimization"] is False
    finally:
        connection.close()


def test_provider_schedule_excludes_week_decline_over_month_opt_in(tmp_path) -> None:
    areas, providers, connection, budget = build_fixture(tmp_path)
    target = date.today() + timedelta(days=1)
    week_start = (target - timedelta(days=target.weekday())).isoformat()
    areas[0]["simulated_monthly_demand"] = 1
    areas[0]["requested_service_windows"] = [
        {"survey_id": "survey-1", "desired_date": target.isoformat()}
    ]
    providers[0]["participation_preferences"] = [
        {
            "scope": "MONTH",
            "period_start": target.replace(day=1).isoformat(),
            "status": "OPTED_IN",
        },
        {"scope": "WEEK", "period_start": week_start, "status": "DECLINED"},
    ]
    try:
        result = generate_provider_schedule(areas, providers, connection, budget, "efficiency")
        assert result["rounds"] == []
        assert result["unmet_criteria"] == [
            {
                "area_id": "area-1",
                "area_name": "도산리",
                "units": 1,
                "reason": "PROVIDER_DECLINED",
                "reasons": ["PROVIDER_DECLINED"],
            }
        ]
    finally:
        connection.close()


def test_provider_schedule_prefers_opted_in_provider_after_policy_cost_ties(tmp_path) -> None:
    areas, providers, connection, budget = build_fixture(tmp_path)
    target = date.today() + timedelta(days=1)
    week_start = (target - timedelta(days=target.weekday())).isoformat()
    areas[0]["simulated_monthly_demand"] = 1
    areas[0]["requested_service_windows"] = [
        {"survey_id": "survey-1", "desired_date": target.isoformat()}
    ]
    opted_in = deepcopy(providers[0])
    opted_in["provider_id"] = "provider-opted-in"
    opted_in["name"] = "주간 참여 공급자"
    opted_in["participation_preferences"] = [
        {"scope": "WEEK", "period_start": week_start, "status": "OPTED_IN"}
    ]
    providers.append(opted_in)
    try:
        result = generate_provider_schedule(areas, providers, connection, budget, "efficiency")
        assert len(result["rounds"]) == 1
        assert result["rounds"][0]["provider_id"] == "provider-opted-in"
        assert result["rounds"][0]["participation_status"] == "OPTED_IN"
        assert result["rounds"][0]["participation_source"] == "WEEK"
    finally:
        connection.close()


def test_provider_date_availability_overrides_weekly_windows_for_that_service(tmp_path) -> None:
    areas, providers, connection, budget = build_fixture(tmp_path)
    target = date.today() + timedelta(days=7)
    weekday = target.strftime("%A").lower()
    areas[0]["preferred_days"] = [weekday]
    providers[0]["availability"] = []
    providers[0]["date_availability"] = [
        {
            "available_date": target.isoformat(),
            "service_type": "laundry",
            "start_time": "13:00",
            "end_time": "17:00",
        }
    ]
    try:
        result = generate_provider_schedule(areas, providers, connection, budget, "efficiency")
        assert result["rounds"]
        assert {item["scheduled_date"] for item in result["rounds"]} == {target.isoformat()}
        assert {item["departure_time"] for item in result["rounds"]} == {"13:00"}
        assert {item["service_start_time"] for item in result["rounds"]} == {"13:10"}
    finally:
        connection.close()


def test_provider_schedule_honors_approved_requested_date_and_service_start_time(tmp_path) -> None:
    areas, providers, connection, budget = build_fixture(tmp_path)
    target = date.today() + timedelta(days=7)
    areas[0]["requested_service_windows"] = [
        {
            "survey_id": "approved-survey-1",
            "desired_date": target.strftime("%m-%d"),
            "desired_time": "13:00",
        }
    ]
    try:
        result = generate_provider_schedule(areas, providers, connection, budget, "efficiency")
        assert len(result["rounds"]) == 1
        scheduled = result["rounds"][0]
        assert scheduled["scheduled_date"] == target.isoformat()
        assert scheduled["service_start_time"] == "13:00"
        assert scheduled["departure_time"] == "12:50"
        assert scheduled["time_window_source"] == "SURVEY INPUT; HUMAN REVIEW"
    finally:
        connection.close()


@pytest.mark.parametrize(
    ("max_daily_hours", "expected_rounds"),
    ((6, 2), (2.5, 1)),
)
def test_provider_schedule_can_use_two_nonoverlapping_availability_windows_same_day(
    tmp_path, max_daily_hours: float, expected_rounds: int
) -> None:
    areas, providers, connection, _budget = build_fixture(tmp_path, budget=2_000_000)
    visit_date = scheduling.korea_today() + timedelta(days=2)
    areas[0]["simulated_monthly_demand"] = 1
    areas[0]["requested_service_windows"] = [
        {"desired_date": visit_date.isoformat(), "desired_time": "10:00"}
    ]
    second_area = {
        **deepcopy(areas[0]),
        "id": "area-2",
        "name": "화계리",
        "requested_service_windows": [
            {"desired_date": visit_date.isoformat(), "desired_time": "14:00"}
        ],
    }
    areas.append(second_area)
    base = {"id": "base", "anchor_lat": 36.5, "anchor_lng": 126.6}
    destination = {"id": "area-2", "anchor_lat": 36.52, "anchor_lng": 126.62}
    put_cached(connection, base, destination, Route("base", "area-2", 5000, 600))
    put_cached(connection, destination, base, Route("area-2", "base", 5000, 600))
    providers[0]["availability"] = [
        {"weekday": weekday, "start_time": start, "end_time": end}
        for weekday in (
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
        )
        for start, end in (("09:00", "12:00"), ("13:00", "17:00"))
    ]
    providers[0]["max_monthly_rounds"] = 4
    providers[0]["service_capacity"] = 1
    providers[0]["max_daily_hours"] = max_daily_hours
    try:
        result = generate_provider_schedule(areas, providers, connection, 2_000_000, "efficiency")
        assert result["served_units"] == expected_rounds
        assert len(result["rounds"]) == expected_rounds
        assert sum(
            item["duration_minutes"] * 60 for item in result["rounds"]
        ) + result["travel_time_s"] <= max_daily_hours * 3600
        if expected_rounds == 1:
            assert {item["service_start_time"] for item in result["rounds"]} in (
                {"10:00"},
                {"14:00"},
            )
        else:
            assert {item["scheduled_date"] for item in result["rounds"]} == {
                visit_date.isoformat()
            }
            assert {item["service_start_time"] for item in result["rounds"]} == {
                "10:00",
                "14:00",
            }
            assert len(result["routes"]) == 2
            assert len({route["route_group_key"] for route in result["routes"]}) == 2
            assert result["travel_time_s"] == sum(
                route["duration_s"] for route in result["routes"]
            )
    finally:
        connection.close()


def test_provider_schedule_passes_exact_times_into_multi_stop_route(tmp_path) -> None:
    areas, providers, connection, _budget = build_fixture(tmp_path, budget=2_000_000)
    second_area = {
        **areas[0],
        "id": "area-2",
        "name": "화계리",
        "simulated_monthly_demand": 1,
    }
    areas[0]["simulated_monthly_demand"] = 1
    areas.append(second_area)
    put_cached(
        connection,
        {"id": "base", "anchor_lat": 36.5, "anchor_lng": 126.6},
        {"id": "area-2", "anchor_lat": 36.52, "anchor_lng": 126.62},
        Route("base", "area-2", 5000, 600),
    )
    put_cached(
        connection,
        {"id": "area-2", "anchor_lat": 36.52, "anchor_lng": 126.62},
        {"id": "base", "anchor_lat": 36.5, "anchor_lng": 126.6},
        Route("area-2", "base", 5000, 600),
    )
    put_cached(
        connection,
        {"id": "area-1", "anchor_lat": 36.51, "anchor_lng": 126.61},
        {"id": "area-2", "anchor_lat": 36.52, "anchor_lng": 126.62},
        Route("area-1", "area-2", 1000, 60),
    )
    put_cached(
        connection,
        {"id": "area-2", "anchor_lat": 36.52, "anchor_lng": 126.62},
        {"id": "area-1", "anchor_lat": 36.51, "anchor_lng": 126.61},
        Route("area-2", "area-1", 1000, 60),
    )
    target = date.today() + timedelta(days=7)
    areas[0]["requested_service_windows"] = [
        {"survey_id": "approved-a", "desired_date": target.isoformat(), "desired_time": "10:00"}
    ]
    areas[1]["requested_service_windows"] = [
        {"survey_id": "approved-b", "desired_date": target.isoformat(), "desired_time": "11:01"}
    ]
    try:
        result = generate_provider_schedule(areas, providers, connection, 2_000_000, "efficiency")
        assert len(result["rounds"]) == 2
        assert {item["service_start_time"] for item in result["rounds"]} == {"10:00", "11:01"}
        assert len(result["routes"]) == 1
        assert result["routes"][0]["route_type"] == "MULTI_STOP"
        assert [stop["service_start_time"] for stop in result["routes"][0]["stops"]] == [
            "10:00",
            "11:01",
        ]
    finally:
        connection.close()


def test_provider_schedule_excludes_requested_dates_when_provider_cannot_meet_exact_time(
    tmp_path,
) -> None:
    areas, providers, connection, budget = build_fixture(tmp_path)
    target = date.today() + timedelta(days=7)
    areas[0]["requested_service_windows"] = [
        {
            "survey_id": "approved-survey-early",
            "desired_date": target.isoformat(),
            "desired_time": "09:00",
        }
    ]
    try:
        result = generate_provider_schedule(areas, providers, connection, budget, "efficiency")
        assert result["rounds"] == []
        assert result["unmet_criteria"][0]["reason"] == "REQUESTED_TIME_WINDOW"
    finally:
        connection.close()


def test_provider_schedule_never_uses_an_explicitly_excluded_weekday(tmp_path) -> None:
    areas, providers, connection, budget = build_fixture(tmp_path)
    target = date.today() + timedelta(days=7)
    areas[0]["requested_service_windows"] = [
        {"survey_id": "approved-survey-excluded", "desired_date": target.isoformat()}
    ]
    areas[0]["excluded_days"] = [target.strftime("%A").lower()]
    try:
        result = generate_provider_schedule(areas, providers, connection, budget, "efficiency")
        assert result["rounds"] == []
        assert result["unmet_criteria"][0]["reason"] == "EXCLUDED_DAY_CONFLICT"
    finally:
        connection.close()


def test_provider_schedule_reports_a_requested_date_outside_the_four_week_horizon(tmp_path) -> None:
    areas, providers, connection, budget = build_fixture(tmp_path)
    areas[0]["requested_service_windows"] = [
        {
            "survey_id": "approved-survey-outside-horizon",
            "desired_date": (date.today() + timedelta(days=40)).isoformat(),
            "desired_time": "13:00",
        }
    ]
    try:
        result = generate_provider_schedule(areas, providers, connection, budget, "efficiency")
        assert result["rounds"] == []
        assert result["unmet_criteria"][0]["reason"] == "REQUESTED_DATE_WINDOW"
    finally:
        connection.close()


def test_provider_schedule_applies_minimum_round_policy_and_reports_capacity_gap(tmp_path) -> None:
    areas, providers, connection, budget = build_fixture(tmp_path)
    areas[0]["simulated_monthly_demand"] = 8
    try:
        policy = PlanningPolicy(minimum_services_per_area=5)
        result = generate_provider_schedule(
            areas, providers, connection, budget, "minimum_coverage", policy
        )
        assert result["minimum_services_per_area"] == 5
        assert result["minimum_coverage_met"] is False
        assert result["minimum_frequency_met_areas"] == 0
        assert result["unmet_minimum_frequency_areas"] == 1
        assert result["required_capacity"] == 5
        assert result["required_budget_won"] is None
        assert result["budget_gap_won"] is None
        assert result["required_budget_status"] == "INFEASIBLE"
        assert result["capacity_basis"] == "ELIGIBLE_PROVIDER_MONTH_LIMIT_UPPER_BOUND"
        capacity = result["minimum_capacity_diagnostic"]
        assert capacity["status"] == "PROVEN_CAPACITY_GAP"
        assert capacity["maximum_feasible_areas"] == 0
        assert capacity["maximum_feasible_areas_upper_bound"] == 0
        assert capacity["minimum_rounds_supplied"] == 2
        assert capacity["minimum_rounds_supplied_upper_bound"] == 2
        assert capacity["missing_rounds_lower_bound"] == 3
        assert capacity["missing_rounds_upper_bound"] == 3
        assert 2 <= result["available_capacity"] <= 4
        assert result["missing_capacity"] == 5 - result["available_capacity"]
        assert result["minimum_frequency_gaps"] == [
            {
                "area_id": "area-1",
                "area_name": "도산리",
                "required_rounds": 5,
                "scheduled_rounds": 2,
                "missing_rounds": 3,
                "reason": "PROVIDER_CAPACITY",
                "reasons": ["PROVIDER_CAPACITY", "BUDGET"],
            }
        ]
        below_floor = deepcopy(areas)
        below_floor[0]["simulated_monthly_demand"] = 3
        below_floor_result = generate_provider_schedule(
            below_floor, providers, connection, budget, "minimum_coverage", policy
        )
        assert below_floor_result["minimum_frequency_gaps"][0]["reason"] == (
            "DEMAND_BELOW_MINIMUM"
        )
        assert below_floor_result["minimum_capacity_diagnostic"]["status"] == (
            "DEMAND_BELOW_MINIMUM"
        )
    finally:
        connection.close()


def test_provider_schedule_calculates_minimum_budget_and_shortfall(tmp_path) -> None:
    areas, providers, connection, _ = build_fixture(tmp_path, budget=500_000)
    areas[0]["simulated_monthly_demand"] = 2
    policy = PlanningPolicy(minimum_services_per_area=1)
    try:
        result = generate_provider_schedule(
            areas, providers, connection, 500_000, "minimum_coverage", policy
        )
        assert result["minimum_coverage_met"] is False
        assert result["required_budget_status"] == "CALCULATED"
        assert result["required_budget_model"] == "PROVIDER_CP_SAT_INTEGRATED_KAKAO_VRPTW"
        assert result["required_budget_won"] > 500_000
        assert result["budget_gap_won"] == result["required_budget_won"] - 500_000
        capacity = result["minimum_capacity_diagnostic"]
        assert capacity["status"] == "CAPACITY_FEASIBLE"
        assert capacity["maximum_feasible_areas"] == 1
        assert capacity["missing_rounds_lower_bound"] == 0
        assert capacity["missing_rounds_upper_bound"] == 0
    finally:
        connection.close()


def test_provider_schedule_applies_allowed_service_travel_and_compensation_policies(
    tmp_path,
) -> None:
    areas, providers, connection, budget = build_fixture(tmp_path, budget=1_100_000)
    try:
        excluded = generate_provider_schedule(
            areas,
            providers,
            connection,
            budget,
            "efficiency",
            PlanningPolicy(allowed_services=("home_repair",)),
        )
        assert excluded["rounds"] == []
        assert excluded["unmet_criteria"][0]["reason"] == "SERVICE_NOT_ALLOWED"
        assert excluded["available_capacity"] == 0
        assert excluded["missing_capacity"] == excluded["required_capacity"]
        assert excluded["minimum_frequency_gaps"][0]["reason"] == "SERVICE_NOT_ALLOWED"

        travel_limited = generate_provider_schedule(
            areas,
            providers,
            connection,
            budget,
            "efficiency",
            PlanningPolicy(maximum_round_trip_travel_minutes=5),
        )
        assert travel_limited["rounds"] == []
        assert travel_limited["unmet_criteria"][0]["reason"] == "MAX_TRAVEL_TIME"

        compensation_limited = generate_provider_schedule(
            areas,
            providers,
            connection,
            budget,
            "efficiency",
            PlanningPolicy(minimum_provider_compensation_won=1_500_000),
        )
        assert compensation_limited["rounds"] == []
        assert compensation_limited["unmet_criteria"][0]["reason"] == "BUDGET"
    finally:
        connection.close()


def test_provider_balanced_policy_weights_change_vulnerable_area(tmp_path) -> None:
    areas, providers, connection, budget = build_fixture(tmp_path)
    second_area = {
        **deepcopy(areas[0]),
        "id": "area-2",
        "name": "화계리",
        "simulated_monthly_demand": 1,
        "elderly_ratio_65": 0.0,
        "single_households_total": 10,
        "single_households_65_plus": 10,
    }
    areas[0]["simulated_monthly_demand"] = 1
    areas[0]["elderly_ratio_65"] = 1.0
    areas[0]["single_households_total"] = 10
    areas[0]["single_households_65_plus"] = 0
    areas.append(second_area)
    providers[0]["max_monthly_rounds"] = 1
    base = {"id": "base", "anchor_lat": 36.5, "anchor_lng": 126.6}
    destination = {"id": "area-2", "anchor_lat": 36.52, "anchor_lng": 126.62}
    put_cached(connection, base, destination, Route("base", "area-2", 5_000, 600))
    put_cached(connection, destination, base, Route("area-2", "base", 5_000, 600))
    try:
        elderly_first = generate_provider_schedule(
            areas,
            providers,
            connection,
            budget,
            "balanced",
            PlanningPolicy(
                elderly_priority_weight=1000,
                single_elderly_household_priority_weight=0,
                survey_required_protection_weight=0,
            ),
        )
        single_elderly_first = generate_provider_schedule(
            areas,
            providers,
            connection,
            budget,
            "balanced",
            PlanningPolicy(
                elderly_priority_weight=0,
                single_elderly_household_priority_weight=1000,
                survey_required_protection_weight=0,
            ),
        )
        assert {item["area_id"] for item in elderly_first["rounds"]} == {"area-1"}
        assert {item["area_id"] for item in single_elderly_first["rounds"]} == {"area-2"}
        assert elderly_first["balanced_objective_policy_weights"] == {
            "elderly_priority_weight": 1000,
            "single_elderly_household_priority_weight": 0,
            "survey_required_protection_weight": 0,
        }
        assert single_elderly_first["balanced_objective_policy_weights"] == {
            "elderly_priority_weight": 0,
            "single_elderly_household_priority_weight": 1000,
            "survey_required_protection_weight": 0,
        }
    finally:
        connection.close()


def test_provider_balanced_trades_one_service_unit_for_a_second_area(tmp_path) -> None:
    areas, providers, connection, _budget = build_fixture(tmp_path, budget=2_000_000)
    areas[0]["simulated_monthly_demand"] = 4
    second_area = {
        **deepcopy(areas[0]),
        "id": "area-2",
        "name": "화계리",
        "simulated_monthly_demand": 1,
        "elderly_ratio_65": 0.0,
        "single_households_total": 0,
        "single_households_65_plus": 0,
    }
    areas.append(second_area)
    base = {"id": "base", "anchor_lat": 36.5, "anchor_lng": 126.6}
    first_destination = {"id": "area-1", "anchor_lat": 36.51, "anchor_lng": 126.61}
    destination = {"id": "area-2", "anchor_lat": 36.52, "anchor_lng": 126.62}
    put_cached(connection, base, destination, Route("base", "area-2", 5000, 600))
    put_cached(connection, destination, base, Route("area-2", "base", 5000, 600))
    put_cached(connection, first_destination, destination, Route("area-1", "area-2", 5000, 600))
    put_cached(connection, destination, first_destination, Route("area-2", "area-1", 5000, 600))
    providers[0]["max_monthly_rounds"] = 2
    providers[0]["service_capacity"] = 2
    providers[0]["minimum_compensation_won"] = 0
    try:
        policy = PlanningPolicy()
        efficiency = generate_provider_schedule(
            areas, providers, connection, 2_000_000, "efficiency", policy
        )
        balanced = generate_provider_schedule(
            areas, providers, connection, 2_000_000, "balanced", policy
        )

        assert efficiency["covered_areas"] == 1
        assert efficiency["served_units"] == 4
        assert balanced["covered_areas"] == 2
        assert balanced["served_units"] >= efficiency["served_units"] - 1
        assert balanced["balanced_objective_weights"] == {
            "service_volume": 63,
            "area_coverage": 27,
            "survey_protection": 5,
            "vulnerability": 3,
            "concentration": 1,
            "travel_cost": 1,
        }
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


def test_provider_schedule_reports_shared_monthly_capacity_competition(tmp_path) -> None:
    areas, providers, connection, _budget = build_fixture(tmp_path, budget=3_000_000)
    second_area = {
        **deepcopy(areas[0]),
        "id": "area-2",
        "name": "화계리",
        "simulated_monthly_demand": 1,
    }
    base = {"id": "base", "anchor_lat": 36.5, "anchor_lng": 126.6}
    destination = {"id": "area-2", "anchor_lat": 36.52, "anchor_lng": 126.62}
    put_cached(connection, base, destination, Route("base", "area-2", 5000, 600))
    put_cached(connection, destination, base, Route("area-2", "base", 5000, 600))
    areas[0]["simulated_monthly_demand"] = 1
    areas.append(second_area)
    providers[0]["max_monthly_rounds"] = 1
    providers[0]["service_capacity"] = 1
    try:
        result = generate_provider_schedule(areas, providers, connection, 3_000_000, "efficiency")
        assert result["served_units"] == 1
        assert len(result["unmet_criteria"]) == 1
        assert "SHARED_PROVIDER_CAPACITY" in result["unmet_criteria"][0]["reasons"]
        capacity = result["minimum_capacity_diagnostic"]
        assert capacity["status"] == "PROVEN_CAPACITY_GAP"
        assert capacity["maximum_feasible_areas"] == 1
        assert capacity["maximum_feasible_areas_upper_bound"] == 1
        assert capacity["missing_rounds_lower_bound"] == 1
        assert capacity["missing_rounds_upper_bound"] == 1
    finally:
        connection.close()


def test_provider_schedule_reports_shared_daily_time_competition(tmp_path) -> None:
    areas, providers, connection, _budget = build_fixture(tmp_path, budget=3_000_000)
    second_area = {
        **deepcopy(areas[0]),
        "id": "area-2",
        "name": "화계리",
        "simulated_monthly_demand": 1,
    }
    base = {"id": "base", "anchor_lat": 36.5, "anchor_lng": 126.6}
    destination = {"id": "area-2", "anchor_lat": 36.52, "anchor_lng": 126.62}
    put_cached(connection, base, destination, Route("base", "area-2", 5000, 600))
    put_cached(connection, destination, base, Route("area-2", "base", 5000, 600))
    target = (scheduling.korea_today() + timedelta(days=1)).isoformat()
    for area in [*areas, second_area]:
        area["simulated_monthly_demand"] = 1
        area["requested_service_windows"] = [
            {"survey_id": f"survey-{area['id']}", "desired_date": target}
        ]
    areas.append(second_area)
    providers[0]["max_monthly_rounds"] = 2
    providers[0]["service_capacity"] = 1
    providers[0]["max_daily_hours"] = 1.5
    try:
        result = generate_provider_schedule(areas, providers, connection, 3_000_000, "efficiency")
        assert result["served_units"] == 1
        assert len(result["unmet_criteria"]) == 1
        assert "SHARED_PROVIDER_TIME" in result["unmet_criteria"][0]["reasons"]
    finally:
        connection.close()


def test_provider_schedule_rejects_same_time_visits_that_cannot_share_a_day(tmp_path) -> None:
    areas, providers, connection, _budget = build_fixture(tmp_path, budget=3_000_000)
    second_area = {
        **deepcopy(areas[0]),
        "id": "area-2",
        "name": "화계리",
        "simulated_monthly_demand": 1,
    }
    base = {"id": "base", "anchor_lat": 36.5, "anchor_lng": 126.6}
    destination = {"id": "area-2", "anchor_lat": 36.52, "anchor_lng": 126.62}
    put_cached(connection, base, destination, Route("base", "area-2", 5000, 600))
    put_cached(connection, destination, base, Route("area-2", "base", 5000, 600))
    target = (date.today() + timedelta(days=1)).isoformat()
    for area in [*areas, second_area]:
        area["simulated_monthly_demand"] = 1
        area["requested_service_windows"] = [
            {
                "survey_id": f"survey-{area['id']}",
                "desired_date": target,
                "desired_time": "10:00",
            }
        ]
    areas.append(second_area)
    providers[0]["max_monthly_rounds"] = 2
    providers[0]["service_capacity"] = 1
    try:
        result = generate_provider_schedule(areas, providers, connection, 3_000_000, "efficiency")
        assert result["served_units"] == 1
        assert len(result["rounds"]) == 1
        assert len(result["unmet_criteria"]) == 1
        assert "SHARED_PROVIDER_TIME" in result["unmet_criteria"][0]["reasons"]
    finally:
        connection.close()


def test_provider_schedule_keeps_serial_exact_time_visits_that_fit(tmp_path) -> None:
    areas, providers, connection, _budget = build_fixture(tmp_path, budget=3_000_000)
    second_area = {
        **deepcopy(areas[0]),
        "id": "area-2",
        "name": "화계리",
        "simulated_monthly_demand": 1,
    }
    base = {"id": "base", "anchor_lat": 36.5, "anchor_lng": 126.6}
    destination = {"id": "area-2", "anchor_lat": 36.52, "anchor_lng": 126.62}
    put_cached(connection, base, destination, Route("base", "area-2", 5000, 600))
    put_cached(connection, destination, base, Route("area-2", "base", 5000, 600))
    target = (date.today() + timedelta(days=1)).isoformat()
    for area, requested_time in zip([areas[0], second_area], ["10:00", "12:00"], strict=True):
        area["simulated_monthly_demand"] = 1
        area["requested_service_windows"] = [
            {
                "survey_id": f"survey-{area['id']}",
                "desired_date": target,
                "desired_time": requested_time,
            }
        ]
    areas.append(second_area)
    providers[0]["max_monthly_rounds"] = 2
    providers[0]["service_capacity"] = 1
    try:
        result = generate_provider_schedule(areas, providers, connection, 3_000_000, "efficiency")
        assert result["served_units"] == 2
        assert {item["service_start_time"] for item in result["rounds"]} == {"10:00", "12:00"}
    finally:
        connection.close()


def test_round_trip_fallback_places_flexible_visit_before_fixed_late_visit() -> None:
    common = {
        "provider_id": "provider-1",
        "provider_name": "테스트 공급자",
        "base_area_id": "base",
        "service_type": "laundry",
        "scheduled_date": "2026-10-05",
        "availability_start": "09:00",
        "availability_end": "13:00",
        "max_daily_hours": 6,
    }
    flexible = {
        **common,
        "area_id": "area-flexible",
        "area_name": "유연 권역",
        "duration_minutes": 40,
        "route": {
            "distance_m": 10_000,
            "duration_s": 2_400,
            "cost_won": 8_000,
            "outbound_s": 1_200,
            "inbound_s": 1_200,
            "outbound_distance_m": 5_000,
            "inbound_distance_m": 5_000,
        },
    }
    fixed = {
        **common,
        "area_id": "area-fixed",
        "area_name": "예약 권역",
        "duration_minutes": 20,
        "requested_start_time": "12:00",
        "route": {
            "distance_m": 2_000,
            "duration_s": 600,
            "cost_won": 2_000,
            "outbound_s": 300,
            "inbound_s": 300,
            "outbound_distance_m": 1_000,
            "inbound_distance_m": 1_000,
        },
    }
    provider = {
        "provider_id": "provider-1",
        "name": "테스트 공급자",
        "base_area_id": "base",
        "max_daily_hours": 6,
    }
    roads = {
        ("base", "area-flexible"): (5_000, 1_200),
        ("area-flexible", "base"): (5_000, 1_200),
        ("base", "area-fixed"): (1_000, 300),
        ("area-fixed", "base"): (1_000, 300),
    }
    rounds = [
        {"area_id": "area-flexible", "area_name": "유연 권역"},
        {"area_id": "area-fixed", "area_name": "예약 권역"},
    ]

    routes = scheduling._route_selected_stops(
        [(flexible, rounds[0]), (fixed, rounds[1])], provider, roads
    )

    assert len(routes) == 2
    assert rounds[0]["service_start_time"] == "09:20"
    assert rounds[1]["service_start_time"] == "12:00"


def test_provider_day_respects_joint_serial_feasibility_beyond_pairwise_checks(tmp_path) -> None:
    areas, providers, connection, _budget = build_fixture(tmp_path, budget=50_000_000)
    area_template = deepcopy(areas[0])
    base = {"id": "base", "anchor_lat": 36.5, "anchor_lng": 126.6}
    target = (scheduling.korea_today() + timedelta(days=1)).isoformat()
    fixed_times = {"area-fixed-a": "10:00", "area-fixed-b": "12:30"}
    provider = providers[0]
    provider["max_monthly_rounds"] = 10
    provider["service_capacity"] = 1
    provider["max_daily_hours"] = 6
    provider["availability"] = [
        {"weekday": day, "start_time": "09:00", "end_time": "15:00"}
        for day in (
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
        )
    ]
    areas = []
    try:
        for index, area_id in enumerate(
            ["area-fixed-a", "area-fixed-b", "area-flex-a", "area-flex-b", "area-flex-c"]
        ):
            area = {
                **area_template,
                "id": area_id,
                "name": f"권역 {index + 1}",
                "service_duration_minutes": 60,
                "simulated_monthly_demand": 1,
                "requested_service_windows": [
                    {
                        "survey_id": f"survey-{area_id}",
                        "desired_date": target,
                        **(
                            {"desired_time": fixed_times[area_id]}
                            if area_id in fixed_times
                            else {}
                        ),
                    }
                ],
            }
            areas.append(area)
            destination = {
                "id": area_id,
                "anchor_lat": 36.51 + index * 0.001,
                "anchor_lng": 126.61 + index * 0.001,
            }
            put_cached(connection, base, destination, Route("base", area_id, 1000, 300))
            put_cached(connection, destination, base, Route(area_id, "base", 1000, 300))

        result = generate_provider_schedule(
            areas, providers, connection, 50_000_000, "efficiency"
        )

        assert result["served_units"] == 4
        assert len(result["rounds"]) == 4
        selected_fixed_times = {
            item["service_start_time"]
            for item in result["rounds"]
            if item["area_id"] in fixed_times
        }
        assert selected_fixed_times
        assert selected_fixed_times <= set(fixed_times.values())
        assert all(item["route_type"] == "HUB_ROUND_TRIP" for item in result["rounds"])
        ordered_rounds = sorted(result["rounds"], key=lambda item: item["departure_time"])

        def to_minutes(value: str) -> int:
            hour, minute = (int(part) for part in value.split(":"))
            return hour * 60 + minute

        assert all(
            to_minutes(first["service_end_time"])
            + (int(first["travel_after_s"]) + 59) // 60
            <= to_minutes(second["departure_time"])
            for first, second in zip(ordered_rounds, ordered_rounds[1:], strict=False)
        )
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


def test_wide_lexicographic_objective_keeps_a_feasible_fallback(monkeypatch) -> None:
    real_solver = scheduling.cp_model.CpSolver
    solver_count = 0

    class SolverWrapper:
        def __init__(self, force_unknown: bool) -> None:
            self.inner = real_solver()
            self.parameters = self.inner.parameters
            self.force_unknown = force_unknown

        def solve(self, model):
            if self.force_unknown:
                return scheduling.cp_model.UNKNOWN
            return self.inner.solve(model)

        def value(self, variable):
            return self.inner.value(variable)

        def status_name(self, status):
            return self.inner.status_name(status)

    def solver_factory():
        nonlocal solver_count
        solver_count += 1
        return SolverWrapper(force_unknown=solver_count > 1)

    monkeypatch.setattr(scheduling.cp_model, "CpSolver", solver_factory)
    model = scheduling.cp_model.CpModel()
    selected = model.new_bool_var("selected")
    model.add(selected == 1)

    solver, status, optimality_proven = scheduling._solve_lexicographic_components(
        model, [(selected, True)]
    )

    assert status == scheduling.cp_model.FEASIBLE
    assert optimality_proven is False
    assert solver.value(selected) == 1


def test_provider_schedule_combines_same_day_stops_when_cached_route_saves_travel(
    tmp_path,
) -> None:
    areas, providers, connection, budget = build_fixture(tmp_path)
    second_area = {
        **deepcopy(areas[0]),
        "id": "area-2",
        "name": "화계리",
        "simulated_monthly_demand": 1,
    }
    areas[0]["simulated_monthly_demand"] = 1
    areas.append(second_area)
    second_destination = {"id": "area-2", "anchor_lat": 36.52, "anchor_lng": 126.62}
    base = {"id": "base", "anchor_lat": 36.5, "anchor_lng": 126.6}
    first_destination = {"id": "area-1", "anchor_lat": 36.51, "anchor_lng": 126.61}
    put_cached(connection, base, second_destination, Route("base", "area-2", 6000, 700))
    put_cached(connection, second_destination, base, Route("area-2", "base", 6000, 700))
    put_cached(
        connection, first_destination, second_destination, Route("area-1", "area-2", 2000, 180)
    )
    put_cached(
        connection, second_destination, first_destination, Route("area-2", "area-1", 1500, 150)
    )
    providers[0]["max_monthly_rounds"] = 4
    try:
        result = generate_provider_schedule(areas, providers, connection, budget, "efficiency")
        assert result["served_units"] == 2
        assert len(result["routes"]) == 1
        route = result["routes"][0]
        assert route["route_type"] == "MULTI_STOP"
        assert len(route["stops"]) == 2
        assert route["distance_savings_m"] > 0
        assert route["duration_savings"] > 0
        assert result["routing_comparison"]["multi_stop_route_count"] == 1
        assert result["travel_distance_m"] == route["distance_m"]
        assert result["travel_time_s"] == route["duration_s"]
        assert result["travel_cost_won"] == route["cost_won"]
        assert all(
            item["travel_time_s"] == item["travel_before_s"] + item["travel_after_s"]
            for item in result["rounds"]
        )
    finally:
        connection.close()


def build_route_savings_provider_fixture(tmp_path, *, budget=1_000_000):
    areas, [template_provider], connection, _ = build_fixture(tmp_path, budget=budget)
    second_area = {
        **deepcopy(areas[0]),
        "id": "area-2",
        "name": "화계리",
        "simulated_monthly_demand": 1,
    }
    areas[0]["simulated_monthly_demand"] = 1
    areas.append(second_area)
    bases = [
        {"id": "base-a", "anchor_lat": 36.5, "anchor_lng": 126.6},
        {"id": "base-b", "anchor_lat": 36.49, "anchor_lng": 126.59},
    ]
    stops = [
        {"id": "area-1", "anchor_lat": 36.51, "anchor_lng": 126.61},
        {"id": "area-2", "anchor_lat": 36.52, "anchor_lng": 126.62},
    ]
    for base in bases:
        for index, stop in enumerate(stops):
            if base["id"] == "base-a":
                outbound = inbound = (5000, 300)
            elif index == 0:
                outbound, inbound = (1000, 60), (19000, 1140)
            else:
                outbound, inbound = (19000, 1140), (1000, 60)
            put_cached(
                connection,
                base,
                stop,
                Route(base["id"], stop["id"], *outbound),
            )
            put_cached(
                connection,
                stop,
                base,
                Route(stop["id"], base["id"], *inbound),
            )
    for origin, destination in ((stops[0], stops[1]), (stops[1], stops[0])):
        put_cached(
            connection,
            origin,
            destination,
            Route(origin["id"], destination["id"], 15_000, 900),
        )
    providers = []
    for provider_id, base in (("provider-a", bases[0]), ("provider-b", bases[1])):
        provider = deepcopy(template_provider)
        provider.update(
            {
                "provider_id": provider_id,
                "name": provider_id,
                "base_area_id": base["id"],
                "max_monthly_rounds": 2,
                "service_capacity": 1,
                "minimum_compensation_won": 0,
            }
        )
        providers.append(provider)
    return areas, providers, connection


def test_provider_schedule_uses_integrated_route_cost_to_break_assignment_ties(
    tmp_path,
) -> None:
    areas, providers, connection = build_route_savings_provider_fixture(tmp_path)
    try:
        result = generate_provider_schedule(areas, providers, connection, 1_000_000, "efficiency")
        assert result["served_units"] == 2
        assert {item["provider_id"] for item in result["rounds"]} == {"provider-b"}
        assert result["routes"][0]["route_type"] == "MULTI_STOP"
        assert result["travel_cost_won"] == 36_268
        assert result["travel_cost_won"] < 2 * 42_667
        assert result["route_assignment_model"] == "INTEGRATED_KAKAO_VRPTW"
        assert result["route_matrix_complete"] is True
    finally:
        connection.close()


def test_balanced_provider_assignment_uses_exact_route_cost_after_policy_priorities(
    tmp_path,
) -> None:
    areas, providers, connection = build_route_savings_provider_fixture(tmp_path)
    try:
        result = generate_provider_schedule(areas, providers, connection, 1_000_000, "balanced")
        assert result["served_units"] == 2
        assert result["covered_areas"] == 2
        assert {item["provider_id"] for item in result["rounds"]} == {"provider-b"}
        assert result["routes"][0]["route_type"] == "MULTI_STOP"
    finally:
        connection.close()


def test_integrated_multi_stop_cost_is_used_by_the_hard_budget(tmp_path) -> None:
    areas, providers, connection = build_route_savings_provider_fixture(tmp_path, budget=560_000)
    try:
        result = generate_provider_schedule(areas, providers, connection, 560_000, "efficiency")
        assert result["served_units"] == 2
        assert {item["provider_id"] for item in result["rounds"]} == {"provider-b"}
        assert result["routes"][0]["route_type"] == "MULTI_STOP"
        assert result["budget_spent_won"] == 546_268
        assert result["total_cost_won"] <= 560_000
    finally:
        connection.close()


def test_provider_schedule_falls_back_to_cached_round_trips_when_stop_leg_is_missing(
    tmp_path,
) -> None:
    areas, providers, connection, budget = build_fixture(tmp_path)
    second_area = {
        **deepcopy(areas[0]),
        "id": "area-2",
        "name": "화계리",
        "simulated_monthly_demand": 1,
    }
    areas[0]["simulated_monthly_demand"] = 1
    areas.append(second_area)
    base = {"id": "base", "anchor_lat": 36.5, "anchor_lng": 126.6}
    second_destination = {"id": "area-2", "anchor_lat": 36.52, "anchor_lng": 126.62}
    put_cached(connection, base, second_destination, Route("base", "area-2", 6000, 700))
    put_cached(connection, second_destination, base, Route("area-2", "base", 6000, 700))
    providers[0]["max_monthly_rounds"] = 4
    try:
        result = generate_provider_schedule(areas, providers, connection, budget, "efficiency")
        assert result["served_units"] == 2
        assert len(result["routes"]) == 2
        assert {route["route_type"] for route in result["routes"]} == {"HUB_ROUND_TRIP"}
        assert result["routing_comparison"]["multi_stop_route_count"] == 0
        assert result["travel_distance_m"] == sum(route["distance_m"] for route in result["routes"])
    finally:
        connection.close()


def test_balanced_schedule_uses_bounded_objective_for_many_candidate_dates(tmp_path) -> None:
    areas, providers, connection, _ = build_fixture(tmp_path, budget=10_000_000)
    base = {"id": "base", "anchor_lat": 36.5, "anchor_lng": 126.6}
    many_areas = []
    for index in range(16):
        area_id = f"wide-{index:02d}"
        area = {
            **deepcopy(areas[0]),
            "id": area_id,
            "name": f"권역 {index + 1}",
            "simulated_monthly_demand": 1,
        }
        destination = {
            "id": area_id,
            "anchor_lat": 36.51 + index * 0.001,
            "anchor_lng": 126.61 + index * 0.001,
        }
        put_cached(connection, base, destination, Route("base", area_id, 5000, 600))
        put_cached(connection, destination, base, Route(area_id, "base", 5000, 600))
        many_areas.append(area)
    many_providers = []
    for index in range(3):
        provider = deepcopy(providers[0])
        provider["provider_id"] = f"wide-provider-{index}"
        provider["name"] = f"테스트 공급자 {index + 1}"
        provider["max_monthly_rounds"] = 20
        provider["minimum_compensation_won"] = 0
        many_providers.append(provider)
    try:
        result = generate_provider_schedule(
            many_areas, many_providers, connection, 10_000_000, "balanced"
        )
        assert result["solver_status"] in {"OPTIMAL", "FEASIBLE"}
        assert result["served_units"] > 0
    finally:
        connection.close()
