#!/usr/bin/env python3
"""Multi-Stop Routing Benchmark (§14).

Compares hub round-trip baseline vs multi-stop planning across at least 30
deterministic synthetic routing scenarios with varying topologies (clusters, corridors,
dispersed stars, zig-zag) and stop counts (2~5 stops).
Computes mean, median, min, max, p25, p75 for distance, duration, and cost.
Outputs artifacts/routing_benchmark.json.
"""

from __future__ import annotations

import json
import math
import random
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.optimization import TRAVEL_LABOR_WON_PER_HOUR, TRAVEL_RATE_WON_PER_KM  # noqa: E402
from backend.routing import optimize_multi_stop_route  # noqa: E402

REFERENCE_SEED = 20261002


def _leg_cost(distance_m: int, duration_s: int) -> int:
    return math.ceil(distance_m / 1000 * TRAVEL_RATE_WON_PER_KM) + math.ceil(
        duration_s / 3600 * TRAVEL_LABOR_WON_PER_HOUR
    )


def percentile(data: list[float], p: float) -> float:
    if not data:
        return 0.0
    s = sorted(data)
    k = (len(s) - 1) * p
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return s[int(k)]
    return s[f] * (c - k) + s[c] * (k - f)


def compute_stats(values: list[float]) -> dict[str, float]:
    if not values:
        return {"mean": 0.0, "median": 0.0, "min": 0.0, "max": 0.0, "p25": 0.0, "p75": 0.0}
    return {
        "mean": round(sum(values) / len(values), 2),
        "median": round(percentile(values, 0.50), 2),
        "min": round(min(values), 2),
        "max": round(max(values), 2),
        "p25": round(percentile(values, 0.25), 2),
        "p75": round(percentile(values, 0.75), 2),
    }


def generate_benchmark_scenarios(
    count: int = 36, seed: int = REFERENCE_SEED
) -> list[dict[str, Any]]:
    """Generate deterministic routing scenarios across spatial patterns."""
    scenarios = []

    topologies = [
        "cluster",  # stops grouped closely together
        "corridor",  # stops arranged linearly along an axis
        "star",  # stops spread radially in opposite directions from base
        "zigzag",  # alternating sides of base
    ]

    scenario_idx = 1
    for stop_count in [2, 3, 4, 5]:
        for topo in topologies:
            # 2-3 variations per combination to reach ~36
            variations = 3 if stop_count in [2, 3] else 2
            for v in range(variations):
                scenarios.append(
                    {
                        "scenario_id": f"scen_{scenario_idx:02d}_{topo}_{stop_count}stops_v{v+1}",
                        "stop_count": stop_count,
                        "topology": topo,
                        "variation": v + 1,
                        "seed": seed + scenario_idx * 17,
                    }
                )
                scenario_idx += 1
                if len(scenarios) >= count:
                    break
            if len(scenarios) >= count:
                break
        if len(scenarios) >= count:
            break

    return scenarios


def run_benchmark_scenario(scen_def: dict[str, Any]) -> dict[str, Any]:
    rng = random.Random(scen_def["seed"])
    stop_count = scen_def["stop_count"]
    topo = scen_def["topology"]

    base_id = "depot_base"
    stops: list[dict[str, Any]] = []

    # Coordinates in km relative to depot (0, 0)
    coords: dict[str, tuple[float, float]] = {base_id: (0.0, 0.0)}

    for i in range(stop_count):
        s_id = f"stop_{i+1}"
        if topo == "cluster":
            # Cluster center at (15, 10), radius 2-5km
            cx, cy = 15.0, 10.0
            ang = rng.uniform(0, 2 * math.pi)
            r = rng.uniform(1.0, 5.0)
            coords[s_id] = (cx + r * math.cos(ang), cy + r * math.sin(ang))
        elif topo == "corridor":
            # Along a line extending from base at (5*i, 2*i) +/- noise
            dist = 8.0 * (i + 1)
            coords[s_id] = (dist + rng.uniform(-1.0, 1.0), dist * 0.4 + rng.uniform(-1.5, 1.5))
        elif topo == "star":
            # Dispersed in opposite directions (e.g. North, South, East, West)
            ang = (2 * math.pi / stop_count) * i + rng.uniform(-0.2, 0.2)
            dist = rng.uniform(10.0, 25.0)
            coords[s_id] = (dist * math.cos(ang), dist * math.sin(ang))
        elif topo == "zigzag":
            # Alternating positive / negative Y with increasing X
            x = 6.0 * (i + 1)
            y = 12.0 * (1 if i % 2 == 0 else -1) + rng.uniform(-2.0, 2.0)
            coords[s_id] = (x, y)
        else:
            coords[s_id] = (rng.uniform(-15.0, 15.0), rng.uniform(-15.0, 15.0))

        stops.append(
            {
                "area_id": s_id,
                "duration_minutes": 30,  # 30 min service per stop
                "service_start_window_start": "09:00",
                "service_start_window_end": "18:00",
            }
        )

    # Build road matrix
    all_locs = [base_id] + [s["area_id"] for s in stops]
    roads: dict[tuple[str, str], tuple[int, int]] = {}

    for u in all_locs:
        for v in all_locs:
            if u == v:
                roads[(u, v)] = (0, 0)
                continue
            x1, y1 = coords[u]
            x2, y2 = coords[v]
            euc_km = math.hypot(x2 - x1, y2 - y1)
            # Add road winding factor 1.25 ~ 1.45
            winding = 1.25 + (rng.random() * 0.20)
            road_km = max(0.5, euc_km * winding)
            dist_m = int(road_km * 1000)
            # Speed ~ 45 km/h -> 750 m/min -> 12.5 m/s
            dur_s = max(60, int(dist_m / 12.5))
            roads[(u, v)] = (dist_m, dur_s)

    # 1. Old Hub Round-Trip Baseline
    old_distance = sum(
        roads[(base_id, s["area_id"])][0] + roads[(s["area_id"], base_id)][0]
        for s in stops
    )
    old_duration = sum(
        roads[(base_id, s["area_id"])][1] + roads[(s["area_id"], base_id)][1]
        for s in stops
    )
    old_cost = sum(
        _leg_cost(roads[(base_id, s["area_id"])][0], roads[(base_id, s["area_id"])][1])
        + _leg_cost(roads[(s["area_id"], base_id)][0], roads[(s["area_id"], base_id)][1])
        for s in stops
    )

    # 2. Multi-stop Routing
    sol = optimize_multi_stop_route(
        base_id,
        stops,
        roads,
        available_from="09:00",
        available_until="18:00",
        max_daily_hours=8.0,
        time_limit_seconds=0.5,
    )

    if sol is not None:
        ms_distance = sol["distance_m"]
        ms_duration = sol["duration_s"]
        ms_cost = sol["cost_won"]
        feasible = True
    else:
        # If multi-stop was infeasible under constraints, fall back to hub round-trip
        ms_distance = old_distance
        ms_duration = old_duration
        ms_cost = old_cost
        feasible = False

    dist_saving = old_distance - ms_distance
    dur_saving = old_duration - ms_duration
    cost_saving = old_cost - ms_cost

    dist_saving_pct = round((dist_saving / old_distance * 100) if old_distance > 0 else 0.0, 2)
    cost_saving_pct = round((cost_saving / old_cost * 100) if old_cost > 0 else 0.0, 2)

    return {
        "scenario_id": scen_def["scenario_id"],
        "topology": topo,
        "stop_count": stop_count,
        "multi_stop_feasible": feasible,
        "old_distance_m": old_distance,
        "multi_stop_distance_m": ms_distance,
        "distance_saving_m": dist_saving,
        "distance_saving_pct": dist_saving_pct,
        "old_duration_s": old_duration,
        "multi_stop_duration_s": ms_duration,
        "duration_saving_s": dur_saving,
        "old_cost_won": old_cost,
        "multi_stop_cost_won": ms_cost,
        "cost_saving_won": cost_saving,
        "cost_saving_pct": cost_saving_pct,
    }


def main() -> int:
    artifacts_dir = ROOT / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    json_path = artifacts_dir / "routing_benchmark.json"

    scenarios = generate_benchmark_scenarios(count=36, seed=REFERENCE_SEED)
    print(f"Running Multi-Stop Routing Benchmark ({len(scenarios)} scenarios)...")

    results: list[dict[str, Any]] = []
    for s in scenarios:
        res = run_benchmark_scenario(s)
        results.append(res)

    distance_savings_km = [r["distance_saving_m"] / 1000.0 for r in results]
    duration_savings_min = [r["duration_saving_s"] / 60.0 for r in results]
    cost_savings_won = [float(r["cost_saving_won"]) for r in results]
    cost_savings_pct = [float(r["cost_saving_pct"]) for r in results]

    summary = {
        "benchmark_metadata": {
            "title": "VillageCoverage Multi-Stop Routing Synthetic Benchmark",
            "seed": REFERENCE_SEED,
            "scenario_count": len(results),
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "interpretation_guideline": (
                "현재 synthetic route scenarios에서 multi-stop planning이 "
                "hub round-trip 기준과 비교해 어떤 차이를 보이는지 검증"
            ),
        },
        "aggregate_statistics": {
            "distance_saving_km": compute_stats(distance_savings_km),
            "duration_saving_minutes": compute_stats(duration_savings_min),
            "cost_saving_won": compute_stats(cost_savings_won),
            "cost_saving_pct": compute_stats(cost_savings_pct),
        },
        "by_topology": {},
        "by_stop_count": {},
        "scenarios": results,
    }

    # Breakdown by topology
    for topo in set(r["topology"] for r in results):
        subset = [r for r in results if r["topology"] == topo]
        mean_saving = sum(r["cost_saving_pct"] for r in subset) / len(subset)
        summary["by_topology"][topo] = {
            "count": len(subset),
            "mean_cost_saving_pct": round(mean_saving, 2),
            "min_cost_saving_pct": min(r["cost_saving_pct"] for r in subset),
            "max_cost_saving_pct": max(r["cost_saving_pct"] for r in subset),
        }

    # Breakdown by stop count
    for sc in sorted(set(r["stop_count"] for r in results)):
        subset = [r for r in results if r["stop_count"] == sc]
        mean_saving = sum(r["cost_saving_pct"] for r in subset) / len(subset)
        summary["by_stop_count"][str(sc)] = {
            "count": len(subset),
            "mean_cost_saving_pct": round(mean_saving, 2),
            "min_cost_saving_pct": min(r["cost_saving_pct"] for r in subset),
            "max_cost_saving_pct": max(r["cost_saving_pct"] for r in subset),
        }

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"Benchmark completed successfully! Total scenarios: {len(results)}")
    print(f"Cost saving pct stats: {summary['aggregate_statistics']['cost_saving_pct']}")
    print(f"Saved to: {json_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
