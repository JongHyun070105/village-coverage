"""V5 schema migrations (resident feedback, expanded audit/approval vocabulary)."""

from __future__ import annotations

AUDIT_EVENT_TYPES = (
    "SURVEY_CREATED",
    "AI_DRAFT_APPROVED",
    "CONFLICT_RESOLVED",
    "DUPLICATE_DECIDED",
    "POLICY_CHANGED",
    "PLAN_GENERATED",
    "PROVIDER_DECLINED",
    "PROVIDER_PARTICIPATION_CHANGED",
    "REPLAN",
    "PLAN_SUBMITTED_FOR_REVIEW",
    "PLAN_APPROVED",
    "PLAN_RETURNED_TO_DRAFT",
    "PLAN_SUPERSEDED",
    "CALIBRATION_RECORDED",
    "IMPORT_ROW_APPROVED",
    "FEEDBACK_SUBMITTED",
    "FEEDBACK_REVIEW_STARTED",
    "FEEDBACK_NEEDS_MORE_INFO",
    "FEEDBACK_ACCEPTED",
    "FEEDBACK_REJECTED",
    "FEEDBACK_RESOLVED",
    "FEEDBACK_CONFLICT_CREATED",
    "FEEDBACK_CONFLICT_RESOLVED",
    "FEEDBACK_DUPLICATE_DECIDED",
    "PLAN_MARKED_STALE",
    "PLAN_CHANGES_REQUESTED",
    "DECISION_MEMO_GENERATED",
    "PROVIDER_FALLBACK_COMPUTED",
    "RESERVE_POLICY_SELECTED",
    "SOURCE_REGISTRY_UPDATED",
)
AUDIT_ACTOR_ROLES = ("PLANNER", "REVIEWER", "SYSTEM", "RESIDENT")
SCENARIO_KEYS = ("efficiency", "balanced", "underserved_first", "minimum_coverage")
APPROVAL_STATUSES = ("DRAFT", "UNDER_REVIEW", "CHANGES_REQUESTED", "APPROVED", "SUPERSEDED")
CHANGE_KINDS = (
    "INITIAL",
    "PROVIDER_REPLAN",
    "EVIDENCE_REPLAN",
    "BUDGET_REPLAN",
    "POLICY_REPLAN",
    "REVISION_AFTER_CHANGES_REQUESTED",
)
FEEDBACK_TYPES = (
    "DATA_CORRECTION",
    "SERVICE_REQUEST",
    "ACCESSIBILITY_ISSUE",
    "UNMET_SERVICE",
    "SCHEDULE_CONCERN",
    "OTHER",
)
FEEDBACK_STATUSES = (
    "SUBMITTED",
    "UNDER_REVIEW",
    "NEEDS_MORE_INFO",
    "ACCEPTED_AS_EVIDENCE",
    "REJECTED",
    "RESOLVED",
)
SUBMITTER_ROLES = ("RESIDENT", "VILLAGE_LEADER", "STAFF_ASSISTED", "OTHER")
INTAKE_CHANNELS = ("PUBLIC_FORM", "STAFF_ASSISTED")


def _in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


MIGRATION_17 = f"""
PRAGMA foreign_keys = OFF;
BEGIN;

CREATE TABLE audit_events_v17 (
    event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL CHECK(event_type IN ({_in(AUDIT_EVENT_TYPES)})),
    subject_type TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    actor_role TEXT NOT NULL CHECK(actor_role IN ({_in(AUDIT_ACTOR_ROLES)})),
    occurred_at TEXT NOT NULL,
    details_json TEXT NOT NULL DEFAULT '{{}}'
);
INSERT INTO audit_events_v17(
    event_id, event_type, subject_type, subject_id, actor_role, occurred_at, details_json)
SELECT event_id, event_type, subject_type, subject_id, actor_role, occurred_at, details_json
FROM audit_events;
DROP TABLE audit_events;
ALTER TABLE audit_events_v17 RENAME TO audit_events;
CREATE INDEX idx_audit_events_subject ON audit_events(subject_type, subject_id, occurred_at);
CREATE INDEX idx_audit_events_time ON audit_events(occurred_at DESC);

CREATE TABLE schedule_runs_v17 (
    schedule_id TEXT PRIMARY KEY,
    scenario_key TEXT NOT NULL CHECK(scenario_key IN ({_in(SCENARIO_KEYS)})),
    budget_won INTEGER NOT NULL CHECK(budget_won >= 0),
    summary_json TEXT NOT NULL,
    provenance TEXT NOT NULL,
    created_at TEXT NOT NULL,
    planning_policy_json TEXT NOT NULL DEFAULT '{{}}',
    region_id TEXT NOT NULL DEFAULT 'pilot:홍성군 장곡면',
    plan_version INTEGER NOT NULL DEFAULT 1 CHECK(plan_version >= 1),
    lineage_root_id TEXT,
    parent_schedule_id TEXT REFERENCES schedule_runs(schedule_id),
    change_kind TEXT NOT NULL DEFAULT 'INITIAL' CHECK(change_kind IN ({_in(CHANGE_KINDS)})),
    change_reason TEXT,
    change_explanation_json TEXT NOT NULL DEFAULT '{{}}',
    approval_status TEXT NOT NULL DEFAULT 'DRAFT'
        CHECK(approval_status IN ({_in(APPROVAL_STATUSES)})),
    approval_updated_at TEXT,
    approved_by_role TEXT CHECK(approved_by_role IS NULL OR approved_by_role IN
        ('PLANNER','REVIEWER')),
    data_snapshot_json TEXT NOT NULL DEFAULT '{{}}',
    stale_since TEXT,
    stale_reason TEXT
);
INSERT INTO schedule_runs_v17(
    schedule_id, scenario_key, budget_won, summary_json, provenance, created_at,
    planning_policy_json, region_id, plan_version, lineage_root_id, parent_schedule_id,
    change_kind, change_reason, change_explanation_json, approval_status,
    approval_updated_at, approved_by_role, data_snapshot_json)
SELECT
    schedule_id, scenario_key, budget_won, summary_json, provenance, created_at,
    planning_policy_json, region_id, plan_version, lineage_root_id, parent_schedule_id,
    change_kind, change_reason, change_explanation_json, approval_status,
    approval_updated_at, approved_by_role, data_snapshot_json
FROM schedule_runs;
DROP TABLE schedule_runs;
ALTER TABLE schedule_runs_v17 RENAME TO schedule_runs;
CREATE UNIQUE INDEX idx_schedule_lineage_version
    ON schedule_runs(lineage_root_id, plan_version);
CREATE INDEX idx_schedule_parent ON schedule_runs(parent_schedule_id);
CREATE INDEX idx_schedule_runs_created ON schedule_runs(created_at DESC);
CREATE INDEX idx_schedule_runs_approval ON schedule_runs(approval_status, lineage_root_id);
CREATE TRIGGER trg_schedule_runs_approved_immutable
BEFORE UPDATE OF scenario_key, budget_won, summary_json, planning_policy_json, region_id,
    plan_version, lineage_root_id, parent_schedule_id, data_snapshot_json
ON schedule_runs
WHEN OLD.approval_status IN ('APPROVED', 'SUPERSEDED')
BEGIN
    SELECT RAISE(ABORT, 'APPROVED_PLAN_IMMUTABLE');
END;

CREATE TABLE resident_claim_evidence (
    evidence_id TEXT PRIMARY KEY,
    feedback_id TEXT NOT NULL UNIQUE,
    area_id TEXT NOT NULL REFERENCES village_service_areas(area_id),
    service_type TEXT REFERENCES service_types(service_type_id),
    evidence_type TEXT NOT NULL DEFAULT 'RESIDENT_CLAIM' CHECK(evidence_type = 'RESIDENT_CLAIM'),
    source_type TEXT NOT NULL DEFAULT 'RESIDENT_FEEDBACK' CHECK(source_type = 'RESIDENT_FEEDBACK'),
    verification_state TEXT NOT NULL DEFAULT 'UNVERIFIED_CLAIM'
        CHECK(verification_state IN ('UNVERIFIED_CLAIM','VERIFIED_BY_SURVEY','SUPERSEDED')),
    payload_json TEXT NOT NULL,
    occurred_on TEXT NOT NULL,
    provenance TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX idx_resident_claim_evidence_area
    ON resident_claim_evidence(area_id, service_type, occurred_on DESC);

CREATE TABLE resident_feedback (
    feedback_id TEXT PRIMARY KEY,
    region_id TEXT NOT NULL REFERENCES regions(region_id),
    area_id TEXT NOT NULL REFERENCES village_service_areas(area_id),
    service_type TEXT REFERENCES service_types(service_type_id),
    feedback_type TEXT NOT NULL CHECK(feedback_type IN ({_in(FEEDBACK_TYPES)})),
    submitted_at TEXT NOT NULL,
    submitter_role TEXT NOT NULL CHECK(submitter_role IN ({_in(SUBMITTER_ROLES)})),
    intake_channel TEXT NOT NULL CHECK(intake_channel IN ({_in(INTAKE_CHANNELS)})),
    description TEXT NOT NULL CHECK(length(description) BETWEEN 1 AND 2000),
    description_was_redacted INTEGER NOT NULL CHECK(description_was_redacted IN (0, 1)),
    requested_change TEXT CHECK(requested_change IS NULL OR length(requested_change) <= 1000),
    claim_json TEXT NOT NULL DEFAULT '{{}}',
    evidence_attachment_metadata_json TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'SUBMITTED' CHECK(status IN ({_in(FEEDBACK_STATUSES)})),
    reviewer_id TEXT CHECK(reviewer_id IS NULL OR reviewer_id IN ('PLANNER','REVIEWER')),
    reviewed_at TEXT,
    resolution TEXT,
    linked_demand_evidence_id TEXT REFERENCES resident_claim_evidence(evidence_id),
    linked_plan_id TEXT REFERENCES schedule_runs(schedule_id),
    content_fingerprint TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX idx_resident_feedback_area_status
    ON resident_feedback(area_id, status, submitted_at DESC);
CREATE INDEX idx_resident_feedback_region_status
    ON resident_feedback(region_id, status, submitted_at DESC);
CREATE INDEX idx_resident_feedback_fingerprint
    ON resident_feedback(area_id, content_fingerprint);

CREATE TABLE resident_feedback_contacts (
    feedback_id TEXT PRIMARY KEY REFERENCES resident_feedback(feedback_id) ON DELETE CASCADE,
    contact_text TEXT NOT NULL CHECK(length(contact_text) BETWEEN 1 AND 200),
    created_at TEXT NOT NULL
);

CREATE TABLE resident_feedback_conflicts (
    conflict_id TEXT PRIMARY KEY,
    feedback_id TEXT NOT NULL REFERENCES resident_feedback(feedback_id),
    area_id TEXT NOT NULL REFERENCES village_service_areas(area_id),
    service_type TEXT REFERENCES service_types(service_type_id),
    conflict_type TEXT NOT NULL CHECK(conflict_type IN (
        'RESIDENT_CLAIM_VS_NO_OFFICIAL_DEMAND', 'RESIDENT_CLAIM_VS_SURVEY_FREQUENCY')),
    official_json TEXT NOT NULL,
    claim_json TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('REVIEW_REQUIRED', 'RESOLVED')),
    resolution_method TEXT CHECK(resolution_method IS NULL OR resolution_method IN (
        'KEEP_OFFICIAL_EVIDENCE', 'FURTHER_SURVEY', 'ACCEPT_AS_RANGE')),
    reason TEXT,
    resolved_by TEXT CHECK(resolved_by IS NULL OR resolved_by IN ('PLANNER','REVIEWER')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(feedback_id, conflict_type)
);
CREATE INDEX idx_resident_feedback_conflicts_area
    ON resident_feedback_conflicts(area_id, status);

CREATE TABLE resident_feedback_duplicate_decisions (
    feedback_id_a TEXT NOT NULL REFERENCES resident_feedback(feedback_id),
    feedback_id_b TEXT NOT NULL REFERENCES resident_feedback(feedback_id),
    state TEXT NOT NULL CHECK(state IN ('LINKED_DUPLICATE', 'CONFIRMED_DISTINCT')),
    canonical_feedback_id TEXT REFERENCES resident_feedback(feedback_id),
    reason TEXT NOT NULL,
    actor_role TEXT NOT NULL CHECK(actor_role IN ('PLANNER','REVIEWER')),
    decided_at TEXT NOT NULL,
    CHECK(feedback_id_a < feedback_id_b),
    PRIMARY KEY(feedback_id_a, feedback_id_b)
);

COMMIT;
PRAGMA foreign_keys = ON;
"""

MIGRATION_18 = """
BEGIN;
CREATE TABLE area_service_history (
    area_id TEXT NOT NULL REFERENCES village_service_areas(area_id),
    service_type TEXT NOT NULL REFERENCES service_types(service_type_id),
    month TEXT NOT NULL CHECK(month GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]'
        AND substr(month, 6, 2) BETWEEN '01' AND '12'),
    rounds_delivered INTEGER NOT NULL CHECK(rounds_delivered BETWEEN 0 AND 62),
    provenance TEXT NOT NULL CHECK(provenance IN ('REAL_REPORTED', 'SIMULATED')),
    created_at TEXT NOT NULL,
    PRIMARY KEY(area_id, service_type, month)
);
CREATE INDEX idx_area_service_history_area ON area_service_history(area_id, service_type, month);
COMMIT;
"""

MIGRATION_19 = """
BEGIN;
ALTER TABLE service_types ADD COLUMN regulation_level TEXT NOT NULL DEFAULT 'UNREGULATED'
    CHECK(regulation_level IN ('UNREGULATED','LIMITED','LICENSE_REQUIRED','EXCLUDED'));
ALTER TABLE service_types ADD COLUMN unit_type TEXT NOT NULL DEFAULT 'ROUND'
    CHECK(unit_type IN ('ROUND','JOB','HOUSEHOLD','BATCH','VISIT'));
UPDATE service_types SET regulation_level='LICENSE_REQUIRED' WHERE policy_status='REGULATED';
UPDATE service_types SET regulation_level='EXCLUDED' WHERE policy_status='EXCLUDED';
UPDATE service_types SET regulation_level='LIMITED', unit_type='JOB'
    WHERE service_type_id='home_repair';

ALTER TABLE provider_services ADD COLUMN max_job_minutes INTEGER
    CHECK(max_job_minutes IS NULL OR max_job_minutes BETWEEN 1 AND 480);
ALTER TABLE provider_services ADD COLUMN material_handling TEXT NOT NULL DEFAULT 'UNKNOWN'
    CHECK(material_handling IN ('NONE','LOW','MEDIUM','HIGH','UNKNOWN'));
ALTER TABLE provider_services ADD COLUMN tools_available INTEGER
    CHECK(tools_available IS NULL OR tools_available IN (0, 1));
ALTER TABLE provider_services ADD COLUMN capability_provenance TEXT NOT NULL
    DEFAULT 'UNSPECIFIED'
    CHECK(capability_provenance IN ('UNSPECIFIED','SIMULATED','PROVIDER_REPORTED'));
COMMIT;
"""

MIGRATION_20 = """
BEGIN;
CREATE TABLE provider_directory_entries (
    entry_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    name TEXT NOT NULL CHECK(length(name) BETWEEN 1 AND 120),
    service_hint TEXT,
    region_id TEXT NOT NULL DEFAULT '',
    existence_provenance TEXT NOT NULL
        CHECK(existence_provenance IN ('REAL_DIRECTORY', 'SIMULATED')),
    reference_date TEXT,
    linked_provider_id TEXT REFERENCES providers(provider_id),
    created_at TEXT NOT NULL,
    UNIQUE(source_id, name, region_id)
);
CREATE INDEX idx_provider_directory_region ON provider_directory_entries(region_id);
COMMIT;
"""
