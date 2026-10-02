"""Tests for multi-stop routing benchmark (§14, §9)."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.run_routing_benchmark import (
    REFERENCE_SEED,
    generate_benchmark_scenarios,
    run_benchmark_scenario,
)

ROOT = Path(__file__).resolve().parents[1]


def test_routing_benchmark_scenario_generation() -> None:
    scenarios = generate_benchmark_scenarios(count=36, seed=REFERENCE_SEED)
    assert len(scenarios) >= 30
    stop_counts = {s["stop_count"] for s in scenarios}
    assert {2, 3, 4, 5}.issubset(stop_counts)


def test_routing_benchmark_single_scenario_execution() -> None:
    scen = {
        "scenario_id": "test_cluster_3stops",
        "stop_count": 3,
        "topology": "cluster",
        "variation": 1,
        "seed": REFERENCE_SEED,
    }
    res = run_benchmark_scenario(scen)
    assert res["scenario_id"] == "test_cluster_3stops"
    assert res["stop_count"] == 3
    assert res["old_distance_m"] > 0
    assert res["multi_stop_distance_m"] > 0
    assert "cost_saving_pct" in res


def test_routing_benchmark_artifacts_and_metrics() -> None:
    json_path = ROOT / "artifacts" / "routing_benchmark.json"
    assert json_path.exists(), "routing_benchmark.json artifact must exist"

    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    meta = data["benchmark_metadata"]
    assert meta["scenario_count"] >= 30
    # Must adhere to strict interpretation guideline without exaggerated claims
    assert "지자체에서 33% 절감" not in meta["interpretation_guideline"]
    assert "synthetic route scenarios" in meta["interpretation_guideline"]

    stats = data["aggregate_statistics"]
    keys = [
        "distance_saving_km",
        "duration_saving_minutes",
        "cost_saving_won",
        "cost_saving_pct",
    ]
    for key in keys:
        metric_stat = stats[key]
        for req_stat in ["mean", "median", "min", "max", "p25", "p75"]:
            assert req_stat in metric_stat

    assert len(data["scenarios"]) >= 30
