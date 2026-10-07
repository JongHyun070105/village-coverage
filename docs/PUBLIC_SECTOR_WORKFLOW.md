# Public-Sector Planning Workflow

1. Select a pilot region and review its data quality and evidence gaps.
2. Open a village record and enter a de-identified survey summary; keep raw
   personal notes out of exports and audit events.
3. Review AI/structured drafts and explicitly approve or edit them before
   they become demand evidence.
4. Inspect the demand range, evidence provenance, calibration state, freshness,
   conflicts, duplicate state, and additional-survey gate.
5. Enter a planning budget and compare efficiency, balanced, underserved-first,
   and minimum-service-guarantee scenarios. Compare service rounds, covered/uncovered areas,
   travel, total cost, public-funding upper bound, and solver status.
6. Review the money-only minimum separately from the schedule-feasible
   minimum and inspect non-monetary blockers.
7. Review the simulated provider draft, capture opt-in/decline input, and
   regenerate a child plan version when the available supply changes.
8. A PLANNER demo role may submit a draft; a REVIEWER demo role may approve or
   return it. Approved rows are immutable. A later approved version supersedes
   the earlier approval in that lineage.
9. Inspect deterministic include/exclude reasons and the append-only audit
   events, then export assignment CSV, budget CSV, unmet-area CSV, or the work
   plan PDF.

The PLANNER and REVIEWER selector is a local demo workflow, not authentication,
authorization, or a signature. All provider profiles and operational supply
availability shown in the demo remain simulated. An approved demo plan is not
a procurement decision, legal approval, contract, or authorization to deliver
service.

## Pilot-context workflow (V5.2)

Create a named pilot context before importing. Preview each CSV, review row
errors and warnings, then explicitly confirm it. Confirmation and domain
promotion are one transaction; invalid mappings roll back the batch promotion.
The pilot plan records the exact context snapshot, import batches, source
lineage, service mapping decisions, scenario assumptions, and route source.
Missing demand, verified provider operations, price, or directed road legs fail
closed; a pilot request never borrows synthetic demo supply or demand.

Pilot plans use the same four policy scenarios and `BASELINE_DECOMPOSED` solver
path. A provider decline can produce a new plan version. The PLANNER submits,
the REVIEWER approves or requests changes, and changed assumptions or imports
require a new version. Execution CSV rows must identify an approved plan and
one matching planned round. Post-plan actual KPIs remain `UNKNOWN` until the
required execution evidence is present. The workflow remains a prototype and
does not provide authenticated roles or legal authorization.
