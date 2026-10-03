# Optimizer Card

## Purpose and status meanings

The optimizer produces a policy-conditioned four-week draft schedule from
service demand inputs, provider availability, budget, travel matrix, and
operating constraints. Providers, capacity, price, and availability in the
current demo are simulated. The resulting schedule is not an offer, contract,
or confirmed service.

`OPTIMAL` means optimal for the declared model and scope. `FEASIBLE` means a
valid incumbent exists without a global optimality proof. `TIME_LIMIT` means a
feasible incumbent may exist but the search limit was reached. `UNKNOWN` means
feasibility was not proved either way. An infeasible restricted subproblem is
not promoted to global `INFEASIBLE`.

The UI separates “실행 가능한 계획” from “최적성 확인 완료”. Decomposed
results expose their optimality scope; they do not claim global route-order
optimality.

## Model

The joint strategy builds a provider-day schedule and road-route circuit in
one CP-SAT model. The decomposed strategy first solves an aggregate
provider-area allocation, then schedules the selected allocations against
date, time-window, provider, and budget constraints; route ordering is
improved after scheduling using cached directed road legs. The aggregate
stage is a relaxation of the full schedule and is not by itself a feasible
calendar.

API plans default to `auto`: use the joint route model while the predicted
route-arc count is at most 1,500; otherwise use decomposition. Each solve keeps
the configured limit (2.5 seconds by default). Decomposed search uses one
worker with a deterministic-time budget and a bounded wall-time cap. A larger
limit is not used to manufacture a pass.

Balanced objectives combine visible service volume, area coverage, survey
protection, vulnerability, concentration, and travel-cost terms. The user
selects policy weights; the terms are deterministic policy settings, not an
AI recommendation. Minimum-coverage money-only estimates are kept separate
from schedule-feasible minimum budgets. A money-only relaxation cannot prove
that providers, routes, or calendars can deliver that plan.

## Decomposition proof and routing limitations

For balanced and required-budget objectives, an `OPTIMAL` result is claimed
only when the allocation relaxation is optimal and the scheduled solution
attains each comparable aggregate objective bound. Efficiency and
minimum-coverage schedules include provider-day effects not bounded by the
aggregate stage, so a restricted stage-B optimum is not reported as global
optimality. If a pruned stage-B candidate set is infeasible, the system reports
`UNKNOWN` because other provider-area pairs were not searched.

The decomposed schedule uses conservative independent round trips before
post-solve route improvement. It can therefore miss a better assignment that
depends on multi-stop savings. The returned multi-stop route is operationally
checked against the cached directed road legs, but the assignment is not
globally optimized over all route permutations. Geographical clustering and
rolling-horizon decomposition are not implemented; monthly shared budget and
minimum-coverage constraints make independent regional solves unsafe without
a reconciliation stage. Prior plan versions are not used as warm starts.

## Measured evidence

Build and solve timings, candidate/model variables, constraints, route arcs,
provider-day combinations, branches, and conflicts are emitted by
`scripts/run_solver_benchmark.py`. Synthetic routes in stress benchmarks are
fixture edges, not live Kakao road evidence. See
`artifacts/solver_benchmark.json` when the benchmark has been run.

The checked-in 52-case same-matrix stress artifacts report 17/52 verified
cases on the V3 reference and 45/52 in V4 strict wall-clock mode (50/52 in
deterministic-time mode), with zero invariant violations in the V4 runs. This
improves verification rate without extending the 2.5-second solve limit.

The separate local benchmark on 2026-10-03 used a 2.5-second per-solve limit.
For the three-stage strategy, the measured end-to-end diagnostic times were
1.45s (16 areas), 5.65s (30), 7.92s (50), 10.18s (100), and 15.43s (200).
Those measurements include route reconstruction and invariant checks, but
exclude synthetic fixture generation; they are not API latency guarantees.
Three-stage `build_ms` / `solve_ms` were 1,316/24, 1,600/63, 1,939/1,718,
2,581/1,489, and 3,302/1,413 respectively. The 200-area monolithic model was
skipped before building because its predicted 500,000-plus route arcs exceed
the benchmark's safety threshold. The artifact records variables,
constraints, provider-day combinations, branches, conflicts, and invariant
checks for every attempted strategy.

The deterministic 100-case matrix is recorded in
`artifacts/stress_test_results_v4_stratified.json` and its CSV companion. It
covers 16/30/50/100/200 areas and 3/5/10/20 providers with baseline, tight and
high budget, partial/no participation, route completeness, low-data,
zero-budget, wrong-service, remote-area, and equal-demand profiles. Requested
provider participation rates are rounded to whole providers at each scale;
both requested and actual rates are recorded. All 100 invariant checks passed
with zero violations; 99 cases had a determinate solver outcome and one
200-area/20-provider baseline returned `UNKNOWN`. Only 59 cases produced any
scheduled rounds and only 7 met minimum coverage, so invariant pass does not
mean service coverage. Solver outcomes were 76 `OPTIMAL`, 20 `FEASIBLE`, 3
`TIME_LIMIT`, and 1 `UNKNOWN`. The 100-case matrix and five-scale strategy
benchmark use distinct experimental designs and must not be pooled.

The five-scale strategy benchmark still compares only three strategies.
Geographical clustering and rolling-horizon planning are not implemented.
Measured times also exceed the interactive target at 30 or more areas on this
local run; users receive the configured solver status and time limit rather
than a claim that those targets were met.

## Intended use

Use results to compare policy alternatives and identify budget, supply,
capacity, route, time-window, and data blockers. Review every draft before
approval. Do not interpret `FEASIBLE` as `OPTIMAL`, no plan as proof of
zero-demand, simulated providers as real suppliers, or a money-only lower
bound as a deliverable service calendar.
