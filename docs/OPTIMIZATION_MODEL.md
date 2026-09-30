# Optimization model

## Separation of responsibilities

Gemini may turn an unstructured note into a typed draft. It does not produce a
route or allocation. OR-Tools CP-SAT selects service units under the budget and
simulated monthly capacity. Kakao Mobility supplies directed road distance and
duration; route results are cached in SQLite.

## Decision variables and shared constraints

For each legal-area service area `i`:

- integer `x_i`: service units assigned, from zero through its simulated need;
- Boolean `v_i`: whether the area receives a trip.

The model enforces `x_i <= demand_i * v_i`, `v_i <= x_i`, total assigned units
no greater than total simulated provider capacity, and total service plus
travel expense no greater than the budget. Assignments have no negative demand,
cost, or capacity. Every served unit contributes to the service total only when
an assignment exists.

Travel cost includes a simulated service unit price and the area's cached road
round trip from a representative central legal area. Per-trip travel cost is
`distance_km * 1,800 KRW + duration_hours * 20,000 KRW`; service prices are
`255,000 KRW` for laundry, `225,000 KRW` for daily necessities, and `305,000 KRW`
for home repair. These prices, provider capacity, and the hub are synthetic
pre-R&D assumptions, not market quotes or real provider schedules.

## Policy scenarios

- **Efficiency** maximizes served units and then favors fewer travel seconds.
- **Balanced** uses policy weights centralized in `backend/settings.py`: base
  weight 100, older-population contribution `90 * elderly_ratio_65`, older single-household
  contribution `45 * single_households_65_plus / population_total`, and 35
  additional points for a survey-required area. Sparse observations do not
  reduce modeled need to zero.
- **Minimum coverage guarantee** first maximizes the number of areas receiving
  at least one unit, then served units, then prefers less travel time. The
  minimum is one monthly service per area.

For minimum coverage, the required budget is the sum of one service unit plus
the area's round-trip cost for every area. If any area has no modeled unit or
aggregate provider capacity is below the number of areas, the required budget
and budget gap are `null`; money alone cannot cure those supply/need feasibility
conditions. If the guarantee is feasible but underfunded, `additional_budget`
is the nonnegative gap and uncovered areas remain visible.

## Current modeling limits

- Provider capacities are aggregated. The current synthetic providers share a
  co-located operating assumption; units are distributed to providers after
  optimization for reporting. This is not a provider-specific shift schedule.
- The travel-cost estimate sums each served area's separate round trip from one
  representative hub. It is not a multi-stop vehicle-routing solution, does
  not sequence visits, and may overstate or understate operational cost.
- Beneficiaries per service unit are simulated, and service fulfillment is
  against synthetic need. Neither is a measured resident outcome.
- A legal-ri population aggregate does not describe individual households or
  sub-ri administrative village demand.

These limits must be addressed with provider and resident validation before a
municipality uses the outputs as an operating plan.
