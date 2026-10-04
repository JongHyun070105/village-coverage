# Rolling Horizon V5.1

## Window model and carried state

The rolling scheduler solves a remaining planning window with lookahead, commits only its near-term dates, carries state, and solves again. The default is a 28-day period with 7 committed days and 21 days of lookahead. Configured alternatives are 7/14 over 21 days and 14/14 over 28 days. `planning_strategy="rolling_horizon"` uses the V5 global schedule model; `geographic_rolling` adds cluster proposals and shared-resource reconciliation within each window.

`RollingHorizonState` carries remaining budget and service demand, minimum-service obligations by area, provider monthly rounds and hours, service cost/compensation already committed, served-area history, and days since last service. Obligations decrement only for committed rounds. Provider monthly capacity is reduced before the next solve. Minimum compensation is charged incrementally once per active provider-month. The final serialized plan is costed and checked against the original budget.

Previous-plan and prior-lookahead assignments go through the existing greedy/CP-SAT hint path. They remain hints, never constraints. Solver status is retained per window; rolling does not claim global optimality.

## Quality protection and fallback

Each rolling result is checked against its first full-lookahead plan for covered areas, service rounds (no more than a 10% reduction), and underserved-first points. If the rolling plan misses minimum obligations that the first lookahead could meet, it falls back with a named regression. If the first lookahead cannot establish whether the minimum is feasible, a single full-month V5 solve is used as a reference; when that baseline meets the minimum, it becomes the explicit fallback. Solver-window errors, failed costs, and failed independent checks also return `BASELINE_FALLBACK` and a reason. The fallback status does not disguise that the rolling attempt failed its quality gate.

## Measured results

The 210-row three-repeat S3/S4 refresh uses the same seven synthetic workload generators, seeds, public-area-free input snapshots, simulated providers, and 2.5-second per-window solver setting as the architecture matrix. Wall-clock totals include repeated window solves, quality checks, and any fallback. The full result is in `artifacts/solver_benchmark_v5_1.json` and `.csv`.

| Areas | V5 baseline mean runtime | S3 rolling 7/21 mean runtime | S4 geographic rolling 7/21 mean runtime | S3 fallback runs / 21 | S4 fallback runs / 21 |
|---:|---:|---:|---:|---:|---:|
| 16 | 2.82 s | 3.77 s | 9.62 s | 18 | 18 |
| 30 | 3.43 s | 10.41 s | 20.73 s | 18 | 18 |
| 50 | 3.96 s | 11.84 s | 25.91 s | 15 | 21 |
| 100 | 4.54 s | 16.16 s | 38.05 s | 15 | 18 |
| 200 | 4.65 s | 15.69 s | 37.37 s | 12 | 21 |

These runtimes are means of the seven per-workload repeat medians; fallback rows contain the full attempted rolling cost plus the returned baseline. Runtime and fallback rates fail the intended rolling acceptance. They are not evidence for choosing S3/S4.

The three-repeat NORMAL horizon comparison is recorded in `artifacts/solver_benchmark_v5_1_variants_final.json` and `.csv`. At 16/30/50/100/200 areas, median S3 runtimes were 5.98/10.31/11.61/19.89/19.74 seconds for 7/14 and 4.35/10.40/10.14/14.75/8.12 seconds for 14/14. S4 14/14 measured 11.00/22.02/18.08/24.76/31.28 seconds. The 200-area S3 rows are all `UNKNOWN`, not passes. Most rolling alternatives use a labelled baseline fallback.

The synthetic 7/21 late-horizon zero-service rate was 41.7%, 63.6%, 80.4%, 80.2%, and 77.0% at 16/30/50/100/200 areas. This indicates the short-window commits cannot be interpreted as a fairness improvement. The common 16-area Hongseong aggregate test reports minimum coverage met for the tested minimum-policy variants; explicit fallback use is retained in the artifact. It does not establish field performance.

## Tests and reproduction

Focused state, remaining budget/capacity, minimum obligations, underserved history, warm-hint, and fallback checks live in `tests/test_rolling_horizon.py` and `tests/test_solver_decomposition.py`.

```bash
uv run pytest -q tests/test_rolling_horizon.py tests/test_solver_decomposition.py
uv run python scripts/run_solver_benchmark_v5_1.py \
  --scenarios NORMAL --strategies S1_V5_BASELINE,S3_ROLLING_HORIZON_7_21 \
  --repeats 3
```

`UNKNOWN` and `TIME_LIMIT` remain visible statuses and are not counted as successful solves. Synthetic fairness metrics are not field-policy evidence.
