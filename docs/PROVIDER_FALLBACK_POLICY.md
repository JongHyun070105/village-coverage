# Provider directory, fallback and reserve policy

Pilot decision-support only. Candidates are never contracts and nothing is auto-assigned.

## Source lifecycle (license first)
`DISCOVERED` (unregistered, not reviewed) -> `LICENSE_VERIFIED` (license known, not a supply
directory) -> `INGEST_ALLOWED` (license known and a supply-candidate source) or
`INGEST_BLOCKED` (license unclear or reuse not allowed). Only `INGEST_ALLOWED` sources can be
ingested; everything else is refused with a 422. An unclear license means no ingest.

Current state: the cooperative standard data (DATA_GO_KR_15155661) is `INGEST_BLOCKED`
because its license could not be confirmed. The self-support enterprise list
(DATA_GO_KR_15091502) is `INGEST_ALLOWED`, but no real file was ingested in this repository:
the framework and guard exist and the rows must be supplied by an operator.

Ingest keeps only name, service hint, region and reference date. Phone, representative,
address and e-mail fields are dropped and counted.

## Real vs simulated badges
A directory hit only proves the organization exists in a public registry
(`REAL_DIRECTORY`). Availability, capacity and price badges stay `SIMULATED` until a provider
reports them. Existence badge is `REAL_DIRECTORY` only after a planner links a directory
entry to a provider.

## Fallback candidates
For each planned round the same hard constraints apply as for the primary: supported service,
availability window, travel limit, daily hours, monthly capacity, no double booking that day,
and for home repair a verified capability (unknown is excluded). Ranking is by estimated
total cost, then travel time, then provider id: SECONDARY then TERTIARY. Every candidate is
flagged `requires_provider_confirmation` and `auto_contract: false`.

## Reserve comparison
The planner chooses the reserve ratio (0, 5, 10 or 15 percent); the system and the AI never do.
- NO_RESERVE: plan with the full budget, a decline loses the provider's rounds.
- BUDGET_RESERVE: plan with (100 - r)% and re-plan with the full budget after a decline.
- PROVIDER_FALLBACK: plan with the full budget and move rounds to ranked fallbacks while the
  leftover budget (including freed cost) allows, including any minimum-compensation top-up.
- BOTH: reserve plan, fallback first, then a re-plan if rounds remain unrecovered; the better
  of the two outcomes is reported with its mechanism.
Each planned provider is declined alone; the report shows the worst case. It is a
SIMULATION of declines, not a forecast of provider behavior.

## Limits
Fallbacks assume one round per provider per day, a conservative simplification. Recovery by
re-plan is a full solve and does not preserve the original schedule for unaffected rounds.
