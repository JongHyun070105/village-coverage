# Pilot Data Lifecycle (V5.2)

This document describes the context-scoped prototype flow. It does not claim
field-pilot results or production readiness.

## Context and isolation

`POST /api/pilot-contexts` creates a named dataset with a region and one mode:

- `PILOT` excludes rows with `SIMULATED` source/provenance and never loads the
  demo fixture as a fallback.
- `SYNTHETIC_REHEARSAL` accepts simulated records and assumptions, and every
  resulting plan keeps a synthetic rehearsal label.

CSV preview accepts `context_id`. It creates an immutable-content batch keyed by
template and file hash and associates it with the selected context. Confirm
imports only `VALID` and `WARNING` rows. `ERROR` rows are retained in the
preview/error report but are not imported.

## Promotion map

| CSV template | Promoted domain type | Planning use |
|---|---|---|
| `region_areas` | `VillageServiceArea` | Scope, population, coordinates, planned coverage |
| `demand_observations` | `DemandEvidence` | Recent observed request-count evidence |
| `surveys` | `Survey` | Evidence quality and freshness; response counts are not converted into requests |
| `provider_organizations` | `ProviderOrganization` | Organization existence and identity provenance |
| `provider_services` | `ProviderService` | Proposal only until context-specific mapping review |
| `provider_availability` | `ProviderAvailability` | Exact dated service windows |
| `provider_capacity` | `ProviderCapacityConstraint` | Period and service-specific round cap |
| `provider_prices` | `ProviderPriceInput` | Positive per-visit cost input; missing price remains unknown |
| `provider_participation` | `ProviderParticipation` | Invite, opt-in, decline, or unavailable status |
| `service_execution_logs` | `ServiceExecutionLog` | Actual outcome linked to an approved plan round |

Each promoted record retains its import record, batch, context, row fingerprint,
source type, and provenance. Confirm and promotion are in one SQLite
transaction. If any row has an invalid domain mapping, the confirm is rolled
back; the batch remains previewed. Reconfirming a batch is idempotent. A changed
CSV content hash creates a new batch and never overwrites the old batch.

An uploaded `REAL_DIRECTORY` organization must match `source_id`,
`source_record_id`, and official name in the local provider-directory table.
Availability, capacity, prices, and participation are separately sourced local
operational facts; directory presence alone does not create any of them.
Provider service CSV values marked verified or rejected cannot self-approve;
the context mapping-review API records a PLANNER/REVIEWER decision.

Resident feedback is linked separately with
`POST /api/pilot-contexts/{context_id}/feedback/{feedback_id}` after its
existing feedback record's exact legal code matches an imported pilot area.
The pilot stores a reference and a privacy-minimized summary (type, status,
service, date, legal code, conflict type/status). It does not copy the feedback
description, requested change, claim, or contact into the pilot context. The
existing feedback review remains authoritative; an unresolved conflict is
shown as unresolved and is never treated as demand evidence.

## Planning gate and assumptions

Planning reads records from one `pilot_context_id`. It excludes simulated rows
in `PILOT`, filters demand to the recent planning window, applies the evidence
readiness gate, and requires per-area evidence. A shortage returns
`DATA_INSUFFICIENT`; it does not create synthetic demand. A provider must have a
verified service mapping, date availability, capacity, a valid positive price
or an explicit price assumption, and an explicit base location. Missing supply
returns `NO_VERIFIED_PROVIDER`; missing cost returns `COST_UNKNOWN`.

Route legs are directed. A leg can come from an exact route cache entry or an
explicit context assumption. Missing required legs return
`ROUTE_MATRIX_UNAVAILABLE`; straight-line distance is not used. The pilot API
pins optimization to V5.1 `BASELINE_DECOMPOSED`. Geographic and rolling
strategies remain experimental.

Route matrix, provider base location, service duration, and service price may be
entered as `SCENARIO_ASSUMPTION` or `SIMULATED` values with a reason. These are
stored in a separate append-only assumption history and included in plan
provenance. Zero is not a permitted substitute for an unknown price.

## Snapshot and freshness

Every plan stores:

- data mode, context ID, context snapshot ID, and import batch IDs;
- region, demand, and provider snapshot fingerprints;
- promoted source record and row-fingerprint lineage;
- source snapshot date and demand freshness warnings;
- provider mapping decisions and active/all assumption history;
- linked resident feedback IDs, minimal provenance, and conflict status;
- route matrix fingerprint/source and optimizer version.

Later imports or assumptions create a new context snapshot. They cannot change
the stored plan JSON or snapshot; an approved plan is immutable. A new plan
version is required to use changed inputs. The freshness date is a source
reference, not a guarantee that a local source is still operationally valid.

## Audit and reproducibility

Promotion and plan approval/generation append audit events without copying raw
resident notes or contacts into event details. Reproducing a plan requires its
persisted snapshot, imports, assumptions, mapping decisions, solver version,
policy scenario, and route matrix source. Missing inputs remain explicit and
stop planning; they are not silently filled by demo data.
