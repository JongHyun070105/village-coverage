"""Stage A of the decomposed planner: aggregate provider x area allocation (V4 §30).

The time-indexed schedule (provider x area x date) is relaxed to one integer
per provider-area pair:

* visits(p, a) <= number of eligible dates for that pair (one visit per date);
* a provider's total work minutes <= the sum of its daily working minutes;
* monthly round limits and compensation floors are summed over the horizon;
* travel uses the conservative independent round trip of each pair.

Every time-indexed plan maps to a feasible aggregate solution with the same
objective components, so the aggregate optimum is an upper bound for the
round-trip-cost model. If stage B realizes exactly the aggregate optimum's
components, the final plan is provably optimal for that model. Nothing here
proves optimality of multi-stop routing; that remains a post-solve improvement.
"""

from __future__ import annotations

import time
from collections import defaultdict
from typing import Any

from ortools.sat.python import cp_model

from backend.optimization import (
    SERVICE_COST_WON,
    _lexicographic_score,
    _underserved_points,
    _vulnerability_points,
)
from backend.settings import PlanningPolicy

BALANCED_WEIGHTS_KEYS = (
    "service_volume",
    "area_coverage",
    "survey_protection",
    "vulnerability",
    "underserved",
    "concentration",
    "travel_cost",
)
BASIS = 10_000
ALLOCATION_WORKERS = 8
DETERMINISTIC_WALL_CAP_FACTOR = 3.0


BALANCED_SCALE = 10_000


def balanced_linear_score(
    *,
    weights: dict[str, int],
    policy: PlanningPolicy,
    total_units: Any,
    max_units: int,
    covered_count: Any,
    area_count: int,
    survey_count: Any,
    max_survey: int,
    vulnerability: Any,
    max_vulnerability: int,
    concentration: Any,
    travel_cost: Any,
    max_travel_cost: int,
    underserved: Any = 0,
    max_underserved: int = 0,
) -> tuple[Any, int]:
    """Exact weighted sum of normalized components with integer coefficients.

    Each component contributes ``weight x strength x (value / maximum)`` in basis
    points. Coefficients are pre-scaled integers (no per-component flooring), so
    the objective stays linear; both planning stages share this definition.
    """
    survey_strength = policy.survey_required_protection_weight
    vulnerability_strength = min(
        1000, policy.elderly_priority_weight + policy.single_elderly_household_priority_weight
    )
    parts = (
        (weights["service_volume"], total_units, max_units, 1000),
        (weights["area_coverage"], covered_count, area_count, 1000),
        (weights["survey_protection"], survey_count, max_survey, survey_strength or 1000),
        (weights["vulnerability"], vulnerability, max_vulnerability,
         vulnerability_strength or 1000),
        (weights.get("underserved", 0), underserved, max_underserved, 1000),
        (weights["concentration"], BASIS - concentration, BASIS, 1000),
        (weights["travel_cost"], max_travel_cost - travel_cost, max_travel_cost, 1000),
    )
    terms = []
    maximum_score = 0
    for weight, numerator, maximum, strength in parts:
        if weight <= 0 or maximum <= 0:
            continue
        coefficient = weight * BASIS * BALANCED_SCALE * strength // (1000 * maximum)
        terms.append(coefficient * numerator)
        maximum_score += coefficient * maximum
    return sum(terms), maximum_score


def objective_maxima(candidates: list[dict[str, Any]], areas: list[dict[str, Any]]
                     ) -> dict[str, int]:
    """Normalization constants of the full time-indexed model (shared by both stages)."""
    return {
        "max_units": sum(max(0, int(a.get("simulated_monthly_demand", 0))) for a in areas),
        "max_travel_cost": sum(c["route"]["cost_won"] for c in candidates),
        "max_travel_time": sum(c["route"]["duration_s"] for c in candidates),
        "max_provider_days": len({(c["provider_id"], c["scheduled_date"]) for c in candidates}),
        "opted_in_candidates": sum(c["participation_status"] == "OPTED_IN" for c in candidates),
    }


def solve_aggregate_allocation(
    *,
    areas: list[dict[str, Any]],
    providers: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    budget_won: int,
    scenario: str,
    policy: PlanningPolicy,
    balanced_weights: dict[str, int],
    max_seconds: float,
    warm_start_targets: dict[tuple[str, str], dict[str, int]] | None = None,
    monthly_capacity_limits: dict[tuple[str, str], int] | None = None,
) -> dict[str, Any]:
    maxima = objective_maxima(candidates, areas)
    pairs: dict[tuple[str, str], dict[str, Any]] = {}
    provider_dates: dict[str, dict[str, int]] = defaultdict(dict)
    provider_months: dict[str, set[str]] = defaultdict(set)
    for c in candidates:
        key = (str(c["provider_id"]), str(c["area_id"]))
        pair = pairs.setdefault(key, {
            "dates": set(), "dates_by_month": defaultdict(set), "opted_dates": set(),
            "cap": 0, "cost": None, "time": None,
            "work": None, "service_type": c["service_type"],
        })
        pair["dates"].add(c["scheduled_date"])
        pair["dates_by_month"][str(c["month"])].add(str(c["scheduled_date"]))
        if c["participation_status"] == "OPTED_IN":
            pair["opted_dates"].add(c["scheduled_date"])
        pair["cap"] = max(pair["cap"], int(c["service_capacity"]))
        # Minimum over dates keeps the relaxation valid if a leg differs by date.
        pair["cost"] = min(pair["cost"] or 10**12, int(c["route"]["cost_won"]))
        pair["time"] = min(pair["time"] or 10**12, int(c["route"]["duration_s"]))
        pair["work"] = min(pair["work"] or 10**12, int(c["estimated_work_minutes"]))
        day_minutes = min(
            int(float(c["max_daily_hours"]) * 60),
            _minute(c["availability_end"]) - _minute(c["availability_start"]),
        )
        dates = provider_dates[key[0]]
        # Several windows on one date add up, capped by the provider's daily hours.
        window_key = (c["scheduled_date"], c["availability_start"], c["availability_end"])
        dates.setdefault(window_key, day_minutes)
        provider_months[key[0]].add(c["month"])

    model = cp_model.CpModel()
    lookup = {str(p["provider_id"]): p for p in providers}
    x: dict[tuple[str, str], Any] = {}
    x_month: dict[tuple[str, str, str], Any] = {}
    u: dict[tuple[str, str], Any] = {}
    o: dict[tuple[str, str], Any] = {}
    x_upper: dict[tuple[str, str], int] = {}
    for key, pair in pairs.items():
        provider_id, area_id = key
        area = next(a for a in areas if str(a["id"]) == area_id)
        demand = max(0, int(area.get("simulated_monthly_demand", 0)))
        upper = min(len(pair["dates"]), demand)
        x_upper[key] = upper
        x[key] = model.new_int_var(0, upper, f"x_{provider_id}_{area_id}")
        u[key] = model.new_int_var(0, upper * pair["cap"], f"u_{provider_id}_{area_id}")
        model.add(u[key] >= x[key])
        model.add(u[key] <= pair["cap"] * x[key])
        o[key] = model.new_int_var(0, min(upper, len(pair["opted_dates"])), f"o_{key}")
        model.add(o[key] <= x[key])
        monthly_vars = []
        for month, dates in sorted(pair["dates_by_month"].items()):
            month_key = (provider_id, area_id, month)
            x_month[month_key] = model.new_int_var(
                0, min(len(dates), demand), f"x_{provider_id}_{area_id}_{month}"
            )
            monthly_vars.append(x_month[month_key])
        model.add(sum(monthly_vars) == x[key])

    by_area: dict[str, list[tuple[str, str]]] = defaultdict(list)
    by_provider: dict[str, list[tuple[str, str]]] = defaultdict(list)
    by_provider_month: dict[tuple[str, str], list[Any]] = defaultdict(list)
    for key in pairs:
        by_area[key[1]].append(key)
        by_provider[key[0]].append(key)
    for (provider_id, _area_id, month), variable in x_month.items():
        by_provider_month[(provider_id, month)].append(variable)
    for area in areas:
        area_id = str(area["id"])
        model.add(sum(u[k] for k in by_area[area_id]) <= max(0, int(
            area.get("simulated_monthly_demand", 0))))

    pay_vars = []
    for provider_id, keys in by_provider.items():
        provider = lookup[provider_id]
        months = len(provider_months[provider_id])
        model.add(sum(x[k] for k in keys) <= int(provider["max_monthly_rounds"]) * months)
        per_date: dict[str, int] = defaultdict(int)
        for (day, _start, _end), minutes in provider_dates[provider_id].items():
            per_date[day] += minutes
        daily_minutes = sum(
            min(total, int(float(provider["max_daily_hours"]) * 60))
            for total in per_date.values()
        )
        model.add(sum(pairs[k]["work"] * x[k] for k in keys) <= daily_minutes)
        for (monthly_provider_id, month), variables in by_provider_month.items():
            if monthly_provider_id != provider_id:
                continue
            capacity = (
                (monthly_capacity_limits or {}).get((provider_id, month))
                if monthly_capacity_limits is not None
                else None
            )
            if capacity is None:
                capacity = int(provider["max_monthly_rounds"])
            model.add(sum(variables) <= max(0, int(capacity)))
        active = model.new_bool_var(f"active_{provider_id}")
        for k in keys:
            model.add(x[k] <= len(pairs[k]["dates"]) * active)
        model.add(active <= sum(x[k] for k in keys))
        floor = max(int(provider["minimum_compensation_won"]),
                    policy.minimum_provider_compensation_won)
        service_cost = sum(u[k] * SERVICE_COST_WON[pairs[k]["service_type"]] for k in keys)
        max_cost = sum(pairs[k]["cap"] * len(pairs[k]["dates"])
                       * SERVICE_COST_WON[pairs[k]["service_type"]] for k in keys)
        pay = model.new_int_var(0, max(max_cost, floor), f"pay_{provider_id}")
        model.add(pay >= service_cost)
        model.add(pay >= floor * active)  # one floor: a valid lower bound on monthly floors
        pay_vars.append(pay)

    travel_cost_expr = sum(pairs[k]["cost"] * x[k] for k in pairs)
    travel_time_expr = sum(pairs[k]["time"] * x[k] for k in pairs)
    travel_cost = model.new_int_var(0, max(maxima["max_travel_cost"], 0), "travel_cost")
    model.add(travel_cost == travel_cost_expr)
    travel_time = model.new_int_var(0, max(maxima["max_travel_time"], 0), "travel_time")
    model.add(travel_time == travel_time_expr)
    total_cost = model.new_int_var(0, budget_won, "total_cost")
    model.add(total_cost == sum(pay_vars) + travel_cost)

    covered: dict[str, Any] = {}
    met: dict[str, Any] = {}
    for area in areas:
        area_id = str(area["id"])
        keys = by_area[area_id]
        covered[area_id] = model.new_bool_var(f"covered_{area_id}")
        visits = sum(x[k] for k in keys)
        if keys:
            model.add(visits >= covered[area_id])
            # Disaggregated linking (one row per pair) gives a much tighter LP bound
            # than a single big-M row over the area's whole candidate count.
            for k in keys:
                model.add(x[k] <= x_upper[k] * covered[area_id])
        else:
            model.add(covered[area_id] == 0)
        met[area_id] = model.new_bool_var(f"met_{area_id}")
        minimum_required = max(
            0,
            int(area.get("minimum_services_remaining", policy.minimum_services_per_area)),
        )
        demand_ok = int(area.get("simulated_monthly_demand", 0)) >= minimum_required
        if minimum_required == 0:
            model.add(met[area_id] == 1)
        elif keys and demand_ok:
            model.add(visits >= minimum_required * met[area_id])
            model.add(met[area_id] <= covered[area_id])
        else:
            model.add(met[area_id] == 0)

    total_units = model.new_int_var(0, maxima["max_units"], "total_units")
    model.add(total_units == sum(u.values()))
    covered_count = model.new_int_var(0, len(areas), "covered_count")
    model.add(covered_count == sum(covered.values()))
    survey_weight = policy.survey_required_protection_weight
    max_survey = survey_weight * sum(bool(a.get("needs_survey")) for a in areas)
    survey_count = model.new_int_var(0, max_survey, "survey_count")
    model.add(survey_count == sum(survey_weight * covered[str(a["id"])]
                                  for a in areas if a.get("needs_survey")))
    vuln_points = {
        str(a["id"]): _vulnerability_points(
            a, policy.elderly_priority_weight, policy.single_elderly_household_priority_weight)
        for a in areas
    }
    max_vulnerability = sum(vuln_points.values())
    vulnerability = model.new_int_var(0, max_vulnerability, "vulnerability")
    model.add(vulnerability == sum(vuln_points[a] * covered[a] for a in covered))
    underserved_points = {str(a["id"]): _underserved_points(a) for a in areas}
    max_underserved = sum(underserved_points.values())
    underserved = model.new_int_var(0, max_underserved, "underserved")
    model.add(underserved == sum(underserved_points[a] * covered[a] for a in covered))
    met_count = sum(met.values())
    opted = sum(o.values())

    components: list[tuple[Any, int, bool]]
    concentration = None
    if scenario == "required_budget":
        # Minimum guarantee cost: every area must reach the minimum frequency.
        for area_met in met.values():
            model.add(area_met == 1)
        components = [(total_cost, budget_won, False)]
    elif scenario == "efficiency":
        components = [(total_units, maxima["max_units"], True),
                      (travel_cost, maxima["max_travel_cost"], False),
                      (travel_time, maxima["max_travel_time"], False)]
    elif scenario == "underserved_first":
        components = [(underserved, max_underserved, True),
                      (covered_count, len(areas), True),
                      (total_units, maxima["max_units"], True),
                      (travel_cost, maxima["max_travel_cost"], False),
                      (travel_time, maxima["max_travel_time"], False)]
    elif scenario == "minimum_coverage":
        components = [(met_count, len(areas), True), (covered_count, len(areas), True),
                      (total_units, maxima["max_units"], True), (total_cost, budget_won, False)]
    else:
        concentration = model.new_int_var(0, BASIS, "concentration")
        for area in areas:
            area_id = str(area["id"])
            demand = max(0, int(area.get("simulated_monthly_demand", 0)))
            if demand:
                saturation = model.new_int_var(0, BASIS, f"sat_{area_id}")
                model.add(saturation * demand >= sum(u[k] for k in by_area[area_id]) * BASIS)
                model.add(concentration >= saturation)
        score, max_score = balanced_linear_score(
            weights=balanced_weights,
            policy=policy,
            total_units=total_units,
            max_units=maxima["max_units"],
            covered_count=covered_count,
            area_count=len(areas),
            survey_count=survey_count,
            max_survey=max_survey,
            vulnerability=vulnerability,
            max_vulnerability=max_vulnerability,
            concentration=concentration,
            travel_cost=travel_cost,
            max_travel_cost=maxima["max_travel_cost"],
            underserved=underserved,
            max_underserved=max_underserved,
        )
        components = [(score, max_score, True)]
    if maxima["opted_in_candidates"] and scenario != "required_budget":
        components.append((opted, maxima["opted_in_candidates"], True))

    # Sequential lexicographic solve: optimize one component, fix it, continue.
    # Each stage has a small objective, so CP-SAT proves bounds far faster than
    # with one composite score whose coefficients span many orders of magnitude.
    # The final model then fixes every component at its proven optimum.
    _lexicographic_score(components)  # validates bounds exactly as the full model does
    started = time.monotonic()
    solver = None
    status = cp_model.UNKNOWN
    all_proven = True
    hint: dict[Any, int] = {}
    for key, target in (warm_start_targets or {}).items():
        if key not in x:
            continue
        visits = int(target.get("visits", 0))
        units = int(target.get("units", 0))
        if 0 <= visits <= x_upper[key] and 0 <= units <= x_upper[key] * pairs[key]["cap"]:
            hint[x[key]] = visits
            hint[u[key]] = units
    deterministic_used = 0.0
    worker_count = 1 if warm_start_targets else ALLOCATION_WORKERS
    for expression, _maximum, maximize in components:
        remaining = max_seconds - deterministic_used
        if remaining <= 0.01:
            all_proven = False
            break
        if maximize:
            model.maximize(expression)
        else:
            model.minimize(expression)
        stage = cp_model.CpSolver()
        # Deterministic-time budget keeps results independent of machine load; the
        # wall-clock cap is only a safety net (see DETERMINISTIC_WALL_CAP_FACTOR).
        stage.parameters.max_deterministic_time = remaining
        stage.parameters.max_time_in_seconds = remaining * DETERMINISTIC_WALL_CAP_FACTOR
        stage.parameters.num_search_workers = worker_count
        stage.parameters.random_seed = 2026
        if worker_count > 1:
            # Deterministic parallel portfolio: reproducible for identical inputs.
            stage.parameters.interleave_search = True
        model.clear_hints()
        if worker_count == 1:
            # Hints are unsafe with interleaved parallel search (OR-Tools CHECK
            # failure), so they are only used on the single-worker path.
            for var, value in hint.items():
                model.add_hint(var, value)
        stage_status = stage.solve(model)
        deterministic_used += stage.deterministic_time
        if stage_status not in {cp_model.OPTIMAL, cp_model.FEASIBLE}:
            all_proven = False
            break
        solver, status = stage, stage_status
        hint = {var: stage.value(var) for var in (*x.values(), *u.values(), *o.values())}
        if stage_status != cp_model.OPTIMAL:
            all_proven = False
            break
        model.add(expression == stage.value(expression))
    wall_ms = round((time.monotonic() - started) * 1000, 2)
    if solver is None:
        return {"status": "UNKNOWN", "targets": {}, "components": None, "wall_ms": wall_ms,
                "deterministic_time": round(deterministic_used, 4)}
    targets = {
        key: {"visits": solver.value(x[key]), "units": solver.value(u[key])}
        for key in pairs if solver.value(x[key]) > 0
    }
    component_values = {
        "total_units": solver.value(total_units),
        "covered_count": solver.value(covered_count),
        "survey_count": solver.value(survey_count),
        "vulnerability": solver.value(vulnerability),
        "underserved": solver.value(underserved),
        "travel_cost": solver.value(travel_cost),
        "travel_time": solver.value(travel_time),
        "met_count": int(sum(solver.value(v) for v in met.values())),
        "opted_in": int(sum(solver.value(v) for v in o.values())),
        "concentration": solver.value(concentration) if concentration is not None else None,
        "total_cost": solver.value(total_cost),
    }
    return {
        "status": "OPTIMAL" if all_proven and status == cp_model.OPTIMAL else "FEASIBLE",
        "targets": targets,
        "components": component_values,
        "maxima": maxima,
        "pair_count": len(pairs),
        "variable_count": len(model.proto.variables),
        "constraint_count": len(model.proto.constraints),
        "wall_ms": wall_ms,
        "deterministic_time": round(deterministic_used, 4),
        "branches": int(solver.num_branches),
    }


def _minute(value: str) -> int:
    hours, minutes = value.split(":")
    return int(hours) * 60 + int(minutes)
