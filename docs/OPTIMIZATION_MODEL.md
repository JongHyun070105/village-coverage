# Optimization model

## Data and decision variables

Gemini structures an unstructured note into a typed draft; it does not create an
allocation or route. OR-Tools CP-SAT assigns synthetic monthly service rounds
under the budget and aggregate simulated provider capacity. Kakao Mobility
provides directed road distance and duration; the 16 × 16 route matrix is
cached in SQLite.

For each legal-area service area `i`, integer `x_i` is the number of monthly
service rounds (zero through its synthetic modeled need), and Boolean `v_i`
indicates a visit. The model enforces `x_i <= demand_i * v_i`, `v_i <= x_i`,
aggregate capacity, and service plus travel expense within budget.

Service prices are simulated: 255,000 KRW for laundry, 225,000 KRW for daily
necessities, and 305,000 KRW for home repair. The route-cost assumption is
`distance_km * 1,800 KRW + duration_hours * 20,000 KRW` for a separate round
trip between each visited area and a representative central area. These prices,
provider capacities, operating conditions, and the hub are not market quotes or
real provider schedules.

## Policy scenarios

All priorities below are solved lexicographically with bounded integer
objectives. Each stage is fixed at its proven optimum before lower priorities
are considered. The solver must return `OPTIMAL`; a merely feasible timeout is
not reported as an optimum.

- **Efficiency:** maximize total monthly service rounds, assuming equal modeled
  utility for each round because no validated marginal resident-outcome data is
  available; then minimize road travel cost and travel time.
- **Balanced:** maximize total rounds; maximize the number of covered areas;
  maximize covered survey-required areas; maximize covered-area vulnerability
  points; minimize the highest area-level allocation / synthetic modeled-need
  ratio (rounded up to basis points); then minimize road travel cost and time. Each covered
  area's vulnerability score is `500 * elderly_ratio_65 + 500 * min(65+ single-households / population, 1)`, rounded to an integer. The two public-data
  shares contribute equally, up to 500 points each. Survey-required coverage
  has a separate higher priority. These are explicit policy choices, not
  empirically calibrated impact weights.
- **Minimum service guarantee:** maximize areas receiving at least one monthly
  round; then maximize total rounds; then minimize road travel cost and time.
  The first round in every covered area acts as the minimum-coverage priority.
  Maximizing covered areas is equivalent to minimizing the number left
  unserved. The model has no measured waiting-time or queue data, so it does
  not invent a waiting penalty.

The balanced hierarchy preserves the maximum feasible total service volume
before choosing a wider, more survey-inclusive allocation. A displayed travel
cost increase is the cost of the resulting area spread under this round-trip
model. Scenario results expose the maximum area-level served / modeled-demand
ratio in basis points, matching the concentration objective. Aggregate
distance is the sum of cached central-area round-trip road distances per
assigned unit; it is a modeled comparison metric, not a provider route. No
scenario score is a count of actual residents served.

For minimum coverage, the required budget is the sum of one simulated service
round plus its area's round-trip expense. If any area has no modeled unit or
aggregate provider capacity is below the number of areas, the required budget
and gap are `null`; money alone cannot resolve those feasibility conditions.
Otherwise, the UI reports the current gap and leaves uncovered areas visible.

## Current limits

- Provider capacities are aggregated. The result reports service-unit
  assignments and a provider-level cost attribution, but the provider movement
  figures still use central-hub round trips per assigned area. Provider bases,
  shift schedules, and final multi-stop routes are not inputs to this scenario
  optimizer.
- Travel expense sums separate hub round trips. This is not a multi-stop vehicle
  route and may overstate or understate operating cost.
- Service need, request observations, provider schedules/capacity, prices, and
  operating conditions are synthetic. No actual resident outcome or resident
  service count is calculated.
- The 21-seed sensitivity changes only synthetic operating inputs. It checks
  algorithm behavior under perturbation and is not evidence of real-world
  effectiveness.
- A legal-ri population aggregate does not describe individual households or
  sub-ri administrative village demand.

Validate these assumptions with residents and providers before operational use.
