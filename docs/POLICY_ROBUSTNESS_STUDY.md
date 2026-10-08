# Policy robustness study

**Scope: SYNTHETIC.** This compares the existing four monthly aggregate
policies on the checked-in 16-area Hongseong fixture. It is not evidence of
rural demand accuracy, resident service increase, provider availability, or
municipal savings. No optimizer was added or changed; the schedule default
remains `BASELINE_DECOMPOSED`.

## Reproduction

```sh
uv run python scripts/run_policy_robustness_study.py
```

Artifacts: `artifacts/research/policy_robustness.json` and
`artifacts/research/policy_robustness.csv`. The JSON records the code SHA at
run time, driver SHA-256, `data/demo.json` SHA-256, route-matrix fingerprint,
solver and version, 3-second aggregate solve limit, seed list, scenario
parameters, exact results, and integrity checks.

| Parameter | Value / interpretation |
|---|---|
| Seeds | 2026, 2027, 2028 |
| Budgets | 4,000,000; 5,000,000; 7,000,000 won per month |
| Policies | EFFICIENCY, BALANCED, UNDERSERVED_FIRST, MINIMUM_GUARANTEE (`minimum_coverage`) |
| Area fixture | 16 synthetic/public fixture areas in `pilot:홍성군 장곡면` |
| Providers | 3 synthetic providers; existing seeded helper varies capacity |
| Demand | Existing seeded operating-profile helper; no new demand inputs |
| Travel | Fixed deterministic straight-line estimate matrix; not a road route |
| Other variables | No supported travel-cost perturbation or per-area observed underserved history; held fixed and identified in JSON |

The reference seed/budget replay returned identical assignments for all four
policies. All 36 seed × budget × policy rows returned `OPTIMAL`. The study
checks budget ceiling, provider capacity, allowed service types, assignment
coverage count, served units, and provider identity. It does not claim dated
schedule compatibility; the aggregate comparator has no dated appointments.

## Results

Values are means across three seeds; coverage range is across those same
seeds. `Covered / 16` is number of areas with at least one modeled service
unit. Served units and costs remain synthetic monthly model outputs. Runtime
is mean solver time in milliseconds, not end-to-end API latency.

| Budget | Policy | Covered areas mean (range) | Zero-service mean | Served units mean | Travel minutes mean | Spend mean (won) | Solver ms mean |
|---:|---|---:|---:|---:|---:|---:|---:|
| 4,000,000 | EFFICIENCY | 3.00 (2–4) | 13.00 | 16.67 | 113.0 | 3,989,319 | 49.9 |
| 4,000,000 | BALANCED | 6.33 (4–8) | 9.67 | 16.67 | 175.1 | 3,995,948 | 72.1 |
| 4,000,000 | MINIMUM_GUARANTEE | 14.33 (14–15) | 1.67 | 14.33 | 213.9 | 3,942,120 | 51.7 |
| 4,000,000 | UNDERSERVED_FIRST | 14.33 (14–15) | 1.67 | 14.33 | 213.9 | 3,942,120 | 51.7 |
| 5,000,000 | EFFICIENCY | 4.00 (4–4) | 12.00 | 20.67 | 168.1 | 4,987,301 | 45.7 |
| 5,000,000 | BALANCED | 7.67 (5–9) | 8.33 | 20.67 | 230.8 | 4,994,667 | 68.8 |
| 5,000,000 | MINIMUM_GUARANTEE | 16.00 (16–16) | 0.00 | 18.00 | 263.1 | 4,927,686 | 46.7 |
| 5,000,000 | UNDERSERVED_FIRST | 16.00 (16–16) | 0.00 | 18.00 | 263.1 | 4,927,686 | 46.4 |
| 7,000,000 | EFFICIENCY | 4.67 (4–5) | 11.33 | 28.67 | 294.5 | 6,983,149 | 49.0 |
| 7,000,000 | BALANCED | 8.67 (5–11) | 7.33 | 28.67 | 371.3 | 6,997,804 | 79.6 |
| 7,000,000 | MINIMUM_GUARANTEE | 16.00 (16–16) | 0.00 | 26.33 | 308.0 | 6,908,141 | 48.7 |
| 7,000,000 | UNDERSERVED_FIRST | 16.00 (16–16) | 0.00 | 26.33 | 308.0 | 6,908,141 | 49.7 |

This fixture shows a trade-off: EFFICIENCY allocates more units to fewer
areas; MINIMUM_GUARANTEE covers more areas with fewer served units; BALANCED
falls between those patterns and has higher modeled travel than EFFICIENCY.
UNDERSERVED_FIRST and MINIMUM_GUARANTEE are identical here because the fixture
does not supply a distinct observed underserved-history signal. The results
do not establish a universally best policy.

## Provider decline condition

At seed 2026 and 5,000,000 won, the aggregate comparator was re-evaluated with
0, 1, and 2 of 3 synthetic providers removed. For MINIMUM_GUARANTEE, all three
conditions remained `OPTIMAL`, covered 16/16 areas, served 18 units, spent
4,996,003 won, and returned the same 4,498,528-won required-budget estimate.
Provider utilization shifted to the remaining providers. This means the
remaining synthetic capacity was nonbinding for these outputs; it does not
mean real provider declines have no effect.

The decline sweep is an aggregate policy recomputation, not a call to the
schedule replan endpoint. The local end-to-end API workload separately
exercised decline → replan and records success by visitor count in
`public_demo_rate_limit_load.json`; the public-demo E2E also verifies that a
declined provider's exact round is not reused in the new plan. Further
schedule-level cost/coverage decline analysis is not established by this
study.

## Low-data cases

The four model-gate cases are in the JSON as A–D. All return
`FORECAST_NOT_ALLOWED` with a null monthly count range: evidence-only/no count,
unknown access-risk with no observations, one survey period, and unresolved
conflicting evidence. Missing frequency remains unknown. `frequency_per_month`
rejects zero in the public survey input contract, so an exact “recorded zero
requests” case cannot be supplied to this model API; it is not silently
reinterpreted as zero demand. The synthetic prior is separately labeled and
does not bypass evidence gates.

## Limits and plots

- The solver status is preserved; `TIME_LIMIT`/`UNKNOWN` would remain distinct
  if returned, but all rows in this bounded run were `OPTIMAL`.
- Provider capacity and availability are synthetic; provider removal is not an
  estimated decline rate.
- Travel-cost sensitivity and historical underserved coverage are not
  supported by the existing aggregate experiment interface and were not
  fabricated.
- No PNG plots were generated because `matplotlib` is not installed in the
  project environment. The complete CSV and JSON preserve the plot data; no
  new dependency was added for optional figures.
- Three seeds are a small reproducibility check, not a statistical sample.
