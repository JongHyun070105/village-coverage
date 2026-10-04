# Solver Decomposition V5.1

## Scope

V5.1 keeps the existing V5 allocation and scheduling objectives. Geographic clusters generate smaller local proposals; every proposal is reconciled against the shared provider and budget resources, then the time indexed scheduler checks the merged candidate plan. A cluster is never treated as an independent budget or provider pool.

The implementation is in `backend/geographic_decomposition.py` and `backend/scheduling.py`.

## Deterministic partitioning

`build_geographic_partition` supports four reproducible strategies:

- `ADMINISTRATIVE_CLUSTER`: groups areas by available administrative identifiers and uses road proximity for missing identifiers.
- `DISTANCE_CLUSTER`: builds a symmetric threshold graph from directed cached road durations and partitions its connected components.
- `PROVIDER_REACHABILITY_CLUSTER`: connects areas that share at least one hard-compatible provider-area candidate.
- `HYBRID_CLUSTER`: connects areas with common administrative identifiers, or areas that are both road-close and provider-reachable.

The implementation uses sorted IDs, connected components, deterministic farthest-first medoid seeds, deterministic size-limited assignment, and nearest-group merging for undersized partitions when the maximum size permits. It adds no machine-learning clustering dependency. Unreachable road pairs do not become neighbors. The default limits are configurable through `ClusterConfig`: minimum 4, target 16, maximum 24 areas, 60 minutes, 3 provider candidates per area, and 0.1 seconds per local proposal. An isolated group can remain below the minimum when no legal merge fits under the maximum. These are starting benchmark parameters, not policy guarantees; the benchmark artifact records the tested settings and results.

By default, every hard-feasible provider-area pair remains available to global reconciliation. This is the safe production mode. The benchmark can explicitly enable the optional heuristic pair limit; boundary areas and areas without local proposals still retain every pair. Results record the count of hard-feasible pairs removed by that experimental limit. No provider is pinned to one cluster.

## Global reconciliation

The phase order is:

1. Generate hard-compatible provider-area-date candidates.
2. Solve one aggregate proposal per cluster, with all eligible providers available.
3. Build a global candidate pool and detect shared provider/month and budget conflicts.
4. Solve a global aggregate allocation over the candidate pool. The local allocations are CP-SAT hints, not fixed assignments.
5. Expand the candidate pool if reconciliation cannot retain a local target.
6. Run the global time-indexed schedule and route model against the reconciled provider-area pairs.
7. Independently check monthly provider rounds, minimum compensation, total cost, service compatibility, daily work/overlap, route coverage, and truthful minimum-coverage reporting.

The global schedule is authoritative. A failed reconciliation, route/schedule solve, or independent check invokes the verified V5 baseline and returns `strategy_used=BASELINE_FALLBACK`, `fallback_used=true`, and a reason. It does not turn a failed cluster proposal into a successful geographic result.

The result includes cluster sizes, local solver statuses, proposed and reconciled pair counts, shared-resource conflict flags, fallback details, and boundary/non-boundary zero-service rates. `GEOGRAPHIC_CLUSTER` results do not claim global optimality: their scope is the reconciled candidate subproblem.

## Candidate and route controls

Candidate generation removes only hard-infeasible provider-area-date combinations: unsupported service, provider participation/unavailability, incompatible requested dates or time windows, missing required hub legs, maximum travel time, and daily work-limit violations. Directed road-cache pairs are read once per solve; route-neighbor sets and location-matrix completeness are cached. The route model still uses exact available cached legs and the existing hub fallback policy.

The default geographic candidate pool does not remove hard-feasible pairs. The benchmark-only heuristic pair limit can reduce provider-area choices for non-boundary areas; these runs are explicitly marked and cannot establish pruning safety. The final scheduler enforces date-level capacity, provider hours, no-overlap, budget, compensation, service units, and route feasibility globally. The benchmark compares rounds, coverage, zeros, travel, and cost as well as runtime; faster but lower-quality plans are not accepted as equivalent.

## Run and inspect

```bash
uv run pytest -q tests/test_geographic_decomposition.py tests/test_solver_decomposition.py
uv run python scripts/run_solver_benchmark_v5_1.py --scenarios NORMAL --repeats 3
```

The benchmark uses synthetic fixtures and synthetic road edges. It is solver evidence, not field performance evidence. `TIME_LIMIT`, `UNKNOWN`, and skipped monolithic builds remain visible and are never converted to `OPTIMAL`.
