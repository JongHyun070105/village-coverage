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
- The legacy DEMO schedule generator still uses its synthetic planning
  baseline. The external KREI propensity is not converted into schedule
  service visits. The separate V5.2 pilot-context path consumes only confirmed
  context inputs and explicitly labeled assumptions.
- Provider-directory ingestion stores source snapshot, record identity, and
  reuse-policy provenance for candidate discovery. The rehearsal matched one
  dated official directory record by exact source record ID; that proves listing
  identity only. A directory row does not establish provider participation,
  current service availability, staffing, capacity, contract, or prices. Those
  operating conditions still require separate local evidence. Any additional
  directory source requires its own current license/reuse review before use.
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

## V5.2 pilot-context limitations

- The pilot loop promotes confirmed CSV rows, calculates four scenarios using
  `BASELINE_DECOMPOSED`, snapshots provenance, supports plan review and
  approval, links execution logs to approved planned rounds, and computes
  actual metrics. The full same-context lifecycle rehearsal is
  `SYNTHETIC_REHEARSAL`; a separate `PILOT` contract test applies local
  operational inputs to an official directory identity, but has not carried
  actual authority-supplied data through approval and execution.
- The CSV validator checks legal-area-code shape and context mapping, but does
  not resolve every uploaded 10-digit code against a complete official legal
  code registry. The responsible authority must validate the jurisdiction.
- Official directory identity can be matched only when its source and record
  are present in the local directory table. Uploading a claimed official
  organization does not establish its service capacity, availability, price,
  contract, or willingness to participate. The complete same-context rehearsal
  includes one official directory identity and simulated operational rows; the
  separate `PILOT` optimizer contract test uses local-authority provenance but
  has not exercised a real authority's operating data through the full
  approval-and-execution loop.
- Pilot planning requires sufficiently recent request observations, explicit
  provider mapping, imported availability and capacity, a positive known price
  or separately recorded assumption, provider base locations, service time,
  and complete directed route legs. Missing demand returns `DATA_INSUFFICIENT`;
  missing provider operations returns `NO_VERIFIED_PROVIDER`; missing cost or
  routes fails closed. No straight-line route fallback is used.
- Demand evidence gates currently summarize imported observations and survey
  rows at area/service level. Resident feedback can be linked by exact legal
  code, with its category/status/conflict summary in the plan snapshot, but its
  claims do not enter demand estimation and conflict resolution stays in the
  existing feedback workflow. A `surveys.note` or execution cancel reason is
  only best-effort PII-redacted.
- Execution KPIs remain `UNKNOWN` until logs cover every planned round. Partial
  logs expose observed counts/costs but do not establish final coverage or
  completion rate. Planned duration and actual duration are aggregate values;
  material, staffing, and resident-wait components are not modeled.
- Calibration is re-evaluated from available evidence, but these rehearsal
  logs cannot promote `LOCAL_VALIDATED_OPERATIONAL`; the configured sample,
  time-span, coverage, and source requirements remain in force.
- The approval UI is a prototype role selector without authentication or
  server-side identity. Plan exports are not signed decisions. Automated
  keyboard, semantic, and 390/1024/1280/1440px checks pass, but a live
  screen-reader audit and explicit focus assertions after every modal,
  validation-error, approval, and replan transition remain incomplete.
- The solver rerun did not provide a conclusive all-size regression comparison:
  V5.1 S1 returned `TIME_LIMIT` at 30 and 100 areas, `OPTIMAL` at 50, and
  `UNKNOWN` at 200. The monolithic comparator returned only `UNKNOWN`,
  `TIME_LIMIT`, or `SKIPPED_PREDICTED_BUILD_TOO_LARGE`. Statuses remain as
  returned; no optimality or regression pass is inferred from those runs.
