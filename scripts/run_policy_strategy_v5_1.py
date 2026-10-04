"""Compare V5.1 solver strategies on the simulated Hongseong policy fixture."""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

POLICIES = ("efficiency", "balanced", "underserved_first", "minimum_coverage")
SOLVER_SECONDS = 2.5


def _strategy_rows() -> list[dict[str, Any]]:
    from backend.geographic_decomposition import ClusterConfig
    from backend.rolling_horizon import RollingHorizonConfig

    return [
        {"name": "S1_V5_BASELINE", "route_strategy": "decomposed"},
        {
            "name": "S2_GEOGRAPHIC_CLUSTER",
            "route_strategy": "decomposed",
            "planning_strategy": "geographic_cluster",
            "cluster_config": ClusterConfig(),
        },
        {
            "name": "S3_ROLLING_HORIZON_7_21",
            "route_strategy": "decomposed",
            "planning_strategy": "rolling_horizon",
            "rolling_config": RollingHorizonConfig(28, 7, 21),
        },
        {
            "name": "S3_ROLLING_HORIZON_7_14",
            "route_strategy": "decomposed",
            "planning_strategy": "rolling_horizon",
            "rolling_config": RollingHorizonConfig(21, 7, 14),
        },
        {
            "name": "S3_ROLLING_HORIZON_14_14",
            "route_strategy": "decomposed",
            "planning_strategy": "rolling_horizon",
            "rolling_config": RollingHorizonConfig(28, 14, 14),
        },
        {
            "name": "S4_GEOGRAPHIC_ROLLING_7_21",
            "route_strategy": "decomposed",
            "planning_strategy": "geographic_rolling",
            "rolling_config": RollingHorizonConfig(28, 7, 21),
            "cluster_config": ClusterConfig(),
        },
        {
            "name": "S4_GEOGRAPHIC_ROLLING_14_14",
            "route_strategy": "decomposed",
            "planning_strategy": "geographic_rolling",
            "rolling_config": RollingHorizonConfig(28, 14, 14),
            "cluster_config": ClusterConfig(enable_heuristic_candidate_pruning=True),
        },
    ]


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="vc-policy-strategy-v5-1-") as temporary:
        temporary_path = Path(temporary)
        os.environ["VILLAGECOVERAGE_APP_DB"] = str(temporary_path / "app.sqlite")
        travel_path = temporary_path / "travel.sqlite"
        source_path = ROOT / "data" / "village_coverage.sqlite"
        source = sqlite3.connect(f"file:{source_path}?mode=ro", uri=True)
        destination = sqlite3.connect(travel_path)
        try:
            source.backup(destination)
        finally:
            destination.close()
            source.close()
        os.environ["VILLAGE_COVERAGE_DB"] = str(travel_path)

        from backend import database, scheduling, underserved
        from backend.main import _load_demo, _prepare_planning_inputs
        from backend.regions import select_region
        from backend.settings import PlanningPolicy
        from backend.source_snapshots import utc_now
        from backend.timeutils import korea_today
        from backend.travel import connect
        from scripts.run_stress_tests import (
            deterministic_scenario_fingerprint,
            verify_invariants,
        )

        demo = _load_demo()
        region_id = str(demo.get("default_region_id", "pilot:legacy"))
        region_data = select_region(demo, region_id)
        app_connection = database.connect()
        try:
            database.seed_reference_data(app_connection, demo)
            database.seed_provider_data(app_connection, demo)
            underserved.seed_simulated_history(
                app_connection,
                region_data["areas"],
                as_of_month=underserved.current_month(korea_today()),
            )
            areas = region_data["areas"]
            providers = _prepare_planning_inputs(app_connection, region_data)
            travel_connection = connect(travel_path)
            input_fingerprint = deterministic_scenario_fingerprint(
                areas,
                providers,
                5_000_000,
                PlanningPolicy(),
                travel_connection,
                seed=20261005,
                variant="HONGSEONG_V5_1_POLICY_STRATEGY",
            )
            rows = []
            try:
                for policy_name in POLICIES:
                    for strategy in _strategy_rows():
                        started = time.perf_counter()
                        result = scheduling.generate_provider_schedule(
                            areas,
                            providers,
                            travel_connection,
                            5_000_000,
                            policy_name,
                            PlanningPolicy(),
                            max_solver_seconds=SOLVER_SECONDS,
                            include_timing=True,
                            include_profile=True,
                            **{key: value for key, value in strategy.items() if key != "name"},
                        )
                        total_ms = round((time.perf_counter() - started) * 1000, 2)
                        checks = verify_invariants(
                            result,
                            areas,
                            providers,
                            5_000_000,
                            travel_connection,
                            allow_route_fallback=False,
                        )
                        rolling = result.get("rolling_horizon", {})
                        rows.append(
                            {
                                "region_id": region_id,
                                "policy": policy_name,
                                "strategy": strategy["name"],
                                "areas": len(areas),
                                "providers": len(providers),
                                "budget_won": 5_000_000,
                                "solver_status": result.get("solver_status"),
                                "optimality_proven": result.get("optimality_proven"),
                                "strategy_used": result.get("strategy_used"),
                                "fallback_used": result.get("fallback_used", False),
                                "fallback_reason": result.get("fallback_reason"),
                                "total_ms": total_ms,
                                "model_build_ms": result.get("profile", {}).get(
                                    "model_build_ms"
                                ),
                                "solve_ms": result.get("solve_time_ms"),
                                "service_rounds": len(result.get("rounds", [])),
                                "covered_areas": result.get("covered_areas"),
                                "zero_service_areas": len(areas) - int(
                                    result.get("covered_areas", 0)
                                ),
                                "minimum_coverage_met": result.get("minimum_coverage_met"),
                                "underserved_points_covered": result.get(
                                    "underserved_outcome", {}
                                ).get("underserved_points_covered"),
                                "underserved_points_total": result.get(
                                    "underserved_outcome", {}
                                ).get("underserved_points_total"),
                                "travel_time": result.get("travel_time_s"),
                                "travel_cost": result.get("travel_cost_won"),
                                "total_cost": result.get("budget_spent_won"),
                                "budget_gap": result.get("budget_gap_won"),
                                "late_horizon_zero_service_rate": rolling.get(
                                    "late_horizon_zero_service_rate"
                                ),
                                "invariant_valid": checks["passed"],
                                "invariant_violations": checks["violations"],
                            }
                        )
            finally:
                travel_connection.close()
        finally:
            app_connection.close()

    report = {
        "generated_at_utc": utc_now(),
        "label": "SIMULATION; NOT FIELD PERFORMANCE",
        "provenance": (
            "PUBLIC HONGSEONG AREA AGGREGATES, SIMULATED PROVIDERS AND HISTORY, "
            "LOCAL ROAD CACHE; NO LIVE API REQUESTS"
        ),
        "repeats": 1,
        "solver_seconds_per_solve": SOLVER_SECONDS,
        "input_fingerprint": input_fingerprint,
        "invariant_violation_count": sum(
            len(row["invariant_violations"]) for row in rows
        ),
        "rows": rows,
    }
    output = ROOT / "artifacts" / "solver_policy_hongseong_v5_1.json"
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "rows": len(rows),
                "invariant_violation_count": report["invariant_violation_count"],
                "artifact": str(output.relative_to(ROOT)),
            },
            ensure_ascii=False,
        )
    )
    return 0 if report["invariant_violation_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
