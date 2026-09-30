# Pre-R&D results

All allocation, request-count, provider, service-price, and beneficiary figures
in these experiments are deterministic **SIMULATED FOR PRE-R&D** values (seed
2026). Population, household aggregates, facility anchors, and road route
distances/times are derived from the live sources described in
`DATA_PROVENANCE.md`. These are prototype behavior checks, not measured service
impact or evidence of improved real-world coverage.

Reproduce with:

```sh
uv run python scripts/run_experiments.py
```

Outputs: `artifacts/experiment_results.json` and
`artifacts/experiment_results.csv`.

## Experiment 1: request-count baseline vs balanced planning

At a simulated monthly budget of 5,000,000 KRW, both approaches allocated 21
service units to 3 of 16 areas. The naive baseline allocated from observation
counts and covered 0 of 8 survey-required areas; the balanced scenario covered
3 of 8 survey-required areas while keeping modeled need separate from observed
request count. Their different synthetic per-service beneficiary multipliers
produce 84 vs 42 estimated beneficiary units, so those values must not be read
as people actually served. Balanced used 4,959,905 KRW and 3,424 travel seconds;
naive used 4,970,942 KRW and 4,467 travel seconds.

The experiment demonstrates the low-data allocation rule. It does not show
higher total coverage at this particular budget because both scenarios cover
only three areas.

## Experiment 2: budget sensitivity

| Budget | Minimum-guarantee result | Required budget | Additional budget at this point |
|---:|---|---:|---:|
| 4,000,000 KRW | 14 / 16 areas; 2 remain uncovered | 4,617,518 KRW | 617,518 KRW |
| 5,000,000 KRW | 16 / 16 areas | 4,617,518 KRW | 0 KRW |
| 6,000,000 KRW | 16 / 16 areas | 4,617,518 KRW | 0 KRW |
| 7,000,000 KRW | 16 / 16 areas | 4,617,518 KRW | 0 KRW |

At 4,000,000 KRW the optimizer does not report full coverage. The minimum
required amount is a model result under simulated unit prices, capacity, and
the hub-based round-trip cost model.

## Experiment 3: low-data handling

One synthetic area has one observation and 11 simulated service units of need.
The deterministic evidence assessment says `조사 필요`; the request-count
baseline allocates zero, while the balanced allocation assigns two units. This
shows that low observation count is not converted into zero modeled need. It
does not establish actual need in that area; field investigation is still
required.
