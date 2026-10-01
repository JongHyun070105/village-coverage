"""Deterministic CP-SAT planning for efficiency, balanced, and minimum coverage."""

from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass
from typing import Any, Literal

from ortools.sat.python import cp_model

from backend.settings import BALANCED_SCENARIO_WEIGHTS, PlanningPolicy

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


def _vulnerability_points(
    area: dict[str, Any],
    elderly_priority_weight: int = BALANCED_SCENARIO_WEIGHTS.vulnerability_points_per_share,
    single_elderly_priority_weight: int = BALANCED_SCENARIO_WEIGHTS.vulnerability_points_per_share,
) -> int:
    population = max(int(area.get("population_total") or 0), 1)
    single_households = max(int(area.get("single_households_total") or 0), 0)
    single_denominator = single_households or population
    single_elderly_share = min(
        int(area.get("single_households_65_plus") or 0) / max(single_denominator, 1), 1
    )
    elderly_share = min(max(float(area.get("elderly_ratio_65") or 0), 0), 1)
    return round(
        elderly_priority_weight * elderly_share
        + single_elderly_priority_weight * single_elderly_share
    )


def _validate_policy(policy: PlanningPolicy) -> None:
    if not 1 <= policy.minimum_services_per_area <= 8:
        raise ValueError("minimum_services_per_area must be between 1 and 8")
    for name, value in (
        ("elderly_priority_weight", policy.elderly_priority_weight),
        (
            "single_elderly_household_priority_weight",
            policy.single_elderly_household_priority_weight,
        ),
        ("survey_required_protection_weight", policy.survey_required_protection_weight),
    ):
        if not 0 <= value <= 1000:
            raise ValueError(f"{name} must be between 0 and 1000")
    if (
        policy.maximum_round_trip_travel_minutes is not None
        and not 1 <= policy.maximum_round_trip_travel_minutes <= 360
    ):
        raise ValueError("maximum_round_trip_travel_minutes must be between 1 and 360")
    if policy.minimum_provider_compensation_won < 0:
        raise ValueError("minimum_provider_compensation_won must be nonnegative")
    if not set(policy.allowed_services) <= set(SERVICE_COST_WON):
        raise ValueError("allowed_services contains an unsupported service")


def _unmet_minimum_reason(
    area: dict[str, Any],
    providers: list[dict[str, Any]],
    trip: AreaTrip,
    budget: int,
    policy: PlanningPolicy,
    scenario: str,
) -> str:
    minimum = policy.minimum_services_per_area
    demand = int(area["simulated_monthly_demand"])
    if demand < minimum:
        return "DEMAND_BELOW_MINIMUM"

    service_type = str(area["service_type"])
    compatible = [
        provider
        for provider in providers
        if int(provider["capacity_per_month"]) > 0
        and (
            provider.get("supported_services") is None
            or service_type in provider["supported_services"]
        )
    ]
    if sum(int(provider["capacity_per_month"]) for provider in compatible) < minimum:
        return "PROVIDER_CAPACITY"

    service_cost = SERVICE_COST_WON[service_type]
    minimum_cost_by_round_count = {0: 0}
    for provider in compatible:
        capacity = min(minimum, int(provider["capacity_per_month"]))
        compensation_floor = max(
            int(provider.get("minimum_compensation_won", 0)),
            policy.minimum_provider_compensation_won,
        )
        next_costs = dict(minimum_cost_by_round_count)
        for assigned, current_cost in minimum_cost_by_round_count.items():
            for provider_rounds in range(1, min(capacity, minimum - assigned) + 1):
                total_rounds = assigned + provider_rounds
                provider_cost = max(provider_rounds * service_cost, compensation_floor)
                candidate_cost = current_cost + provider_cost
                next_costs[total_rounds] = min(
                    next_costs.get(total_rounds, candidate_cost), candidate_cost
                )
        minimum_cost_by_round_count = next_costs

    provider_cost = minimum_cost_by_round_count.get(minimum)
    if provider_cost is None:
        return "PROVIDER_CAPACITY"
    if provider_cost + minimum * trip.cost_won > budget:
        return "BUDGET"
    if scenario != "minimum_coverage":
        return "SCENARIO_PRIORITY"
    return "SHARED_BUDGET_OR_CAPACITY"


def _lexicographic_score(components: list[tuple[Any, int, bool]]) -> Any:
    """Encode bounded lexicographic objectives without heuristic tie weights."""
    score = 0
    multiplier = 1
    for expression, maximum, maximize in reversed(components):
        if maximum < 0:
            raise ValueError("objective bounds must be nonnegative")
        score += (expression if maximize else maximum - expression) * multiplier
        multiplier *= maximum + 1
    if multiplier >= 2**62:
        raise ValueError("lexicographic objective exceeds the safe CP-SAT integer range")
    return score


def _solve_scenario(
    areas: list[dict[str, Any]],
    providers: list[dict[str, Any]],
    trips: dict[str, AreaTrip],
    budget: int,
    scenario: Literal["efficiency", "balanced", "minimum_coverage"],
    policy: PlanningPolicy,
) -> dict[str, Any]:
    model = cp_model.CpModel()
    units: dict[str, cp_model.IntVar] = {}
    visits: dict[str, cp_model.IntVar] = {}
    guarantee: dict[str, cp_model.IntVar] = {}
    area_provider_units: dict[str, list[tuple[str, cp_model.IntVar]]] = {}
    provider_unit_terms: dict[str, list[tuple[str, cp_model.IntVar]]] = {
        str(provider["id"]): [] for provider in providers
    }
    area_block_reasons: dict[str, str] = {}
    provider_capacity = {
        str(provider["id"]): int(provider["capacity_per_month"]) for provider in providers
    }
    area_is_eligible: dict[str, bool] = {}
    for area in areas:
        area_id = str(area["id"])
        demand = int(area["simulated_monthly_demand"])
        units[area_id] = model.new_int_var(0, demand, f"x_{area_id}")
        visits[area_id] = model.new_bool_var(f"v_{area_id}")
        model.add(units[area_id] <= demand * visits[area_id])
        model.add(visits[area_id] <= units[area_id])
        reasons = []
        if area["service_type"] not in policy.allowed_services:
            reasons.append("SERVICE_NOT_ALLOWED")
        if (
            policy.maximum_round_trip_travel_minutes is not None
            and trips[area_id].duration_s > policy.maximum_round_trip_travel_minutes * 60
        ):
            reasons.append("MAX_TRAVEL_TIME")
        compatible = []
        for provider in providers:
            provider_id = str(provider["id"])
            supported = provider.get("supported_services")
            supports_service = supported is None or area["service_type"] in supported
            if supports_service and provider_capacity[provider_id] > 0:
                assignment = model.new_int_var(
                    0,
                    min(demand, provider_capacity[provider_id]),
                    f"provider_units_{area_id}_{provider_id}",
                )
                provider_unit_terms[provider_id].append((area_id, assignment))
                compatible.append((provider_id, assignment))
        if not compatible:
            reasons.append("NO_SUPPORTED_PROVIDER")
        area_provider_units[area_id] = compatible
        area_is_eligible[area_id] = not reasons
        if reasons:
            area_block_reasons[area_id] = reasons[0]
            model.add(units[area_id] == 0)
            model.add(visits[area_id] == 0)
            for _, assignment in compatible:
                model.add(assignment == 0)
        elif compatible:
            model.add(sum(variable for _, variable in compatible) == units[area_id])

        if scenario == "minimum_coverage":
            guarantee[area_id] = model.new_bool_var(f"minimum_frequency_met_{area_id}")
            if not area_is_eligible[area_id] or demand < policy.minimum_services_per_area:
                model.add(guarantee[area_id] == 0)
            else:
                model.add(units[area_id] >= policy.minimum_services_per_area * guarantee[area_id])
                model.add(guarantee[area_id] <= visits[area_id])

    provider_paid: dict[str, cp_model.IntVar] = {}
    provider_service_cost: dict[str, Any] = {}
    provider_active: dict[str, cp_model.IntVar] = {}
    provider_compensation_floor: dict[str, int] = {}
    spend_terms = []
    maximum_cost_by_unit = max(SERVICE_COST_WON.values())
    for provider in providers:
        provider_id = str(provider["id"])
        capacity = provider_capacity[provider_id]
        active = model.new_bool_var(f"provider_active_{provider_id}")
        provider_active[provider_id] = active
        total_units = model.new_int_var(0, capacity, f"provider_total_units_{provider_id}")
        terms = [variable for _, variable in provider_unit_terms[provider_id]]
        model.add(total_units == sum(terms))
        if capacity:
            model.add(total_units <= capacity * active)
            model.add(total_units >= active)
        else:
            model.add(active == 0)
        service_cost = sum(
            variable
            * SERVICE_COST_WON[
                next(area["service_type"] for area in areas if str(area["id"]) == area_id)
            ]
            for area_id, variable in provider_unit_terms[provider_id]
        )
        provider_service_cost[provider_id] = service_cost
        compensation_floor = max(
            int(provider.get("minimum_compensation_won", 0)),
            policy.minimum_provider_compensation_won,
        )
        provider_compensation_floor[provider_id] = compensation_floor
        paid = model.new_int_var(
            0,
            max(capacity * maximum_cost_by_unit, compensation_floor),
            f"provider_compensation_{provider_id}",
        )
        model.add_max_equality(paid, [service_cost, compensation_floor * active])
        provider_paid[provider_id] = paid
        spend_terms.append(paid)
    spend_terms.extend(trips[str(area["id"])].cost_won * units[str(area["id"])] for area in areas)
    model.add(sum(spend_terms) <= budget)
    total_units = sum(units.values())
    covered_count = sum(visits.values())
    travel_cost = sum(trips[area_id].cost_won * units[area_id] for area_id in units)
    travel_time = sum(trips[area_id].duration_s * units[area_id] for area_id in units)
    maximum_travel_cost = sum(
        trips[str(area["id"])].cost_won * int(area["simulated_monthly_demand"]) for area in areas
    )
    maximum_travel_time = sum(
        trips[str(area["id"])].duration_s * int(area["simulated_monthly_demand"]) for area in areas
    )

    if scenario == "efficiency":
        primary = _lexicographic_score(
            [
                (total_units, sum(int(area["simulated_monthly_demand"]) for area in areas), True),
                (travel_cost, maximum_travel_cost, False),
                (travel_time, maximum_travel_time, False),
            ]
        )
        model.maximize(primary)
        solver = _new_solver()
        status = solver.solve(model)
    elif scenario == "minimum_coverage":
        primary = _lexicographic_score(
            [
                (sum(guarantee.values()), len(areas), True),
                (covered_count, len(areas), True),
                (total_units, sum(int(area["simulated_monthly_demand"]) for area in areas), True),
                (travel_cost, maximum_travel_cost, False),
                (travel_time, maximum_travel_time, False),
            ]
        )
        model.maximize(primary)
        solver = _new_solver()
        status = solver.solve(model)
    else:
        survey_weight = policy.survey_required_protection_weight
        survey_visits = sum(
            survey_weight * visits[str(area["id"])] for area in areas if area.get("needs_survey")
        )
        vulnerable_area_points = sum(
            _vulnerability_points(
                area,
                policy.elderly_priority_weight,
                policy.single_elderly_household_priority_weight,
            )
            * visits[str(area["id"])]
            for area in areas
        )
        maximum_vulnerability_points = sum(
            _vulnerability_points(
                area,
                policy.elderly_priority_weight,
                policy.single_elderly_household_priority_weight,
            )
            for area in areas
        )
        primary = _lexicographic_score(
            [
                (total_units, sum(int(area["simulated_monthly_demand"]) for area in areas), True),
                (covered_count, len(areas), True),
                (
                    survey_visits,
                    survey_weight * sum(bool(area.get("needs_survey")) for area in areas),
                    True,
                ),
                (vulnerable_area_points, maximum_vulnerability_points, True),
            ]
        )
        model.maximize(primary)
        solver = _new_solver()
        status = solver.solve(model)
        if status == cp_model.OPTIMAL:
            model.add(primary == solver.value(primary))
            concentration = model.new_int_var(
                0, BALANCED_SCENARIO_WEIGHTS.concentration_basis_points, "max_area_saturation"
            )
            for area in areas:
                area_id = str(area["id"])
                demand = int(area["simulated_monthly_demand"])
                if demand:
                    area_saturation = model.new_int_var(
                        0,
                        BALANCED_SCENARIO_WEIGHTS.concentration_basis_points,
                        f"saturation_{area_id}",
                    )
                    model.add(
                        area_saturation * demand
                        >= units[area_id] * BALANCED_SCENARIO_WEIGHTS.concentration_basis_points
                    )
                    model.add(concentration >= area_saturation)
            secondary = _lexicographic_score(
                [
                    (concentration, BALANCED_SCENARIO_WEIGHTS.concentration_basis_points, False),
                    (travel_cost, maximum_travel_cost, False),
                    (travel_time, maximum_travel_time, False),
                ]
            )
            model.maximize(secondary)
            solver = _new_solver()
            status = solver.solve(model)
    if status not in {cp_model.OPTIMAL, cp_model.FEASIBLE}:
        raise RuntimeError(f"scenario solve did not prove optimum ({solver.status_name(status)})")
    optimality_proven = status == cp_model.OPTIMAL

    area_results: list[dict[str, Any]] = []
    base_service_cost_total = served_total = travel_duration = travel_distance = 0
    travel_cost_total = compensation_topup_total = provider_minimum_total = 0
    for area in areas:
        area_id = str(area["id"])
        served_units = solver.value(units[area_id])
        visits_count = served_units
        provider_units = {
            provider_id: solver.value(variable)
            for provider_id, variable in area_provider_units[area_id]
            if solver.value(variable) > 0
        }
        service_cost = served_units * SERVICE_COST_WON[area["service_type"]]
        route_cost = visits_count * trips[area_id].cost_won
        area_spend = service_cost + route_cost
        area_time = visits_count * trips[area_id].duration_s
        area_distance = visits_count * trips[area_id].distance_m
        base_service_cost_total += service_cost
        served_total += served_units
        travel_duration += area_time
        travel_distance += area_distance
        travel_cost_total += route_cost
        unmet_minimum = served_units < policy.minimum_services_per_area
        constraint_reason = area_block_reasons.get(area_id)
        if unmet_minimum and constraint_reason is None:
            constraint_reason = _unmet_minimum_reason(
                area, providers, trips[area_id], budget, policy, scenario
            )
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
                "travel_distance_m": area_distance,
                "status": "충족"
                if served_units >= int(area["simulated_monthly_demand"])
                else "부분충족"
                if served_units
                else "미충족",
                "needs_survey": bool(area.get("needs_survey")),
                "minimum_frequency_met": not unmet_minimum,
                "constraint_reason": constraint_reason,
            }
        )
    for provider_id, paid in provider_paid.items():
        provider_minimum_total += provider_compensation_floor[provider_id] * solver.value(
            provider_active[provider_id]
        )
        compensation_topup_total += solver.value(paid) - solver.value(
            provider_service_cost[provider_id]
        )
    provider_cost_breakdown = []
    for provider in providers:
        provider_id = str(provider["id"])
        provider_assignments = [
            (area_id, solver.value(variable))
            for area_id, variable in provider_unit_terms[provider_id]
            if solver.value(variable) > 0
        ]
        if not provider_assignments:
            continue
        service_cost = solver.value(provider_service_cost[provider_id])
        compensation_paid = solver.value(provider_paid[provider_id])
        provider_travel_distance = sum(
            rounds * trips[area_id].distance_m for area_id, rounds in provider_assignments
        )
        provider_travel_time = sum(
            rounds * trips[area_id].duration_s for area_id, rounds in provider_assignments
        )
        provider_travel_cost = sum(
            rounds * trips[area_id].cost_won for area_id, rounds in provider_assignments
        )
        provider_cost_breakdown.append(
            {
                "provider_id": provider_id,
                "provider_name": str(provider.get("name") or provider_id),
                "service_rounds": sum(rounds for _, rounds in provider_assignments),
                "service_cost_won": service_cost,
                "travel_distance_m": provider_travel_distance,
                "travel_time_s": provider_travel_time,
                "travel_cost_won": provider_travel_cost,
                "minimum_compensation_floor_won": provider_compensation_floor[provider_id],
                "compensation_paid_won": compensation_paid,
                "compensation_topup_won": compensation_paid - service_cost,
                "total_cost_won": compensation_paid + provider_travel_cost,
            }
        )
    total_spend = base_service_cost_total + travel_cost_total + compensation_topup_total
    total_demand = sum(int(area["simulated_monthly_demand"]) for area in areas)
    covered_areas = sum(item["covered"] for item in area_results)
    saturation_basis_points = BALANCED_SCENARIO_WEIGHTS.concentration_basis_points
    max_area_demand_saturation = max(
        (
            -(-(item["served_units"] * saturation_basis_points) // item["demand_units"])
            for item in area_results
            if item["demand_units"] > 0
        ),
        default=0,
    )
    unmet_minimum_areas = sum(not item["minimum_frequency_met"] for item in area_results)
    minimum_met_count = len(areas) - unmet_minimum_areas
    return {
        "scenario": scenario,
        "budget_won": budget,
        "required_budget_won": None,
        "additional_budget_won": None,
        "budget_spent_won": total_spend,
        "budget_remaining_won": budget - total_spend,
        "service_cost_won": base_service_cost_total,
        "travel_cost_won": travel_cost_total,
        "provider_minimum_compensation_won": provider_minimum_total,
        "minimum_compensation_topup_won": compensation_topup_total,
        "provider_cost_breakdown": provider_cost_breakdown,
        "provider_travel_model": "CENTRAL_HUB_ROUND_TRIP_ESTIMATE",
        "additional_public_subsidy_won": None,
        "total_demand_units": total_demand,
        "served_units": served_total,
        "service_fulfillment_rate": round(served_total / total_demand, 4) if total_demand else 0,
        "covered_villages": covered_areas,
        "uncovered_villages": len(areas) - covered_areas,
        "minimum_services_per_area": policy.minimum_services_per_area
        if scenario == "minimum_coverage"
        else None,
        "required_capacity": None,
        "available_capacity": None,
        "missing_capacity": None,
        "minimum_coverage_met": unmet_minimum_areas == 0,
        "minimum_frequency_met_areas": minimum_met_count,
        "unmet_minimum_frequency_areas": unmet_minimum_areas,
        "guarantee_capacity_feasible": None,
        "travel_time_s": travel_duration,
        "travel_distance_m": travel_distance,
        "max_area_demand_saturation_basis_points": max_area_demand_saturation,
        "service_gap": unmet_minimum_areas if scenario == "minimum_coverage" else None,
        "assignments": area_results,
        "solver_status": solver.status_name(status),
        "optimality_proven": optimality_proven,
    }


def _new_solver() -> cp_model.CpSolver:
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = MAX_SOLVER_SECONDS
    solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = 2026
    return solver


def _request_count_baseline(
    areas: list[dict[str, Any]],
    providers: list[dict[str, Any]],
    trips: dict[str, AreaTrip],
    budget: int,
) -> dict[str, Any]:
    remaining_capacity = sum(int(provider["capacity_per_month"]) for provider in providers)
    spend = units = travel_time = travel_cost = covered = 0
    assigned = {str(area["id"]): 0 for area in areas}
    for area in sorted(
        areas, key=lambda item: (-int(item["demand_observation_count"]), str(item["id"]))
    ):
        area_id = str(area["id"])
        while (
            assigned[area_id]
            < min(
                int(area["demand_observation_count"]),
                int(area["simulated_monthly_demand"]),
            )
            and remaining_capacity > 0
            and spend + SERVICE_COST_WON[area["service_type"]] + trips[area_id].cost_won <= budget
        ):
            if assigned[area_id] == 0:
                covered += 1
            spend += trips[area_id].cost_won
            travel_cost += trips[area_id].cost_won
            travel_time += trips[area_id].duration_s
            spend += SERVICE_COST_WON[area["service_type"]]
            assigned[area_id] += 1
            units += 1
            remaining_capacity -= 1
    survey_areas = [area for area in areas if area.get("needs_survey")]
    survey_covered = sum(assigned[str(area["id"])] > 0 for area in survey_areas)
    return {
        "served_units": units,
        "covered_villages": covered,
        "uncovered_villages": len(areas) - covered,
        "survey_required_areas": len(survey_areas),
        "survey_required_covered": survey_covered,
        "budget_spent_won": spend,
        "travel_cost_won": travel_cost,
        "travel_time_s": travel_time,
        "service_units_by_area": assigned,
    }


def minimum_guarantee_budget(
    areas: list[dict[str, Any]],
    providers: list[dict[str, Any]],
    trips: dict[str, AreaTrip],
    policy: PlanningPolicy | None = None,
) -> int | None:
    active_policy = policy or PlanningPolicy()
    _validate_policy(active_policy)
    model = cp_model.CpModel()
    assignments: dict[str, list[tuple[str, cp_model.IntVar]]] = {}
    provider_terms: dict[str, list[tuple[str, cp_model.IntVar]]] = {
        str(provider["id"]): [] for provider in providers
    }
    for area in areas:
        area_id = str(area["id"])
        service_type = str(area["service_type"])
        required = active_policy.minimum_services_per_area
        demand = int(area["simulated_monthly_demand"])
        if (
            service_type not in active_policy.allowed_services
            or demand < required
            or (
                active_policy.maximum_round_trip_travel_minutes is not None
                and trips[area_id].duration_s > active_policy.maximum_round_trip_travel_minutes * 60
            )
        ):
            return None
        compatible = []
        for provider in providers:
            provider_id = str(provider["id"])
            supported = provider.get("supported_services")
            capacity = int(provider["capacity_per_month"])
            if capacity > 0 and (supported is None or service_type in supported):
                variable = model.new_int_var(
                    0, min(required, capacity), f"guarantee_{area_id}_{provider_id}"
                )
                compatible.append((provider_id, variable))
                provider_terms[provider_id].append((area_id, variable))
        if not compatible:
            return None
        assignments[area_id] = compatible
        model.add(sum(variable for _, variable in compatible) == required)

    provider_paid = []
    for provider in providers:
        provider_id = str(provider["id"])
        capacity = int(provider["capacity_per_month"])
        terms = [variable for _, variable in provider_terms[provider_id]]
        used = model.new_int_var(0, capacity, f"guarantee_provider_units_{provider_id}")
        model.add(used == sum(terms))
        active = model.new_bool_var(f"guarantee_provider_active_{provider_id}")
        if capacity:
            model.add(used <= capacity * active)
            model.add(used >= active)
        else:
            model.add(active == 0)
        service_cost = sum(
            variable
            * SERVICE_COST_WON[
                next(area["service_type"] for area in areas if str(area["id"]) == area_id)
            ]
            for area_id, variable in provider_terms[provider_id]
        )
        compensation_floor = max(
            int(provider.get("minimum_compensation_won", 0)),
            active_policy.minimum_provider_compensation_won,
        )
        paid = model.new_int_var(
            0,
            max(capacity * max(SERVICE_COST_WON.values()), compensation_floor),
            f"guarantee_provider_pay_{provider_id}",
        )
        model.add_max_equality(paid, [service_cost, compensation_floor * active])
        provider_paid.append(paid)

    required_travel = sum(
        trips[str(area["id"])].cost_won * active_policy.minimum_services_per_area for area in areas
    )
    model.minimize(sum(provider_paid) + required_travel)
    solver = _new_solver()
    status = solver.solve(model)
    return int(round(solver.objective_value)) if status == cp_model.OPTIMAL else None


def _minimum_guarantee_failure_reason(
    areas: list[dict[str, Any]],
    providers: list[dict[str, Any]],
    trips: dict[str, AreaTrip],
    policy: PlanningPolicy,
) -> str | None:
    for area in areas:
        if str(area["service_type"]) not in policy.allowed_services:
            return "SERVICE_NOT_ALLOWED"
    for area in areas:
        if int(area["simulated_monthly_demand"]) < policy.minimum_services_per_area:
            return "DEMAND_BELOW_MINIMUM"
    for area in areas:
        if (
            policy.maximum_round_trip_travel_minutes is not None
            and trips[str(area["id"])].duration_s > policy.maximum_round_trip_travel_minutes * 60
        ):
            return "MAX_TRAVEL_TIME"

    model = cp_model.CpModel()
    provider_terms: dict[str, list[cp_model.IntVar]] = {
        str(provider["id"]): [] for provider in providers
    }
    for area in areas:
        area_id = str(area["id"])
        service_type = str(area["service_type"])
        compatible = []
        if not any(
            int(provider["capacity_per_month"]) > 0
            and (
                provider.get("supported_services") is None
                or service_type in provider["supported_services"]
            )
            for provider in providers
        ):
            return "NO_SUPPORTED_PROVIDER"
        for provider in providers:
            provider_id = str(provider["id"])
            capacity = int(provider["capacity_per_month"])
            supported = provider.get("supported_services")
            if capacity and (supported is None or service_type in supported):
                units = model.new_int_var(
                    0,
                    min(policy.minimum_services_per_area, capacity),
                    f"capacity_{area_id}_{provider_id}",
                )
                compatible.append(units)
                provider_terms[provider_id].append(units)
        model.add(sum(compatible) == policy.minimum_services_per_area)
    for provider in providers:
        model.add(sum(provider_terms[str(provider["id"])]) <= int(provider["capacity_per_month"]))
    solver = _new_solver()
    status = solver.solve(model)
    if status == cp_model.INFEASIBLE:
        return "PROVIDER_CAPACITY_OR_SERVICE_MIX"
    if status not in {cp_model.OPTIMAL, cp_model.FEASIBLE}:
        return "GUARANTEE_FEASIBILITY_NOT_PROVEN"
    return None


def _full_demand_required_budget(
    areas: list[dict[str, Any]],
    providers: list[dict[str, Any]],
    trips: dict[str, AreaTrip],
    policy: PlanningPolicy,
) -> tuple[int | None, str, str | None]:
    """Find the least aggregate hub-round-trip budget for all modeled demand."""
    model = cp_model.CpModel()
    provider_terms: dict[str, list[cp_model.IntVar]] = {
        str(provider["id"]): [] for provider in providers
    }
    area_assignments: dict[str, list[tuple[str, cp_model.IntVar]]] = {}
    service_by_area = {str(area["id"]): str(area["service_type"]) for area in areas}

    for area in areas:
        area_id = str(area["id"])
        demand = int(area["simulated_monthly_demand"])
        if demand == 0:
            area_assignments[area_id] = []
            continue
        service_type = str(area["service_type"])
        if service_type not in policy.allowed_services:
            return None, "INFEASIBLE", "SERVICE_NOT_ALLOWED"
        if (
            policy.maximum_round_trip_travel_minutes is not None
            and trips[area_id].duration_s > policy.maximum_round_trip_travel_minutes * 60
        ):
            return None, "INFEASIBLE", "MAX_TRAVEL_TIME"

        supporting_providers = [
            provider
            for provider in providers
            if provider.get("supported_services") is None
            or service_type in provider["supported_services"]
        ]
        if not supporting_providers:
            return None, "INFEASIBLE", "NO_SUPPORTED_PROVIDER"

        assignments: list[tuple[str, cp_model.IntVar]] = []
        for provider in supporting_providers:
            provider_id = str(provider["id"])
            capacity = int(provider["capacity_per_month"])
            if capacity <= 0:
                continue
            assignment = model.new_int_var(
                0, min(demand, capacity), f"full_demand_{area_id}_{provider_id}"
            )
            assignments.append((provider_id, assignment))
            provider_terms[provider_id].append(assignment)
        if not assignments:
            return None, "INFEASIBLE", "PROVIDER_CAPACITY_OR_SERVICE_MIX"
        model.add(sum(variable for _, variable in assignments) == demand)
        area_assignments[area_id] = assignments

    provider_pay: list[cp_model.IntVar] = []
    maximum_service_cost = max(SERVICE_COST_WON.values())
    for provider in providers:
        provider_id = str(provider["id"])
        capacity = int(provider["capacity_per_month"])
        assignments = provider_terms[provider_id]
        total_units = model.new_int_var(0, capacity, f"full_demand_total_{provider_id}")
        model.add(total_units == sum(assignments))
        active = model.new_bool_var(f"full_demand_active_{provider_id}")
        if capacity:
            model.add(total_units <= capacity * active)
            model.add(total_units >= active)
        else:
            model.add(active == 0)
        service_cost = sum(
            variable * SERVICE_COST_WON[service_by_area[area_id]]
            for area_id, assignments in area_assignments.items()
            for assigned_provider_id, variable in assignments
            if assigned_provider_id == provider_id
        )
        compensation_floor = max(
            int(provider.get("minimum_compensation_won", 0)),
            policy.minimum_provider_compensation_won,
        )
        paid = model.new_int_var(
            0,
            max(capacity * maximum_service_cost, compensation_floor),
            f"full_demand_pay_{provider_id}",
        )
        model.add_max_equality(paid, [service_cost, compensation_floor * active])
        provider_pay.append(paid)

    hub_travel_cost = sum(
        int(trips[str(area["id"])].cost_won) * int(area["simulated_monthly_demand"])
        for area in areas
    )
    model.minimize(sum(provider_pay) + hub_travel_cost)
    solver = _new_solver()
    status = solver.solve(model)
    if status == cp_model.INFEASIBLE:
        return None, "INFEASIBLE", "PROVIDER_CAPACITY_OR_SERVICE_MIX"
    if status != cp_model.OPTIMAL:
        return None, "NOT_PROVEN", "OPTIMALITY_NOT_PROVEN"
    return int(solver.value(sum(provider_pay)) + hub_travel_cost), "CALCULATED", None


def evaluate_scenarios(
    areas: list[dict[str, Any]],
    providers: list[dict[str, Any]],
    connection: sqlite3.Connection,
    budget: int,
    policy: PlanningPolicy | None = None,
) -> dict[str, Any]:
    validate_input(areas, providers, budget)
    policy = policy or PlanningPolicy()
    _validate_policy(policy)
    hub_id, trips = derive_trip_costs(areas, connection)
    results = {
        scenario: _solve_scenario(areas, providers, trips, budget, scenario, policy)
        for scenario in ("efficiency", "balanced", "minimum_coverage")
    }
    guarantee_failure_reason = _minimum_guarantee_failure_reason(areas, providers, trips, policy)
    full_demand_budget, full_demand_status, full_demand_reason = _full_demand_required_budget(
        areas, providers, trips, policy
    )
    required_budget = (
        minimum_guarantee_budget(areas, providers, trips, policy)
        if guarantee_failure_reason is None
        else None
    )
    minimum = results["minimum_coverage"]
    minimum["guarantee_scope"] = "MONTHLY_AGGREGATE_CAPACITY_ESTIMATE"
    minimum["guarantee_travel_model"] = "CENTRAL_HUB_ROUND_TRIP_ESTIMATE"
    for result in results.values():
        result.update(
            {
                "full_demand_required_budget_won": full_demand_budget,
                "full_demand_budget_gap_won": (
                    max(0, full_demand_budget - budget) if full_demand_budget is not None else None
                ),
                "full_demand_budget_status": full_demand_status,
                "full_demand_failure_reason": full_demand_reason,
                "full_demand_budget_model": "CENTRAL_HUB_ROUND_TRIP_ESTIMATE",
            }
        )
    if required_budget is None and guarantee_failure_reason is None:
        guarantee_failure_reason = "GUARANTEE_COST_NOT_PROVEN"
    minimum["guarantee_capacity_feasible"] = (
        False
        if guarantee_failure_reason in {"PROVIDER_CAPACITY", "PROVIDER_CAPACITY_OR_SERVICE_MIX"}
        else None
        if guarantee_failure_reason is not None
        else True
    )
    minimum["guarantee_feasible"] = guarantee_failure_reason is None
    minimum["guarantee_failure_reason"] = guarantee_failure_reason
    minimum["required_capacity"] = policy.minimum_services_per_area * len(areas)
    minimum["available_capacity"] = sum(
        int(provider["capacity_per_month"]) for provider in providers
    )
    minimum["missing_capacity"] = max(
        0, minimum["required_capacity"] - minimum["available_capacity"]
    )
    if required_budget is not None:
        minimum["required_budget_won"] = required_budget
        minimum["additional_budget_won"] = max(0, required_budget - budget)
        minimum["budget_gap_won"] = max(0, required_budget - budget)
        minimum["additional_public_subsidy_won"] = max(0, required_budget - budget)
    else:
        minimum["additional_budget_won"] = None
        minimum["budget_gap_won"] = None
    efficiency = results["efficiency"]
    minimum["travel_time_added_vs_efficiency_s"] = (
        minimum["travel_time_s"] - efficiency["travel_time_s"]
    )
    return {
        "region": "홍성군 장곡면",
        "budget_won": budget,
        "planning_policy": {
            "minimum_services_per_area": policy.minimum_services_per_area,
            "elderly_priority_weight": policy.elderly_priority_weight,
            "single_elderly_household_priority_weight": (
                policy.single_elderly_household_priority_weight
            ),
            "survey_required_protection_weight": policy.survey_required_protection_weight,
            "maximum_round_trip_travel_minutes": policy.maximum_round_trip_travel_minutes,
            "allowed_services": list(policy.allowed_services),
            "minimum_provider_compensation_won": policy.minimum_provider_compensation_won,
        },
        "hub_area_id": hub_id,
        "travel_source": "Kakao Mobility road distance/time, directed routes cached in SQLite",
        "request_count_baseline": _request_count_baseline(areas, providers, trips, budget),
        "scenario_results": results,
    }
