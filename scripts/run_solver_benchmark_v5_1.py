"""Reproducible V5.1 solver architecture benchmark on synthetic road fixtures."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
import tempfile
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend import scheduling  # noqa: E402
from backend.geographic_decomposition import ClusterConfig  # noqa: E402
from backend.rolling_horizon import RollingHorizonConfig  # noqa: E402
from backend.source_snapshots import utc_now  # noqa: E402
from scripts.run_stress_tests import (  # noqa: E402
    REFERENCE_SEED,
    deterministic_scenario_fingerprint,
    generate_scenario_data,
    verify_invariants,
)

CASES = ((16, 3), (30, 5), (50, 5), (100, 10), (200, 20))
SCENARIOS = {
    "NORMAL": ("A", {}),
    "TIGHT_BUDGET": ("B", {}),
    "PROVIDER_SHORTAGE": ("C", {}),
    "REMOTE_AREAS": ("A", {"remote_area_fraction": 0.3}),
    "MANY_LOW_DATA": ("F", {}),
    "HOME_REPAIR_MIXED": ("A", {"home_repair_share": 0.5}),
    "MASS_DECLINE": ("A", {"participation_rate": 0.2}),
}
STRATEGIES: dict[str, dict[str, Any]] = {
    "S0_MONOLITHIC": {"route_strategy": "joint"},
    "S1_V5_BASELINE": {"route_strategy": "decomposed"},
    "S2_GEOGRAPHIC_CLUSTER": {
        "route_strategy": "decomposed",
        "planning_strategy": "geographic_cluster",
        "cluster_config": ClusterConfig(),
    },
    "S2_ADMINISTRATIVE_CLUSTER": {
        "route_strategy": "decomposed",
        "planning_strategy": "geographic_cluster",
        "cluster_strategy": "ADMINISTRATIVE_CLUSTER",
        "cluster_config": ClusterConfig(),
    },
    "S2_DISTANCE_CLUSTER": {
        "route_strategy": "decomposed",
        "planning_strategy": "geographic_cluster",
        "cluster_strategy": "DISTANCE_CLUSTER",
        "cluster_config": ClusterConfig(),
    },
    "S2_PROVIDER_REACHABILITY_CLUSTER": {
        "route_strategy": "decomposed",
        "planning_strategy": "geographic_cluster",
        "cluster_strategy": "PROVIDER_REACHABILITY_CLUSTER",
        "cluster_config": ClusterConfig(),
    },
    "S3_ROLLING_HORIZON_7_21": {
        "route_strategy": "decomposed",
        "planning_strategy": "rolling_horizon",
        "rolling_config": RollingHorizonConfig(28, 7, 21),
    },
    "S3_ROLLING_HORIZON_7_14": {
        "route_strategy": "decomposed",
        "planning_strategy": "rolling_horizon",
        "rolling_config": RollingHorizonConfig(21, 7, 14),
    },
    "S3_ROLLING_HORIZON_14_14": {
        "route_strategy": "decomposed",
        "planning_strategy": "rolling_horizon",
        "rolling_config": RollingHorizonConfig(28, 14, 14),
    },
    "S4_GEOGRAPHIC_ROLLING_7_21": {
        "route_strategy": "decomposed",
        "planning_strategy": "geographic_rolling",
        "rolling_config": RollingHorizonConfig(28, 7, 21),
        "cluster_config": ClusterConfig(),
    },
    "S4_GEOGRAPHIC_ROLLING_14_14": {
        "route_strategy": "decomposed",
        "planning_strategy": "geographic_rolling",
        "rolling_config": RollingHorizonConfig(28, 14, 14),
        "cluster_config": ClusterConfig(enable_heuristic_candidate_pruning=True),
    },
}
JOINT_MAX_PREDICTED_ARCS = 500_000


def _instrumented_run(
    areas_n: int,
    providers_n: int,
    scenario_name: str,
    strategy_name: str,
    strategy: dict[str, Any],
    seed: int,
    seconds: float,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    telemetry: dict[str, Any] = {
        "preprocess_ms": 0.0,
        "route_ms": 0.0,
        "allocation_wall_ms": 0.0,
        "candidate_counts": [],
        "candidate_generation_ms": 0.0,
        "route_row_ms": 0.0,
        "route_profiles": [],
        "allocation_profiles": [],
        "schedule_profiles": [],
        "diagnostic_ms": 0.0,
        "route_matrix_maps": [],
    }
    names = (
        "_route_rows",
        "_make_candidates",
        "_route_selected_stops",
        "solve_aggregate_allocation",
        "_calculate_minimum_budget",
        "_minimum_capacity_diagnostic",
        "generate_provider_schedule",
    )
    originals = {name: getattr(scheduling, name) for name in names}
    depth = 0

    def wrap_simple(name: str, metric: str, *, count_candidates: bool = False) -> None:
        original = originals[name]

        def wrapped(*args: Any, **kwargs: Any) -> Any:
            started = time.perf_counter()
            value = original(*args, **kwargs)
            elapsed = (time.perf_counter() - started) * 1000
            telemetry[metric] += elapsed
            if count_candidates:
                telemetry["candidate_counts"].append(len(value[0]))
            return value

        setattr(scheduling, name, wrapped)

    original_route_rows = originals["_route_rows"]

    class ReadCountingRouteMap(dict):
        def __init__(self, rows: dict[tuple[str, str], tuple[int, int]]) -> None:
            super().__init__(rows)
            self.lookup_counts: Counter[tuple[str, str]] = Counter()

        def get(self, key: tuple[str, str], default: Any = None) -> Any:
            self.lookup_counts[key] += 1
            return super().get(key, default)

        def __contains__(self, key: object) -> bool:
            if isinstance(key, tuple) and len(key) == 2:
                self.lookup_counts[key] += 1
            return super().__contains__(key)

        def __getitem__(self, key: tuple[str, str]) -> Any:
            self.lookup_counts[key] += 1
            return super().__getitem__(key)

    def route_rows_wrapper(*args: Any, **kwargs: Any) -> ReadCountingRouteMap:
        started = time.perf_counter()
        rows = original_route_rows(*args, **kwargs)
        telemetry["route_row_ms"] += (time.perf_counter() - started) * 1000
        counted = ReadCountingRouteMap(rows)
        telemetry["route_matrix_maps"].append(counted)
        return counted

    scheduling._route_rows = route_rows_wrapper
    wrap_simple("_make_candidates", "candidate_generation_ms", count_candidates=True)
    wrap_simple("_route_selected_stops", "route_ms")

    original_allocation = originals["solve_aggregate_allocation"]

    def allocation_wrapper(*args: Any, **kwargs: Any) -> Any:
        started = time.perf_counter()
        value = original_allocation(*args, **kwargs)
        elapsed = (time.perf_counter() - started) * 1000
        telemetry["allocation_wall_ms"] += elapsed
        telemetry["allocation_profiles"].append(value)
        return value

    scheduling.solve_aggregate_allocation = allocation_wrapper

    for name in ("_calculate_minimum_budget", "_minimum_capacity_diagnostic"):
        original = originals[name]

        def diagnostic_wrapper(*args: Any, _original=original, **kwargs: Any) -> Any:
            started = time.perf_counter()
            try:
                return _original(*args, **kwargs)
            finally:
                telemetry["diagnostic_ms"] += (time.perf_counter() - started) * 1000

        setattr(scheduling, name, diagnostic_wrapper)

    original_generate = originals["generate_provider_schedule"]

    def generate_wrapper(*args: Any, **kwargs: Any) -> Any:
        nonlocal depth
        call_depth = depth
        depth += 1
        try:
            result = original_generate(*args, **kwargs)
            telemetry["schedule_profiles"].append(
                {
                    "depth": call_depth,
                    "solver_profile": result.get("solver_profile") or {},
                    "decomposition": result.get("decomposition") or {},
                    "status": result.get("solver_status"),
                }
            )
            return result
        finally:
            depth -= 1

    scheduling.generate_provider_schedule = generate_wrapper

    try:
        variant, profile = SCENARIOS[scenario_name]
        with tempfile.TemporaryDirectory(prefix="vc-v51-benchmark-") as temporary:
            areas, providers, connection, budget, policy, fallback, metadata = (
                generate_scenario_data(
                    areas_n,
                    providers_n,
                    variant,
                    seed,
                    Path(temporary) / "routes.sqlite",
                    profile=profile,
                )
            )
            input_fingerprint = deterministic_scenario_fingerprint(
                areas,
                providers,
                budget,
                policy,
                connection,
                seed=seed,
                variant=f"{scenario_name}:{variant}",
            )
            if strategy["route_strategy"] == "joint":
                candidates, _blocked = originals["_make_candidates"](
                    areas,
                    providers,
                    originals["_route_rows"](connection),
                    policy,
                    None,
                    allow_route_fallback=fallback,
                )
                predicted_arcs = scheduling._estimated_route_arcs(candidates)
                if predicted_arcs > JOINT_MAX_PREDICTED_ARCS:
                    connection.close()
                    return (
                        {
                            "solver_status": "SKIPPED_PREDICTED_BUILD_TOO_LARGE",
                            "optimality_proven": False,
                            "plan_found": False,
                            "invariant_valid": None,
                            "predicted_route_arcs": predicted_arcs,
                            "candidate_edges": len(candidates),
                        },
                        telemetry,
                        {"input_fingerprint": input_fingerprint, "metadata": metadata},
                    )
            started = time.perf_counter()
            result = scheduling.generate_provider_schedule(
                areas,
                providers,
                connection,
                budget,
                "balanced",
                policy,
                allow_route_fallback=fallback,
                include_timing=True,
                max_solver_seconds=seconds,
                include_profile=True,
                **strategy,
            )
            generation_ms = (time.perf_counter() - started) * 1000
            check_started = time.perf_counter()
            check = verify_invariants(
                result,
                areas,
                providers,
                budget,
                connection,
                allow_route_fallback=fallback,
            )
            invariant_ms = (time.perf_counter() - check_started) * 1000
            connection.close()
        telemetry["preprocess_ms"] = (
            telemetry["route_row_ms"] + telemetry["candidate_generation_ms"]
        )
        route_lookup_counts = Counter()
        for route_map in telemetry["route_matrix_maps"]:
            route_lookup_counts.update(route_map.lookup_counts)
        route_lookup_count = sum(route_lookup_counts.values())
        route_lookup_unique_count = len(route_lookup_counts)
        route_matrix_cache_hits = sum(
            count
            for route_map in telemetry["route_matrix_maps"]
            for pair, count in route_map.lookup_counts.items()
            if dict.__contains__(route_map, pair)
        )
        route_matrix_cache_misses = route_lookup_count - route_matrix_cache_hits
        geographic_reconciliation = result.get("geographic_reconciliation", {})
        rolling_windows = result.get("rolling_horizon", {}).get("windows", [])
        record = {
            "solver_status": result.get("solver_status"),
            "optimality_proven": result.get("optimality_proven"),
            "strategy_used": result.get("strategy_used"),
            "fallback_used": result.get("fallback_used", False),
            "fallback_reason": result.get("fallback_reason"),
            "geographic_global_checks": result.get("geographic_reconciliation", {}).get(
                "global_reconciliation_checks"
            ),
            "heuristic_candidate_pruning_used": result.get(
                "geographic_reconciliation", {}
            ).get(
                "heuristic_candidate_pruning_used",
                any(window.get("heuristic_candidate_pruning_used") for window in rolling_windows),
            ),
            "pruned_hard_compatible_pair_count": geographic_reconciliation.get(
                "pruned_hard_compatible_pair_count",
                sum(
                    int(window.get("pruned_hard_compatible_pair_count", 0))
                    for window in rolling_windows
                ),
            ),
            "rolling_window_summaries": [
                {
                    "solver_status": window.get("solver_status"),
                    "strategy_used": window.get("strategy_used"),
                    "fallback_used": window.get("fallback_used"),
                    "heuristic_candidate_pruning_used": window.get(
                        "heuristic_candidate_pruning_used", False
                    ),
                    "pruned_hard_compatible_pair_count": window.get(
                        "pruned_hard_compatible_pair_count", 0
                    ),
                    "committed_round_count": window.get("committed_round_count"),
                }
                for window in rolling_windows
            ],
            "rolling_quality_regressions": result.get("rolling_horizon", {}).get(
                "quality_regressions", []
            ),
            "rolling_attempt_quality": result.get("rolling_horizon", {}).get(
                "rolling_attempt_quality"
            ),
            "rolling_boundary_zero_service_rate": result.get("rolling_horizon", {}).get(
                "boundary_zero_service_rate"
            ),
            "rolling_non_boundary_zero_service_rate": result.get(
                "rolling_horizon", {}
            ).get("non_boundary_zero_service_rate"),
            "rolling_late_horizon_zero_service_rate": result.get(
                "rolling_horizon", {}
            ).get("late_horizon_zero_service_rate"),
            "plan_found": bool(result.get("rounds")),
            "invariant_valid": check["passed"],
            "invariant_violations": check["violations"],
            "generation_ms": round(generation_ms, 2),
            "invariant_check_ms": round(invariant_ms, 2),
            "route_matrix_pair_lookup_count": route_lookup_count,
            "route_matrix_pair_lookup_unique_count": route_lookup_unique_count,
            "route_matrix_pair_lookup_repeated_count": max(
                0, route_lookup_count - route_lookup_unique_count
            ),
            "route_matrix_cache_hits": route_matrix_cache_hits,
            "route_matrix_cache_misses": route_matrix_cache_misses,
            "external_map_api_requests": 0,
            "total_ms": round(generation_ms + invariant_ms, 2),
            "candidate_edges": max(telemetry["candidate_counts"], default=0),
            "service_rounds": len(result.get("rounds", [])),
            "covered_areas": result.get("covered_areas"),
            "zero_service_areas": result.get("uncovered_areas"),
            "underserved_points_covered": (result.get("underserved_outcome") or {}).get(
                "underserved_points_covered"
            ),
            "underserved_points_total": (result.get("underserved_outcome") or {}).get(
                "underserved_points_total"
            ),
            "long_unserved_areas_served": (result.get("underserved_outcome") or {}).get(
                "excluded_areas_served_count"
            ),
            "minimum_coverage_met": result.get("minimum_coverage_met"),
            "travel_time": result.get("travel_time_s"),
            "travel_cost": result.get("travel_cost_won"),
            "total_cost": result.get("total_cost_won"),
            "budget_gap": result.get("budget_gap_won"),
            "minimum_capacity_diagnostic": result.get("minimum_capacity_diagnostic"),
            "boundary_zero_service_rate": (
                result.get("geographic_reconciliation", {}).get(
                    "boundary_zero_service_rate"
                )
                if result.get("geographic_reconciliation")
                else result.get("rolling_horizon", {}).get("boundary_zero_service_rate")
            ),
            "non_boundary_zero_service_rate": (
                result.get("geographic_reconciliation", {}).get(
                    "non_boundary_zero_service_rate"
                )
                if result.get("geographic_reconciliation")
                else result.get("rolling_horizon", {}).get(
                    "non_boundary_zero_service_rate"
                )
            ),
        }
        return record, telemetry, {
            "input_fingerprint": input_fingerprint,
            "metadata": metadata,
            "result": result,
        }
    finally:
        for name, original in originals.items():
            setattr(scheduling, name, original)


def _row(
    areas_n: int,
    providers_n: int,
    scenario_name: str,
    strategy_name: str,
    repeat: int,
    seed: int,
    seconds: float,
) -> dict[str, Any]:
    strategy = STRATEGIES[strategy_name]
    result, telemetry, extras = _instrumented_run(
        areas_n,
        providers_n,
        scenario_name,
        strategy_name,
        strategy,
        seed,
        seconds,
    )
    profiles = telemetry["schedule_profiles"]
    solver_profiles = [
        item["solver_profile"] for item in profiles if item.get("solver_profile")
    ]
    allocation_profiles = telemetry["allocation_profiles"]
    model_build_ms = sum(float(item.get("build_ms") or 0) for item in solver_profiles)
    solver_ms = sum(float(item.get("solve_ms") or 0) for item in solver_profiles)
    variables = sum(int(item.get("model_variable_count") or 0) for item in solver_profiles)
    constraints = sum(int(item.get("model_constraint_count") or 0) for item in solver_profiles)
    route_arcs = sum(int(item.get("route_edge_variable_count") or 0) for item in solver_profiles)
    variables += sum(int(item.get("variable_count") or 0) for item in allocation_profiles)
    constraints += sum(int(item.get("constraint_count") or 0) for item in allocation_profiles)
    is_geographic = strategy_name.startswith("S2_") or strategy_name.startswith("S4_")
    reconciliation_ms = telemetry["allocation_wall_ms"] if is_geographic else 0.0
    if not is_geographic:
        solver_ms += telemetry["allocation_wall_ms"]
    known_phase_ms = (
        telemetry["preprocess_ms"]
        + telemetry["route_ms"]
        + reconciliation_ms
        + model_build_ms
        + solver_ms
        + float(telemetry["diagnostic_ms"])
    )
    generation_ms = float(result.get("generation_ms") or 0)
    schedule_ms = max(0.0, generation_ms - known_phase_ms)
    decomposition = extras.get("result", {}).get("geographic_reconciliation", {})
    rolling_windows = extras.get("result", {}).get("rolling_horizon", {}).get("windows", [])
    cluster_count = decomposition.get("cluster_count")
    if cluster_count is None and rolling_windows:
        cluster_counts = [
            item.get("cluster_count")
            for item in rolling_windows
            if item.get("cluster_count") is not None
        ]
        cluster_count = max(cluster_counts, default=0) or None
    return {
        "scenario_id": f"{scenario_name.lower()}-{areas_n}-{providers_n}-seed{seed}",
        "scenario": scenario_name,
        "strategy": strategy_name,
        "areas": areas_n,
        "providers": providers_n,
        "cluster_count": cluster_count,
        "horizon_config": (
            json.dumps(strategy["rolling_config"].__dict__, sort_keys=True)
            if strategy.get("rolling_config")
            else "FULL_MONTH"
        ),
        "repeat": repeat,
        "seed": seed,
        "input_fingerprint": extras["input_fingerprint"],
        "model_build_ms": round(model_build_ms, 2),
        "preprocess_ms": round(telemetry["preprocess_ms"], 2),
        "solve_ms": round(solver_ms, 2),
        "reconciliation_ms": round(reconciliation_ms, 2),
        "schedule_ms": round(schedule_ms, 2),
        "route_ms": round(telemetry["route_ms"], 2),
        "total_ms": result.get("total_ms"),
        "variables": variables,
        "constraints": constraints,
        "candidate_edges": result.get("candidate_edges"),
        "route_arcs": route_arcs or result.get("predicted_route_arcs", 0),
        "solver_status": result.get("solver_status"),
        "optimality_proven": result.get("optimality_proven"),
        "strategy_used": result.get("strategy_used"),
        "fallback_used": result.get("fallback_used", False),
        "fallback_reason": result.get("fallback_reason"),
        "service_rounds": result.get("service_rounds"),
        "covered_areas": result.get("covered_areas"),
        "zero_service_areas": result.get("zero_service_areas"),
        "underserved_points_covered": result.get("underserved_points_covered"),
        "underserved_points_total": result.get("underserved_points_total"),
        "long_unserved_areas_served": result.get("long_unserved_areas_served"),
        "minimum_coverage_met": result.get("minimum_coverage_met"),
        "travel_time": result.get("travel_time"),
        "travel_cost": result.get("travel_cost"),
        "total_cost": result.get("total_cost"),
        "budget_gap": result.get("budget_gap"),
        "invariant_valid": result.get("invariant_valid"),
        "invariant_violations": result.get("invariant_violations", []),
        "geographic_global_checks": result.get("geographic_global_checks"),
        "route_matrix_pair_lookup_count": result.get("route_matrix_pair_lookup_count"),
        "route_matrix_pair_lookup_unique_count": result.get(
            "route_matrix_pair_lookup_unique_count"
        ),
        "route_matrix_pair_lookup_repeated_count": result.get(
            "route_matrix_pair_lookup_repeated_count"
        ),
        "route_matrix_cache_hits": result.get("route_matrix_cache_hits"),
        "route_matrix_cache_misses": result.get("route_matrix_cache_misses"),
        "external_map_api_requests": result.get("external_map_api_requests"),
        "heuristic_candidate_pruning_used": result.get(
            "heuristic_candidate_pruning_used", False
        ),
        "pruned_hard_compatible_pair_count": result.get(
            "pruned_hard_compatible_pair_count", 0
        ),
        "rolling_window_summaries": result.get("rolling_window_summaries", []),
        "rolling_quality_regressions": result.get("rolling_quality_regressions", []),
        "rolling_attempt_quality": result.get("rolling_attempt_quality"),
        "rolling_boundary_zero_service_rate": result.get(
            "rolling_boundary_zero_service_rate"
        ),
        "rolling_non_boundary_zero_service_rate": result.get(
            "rolling_non_boundary_zero_service_rate"
        ),
        "rolling_late_horizon_zero_service_rate": result.get(
            "rolling_late_horizon_zero_service_rate"
        ),
        "boundary_zero_service_rate": result.get("boundary_zero_service_rate"),
        "non_boundary_zero_service_rate": result.get("non_boundary_zero_service_rate"),
        "diagnostics_ms": round(float(telemetry["diagnostic_ms"]), 2),
        "input_provenance": "SYNTHETIC_GENERATOR_AND_SYNTHETIC_ROAD_EDGES",
    }


def _write_artifacts(
    rows: list[dict[str, Any]], report: dict[str, Any], output_stem: str
) -> None:
    output_dir = ROOT / "artifacts"
    output_dir.mkdir(exist_ok=True)
    json_path = output_dir / f"{output_stem}.json"
    csv_path = output_dir / f"{output_stem}.csv"
    report["rows"] = rows
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    columns = list(rows[0]) if rows else []
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for item in rows:
            encoded = dict(item)
            encoded["invariant_violations"] = "; ".join(item["invariant_violations"])
            for key, value in encoded.items():
                if isinstance(value, (dict, list)):
                    encoded[key] = json.dumps(value, ensure_ascii=False, sort_keys=True)
            writer.writerow(encoded)


def _summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, int, int, str], list[dict[str, Any]]] = defaultdict(list)
    for item in rows:
        groups[(item["strategy"], item["areas"], item["providers"], item["scenario"])].append(
            item
        )
    summaries = []
    for (strategy, areas, providers, scenario), group in sorted(groups.items()):
        timing = [float(item["total_ms"]) for item in group if item.get("total_ms") is not None]
        summaries.append(
            {
                "strategy": strategy,
                "areas": areas,
                "providers": providers,
                "scenario": scenario,
                "repeats": len(timing),
                "total_ms_median": statistics.median(timing) if timing else None,
                "statuses": [item.get("solver_status") for item in group],
                "all_invariants_valid": all(item.get("invariant_valid") for item in group),
                "minimum_coverage_met_runs": sum(
                    item.get("minimum_coverage_met") is True for item in group
                ),
                "fallback_runs": sum(bool(item.get("fallback_used")) for item in group),
                "quality_medians": {
                    key: statistics.median(
                        [float(item[key]) for item in group if item.get(key) is not None]
                    )
                    if any(item.get(key) is not None for item in group)
                    else None
                    for key in (
                        "service_rounds",
                        "covered_areas",
                        "zero_service_areas",
                        "underserved_points_covered",
                        "long_unserved_areas_served",
                        "travel_time",
                        "travel_cost",
                        "total_cost",
                    )
                },
            }
        )
    baselines = {
        (item["areas"], item["providers"], item["scenario"]): item
        for item in summaries
        if item["strategy"] == "S1_V5_BASELINE"
    }
    for item in summaries:
        baseline = baselines.get((item["areas"], item["providers"], item["scenario"]))
        if baseline is None or item["strategy"] == "S1_V5_BASELINE":
            continue
        current_quality = item["quality_medians"]
        baseline_quality = baseline["quality_medians"]

        def percent_delta(
            field: str,
            _baseline_quality=baseline_quality,
            _current_quality=current_quality,
        ) -> float | None:
            baseline_value = _baseline_quality.get(field)
            current_value = _current_quality.get(field)
            if baseline_value is None or current_value is None or baseline_value == 0:
                return None
            return round((current_value - baseline_value) / abs(baseline_value) * 100, 2)

        item["vs_baseline"] = {
            "runtime_delta_pct": (
                round(
                    (item["total_ms_median"] - baseline["total_ms_median"])
                    / abs(baseline["total_ms_median"])
                    * 100,
                    2,
                )
                if item["total_ms_median"] is not None
                and baseline["total_ms_median"] not in (None, 0)
                else None
            ),
            "service_rounds_delta_pct": percent_delta("service_rounds"),
            "covered_areas_delta": (
                current_quality["covered_areas"] - baseline_quality["covered_areas"]
                if current_quality.get("covered_areas") is not None
                and baseline_quality.get("covered_areas") is not None
                else None
            ),
            "zero_service_areas_delta": (
                current_quality["zero_service_areas"] - baseline_quality["zero_service_areas"]
                if current_quality.get("zero_service_areas") is not None
                and baseline_quality.get("zero_service_areas") is not None
                else None
            ),
            "underserved_points_delta": (
                current_quality["underserved_points_covered"]
                - baseline_quality["underserved_points_covered"]
                if current_quality.get("underserved_points_covered") is not None
                and baseline_quality.get("underserved_points_covered") is not None
                else None
            ),
            "travel_time_delta_pct": percent_delta("travel_time"),
            "travel_cost_delta_pct": percent_delta("travel_cost"),
            "total_cost_delta_pct": percent_delta("total_cost"),
            "minimum_coverage_met_delta_runs": (
                item["minimum_coverage_met_runs"] - baseline["minimum_coverage_met_runs"]
            ),
        }
    return summaries


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=float, default=2.5)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--scenarios", default=",".join(SCENARIOS))
    parser.add_argument("--strategies", default=",".join(STRATEGIES))
    parser.add_argument("--sizes", default=",".join(str(a) for a, _ in CASES))
    parser.add_argument("--max-cases", type=int, default=0)
    parser.add_argument("--output-stem", default="solver_benchmark_v5_1")
    args = parser.parse_args()
    scenario_names = [item.strip().upper() for item in args.scenarios.split(",")]
    strategy_names = [item.strip().upper() for item in args.strategies.split(",")]
    sizes = {int(item) for item in args.sizes.split(",")}
    unknown_scenarios = set(scenario_names) - set(SCENARIOS)
    unknown_strategies = set(strategy_names) - set(STRATEGIES)
    if unknown_scenarios or unknown_strategies or args.repeats < 1 or args.seconds <= 0:
        parser.error(
            f"invalid input: scenarios={sorted(unknown_scenarios)}, "
            f"strategies={sorted(unknown_strategies)}, repeats={args.repeats}"
        )
    run_matrix = [
        (areas_n, providers_n, scenario_name, strategy_name, repeat)
        for areas_n, providers_n in CASES
        if areas_n in sizes
        for scenario_name in scenario_names
        for strategy_name in strategy_names
        for repeat in range(1, args.repeats + 1)
    ]
    if args.max_cases > 0:
        run_matrix = run_matrix[: args.max_cases]
    rows: list[dict[str, Any]] = []
    report = {
        "schema": "village-coverage-solver-benchmark-v5.1-v1",
        "generated_at_utc": utc_now(),
        "solver_limit_seconds_per_window": args.seconds,
        "repeats_per_case": args.repeats,
        "seed": REFERENCE_SEED,
        "scenario_names": scenario_names,
        "strategy_names": strategy_names,
        "case_matrix": [
            {"areas": areas, "providers": providers}
            for areas, providers in CASES
            if areas in sizes
        ],
        "provenance": "SYNTHETIC_INPUTS_AND_SYNTHETIC_ROAD_EDGES; NOT FIELD PERFORMANCE",
        "unknown_and_time_limit_are_not_pass": True,
        "rows": rows,
    }
    _write_artifacts(rows, report, args.output_stem)
    for areas_n, providers_n, scenario_name, strategy_name, repeat in run_matrix:
        seed = REFERENCE_SEED + areas_n * 1000 + providers_n * 10 + list(SCENARIOS).index(
            scenario_name
        )
        item = _row(
            areas_n,
            providers_n,
            scenario_name,
            strategy_name,
            repeat,
            seed,
            args.seconds,
        )
        rows.append(item)
        report["summary_medians"] = _summary(rows)
        _write_artifacts(rows, report, args.output_stem)
        print(
            item["scenario_id"],
            strategy_name,
            f"r{repeat}",
            item["solver_status"],
            item["total_ms"],
            item["invariant_valid"],
            flush=True,
        )
    report["completed_case_count"] = len(rows)
    report["requested_case_count"] = len(run_matrix)
    report["invariant_violation_count"] = sum(
        len(item.get("invariant_violations", [])) for item in rows
    )
    report["complete_matrix"] = len(rows) == len(run_matrix)
    report["summary_medians"] = _summary(rows)
    _write_artifacts(rows, report, args.output_stem)
    return 0 if report["complete_matrix"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
