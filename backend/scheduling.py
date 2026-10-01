"""Provider-specific monthly service schedules using CP-SAT and cached road routes."""

from __future__ import annotations

import math
import sqlite3
import time
from collections import defaultdict
from copy import deepcopy
from datetime import date, datetime, timedelta
from functools import lru_cache
from typing import Any, Literal

from ortools.sat.python import cp_model

from backend.optimization import (
    MAX_SOLVER_SECONDS,
    SERVICE_COST_WON,
    TRAVEL_LABOR_WON_PER_HOUR,
    TRAVEL_RATE_WON_PER_KM,
    _lexicographic_score,
    _validate_policy,
    _vulnerability_points,
)
from backend.routing import MissingRoadLegError, optimize_multi_stop_route
from backend.settings import PlanningPolicy
from backend.timeutils import korea_today

Scenario = Literal["efficiency", "balanced", "minimum_coverage"]


def _solve_lexicographic_components(
    model: cp_model.CpModel,
    components: list[tuple[Any, bool]],
) -> tuple[cp_model.CpSolver, int, bool]:
    """Keep a feasible incumbent while optimizing wide lexicographic objectives."""
    started = time.monotonic()
    feasibility_solver = cp_model.CpSolver()
    feasibility_solver.parameters.max_time_in_seconds = MAX_SOLVER_SECONDS
    feasibility_solver.parameters.num_search_workers = 1
    feasibility_solver.parameters.random_seed = 2026
    model.minimize(0)
    status = feasibility_solver.solve(model)
    if status not in {cp_model.OPTIMAL, cp_model.FEASIBLE}:
        raise RuntimeError(
            "provider scheduling found no feasible plan "
            f"({feasibility_solver.status_name(status)})"
        )

    solver = feasibility_solver
    status = cp_model.FEASIBLE
    optimality_proven = True
    for expression, maximize in components:
        remaining = MAX_SOLVER_SECONDS - (time.monotonic() - started)
        if remaining <= 0:
            optimality_proven = False
            break
        stage_solver = cp_model.CpSolver()
        stage_solver.parameters.max_time_in_seconds = remaining
        stage_solver.parameters.num_search_workers = 1
        stage_solver.parameters.random_seed = 2026
        if maximize:
            model.maximize(expression)
        else:
            model.minimize(expression)
        status = stage_solver.solve(model)
        if status == cp_model.UNKNOWN:
            # Preserve the last valid incumbent; objective optimality remains unproven.
            status = cp_model.FEASIBLE
            optimality_proven = False
            break
        if status not in {cp_model.OPTIMAL, cp_model.FEASIBLE}:
            raise RuntimeError(
                f"provider scheduling found no feasible plan ({stage_solver.status_name(status)})"
            )
        solver = stage_solver
        model.add(expression == solver.value(expression))
        if status != cp_model.OPTIMAL:
            optimality_proven = False
            break
    if solver is None:
        raise RuntimeError("provider scheduling could not start within its solver time budget")
    all_components_solved = len(components) == 0 or (
        optimality_proven and status == cp_model.OPTIMAL
    )
    return solver, status, all_components_solved


def _route_rows(connection: sqlite3.Connection) -> dict[tuple[str, str], tuple[int, int]]:
    return {
        (str(origin), str(destination)): (int(distance), int(duration))
        for origin, destination, distance, duration in connection.execute(
            "SELECT origin_id, destination_id, distance_m, duration_s FROM travel_matrix"
        ).fetchall()
    }


def _round_trip(
    routes: dict[tuple[str, str], tuple[int, int]], base_area_id: str, area_id: str
) -> dict[str, int]:
    outbound = routes.get((base_area_id, area_id))
    inbound = routes.get((area_id, base_area_id))
    if outbound is None or inbound is None:
        raise ValueError(f"provider road route missing for {base_area_id} and {area_id}")
    distance_m = outbound[0] + inbound[0]
    duration_s = outbound[1] + inbound[1]
    cost_won = math.ceil(distance_m / 1000 * TRAVEL_RATE_WON_PER_KM)
    cost_won += math.ceil(duration_s / 3600 * TRAVEL_LABOR_WON_PER_HOUR)
    return {
        "outbound_distance_m": outbound[0],
        "inbound_distance_m": inbound[0],
        "distance_m": distance_m,
        "outbound_s": outbound[1],
        "inbound_s": inbound[1],
        "duration_s": duration_s,
        "cost_won": cost_won,
    }


def _minute(value: str) -> int:
    parsed = datetime.strptime(value, "%H:%M")
    return parsed.hour * 60 + parsed.minute


def _time(value: int) -> str:
    return f"{value // 60:02d}:{value % 60:02d}"


def _requested_date_matches(raw_date: Any, candidate: date) -> bool:
    if raw_date in (None, ""):
        return True
    value = str(raw_date).strip()
    try:
        if len(value) == 5 and value[2] == "-":
            return candidate.strftime("%m-%d") == value
        return date.fromisoformat(value) == candidate
    except ValueError:
        return False


def _make_candidates(
    areas: list[dict[str, Any]],
    providers: list[dict[str, Any]],
    routes: dict[tuple[str, str], tuple[int, int]],
    policy: PlanningPolicy,
) -> tuple[list[dict[str, Any]], dict[str, set[str]]]:
    today = korea_today()
    planning_dates = [today + timedelta(days=offset) for offset in range(1, 29)]
    weekday_names = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
    candidates: list[dict[str, Any]] = []
    blocked: dict[str, set[str]] = {str(area["id"]): set() for area in areas}
    for area in areas:
        area_id = str(area["id"])
        preferred = {str(day).lower() for day in area.get("preferred_days", [])}
        excluded = {str(day).lower() for day in area.get("excluded_days", [])}
        requested_windows = [
            window
            for window in area.get("requested_service_windows", [])
            if window.get("desired_date") or window.get("desired_time")
        ]
        requested_date_windows = [
            window for window in requested_windows if window.get("desired_date")
        ]
        if requested_date_windows and not any(
            _requested_date_matches(window.get("desired_date"), planning_date)
            for window in requested_date_windows
            for planning_date in planning_dates
        ):
            blocked[area_id].add("REQUESTED_DATE_WINDOW")
        demand = max(0, int(area.get("simulated_monthly_demand", 0)))
        if demand == 0:
            continue
        if str(area["service_type"]) not in policy.allowed_services:
            blocked[area_id].add("SERVICE_NOT_ALLOWED")
            continue
        capable_providers = [
            provider
            for provider in providers
            if str(area["service_type"]) in provider["supported_services"]
        ]
        if not capable_providers:
            blocked[area_id].add("NO_SUPPORTED_PROVIDER")
            continue
        for provider in capable_providers:
            provider_id = str(provider["provider_id"])
            participation_preferences = {
                (str(item["scope"]), str(item["period_start"])): str(item["status"])
                for item in provider.get("participation_preferences", [])
            }
            weekday_availability: dict[str, list[dict[str, str]]] = {}
            for item in provider["availability"]:
                weekday_availability.setdefault(item["weekday"], []).append(item)
            for round_date in planning_dates:
                month_key = ("MONTH", round_date.replace(day=1).isoformat())
                week_key = (
                    "WEEK",
                    (round_date - timedelta(days=round_date.weekday())).isoformat(),
                )
                if week_key in participation_preferences:
                    participation_status = participation_preferences[week_key]
                    participation_source = "WEEK"
                elif month_key in participation_preferences:
                    participation_status = participation_preferences[month_key]
                    participation_source = "MONTH"
                else:
                    participation_status = "AVAILABLE"
                    participation_source = None
                if participation_status == "DECLINED":
                    blocked[area_id].add("PROVIDER_DECLINED")
                    continue
                weekday = weekday_names[round_date.weekday()]
                if weekday in excluded:
                    blocked[area_id].add("EXCLUDED_DAY_CONFLICT")
                    continue
                if preferred and weekday not in preferred:
                    blocked[area_id].add("PREFERRED_DAY_CONFLICT")
                    continue
                matching_windows = [
                    window
                    for window in requested_windows
                    if _requested_date_matches(window.get("desired_date"), round_date)
                ]
                matching_date_windows = [
                    window
                    for window in requested_date_windows
                    if _requested_date_matches(window.get("desired_date"), round_date)
                ]
                time_only_windows = [
                    window for window in requested_windows if not window.get("desired_date")
                ]
                if requested_date_windows and not matching_date_windows and not time_only_windows:
                    continue
                if requested_date_windows and not matching_date_windows:
                    matching_windows = time_only_windows
                date_availability = [
                    item
                    for item in provider.get("date_availability", [])
                    if item["available_date"] == round_date.isoformat()
                ]
                if date_availability:
                    availabilities = [
                        {"start_time": item["start_time"], "end_time": item["end_time"]}
                        for item in date_availability
                        if item["service_type"] == area["service_type"]
                    ]
                else:
                    availabilities = weekday_availability.get(weekday, [])
                if not availabilities:
                    blocked[area_id].add("PROVIDER_UNAVAILABLE")
                    continue
                try:
                    trip = _round_trip(routes, str(provider["base_area_id"]), area_id)
                except ValueError:
                    raise
                max_travel_minutes = int(provider["max_travel_time_minutes"])
                if policy.maximum_round_trip_travel_minutes is not None:
                    max_travel_minutes = min(
                        max_travel_minutes, policy.maximum_round_trip_travel_minutes
                    )
                max_travel = max_travel_minutes * 60
                if trip["duration_s"] > max_travel:
                    blocked[area_id].add("MAX_TRAVEL_TIME")
                    continue
                duration_minutes = max(1, int(area.get("service_duration_minutes", 60)))
                total_work_seconds = trip["duration_s"] + duration_minutes * 60
                if total_work_seconds > float(provider["max_daily_hours"]) * 3600:
                    blocked[area_id].add("MAX_DAILY_HOURS")
                    continue
                for availability in availabilities:
                    availability_start = _minute(availability["start_time"])
                    availability_end = _minute(availability["end_time"])
                    outbound_minutes = math.ceil(trip["outbound_s"] / 60)
                    time_options: list[tuple[str | None, list[str]]] = []
                    if not requested_windows:
                        time_options.append((None, []))
                    else:
                        date_only_windows = [
                            window
                            for window in matching_windows
                            if not window.get("desired_time")
                        ]
                        if date_only_windows:
                            time_options.append(
                                (
                                    None,
                                    [
                                        str(window.get("survey_id", ""))
                                        for window in date_only_windows
                                    ],
                                )
                            )
                        exact_times: dict[str, list[str]] = {}
                        for window in matching_windows:
                            raw_time = window.get("desired_time")
                            if not raw_time:
                                continue
                            desired_time = str(raw_time)
                            try:
                                _minute(desired_time)
                            except ValueError:
                                blocked[area_id].add("REQUESTED_TIME_WINDOW")
                                continue
                            exact_times.setdefault(desired_time, []).append(
                                str(window.get("survey_id", ""))
                            )
                        time_options.extend(
                            (desired_time, survey_ids)
                            for desired_time, survey_ids in exact_times.items()
                        )
                        if not time_options:
                            blocked[area_id].add("REQUESTED_TIME_WINDOW")
                            continue
                    for desired_start, survey_ids in time_options:
                        service_start = (
                            _minute(desired_start)
                            if desired_start is not None
                            else availability_start + outbound_minutes
                        )
                        departure_minute = service_start - outbound_minutes
                        service_end = service_start + duration_minutes
                        return_at = service_end + math.ceil(trip["inbound_s"] / 60)
                        if (
                            departure_minute < availability_start
                            or return_at > availability_end
                        ):
                            blocked[area_id].add(
                                "REQUESTED_TIME_WINDOW" if desired_start else "TIME_WINDOW"
                            )
                            continue
                        candidate = {
                            "provider_id": provider_id,
                            "provider_name": provider["name"],
                            "area_id": area_id,
                            "area_name": str(area.get("name", area_id)),
                            "service_type": str(area["service_type"]),
                            "scheduled_date": round_date.isoformat(),
                            "weekday": weekday,
                            "departure_time": _time(departure_minute),
                            "availability_start": availability["start_time"],
                            "availability_end": availability["end_time"],
                            "estimated_work_minutes": (
                                outbound_minutes
                                + duration_minutes
                                + math.ceil(trip["inbound_s"] / 60)
                            ),
                            "base_area_id": str(provider["base_area_id"]),
                            "max_daily_hours": float(provider["max_daily_hours"]),
                            "service_start_time": _time(service_start),
                            "service_end_time": _time(service_end),
                            "duration_minutes": duration_minutes,
                            "service_capacity": max(1, int(provider["service_capacity"])),
                            "max_monthly_rounds": max(0, int(provider["max_monthly_rounds"])),
                            "participation_status": participation_status,
                            "participation_source": participation_source,
                            "minimum_compensation_won": max(
                                0,
                                int(provider["minimum_compensation_won"]),
                                policy.minimum_provider_compensation_won,
                            ),
                            "route": trip,
                            "month": round_date.strftime("%Y-%m"),
                        }
                        if requested_windows:
                            candidate["time_window_source"] = "SURVEY INPUT; HUMAN REVIEW"
                            candidate["requested_survey_ids"] = [
                                survey_id for survey_id in survey_ids if survey_id
                            ]
                        if desired_start is not None:
                            candidate["requested_start_time"] = desired_start
                        candidates.append(candidate)
    return candidates, blocked


def _pairwise_multi_stop_metrics(
    first: dict[str, Any],
    second: dict[str, Any],
    routes: dict[tuple[str, str], tuple[int, int]],
) -> tuple[int, int, int] | None:
    """Return conservative cost, duration, and distance for a feasible two-stop route."""
    if first["area_id"] == second["area_id"]:
        return None
    if (
        first["provider_id"] != second["provider_id"]
        or first["scheduled_date"] != second["scheduled_date"]
        or first["base_area_id"] != second["base_area_id"]
        or first["availability_start"] != second["availability_start"]
        or first["availability_end"] != second["availability_end"]
    ):
        return None

    base_id = str(first["base_area_id"])
    first_area = str(first["area_id"])
    second_area = str(second["area_id"])
    required_legs = (
        (base_id, first_area),
        (first_area, base_id),
        (base_id, second_area),
        (second_area, base_id),
        (first_area, second_area),
        (second_area, first_area),
    )
    if any(leg not in routes for leg in required_legs):
        return None

    available_start = _minute(str(first["availability_start"]))
    available_end = _minute(str(first["availability_end"]))
    work_limit = min(
        available_end,
        available_start + int(float(first["max_daily_hours"]) * 60),
    )
    feasible_routes: list[tuple[int, int, int]] = []
    for order in ((first, second), (second, first)):
        current = available_start
        previous_area = base_id
        service_minutes = 0
        route_duration = 0
        route_cost = 0
        route_distance = 0
        feasible = True
        for candidate in order:
            area_id = str(candidate["area_id"])
            distance_m, duration_s = routes[(previous_area, area_id)]
            travel_minutes = math.ceil(duration_s / 60)
            arrival = current + service_minutes + travel_minutes
            requested_start = candidate.get("requested_start_time")
            service_start = max(
                arrival,
                _minute(str(requested_start)) if requested_start else arrival,
            )
            latest_start = (
                _minute(str(requested_start))
                if requested_start
                else available_end - int(candidate["duration_minutes"])
            )
            duration_minutes = int(candidate["duration_minutes"])
            if service_start > latest_start or service_start + duration_minutes > available_end:
                feasible = False
                break
            current = service_start
            service_minutes = duration_minutes
            previous_area = area_id
            route_duration += int(duration_s)
            route_distance += int(distance_m)
            route_cost += math.ceil(distance_m / 1000 * TRAVEL_RATE_WON_PER_KM)
            route_cost += math.ceil(duration_s / 3600 * TRAVEL_LABOR_WON_PER_HOUR)
        if not feasible:
            continue
        distance_m, duration_s = routes[(previous_area, base_id)]
        route_duration += int(duration_s)
        route_distance += int(distance_m)
        route_cost += math.ceil(distance_m / 1000 * TRAVEL_RATE_WON_PER_KM)
        route_cost += math.ceil(duration_s / 3600 * TRAVEL_LABOR_WON_PER_HOUR)
        finish = current + service_minutes + math.ceil(duration_s / 60)
        if finish > work_limit:
            continue
        feasible_routes.append((route_cost, route_duration, route_distance))
    if not feasible_routes:
        return None
    minimum_route_cost = min(cost for cost, _duration, _distance in feasible_routes)
    # Equal-cost route order is not the routing engine's time/distance objective,
    # so use the slower and longer tie as the conservative estimate.
    return (
        minimum_route_cost,
        max(
            duration
            for cost, duration, _distance in feasible_routes
            if cost == minimum_route_cost
        ),
        max(
            distance
            for cost, _duration, distance in feasible_routes
            if cost == minimum_route_cost
        ),
    )


def _pairwise_multi_stop_savings(
    first: dict[str, Any],
    second: dict[str, Any],
    routes: dict[tuple[str, str], tuple[int, int]],
) -> tuple[int, int]:
    """Return feasible two-stop Kakao savings used only as a scheduling tie-break."""
    metrics = _pairwise_multi_stop_metrics(first, second, routes)
    if metrics is None:
        return 0, 0
    route_cost, route_duration, _route_distance = metrics
    old_cost = int(first["route"]["cost_won"]) + int(second["route"]["cost_won"])
    old_duration = int(first["route"]["duration_s"]) + int(second["route"]["duration_s"])
    if route_cost > old_cost or route_duration > old_duration:
        return 0, 0
    savings = (old_cost - route_cost, old_duration - route_duration)
    return savings if savings != (0, 0) else (0, 0)


def _pairwise_independent_round_trips_feasible(
    first: dict[str, Any], second: dict[str, Any]
) -> bool:
    """Check whether either serial hub-tour order meets both visits' time windows."""
    if (
        first["provider_id"] != second["provider_id"]
        or first["scheduled_date"] != second["scheduled_date"]
        or first["base_area_id"] != second["base_area_id"]
        or first["availability_start"] != second["availability_start"]
        or first["availability_end"] != second["availability_end"]
    ):
        return False
    available_start = _minute(str(first["availability_start"]))
    available_end = _minute(str(first["availability_end"]))
    work_limit = min(
        available_end,
        available_start + int(float(first["max_daily_hours"]) * 60),
    )
    for order in ((first, second), (second, first)):
        current = available_start
        feasible = True
        for candidate in order:
            route = candidate["route"]
            outbound_minutes = math.ceil(int(route["outbound_s"]) / 60)
            requested_start = candidate.get("requested_start_time")
            service_start = (
                _minute(str(requested_start))
                if requested_start
                else current + outbound_minutes
            )
            departure = service_start - outbound_minutes
            return_at = (
                service_start
                + int(candidate["duration_minutes"])
                + math.ceil(int(route["inbound_s"]) / 60)
            )
            if departure < current or return_at > work_limit:
                feasible = False
                break
            current = return_at
        if feasible:
            return True
    return False


def _pairwise_provider_day_compatible(
    first: dict[str, Any],
    second: dict[str, Any],
    routes: dict[tuple[str, str], tuple[int, int]],
) -> bool:
    """Accept a pair only when its optimized route or serial fallback is schedulable."""
    if first["area_id"] == second["area_id"]:
        return False
    metrics = _pairwise_multi_stop_metrics(first, second, routes)
    if metrics is not None:
        route_cost, route_duration, route_distance = metrics
        old_cost = int(first["route"]["cost_won"]) + int(second["route"]["cost_won"])
        old_duration = int(first["route"]["duration_s"]) + int(second["route"]["duration_s"])
        old_distance = int(first["route"]["distance_m"]) + int(second["route"]["distance_m"])
        if (
            route_cost <= old_cost
            and route_duration <= old_duration
            and (
                route_cost < old_cost
                or route_duration < old_duration
                or route_distance < old_distance
            )
        ):
            return True
    return _pairwise_independent_round_trips_feasible(first, second)


def _fits_selected_provider_day(
    candidate: dict[str, Any],
    selected: list[tuple[dict[str, Any], dict[str, Any]]],
) -> bool:
    """Check the scheduler's active-window and estimated-work constraints for one more visit."""
    if not selected:
        return True
    candidate_window = (candidate["availability_start"], candidate["availability_end"])
    selected_windows = {
        (item["availability_start"], item["availability_end"])
        for item, _round in selected
    }
    candidate_start = _minute(candidate_window[0])
    candidate_end = _minute(candidate_window[1])
    if any(
        window != candidate_window
        and _minute(window[0]) < candidate_end
        and candidate_start < _minute(window[1])
        for window in selected_windows
    ):
        return False
    already_used = sum(int(item["estimated_work_minutes"]) for item, _round in selected)
    daily_minutes = int(float(candidate["max_daily_hours"]) * 60)
    return already_used + int(candidate["estimated_work_minutes"]) <= daily_minutes


def _minimum_budget_upper_bound(
    candidates: list[dict[str, Any]], providers: list[dict[str, Any]], policy: PlanningPolicy
) -> int:
    provider_lookup = {str(provider["provider_id"]): provider for provider in providers}
    maximum_service_cost: dict[tuple[str, str], int] = defaultdict(int)
    minimum_compensation: dict[tuple[str, str], int] = {}
    for candidate in candidates:
        key = (str(candidate["provider_id"]), str(candidate["month"]))
        maximum_service_cost[key] += (
            int(candidate["service_capacity"]) * SERVICE_COST_WON[candidate["service_type"]]
        )
        minimum_compensation[key] = max(
            int(provider_lookup[key[0]]["minimum_compensation_won"]),
            policy.minimum_provider_compensation_won,
        )
    maximum_provider_pay = sum(
        max(maximum_service_cost[key], minimum_compensation[key])
        for key in maximum_service_cost
    )
    maximum_travel_cost = sum(int(candidate["route"]["cost_won"]) for candidate in candidates)
    return max(1, maximum_provider_pay + maximum_travel_cost)


def _calculate_minimum_budget(
    areas: list[dict[str, Any]],
    providers: list[dict[str, Any]],
    connection: sqlite3.Connection,
    candidates: list[dict[str, Any]],
    budget_won: int,
    policy: PlanningPolicy,
) -> tuple[int | None, str, str | None]:
    if any(
        int(area.get("simulated_monthly_demand", 0)) < policy.minimum_services_per_area
        for area in areas
    ):
        return None, "INFEASIBLE", "DEMAND_BELOW_MINIMUM"
    try:
        required = generate_provider_schedule(
            deepcopy(areas),
            deepcopy(providers),
            connection,
            _minimum_budget_upper_bound(candidates, providers, policy),
            "minimum_coverage",
            policy,
            _required_budget_only=True,
        )
    except RuntimeError:
        return None, "INFEASIBLE", "PROVIDER_CAPACITY_OR_TIME"
    if not required["optimality_proven"]:
        return None, "NOT_PROVEN", "OPTIMALITY_NOT_PROVEN"
    return int(required["required_budget_won"]), "CALCULATED", None


def _serial_round_trip_order(
    selected: list[tuple[dict[str, Any], dict[str, Any]]],
) -> tuple[tuple[int, int, int, int], ...] | None:
    """Find a feasible independent hub-tour order around any fixed visit times."""
    if not selected:
        return ()
    first = selected[0][0]
    available_start = _minute(str(first["availability_start"]))
    available_end = _minute(str(first["availability_end"]))
    daily_work_limit = min(
        available_end - available_start,
        int(float(first["max_daily_hours"]) * 60),
    )
    work_minutes = sum(
        int(
            candidate.get(
                "estimated_work_minutes",
                int(candidate["duration_minutes"])
                + math.ceil(
                    (
                        int(candidate["route"]["outbound_s"])
                        + int(candidate["route"]["inbound_s"])
                    )
                    / 60
                ),
            )
        )
        for candidate, _item in selected
    )
    if work_minutes > daily_work_limit:
        return None

    candidate_order = sorted(
        range(len(selected)),
        key=lambda index: (
            selected[index][0].get("requested_start_time") is None,
            selected[index][0].get("requested_start_time", ""),
            selected[index][0]["area_id"],
            selected[index][0]["service_type"],
        ),
    )
    all_selected = (1 << len(selected)) - 1

    @lru_cache(maxsize=None)
    def search(mask: int, current_minute: int) -> tuple[tuple[int, int, int, int], ...] | None:
        if mask == all_selected:
            return ()
        for index in candidate_order:
            bit = 1 << index
            if mask & bit:
                continue
            candidate = selected[index][0]
            route = candidate["route"]
            outbound_minutes = math.ceil(int(route["outbound_s"]) / 60)
            requested_start = candidate.get("requested_start_time")
            service_start = (
                _minute(str(requested_start))
                if requested_start
                else current_minute + outbound_minutes
            )
            departure = service_start - outbound_minutes
            service_end = service_start + int(candidate["duration_minutes"])
            return_minute = service_end + math.ceil(int(route["inbound_s"]) / 60)
            if departure < current_minute or return_minute > available_end:
                continue
            suffix = search(mask | bit, return_minute)
            if suffix is not None:
                return ((index, departure, service_start, service_end), *suffix)
        return None

    return search(0, available_start)


def _route_selected_stops(
    selected: list[tuple[dict[str, Any], dict[str, Any]]],
    provider: dict[str, Any],
    roads: dict[tuple[str, str], tuple[int, int]],
    route_order: list[str] | None = None,
    route_group_key: str | None = None,
) -> list[dict[str, Any]]:
    """Use one feasible multi-stop route when it improves on independent round trips."""
    if not selected:
        return []
    provider_id = str(provider["provider_id"])
    first_candidate = selected[0][0]
    route_date = first_candidate["scheduled_date"]
    base_id = str(provider["base_area_id"])
    old_distance = sum(candidate["route"]["distance_m"] for candidate, _ in selected)
    old_duration = sum(candidate["route"]["duration_s"] for candidate, _ in selected)
    old_cost = sum(candidate["route"]["cost_won"] for candidate, _ in selected)
    route_type = "HUB_ROUND_TRIP"
    route_key = route_group_key or f"{provider_id}::{route_date}"
    route_result = None
    if len(selected) > 1:
        try:
            selected_by_area = {candidate["area_id"]: item for candidate, item in selected}
            route_stops = [
                (candidate, selected_by_area[candidate["area_id"]])
                for candidate, _item in selected
            ]
            if route_order is not None:
                route_order_map = {candidate["area_id"]: candidate for candidate, _ in selected}
                route_stops = [
                    (route_order_map[area_id], selected_by_area[area_id])
                    for area_id in route_order
                ]
            route_result = optimize_multi_stop_route(
                base_id,
                [
                    {
                        "area_id": candidate["area_id"],
                        "name": item["area_name"],
                        "duration_minutes": candidate["duration_minutes"],
                        **(
                            {
                                "service_start_window_start": candidate["requested_start_time"],
                                "service_start_window_end": candidate["requested_start_time"],
                            }
                            if candidate.get("requested_start_time")
                            else {}
                        ),
                    }
                    for candidate, item in route_stops
                ],
                roads,
                available_from=first_candidate["availability_start"],
                available_until=first_candidate["availability_end"],
                max_daily_hours=float(provider["max_daily_hours"]),
                fixed_order=route_order,
            )
        except MissingRoadLegError:
            # Preserve valid cached hub round trips when only an inter-stop leg is absent.
            route_result = None
    if route_order is not None and route_result is None:
        raise RuntimeError("the integrated route solver order could not be serialized")
    use_multi_stop = bool(
        route_result
        and route_result["cost_won"] <= old_cost
        and route_result["duration_s"] <= old_duration
        and (
            route_order is not None
            or
            route_result["distance_m"] < old_distance
            or route_result["duration_s"] < old_duration
            or route_result["cost_won"] < old_cost
        )
    )
    if use_multi_stop:
        route_type = "MULTI_STOP"
        selected_items = {item["area_id"]: item for _candidate, item in selected}
        stops: list[dict[str, Any]] = []
        for stop in route_result["stops"]:
            item = selected_items[str(stop["area_id"])]
            item.update(
                {
                    "departure_time": stop["departure_time"],
                    "service_start_time": stop["service_start_time"],
                    "service_end_time": stop["service_end_time"],
                    "travel_before_s": stop["travel_before_s"],
                    "travel_after_s": stop["travel_after_s"],
                    "travel_time_s": stop["travel_before_s"] + stop["travel_after_s"],
                    "travel_distance_m": stop["travel_distance_m"],
                    "travel_before_distance_m": stop["travel_before_distance_m"],
                    "travel_after_distance_m": stop["travel_after_distance_m"],
                    "travel_cost_won": stop["travel_cost_won"],
                    "route_type": route_type,
                    "route_group_key": route_key,
                    "route_sequence": stop["route_sequence"],
                    "route_from_area_id": stop["route_from_area_id"],
                    "route_to_area_id": stop["route_to_area_id"],
                }
            )
            stops.append(
                {
                    "area_id": item["area_id"],
                    "area_name": item["area_name"],
                    "sequence": stop["route_sequence"],
                    "incoming_from_area_id": stop["route_from_area_id"],
                    "outgoing_to_area_id": stop["route_to_area_id"],
                    "service_start_time": item["service_start_time"],
                    "service_end_time": item["service_end_time"],
                    "travel_before_s": item["travel_before_s"],
                    "travel_after_s": item["travel_after_s"],
                    "travel_before_distance_m": item["travel_before_distance_m"],
                    "travel_after_distance_m": item["travel_after_distance_m"],
                }
            )
        return [
            {
                "route_group_key": route_key,
                "provider_id": provider_id,
                "provider_name": provider["name"],
                "scheduled_date": route_date,
                "route_type": route_type,
                "base_area_id": base_id,
                "stop_area_ids": [stop["area_id"] for stop in stops],
                "distance_m": route_result["distance_m"],
                "duration_s": route_result["duration_s"],
                "cost_won": route_result["cost_won"],
                "old_hub_round_trip_distance_m": old_distance,
                "old_hub_round_trip_duration_s": old_duration,
                "old_hub_round_trip_cost_won": old_cost,
                "distance_savings_m": old_distance - route_result["distance_m"],
                "duration_savings": old_duration - route_result["duration_s"],
                "cost_savings_won": old_cost - route_result["cost_won"],
                "stops": stops,
                "provenance": "OR-TOOLS ROUTING; KAKAO ROAD CACHE; SIMULATED PROVIDER",
            }
        ]

    serial_order = _serial_round_trip_order(selected)
    if serial_order is None:
        raise RuntimeError("selected rounds cannot fit provider availability and daily work time")
    standalone_routes: list[dict[str, Any]] = []
    for sequence, (index, departure_minute, service_start, service_end) in enumerate(
        serial_order, start=1
    ):
        candidate, item = selected[index]
        route = candidate["route"]
        item.update(
            {
                "departure_time": _time(departure_minute),
                "service_start_time": _time(service_start),
                "service_end_time": _time(service_end),
                "travel_before_s": route["outbound_s"],
                "travel_after_s": route["inbound_s"],
                "travel_time_s": route["duration_s"],
                "travel_distance_m": route["distance_m"],
                "travel_before_distance_m": route["outbound_distance_m"],
                "travel_after_distance_m": route["inbound_distance_m"],
                "travel_cost_won": route["cost_won"],
                "route_type": "HUB_ROUND_TRIP",
                "route_group_key": f"{provider_id}::{route_date}::{item['area_id']}",
                "route_sequence": sequence,
                "route_from_area_id": base_id,
                "route_to_area_id": base_id,
            }
        )
        standalone_routes.append(
            {
                "route_group_key": item["route_group_key"],
                "provider_id": provider_id,
                "provider_name": provider["name"],
                "scheduled_date": route_date,
                "route_type": "HUB_ROUND_TRIP",
                "base_area_id": base_id,
                "stop_area_ids": [item["area_id"]],
                "distance_m": route["distance_m"],
                "duration_s": route["duration_s"],
                "cost_won": route["cost_won"],
                "old_hub_round_trip_distance_m": route["distance_m"],
                "old_hub_round_trip_duration_s": route["duration_s"],
                "old_hub_round_trip_cost_won": route["cost_won"],
                "distance_savings_m": 0,
                "duration_savings": 0,
                "cost_savings_won": 0,
                "stops": [
                    {
                        "area_id": item["area_id"],
                        "area_name": item["area_name"],
                        "sequence": 1,
                        "incoming_from_area_id": base_id,
                        "outgoing_to_area_id": base_id,
                        "service_start_time": item["service_start_time"],
                        "service_end_time": item["service_end_time"],
                        "travel_before_s": route["outbound_s"],
                        "travel_after_s": route["inbound_s"],
                        "travel_before_distance_m": route["outbound_distance_m"],
                        "travel_after_distance_m": route["inbound_distance_m"],
                    }
                ],
                "provenance": "KAKAO ROAD CACHE; SIMULATED PROVIDER",
            }
        )
    return standalone_routes


def _add_provider_window_route_model(
    model: cp_model.CpModel,
    candidates: list[dict[str, Any]],
    indexes: list[int],
    visit_vars: list[cp_model.IntVar],
    routes: dict[tuple[str, str], tuple[int, int]],
    window_active: cp_model.IntVar,
    group_number: int,
) -> tuple[Any, Any, dict[str, Any]]:
    """Jointly choose visits and a feasible Kakao-road order for one provider window."""
    window_start = _minute(candidates[indexes[0]]["availability_start"])
    window_end = _minute(candidates[indexes[0]]["availability_end"])
    provider = candidates[indexes[0]]
    base_id = str(provider["base_area_id"])
    area_ids = {str(candidates[index]["area_id"]) for index in indexes}
    locations = area_ids | {base_id}
    matrix_complete = all(
        (origin, destination) in routes
        for origin in locations
        for destination in locations
        if origin != destination
    )
    daily_minutes = min(
        window_end - window_start,
        int(float(provider["max_daily_hours"]) * 60),
    )

    service_starts: dict[int, cp_model.IntVar] = {}
    fallback_visits: dict[int, cp_model.IntVar] = {}
    intervals = []
    fallback_work_terms = []
    for index in indexes:
        candidate = candidates[index]
        latest_start = window_end - int(candidate["duration_minutes"])
        service_start = model.new_int_var(
            window_start, latest_start, f"route_service_start_{group_number}_{index}"
        )
        candidate["service_start_var"] = service_start
        service_starts[index] = service_start
        requested_start = candidate.get("requested_start_time")
        if requested_start:
            model.add(service_start == _minute(str(requested_start))).only_enforce_if(
                visit_vars[index]
            )

    use_multi_stop = None
    arc_vars: dict[tuple[int, int], cp_model.IntVar] = {}
    route_node_vars: dict[int, cp_model.IntVar] = {}
    if matrix_complete and len(indexes) > 1:
        use_multi_stop = model.new_bool_var(f"route_multi_stop_{group_number}")
        model.add(use_multi_stop <= window_active)
        model.add(sum(visit_vars[index] for index in indexes) >= 2 * use_multi_stop)
        route_start = model.new_int_var(
            window_start, window_end, f"multi_stop_start_{group_number}"
        )
        route_end = model.new_int_var(
            window_start, window_end, f"multi_stop_end_{group_number}"
        )
        route_size = model.new_int_var(
            0, window_end - window_start, f"multi_stop_size_{group_number}"
        )
        model.add(route_size == route_end - route_start).only_enforce_if(use_multi_stop)
        intervals.append(
            model.new_optional_interval_var(
                route_start,
                route_size,
                route_end,
                use_multi_stop,
                f"multi_stop_interval_{group_number}",
            )
        )
        circuit_arcs: list[tuple[int, int, cp_model.IntVar]] = []
        depot_skip = model.new_bool_var(f"route_depot_skip_{group_number}")
        model.add(depot_skip + use_multi_stop == 1)
        circuit_arcs.append((0, 0, depot_skip))

        for node, index in enumerate(indexes, start=1):
            included = model.new_bool_var(f"route_node_{group_number}_{node}")
            model.add(included <= visit_vars[index])
            model.add(included <= use_multi_stop)
            model.add(included >= visit_vars[index] + use_multi_stop - 1)
            route_node_vars[node] = included
            skipped = model.new_bool_var(f"route_node_skip_{group_number}_{node}")
            model.add(skipped + included == 1)
            circuit_arcs.append((node, node, skipped))

        route_cost_terms = []
        route_time_terms = []
        route_distance_terms = []
        route_work_terms = []
        for node, index in enumerate(indexes, start=1):
            candidate = candidates[index]
            outbound = routes[(base_id, str(candidate["area_id"]))]
            outbound_minutes = math.ceil(outbound[1] / 60)
            first_arc = model.new_bool_var(f"route_arc_{group_number}_0_{node}")
            arc_vars[(0, node)] = first_arc
            circuit_arcs.append((0, node, first_arc))
            model.add(
                service_starts[index] >= window_start + outbound_minutes
            ).only_enforce_if(first_arc)
            model.add(route_start == service_starts[index] - outbound_minutes).only_enforce_if(
                first_arc
            )
            route_cost_terms.append(
                math.ceil(outbound[0] / 1000 * TRAVEL_RATE_WON_PER_KM)
                + math.ceil(outbound[1] / 3600 * TRAVEL_LABOR_WON_PER_HOUR)
            )
            route_cost_terms[-1] *= first_arc
            route_time_terms.append(outbound[1] * first_arc)
            route_distance_terms.append(outbound[0] * first_arc)
            route_work_terms.append(outbound_minutes * first_arc)

            return_leg = routes[(str(candidate["area_id"]), base_id)]
            return_minutes = math.ceil(return_leg[1] / 60)
            last_arc = model.new_bool_var(f"route_arc_{group_number}_{node}_0")
            arc_vars[(node, 0)] = last_arc
            circuit_arcs.append((node, 0, last_arc))
            model.add(
                service_starts[index]
                + int(candidate["duration_minutes"])
                + return_minutes
                <= window_end
            ).only_enforce_if(last_arc)
            model.add(
                route_end
                == service_starts[index]
                + int(candidate["duration_minutes"])
                + return_minutes
            ).only_enforce_if(last_arc)
            route_cost_terms.append(
                (
                    math.ceil(return_leg[0] / 1000 * TRAVEL_RATE_WON_PER_KM)
                    + math.ceil(return_leg[1] / 3600 * TRAVEL_LABOR_WON_PER_HOUR)
                )
                * last_arc
            )
            route_time_terms.append(return_leg[1] * last_arc)
            route_distance_terms.append(return_leg[0] * last_arc)
            route_work_terms.append(return_minutes * last_arc)

            for next_node, next_index in enumerate(indexes, start=1):
                if node == next_node:
                    continue
                from_area = str(candidate["area_id"])
                to_area = str(candidates[next_index]["area_id"])
                leg = routes.get((from_area, to_area), (0, 0))
                travel_minutes = math.ceil(leg[1] / 60)
                arc = model.new_bool_var(
                    f"route_arc_{group_number}_{node}_{next_node}"
                )
                arc_vars[(node, next_node)] = arc
                circuit_arcs.append((node, next_node, arc))
                model.add(
                    service_starts[next_index]
                    >= service_starts[index]
                    + int(candidate["duration_minutes"])
                    + travel_minutes
                ).only_enforce_if(arc)
                route_cost_terms.append(
                    (
                        math.ceil(leg[0] / 1000 * TRAVEL_RATE_WON_PER_KM)
                        + math.ceil(leg[1] / 3600 * TRAVEL_LABOR_WON_PER_HOUR)
                    )
                    * arc
                )
                route_time_terms.append(leg[1] * arc)
                route_distance_terms.append(leg[0] * arc)
                route_work_terms.append(travel_minutes * arc)
            route_work_terms.append(int(candidate["duration_minutes"]) * route_node_vars[node])

        model.add_circuit(circuit_arcs)
        route_cost_expression = sum(route_cost_terms)
        route_time_expression = sum(route_time_terms)
        route_distance_expression = sum(route_distance_terms)
        route_work_expression = sum(route_work_terms)
        hub_cost_expression = sum(
            int(candidates[index]["route"]["cost_won"]) * visit_vars[index]
            for index in indexes
        )
        hub_time_expression = sum(
            int(candidates[index]["route"]["duration_s"]) * visit_vars[index]
            for index in indexes
        )
        hub_distance_expression = sum(
            int(candidates[index]["route"]["distance_m"]) * visit_vars[index]
            for index in indexes
        )
        model.add(route_cost_expression <= hub_cost_expression).only_enforce_if(
            use_multi_stop
        )
        model.add(route_time_expression <= hub_time_expression).only_enforce_if(
            use_multi_stop
        )
        model.add(route_distance_expression <= hub_distance_expression).only_enforce_if(
            use_multi_stop
        )
        model.add(route_work_expression <= daily_minutes).only_enforce_if(use_multi_stop)
    else:
        route_cost_expression = 0
        route_time_expression = 0
        route_distance_expression = 0
        route_work_expression = 0

    for index in indexes:
        if use_multi_stop is None:
            fallback = visit_vars[index]
        else:
            fallback = model.new_bool_var(f"hub_fallback_visit_{group_number}_{index}")
            model.add(fallback <= visit_vars[index])
            model.add(fallback + use_multi_stop <= 1)
            model.add(fallback >= visit_vars[index] - use_multi_stop)
        fallback_visits[index] = fallback
        candidate = candidates[index]
        departure = model.new_int_var(
            window_start,
            window_end,
            f"hub_fallback_departure_{group_number}_{index}",
        )
        end = model.new_int_var(
            window_start, window_end, f"hub_fallback_end_{group_number}_{index}"
        )
        outbound_minutes = math.ceil(int(candidate["route"]["outbound_s"]) / 60)
        model.add(
            departure == service_starts[index] - outbound_minutes
        ).only_enforce_if(fallback)
        intervals.append(
            model.new_optional_interval_var(
                departure,
                int(candidate["estimated_work_minutes"]),
                end,
                fallback,
                f"hub_fallback_interval_{group_number}_{index}",
            )
        )
        fallback_work_terms.append(
            int(candidate["estimated_work_minutes"]) * fallback
        )

    model.add(sum(fallback_work_terms) <= daily_minutes * window_active)
    fallback_cost_expression = sum(
        int(candidates[index]["route"]["cost_won"]) * fallback_visits[index]
        for index in indexes
    )
    fallback_time_expression = sum(
        int(candidates[index]["route"]["duration_s"]) * fallback_visits[index]
        for index in indexes
    )
    group_metadata = {
        "provider_id": str(provider["provider_id"]),
        "scheduled_date": str(provider["scheduled_date"]),
        "candidate_indexes": indexes,
        "node_candidate_indexes": {node: index for node, index in enumerate(indexes, start=1)},
        "arc_vars": arc_vars,
        "route_multi_stop_var": use_multi_stop,
        "matrix_complete": matrix_complete,
        "availability_start": str(provider["availability_start"]),
        "availability_end": str(provider["availability_end"]),
        "intervals": intervals,
        "work_expression": route_work_expression + sum(fallback_work_terms),
    }
    return (
        route_cost_expression + fallback_cost_expression,
        route_time_expression + fallback_time_expression,
        group_metadata,
    )


def _add_greedy_schedule_hint(
    model: cp_model.CpModel,
    areas: list[dict[str, Any]],
    providers: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    visit_vars: list[cp_model.IntVar],
    unit_vars: list[cp_model.IntVar],
    budget_won: int,
    scenario: Scenario,
    policy: PlanningPolicy,
) -> None:
    """Seed CP-SAT with a feasible single-visit-per-area plan when one fits."""
    providers_by_id = {str(item["provider_id"]): item for item in providers}
    candidates_by_area: dict[str, list[int]] = defaultdict(list)
    for index, candidate in enumerate(candidates):
        candidates_by_area[str(candidate["area_id"])].append(index)

    def area_priority(area: dict[str, Any]) -> tuple[int, int, int]:
        area_id = str(area["id"])
        choices = candidates_by_area.get(area_id, [])
        cheapest = min(
            (
                int(candidates[index]["route"]["cost_won"])
                + SERVICE_COST_WON[candidates[index]["service_type"]]
                for index in choices
            ),
            default=budget_won + 1,
        )
        vulnerability = _vulnerability_points(
            area,
            policy.elderly_priority_weight,
            policy.single_elderly_household_priority_weight,
        )
        if scenario == "efficiency":
            return (0, -int(area.get("simulated_monthly_demand", 0)), cheapest)
        if scenario == "balanced":
            protection = vulnerability + (
                policy.survey_required_protection_weight
                if area.get("needs_survey")
                else 0
            )
            return (0, -protection, cheapest)
        return (0, cheapest, -vulnerability)

    selected_indexes: set[int] = set()
    selected_provider_dates: set[tuple[str, str]] = set()
    provider_month_rounds: dict[tuple[str, str], int] = defaultdict(int)
    provider_month_service_cost: dict[tuple[str, str], int] = defaultdict(int)
    provider_month_pay: dict[tuple[str, str], int] = defaultdict(int)
    used_cost = 0
    for area in sorted(areas, key=area_priority):
        area_id = str(area["id"])
        if int(area.get("simulated_monthly_demand", 0)) <= 0:
            continue
        choices = candidates_by_area.get(area_id, [])
        choices.sort(
            key=lambda index: (
                candidates[index]["participation_status"] != "OPTED_IN",
                int(candidates[index]["route"]["cost_won"]),
                candidates[index]["scheduled_date"],
                candidates[index]["provider_id"],
            )
        )
        for index in choices:
            candidate = candidates[index]
            provider_id = str(candidate["provider_id"])
            provider_date = (provider_id, str(candidate["scheduled_date"]))
            provider_month = (provider_id, str(candidate["month"]))
            provider = providers_by_id[provider_id]
            if provider_date in selected_provider_dates:
                continue
            if provider_month_rounds[provider_month] >= int(provider["max_monthly_rounds"]):
                continue
            service_cost = SERVICE_COST_WON[candidate["service_type"]]
            new_service_cost = provider_month_service_cost[provider_month] + service_cost
            minimum_compensation = max(
                int(provider["minimum_compensation_won"]),
                policy.minimum_provider_compensation_won,
            )
            new_pay = max(new_service_cost, minimum_compensation)
            incremental_pay = new_pay - provider_month_pay[provider_month]
            incremental_cost = incremental_pay + int(candidate["route"]["cost_won"])
            if used_cost + incremental_cost > budget_won:
                continue
            selected_indexes.add(index)
            selected_provider_dates.add(provider_date)
            provider_month_rounds[provider_month] += 1
            provider_month_service_cost[provider_month] = new_service_cost
            provider_month_pay[provider_month] = new_pay
            used_cost += incremental_cost
            break

    for index, visit in enumerate(visit_vars):
        selected = int(index in selected_indexes)
        model.add_hint(visit, selected)
        model.add_hint(unit_vars[index], selected)


def generate_provider_schedule(
    areas: list[dict[str, Any]],
    providers: list[dict[str, Any]],
    connection: sqlite3.Connection,
    budget_won: int,
    scenario: Scenario,
    policy: PlanningPolicy | None = None,
    *,
    _required_budget_only: bool = False,
) -> dict[str, Any]:
    """Schedule up to 28 days of provider-specific rounds; roads are exact cached Kakao legs."""
    if budget_won < 0:
        raise ValueError("budget must be nonnegative")
    if scenario not in {"efficiency", "balanced", "minimum_coverage"}:
        raise ValueError("unsupported planning scenario")
    if not areas or not providers:
        raise ValueError("areas and providers are required")
    policy = policy or PlanningPolicy()
    _validate_policy(policy)
    for area in areas:
        if area.get("service_type") not in SERVICE_COST_WON:
            raise ValueError("unsupported or missing service type")
    routes = _route_rows(connection)
    candidates, blocked = _make_candidates(areas, providers, routes, policy)
    model = cp_model.CpModel()
    visit_vars: list[cp_model.IntVar] = []
    unit_vars: list[cp_model.IntVar] = []
    rows_by_area: dict[str, list[int]] = {str(area["id"]): [] for area in areas}
    rows_by_provider_month: dict[tuple[str, str], list[int]] = {}
    rows_by_provider_date: dict[tuple[str, str], list[int]] = {}
    rows_by_provider_area_date: dict[tuple[str, str, str], list[int]] = {}
    for index, candidate in enumerate(candidates):
        visit = model.new_bool_var(f"visit_{index}")
        units = model.new_int_var(0, candidate["service_capacity"], f"units_{index}")
        model.add(units >= visit)
        model.add(units <= candidate["service_capacity"] * visit)
        candidate["visit_var"] = visit
        candidate["units_var"] = units
        visit_vars.append(visit)
        unit_vars.append(units)
        rows_by_area[candidate["area_id"]].append(index)
        rows_by_provider_month.setdefault(
            (candidate["provider_id"], candidate["month"]), []
        ).append(index)
        rows_by_provider_date.setdefault(
            (candidate["provider_id"], candidate["scheduled_date"]), []
        ).append(index)
        rows_by_provider_area_date.setdefault(
            (candidate["provider_id"], candidate["area_id"], candidate["scheduled_date"]), []
        ).append(index)
    for indexes in rows_by_provider_area_date.values():
        if len(indexes) > 1:
            model.add(sum(visit_vars[index] for index in indexes) <= 1)
    for area in areas:
        area_id = str(area["id"])
        indexes = rows_by_area[area_id]
        model.add(
            sum(unit_vars[index] for index in indexes)
            <= max(0, int(area.get("simulated_monthly_demand", 0)))
        )

    provider_lookup = {str(provider["provider_id"]): provider for provider in providers}
    provider_pay_vars: list[cp_model.IntVar] = []
    for (provider_id, month), indexes in rows_by_provider_month.items():
        provider = provider_lookup[provider_id]
        model.add(
            sum(visit_vars[index] for index in indexes) <= int(provider["max_monthly_rounds"])
        )
        active = model.new_bool_var(f"active_{provider_id}_{month}")
        for index in indexes:
            model.add(active >= visit_vars[index])
        model.add(active <= sum(visit_vars[index] for index in indexes))
        service_cost = sum(
            unit_vars[index] * SERVICE_COST_WON[candidates[index]["service_type"]]
            for index in indexes
        )
        maximum_service_cost = sum(
            candidates[index]["service_capacity"]
            * SERVICE_COST_WON[candidates[index]["service_type"]]
            for index in indexes
        )
        compensation_floor = max(
            int(provider["minimum_compensation_won"]),
            policy.minimum_provider_compensation_won,
        )
        pay = model.new_int_var(
            0,
            max(maximum_service_cost, compensation_floor),
            f"provider_pay_{provider_id}_{month}",
        )
        model.add(pay >= service_cost)
        model.add(pay >= compensation_floor * active)
        provider_pay_vars.append(pay)
    active_provider_days: list[cp_model.IntVar] = []
    route_model_groups: list[dict[str, Any]] = []
    route_cost_expressions = []
    route_time_expressions = []
    route_matrix_complete = True
    exact_route_group_count = 0
    for (provider_id, scheduled_date), indexes in rows_by_provider_date.items():
        day_active = model.new_bool_var(f"provider_day_{provider_id}_{scheduled_date}")
        active_provider_days.append(day_active)
        for index in indexes:
            model.add(day_active >= visit_vars[index])
        model.add(day_active <= sum(visit_vars[index] for index in indexes))

        indexes_by_window: dict[tuple[str, str], list[int]] = {}
        for index in indexes:
            candidate = candidates[index]
            window = (candidate["availability_start"], candidate["availability_end"])
            indexes_by_window.setdefault(window, []).append(index)
        day_work_expressions = []
        day_intervals = []
        for window_index, (_window, window_indexes) in enumerate(indexes_by_window.items()):
            window_active = model.new_bool_var(
                f"window_{provider_id}_{scheduled_date}_{window_index}"
            )
            for index in window_indexes:
                model.add(visit_vars[index] <= window_active)
            model.add(window_active <= sum(visit_vars[index] for index in window_indexes))
            route_cost_expression, route_time_expression, group_metadata = (
                _add_provider_window_route_model(
                    model,
                    candidates,
                    window_indexes,
                    visit_vars,
                    routes,
                    window_active,
                    len(route_model_groups),
                )
            )
            group_metadata["window_active_var"] = window_active
            route_model_groups.append(group_metadata)
            day_work_expressions.append(group_metadata["work_expression"])
            day_intervals.extend(group_metadata["intervals"])
            route_cost_expressions.append(route_cost_expression)
            route_time_expressions.append(route_time_expression)
            route_matrix_complete = route_matrix_complete and bool(
                group_metadata["matrix_complete"]
            )
            exact_route_group_count += int(
                group_metadata["matrix_complete"]
                and len(window_indexes) > 1
            )
        max_daily_work_minutes = int(
            float(candidates[indexes[0]]["max_daily_hours"]) * 60
        )
        model.add(sum(day_work_expressions) <= max_daily_work_minutes * day_active)
        if day_intervals:
            model.add_no_overlap(day_intervals)

    max_units = sum(max(0, int(area.get("simulated_monthly_demand", 0))) for area in areas)
    total_units_expression = sum(unit_vars)
    total_units = model.new_int_var(0, max_units, "objective_total_units")
    model.add(total_units == total_units_expression)

    max_travel_cost = sum(candidate["route"]["cost_won"] for candidate in candidates)
    max_travel_time = sum(candidate["route"]["duration_s"] for candidate in candidates)
    travel_cost_expression = sum(route_cost_expressions)
    travel_cost = model.new_int_var(0, max_travel_cost, "objective_travel_cost")
    model.add(travel_cost == travel_cost_expression)
    travel_time_expression = sum(route_time_expressions)
    travel_time = model.new_int_var(0, max_travel_time, "objective_travel_time")
    model.add(travel_time == travel_time_expression)
    total_cost = model.new_int_var(0, budget_won, "objective_total_cost")
    model.add(total_cost == sum(provider_pay_vars) + travel_cost)
    model.add(total_cost <= budget_won)

    route_aware_travel_cost = travel_cost
    route_aware_travel_time = travel_time
    route_aware_total_cost = total_cost
    area_covered_vars: dict[str, cp_model.IntVar] = {}
    for area in areas:
        area_id = str(area["id"])
        indexes = rows_by_area[area_id]
        covered = model.new_bool_var(f"covered_{area_id}")
        area_covered_vars[area_id] = covered
        if indexes:
            model.add(sum(visit_vars[index] for index in indexes) >= covered)
            model.add(sum(visit_vars[index] for index in indexes) <= len(indexes) * covered)
        else:
            model.add(covered == 0)
    covered_count_expression = sum(area_covered_vars.values())
    covered_count = model.new_int_var(0, len(areas), "objective_covered_areas")
    model.add(covered_count == covered_count_expression)
    max_survey_areas = policy.survey_required_protection_weight * sum(
        bool(area.get("needs_survey")) for area in areas
    )
    survey_count_expression = sum(
        policy.survey_required_protection_weight * area_covered_vars[str(area["id"])]
        for area in areas
        if area.get("needs_survey")
    )
    survey_count = model.new_int_var(0, max_survey_areas, "objective_survey_areas")
    model.add(survey_count == survey_count_expression)
    max_vulnerability = sum(
        _vulnerability_points(
            area,
            policy.elderly_priority_weight,
            policy.single_elderly_household_priority_weight,
        )
        for area in areas
    )
    vulnerability_expression = sum(
        _vulnerability_points(
            area,
            policy.elderly_priority_weight,
            policy.single_elderly_household_priority_weight,
        )
        * area_covered_vars[str(area["id"])]
        for area in areas
    )
    vulnerability = model.new_int_var(0, max_vulnerability, "objective_vulnerability")
    model.add(vulnerability == vulnerability_expression)
    max_provider_days = len(rows_by_provider_date)
    provider_days_expression = sum(active_provider_days)
    provider_days = model.new_int_var(0, max_provider_days, "objective_provider_days")
    model.add(provider_days == provider_days_expression)
    minimum_frequency_vars: dict[str, cp_model.IntVar] = {}
    for area in areas:
        area_id = str(area["id"])
        indexes = rows_by_area[area_id]
        met = model.new_bool_var(f"minimum_frequency_met_{area_id}")
        minimum_frequency_vars[area_id] = met
        demand_meets_minimum = (
            int(area.get("simulated_monthly_demand", 0)) >= policy.minimum_services_per_area
        )
        if indexes and demand_meets_minimum:
            model.add(
                sum(visit_vars[index] for index in indexes)
                >= policy.minimum_services_per_area * met
            )
            model.add(met <= area_covered_vars[area_id])
        else:
            model.add(met == 0)
    minimum_frequency_count = sum(minimum_frequency_vars.values())

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = MAX_SOLVER_SECONDS
    solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = 2026
    objective_components: list[tuple[Any, int, bool]]
    if _required_budget_only:
        for _area_id, met in minimum_frequency_vars.items():
            model.add(met == 1)
        objective_components = [(total_cost, budget_won, False)]
    elif scenario == "efficiency":
        objective_components = [
            (total_units, max_units, True),
            (provider_days, max_provider_days, False),
            (route_aware_travel_cost, max_travel_cost, False),
            (route_aware_travel_time, max_travel_time, False),
        ]
    elif scenario == "minimum_coverage":
        objective_components = [
            (minimum_frequency_count, len(areas), True),
            (covered_count, len(areas), True),
            (total_units, max_units, True),
            (provider_days, max_provider_days, False),
            (route_aware_total_cost, budget_won, False),
        ]
    else:
        concentration = model.new_int_var(0, 10_000, "max_area_saturation_basis_points")
        for area in areas:
            area_id = str(area["id"])
            demand = max(0, int(area.get("simulated_monthly_demand", 0)))
            if demand:
                area_saturation = model.new_int_var(0, 10_000, f"saturation_{area_id}")
                area_units = sum(unit_vars[index] for index in rows_by_area[area_id])
                model.add(area_saturation * demand >= area_units * 10_000)
                model.add(concentration >= area_saturation)
        scaled_total_cost = model.new_int_var(0, budget_won // 100, "cost_hundreds_won")
        model.add(scaled_total_cost * 100 <= route_aware_total_cost)
        model.add(route_aware_total_cost <= scaled_total_cost * 100 + 99)
        objective_components = [
            (total_units, max_units, True),
            (covered_count, len(areas), True),
            (survey_count, max_survey_areas, True),
            (vulnerability, max_vulnerability, True),
            (concentration, 10_000, False),
            (provider_days, max_provider_days, False),
            (scaled_total_cost, budget_won // 100, False),
        ]

    opted_in_visits = [
        visit_vars[index]
        for index, candidate in enumerate(candidates)
        if candidate["participation_status"] == "OPTED_IN"
    ]
    if opted_in_visits and not _required_budget_only:
        preferred_visit_count = model.new_int_var(
            0, len(opted_in_visits), "objective_opted_in_provider_visits"
        )
        model.add(preferred_visit_count == sum(opted_in_visits))
        objective_components.append((preferred_visit_count, len(opted_in_visits), True))

    _add_greedy_schedule_hint(
        model,
        areas,
        providers,
        candidates,
        visit_vars,
        unit_vars,
        budget_won,
        scenario,
        policy,
    )
    optimality_proven = False
    try:
        score = _lexicographic_score(objective_components)
    except ValueError as exc:
        if "safe CP-SAT integer range" not in str(exc):
            raise
        solver, status, optimality_proven = _solve_lexicographic_components(
            model,
            [(expression, maximize) for expression, _maximum, maximize in objective_components],
        )
    else:
        model.maximize(score)
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = MAX_SOLVER_SECONDS
        solver.parameters.num_search_workers = 1
        solver.parameters.random_seed = 2026
        status = solver.solve(model)
        optimality_proven = status == cp_model.OPTIMAL
    if status not in {cp_model.OPTIMAL, cp_model.FEASIBLE}:
        raise RuntimeError(
            f"provider scheduling found no feasible plan ({solver.status_name(status)})"
        )

    route_orders: dict[tuple[str, str, str, str], list[str]] = {}
    for group in route_model_groups:
        route_choice = group["route_multi_stop_var"]
        if route_choice is None or not solver.value(route_choice):
            continue
        successors = {
            origin: destination
            for (origin, destination), arc in group["arc_vars"].items()
            if solver.value(arc)
        }
        ordered_area_ids: list[str] = []
        current_node = 0
        while (next_node := successors.get(current_node, 0)) != 0:
            candidate_index = group["node_candidate_indexes"][next_node]
            ordered_area_ids.append(str(candidates[candidate_index]["area_id"]))
            current_node = next_node
        if len(ordered_area_ids) < 2:
            raise RuntimeError("integrated route solution omitted a selected provider stop")
        route_orders[
            (
                group["provider_id"],
                group["scheduled_date"],
                group["availability_start"],
                group["availability_end"],
            )
        ] = ordered_area_ids

    service_cost_by_provider_month: dict[tuple[str, str], int] = {}
    scheduled_rounds_by_provider_month: dict[tuple[str, str], int] = {}
    rounds: list[dict[str, Any]] = []
    selected_by_provider_date: dict[
        tuple[str, str], list[tuple[dict[str, Any], dict[str, Any]]]
    ] = {}
    selected_by_provider_window: dict[
        tuple[str, str, str, str], list[tuple[dict[str, Any], dict[str, Any]]]
    ] = {}
    service_cost_total = 0
    served_by_area = {str(area["id"]): 0 for area in areas}
    scheduled_rounds_by_area = {str(area["id"]): 0 for area in areas}
    for candidate in candidates:
        count = solver.value(candidate["units_var"])
        if count <= 0:
            continue
        service_cost_won = count * SERVICE_COST_WON[candidate["service_type"]]
        route = candidate["route"]
        service_start_minute = int(solver.value(candidate["service_start_var"]))
        candidate["solved_service_start_time"] = _time(service_start_minute)
        round_item = {
            "provider_id": candidate["provider_id"],
            "provider_name": candidate["provider_name"],
            "area_id": candidate["area_id"],
            "area_name": candidate["area_name"],
            "service_type": candidate["service_type"],
            "scheduled_date": candidate["scheduled_date"],
            "departure_time": candidate["departure_time"],
            "service_start_time": candidate["solved_service_start_time"],
            "service_end_time": _time(
                service_start_minute + int(candidate["duration_minutes"])
            ),
            "duration_minutes": candidate["duration_minutes"],
            "service_units": count,
            "travel_before_s": route["outbound_s"],
            "travel_after_s": route["inbound_s"],
            "travel_distance_m": route["distance_m"],
            "travel_time_s": route["duration_s"],
            "travel_before_distance_m": route["outbound_distance_m"],
            "travel_after_distance_m": route["inbound_distance_m"],
            "service_cost_won": service_cost_won,
            "travel_cost_won": route["cost_won"],
            "minimum_compensation_topup_won": 0,
            "total_cost_won": service_cost_won + route["cost_won"],
            "participation_status": candidate["participation_status"],
            "participation_source": candidate["participation_source"],
            "provenance": "OPTIMIZATION RESULT; KAKAO ROAD CACHE; SIMULATED PROVIDER",
            "route_group_key": f"{candidate['provider_id']}::{candidate['scheduled_date']}",
            "route_sequence": 1,
            "route_type": "HUB_ROUND_TRIP",
            "route_from_area_id": candidate["base_area_id"],
            "route_to_area_id": candidate["base_area_id"],
        }
        if candidate.get("time_window_source"):
            round_item["time_window_source"] = candidate["time_window_source"]
            round_item["provenance"] += "; SURVEY INPUT; HUMAN REVIEW"
        rounds.append(round_item)
        selected_by_provider_date.setdefault(
            (candidate["provider_id"], candidate["scheduled_date"]), []
        ).append((candidate, round_item))
        selected_by_provider_window.setdefault(
            (
                candidate["provider_id"],
                candidate["scheduled_date"],
                candidate["availability_start"],
                candidate["availability_end"],
            ),
            [],
        ).append((candidate, round_item))
        key = (candidate["provider_id"], candidate["month"])
        selected_visits = solver.value(candidate["visit_var"])
        scheduled_rounds_by_area[candidate["area_id"]] += selected_visits
        scheduled_rounds_by_provider_month[key] = (
            scheduled_rounds_by_provider_month.get(key, 0) + selected_visits
        )
        service_cost_by_provider_month[key] = (
            service_cost_by_provider_month.get(key, 0) + service_cost_won
        )
        served_by_area[candidate["area_id"]] += count
        service_cost_total += service_cost_won

    minimum_topup_total = 0
    selected_provider_month: dict[tuple[str, str], int] = {}
    for key, service_cost_won in service_cost_by_provider_month.items():
        provider_id, _month = key
        minimum_compensation = max(
            int(provider_lookup[provider_id]["minimum_compensation_won"]),
            policy.minimum_provider_compensation_won,
        )
        topup = max(0, minimum_compensation - service_cost_won)
        minimum_topup_total += topup
        selected_provider_month[key] = service_cost_won
        if topup:
            first_round = next(
                round_item
                for round_item in rounds
                if round_item["provider_id"] == provider_id
                and round_item["scheduled_date"].startswith(key[1])
            )
            first_round["minimum_compensation_topup_won"] = topup
    route_records: list[dict[str, Any]] = []
    selected_windows_by_provider_date: dict[tuple[str, str], set[tuple[str, str]]] = {}
    for provider_id, scheduled_date, window_start, window_end in selected_by_provider_window:
        selected_windows_by_provider_date.setdefault(
            (provider_id, scheduled_date), set()
        ).add((window_start, window_end))
    for provider_window in sorted(selected_by_provider_window):
        provider_id, scheduled_date, window_start, window_end = provider_window
        date_key = (provider_id, scheduled_date)
        route_group_key = f"{provider_id}::{scheduled_date}"
        if len(selected_windows_by_provider_date[date_key]) > 1:
            route_group_key += f"::{window_start}-{window_end}"
        route_records.extend(
            _route_selected_stops(
                selected_by_provider_window[provider_window],
                provider_lookup[provider_id],
                routes,
                route_orders.get(provider_window),
                route_group_key,
            )
        )
    travel_cost_total = sum(int(route["cost_won"]) for route in route_records)
    distance_total = sum(int(route["distance_m"]) for route in route_records)
    duration_total = sum(int(route["duration_s"]) for route in route_records)
    actual_total_cost_won = service_cost_total + travel_cost_total + minimum_topup_total
    if actual_total_cost_won > budget_won:
        raise RuntimeError("serialized route costs exceed the optimized budget constraint")
    baseline_budget_spent_won = int(solver.value(total_cost))
    for round_item in rounds:
        round_item["total_cost_won"] = (
            int(round_item["service_cost_won"])
            + int(round_item["travel_cost_won"])
            + int(round_item["minimum_compensation_topup_won"])
        )
    for area in areas:
        area_id = str(area["id"])
        remaining = max(0, int(area.get("simulated_monthly_demand", 0)) - served_by_area[area_id])
        if not remaining:
            continue
        diagnostic_reasons: list[str] = []
        area_blockers = blocked[area_id]
        if "SERVICE_NOT_ALLOWED" in area_blockers:
            reason = "SERVICE_NOT_ALLOWED"
        elif "NO_SUPPORTED_PROVIDER" in area_blockers:
            reason = "NO_SUPPORTED_PROVIDER"
        elif "MAX_TRAVEL_TIME" in area_blockers and not any(
            candidate["area_id"] == area_id for candidate in candidates
        ):
            reason = "MAX_TRAVEL_TIME"
        elif "MAX_DAILY_HOURS" in area_blockers and not any(
            candidate["area_id"] == area_id for candidate in candidates
        ):
            reason = "MAX_DAILY_HOURS"
        elif "TIME_WINDOW" in area_blockers and not any(
            candidate["area_id"] == area_id for candidate in candidates
        ):
            reason = "TIME_WINDOW"
        elif not any(candidate["area_id"] == area_id for candidate in candidates):
            reason = next(
                (
                    blocker
                    for blocker in (
                        "REQUESTED_TIME_WINDOW",
                        "EXCLUDED_DAY_CONFLICT",
                        "REQUESTED_DATE_WINDOW",
                        "PREFERRED_DAY_CONFLICT",
                        "PROVIDER_DECLINED",
                    )
                    if blocker in area_blockers
                ),
                "PROVIDER_UNAVAILABLE",
            )
        else:
            area_candidates = [
                candidate for candidate in candidates if candidate["area_id"] == area_id
            ]
            slot_capacity_by_month: dict[tuple[str, str], dict[str, int]] = {}
            for candidate in area_candidates:
                key = (candidate["provider_id"], candidate["month"])
                date_slots = slot_capacity_by_month.setdefault(key, {})
                scheduled_date = str(candidate["scheduled_date"])
                date_slots[scheduled_date] = max(
                    date_slots.get(scheduled_date, 0),
                    int(candidate["service_capacity"]),
                )
            available_capacity = 0
            remaining_month_capacity = 0
            relevant_monthly_capacity_used = False
            for key, date_slots in slot_capacity_by_month.items():
                provider_id, _month = key
                provider = provider_lookup[provider_id]
                slot_capacity = sum(date_slots.values())
                monthly_round_limit = max(0, int(provider["max_monthly_rounds"]))
                service_capacity = max(1, int(provider["service_capacity"]))
                scheduled_rounds = scheduled_rounds_by_provider_month.get(key, 0)
                available_capacity += min(slot_capacity, monthly_round_limit * service_capacity)
                remaining_month_capacity += min(
                    slot_capacity,
                    max(0, monthly_round_limit - scheduled_rounds) * service_capacity,
                )
                relevant_monthly_capacity_used = (
                    relevant_monthly_capacity_used or scheduled_rounds > 0
                )
            selected_area_rounds = [
                (candidate, round_item)
                for selected in selected_by_provider_date.values()
                for candidate, round_item in selected
                if candidate["area_id"] == area_id
            ]
            spare_units_in_existing_rounds = sum(
                max(
                    0,
                    int(candidate["service_capacity"])
                    - int(round_item["service_units"]),
                )
                for candidate, round_item in selected_area_rounds
            )
            remaining_capacity = remaining_month_capacity + spare_units_in_existing_rounds
            if available_capacity < int(area.get("simulated_monthly_demand", 0)):
                diagnostic_reasons.append("PROVIDER_CAPACITY")
            if (
                remaining_capacity < remaining
                and relevant_monthly_capacity_used
                and "PROVIDER_CAPACITY" not in diagnostic_reasons
            ):
                diagnostic_reasons.append("SHARED_PROVIDER_CAPACITY")

            marginal_costs = []
            for candidate in area_candidates:
                key = (candidate["provider_id"], candidate["month"])
                current_service_cost = service_cost_by_provider_month.get(key, 0)
                compensation_floor = int(candidate["minimum_compensation_won"])
                current_provider_pay = (
                    max(current_service_cost, compensation_floor)
                    if key in selected_provider_month
                    else 0
                )
                next_provider_pay = max(
                    current_service_cost + SERVICE_COST_WON[candidate["service_type"]],
                    compensation_floor,
                )
                provider_cost = next_provider_pay - current_provider_pay
                same_day_round = any(
                    selected_candidate["provider_id"] == candidate["provider_id"]
                    and selected_candidate["scheduled_date"] == candidate["scheduled_date"]
                    and int(round_item["service_units"])
                    < int(selected_candidate["service_capacity"])
                    for selected_candidate, round_item in selected_area_rounds
                )
                travel_cost = 0 if same_day_round else int(candidate["route"]["cost_won"])
                marginal_costs.append(provider_cost + travel_cost)
            minimum_marginal = min(marginal_costs, default=budget_won + 1)
            if budget_won - baseline_budget_spent_won < minimum_marginal:
                diagnostic_reasons.append("BUDGET")

            has_time_feasible_candidate = False
            for candidate in area_candidates:
                selected_day = selected_by_provider_date.get(
                    (candidate["provider_id"], candidate["scheduled_date"]), []
                )
                if any(
                    int(round_item["service_units"])
                    < int(selected_candidate["service_capacity"])
                    for selected_candidate, round_item in selected_day
                    if selected_candidate["area_id"] == area_id
                ):
                    has_time_feasible_candidate = True
                    break
                if not _fits_selected_provider_day(candidate, selected_day):
                    continue
                if all(
                    _pairwise_provider_day_compatible(candidate, selected_candidate, routes)
                    for selected_candidate, _round_item in selected_day
                    if selected_candidate["area_id"] != area_id
                ):
                    has_time_feasible_candidate = True
                    break
            if (
                not has_time_feasible_candidate
                and remaining_capacity > 0
                and "SHARED_PROVIDER_CAPACITY" not in diagnostic_reasons
            ):
                diagnostic_reasons.append("SHARED_PROVIDER_TIME")
            if not diagnostic_reasons:
                diagnostic_reasons.append(
                    "SCENARIO_PRIORITY" if optimality_proven else "SCHEDULER_OPTIMALITY_NOT_PROVEN"
                )
            reason = diagnostic_reasons[0]
        area["unserved_units"] = remaining
        area["constraint_reason"] = reason
        area["constraint_reasons"] = diagnostic_reasons or [reason]

    minimum_frequency_gaps = []
    for area in areas:
        area_id = str(area["id"])
        scheduled_count = scheduled_rounds_by_area[area_id]
        missing_rounds = max(0, policy.minimum_services_per_area - scheduled_count)
        if missing_rounds:
            if int(area.get("simulated_monthly_demand", 0)) < policy.minimum_services_per_area:
                reason = "DEMAND_BELOW_MINIMUM"
            else:
                reason = str(area.get("constraint_reason") or "MINIMUM_FREQUENCY")
            minimum_frequency_gaps.append(
                {
                    "area_id": area_id,
                    "area_name": str(area.get("name", area_id)),
                    "required_rounds": policy.minimum_services_per_area,
                    "scheduled_rounds": scheduled_count,
                    "missing_rounds": missing_rounds,
                    "reason": reason,
                    "reasons": area.get("constraint_reasons", [reason]),
                }
            )

    served_units = sum(served_by_area.values())
    covered_areas = sum(value > 0 for value in served_by_area.values())
    total_demand = sum(max(0, int(area.get("simulated_monthly_demand", 0))) for area in areas)
    planning_demand_inputs = [
        {
            "area_id": str(area["id"]),
            "area_name": str(area.get("name", area["id"])),
            "service_type": str(area["service_type"]),
            "source_baseline_units": max(
                0,
                int(
                    area.get(
                        "baseline_monthly_demand",
                        area.get("simulated_monthly_demand", 0),
                    )
                ),
            ),
            "survey_frequency_floor_monthly": area.get("survey_frequency_floor_monthly"),
            "survey_frequency_observation_count": int(
                area.get("survey_frequency_observation_count", 0)
            ),
            "gross_planning_demand_units": max(
                0,
                int(
                    area.get(
                        "gross_planning_monthly_demand",
                        area.get("simulated_monthly_demand", 0),
                    )
                ),
            ),
            "existing_service_rounds_deducted": int(
                area.get("existing_service_monthly_rounds") or 0
            ),
            "existing_service_status": str(area.get("existing_service_status", "UNKNOWN")),
            "planning_demand_units": max(
                0, int(area.get("simulated_monthly_demand", 0))
            ),
            "policy": str(
                area.get(
                    "planning_demand_policy",
                    "SIMULATED_BASELINE_ONLY; SURVEY_SAMPLE_NOT_EXTRAPOLATED",
                )
            ),
            "provenance": str(
                area.get("planning_demand_provenance", "SIMULATED BASELINE")
            ),
        }
        for area in areas
    ]
    required_capacity = policy.minimum_services_per_area * len(areas)
    eligible_provider_months = {
        (str(candidate["provider_id"]), str(candidate["month"])) for candidate in candidates
    }
    available_capacity = sum(
        max(0, int(provider_lookup[provider_id]["max_monthly_rounds"]))
        for provider_id, _month in eligible_provider_months
    )
    missing_capacity = max(0, required_capacity - available_capacity)
    total_cost_won = actual_total_cost_won
    if _required_budget_only:
        required_budget_won = int(solver.value(total_cost)) if optimality_proven else None
        required_budget_status = "CALCULATED" if optimality_proven else "NOT_PROVEN"
        required_budget_reason = None if optimality_proven else "OPTIMALITY_NOT_PROVEN"
    else:
        required_budget_won, required_budget_status, required_budget_reason = (
            _calculate_minimum_budget(
                areas, providers, connection, candidates, budget_won, policy
            )
        )
    budget_gap_won = (
        max(0, required_budget_won - budget_won)
        if required_budget_won is not None
        else None
    )
    old_distance_total = sum(int(route["old_hub_round_trip_distance_m"]) for route in route_records)
    old_duration_total = sum(int(route["old_hub_round_trip_duration_s"]) for route in route_records)
    old_cost_total = sum(int(route["old_hub_round_trip_cost_won"]) for route in route_records)
    rounds.sort(
        key=lambda item: (
            item["scheduled_date"],
            item["departure_time"],
            item["provider_id"],
            item["route_sequence"],
        )
    )
    return {
        "scenario": scenario,
        "budget_won": budget_won,
        "budget_spent_won": total_cost_won,
        "budget_remaining_won": max(0, budget_won - total_cost_won),
        "budget_gap_won": budget_gap_won,
        "required_budget_won": required_budget_won,
        "required_budget_status": required_budget_status,
        "required_budget_reason": required_budget_reason,
        "required_budget_model": (
            "PROVIDER_CP_SAT_INTEGRATED_KAKAO_VRPTW"
            if route_matrix_complete
            else "PROVIDER_CP_SAT_KAKAO_VRPTW_WITH_HUB_FALLBACK"
        ),
        "service_cost_won": service_cost_total,
        "travel_cost_won": travel_cost_total,
        "minimum_compensation_topup_won": minimum_topup_total,
        "total_cost_won": total_cost_won,
        "travel_distance_m": distance_total,
        "travel_time_s": duration_total,
        "routing_comparison": {
            "baseline_name": "OLD HUB ROUND-TRIP",
            "actual_name": "KAKAO MULTI-STOP ROUTE WHEN FEASIBLE",
            "old_distance_m": old_distance_total,
            "actual_distance_m": distance_total,
            "distance_savings_m": old_distance_total - distance_total,
            "old_duration_s": old_duration_total,
            "actual_duration_s": duration_total,
            "duration_savings_s": old_duration_total - duration_total,
            "old_cost_won": old_cost_total,
            "actual_cost_won": travel_cost_total,
            "cost_savings_won": old_cost_total - travel_cost_total,
            "multi_stop_route_count": sum(
                route["route_type"] == "MULTI_STOP" for route in route_records
            ),
        },
        "routes": route_records,
        "total_demand_units": total_demand,
        "planning_demand_inputs": planning_demand_inputs,
        "served_units": served_units,
        "covered_areas": covered_areas,
        "uncovered_areas": len(areas) - covered_areas,
        "minimum_services_per_area": policy.minimum_services_per_area,
        "minimum_coverage_met": not minimum_frequency_gaps,
        "minimum_frequency_met_areas": len(areas) - len(minimum_frequency_gaps),
        "unmet_minimum_frequency_areas": len(minimum_frequency_gaps),
        "minimum_frequency_gaps": minimum_frequency_gaps,
        "required_capacity": required_capacity,
        "available_capacity": available_capacity,
        "capacity_basis": "ELIGIBLE_PROVIDER_MONTH_LIMIT_UPPER_BOUND",
        "missing_capacity": missing_capacity,
        "unmet_criteria": [
            {
                "area_id": str(area["id"]),
                "area_name": area.get("name", str(area["id"])),
                "units": int(area.get("unserved_units", 0)),
                "reason": str(area.get("constraint_reason", "")),
                "reasons": list(area.get("constraint_reasons", [])),
            }
            for area in areas
            if int(area.get("unserved_units", 0)) > 0
        ],
        "rounds": sorted(rounds, key=lambda item: (item["scheduled_date"], item["departure_time"])),
        "travel_source": "Kakao Mobility directed road routes; provider multi-stop routing",
        "solver_objective_model": (
            "CP_SAT_INTEGRATED_PROVIDER_DAY_VRPTW"
            if route_matrix_complete
            else "CP_SAT_PROVIDER_DAY_VRPTW_WITH_HUB_FALLBACK"
        ),
        "route_assignment_model": (
            "INTEGRATED_KAKAO_VRPTW"
            if route_matrix_complete
            else "KAKAO_VRPTW_WITH_HUB_ROUND_TRIP_FALLBACK"
        ),
        "route_matrix_complete": route_matrix_complete,
        "exact_route_group_count": exact_route_group_count,
        "hub_fallback_group_count": sum(
            not group["matrix_complete"] for group in route_model_groups
        ),
        "route_savings_proxy_pair_count": 0,
        "route_savings_proxy": "NONE",
        "global_route_optimality_proven": bool(
            optimality_proven and route_matrix_complete
        ),
        "solver_status": "OPTIMAL" if optimality_proven else "FEASIBLE",
        "optimality_proven": optimality_proven,
    }
