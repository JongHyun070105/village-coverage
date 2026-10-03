# Demand Model Card

Version: `hierarchical_demand_v4.0`
Status: decision-support prototype; not a validated village demand predictor.

## Purpose

Keep external evidence, local observations, synthetic planning inputs, and
model estimates distinct. When local evidence is inadequate or conflicted,
return `FORECAST_NOT_ALLOWED` instead of treating missing data as zero demand.
The output is a count range (P10/P50/P90), not a precise point estimate.

## Data and provenance

- KREI R 2025-23 Table 4-8 supplies an `EXTERNAL_EMPIRICAL_PRIOR` for rural
  service need propensity, plus separate usage and unmet rates. It is not a
  local observation and is not converted to service visits.
- Local surveys and service observations are `LOCAL_OBSERVATION`. Only
  reviewed eligible evidence reaches the model; unresolved conflict and
  duplicate states block forecasting.
- A synthetic monthly planning baseline remains available and is labeled
  `SIMULATION`. It is not an empirical demand count.
- Home Doctor records are `EXTERNAL_OPERATIONAL_REFERENCE` for external
  forecast-method backtesting only. They are not modelled as rural village
  demand.
- Demographic modifiers default to `NO_EFFECT`. Configured coefficients and
  prior strengths are `EXPERIMENTAL`, visible settings rather than estimated
  effects.

## Method

For need propensity, the model starts with the service-specific KREI need rate
and a visible pseudo-respondent strength (default 20). Local respondent and
needer counts update a Beta-Binomial distribution and produce a percentile
range. This quantity remains a percent and is never multiplied by population
to create service rounds.

For monthly counts, eligible local observations update a Gamma-Poisson
predictive distribution. A synthetic monthly count baseline can contribute a
separately labeled prior with visible pseudo-month strength (default 1). As
local count periods increase, their contribution dominates that prior. This
does not make the estimate calibrated without a calibration profile.

Default forecast gates require at least 3 observations over at least 2 unique
months, a fresh observation, an allowed source, and no unresolved conflict or
duplicate. A gate failure produces no monthly range. Calibration labels move
only with local evidence: `SYNTHETIC_ONLY`, `EXTERNAL_EMPIRICAL`,
`LOCAL_LIMITED`, `LOCAL_CALIBRATED`, `LOCAL_OPERATIONAL_VALIDATED`.

## Evaluation

The rolling-origin benchmark in `artifacts/forecast_backtest.json` evaluates
synthetic controlled data, Home Doctor operational counts, and local
observations separately. The current local-observation dataset has zero
series, so there is no local predictive validation. The benchmark compares
NAIVE_LAST, SEASONAL_NAIVE, ROLLING_MEDIAN, EXPONENTIAL_SMOOTHING,
POISSON_BASELINE, NEGATIVE_BINOMIAL, and GAMMA_POISSON_BAYES on MAE, MASE,
WAPE when valid, bias, 80% interval coverage, interval width, and availability.
No single lowest-MAE result is automatically selected.

The controlled demand benchmark uses 400 simulated areas with known synthetic
truth. It can test shrinkage behavior; it is not evidence about actual
residents. Home Doctor's series is an external operations domain with
different population, services, reporting, and count scale. Its metrics do
not establish rural demand accuracy.

## Intended and prohibited uses

Use as a transparent evidence summary and a gate for further investigation.
Do not use the external propensity as a village rate, convert propensity to
visits, represent a forecast as a commitment, or describe an experimental
coefficient as a discovered effect. Do not infer zero from no observations.

## Known limitations and next validation

- The V4 evidence range endpoint supplements the existing schedule input path;
  the legacy schedule generator still carries a synthetic baseline. The
  external need prior does not currently drive optimized service-unit counts.
- There are no local operational time series in the current backtest.
- The model's configurable modifiers have no local empirical validation and
  should remain disabled unless a reviewed experiment explicitly configures
  them.
- Calibration profiles, uncertainty coverage, and data-leakage boundaries
  need ongoing checks when real local observations arrive.
