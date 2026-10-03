#!/usr/bin/env python3
"""VillageCoverage deterministic scale and adversarial stress framework.

Generates synthetic stress scenarios across scales [16, 30, 50, 100, 200] areas,
[3, 5, 10, 20] providers, with legacy A~J variants and an optional V4 stratified
100-case matrix. All route edges and scenario demand are synthetic.
Verifies schedule, routing, resource, and solver invariants and writes results to
artifacts/stress_test_results.json & .csv.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
import sys
import time
from dataclasses import asdict
from datetime import datetime
from itertools import product
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend import scheduling  # noqa: E402
from backend.scheduling import PlanningPolicy  # noqa: E402
from backend.travel import PRIORITY, ROUTING_VERSION, cache_key, connect  # noqa: E402

REFERENCE_SEED = 20261002
SERVICES = ("laundry", "daily_necessities", "home_repair")
DAYS_OF_WEEK = ("monday", "tuesday", "wednesday", "thursday", "friday")
VARIANT_LABELS = {
    "A": "NORMAL",
    "B": "TIGHT_BUDGET",
    "C": "TIGHT_PROVIDER_CAPACITY",
    "D": "TIGHT_AVAILABILITY",
    "E": "HIGH_DEMAND",
    "F": "HIGH_LOW_DATA_RATIO",
    "G": "MISSING_5_PERCENT_ROUTE_EDGES",
    "H": "MISSING_20_PERCENT_ROUTE_EDGES",
    "I": "ONE_MAJOR_PROVIDER_UNAVAILABLE",
    "J": "MULTIPLE_PROVIDERS_UNAVAILABLE",
}
V4_STRESS_PROFILES: tuple[dict[str, Any], ...] = (
    {"name": "BASELINE", "budget_tier": "normal", "participation_rate": 1.0,
     "route_missing_rate": 0.0, "low_data_rate": 0.25},
    {"name": "TIGHT_MIXED", "budget_tier": "tight", "participation_rate": 0.75,
     "route_missing_rate": 0.05, "low_data_rate": 0.50},
    {"name": "HIGH_POOR", "budget_tier": "high", "participation_rate": 0.50,
     "route_missing_rate": 0.20, "low_data_rate": 0.80},
    {"name": "ZERO_BUDGET_NO_SUPPLY_LOW_DATA", "budget_tier": "zero",
     "participation_rate": 0.0, "route_missing_rate": 0.0, "low_data_rate": 1.0},
    {"name": "WRONG_SERVICE_REMOTE_EQUAL_DEMAND", "budget_tier": "normal",
     "participation_rate": 1.0, "route_missing_rate": 0.05, "low_data_rate": 0.50,
     "wrong_service_only": True, "single_remote_area": True,
     "same_demand_for_all_areas": True, "same_demand_units": 1},
)


def build_v4_stratified_matrix() -> list[tuple[int, int, int, dict[str, Any]]]:
    """Return 100 reproducible area/provider/profile cases without a full cross-product."""
    cases = []
    seed_index = 0
    for areas, providers in product((16, 30, 50, 100, 200), (3, 5, 10, 20)):
        for profile in V4_STRESS_PROFILES:
            seed_index += 1
            cases.append((areas, providers, REFERENCE_SEED + seed_index, dict(profile)))
    return cases


def _time_minutes(value: str) -> int:
    parsed = datetime.strptime(value, "%H:%M")
    return parsed.hour * 60 + parsed.minute


def generate_scenario_data(
    num_areas: int,
    num_providers: int,
    variant: str,
    seed: int,
    db_path: Path,
    *,
    profile: dict[str, Any] | None = None,
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    Any,
    int,
    PlanningPolicy,
    bool,
    dict[str, Any],
]:
    """Build synthetic areas, providers, road matrix in SQLite, budget, and policy."""
    profile = profile or {}
    rng = random.Random(seed + num_areas * 1000 + num_providers * 10)
    connection = connect(db_path)

    # Base center: Chungnam Hongseong / Buyeo approx
    center_lat = 36.50
    center_lng = 126.65

    # 1. Generate Areas
    areas: list[dict[str, Any]] = []
    for i in range(num_areas):
        area_id = f"area-{i:03d}"
        if variant == "I" and i >= int(num_areas * 0.7):
            # Remote cluster ~35-50km away
            angle = rng.uniform(0, 2 * math.pi)
            dist_km = rng.uniform(35.0, 50.0)
        else:
            angle = rng.uniform(0, 2 * math.pi)
            dist_km = rng.uniform(2.0, 20.0)

        lat = center_lat + (dist_km / 111.0) * math.cos(angle)
        cos_center = math.cos(math.radians(center_lat))
        lng = center_lng + (dist_km / (111.0 * cos_center)) * math.sin(angle)

        base_demand = rng.randint(1, 3)
        if variant == "E":
            base_demand = max(1, int(base_demand * 2.5))

        service_type = SERVICES[i % len(SERVICES)]
        low_data_rate = float(profile.get("low_data_rate", 0.80 if variant == "F" else 0.25))
        needs_survey = rng.random() < low_data_rate
        if profile.get("same_demand_for_all_areas"):
            base_demand = int(profile.get("same_demand_units", 1))
        pop_total = rng.randint(50, 400)
        elderly_ratio = rng.uniform(0.25, 0.65)
        single_elderly = int(pop_total * elderly_ratio * rng.uniform(0.2, 0.5))

        area: dict[str, Any] = {
            "id": area_id,
            "name": f"마을-{i:03d}",
            "service_type": service_type,
            "simulated_monthly_demand": max(1, base_demand),
            "needs_survey": needs_survey,
            "population_total": pop_total,
            "elderly_ratio_65": round(elderly_ratio, 3),
            "single_households_65_plus": single_elderly,
            "anchor_lat": lat,
            "anchor_lng": lng,
            "service_duration_minutes": 45,
        }

        if variant == "D":
            area["requested_service_windows"] = [
                {
                    "desired_time": "10:00",
                    "window_start": "10:00",
                    "window_end": "11:00",
                }
            ]
        if profile.get("single_remote_area") and i == num_areas - 1:
            remote_angle = rng.uniform(0, 2 * math.pi)
            remote_km = 45.0
            area["anchor_lat"] = center_lat + (remote_km / 111.0) * math.cos(remote_angle)
            area["anchor_lng"] = center_lng + (
                remote_km / (111.0 * math.cos(math.radians(center_lat)))
            ) * math.sin(remote_angle)
        areas.append(area)

    # 2. Generate Providers
    providers: list[dict[str, Any]] = []
    depot_nodes: list[dict[str, Any]] = []
    for j in range(num_providers):
        p_id = f"provider-{j:02d}"
        depot_id = f"depot-{j:02d}"
        # Depot placed near center
        d_angle = rng.uniform(0, 2 * math.pi)
        d_dist = rng.uniform(1.0, 8.0)
        d_lat = center_lat + (d_dist / 111.0) * math.cos(d_angle)
        cos_center = math.cos(math.radians(center_lat))
        d_lng = center_lng + (d_dist / (111.0 * cos_center)) * math.sin(d_angle)
        depot_node = {"id": depot_id, "anchor_lat": d_lat, "anchor_lng": d_lng}
        depot_nodes.append(depot_node)

        # Services supported
        if j % 3 == 0:
            supp = ["laundry", "daily_necessities"]
        elif j % 3 == 1:
            supp = ["daily_necessities", "home_repair"]
        else:
            supp = ["laundry", "home_repair"]
        if profile.get("wrong_service_only"):
            supp = ["unrelated_service"]
        if profile.get("dominant_provider") and j == 0:
            supp = list(SERVICES)

        max_rounds = 12
        service_cap = 3
        if variant == "C":
            # Tight capacity
            max_rounds = rng.randint(2, 4)
            service_cap = 2
        if profile.get("dominant_provider") and j == 0:
            max_rounds = max(max_rounds, num_areas * 3)

        # Realistic mobile outreach availability: 2-3 specific weekdays per provider
        schedule_patterns = [
            ["monday", "wednesday", "friday"],
            ["tuesday", "thursday"],
            ["monday", "thursday"],
            ["tuesday", "friday"],
            ["wednesday", "friday"],
        ]
        chosen_days = schedule_patterns[j % len(schedule_patterns)]
        availability_start = "09:00"
        availability_end = "18:00"
        if variant == "D":
            chosen_days = chosen_days[:1]
            availability_start = "10:00"
            availability_end = "13:00"
        if "participation_rate" in profile:
            active_count = round(num_providers * float(profile["participation_rate"]))
            unavailable_count = num_providers - active_count
            provider_unavailable = j >= active_count
        else:
            unavailable_count = 1 if variant == "I" else 2 if variant == "J" else 0
            provider_unavailable = j < min(unavailable_count, num_providers)
        if provider_unavailable:
            chosen_days = []
        provider = {
            "provider_id": p_id,
            "name": f"공급업체-{j:02d}",
            "base_area_id": depot_id,
            "supported_services": supp,
            "availability": [
                {
                    "weekday": d,
                    "start_time": availability_start,
                    "end_time": availability_end,
                }
                for d in chosen_days
            ],
            "max_monthly_rounds": max_rounds,
            "service_capacity": service_cap,
            "max_daily_hours": 7.0,
            "max_travel_time_minutes": 90,
            "minimum_compensation_won": 1_000_000,
            "provider_unavailable": provider_unavailable,
        }
        providers.append(provider)

    # 3. Populate travel matrix in SQLite
    all_nodes = [
        {"id": a["id"], "anchor_lat": a["anchor_lat"], "anchor_lng": a["anchor_lng"]}
        for a in areas
    ] + depot_nodes

    def calc_travel(lat1, lng1, lat2, lng2) -> tuple[int, int]:
        # Haversine distance in km * 1.35 winding factor
        dlat = math.radians(lat2 - lat1)
        dlng = math.radians(lng2 - lng1)
        cos_prod = math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
        a_geo = math.sin(dlat / 2) ** 2 + cos_prod * math.sin(dlng / 2) ** 2
        c_geo = 2 * math.atan2(math.sqrt(a_geo), math.sqrt(1 - a_geo))
        straight_km = 6371.0 * c_geo
        road_km = max(0.5, straight_km * 1.35)
        dist_m = int(road_km * 1000)
        # Average speed 45 km/h -> 750 m/min -> 12.5 m/s
        dur_s = max(60, int(dist_m / 12.5))
        return dist_m, dur_s

    # Register routes
    # All generated edges are synthetic stress fixtures, not live road measurements.
    default_edge_drop_rate = {"G": 0.05, "H": 0.20}.get(variant, 0.0)
    edge_drop_rate = float(profile.get("route_missing_rate", default_edge_drop_rate))
    inter_area_edges = [
        (origin["id"], destination["id"])
        for origin in areas
        for destination in areas
        if origin["id"] != destination["id"]
    ]
    missing_edge_count = round(len(inter_area_edges) * edge_drop_rate)
    missing_edge_pairs = set(rng.sample(inter_area_edges, missing_edge_count))
    allow_route_fallback = edge_drop_rate > 0
    route_rows: list[tuple[Any, ...]] = []

    fetched_at = "2026-10-02T00:00:00+00:00"
    for origin in all_nodes:
        for dest in all_nodes:
            if origin["id"] == dest["id"]:
                continue
            if (origin["id"], dest["id"]) in missing_edge_pairs:
                continue
            dist_m, dur_s = calc_travel(
                origin["anchor_lat"], origin["anchor_lng"], dest["anchor_lat"], dest["anchor_lng"]
            )
            route_rows.append(
                (
                    cache_key(origin, dest),
                    origin["id"],
                    dest["id"],
                    float(origin["anchor_lng"]),
                    float(origin["anchor_lat"]),
                    float(dest["anchor_lng"]),
                    float(dest["anchor_lat"]),
                    ROUTING_VERSION,
                    PRIORITY,
                    dist_m,
                    dur_s,
                    fetched_at,
                )
            )

    connection.executemany(
        """INSERT INTO travel_matrix(
               cache_key, origin_id, destination_id, origin_x, origin_y,
               destination_x, destination_y, routing_version, priority,
               distance_m, duration_s, fetched_at
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        route_rows,
    )
    connection.commit()

    # 4. Budget calculation
    estimated_needed = num_areas * 200_000
    budget_tier = str(profile.get("budget_tier", "tight" if variant == "B" else "normal"))
    if budget_tier == "zero":
        budget_won = 0
    elif budget_tier == "tight":
        # Tight budget: 40% of needed
        budget_won = int(estimated_needed * 0.40)
    elif budget_tier == "high":
        budget_won = int(estimated_needed * 2.0)
    else:
        budget_won = int(estimated_needed * 1.50)

    policy = PlanningPolicy(minimum_services_per_area=1)
    metadata = {
        "variation": VARIANT_LABELS[variant],
        "route_missing_edges": missing_edge_count,
        "route_fallback_allowed": allow_route_fallback,
        "unavailable_provider_ids": [
            provider["provider_id"]
            for provider in providers
            if provider["provider_unavailable"]
        ],
        "low_data_area_count": sum(bool(area["needs_survey"]) for area in areas),
        "matrix_profile": profile.get("name"),
        "budget_tier": budget_tier,
        "requested_participation_rate": profile.get("participation_rate", 1.0),
        "observed_participation_rate": round(
            sum(not provider["provider_unavailable"] for provider in providers) / len(providers), 4
        ) if providers else 0.0,
        "evidence_low_data_rate": low_data_rate,
        "route_missing_rate": edge_drop_rate,
        "service_support_mode": (
            "WRONG_SERVICE_ONLY" if profile.get("wrong_service_only") else "NORMAL"
        ),
    }
    return areas, providers, connection, budget_won, policy, allow_route_fallback, metadata


def deterministic_scenario_fingerprint(
    areas: list[dict[str, Any]],
    providers: list[dict[str, Any]],
    budget_won: int,
    policy: PlanningPolicy,
    connection: Any,
    *,
    seed: int,
    variant: str,
) -> str:
    """Fingerprint the complete deterministic synthetic input, including directed edges."""
    route_snapshot = [
        list(row)
        for row in connection.execute(
            """SELECT origin_id, destination_id, distance_m, duration_s
               FROM travel_matrix ORDER BY origin_id, destination_id"""
        ).fetchall()
    ]
    payload = {
        "seed": seed,
        "variant": variant,
        "areas": areas,
        "providers": providers,
        "budget_won": budget_won,
        "policy": asdict(policy),
        "route_matrix": route_snapshot,
    }
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def verify_invariants(
    result: dict[str, Any],
    areas: list[dict[str, Any]],
    providers: list[dict[str, Any]],
    budget_won: int,
    connection: Any,
    *,
    allow_route_fallback: bool,
) -> dict[str, Any]:
    """Verify schedule, solver, and exact directed-road invariants."""
    violations: list[str] = []
    spent = int(result.get("budget_spent_won", 0))
    if spent < 0 or spent > budget_won:
        violations.append(f"BUDGET_OUT_OF_RANGE: spent {spent}, budget {budget_won}")

    provider_lookup = {p["provider_id"]: p for p in providers}
    area_lookup = {str(area["id"]): area for area in areas}
    roads = {
        (str(origin), str(destination)): (int(distance), int(duration))
        for origin, destination, distance, duration in connection.execute(
            "SELECT origin_id, destination_id, distance_m, duration_s FROM travel_matrix"
        ).fetchall()
    }
    route_duration_by_group = {
        (str(route["provider_id"]), str(route["scheduled_date"]), str(route["route_group_key"])):
        int(route["duration_s"])
        for route in result.get("routes", [])
        if route.get("route_group_key") is not None
        and route.get("duration_s") is not None
    }
    rounds_by_provider: dict[str, int] = {}
    work_by_provider_date: dict[tuple[str, str], int] = {}
    served_by_area: dict[str, int] = {}
    observed_served_units = 0
    for round_item in result.get("rounds", []):
        provider_id = str(round_item.get("provider_id", ""))
        area_id = str(round_item.get("area_id", ""))
        provider = provider_lookup.get(provider_id)
        area = area_lookup.get(area_id)
        if provider is None or area is None:
            violations.append(f"UNSUPPORTED_ASSIGNMENT_REFERENCE: {provider_id}/{area_id}")
            continue

        if provider.get("provider_unavailable", False):
            violations.append(f"PROVIDER_UNAVAILABLE_ASSIGNED: {provider_id}/{area_id}")

        rounds_by_provider[provider_id] = rounds_by_provider.get(provider_id, 0) + 1
        units = int(round_item.get("service_units", 0))
        if "service_capacity" in provider and units > int(provider["service_capacity"]):
            violations.append(
                f"SERVICE_CAPACITY_EXCEEDED: {provider_id}/{area_id} "
                f"served {units} > {provider['service_capacity']}"
            )
        observed_served_units += units
        served_by_area[area_id] = served_by_area.get(area_id, 0) + units
        if units < 0:
            violations.append(f"NEGATIVE_DEMAND_ASSIGNMENT: {area_id} served {units}")
        if str(round_item.get("service_type")) not in provider.get("supported_services", []):
            violations.append(f"UNSUPPORTED_SERVICE_ASSIGNMENT: {provider_id}/{area_id}")

        costs = (
            "service_cost_won",
            "travel_cost_won",
            "minimum_compensation_topup_won",
            "total_cost_won",
        )
        if any(int(round_item.get(key, 0)) < 0 for key in costs):
            violations.append(f"NEGATIVE_COST: {provider_id}/{area_id}")
        if int(round_item.get("travel_distance_m", 0)) < 0 or int(
            round_item.get("travel_time_s", 0)
        ) < 0:
            violations.append(f"NEGATIVE_TRAVEL: {provider_id}/{area_id}")

        date_value = datetime.strptime(str(round_item["scheduled_date"]), "%Y-%m-%d").date()
        weekday = date_value.strftime("%A").lower()
        slots = [
            slot for slot in provider.get("availability", []) if slot.get("weekday") == weekday
        ]
        departure_minute = _time_minutes(str(round_item["departure_time"]))
        service_end_minute = _time_minutes(str(round_item["service_end_time"]))
        return_minute = service_end_minute + math.ceil(
            int(round_item.get("travel_after_s", 0)) / 60
        )
        if not any(
            departure_minute >= _time_minutes(str(slot["start_time"]))
            and return_minute <= _time_minutes(str(slot["end_time"]))
            for slot in slots
        ):
            violations.append(f"PROVIDER_AVAILABILITY_VIOLATION: {provider_id}/{area_id}")

        area_windows = area.get("requested_service_windows", [])
        if area_windows:
            start_minute = _time_minutes(str(round_item["service_start_time"]))
            window_matches = []
            for window in area_windows:
                if window.get("desired_date") and window["desired_date"] != str(
                    round_item["scheduled_date"]
                ):
                    continue
                earliest = _time_minutes(str(window.get("window_start", "00:00")))
                latest = _time_minutes(str(window.get("window_end", "23:59")))
                desired = window.get("desired_time")
                if earliest <= start_minute <= latest and (
                    not desired or start_minute == _time_minutes(str(desired))
                ):
                    window_matches.append(window)
            if not window_matches:
                violations.append(f"TIME_WINDOW_VIOLATION: {provider_id}/{area_id}")

        daily_key = (provider_id, str(round_item["scheduled_date"]))
        work_by_provider_date[daily_key] = work_by_provider_date.get(daily_key, 0) + int(
            round_item.get("duration_minutes", 0)
        )
        route_group = str(round_item.get("route_group_key", ""))
        route_key = (provider_id, str(round_item["scheduled_date"]), route_group)
        if route_key not in route_duration_by_group:
            work_by_provider_date[daily_key] += math.ceil(
                (
                    int(round_item.get("travel_before_s", 0))
                    + int(round_item.get("travel_after_s", 0))
                )
                / 60
            )

    for (provider_id, scheduled_date, _route_group), duration_s in route_duration_by_group.items():
        daily_key = (provider_id, scheduled_date)
        work_by_provider_date[daily_key] = work_by_provider_date.get(daily_key, 0) + math.ceil(
            duration_s / 60
        )

    for provider_id, count in rounds_by_provider.items():
        max_rounds = int(provider_lookup[provider_id]["max_monthly_rounds"])
        if count > max_rounds:
            violations.append(
                f"PROVIDER_CAPACITY_EXCEEDED: {provider_id} assigned {count} > {max_rounds}"
            )
    for (provider_id, _scheduled_date), work_minutes in work_by_provider_date.items():
        limit_minutes = int(float(provider_lookup[provider_id]["max_daily_hours"]) * 60)
        if work_minutes > limit_minutes:
            violations.append(
                "DAILY_WORK_LIMIT_EXCEEDED: "
                f"{provider_id} scheduled {work_minutes} > {limit_minutes}"
            )

    for area in areas:
        area_id = str(area["id"])
        demand = int(area.get("simulated_monthly_demand", 0))
        if demand < 0:
            violations.append(f"NEGATIVE_DEMAND: {area_id} demand {demand}")
        if served_by_area.get(area_id, 0) > demand:
            violations.append(
                f"SERVED_EXCEEDS_DEMAND: {area_id} served {served_by_area[area_id]} > {demand}"
            )
    if int(result.get("served_units", 0)) < 0 or observed_served_units != int(
        result.get("served_units", 0)
    ):
        violations.append("SERVED_UNIT_TOTAL_MISMATCH")

    # Every serialized route leg must match an exact directed edge in the matrix.
    def check_route_leg(
        origin_id: str, destination_id: str, distance_m: int, duration_s: int
    ) -> None:
        expected = roads.get((origin_id, destination_id))
        if expected is None:
            violations.append(f"MISSING_ROAD_EDGE_USED: {origin_id}->{destination_id}")
        elif expected != (distance_m, duration_s):
            violations.append(f"ROAD_EDGE_VALUE_MISMATCH: {origin_id}->{destination_id}")

    for route in result.get("routes", []):
        if route.get("route_source") == "HAVERSINE":
            violations.append("STRAIGHT_LINE_SUBSTITUTED: found haversine synthetic route")
        for stop in route.get("stops", []):
            area_id = str(stop["area_id"])
            check_route_leg(
                str(stop["incoming_from_area_id"]),
                area_id,
                int(stop.get("travel_before_distance_m", 0)),
                int(stop.get("travel_before_s", 0)),
            )
            check_route_leg(
                area_id,
                str(stop["outgoing_to_area_id"]),
                int(stop.get("travel_after_distance_m", 0)),
                int(stop.get("travel_after_s", 0)),
            )

    if (
        result.get("hub_fallback_group_count", 0)
        and not allow_route_fallback
        and not result.get("route_matrix_complete", True)
    ):
        violations.append("UNAUTHORIZED_HUB_FALLBACK")

    # Solver states and optimality claims must agree.
    status = result.get("solver_status")
    optimality = bool(result.get("optimality_proven"))
    allowed_statuses = {
        "OPTIMAL",
        "FEASIBLE",
        "INFEASIBLE",
        "UNKNOWN",
        "TIME_LIMIT",
        "MODEL_INVALID",
    }
    if status not in allowed_statuses:
        violations.append(f"INVALID_SOLVER_STATUS: {status}")
    if optimality != (status == "OPTIMAL"):
        violations.append(f"SOLVER_STATUS_DISTORTION: {status}, optimality_proven={optimality}")
    if bool(result.get("time_limit_reached")) != (status == "TIME_LIMIT"):
        violations.append(f"SOLVER_TIME_LIMIT_MISMATCH: {status}")
    if bool(result.get("minimum_coverage_met")) != (
        int(result.get("unmet_minimum_frequency_areas", 0)) == 0
    ):
        violations.append("MINIMUM_COVERAGE_STATUS_MISMATCH")

    return {
        "passed": len(violations) == 0,
        "violations": violations,
    }


def run_single_stress_test(
    num_areas: int,
    num_providers: int,
    variant: str,
    seed: int,
    temp_dir: Path,
    max_solver_seconds: float = 5.0,
    route_strategy: str = "joint",
    profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run one scenario and return metrics and invariant check."""
    db_file = temp_dir / f"test_{num_areas}_{num_providers}_{variant}_{seed}.sqlite"
    areas, providers, connection, budget_won, policy, allow_route_fallback, metadata = (
        generate_scenario_data(num_areas, num_providers, variant, seed, db_file, profile=profile)
    )
    scenario_fingerprint = deterministic_scenario_fingerprint(
        areas,
        providers,
        budget_won,
        policy,
        connection,
        seed=seed,
        variant=variant,
    )

    start_wall = time.perf_counter()
    try:
        res = scheduling.generate_provider_schedule(
            areas,
            providers,
            connection,
            budget_won,
            scenario="balanced",
            policy=policy,
            allow_route_fallback=allow_route_fallback,
            include_timing=True,
            max_solver_seconds=max_solver_seconds,
            route_strategy=route_strategy,
        )
        elapsed_ms = round((time.perf_counter() - start_wall) * 1000, 2)
        inv = verify_invariants(
            res,
            areas,
            providers,
            budget_won,
            connection,
            allow_route_fallback=allow_route_fallback,
        )
        solver_status = str(res["solver_status"])
        has_no_solution = solver_status in {"INFEASIBLE", "UNKNOWN", "MODEL_INVALID"} or (
            solver_status == "TIME_LIMIT" and not res.get("rounds")
        )
        scenario_status = (
            "FAIL"
            if not inv["passed"]
            else "NOT_VERIFIABLE"
            if has_no_solution
            else "PASS"
        )
        record = {
            "service_area_count": num_areas,
            "provider_count": num_providers,
            "num_areas": num_areas,
            "num_providers": num_providers,
            "variant": variant,
            "variation": metadata["variation"],
            "matrix_profile": metadata["matrix_profile"],
            "budget_tier": metadata["budget_tier"],
            "requested_participation_rate": metadata["requested_participation_rate"],
            "observed_participation_rate": metadata["observed_participation_rate"],
            "evidence_low_data_rate": metadata["evidence_low_data_rate"],
            "route_missing_rate": metadata["route_missing_rate"],
            "service_support_mode": metadata["service_support_mode"],
            "seed": seed,
            "scenario_provenance": "SYNTHETIC_SCENARIO_GENERATOR",
            "route_matrix_provenance": "SYNTHETIC_ROUTE_EDGES_FOR_STRESS_ONLY",
            "deterministic_fingerprint": scenario_fingerprint,
            "reproducibility_fingerprint": res.get("reproducibility_fingerprint"),
            "budget_won": budget_won,
            "budget_spent_won": res["budget_spent_won"],
            "budget_remaining_won": res["budget_remaining_won"],
            "budget_gap_won": res.get("budget_gap_won"),
            "missing_capacity": res.get("missing_capacity"),
            "candidate_round_count": res.get("candidate_round_count", 0),
            "served_rounds": len(res.get("rounds", [])),
            "served_units": res["served_units"],
            "total_demand_units": res["total_demand_units"],
            "covered_areas": res["covered_areas"],
            "uncovered_areas": res["uncovered_areas"],
            "minimum_coverage_met": res["minimum_coverage_met"],
            "solver_status": res["solver_status"],
            "optimality_proven": res["optimality_proven"],
            "time_limit_reached": res.get("time_limit_reached", False),
            "objective_value": res.get("objective_value"),
            "objective_bound": res.get("best_objective_bound"),
            "relative_gap": res.get("relative_gap"),
            "solver_runtime_ms": res.get("solve_time_ms", elapsed_ms),
            "solve_time_ms": res.get("solve_time_ms", elapsed_ms),
            "elapsed_ms": elapsed_ms,
            "route_matrix_complete": res["route_matrix_complete"],
            "route_missing_edges": metadata["route_missing_edges"],
            "route_fallback_allowed": allow_route_fallback,
            "fallback_route_count": res.get("hub_fallback_group_count", 0),
            "unavailable_provider_count": len(metadata["unavailable_provider_ids"]),
            "unavailable_provider_ids": metadata["unavailable_provider_ids"],
            "low_data_area_count": metadata["low_data_area_count"],
            "memory_peak_bytes": None,
            "memory_peak_status": "NOT_MEASURED_NATIVE_SOLVER_MEMORY_UNAVAILABLE",
            "multi_stop_routes": res["routing_comparison"]["multi_stop_route_count"],
            "distance_savings_m": res["routing_comparison"]["distance_savings_m"],
            "cost_savings_won": res["routing_comparison"]["cost_savings_won"],
            "invariants_passed": inv["passed"],
            "violations": inv["violations"],
            "status": scenario_status,
            "route_strategy": res.get("route_strategy", route_strategy),
            "decomposition_proof": (res.get("decomposition") or {}).get("optimality_proven"),
        }
    except Exception as e:
        elapsed_ms = round((time.perf_counter() - start_wall) * 1000, 2)
        record = {
            "service_area_count": num_areas,
            "provider_count": num_providers,
            "num_areas": num_areas,
            "num_providers": num_providers,
            "variant": variant,
            "variation": metadata["variation"],
            "matrix_profile": metadata["matrix_profile"],
            "budget_tier": metadata["budget_tier"],
            "requested_participation_rate": metadata["requested_participation_rate"],
            "observed_participation_rate": metadata["observed_participation_rate"],
            "evidence_low_data_rate": metadata["evidence_low_data_rate"],
            "route_missing_rate": metadata["route_missing_rate"],
            "service_support_mode": metadata["service_support_mode"],
            "seed": seed,
            "scenario_provenance": "SYNTHETIC_SCENARIO_GENERATOR",
            "route_matrix_provenance": "SYNTHETIC_ROUTE_EDGES_FOR_STRESS_ONLY",
            "deterministic_fingerprint": scenario_fingerprint,
            "reproducibility_fingerprint": None,
            "budget_won": budget_won,
            "budget_spent_won": 0,
            "budget_remaining_won": budget_won,
            "served_units": 0,
            "total_demand_units": 0,
            "covered_areas": 0,
            "uncovered_areas": num_areas,
            "minimum_coverage_met": False,
            "solver_status": "ERROR",
            "optimality_proven": False,
            "time_limit_reached": False,
            "objective_value": None,
            "objective_bound": None,
            "relative_gap": None,
            "solver_runtime_ms": elapsed_ms,
            "solve_time_ms": elapsed_ms,
            "elapsed_ms": elapsed_ms,
            "route_matrix_complete": False,
            "route_missing_edges": metadata["route_missing_edges"],
            "route_fallback_allowed": allow_route_fallback,
            "fallback_route_count": 0,
            "unavailable_provider_count": len(metadata["unavailable_provider_ids"]),
            "unavailable_provider_ids": metadata["unavailable_provider_ids"],
            "low_data_area_count": metadata["low_data_area_count"],
            "memory_peak_bytes": None,
            "memory_peak_status": "NOT_MEASURED_NATIVE_SOLVER_MEMORY_UNAVAILABLE",
            "multi_stop_routes": 0,
            "distance_savings_m": 0,
            "cost_savings_won": 0,
            "invariants_passed": False,
            "violations": [f"EXCEPTION: {type(e).__name__}: {str(e)}"],
            "status": "ERROR",
        }
    finally:
        connection.close()
        if db_file.exists():
            db_file.unlink(missing_ok=True)

    return record


def main() -> int:
    parser = argparse.ArgumentParser(description="Run scenario stress test suite.")
    parser.add_argument("--quick", action="store_true", help="Run fast smoke subset (10 scenarios)")
    parser.add_argument(
        "--v4-stratified",
        action="store_true",
        help="Run the deterministic 100-case V4 scale/provider/evidence stress matrix",
    )
    parser.add_argument(
        "--max-solver-seconds",
        type=float,
        default=2.5,
        help="Per scheduling solve limit (default: 2.5 seconds)",
    )
    parser.add_argument(
        "--route-strategy",
        choices=("joint", "decomposed", "auto"),
        default="joint",
        help="joint reproduces the V3 baseline; auto is the V4 default",
    )
    parser.add_argument(
        "--strict-wall-clock",
        action="store_true",
        help="cap wall time at the deterministic budget (apples-to-apples with V3 wall limits)",
    )
    parser.add_argument(
        "--output-stem",
        default=None,
        help="artifact file stem (keep V3 evidence by writing V4 runs to a new stem)",
    )
    args = parser.parse_args()
    if args.strict_wall_clock:
        from backend import allocation_stage

        scheduling.DETERMINISTIC_WALL_CAP_FACTOR = 1.0
        allocation_stage.DETERMINISTIC_WALL_CAP_FACTOR = 1.0

    artifacts_dir = ROOT / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    temp_dir = ROOT / "artifacts" / "scratch_stress"
    temp_dir.mkdir(parents=True, exist_ok=True)

    if args.v4_stratified:
        test_matrix = build_v4_stratified_matrix()
        output_stem = args.output_stem or "stress_test_results_v4_stratified"
    elif args.quick:
        # Quick subset for fast validation / CI
        test_matrix = [
            (16, 3, variant) for variant in VARIANT_LABELS
        ]
        output_stem = args.output_stem or "stress_test_results"
    else:
        # Full comprehensive matrix
        # Representative cases cover all scales, provider counts, and A~J variations.
        test_matrix = [
            *((16, 3, variant) for variant in VARIANT_LABELS),
            *((30, 5, variant) for variant in VARIANT_LABELS),
            *((50, 10, variant) for variant in ("A", "C", "D", "F", "G", "H", "I", "J")),
            *((100, 10, variant) for variant in ("A", "B", "D", "E", "G", "H", "I")),
            *((100, 20, variant) for variant in ("A", "C", "E", "F", "G", "H", "J")),
            *((200, 20, variant) for variant in VARIANT_LABELS),
        ]
        output_stem = args.output_stem or "stress_test_results"

    run_label = "V4 Stratified" if args.v4_stratified else "Legacy V3"
    print(
        f"=== VillageCoverage {run_label} - Scenario Stress Tests "
        f"({len(test_matrix)} scenarios) ==="
    )
    results: list[dict[str, Any]] = []

    for idx, case in enumerate(test_matrix, 1):
        if args.v4_stratified:
            n_areas, n_provs, case_seed, profile = case
            variant = "A"
        else:
            n_areas, n_provs, variant = case
            case_seed = REFERENCE_SEED
            profile = None
        print(
            f"[{idx:02d}/{len(test_matrix):02d}] N={n_areas:03d}, P={n_provs:02d}, "
            f"Variant={variant}, profile={(profile or {}).get('name', 'legacy')} ... ",
            end="",
            flush=True,
        )
        rec = run_single_stress_test(
            n_areas,
            n_provs,
            variant,
            case_seed,
            temp_dir,
            max_solver_seconds=args.max_solver_seconds,
            route_strategy=args.route_strategy,
            profile=profile,
        )
        status = rec["status"]
        solve_ms = rec["solve_time_ms"]
        solver_st = rec["solver_status"]
        violations = len(rec["violations"])
        print(f"{status} (Solver: {solver_st}, {solve_ms}ms, violations: {violations})")
        results.append(rec)

    # Clean scratch
    try:
        temp_dir.rmdir()
    except Exception:
        pass

    # Save JSON artifact
    json_path = artifacts_dir / f"{output_stem}.json"
    summary = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "route_strategy": args.route_strategy,
        "max_solver_seconds": args.max_solver_seconds,
        "strict_wall_clock": args.strict_wall_clock,
        "reference_seed": REFERENCE_SEED,
        "matrix_type": "V4_STRATIFIED_100" if args.v4_stratified else "LEGACY",
        "total_scenarios": len(results),
        "passed_scenarios": sum(r["status"] == "PASS" for r in results),
        "not_verifiable_scenarios": sum(r["status"] == "NOT_VERIFIABLE" for r in results),
        "failed_scenarios": sum(r["status"] == "FAIL" for r in results),
        "error_scenarios": sum(r["status"] == "ERROR" for r in results),
        "invariant_passed_scenarios": sum(bool(r.get("invariants_passed")) for r in results),
        "scenarios_with_scheduled_rounds": sum(bool(r.get("served_rounds")) for r in results),
        "minimum_coverage_met_scenarios": sum(bool(r.get("minimum_coverage_met")) for r in results),
        "total_invariant_violations": sum(len(r["violations"]) for r in results),
        "status_distribution": {
            st: sum(r["solver_status"] == st for r in results)
            for st in sorted({r["solver_status"] for r in results})
        },
        "results": results,
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    # Save CSV artifact
    csv_path = artifacts_dir / f"{output_stem}.csv"
    fieldnames = [
        "service_area_count", "provider_count", "num_areas", "num_providers",
        "variant", "variation", "matrix_profile", "budget_tier",
        "requested_participation_rate", "observed_participation_rate",
        "evidence_low_data_rate", "route_missing_rate", "service_support_mode",
        "seed", "scenario_provenance",
        "route_matrix_provenance", "deterministic_fingerprint",
        "reproducibility_fingerprint", "budget_won", "budget_spent_won",
        "budget_gap_won", "missing_capacity", "candidate_round_count", "served_rounds",
        "served_units", "total_demand_units",
        "covered_areas", "uncovered_areas", "minimum_coverage_met",
        "solver_status", "optimality_proven", "time_limit_reached", "objective_value",
        "objective_bound", "relative_gap", "solver_runtime_ms", "solve_time_ms",
        "route_matrix_complete", "route_missing_edges", "route_fallback_allowed",
        "fallback_route_count", "unavailable_provider_count", "low_data_area_count",
        "memory_peak_bytes", "memory_peak_status", "multi_stop_routes",
        "distance_savings_m", "cost_savings_won", "status", "violations",
    ]
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for r in results:
            row = dict(r)
            row["violations"] = "; ".join(r["violations"])
            writer.writerow(row)

    print("\nSummary:")
    print(f"- Total scenarios: {summary['total_scenarios']}")
    print(f"- Passed (0 violations): {summary['passed_scenarios']}")
    print(f"- Not verifiable (no feasible plan): {summary['not_verifiable_scenarios']}")
    print(f"- Failed: {summary['failed_scenarios']}")
    print(f"- Errors: {summary['error_scenarios']}")
    print(f"- Status distribution: {summary['status_distribution']}")
    print(f"- Saved JSON to: {json_path}")
    print(f"- Saved CSV to: {csv_path}")

    return (
        0
        if summary["failed_scenarios"] == 0 and summary["error_scenarios"] == 0
        else 1
    )


if __name__ == "__main__":
    sys.exit(main())
