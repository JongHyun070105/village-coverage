# Public-Sector Planning Workflow

1. Select a pilot region and review its data quality and evidence gaps.
2. Open a village record and enter a de-identified survey summary; keep raw
   personal notes out of exports and audit events.
3. Review AI/structured drafts and explicitly approve or edit them before
   they become demand evidence.
4. Inspect the demand range, evidence provenance, calibration state, freshness,
   conflicts, duplicate state, and additional-survey gate.
5. Enter a planning budget and compare efficiency, balanced, and minimum
   coverage scenarios. Compare service rounds, covered/uncovered areas,
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
