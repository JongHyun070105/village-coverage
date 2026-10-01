"""Provider-specific monthly service schedules using CP-SAT and cached road routes."""

from __future__ import annotations

import math
import sqlite3
from datetime import date, datetime, timedelta
from typing import Any, Literal

from ortools.sat.python import cp_model

from backend.optimization import (
    MAX_SOLVER_SECONDS,
    SERVICE_COST_WON,
    TRAVEL_LABOR_WON_PER_HOUR,
    TRAVEL_RATE_WON_PER_KM,
    _lexicographic_score,
    _vulnerability_points,
)
from backend.routing import MissingRoadLegError, optimize_multi_stop_route

Scenario = Literal["efficiency", "balanced", "minimum_coverage"]


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


def _make_candidates(
    areas: list[dict[str, Any]],
    providers: list[dict[str, Any]],
    routes: dict[tuple[str, str], tuple[int, int]],
) -> tuple[list[dict[str, Any]], dict[str, set[str]]]:
    today = date.today()
    weekday_names = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
    candidates: list[dict[str, Any]] = []
    blocked: dict[str, set[str]] = {str(area["id"]): set() for area in areas}
    for area in areas:
        area_id = str(area["id"])
        preferred = {str(day).lower() for day in area.get("preferred_days", [])}
        demand = max(0, int(area.get("simulated_monthly_demand", 0)))
        if demand == 0:
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
            weekday_availability: dict[str, list[dict[str, str]]] = {}
            for item in provider["availability"]:
                weekday_availability.setdefault(item["weekday"], []).append(item)
            for offset in range(1, 29):
                round_date = today + timedelta(days=offset)
                weekday = weekday_names[round_date.weekday()]
                if preferred and weekday not in preferred:
                    blocked[area_id].add("PREFERRED_DAY_CONFLICT")
                    continue
                availabilities = weekday_availability.get(weekday, [])
                if not availabilities:
                    blocked[area_id].add("PROVIDER_UNAVAILABLE")
                    continue
                try:
                    trip = _round_trip(routes, str(provider["base_area_id"]), area_id)
                except ValueError:
                    raise
                max_travel = int(provider["max_travel_time_minutes"]) * 60
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
                    service_start = availability_start + outbound_minutes
                    service_end = service_start + duration_minutes
                    return_at = service_end + math.ceil(trip["inbound_s"] / 60)
                    if return_at > availability_end:
                        blocked[area_id].add("TIME_WINDOW")
                        continue
                    candidates.append(
                        {
                            "provider_id": provider_id,
                            "provider_name": provider["name"],
                            "area_id": area_id,
                            "area_name": str(area.get("name", area_id)),
                            "service_type": str(area["service_type"]),
                            "scheduled_date": round_date.isoformat(),
                            "weekday": weekday,
                            "departure_time": availability["start_time"],
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
                            "minimum_compensation_won": max(
                                0, int(provider["minimum_compensation_won"])
                            ),
                            "route": trip,
                            "month": round_date.strftime("%Y-%m"),
                        }
                    )
    return candidates, blocked


def _route_selected_stops(
    selected: list[tuple[dict[str, Any], dict[str, Any]]],
    provider: dict[str, Any],
    roads: dict[tuple[str, str], tuple[int, int]],
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
    route_key = f"{provider_id}::{route_date}"
    route_result = None
    if len(selected) > 1:
        try:
            route_result = optimize_multi_stop_route(
                base_id,
                [
                    {
                        "area_id": candidate["area_id"],
                        "name": item["area_name"],
                        "duration_minutes": candidate["duration_minutes"],
                    }
                    for candidate, item in selected
                ],
                roads,
                available_from=first_candidate["availability_start"],
                available_until=first_candidate["availability_end"],
                max_daily_hours=float(provider["max_daily_hours"]),
            )
        except MissingRoadLegError:
            # Preserve valid cached hub round trips when only an inter-stop leg is absent.
            route_result = None
    use_multi_stop = bool(
        route_result
        and route_result["cost_won"] <= old_cost
        and route_result["duration_s"] <= old_duration
        and (
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

    current_minute = _minute(first_candidate["availability_start"])
    standalone_routes: list[dict[str, Any]] = []
    for sequence, (candidate, item) in enumerate(
        sorted(selected, key=lambda pair: (pair[0]["area_id"], pair[0]["service_type"])),
        start=1,
    ):
        route = candidate["route"]
        outbound_minutes = math.ceil(route["outbound_s"] / 60)
        service_start = current_minute + outbound_minutes
        service_end = service_start + candidate["duration_minutes"]
        return_minute = service_end + math.ceil(route["inbound_s"] / 60)
        if return_minute > _minute(candidate["availability_end"]):
            raise RuntimeError("conservative daily schedule exceeded provider availability")
        item.update(
            {
                "departure_time": _time(current_minute),
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
        current_minute = return_minute
    return standalone_routes


def generate_provider_schedule(
    areas: list[dict[str, Any]],
    providers: list[dict[str, Any]],
    connection: sqlite3.Connection,
    budget_won: int,
    scenario: Scenario,
) -> dict[str, Any]:
    """Schedule up to 28 days of provider-specific rounds; roads are exact cached Kakao legs."""
    if budget_won < 0:
        raise ValueError("budget must be nonnegative")
    if scenario not in {"efficiency", "balanced", "minimum_coverage"}:
        raise ValueError("unsupported planning scenario")
    if not areas or not providers:
        raise ValueError("areas and providers are required")
    for area in areas:
        if area.get("service_type") not in SERVICE_COST_WON:
            raise ValueError("unsupported or missing service type")
    routes = _route_rows(connection)
    candidates, blocked = _make_candidates(areas, providers, routes)
    model = cp_model.CpModel()
    visit_vars: list[cp_model.IntVar] = []
    unit_vars: list[cp_model.IntVar] = []
    rows_by_area: dict[str, list[int]] = {str(area["id"]): [] for area in areas}
    rows_by_provider_month: dict[tuple[str, str], list[int]] = {}
    rows_by_provider_date: dict[tuple[str, str], list[int]] = {}
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
        pay = model.new_int_var(
            0,
            max(maximum_service_cost, int(provider["minimum_compensation_won"])),
            f"provider_pay_{provider_id}_{month}",
        )
        model.add(pay >= service_cost)
        model.add(pay >= int(provider["minimum_compensation_won"]) * active)
        provider_pay_vars.append(pay)
    active_provider_days: list[cp_model.IntVar] = []
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
        window_active_vars = []
        for window_index, (window, window_indexes) in enumerate(indexes_by_window.items()):
            window_active = model.new_bool_var(
                f"window_{provider_id}_{scheduled_date}_{window_index}"
            )
            window_active_vars.append(window_active)
            for index in window_indexes:
                model.add(visit_vars[index] <= window_active)
            model.add(window_active <= sum(visit_vars[index] for index in window_indexes))
            available_minutes = _minute(window[1]) - _minute(window[0])
            daily_minutes = min(
                available_minutes,
                int(float(candidates[window_indexes[0]]["max_daily_hours"]) * 60),
            )
            estimated_work = sum(
                candidates[index]["estimated_work_minutes"] * visit_vars[index]
                for index in window_indexes
            )
            model.add(estimated_work <= daily_minutes * window_active)
        model.add(sum(window_active_vars) == day_active)

    max_units = sum(max(0, int(area.get("simulated_monthly_demand", 0))) for area in areas)
    total_units_expression = sum(unit_vars)
    total_units = model.new_int_var(0, max_units, "objective_total_units")
    model.add(total_units == total_units_expression)

    max_travel_cost = sum(candidate["route"]["cost_won"] for candidate in candidates)
    max_travel_time = sum(candidate["route"]["duration_s"] for candidate in candidates)
    travel_cost_expression = sum(
        candidates[index]["route"]["cost_won"] * visit_vars[index]
        for index in range(len(candidates))
    )
    travel_cost = model.new_int_var(0, max_travel_cost, "objective_travel_cost")
    model.add(travel_cost == travel_cost_expression)
    travel_time_expression = sum(
        candidates[index]["route"]["duration_s"] * visit_vars[index]
        for index in range(len(candidates))
    )
    travel_time = model.new_int_var(0, max_travel_time, "objective_travel_time")
    model.add(travel_time == travel_time_expression)
    total_cost = model.new_int_var(0, budget_won, "objective_total_cost")
    model.add(total_cost == sum(provider_pay_vars) + travel_cost)
    model.add(total_cost <= budget_won)
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
    max_survey_areas = sum(bool(area.get("needs_survey")) for area in areas)
    survey_count_expression = sum(
        area_covered_vars[str(area["id"])] for area in areas if area.get("needs_survey")
    )
    survey_count = model.new_int_var(0, max_survey_areas, "objective_survey_areas")
    model.add(survey_count == survey_count_expression)
    max_vulnerability = sum(_vulnerability_points(area) for area in areas)
    vulnerability_expression = sum(
        _vulnerability_points(area) * area_covered_vars[str(area["id"])] for area in areas
    )
    vulnerability = model.new_int_var(0, max_vulnerability, "objective_vulnerability")
    model.add(vulnerability == vulnerability_expression)
    max_provider_days = len(rows_by_provider_date)
    provider_days_expression = sum(active_provider_days)
    provider_days = model.new_int_var(0, max_provider_days, "objective_provider_days")
    model.add(provider_days == provider_days_expression)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = MAX_SOLVER_SECONDS
    solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = 2026
    if scenario == "efficiency":
        score = _lexicographic_score(
            [
                (total_units, max_units, True),
                (provider_days, max_provider_days, False),
                (travel_cost, max_travel_cost, False),
                (travel_time, max_travel_time, False),
            ]
        )
    elif scenario == "minimum_coverage":
        score = _lexicographic_score(
            [
                (covered_count, len(areas), True),
                (total_units, max_units, True),
                (provider_days, max_provider_days, False),
                (total_cost, budget_won, False),
            ]
        )
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
        model.add(scaled_total_cost * 100 <= total_cost)
        model.add(total_cost <= scaled_total_cost * 100 + 99)
        score = _lexicographic_score(
            [
                (total_units, max_units, True),
                (covered_count, len(areas), True),
                (survey_count, max_survey_areas, True),
                (vulnerability, max_vulnerability, True),
                (concentration, 10_000, False),
                (provider_days, max_provider_days, False),
                (scaled_total_cost, budget_won // 100, False),
            ]
        )
    model.maximize(score)
    status = solver.solve(model)
    if status not in {cp_model.OPTIMAL, cp_model.FEASIBLE}:
        raise RuntimeError(
            f"provider scheduling found no feasible plan ({solver.status_name(status)})"
        )

    service_cost_by_provider_month: dict[tuple[str, str], int] = {}
    rounds: list[dict[str, Any]] = []
    selected_by_provider_date: dict[
        tuple[str, str], list[tuple[dict[str, Any], dict[str, Any]]]
    ] = {}
    service_cost_total = 0
    served_by_area = {str(area["id"]): 0 for area in areas}
    for candidate in candidates:
        count = solver.value(candidate["units_var"])
        if count <= 0:
            continue
        service_cost_won = count * SERVICE_COST_WON[candidate["service_type"]]
        route = candidate["route"]
        round_item = {
            "provider_id": candidate["provider_id"],
            "provider_name": candidate["provider_name"],
            "area_id": candidate["area_id"],
            "area_name": candidate["area_name"],
            "service_type": candidate["service_type"],
            "scheduled_date": candidate["scheduled_date"],
            "departure_time": candidate["departure_time"],
            "service_start_time": candidate["service_start_time"],
            "service_end_time": candidate["service_end_time"],
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
            "participation_status": "AVAILABLE",
            "provenance": "OPTIMIZATION RESULT; KAKAO ROAD CACHE; SIMULATED PROVIDER",
            "route_group_key": f"{candidate['provider_id']}::{candidate['scheduled_date']}",
            "route_sequence": 1,
            "route_type": "HUB_ROUND_TRIP",
            "route_from_area_id": candidate["base_area_id"],
            "route_to_area_id": candidate["base_area_id"],
        }
        rounds.append(round_item)
        selected_by_provider_date.setdefault(
            (candidate["provider_id"], candidate["scheduled_date"]), []
        ).append((candidate, round_item))
        key = (candidate["provider_id"], candidate["month"])
        service_cost_by_provider_month[key] = (
            service_cost_by_provider_month.get(key, 0) + service_cost_won
        )
        served_by_area[candidate["area_id"]] += count
        service_cost_total += service_cost_won

    minimum_topup_total = 0
    selected_provider_month: dict[tuple[str, str], int] = {}
    for key, service_cost_won in service_cost_by_provider_month.items():
        provider_id, _month = key
        minimum_compensation = int(provider_lookup[provider_id]["minimum_compensation_won"])
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
    for provider_date in sorted(selected_by_provider_date):
        provider_id, _scheduled_date = provider_date
        route_records.extend(
            _route_selected_stops(
                selected_by_provider_date[provider_date],
                provider_lookup[provider_id],
                routes,
            )
        )
    travel_cost_total = sum(int(route["cost_won"]) for route in route_records)
    distance_total = sum(int(route["distance_m"]) for route in route_records)
    duration_total = sum(int(route["duration_s"]) for route in route_records)
    actual_total_cost_won = service_cost_total + travel_cost_total + minimum_topup_total
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
        area_blockers = blocked[area_id]
        if "NO_SUPPORTED_PROVIDER" in area_blockers:
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
            reason = (
                "PREFERRED_DAY_CONFLICT"
                if "PREFERRED_DAY_CONFLICT" in area_blockers
                else "PROVIDER_UNAVAILABLE"
            )
        else:
            supported = [
                provider
                for provider in providers
                if area["service_type"] in provider["supported_services"]
            ]
            available_capacity = 0
            for provider in supported:
                months = {
                    candidate["month"]
                    for candidate in candidates
                    if candidate["provider_id"] == provider["provider_id"]
                    and candidate["area_id"] == area_id
                }
                for month in months:
                    slot_capacity = sum(
                        candidate["service_capacity"]
                        for candidate in candidates
                        if candidate["provider_id"] == provider["provider_id"]
                        and candidate["area_id"] == area_id
                        and candidate["month"] == month
                    )
                    available_capacity += min(
                        slot_capacity,
                        int(provider["max_monthly_rounds"]) * int(provider["service_capacity"]),
                    )
            if available_capacity < int(area.get("simulated_monthly_demand", 0)):
                reason = "PROVIDER_CAPACITY"
            else:
                marginal_costs = []
                for candidate in candidates:
                    if candidate["area_id"] != area_id:
                        continue
                    key = (candidate["provider_id"], candidate["month"])
                    already_active = key in selected_provider_month
                    service_cost = SERVICE_COST_WON[candidate["service_type"]]
                    provider_cost = (
                        service_cost
                        if already_active
                        else max(service_cost, candidate["minimum_compensation_won"])
                    )
                    marginal_costs.append(provider_cost + candidate["route"]["cost_won"])
                minimum_marginal = min(marginal_costs, default=budget_won + 1)
                reason = (
                    "BUDGET"
                    if budget_won - actual_total_cost_won < minimum_marginal
                    else "PROVIDER_CAPACITY"
                )
        area["unserved_units"] = remaining
        area["constraint_reason"] = reason

    served_units = sum(served_by_area.values())
    covered_areas = sum(value > 0 for value in served_by_area.values())
    total_demand = sum(max(0, int(area.get("simulated_monthly_demand", 0))) for area in areas)
    total_cost_won = actual_total_cost_won
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
        "budget_gap_won": None,
        "required_budget_won": None,
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
        "served_units": served_units,
        "covered_areas": covered_areas,
        "uncovered_areas": len(areas) - covered_areas,
        "minimum_coverage_met": covered_areas == len(areas),
        "unmet_criteria": [
            {
                "area_id": str(area["id"]),
                "area_name": area.get("name", str(area["id"])),
                "units": int(area.get("unserved_units", 0)),
                "reason": str(area.get("constraint_reason", "")),
            }
            for area in areas
            if int(area.get("unserved_units", 0)) > 0
        ],
        "rounds": sorted(rounds, key=lambda item: (item["scheduled_date"], item["departure_time"])),
        "travel_source": "Kakao Mobility directed road routes; provider multi-stop routing",
        "solver_status": solver.status_name(status),
        "optimality_proven": status == cp_model.OPTIMAL,
    }
