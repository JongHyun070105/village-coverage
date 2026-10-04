# Rolling Horizon V5.1

## Window model

The rolling scheduler repeatedly solves the remaining planning dates with lookahead, commits only the near-term window, then solves again. Future dates in a lookahead plan remain provisional. The default is a 28-day planning period with 7 committed days and 21 days of lookahead. `RollingHorizonConfig` also supports 7/14 (21-day lookahead window) and 14/14 (28-day lookahead window); commit and lookahead must sum to the configured window.

`planning_strategy="rolling_horizon"` applies the V5 global schedule model to each window. `planning_strategy="geographic_rolling"` adds cluster proposals and global reconciliation inside each window. Both use the same remaining demand, budget, provider limits, and area obligations.

## State carried between commits

`RollingHorizonState` carries:

- remaining budget and area service demand;
- remaining minimum-service obligations per area;
- provider rounds, scheduled hours, and service cost by month;
- served-area history and days since last service;
- the remaining minimum-obligation service-cost lower bound.

Provider monthly capacity is reduced by committed rounds before solving the next window. Service demand is reduced by committed service units. Minimum-service obligations decrease only when an area receives a committed round. The full remaining date range is included in each solve up to the end of the 28-day planning period, so future minimum-coverage work remains in the objective/constraints where the selected scenario enforces that guarantee.

Provider minimum compensation is paid once per active provider-month across commits. A later window models only the incremental provider pay above the amount already reserved. The serialized committed plan is then recomputed from committed service, travel, compensation, and carryover credit and checked against the original global budget.

The previous plan and the previous lookahead assignment set feed the existing greedy/CP-SAT hint path. Hints never add a hard constraint. A provider decline or changed feasibility therefore removes an incompatible old assignment instead of preserving it.

## Status and fallback

Each window records its dates, solver status, strategy, fallback flag, committed/lookahead round counts, solve time, and state after commit. The final result is `FEASIBLE` unless at least one window is `TIME_LIMIT`; it never reports rolling-horizon optimality. If a window solve or serialized cost check fails, the scheduler runs the V5 baseline and returns `BASELINE_FALLBACK` with the failed window and reason. It also compares the committed plan with the first full-lookahead solution. A loss in covered areas, a service-round drop greater than 10%, or reduced underserved-first points returns a labelled baseline fallback. Minimum-coverage failures also trigger fallback.

`minimum_coverage_met` is recomputed from the original obligations and committed rounds. A partial lookahead solution cannot silently claim that an unmet obligation was satisfied. Each window keeps the existing per-solve time limit; it is not divided into smaller budgets as the number of windows increases. The benchmark records quality fallbacks separately, so their output is not counted as evidence that rolling horizon itself preserved quality or improved runtime.

## Benchmark

```bash
uv run pytest -q tests/test_rolling_horizon.py tests/test_solver_decomposition.py
uv run python scripts/run_solver_benchmark_v5_1.py \
  --scenarios NORMAL --strategies S1_V5_BASELINE,S3_ROLLING_HORIZON_7_21 \
  --repeats 3
```

Compare the rolling strategies to `FULL_MONTH` on service rounds, covered and zero-service areas, minimum coverage, travel, total cost, status, and invariants. Synthetic late-horizon fairness is reported separately from field outcomes.
