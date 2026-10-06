# Pilot Execution Feedback Loop (V5.2)

## Plan lifecycle

Pilot plans are scoped to one context and use these statuses:

`DRAFT → UNDER_REVIEW → APPROVED` or `DRAFT → UNDER_REVIEW → CHANGES_REQUESTED`.

A PLANNER submits a draft. A REVIEWER approves or requests changes with a
comment. A changed plan is generated as a new version with parent/version
lineage. Provider declines and unavailable decisions from the plan lineage are
carried into replan exclusions. Approving a newer version supersedes an earlier
approved plan in the lineage. Content and snapshot fields of an approved or
superseded plan cannot be updated.

Approval roles in this prototype are workflow selectors, not authenticated
identities, legal signatures, or agency approval.

## Execution import

Import `service_execution_logs` against the same `pilot_context_id`. Rows must
reference an `APPROVED` plan in that context and match exactly one planned round
by provider, area, service, scheduled date, and optional `round_id`. A supplied
plan version must match. Unmatched or unapproved execution rows roll back the
whole confirm operation.

Supported outcomes:

- `COMPLETED`
- `PARTIALLY_COMPLETED`
- `CANCELLED`
- `NO_SHOW`
- `PROVIDER_CANCELLED`
- `RESCHEDULED`

Optional `actual_date` (also accepts legacy `executed_date`),
`actual_duration_minutes`, `actual_cost_won`, `completion_percent`, and
`cancel_reason` are stored with the execution batch and source. Do not put
resident contact details or raw resident free text in the cancel reason.

## Plan versus actual metrics

`GET /api/pilot-contexts/plans/{plan_id}/actuals` returns `UNKNOWN` when there
are no execution logs. With partial logs, it reports only observed actual rows
and marks coverage-dependent measures unknown until all planned `round_id`s are
covered. Measures include:

- planned and actual cost, cost variance;
- planned and actual service duration;
- planned and completed round counts, completion rate;
- actual served and zero-service areas;
- provider decline rate from the context's plan-lineage participation records;
- schedule variance in days and unmet/cancelled services.

Missing actual cost or duration remains `UNKNOWN`; it is not interpreted as
zero. Planned coverage is labeled as planned. Actual coverage is not inferred
from a plan or from incomplete execution logs.

## Resident feedback linkage

Use the existing resident feedback intake/review flow, then attach a reviewed
feedback ID to the pilot context. Attachment requires an exact legal-code match
to an imported region row. The plan snapshot stores only the feedback ID,
category, service, status, submitted date, area code, and conflict status. It
does not store the description, requested change, claim text, or contact. An
unresolved conflict remains explicitly unresolved and does not update demand
or override a survey.

## Calibration feedback

After execution-log confirmation, a context-scoped readiness request evaluates
the updated records. Readiness is not automatic calibration or model promotion.
`LOCAL_VALIDATED_OPERATIONAL` still requires the configured service-specific
sample, time-span, coverage, source, freshness, provider-operation, and human
review criteria. One successful service is not enough.

The current pilot import template set has no resident-feedback CSV template;
feedback uses the existing intake and review workflow plus a context link. The
pilot context does not own or resolve the underlying feedback record.
