# Solver Decomposition V5.1

## Architecture

V5.1 keeps the V5 allocation and scheduling objectives. Geographic clusters produce local allocation proposals; the proposals share the same providers, provider-month limits, compensation, and budget. A global reconciliation allocation treats local results as CP-SAT hints, expands candidate pairs when needed, then the existing global scheduler checks capacity, dates, overlap, cost, service compatibility, route feasibility, and truthful minimum-coverage reporting.

`build_geographic_partition` supports `ADMINISTRATIVE_CLUSTER`, `DISTANCE_CLUSTER`, `PROVIDER_REACHABILITY_CLUSTER`, and `HYBRID_CLUSTER`. Sorted IDs, connected components, deterministic farthest-first medoid seeds, bounded assignment, and deterministic nearest-group merging make partitions repeatable. The algorithm uses available administrative IDs and cached road duration/provider compatibility; it adds no ML clustering dependency. `ClusterConfig` exposes minimum/target/maximum sizes, radius, per-area provider candidates, and local proposal time limits. Providers are never pinned to one cluster.

A failed proposal reconciliation, schedule, or independent invariant check returns a labelled `BASELINE_FALLBACK` with the reason. Fallback output remains identifiable in the API result and benchmark. `GEOGRAPHIC_CLUSTER` does not claim global optimality.

## Candidate and route controls

`_make_candidates` removes only hard-infeasible provider-area-date pairs, including unsupported service, provider participation/unavailability, requested date/time windows, missing required road legs, maximum travel time, and daily work limits. The remaining provider-area pairs are available to reconciliation by default. An optional heuristic pair cap is available for benchmark-only experiments; it is not enabled in the selected strategy and may remove hard-feasible choices. The default cluster benchmark pruned zero compatible pairs. The separately labelled heuristic variant removed 5,226 pairs over 15 synthetic runs, so it is not accepted as pruning-safety or production evidence.

Route-pair reads, cache hits/misses, candidate edges, and route arcs are recorded. Missing strict routes fail closed; no live map API is called by the benchmark.

## Measured result

The three-repeat architecture matrix covers 16/30/50/100/200 areas, seven synthetic workload types, and 3/5/5/10/20 simulated providers. The table is the mean of each workload's repeat median and is synthetic evidence only.

| Areas | V5 baseline runtime / covered / zero | Geographic runtime / covered / zero | Rolling 7/21 runtime / covered / zero | Geographic rolling 7/21 runtime / covered / zero |
|---:|---:|---:|---:|---:|
| 16 | 2.82 s / 11.43 / 4.57 | 3.58 s / 10.57 / 5.43 | 3.77 s / 11.43 / 4.57 | 9.62 s / 11.14 / 4.86 |
| 30 | 3.43 s / 21.00 / 9.00 | 4.90 s / 17.14 / 12.86 | 10.41 s / 21.00 / 9.00 | 20.73 s / 19.57 / 10.43 |
| 50 | 3.96 s / 31.86 / 18.14 | 6.07 s / 24.14 / 25.86 | 11.84 s / 31.86 / 18.14 | 25.91 s / 28.57 / 21.43 |
| 100 | 4.54 s / 55.00 / 45.00 | 7.55 s / 36.86 / 63.14 | 16.16 s / 55.71 / 44.29 | 38.05 s / 55.29 / 44.71 |
| 200 | 4.65 s / 58.71 / 141.29 | 10.18 s / 38.43 / 161.57 | 15.69 s / 62.43 / 137.57 | 37.37 s / 64.71 / 135.29 |

Global invariants had zero violations in the completed measured rows. This does not make `TIME_LIMIT` or `UNKNOWN` a successful solve. The 200-area monolithic route model was skipped when its estimated arc count exceeded 500,000. Geographic-only solving is rejected for adoption: on the seven-workload means it covers about 4–24 fewer areas than V5 across sizes 30–200. Rolling variants mostly return quality-guarded baseline fallbacks; their wall-clock includes the attempted rolling solve and the fallback. No tested size selects geographic or rolling over the V5 baseline.

At 200 areas, the normal workload is `UNKNOWN` for the V5 baseline and the geographic/rolling variants. These rows have no assignments and count as unverified outcomes, even where vacuous route checks and other invariants are valid.

The NORMAL-only horizon comparison (three repeats) also shows no adoption case: S3 7/14 medians were 5.98/10.31/11.61/19.89/19.74 seconds at 16/30/50/100/200 areas; S3 14/14 was 4.35/10.40/10.14/14.75/8.12 seconds; S4 14/14 was 11.00/22.02/18.08/24.76/31.28 seconds. The 200-area S3 results were `UNKNOWN`; they are not passes.

## Synthetic fairness and quality

Across the geographic-only synthetic cases, boundary-area zero-service rates were not higher than non-boundary rates at the tested sizes. At 100 areas the rates were 61.6% and 63.5%; at 200 they were 79.5% and 81.7%. Rolling 7/21 late-horizon zero-service rates were 41.7%, 63.6%, 80.4%, 80.2%, and 77.0% at 16/30/50/100/200 areas. This synthetic fixture check does not establish field fairness. Quality guards and labelled fallback preserve the baseline result when the committed plan regresses.

The same 16-area Hongseong public-area aggregate fixture, simulated providers/history, and local road cache was run at ₩5,000,000 under all four policies and seven solver strategies. There were zero invariant violations. `UNDERSERVED_FIRST` and `MINIMUM_GUARANTEE` retained all 16 areas, zero zero-service areas, and all 14 underserved points in the reported rows. This is a deterministic local simulation, not field evidence. Some rolling/minimum cases explicitly used `BASELINE_FALLBACK`.

## How to reproduce

```bash
uv run pytest -q tests/test_geographic_decomposition.py tests/test_solver_decomposition.py
uv run python scripts/run_solver_benchmark_v5_1.py --scenarios NORMAL --repeats 3
```

See [SOLVER_BENCHMARK_V5_1.md](SOLVER_BENCHMARK_V5_1.md) for artifact definitions, profile timings, statuses, and acceptance limits. Full data are in `artifacts/solver_benchmark_v5_1.json` and `.csv`, with alternate cluster/horizon variants in `artifacts/solver_benchmark_v5_1_variants_final.json` and `.csv`.
