# SIMPLE_HOME_REPAIR service model

Pilot decision-support only. Every number below is a SIMULATED planning assumption.

## Regulation gate
- `service_types.regulation_level`: UNREGULATED / LIMITED / LICENSE_REQUIRED / EXCLUDED.
  `policy_status` stays consistent (UNREGULATED and LIMITED map to ALLOWED).
- `home_repair` is LIMITED with unit type JOB. `licensed_repair` (gas, boiler, electrical,
  plumbing/waterproofing, structural/roof, asbestos/height work) is LICENSE_REQUIRED and blocked.
- `classify_repair_text` returns SIMPLE_REPAIR, NEEDS_REVIEW, LICENSE_REQUIRED, EXCLUDED or
  NOT_REPAIR. Whitespace is stripped before matching. Any risky term blocks the whole request,
  even when a simple job is mentioned; simple jobs are listed as information only and a planner
  must split the request. A generic word such as "수리" alone is NEEDS_REVIEW, never auto-accepted.
- The demand parser drops `home_repair` and emits `licensed_repair` when the gate blocks.

## Unit types
ROUND, JOB, HOUSEHOLD, BATCH, VISIT. Laundry stays ROUND; home repair is JOB.

## Job catalog and uncertainty
Five simple jobs (bulb, screen door, door handle, faucet part, hinge). Each has
min/likely/max minutes, a material level (NONE/LOW/MEDIUM/HIGH) and a material cost range.
Unclear requests carry material level UNKNOWN; an unknown cost is never turned into 0 won.

## Demand model
`estimate_area_job_demand` uses eligible single elderly households x the external KREI need
rate x jobs per needing household x public uptake. LOW/MID/HIGH are scenario bounds, not
statistical quantiles (`bounds_are_quantiles: false`). It does not reuse the laundry model.
Missing households yield INSUFFICIENT_INPUT, not zero.

## Provider capability
`provider_services` gains `max_job_minutes`, `material_handling`, `tools_available` and
`capability_provenance` (default UNSPECIFIED). `provider_job_fit` returns FIT,
FIT_WITH_DURATION_RISK, NOT_FIT or UNVERIFIED. Unknown capability is UNVERIFIED, never FIT.

## Opt-in
`apply_to_area` sets a job-based visit duration only for `home_repair` areas. V4 baseline
planning is unchanged unless this profile is applied.

## API
`GET /api/home-repair/profile`, `POST /api/home-repair/classify`,
`GET /api/regions/{id}/home-repair/demand`,
`GET|PUT /api/providers/{id}/home-repair-capability`.

## Limits
Keyword matching is conservative and can over-block (for example the word "가스" in an
unrelated sentence). It is not a legal determination of what needs a license.
