"""Solver decomposition benchmark with build/solve profiling (V5 §35-§40).

Strategies on representative 16/30/50/100/200-area synthetic cases:

A. JOINT_MONOLITHIC   - V3 integrated provider-day circuit model
B. TWO_STAGE          - time-indexed round-trip schedule, then post-solve routing
C. THREE_STAGE        - aggregate allocation -> time-indexed schedule -> routing
D. GEOGRAPHIC_CLUSTER - not implemented (budget couples clusters; see report)
E. ROLLING_HORIZON    - not implemented (monthly guarantee spans the horizon)

Every run uses the same per-solve limit; wall and deterministic time are both
reported. Usage: uv run python scripts/run_solver_benchmark.py [--seconds 2.5]
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend import scheduling  # noqa: E402
from backend.source_snapshots import utc_now  # noqa: E402
from scripts.run_stress_tests import (  # noqa: E402
    REFERENCE_SEED,
    generate_scenario_data,
    verify_invariants,
)

CASES = ((16, 3), (30, 5), (50, 5), (100, 10), (200, 20))
STRATEGIES = {
    "A_JOINT_MONOLITHIC": {"route_strategy": "joint"},
    "B_TWO_STAGE_SCHEDULE_THEN_ROUTE": {"route_strategy": "decomposed",
                                        "use_allocation_stage": False},
    "C_THREE_STAGE_ALLOCATE_SCHEDULE_ROUTE": {"route_strategy": "decomposed"},
}
JOINT_MAX_PREDICTED_ARCS = 500_000  # beyond this the joint build alone exceeds minutes


def run_case(areas_n: int, providers_n: int, name: str, kwargs: dict, seconds: float,
             scenario: str) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        areas, providers, connection, budget, policy, fallback, _ = generate_scenario_data(
            areas_n, providers_n, "A", REFERENCE_SEED, Path(tmp) / "bench.sqlite")
        try:
            if kwargs["route_strategy"] == "joint":
                candidates, _ = scheduling._make_candidates(
                    areas, providers, scheduling._route_rows(connection), policy, None,
                    allow_route_fallback=fallback)
                arcs = scheduling._estimated_route_arcs(candidates)
                if arcs > JOINT_MAX_PREDICTED_ARCS:
                    return {"status": "SKIPPED_PREDICTED_BUILD_TOO_LARGE",
                            "predicted_route_arcs": arcs, "candidates": len(candidates)}
            started = time.perf_counter()
            result = scheduling.generate_provider_schedule(
                areas, providers, connection, budget, scenario, policy,
                allow_route_fallback=fallback, include_timing=True,
                max_solver_seconds=seconds, include_profile=True, **kwargs)
            elapsed = round((time.perf_counter() - started) * 1000, 1)
            check = verify_invariants(result, areas, providers, budget, connection,
                                      allow_route_fallback=fallback)
        finally:
            connection.close()
    profile = result.get("solver_profile") or {}
    decomposition = result.get("decomposition") or {}
    return {
        "status": result["solver_status"],
        "optimality_proven": result["optimality_proven"],
        "optimality_scope": result.get("optimality_scope"),
        "plan_found": bool(result.get("rounds")),
        "invariants_passed": check["passed"],
        "served_units": result["served_units"],
        "covered_areas": result["covered_areas"],
        "budget_spent_won": result["budget_spent_won"],
        "elapsed_ms_including_diagnostics": elapsed,
        "stage_a_ms": decomposition.get("stage_a_ms"),
        "stage_a_status": decomposition.get("stage_a_status"),
        **{key: profile.get(key) for key in (
            "build_ms", "solve_ms", "candidate_variable_count", "model_variable_count",
            "model_constraint_count", "route_edge_variable_count", "provider_day_combinations",
            "solver_branches", "solver_conflicts")},
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=float, default=2.5)
    parser.add_argument("--scenario", default="balanced")
    parser.add_argument(
        "--output", default="artifacts/solver_benchmark.json",
        help="write to a separate path to preserve earlier benchmark evidence",
    )
    args = parser.parse_args()
    rows = []
    for areas_n, providers_n in CASES:
        for name, kwargs in STRATEGIES.items():
            record = run_case(areas_n, providers_n, name, kwargs, args.seconds, args.scenario)
            rows.append({"areas": areas_n, "providers": providers_n, "strategy": name,
                         **record})
            print(areas_n, providers_n, name, record.get("status"),
                  record.get("served_units"), record.get("elapsed_ms_including_diagnostics"),
                  flush=True)
    report = {
        "generated_at": utc_now(),
        "scenario": args.scenario,
        "seconds_per_solve": args.seconds,
        "seed": REFERENCE_SEED,
        "provenance": "SYNTHETIC_SCENARIO_GENERATOR; SYNTHETIC ROUTE EDGES FOR STRESS ONLY",
        "strategies": list(STRATEGIES),
        "not_implemented": {
            "D_GEOGRAPHIC_CLUSTERING": (
                "공급자 예산·월 회차 한도가 군집 간에 공유되어 군집별 독립 해의 합이 실행가능성을 "
                "보장하지 않음; 조정(reconciliation) 단계 설계는 후속 과제."
            ),
            "E_ROLLING_HORIZON": (
                "최소보장(월 1회 이상)과 예산이 4주 전체에 걸린 제약이라 기간 분할 시 "
                "앞 구간 결정이 뒤 구간 보장을 해칠 수 있음; 후속 과제."
            ),
        },
        "warm_start": (
            "THREE_STAGE는 집계 최적해(stage A)를 시간색인 모델에 목표값 고정 탐색으로 전달하는 "
            "warm start를 사용. 재계획은 이전 계획의 제공자·권역·일자 후보를 CP-SAT hint에 "
            "우선 반영하고, 용량·예산·경로 제약을 유지합니다."
        ),
        "rows": rows,
    }
    out = Path(args.output)
    if not out.is_absolute():
        out = ROOT / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
