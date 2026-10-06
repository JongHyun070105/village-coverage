# V5.2 Field-Pilot Readiness Audit

**Audit date:** 2026-10-06

**Branch:** `v5-2-pilot-loop-completion`

**Baseline:** `73cce371fbf60a07cfcf2938dca6636407566493`

**Decision:** `FIELD_PILOT_READY` prototype; field validation has not started.

> V5.2 is a field-pilot-ready prototype. It is not field-validated or production-ready.

## Decision boundary

Readiness means that a controlled pilot can accept appropriately de-identified institution data and exercise import, validation, planning, human review, approval, execution-log intake, and post-analysis. A real institution dataset is needed to validate those results in the field; its absence does not mean the prototype cannot accept such a dataset. The synthetic rehearsal is evidence of the technical path only, never evidence of community need, provider commitment, service delivery, or calibrated outcomes.

The prototype has no authenticated user identity or production authorization layer. Use it only in a trusted, access-controlled pilot environment with approved, minimized data. Do not expose it on an untrusted/shared network or treat it as a production public-sector system.

## Technical readiness matrix

| Requirement | Technical readiness | Evidence | Field validation needed? | Status |
|---|---|---|---|---|
| Pilot data import | CSV templates, preview, explicit confirmation, context-scoped promotion, and source retention work. | `tests/test_pilot_imports.py`; browser intake E2E. | Yes: institution-owned source files and their permitted use. | PASS |
| Preview / row validation | Row errors and warnings are visible before confirmation; invalid rows are omitted and PII is not echoed. Ten-digit area-code shape and context checks are enforced. | `test_row_80_validation_error_uses_explicit_partial_import_contract`; `test_pilot_import_error_does_not_echo_raw_contact_data`; Playwright intake test. | Yes: authority must confirm the canonical area-code mapping and source data quality. | PASS |
| Transaction safety | A row-level validation failure follows the explicit `IMPORTED_WITH_ERRORS` contract; a storage/promotion failure on row 80 of 100 rolls back the entire batch. | `test_promotion_failure_on_row_80_rolls_back_the_entire_batch`. | No. | PASS |
| Domain promotion | Confirmed imports promote into the selected pilot context; repeats do not create duplicate records. | `tests/test_pilot_imports.py`; lifecycle idempotency tests. | No. | PASS |
| Demo / pilot isolation | Pilot plans use context-scoped records; direct PILOT planning asserts zero DEMO provider inputs and zero DEMO source rows. | `test_real_directory_and_local_operations_reach_pilot_optimizer`; same-context lifecycle test. | No. | PASS |
| No synthetic silent fallback | Missing PILOT inputs fail closed. Scenario assumptions are separately labeled `SIMULATION`; synthetic rehearsal is explicitly named. | Lifecycle missing-input tests; `artifacts/pilot_rehearsal_v5_2_completion.json`; mode-label Playwright test. | No. | PASS |
| Demand wiring | Confirmed demand observations and survey evidence are included in pilot planning snapshots and provenance. | Lifecycle same-context test and browser `pilot-loop` E2E. | Yes: representative, longitudinal resident-demand evidence. | PASS |
| Provider operational wiring | Confirmed local-authority availability and capacity reach the PILOT optimizer through persisted imports. | `test_real_directory_and_local_operations_reach_pilot_optimizer`; `provider_availability` re-import checks. | Yes: actual provider availability and capacity. | PASS |
| Pilot Setup readiness dimensions | `REGION_DATA`, `DEMAND_EVIDENCE`, `PROVIDER_DIRECTORY`, `PROVIDER_OPERATIONS`, `PRICING`, `ROUTES`, and `EXECUTION_LOGS` report READY/LIMITED/MISSING; execution logs report NOT_REQUIRED_YET before the first execution. | `test_setup_readiness_dimensions_and_pre_execution_log_state`; provider integration readiness assertions; browser pilot workflow. | Yes: authority confirms its data and readiness interpretation. | PASS |
| Price / UNKNOWN handling | Imported prices are traceable; absent prices remain unknown and fail closed instead of inventing cost. | Lifecycle missing-price case (`COST_UNKNOWN`); provider-price provenance test. | Yes: current provider quotes and price basis. | PASS |
| Optimizer wiring | Context snapshots provide demand, directory, operations, price, routes, and optimizer version to the pilot planner. | PILOT API integration test; provenance snapshot assertions. | No for technical wiring; yes for validating real-world plan quality. | PASS |
| Same-context planning | Imports and all four strategy scenarios use one `pilot_context_id`; plan snapshots link the same imports and assumptions. | Synthetic rehearsal artifact and lifecycle invariant assertions. | Yes: repeat with an institution's approved dataset. | PASS |
| Provider decline / replan | A declined provider is removed in the child plan; replan creates a new immutable version and records the reason. | Lifecycle and browser `pilot-loop` E2E. | Yes: real provider responses. | PASS |
| Approval / version immutability | Approval is an auditable state transition; a later import creates a new version without modifying the approved snapshot. | Lifecycle database immutability test; browser E2E checks approved version and child version. | No for the version contract; yes for authority review practice. | PASS |
| Execution-log linkage | Execution rows link to approved plan version, round, provider, area, and service; repeated confirmation is idempotent. | Lifecycle execution linkage and repeated-import assertions; browser E2E. | Yes: real service records. | PASS |
| Plan-vs-actual metrics | Metrics are linked to the plan and retain `UNKNOWN` for rates/variance that a partial log cannot establish. | Synthetic rehearsal artifact (`post_metrics`) and lifecycle tests. | Yes: complete execution evidence. | PASS |
| Calibration readiness | Synthetic logs cannot promote to `LOCAL_VALIDATED_OPERATIONAL`; volume alone does not satisfy calibration gates. | `test_calibration_promotes_only_after_coverage_sources_freshness_and_real_logs`; same-context invariant. | Yes: sufficient fresh real observations and executions. | PASS |
| Provenance / audit trail | Plan snapshots retain context, import batch IDs, source records, evidence, cost inputs, route fingerprint, and optimizer version; actions are audited. | Lifecycle provenance-chain assertions and `artifacts/pilot_rehearsal_v5_2_completion.json`. | Yes: verify source legitimacy and authority ownership in the field. | PASS |
| Same-dataset rehearsal | One explicitly synthetic context completed import, promotion, four scenarios, decline/replan, changes requested, approval, execution, metrics, and calibration re-evaluation. | `artifacts/pilot_rehearsal_v5_2_completion.json`; lifecycle test rechecks invariants. | Yes: repeat with institution data before field conclusions. | PASS |
| Privacy baseline | Resident contact is excluded from plan snapshots/default exports, import errors, and captured application logs; provider API keys are absent from captured logs/errors and persisted source parameters; free text is minimized. | `tests/test_pilot_imports.py`, `tests/test_resident_feedback.py`, lifecycle feedback snapshot test, and KOSIS key-redaction tests. | Yes: authority privacy review and actual field-process observation. | PASS |
| External failure handling | Offline KOSIS/data.go.kr failures and route failures are handled explicitly; cache provenance is surfaced; Kakao route failures do not substitute straight-line distance. | `tests/test_external_ingestion.py`, `tests/test_travel.py`, `tests/test_route_failure.py`; see `external_api_resilience` in the JSON artifact. | Live network/credential smoke is separate and was not run. | PASS |
| Accessibility baseline | Keyboard-visible focus, labels, headings, landmarks, table semantics, responsive layouts, map/table alternative, and action-focus transitions are automated. A modal close/restore scenario is not applicable: these audited pilot actions do not use a modal dialog. | `frontend/e2e/focus-transitions.spec.ts`, pilot accessibility and keyboard E2E, full Playwright run. | Yes: real authority users, field observation, and screen-reader users. | PASS |

## Reclassification of the prior PARTIAL decision

`artifacts/v5_2_completion_acceptance.json` marked `pilot_data_wired_to_optimizer` PARTIAL because authority-supplied operations had not completed the entire lifecycle in one PILOT context. That combines two different claims:

| Prior reason | Correct classification | Current technical evidence |
|---|---|---|
| No actual institution dataset completed import through execution | Field validation prerequisite, not a readiness prerequisite. | Synthetic same-context rehearsal covers the full lifecycle; a separate persisted PILOT API test joins a real-directory identity with local-authority operations and provider price at the optimizer. |
| Current real provider participation, availability, capacity, and price are unconfirmed | Field validation prerequisite. | Integration proves the distinct source types and optimizer path; it does not claim an actual provider commitment. |
| Longitudinal resident demand and outcomes are absent | Field validation prerequisite. | Demand wiring, metrics, and calibration safety are tested; predictive/calibration validity is not claimed. |
| A live authority user has not reviewed or approved a plan | Field/user validation prerequisite. | Prototype approval/version transitions and audit events are exercised in tests. |
| No human screen-reader test has been performed | Manual user validation pending. | Automated accessibility baseline and action focus checks pass; no readiness failure is inferred from unavailable human testing. |
| Adapter-specific data.go.kr stale cache provenance was missing | Technical gap; fixed in this audit. | Adapter fallback now reports `CACHE_FALLBACK`, `snapshot_date`, `last_success`, `failure_reason`; API/evidence/UI expose cached status and tests exercise success-then-failure. |
| Area code validation accepted arbitrary text | Technical correctness gap; fixed in this audit. | `region_areas.area_code` now uses the ten-digit code validator; downstream records are context-checked. Canonical code registry membership still needs authority confirmation. |
| Post-action focus was not asserted on import, demand approval, scenario results, and plan lifecycle | Technical accessibility gap; fixed and automated. | Focus assertions verify the actual error summary, result/status heading, replan heading, and approval status. |

The older completion artifact is retained as historical evidence. This audit supersedes its readiness interpretation; it does not rewrite or relabel the earlier record.

## Synthetic same-context rehearsal

The checked-in rehearsal is labeled **SYNTHETIC FIELD-PILOT REHEARSAL; NOT FIELD RESULTS**. Its one context contains 16 areas and 10 import batches and reaches four scenarios, a provider decline and replan, changes requested, approval, an execution log, post-metrics, and calibration re-evaluation. The artifact and lifecycle test assert that every plan uses the same context, that execution links to the approved version/round, that duplicate execution import is idempotent, and that synthetic logs do not promote calibration. Incomplete actual metrics remain `UNKNOWN`.

The additional API integration test uses a persisted official-directory record and confirmed pilot imports for local availability, capacity, and provider-reported price. It asserts these values appear in the PILOT plan and snapshot, with zero DEMO source rows. The directory fixture is dated `2025-12-31`; it verifies source and integration semantics, not current provider status.

## External API and cache semantics

- **data.go.kr:** successful snapshot followed by failed live fetch uses the snapshot with `CACHE_FALLBACK`, snapshot date, last-success time, and failure reason. The note and UI say a cached snapshot was used; this is never labeled live.
- **KOSIS:** timeout, HTTP, malformed payload, empty result, key redaction, and stale-snapshot behavior are covered offline.
- **Kakao Mobility:** timeout, HTTP/route-unavailable, malformed/empty response, and incomplete directed route matrices fail explicitly or use the documented hub fallback. No straight-line substitution is made.
- **Live smoke:** not run. `FAILURE_HANDLING_PASS` is distinct from `LIVE_SMOKE_PASS`; unavailable credentials/network do not turn a verified offline failure contract into a readiness failure. The adapter paths are tested, so the skipped live smoke is a scope limit, not an unverified adapter.

## Solver comparison

V5.1 (`72f326782f79316e835e8855d017cb6e8f3e9b1e`) and V5.2 were run on the same machine, with the same frozen dependency lock, seeds, inputs, 2.5-second limit, and three repeats per case. All 12 paired cases produced identical solver statuses, covered/zero-service area counts, cost, and invariant results. The comparison is **PASS: no regression detected**. `TIME_LIMIT` at 30/100 areas and `UNKNOWN` at 200 areas occurred in both versions; they are solver-optimality limits, not evidence of a V5.2 regression or a field-performance guarantee.

Artifacts: `artifacts/v5_2_readiness_v51_baseline_20261006.json` and `artifacts/v5_2_readiness_v52_current_20261006.json` (plus paired CSVs). Median runtimes in milliseconds by area count were 30: 5809.23 → 5376.60; 50: 3278.97 → 2730.05; 100: 8448.41 → 7326.86; 200: 5244.12 → 5098.36. These short local runs are not a capacity or latency SLO.

## Field validation status: NOT_STARTED

Field validation needs an authorized partner and its approved, appropriately minimized data: an institution dataset; longitudinal resident demand; current provider identity, availability, capacity, and prices; real service execution records; live authority-user review; and observed accessibility behavior including screen-reader testing. Until then, no field effectiveness, provider commitment, demand calibration, or actual service result is claimed. Execution logs may be `NOT_REQUIRED_YET` before the first service is run; pre-execution setup readiness is distinct from post-execution validation readiness.

## Remaining limitations

- No real institution dataset, live authority user, current provider confirmation, real resident longitudinal series, or real execution results have been used.
- Screen-reader/manual accessibility and field accessibility observations are pending. Automated focus and responsive checks are not a substitute for those users.
- No authenticated identity/production authorization is included. Restrict a prototype pilot host and use data minimization; production use requires a separately authorized security design.
- Official directory fixture freshness ends at 2025-12-31; canonical area-code membership must be confirmed against the authority's source.
- Live external API smoke was skipped. Solver `TIME_LIMIT`/`UNKNOWN` cases remain explicit limitations.
- Partial execution logs do not establish complete-plan completion, zero-service totals, or plan-wide variance; such metrics remain unknown until sufficient records arrive.

## Verification record

Machine-readable acceptance: [`artifacts/v5_2_field_pilot_readiness_audit.json`](../artifacts/v5_2_field_pilot_readiness_audit.json). Current branch verification results and proposal acceptance rerun are recorded there. The historical proposal and completion artifacts remain unchanged.
