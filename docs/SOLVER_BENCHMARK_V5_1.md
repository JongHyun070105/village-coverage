# Solver Benchmark V5.1

## Reproducibility

`scripts/run_solver_benchmark_v5_1.py` writes `artifacts/solver_benchmark_v5_1.json` and `.csv`. It uses deterministic synthetic scenario inputs and synthetic route-cache edges. Every strategy for a scenario uses the same generated seed, road snapshot, providers, policy, and budget. The default matrix runs three repeats for:

- areas/providers: 16/3, 30/5, 50/5, 100/10, 200/20;
- workloads: NORMAL, TIGHT_BUDGET, PROVIDER_SHORTAGE, REMOTE_AREAS, MANY_LOW_DATA, HOME_REPAIR_MIXED, MASS_DECLINE;
- architectures: monolithic, V5 baseline, administrative/distance/provider-reachability/hybrid geographic clusters, rolling 7/21, rolling 7/14, rolling 14/14, and hybrid-geographic+rolling 7/21 and 14/14.

The solver time budget is passed unchanged to baseline/geographic models. Rolling windows divide the same configured solver budget over the commit windows. The 200-area monolithic case is skipped when the estimated route circuit exceeds 500,000 arcs; this status is reported rather than treated as a solve result.

## Metrics

The row schema separates model build, candidate/route preprocessing, CP-SAT solve, geographic reconciliation, scheduling residual, route reconstruction, and total generation plus invariant-check time. It records variable/constraint counts, candidate edges, route arcs, cluster count, horizon settings, status and optimality, service rounds, coverage/zeros, minimum coverage, underserved points and long-unserved areas served, travel, total cost, budget gap, and invariant validity. Geographic boundary and non-boundary zero-service rates and rolling late-horizon zero-service rate are also reported where applicable. Route-matrix pair lookups are instrumented as in-memory hits/misses; synthetic runs make zero external map API requests and report repeated pair lookups separately.

`OPTIMAL` means the solver proved the modeled subproblem optimum. `FEASIBLE` and `TIME_LIMIT` remain distinct. `UNKNOWN`, failed invariants, and skipped route models are not acceptance passes. A valid invariant result alone does not establish quality preservation or optimality.

## Commands

Full configured matrix:

```bash
uv run python scripts/run_solver_benchmark_v5_1.py
```

Bounded architecture comparison:

```bash
uv run python scripts/run_solver_benchmark_v5_1.py \
  --sizes 16,30,50,100,200 --scenarios NORMAL --repeats 3
```

The benchmark is intended to select a strategy per size only after median runtime and solution-quality results are available. Synthetic results do not establish real-road performance. External map API latency is excluded because no live API calls occur.
