"""Deterministic CP-SAT planning for efficiency, balanced, and minimum coverage."""

from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass
from typing import Any, Literal

from ortools.sat.python import cp_model

from backend.settings import BALANCED_SCENARIO_WEIGHTS

SERVICE_COST_WON = {
    "laundry": 255_000,
    "daily_necessities": 225_000,
    "home_repair": 305_000,
}
TRAVEL_RATE_WON_PER_KM = 1_800
TRAVEL_LABOR_WON_PER_HOUR = 20_000
MAX_SOLVER_SECONDS = 3.0


@dataclass(frozen=True)
class AreaTrip:
    duration_s: int
    distance_m: int
    cost_won: int


def validate_input(
    areas: list[dict[str, Any]], providers: list[dict[str, Any]], budget: int
) -> None:
    if budget < 0:
        raise ValueError("budget must be nonnegative")
    if not areas or not providers:
        raise ValueError("areas and providers are required")
    if len({str(area.get("id")) for area in areas}) != len(areas):
        raise ValueError("area ids must be unique")
    if len({str(provider.get("id")) for provider in providers}) != len(providers):
        raise ValueError("provider ids must be unique")
    for area in areas:
        if int(area.get("simulated_monthly_demand", 0)) < 0:
            raise ValueError("negative demand is invalid")
        if area.get("service_type") not in SERVICE_COST_WON:
            raise ValueError("unsupported or missing service type")
    for provider in providers:
        if int(provider.get("capacity_per_month", 0)) < 0:
            raise ValueError("negative provider capacity is invalid")


def _route_rows(connection: sqlite3.Connection) -> dict[tuple[str, str], tuple[int, int]]:
    return {
        (str(origin), str(destination)): (int(distance), int(duration))
        for origin, destination, distance, duration in connection.execute(
            "SELECT origin_id, destination_id, distance_m, duration_s FROM travel_matrix"
        ).fetchall()
    }


def _central_area(
    areas: list[dict[str, Any]], routes: dict[tuple[str, str], tuple[int, int]]
) -> dict[str, Any]:
    def total_duration(candidate: dict[str, Any]) -> int:
        return sum(
            routes[(candidate["id"], other["id"])][1] + routes[(other["id"], candidate["id"])][1]
            for other in areas
            if other["id"] != candidate["id"]
        )

    return min(areas, key=total_duration)


def derive_trip_costs(
    areas: list[dict[str, Any]], connection: sqlite3.Connection
) -> tuple[str, dict[str, AreaTrip]]:
    routes = _route_rows(connection)
    expected = {(a["id"], b["id"]) for a in areas for b in areas}
    missing = expected - routes.keys()
    if missing:
        raise ValueError(
            f"travel matrix is incomplete ({len(missing)} exact directed pairs missing)"
        )
    hub = _central_area(areas, routes)
    trips: dict[str, AreaTrip] = {}
    for area in areas:
        outbound_m, outbound_s = routes[(hub["id"], area["id"])]
        inbound_m, inbound_s = routes[(area["id"], hub["id"])]
        distance = outbound_m + inbound_m
        duration = outbound_s + inbound_s
        cost = math.ceil(distance / 1000 * TRAVEL_RATE_WON_PER_KM)
        cost += math.ceil(duration / 3600 * TRAVEL_LABOR_WON_PER_HOUR)
        trips[area["id"]] = AreaTrip(duration, distance, cost)
    return str(hub["id"]), trips


def _trip_expense(area: dict[str, Any], trip: AreaTrip) -> int:
    return SERVICE_COST_WON[area["service_type"]] + trip.cost_won


def _objective_weight(area: dict[str, Any], scenario: str) -> int:
    if scenario == "efficiency":
        return 100
    elderly = float(area.get("elderly_ratio_65") or 0)
    population = max(int(area.get("population_total") or 0), 1)
    older_single_household_population_share = min(
        int(area.get("single_households_65_plus") or 0) / population, 1
    )
    # Explicit, documented coefficients: service fairness priority, older residents,
    # and low-data protection. Sparse records are never turned into zero demand.
    weights = BALANCED_SCENARIO_WEIGHTS
    score = weights.base
    score += round(weights.elderly_population_share * elderly)
    score += round(
        weights.older_single_household_population_share * older_single_household_population_share
    )
    if area.get("needs_survey"):
        score += weights.needs_survey
    return score


def _solve_scenario(
    areas: list[dict[str, Any]],
    providers: list[dict[str, Any]],
    trips: dict[str, AreaTrip],
    budget: int,
    scenario: Literal["efficiency", "balanced", "minimum_coverage"],
) -> dict[str, Any]:
    model = cp_model.CpModel()
    units: dict[str, cp_model.IntVar] = {}
    visits: dict[str, cp_model.IntVar] = {}
    spend_terms = []
    for area in areas:
        area_id = str(area["id"])
        demand = int(area["simulated_monthly_demand"])
        units[area_id] = model.new_int_var(0, demand, f"x_{area_id}")
        visits[area_id] = model.new_bool_var(f"v_{area_id}")
        model.add(units[area_id] <= demand * visits[area_id])
        model.add(visits[area_id] <= units[area_id])
        spend_terms.append(SERVICE_COST_WON[area["service_type"]] * units[area_id])
        spend_terms.append(trips[area_id].cost_won * visits[area_id])
    model.add(
        sum(units.values()) <= sum(int(provider["capacity_per_month"]) for provider in providers)
    )
    model.add(sum(spend_terms) <= budget)
    travel_terms = [trips[area_id].duration_s * visit for area_id, visit in visits.items()]

    if scenario == "minimum_coverage":
        score = sum(visits.values()) * 1_000_000
        score += sum(units.values()) * 1_000
        score -= sum(travel_terms)
    else:
        weighted_units = sum(
            _objective_weight(area, scenario) * units[str(area["id"])] for area in areas
        )
        score = weighted_units * 1_000_000 - sum(travel_terms)
    model.maximize(score)
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = MAX_SOLVER_SECONDS
    solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = 2026
    status = solver.solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise RuntimeError(f"scenario solve failed with status {solver.status_name(status)}")

    area_results: list[dict[str, Any]] = []
    total_spend = total_units = beneficiaries = travel_duration = 0
    travel_cost_total = 0
    provider_capacity = {
        str(provider["id"]): int(provider["capacity_per_month"]) for provider in providers
    }
    provider_used = {provider_id: 0 for provider_id in provider_capacity}
    for area in areas:
        area_id = str(area["id"])
        served_units = solver.value(units[area_id])
        visits_count = solver.value(visits[area_id])
        provider_units: dict[str, int] = {}
        remaining = served_units
        for provider_id in provider_capacity:
            allocation = min(remaining, provider_capacity[provider_id] - provider_used[provider_id])
            if allocation > 0:
                provider_units[provider_id] = allocation
                provider_used[provider_id] += allocation
                remaining -= allocation
            if remaining == 0:
                break
        if remaining:
            raise RuntimeError("solver allocation exceeded aggregate provider capacity")
        service_cost = served_units * SERVICE_COST_WON[area["service_type"]]
        route_cost = visits_count * trips[area_id].cost_won
        area_spend = service_cost + route_cost
        area_beneficiaries = served_units * int(area.get("simulated_beneficiaries_per_service", 1))
        area_time = visits_count * trips[area_id].duration_s
        total_spend += area_spend
        total_units += served_units
        beneficiaries += area_beneficiaries
        travel_duration += area_time
        travel_cost_total += route_cost
        area_results.append(
            {
                "area_id": area_id,
                "served_units": served_units,
                "demand_units": int(area["simulated_monthly_demand"]),
                "covered": served_units > 0,
                "visits": visits_count,
                "provider_assignments": {
                    key: value for key, value in provider_units.items() if value > 0
                },
                "cost_won": area_spend,
                "travel_time_s": area_time,
                "beneficiaries": area_beneficiaries,
                "status": "충족"
                if served_units >= int(area["simulated_monthly_demand"])
                else "부분충족"
                if served_units
                else "미충족",
                "needs_survey": bool(area.get("needs_survey")),
            }
        )
    total_demand = sum(int(area["simulated_monthly_demand"]) for area in areas)
    covered_areas = sum(item["covered"] for item in area_results)
    return {
        "scenario": scenario,
        "budget_won": budget,
        "required_budget_won": None,
        "additional_budget_won": None,
        "budget_spent_won": total_spend,
        "budget_remaining_won": budget - total_spend,
        "total_demand_units": total_demand,
        "served_units": total_units,
        "service_fulfillment_rate": round(total_units / total_demand, 4) if total_demand else 0,
        "covered_villages": covered_areas,
        "uncovered_villages": len(areas) - covered_areas,
        "minimum_services_per_area": 1 if scenario == "minimum_coverage" else None,
        "minimum_coverage_met": covered_areas == len(areas),
        "guarantee_capacity_feasible": None,
        "beneficiaries": beneficiaries,
        "travel_time_s": travel_duration,
        "travel_cost_won": travel_cost_total,
        "service_gap": len(areas) - covered_areas if scenario == "minimum_coverage" else None,
        "assignments": area_results,
        "solver_status": solver.status_name(status),
    }


def minimum_guarantee_budget(
    areas: list[dict[str, Any]], providers: list[dict[str, Any]], trips: dict[str, AreaTrip]
) -> int | None:
    if any(int(area["simulated_monthly_demand"]) < 1 for area in areas):
        return None
    if sum(int(provider["capacity_per_month"]) for provider in providers) < len(areas):
        return None
    return sum(_trip_expense(area, trips[str(area["id"])]) for area in areas)


def evaluate_scenarios(
    areas: list[dict[str, Any]],
    providers: list[dict[str, Any]],
    connection: sqlite3.Connection,
    budget: int,
) -> dict[str, Any]:
    validate_input(areas, providers, budget)
    hub_id, trips = derive_trip_costs(areas, connection)
    results = {
        scenario: _solve_scenario(areas, providers, trips, budget, scenario)
        for scenario in ("efficiency", "balanced", "minimum_coverage")
    }
    required_budget = minimum_guarantee_budget(areas, providers, trips)
    minimum = results["minimum_coverage"]
    minimum["guarantee_capacity_feasible"] = required_budget is not None
    if required_budget is not None:
        minimum["required_budget_won"] = required_budget
        minimum["additional_budget_won"] = max(0, required_budget - budget)
        minimum["budget_gap_won"] = max(0, required_budget - budget)
    else:
        minimum["additional_budget_won"] = None
        minimum["budget_gap_won"] = None
    efficiency = results["efficiency"]
    minimum["beneficiaries_added_vs_efficiency"] = (
        minimum["beneficiaries"] - efficiency["beneficiaries"]
    )
    minimum["travel_time_added_vs_efficiency_s"] = (
        minimum["travel_time_s"] - efficiency["travel_time_s"]
    )
    return {
        "region": "홍성군 장곡면",
        "budget_won": budget,
        "hub_area_id": hub_id,
        "travel_source": "Kakao Mobility road distance/time, directed routes cached in SQLite",
        "scenario_results": results,
    }
