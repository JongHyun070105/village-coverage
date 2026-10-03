# Current Limitations

This prototype is not production-ready. Current known limits include:

- KREI rural-survey values describe external survey respondents; KOSIS describes
  broader nationwide social services. Neither is local village demand.
- The Home Doctor source covers public rental-housing operations, not rural
  villages. Its live API returned 22,058 rows beginning in 2022-01, although the
  provider recommends using the period from 2021-10. There are 2,905 rows where
  category sums differ from the reported total. Raw values are retained.
- No local operational demand series is available for forecast backtesting.
  One or a few survey inputs do not establish local calibration.
- The schedule generator still uses a synthetic planning baseline. The
  external KREI propensity is not converted into schedule service visits.
- Official nationwide cooperative and self-support enterprise directories
  have been identified as candidate-discovery sources, but their rows are not
  ingested or matched to supported services. One directory's reuse terms were
  unclear and its ingestion is blocked. Neither directory provides verified
  participation, current service availability, staffing, capacity, or prices;
  these remain simulated in the demo. The directories include representative
  fields, which the system does not collect or display.
- The original 52-case same-matrix stress results remain as historical
  evidence. The new 100-case deterministic stratified run had zero invariant
  violations, but one case returned `UNKNOWN`; only 59 cases scheduled any
  rounds and only 7 met minimum coverage. This is invariant validation, not a
  99% service-coverage claim. Requested participation rates are rounded to
  whole providers at each provider-count scale. A separate five-scale solver
  benchmark found three-stage end-to-end diagnostic times from 1.45s (16
  areas) to 15.43s (200 areas) under a 2.5s per-solve limit; the 30/50/100-area
  cases exceeded their interactive targets on this local run. Geographical
  decomposition, rolling-horizon planning, and prior-version warm starts are
  not implemented.
- Decomposed schedules improve route ordering after assignment but do not
  globally optimize assignment against all multi-stop route permutations.
- KOSIS catalog search did not find a matching willingness-to-pay or desired
  service-time table. Fee-burden opinions are not treated as willingness to
  pay.
- The public-sector approval roles have no real authentication. Existing plan
  exports are operational work-plan exports, not signed approvals.
- Map alternative tables, full keyboard walkthrough, responsive coverage for
  every screen, and the full 13-step user journey still require dedicated
  acceptance review.
- Source-specific license and use terms must be rechecked before publishing
  or deploying the system beyond this local demonstration.
