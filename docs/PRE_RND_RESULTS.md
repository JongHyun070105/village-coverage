# Pre-R&D results

These are algorithm-behavior checks. Service need, requests, providers,
capacity, prices, and operating conditions are **SIMULATED FOR PRE-R&D**. The
2026-10-01 public-data recheck, pilot statistics, and cached road-route source
are described in `DATA_PROVENANCE.md` and `DATA_QUALITY_REPORT.md`. Nothing here
estimates actual people served or proves real-world impact.

Reproduce the fixed-seed experiment and 21-seed synthetic sensitivity with:

```sh
uv run python scripts/run_experiments.py
```

Outputs: `artifacts/experiment_results.json` and
`artifacts/experiment_results.csv`.

## Request-count baseline and Balanced at 5,000,000 KRW

Both plans allocate 21 monthly service rounds (15.0% of 140 synthetic modeled
rounds). Request-count priority serves 3 of 16 areas and 0 of 8 survey-required
areas. Balanced serves 8 of 16 areas and 5 of 8 survey-required areas. Balanced
therefore trades 91,882 KRW more modeled travel cost (183,732 vs 91,850 KRW)
and 4,124 additional travel seconds (8,417 vs 4,293 seconds) for five more
covered areas and five survey-required areas included. The comparisons share
the same synthetic budget and modeled service volume.

At the same budget, Efficiency covers 3 areas and 3 of 8 survey-required areas;
Balanced covers 8 areas and 5 of 8. This makes the area-spread policy visible
while showing its travel-cost trade-off. It is a result of the stated synthetic
inputs and hierarchy, not evidence that the policy improves actual coverage.

For comparison, the prior Balanced objective at 5,000,000 KRW produced the same
21 rounds but covered 3 areas and 3 / 8 survey-required areas, with 74,243 KRW
modeled travel cost and 3,305 seconds. The current hierarchy covers five more
areas and two more survey-required areas; its modeled travel cost rises by
109,489 KRW and travel time by 5,112 seconds versus that earlier allocation.

## 4–7 million KRW scenario sensitivity

| Budget | Scenario | Monthly rounds / modeled need | Service areas | Survey-required included | Road cost | Travel time | Extra for all-area minimum |
|---:|---|---:|---:|---:|---:|---:|---:|
| 4,000,000 | Efficiency | 17 / 140 (12.14%) | 3 / 16 | 3 / 8 | 49,589 KRW | 2,397 s | — |
| 4,000,000 | Balanced | 17 / 140 (12.14%) | 5 / 16 | 5 / 8 | 91,882 KRW | 4,124 s | — |
| 4,000,000 | Minimum service guarantee | 14 / 140 (10.00%) | 14 / 16 | 7 / 8 | 318,027 KRW | 15,057 s | **608,959 KRW** |
| 5,000,000 | Efficiency | 21 / 140 (15.00%) | 3 / 16 | 3 / 8 | 49,589 KRW | 2,397 s | — |
| 5,000,000 | Balanced | 21 / 140 (15.00%) | 8 / 16 | 5 / 8 | 183,732 KRW | 8,417 s | — |
| 5,000,000 | Minimum service guarantee | 17 / 140 (12.14%) | 16 / 16 | 8 / 8 | 428,959 KRW | 19,580 s | 0 KRW |
| 6,000,000 | Efficiency | 26 / 140 (18.57%) | 4 / 16 | 3 / 8 | 79,757 KRW | 3,863 s | — |
| 6,000,000 | Balanced | 26 / 140 (18.57%) | 5 / 16 | 4 / 8 | 111,413 KRW | 5,081 s | — |
| 6,000,000 | Minimum service guarantee | 22 / 140 (15.71%) | 16 / 16 | 8 / 8 | 428,959 KRW | 19,580 s | 0 KRW |
| 7,000,000 | Efficiency | 30 / 140 (21.43%) | 4 / 16 | 4 / 8 | 81,245 KRW | 3,615 s | — |
| 7,000,000 | Balanced | 30 / 140 (21.43%) | 7 / 16 | 6 / 8 | 155,395 KRW | 7,157 s | — |
| 7,000,000 | Minimum service guarantee | 26 / 140 (18.57%) | 16 / 16 | 8 / 8 | 428,959 KRW | 19,580 s | 0 KRW |

The synthetic minimum budget for 16 of 16 areas is **4,608,959 KRW**. At
4,000,000 KRW, the guarantee plan shows 14 / 16 areas and a 608,959 KRW gap;
at 5,000,000 KRW it shows 16 / 16. Higher budgets increase extra rounds after
the minimum is met. The requirement depends on synthetic prices and modeled
hub trips.

## 21-seed robustness sensitivity

This run retains reference seed 2026 and adds 20 seeds. It varies only synthetic
request observation counts, modeled service need, service categories, and
provider capacity. Public pilot population, household aggregates, facility
anchors, and cached road routes stay fixed. Each seed is evaluated at 5,000,000
KRW. Across 21 synthetic runs:

- Efficiency mean service fulfillment: **15.59%**.
- Balanced mean service areas: **5.86 / 16**.
- Balanced mean survey-required coverage: **49.88%**.
- Balanced mean modeled road cost: **140,140 KRW**.
- Minimum all-area budget: **4,591,816 KRW mean**, 4,388,959–4,808,959 KRW
  range.

These values only show sensitivity of this model under seeded input changes.
They do not generalize to other regions and do not establish an actual service
effect.
