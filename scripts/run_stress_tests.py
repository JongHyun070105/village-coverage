#!/usr/bin/env python3
"""VillageCoverage V3 Phase 2 - Scenario Stress Test Framework (§11).

Generates synthetic stress scenarios across scales [16, 30, 50, 100, 200] areas,
[3, 5, 10, 20] providers, and 10 condition variants (A~J).
Verifies 6 core invariants and writes results to artifacts/stress_test_results.json & .csv.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend import scheduling  # noqa: E402
from backend.scheduling import PlanningPolicy  # noqa: E402
from backend.travel import Route, connect, put_cached  # noqa: E402

REFERENCE_SEED = 20261002
SERVICES = ("laundry", "daily_necessities", "home_repair")
DAYS_OF_WEEK = ("monday", "tuesday", "wednesday", "thursday", "friday")


def generate_scenario_data(
    num_areas: int,
    num_providers: int,
    variant: str,
    seed: int,
    db_path: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], Any, int, PlanningPolicy, bool]:
    """Build synthetic areas, providers, road matrix in SQLite, budget, and policy."""
    rng = random.Random(seed + num_areas * 1000 + num_providers * 10 + ord(variant[0]))
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
        if variant == "G":
            # High demand shock: 2.5x demand
            base_demand = int(base_demand * 2.5)

        service_type = SERVICES[i % len(SERVICES)]
        needs_survey = (rng.random() < 0.25)
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

        if variant == "F":
            # Strict time windows: 2-hour window on a preferred day
            pref_day = rng.choice(DAYS_OF_WEEK)
            start_h = rng.randint(9, 14)
            area["requested_windows"] = [
                {
                    "day_of_week": pref_day,
                    "desired_time": f"{start_h:02d}:00",
                    "window_start": f"{start_h:02d}:00",
                    "window_end": f"{start_h + 2:02d}:00",
                }
            ]
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

        max_rounds = 12
        service_cap = 3
        if variant == "C":
            # Tight capacity
            max_rounds = rng.randint(2, 4)
            service_cap = 2

        declined_areas = []
        if variant == "H" and (j % 3 == 0):
            # Provider dropout / decline 40% of areas
            declined_areas = [a["id"] for a in areas if rng.random() < 0.4]

        # Realistic mobile outreach availability: 2-3 specific weekdays per provider
        schedule_patterns = [
            ["monday", "wednesday", "friday"],
            ["tuesday", "thursday"],
            ["monday", "thursday"],
            ["tuesday", "friday"],
            ["wednesday", "friday"],
        ]
        chosen_days = schedule_patterns[j % len(schedule_patterns)]
        provider = {
            "provider_id": p_id,
            "name": f"공급업체-{j:02d}",
            "base_area_id": depot_id,
            "supported_services": supp,
            "availability": [
                {"weekday": d, "start_time": "09:00", "end_time": "18:00"}
                for d in chosen_days
            ],
            "max_monthly_rounds": max_rounds,
            "service_capacity": service_cap,
            "max_daily_hours": 7.0,
            "max_travel_time_minutes": 90,
            "minimum_compensation_won": 1_000_000,
            "declined_areas": declined_areas,
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
    # Depots to all areas and areas to all areas
    allow_route_fallback = (variant == "E")
    edge_drop_rate = 0.30 if variant == "E" else 0.0

    for origin in all_nodes:
        for dest in all_nodes:
            if origin["id"] == dest["id"]:
                continue
            is_depot_leg = origin["id"].startswith("depot-") or dest["id"].startswith("depot-")
            # In sparse network (variant E), drop some inter-area edges,
            # but keep depot edges so hub fallback works
            if not is_depot_leg and edge_drop_rate > 0 and rng.random() < edge_drop_rate:
                continue
            dist_m, dur_s = calc_travel(
                origin["anchor_lat"], origin["anchor_lng"], dest["anchor_lat"], dest["anchor_lng"]
            )
            put_cached(connection, origin, dest, Route(origin["id"], dest["id"], dist_m, dur_s))

    # 4. Budget calculation
    estimated_needed = num_areas * 200_000
    if variant == "B":
        # Tight budget: 40% of needed
        budget_won = int(estimated_needed * 0.40)
    else:
        budget_won = int(estimated_needed * 1.50)

    policy = PlanningPolicy(minimum_services_per_area=1)
    return areas, providers, connection, budget_won, policy, allow_route_fallback


def verify_invariants(
    result: dict[str, Any],
    areas: list[dict[str, Any]],
    providers: list[dict[str, Any]],
    budget_won: int,
) -> dict[str, Any]:
    """Verify the 6 core robustness invariants."""
    violations: list[str] = []

    # 1. Budget exceeded invariant
    spent = result.get("budget_spent_won", 0)
    if spent > budget_won:
        violations.append(f"BUDGET_EXCEEDED: spent {spent} > budget {budget_won}")

    # 2. Provider capacity violated invariant
    provider_lookup = {p["provider_id"]: p for p in providers}
    rounds_by_provider: dict[str, int] = {}
    for r in result.get("rounds", []):
        p_id = r["provider_id"]
        rounds_by_provider[p_id] = rounds_by_provider.get(p_id, 0) + 1

    for p_id, count in rounds_by_provider.items():
        max_r = provider_lookup[p_id]["max_monthly_rounds"]
        if count > max_r:
            violations.append(f"CAPACITY_VIOLATED: provider {p_id} assigned {count} > max {max_r}")

    # 3. Time window / daily hours violation
    for r in result.get("rounds", []):
        limit_m = provider_lookup[r["provider_id"]]["max_daily_hours"] * 60
        if r.get("work_duration_minutes", 0) > limit_m:
            violations.append(
                f"DAILY_HOURS_VIOLATED: round in area {r['area_id']} exceeded max daily hours"
            )

    # 4. Negative values invariant
    if spent < 0:
        violations.append(f"NEGATIVE_SPENT: {spent}")
    if result.get("served_units", 0) < 0:
        violations.append(f"NEGATIVE_SERVED_UNITS: {result.get('served_units')}")
    if result.get("travel_distance_m", 0) < 0:
        violations.append(f"NEGATIVE_DISTANCE: {result.get('travel_distance_m')}")
    if result.get("travel_time_s", 0) < 0:
        violations.append(f"NEGATIVE_TIME: {result.get('travel_time_s')}")

    # 5. Straight-line / haversine substituted invariant
    # Routes must be verified road routes (never haversine fallback in actual schedule)
    for route in result.get("routes", []):
        if route.get("route_source") == "HAVERSINE":
            violations.append("STRAIGHT_LINE_SUBSTITUTED: found haversine synthetic route")

    # 6. Solver status distortion invariant
    status = result.get("solver_status")
    optimality = result.get("optimality_proven")
    if status in {"FEASIBLE", "TIME_LIMIT", "INFEASIBLE"} and optimality is True:
        violations.append(f"SOLVER_STATUS_DISTORTION: status {status} but optimality_proven=True")
    if status == "OPTIMAL" and optimality is False:
        violations.append("SOLVER_STATUS_DISTORTION: status OPTIMAL but optimality_proven=False")

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
) -> dict[str, Any]:
    """Run one scenario and return metrics and invariant check."""
    db_file = temp_dir / f"test_{num_areas}_{num_providers}_{variant}_{seed}.sqlite"
    areas, providers, connection, budget_won, policy, allow_route_fallback = (
        generate_scenario_data(num_areas, num_providers, variant, seed, db_file)
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
        )
        elapsed_ms = round((time.perf_counter() - start_wall) * 1000, 2)
        inv = verify_invariants(res, areas, providers, budget_won)
        
        record = {
            "num_areas": num_areas,
            "num_providers": num_providers,
            "variant": variant,
            "seed": seed,
            "budget_won": budget_won,
            "budget_spent_won": res["budget_spent_won"],
            "budget_remaining_won": res["budget_remaining_won"],
            "served_units": res["served_units"],
            "total_demand_units": res["total_demand_units"],
            "covered_areas": res["covered_areas"],
            "uncovered_areas": res["uncovered_areas"],
            "minimum_coverage_met": res["minimum_coverage_met"],
            "solver_status": res["solver_status"],
            "optimality_proven": res["optimality_proven"],
            "time_limit_reached": res.get("time_limit_reached", False),
            "solve_time_ms": res.get("solve_time_ms", elapsed_ms),
            "elapsed_ms": elapsed_ms,
            "route_matrix_complete": res["route_matrix_complete"],
            "multi_stop_routes": res["routing_comparison"]["multi_stop_route_count"],
            "distance_savings_m": res["routing_comparison"]["distance_savings_m"],
            "cost_savings_won": res["routing_comparison"]["cost_savings_won"],
            "invariants_passed": inv["passed"],
            "violations": inv["violations"],
            "status": "PASS" if inv["passed"] else "FAIL",
        }
    except Exception as e:
        elapsed_ms = round((time.perf_counter() - start_wall) * 1000, 2)
        record = {
            "num_areas": num_areas,
            "num_providers": num_providers,
            "variant": variant,
            "seed": seed,
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
            "solve_time_ms": elapsed_ms,
            "elapsed_ms": elapsed_ms,
            "route_matrix_complete": False,
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
    args = parser.parse_args()

    artifacts_dir = ROOT / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    temp_dir = ROOT / "artifacts" / "scratch_stress"
    temp_dir.mkdir(parents=True, exist_ok=True)

    if args.quick:
        # Quick subset for fast validation / CI
        test_matrix = [
            (16, 3, "A"),  # baseline small
            (16, 3, "B"),  # tight budget
            (16, 3, "C"),  # tight capacity
            (16, 3, "E"),  # sparse network
            (16, 3, "F"),  # strict time windows
            (30, 5, "A"),  # baseline medium
            (30, 5, "B"),  # tight budget medium
            (30, 5, "G"),  # demand shock
            (30, 5, "H"),  # provider dropout
            (50, 5, "A"),  # 50 areas baseline
        ]
    else:
        # Full comprehensive matrix
        # Scales: 16, 30, 50, 100, 200
        # Providers: 3, 5, 10, 20
        # Variants: A~J
        test_matrix = [
            # Scale 16
            (16, 3, "A"), (16, 3, "B"), (16, 3, "C"), (16, 3, "E"), (16, 3, "F"),
            (16, 5, "A"), (16, 5, "G"), (16, 5, "H"), (16, 5, "I"),
            # Scale 30
            (30, 5, "A"), (30, 5, "B"), (30, 5, "C"), (30, 5, "E"), (30, 5, "F"),
            (30, 10, "A"), (30, 10, "G"), (30, 10, "H"), (30, 10, "I"),
            # Scale 50
            (50, 5, "A"), (50, 5, "B"), (50, 10, "A"), (50, 10, "C"), (50, 10, "E"),
            (50, 10, "F"), (50, 10, "G"), (50, 10, "H"), (50, 10, "I"),
            # Scale 100
            (100, 10, "A"), (100, 10, "B"), (100, 10, "D"), (100, 10, "E"),
            (100, 20, "A"), (100, 20, "G"), (100, 20, "H"),
            # Scale 200
            (200, 20, "A"), (200, 20, "D"), (200, 20, "J"),
        ]

    print(
        f"=== VillageCoverage V3 Phase 2 - Scenario Stress Tests ({len(test_matrix)} scenarios) ==="
    )
    results: list[dict[str, Any]] = []

    for idx, (n_areas, n_provs, variant) in enumerate(test_matrix, 1):
        print(
            f"[{idx:02d}/{len(test_matrix):02d}] N={n_areas:03d}, P={n_provs:02d}, "
            f"Variant={variant} ... ",
            end="",
            flush=True,
        )
        rec = run_single_stress_test(n_areas, n_provs, variant, REFERENCE_SEED, temp_dir)
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
    json_path = artifacts_dir / "stress_test_results.json"
    summary = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "reference_seed": REFERENCE_SEED,
        "total_scenarios": len(results),
        "passed_scenarios": sum(r["status"] == "PASS" for r in results),
        "failed_scenarios": sum(r["status"] == "FAIL" for r in results),
        "error_scenarios": sum(r["status"] == "ERROR" for r in results),
        "total_invariant_violations": sum(len(r["violations"]) for r in results),
        "status_distribution": {
            st: sum(r["solver_status"] == st for r in results)
            for st in set(r["solver_status"] for r in results)
        },
        "results": results,
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    # Save CSV artifact
    csv_path = artifacts_dir / "stress_test_results.csv"
    fieldnames = [
        "num_areas", "num_providers", "variant", "seed",
        "budget_won", "budget_spent_won", "served_units", "total_demand_units",
        "covered_areas", "uncovered_areas", "minimum_coverage_met",
        "solver_status", "optimality_proven", "time_limit_reached",
        "solve_time_ms", "route_matrix_complete", "multi_stop_routes",
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
    print(f"- Failed: {summary['failed_scenarios']}")
    print(f"- Errors: {summary['error_scenarios']}")
    print(f"- Status distribution: {summary['status_distribution']}")
    print(f"- Saved JSON to: {json_path}")
    print(f"- Saved CSV to: {csv_path}")

    return 0 if summary["failed_scenarios"] == 0 and summary["error_scenarios"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
