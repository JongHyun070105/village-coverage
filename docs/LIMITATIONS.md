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
- The original 52-case and V4 100-case stress results remain historical
  evidence. The V5 180-case deterministic matrix had zero invariant violations;
  173 cases returned a determinate result at the 1.5-second limit and the 7
  `UNKNOWN` cases all returned `OPTIMAL`/`FEASIBLE` after targeted 2.5- or
  5-second reruns. Only 133/180 cases scheduled rounds and 8/180 met minimum
  coverage. This is solver/invariant evidence, not a service-coverage claim.
  Requested participation rates are rounded to whole providers at each scale.
  A V5 five-scale solver benchmark measured three-stage end-to-end times from
  1.46s (16 areas) to 15.40s (200 areas) under a 2.5-second per-solve limit;
  the 30/50/100-area cases exceeded interactive targets. Geographic
  decomposition and rolling-horizon planning remain unimplemented. Replanning
  now supplies compatible prior provider-area-date choices as solver hints,
  which do not guarantee faster solves or preserve unaffected assignments.
- Decomposed schedules improve route ordering after assignment but do not
  globally optimize assignment against all multi-stop route permutations.
- KOSIS catalog search did not find a matching willingness-to-pay or desired
  service-time table. Fee-burden opinions are not treated as willingness to
  pay.
- The public-sector approval roles have no real authentication. Existing plan
  exports are operational work-plan exports, not signed approvals.
- The public journey and targeted keyboard checks cover intake, area detail,
  policy comparison, the dashboard's map-alternative table, plan review, and
  export. They do not constitute a full assistive-technology, map-control,
  dialog, or every-screen responsive audit.
- Source-specific license and use terms must be rechecked before publishing
  or deploying the system beyond this local demonstration.
