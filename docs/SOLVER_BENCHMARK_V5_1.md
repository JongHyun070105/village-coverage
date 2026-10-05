# Solver Benchmark V5.1

## Baseline profile and bottleneck

`artifacts/solver_profile_v5_1_baseline.json` and `artifacts/solver_profile_v5_1_after.json` contain three-repeat profiles for the 16/30/50/100/200-area V5 allocation→scheduling path. They separate model build, preprocessing, CP-SAT solve, scheduling, route reconstruction, diagnostics, and invariant check. The dominant V5 cost was not road routing: route reconstruction was milliseconds. At 30–100 areas the nested minimum-budget diagnostic added seconds (4.48/4.29/6.35 seconds at 30/50/100); at 200 areas the time-indexed scheduling path itself dominated.

| Areas | V5 baseline total | Profiled V5.1 total | Change | Target |
|---:|---:|---:|---:|---:|
| 16 | 1,536.58 ms | 1,421.18 ms | -7.5% | < 2 s |
| 30 | 6,576.33 ms | 2,649.82 ms | -59.7% | < 4 s |
| 50 | 8,050.23 ms | 4,816.49 ms | -40.2% | < 6 s |
| 100 | 10,715.40 ms | 5,066.30 ms | -52.7% | < 10 s |
| 200 | 16,357.24 ms | 5,368.60 ms | -67.2% | <= 15 s or meaningful improvement |

The V5.1 profile removes repeated expensive minimum-budget solves from the ordinary path and reports the bounded diagnostic as `NOT_PROVEN` where an exact proof is not available. It also reuses provider/preference preprocessing and route-neighbor/completeness data. No solver time limit was increased. Per profile, S1 met all five timing targets. The 50/100/200 statuses remain `TIME_LIMIT`; time compliance is not optimality.

## Comparative methodology

`scripts/run_solver_benchmark_v5_1.py` creates deterministic synthetic scenarios and road-cache edges. Across strategies, the same size/scenario repeat uses the same input fingerprint, seed, simulated providers, policy, budget, and local road snapshot. There are seven workload types: NORMAL, TIGHT_BUDGET, PROVIDER_SHORTAGE, REMOTE_AREAS, MANY_LOW_DATA, HOME_REPAIR_MIXED, and MASS_DECLINE. The main matrix has 525 rows: 5 sizes × 7 workloads × 5 strategies × 3 repeats. It records model-build, preprocessing, solve, reconciliation, scheduling, route, diagnostics, total, variables, constraints, candidate edges, route arcs, cache hits/misses, quality, status, and invariants. External map API requests are zero.

The 200-area monolithic route model is skipped when predicted route arcs exceed 500,000 (21 rows); it is `SKIPPED_PREDICTED_BUILD_TOO_LARGE`, not a solve. Full JSON and CSV: `artifacts/solver_benchmark_v5_1.json` and `.csv`. The rows for S3/S4 7/21 were refreshed after adding the minimum-coverage reference fallback; the artifact records the source fingerprint and six semantic corrections for empty `UNKNOWN` route checks. Their solver status remains `UNKNOWN`.

An additional 90-row NORMAL matrix compares administrative/distance/provider-reachability clusters and the 7/14, 14/14, and geographic 14/14 alternatives. Full results: `artifacts/solver_benchmark_v5_1_variants_final.json` and `.csv`.

## Strategy results and selection

The following values are means of the seven workload repeat medians; they describe synthetic workloads, not a field service region.

| Areas | V5 baseline seconds / covered / zero | Geographic seconds / covered / zero | Rolling 7/21 seconds / covered / zero | Geographic rolling seconds / covered / zero |
|---:|---:|---:|---:|---:|
| 16 | 2.82 / 11.43 / 4.57 | 3.58 / 10.57 / 5.43 | 3.77 / 11.43 / 4.57 | 9.62 / 11.14 / 4.86 |
| 30 | 3.43 / 21.00 / 9.00 | 4.90 / 17.14 / 12.86 | 10.41 / 21.00 / 9.00 | 20.73 / 19.57 / 10.43 |
| 50 | 3.96 / 31.86 / 18.14 | 6.07 / 24.14 / 25.86 | 11.84 / 31.86 / 18.14 | 25.91 / 28.57 / 21.43 |
| 100 | 4.54 / 55.00 / 45.00 | 7.55 / 36.86 / 63.14 | 16.16 / 55.71 / 44.29 | 38.05 / 55.29 / 44.71 |
| 200 | 4.65 / 58.71 / 141.29 | 10.18 / 38.43 / 161.57 | 15.69 / 62.43 / 137.57 | 37.37 / 64.71 / 135.29 |

The geographic-only solver loses coverage and increases zeros at every tested size, so it is not selected. Rolling variants are generally slower and often incur labelled baseline fallbacks. The evidence-based strategy choice is V5 `S1_V5_BASELINE` for 16–200 areas; this is not an AUTO crossover claim. The 200-area NORMAL rows are `UNKNOWN` with zero assignments for all four strategies. They are not passes even though invariant checks can be valid for an empty output.

NORMAL-only horizon medians at 16/30/50/100/200 areas were 5.98/10.31/11.61/19.89/19.74 seconds for S3 7/14; 4.35/10.40/10.14/14.75/8.12 seconds for S3 14/14; and 11.00/22.02/18.08/24.76/31.28 seconds for S4 14/14. The S3 200-area results are `UNKNOWN`. Alternative cluster topology runs had equivalent coverage/runtime patterns and no topology qualified for selection.

`TIME_LIMIT`, `UNKNOWN`, and skipped cases remain separate from successful solve evidence. Status counts in the 525-row matrix are 99 `OPTIMAL`, 42 `FEASIBLE`, 310 `TIME_LIMIT`, 53 `UNKNOWN`, and 21 skipped. There were zero invariant violations in measured solve rows (504 invariant-valid rows; skipped rows have no invariant verdict).

## Candidate pruning, route arcs, and caches

Hard candidate filters remove incompatible provider-area-date pairs before allocation/scheduling, based on supported service, availability/participation, requested windows, required route legs, maximum travel, and daily work. Every remaining hard-feasible pair stays available to default reconciliation. The optional heuristic candidate cap is off in selected strategies. Its labelled experimental 14/14 geographic variant removed 5,226 hard-compatible pairs across 15 synthetic runs; this variant is not evidence that heuristic pruning is safe. Route-arc estimates and pair-cache hits/misses are stored per row. A cached local-road benchmark makes no API request and cannot measure live map latency.

## Rolling, policy, and replan evidence

The rolling-state tests cover remaining budget and capacity, minimum obligations, underserved history, warm hints, and fallback. In the 16-area Hongseong aggregate simulation at ₩5,000,000 (fingerprint `5016a03465280e8c6db3dc04ce4390d1d096f343a675ba37192a997901bbf393`), all seven strategies preserved all areas, zero zero-service areas, all 14 underserved points, and minimum coverage for both UNDERSERVED_FIRST and MINIMUM_GUARANTEE; invariant violations were zero. Some strategies returned an explicit baseline fallback. The result is local simulation, not field evidence. The historical V5 request-count-only comparison (13 zero-service areas) used a different experiment snapshot and is not mixed into this same-input comparison.

The current-tree cold/warm replan benchmark has 18 synthetic cases: 16 produced invariant-valid replans; two route-unavailable cases correctly failed closed as `NOT_VERIFIABLE`; invariant violations were zero. For the 16 comparable cases, mean cold/warm runtimes were 2.94/2.86 seconds, and mean assignment-change rates were 1.192/1.142. The average stability change was small and mixed by case, so warm start is a non-binding hint, not a demonstrated universal stability improvement. Files: `artifacts/replan_benchmark_v5_1_current_tree.json` and `.csv`.

The original 180-case artifact recorded 178 verified scenarios and two `UNKNOWN`. A fresh acceptance-audit rerun on HEAD `d69e5d8` has 174 resolved outcomes and six `UNKNOWN`/`NOT_VERIFIABLE`, zero failures/errors, and zero invariant violations. Its statuses are 104 `OPTIMAL`, 63 `FEASIBLE`, seven `TIME_LIMIT`, and six `UNKNOWN`. The six unresolved outcomes are 200-area cases; empty unknown plans remain unresolved even where invariant checks are vacuously valid. The rerun summary and exact cases are recorded in `artifacts/v5_1_acceptance_audit.json`; the earlier raw artifact remains unchanged.

## Acceptance status and adoption

The strategy-level adoption gates reject geographic decomposition and rolling horizon: geographic quality regresses and rolling is slower with frequent labelled baseline fallbacks. Their implementations and invariant/carryover checks pass; benchmark rejection is not an implementation failure. The selected path remains `S1_V5_BASELINE` / `BASELINE_DECOMPOSED`.

The overall V5.1 solver scalability acceptance is **PASS** under the original implementation criteria: bottlenecks were profiled, latency targets pass, the optimized baseline improves meaningfully at four larger sizes, experimental strategies were implemented and tested, selected-plan invariants and policy semantics pass, and the regression suite passes. Six stress outcomes remain `UNKNOWN` and are not solver passes. Current-HEAD acceptance evidence and the explicit gate-by-gate decision are in [V5_1_ACCEPTANCE_AUDIT.md](V5_1_ACCEPTANCE_AUDIT.md). All benchmarks remain synthetic/local; they do not establish field readiness.

```bash
uv run python scripts/run_solver_benchmark_v5_1.py
uv run python scripts/run_replan_benchmark_v5.py
uv run python scripts/run_stress_tests.py --v5-stress --strict-wall-clock \
  --route-strategy decomposed --output-stem stress_v5_1_final
```

The profile JSON preserves the measured before/after data and their source SHAs. The comparative runner reproduces the current five-strategy synthetic matrix; profiling inputs and limits are recorded in the profile artifact itself.
