# Decision Memo guide

The Decision Memo is a print-ready comparison document for the reviewer who approves a plan.
It supports a decision; it does not make one.

## Wording rules

- Options are called 검토안 (the plan under review) and 비교안 (other stored plans of the same
  region). There is no "recommended" option.
- 추가재원 검토 필요 appears when a known shortfall exists, when the cost floor already exceeds
  funding, or when unserved areas are money-resolvable.
- 정책 선택 필요 lists choices the planner or reviewer owns: scenario, reserve ratio (0/5/10/15%),
  and handling of survey-needed or zero-service areas.
- Zero-service areas read "현재 계획에서 서비스 미배정", never "위험".
- Unknown costs and funding are shown as "알 수 없음" and as a bound, never as 0 won.

## Endpoints

- `GET /api/schedules/{id}/decision-memo` — JSON (`compare_with` up to 3 plan ids, same region).
- `GET /api/schedules/{id}/decision-memo.html` — print-ready HTML (`@media print`).
- `GET /api/schedules/{id}/decision-memo.pdf` — PDF.

## Approval flow

DRAFT, UNDER_REVIEW, CHANGES_REQUESTED, APPROVED, SUPERSEDED. CHANGES_REQUESTED is derived: the
stored status returns to DRAFT and an open `plan_change_requests` row (comment, max 500 chars,
reviewer only) marks it; re-submitting resolves the row. This avoids rebuilding `schedule_runs`.
Approved and superseded plans are immutable at the database level (triggers on `schedule_runs`
and `scheduled_rounds`); a change needs a new plan version. Roles are demo PLANNER/REVIEWER
only; there is no production authentication. Audit events never store the comment text.

## Evidence legend

PUBLIC DATA, EXTERNAL EMPIRICAL, LOCAL OBSERVATION, MODEL ESTIMATE, SIMULATION. Provider
availability, capacity and price are SIMULATION until verified by contract or field check.
