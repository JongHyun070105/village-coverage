"""Versioned SQLite persistence for operational evidence and planning inputs."""

from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from backend.forecast import MODEL_VERSION, forecast_region_service
from backend.regions import DEFAULT_REGION_ID, region_catalog
from backend.regions import region_id as make_region_id
from backend.service_registry import SERVICE_REGISTRY, SERVICE_REGISTRY_PROVENANCE
from backend.settings import PlanningPolicy
from backend.timeutils import korea_today
from scripts.api_smoke_test import _load_config

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = 11
APP_DATABASE_ENV = "VILLAGECOVERAGE_APP_DB"
_CONNECT_LOCK = threading.RLock()

_MIGRATION_1 = """
CREATE TABLE regions (
    region_id TEXT PRIMARY KEY,
    province TEXT NOT NULL,
    county TEXT NOT NULL,
    town TEXT NOT NULL,
    provenance TEXT NOT NULL
);

CREATE TABLE village_service_areas (
    area_id TEXT PRIMARY KEY,
    region_id TEXT NOT NULL REFERENCES regions(region_id),
    legal_code TEXT NOT NULL UNIQUE CHECK(length(legal_code) = 10),
    name TEXT NOT NULL,
    facility_count INTEGER NOT NULL CHECK(facility_count >= 0),
    anchor_lat REAL NOT NULL,
    anchor_lng REAL NOT NULL,
    provenance TEXT NOT NULL
);

CREATE TABLE population_snapshots (
    area_id TEXT NOT NULL REFERENCES village_service_areas(area_id),
    reference_date TEXT NOT NULL,
    population_total INTEGER NOT NULL CHECK(population_total >= 0),
    population_65_plus INTEGER NOT NULL CHECK(population_65_plus >= 0),
    population_75_plus INTEGER NOT NULL CHECK(population_75_plus >= 0),
    population_80_plus INTEGER NOT NULL CHECK(population_80_plus >= 0),
    provenance TEXT NOT NULL,
    PRIMARY KEY(area_id, reference_date)
);

CREATE TABLE household_snapshots (
    area_id TEXT NOT NULL REFERENCES village_service_areas(area_id),
    reference_date TEXT NOT NULL,
    households_total INTEGER NOT NULL CHECK(households_total >= 0),
    households_65_plus INTEGER NOT NULL CHECK(households_65_plus >= 0),
    households_75_plus INTEGER NOT NULL CHECK(households_75_plus >= 0),
    households_80_plus INTEGER NOT NULL CHECK(households_80_plus >= 0),
    provenance TEXT NOT NULL,
    PRIMARY KEY(area_id, reference_date)
);

CREATE TABLE service_types (
    service_type_id TEXT PRIMARY KEY,
    label_ko TEXT NOT NULL,
    policy_status TEXT NOT NULL CHECK(policy_status IN ('ALLOWED', 'REGULATED', 'EXCLUDED')),
    policy_reason TEXT NOT NULL,
    provenance TEXT NOT NULL
);

CREATE TABLE surveys (
    survey_id TEXT PRIMARY KEY,
    area_id TEXT NOT NULL REFERENCES village_service_areas(area_id),
    survey_type TEXT NOT NULL CHECK(survey_type IN ('phone', 'village_meeting', 'proxy', 'field')),
    survey_date TEXT NOT NULL,
    service_type TEXT NOT NULL REFERENCES service_types(service_type_id),
    frequency_per_month INTEGER CHECK(frequency_per_month BETWEEN 1 AND 31),
    preferred_period TEXT,
    preferred_days_json TEXT NOT NULL,
    constraints_json TEXT NOT NULL,
    free_text_note TEXT NOT NULL,
    source_text_was_redacted INTEGER NOT NULL CHECK(source_text_was_redacted IN (0, 1)),
    provenance TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE demand_observations (
    observation_id TEXT PRIMARY KEY,
    area_id TEXT NOT NULL REFERENCES village_service_areas(area_id),
    survey_id TEXT UNIQUE REFERENCES surveys(survey_id),
    occurred_on TEXT NOT NULL,
    source_type TEXT NOT NULL,
    service_type TEXT NOT NULL REFERENCES service_types(service_type_id),
    provenance TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE demand_evidence (
    evidence_id TEXT PRIMARY KEY,
    observation_id TEXT NOT NULL UNIQUE REFERENCES demand_observations(observation_id),
    evidence_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    provenance TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE demand_assessments (
    area_id TEXT NOT NULL REFERENCES village_service_areas(area_id),
    service_type TEXT NOT NULL REFERENCES service_types(service_type_id),
    observation_count INTEGER NOT NULL CHECK(observation_count >= 0),
    survey_count INTEGER NOT NULL CHECK(survey_count >= 0),
    source_diversity INTEGER NOT NULL CHECK(source_diversity >= 0),
    missingness REAL NOT NULL CHECK(missingness BETWEEN 0 AND 1),
    latest_observation_date TEXT,
    deterministic_confidence REAL NOT NULL CHECK(deterministic_confidence BETWEEN 0 AND 1),
    combined_confidence REAL NOT NULL CHECK(combined_confidence BETWEEN 0 AND 1),
    status TEXT NOT NULL,
    needs_survey INTEGER NOT NULL CHECK(needs_survey IN (0, 1)),
    limited_planning_allowed INTEGER NOT NULL CHECK(limited_planning_allowed IN (0, 1)),
    evidence_reasons_json TEXT NOT NULL,
    provenance TEXT NOT NULL,
    calculated_at TEXT NOT NULL,
    PRIMARY KEY(area_id, service_type)
);

CREATE INDEX idx_surveys_area_date ON surveys(area_id, survey_date DESC);
CREATE INDEX idx_observations_area_date ON demand_observations(area_id, occurred_on DESC);
"""

_MIGRATION_2 = """
CREATE TABLE providers (
    provider_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    base_location TEXT NOT NULL,
    base_lat REAL NOT NULL,
    base_lng REAL NOT NULL,
    max_daily_hours REAL NOT NULL CHECK(max_daily_hours > 0),
    max_monthly_rounds INTEGER NOT NULL CHECK(max_monthly_rounds >= 0),
    service_capacity INTEGER NOT NULL CHECK(service_capacity > 0),
    max_travel_time_minutes INTEGER NOT NULL CHECK(max_travel_time_minutes > 0),
    minimum_compensation_won INTEGER NOT NULL CHECK(minimum_compensation_won >= 0),
    provenance TEXT NOT NULL
);

CREATE TABLE provider_services (
    provider_id TEXT NOT NULL REFERENCES providers(provider_id) ON DELETE CASCADE,
    service_type TEXT NOT NULL REFERENCES service_types(service_type_id),
    PRIMARY KEY(provider_id, service_type)
);

CREATE TABLE provider_availability (
    provider_id TEXT NOT NULL REFERENCES providers(provider_id) ON DELETE CASCADE,
    weekday TEXT NOT NULL CHECK(weekday IN
        ('monday','tuesday','wednesday','thursday','friday','saturday','sunday')),
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    PRIMARY KEY(provider_id, weekday, start_time)
);

CREATE TABLE service_rounds (
    round_id TEXT PRIMARY KEY,
    provider_id TEXT NOT NULL REFERENCES providers(provider_id),
    area_id TEXT NOT NULL REFERENCES village_service_areas(area_id),
    service_type TEXT NOT NULL REFERENCES service_types(service_type_id),
    round_date TEXT NOT NULL,
    start_time TEXT NOT NULL,
    duration_minutes INTEGER NOT NULL CHECK(duration_minutes > 0),
    estimated_compensation_won INTEGER NOT NULL CHECK(estimated_compensation_won >= 0),
    travel_time_minutes INTEGER,
    travel_distance_km REAL,
    provenance TEXT NOT NULL
);

CREATE TABLE provider_participations (
    participation_id TEXT PRIMARY KEY,
    provider_id TEXT NOT NULL REFERENCES providers(provider_id),
    round_id TEXT NOT NULL REFERENCES service_rounds(round_id),
    status TEXT NOT NULL CHECK(status IN
        ('AVAILABLE','OPTED_IN','DECLINED','UNAVAILABLE','COMPLETED','CANCELLED')),
    updated_at TEXT NOT NULL,
    provenance TEXT NOT NULL,
    UNIQUE(provider_id, round_id)
);

CREATE INDEX idx_rounds_provider_date ON service_rounds(provider_id, round_date);
CREATE INDEX idx_participation_provider_status ON provider_participations(provider_id, status);
"""

_MIGRATION_3 = """
ALTER TABLE providers ADD COLUMN base_area_id TEXT REFERENCES village_service_areas(area_id);

CREATE TABLE schedule_runs (
    schedule_id TEXT PRIMARY KEY,
    scenario_key TEXT NOT NULL CHECK(scenario_key IN
        ('efficiency','balanced','minimum_coverage')),
    budget_won INTEGER NOT NULL CHECK(budget_won >= 0),
    summary_json TEXT NOT NULL,
    provenance TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE scheduled_rounds (
    scheduled_round_id TEXT PRIMARY KEY,
    schedule_id TEXT NOT NULL REFERENCES schedule_runs(schedule_id) ON DELETE CASCADE,
    service_round_id TEXT NOT NULL UNIQUE REFERENCES service_rounds(round_id),
    provider_id TEXT NOT NULL REFERENCES providers(provider_id),
    area_id TEXT NOT NULL REFERENCES village_service_areas(area_id),
    service_type TEXT NOT NULL REFERENCES service_types(service_type_id),
    scheduled_date TEXT NOT NULL,
    departure_time TEXT NOT NULL,
    service_start_time TEXT NOT NULL,
    service_end_time TEXT NOT NULL,
    duration_minutes INTEGER NOT NULL CHECK(duration_minutes > 0),
    service_units INTEGER NOT NULL CHECK(service_units > 0),
    travel_before_s INTEGER NOT NULL CHECK(travel_before_s >= 0),
    travel_after_s INTEGER NOT NULL CHECK(travel_after_s >= 0),
    travel_distance_m INTEGER NOT NULL CHECK(travel_distance_m >= 0),
    service_cost_won INTEGER NOT NULL CHECK(service_cost_won >= 0),
    travel_cost_won INTEGER NOT NULL CHECK(travel_cost_won >= 0),
    minimum_compensation_topup_won INTEGER NOT NULL CHECK(minimum_compensation_topup_won >= 0),
    total_cost_won INTEGER NOT NULL CHECK(total_cost_won >= 0),
    provenance TEXT NOT NULL
);

CREATE INDEX idx_schedule_rounds_date
    ON scheduled_rounds(schedule_id, scheduled_date, departure_time);
CREATE INDEX idx_schedule_rounds_provider ON scheduled_rounds(provider_id, scheduled_date);
"""

_MIGRATION_4 = """
CREATE TABLE routes (
    route_id TEXT PRIMARY KEY,
    schedule_id TEXT NOT NULL REFERENCES schedule_runs(schedule_id) ON DELETE CASCADE,
    provider_id TEXT NOT NULL REFERENCES providers(provider_id),
    scheduled_date TEXT NOT NULL,
    route_type TEXT NOT NULL CHECK(route_type IN ('HUB_ROUND_TRIP', 'MULTI_STOP')),
    base_area_id TEXT NOT NULL REFERENCES village_service_areas(area_id),
    distance_m INTEGER NOT NULL CHECK(distance_m >= 0),
    duration_s INTEGER NOT NULL CHECK(duration_s >= 0),
    cost_won INTEGER NOT NULL CHECK(cost_won >= 0),
    old_distance_m INTEGER NOT NULL CHECK(old_distance_m >= 0),
    old_duration_s INTEGER NOT NULL CHECK(old_duration_s >= 0),
    old_cost_won INTEGER NOT NULL CHECK(old_cost_won >= 0),
    distance_savings_m INTEGER NOT NULL,
    duration_savings_s INTEGER NOT NULL,
    cost_savings_won INTEGER NOT NULL,
    provenance TEXT NOT NULL
);

ALTER TABLE scheduled_rounds ADD COLUMN route_id TEXT REFERENCES routes(route_id);
ALTER TABLE scheduled_rounds ADD COLUMN route_sequence INTEGER NOT NULL DEFAULT 1
    CHECK(route_sequence > 0);
ALTER TABLE scheduled_rounds ADD COLUMN route_type TEXT NOT NULL DEFAULT 'HUB_ROUND_TRIP'
    CHECK(route_type IN ('HUB_ROUND_TRIP', 'MULTI_STOP'));

CREATE TABLE route_stops (
    route_stop_id TEXT PRIMARY KEY,
    route_id TEXT NOT NULL REFERENCES routes(route_id) ON DELETE CASCADE,
    service_round_id TEXT NOT NULL UNIQUE REFERENCES scheduled_rounds(service_round_id)
        ON DELETE CASCADE,
    incoming_from_area_id TEXT NOT NULL REFERENCES village_service_areas(area_id),
    area_id TEXT NOT NULL REFERENCES village_service_areas(area_id),
    outgoing_to_area_id TEXT NOT NULL REFERENCES village_service_areas(area_id),
    sequence INTEGER NOT NULL CHECK(sequence > 0),
    service_start_time TEXT NOT NULL,
    service_end_time TEXT NOT NULL,
    incoming_time_s INTEGER NOT NULL CHECK(incoming_time_s >= 0),
    outgoing_time_s INTEGER NOT NULL CHECK(outgoing_time_s >= 0),
    incoming_distance_m INTEGER NOT NULL CHECK(incoming_distance_m >= 0),
    outgoing_distance_m INTEGER NOT NULL CHECK(outgoing_distance_m >= 0),
    UNIQUE(route_id, sequence)
);

CREATE INDEX idx_routes_schedule_provider_date
    ON routes(schedule_id, provider_id, scheduled_date);
CREATE INDEX idx_route_stops_order ON route_stops(route_id, sequence);
"""

_MIGRATION_5 = """
CREATE TABLE demand_forecasts (
    forecast_id TEXT PRIMARY KEY,
    region_id TEXT NOT NULL REFERENCES regions(region_id),
    service_type TEXT NOT NULL REFERENCES service_types(service_type_id),
    target_month TEXT NOT NULL CHECK(length(target_month) = 7),
    expected_rounds_low INTEGER CHECK(expected_rounds_low IS NULL OR expected_rounds_low >= 0),
    expected_rounds_mid INTEGER CHECK(expected_rounds_mid IS NULL OR expected_rounds_mid >= 0),
    expected_rounds_high INTEGER CHECK(expected_rounds_high IS NULL OR expected_rounds_high >= 0),
    confidence TEXT CHECK(confidence IS NULL OR confidence IN ('LOW','MEDIUM','HIGH')),
    evidence_status TEXT NOT NULL CHECK(
      evidence_status IN ('SUFFICIENT_OBSERVED','DATA_INSUFFICIENT')
    ),
    survey_required INTEGER NOT NULL CHECK(survey_required IN (0, 1)),
    observation_count INTEGER NOT NULL CHECK(observation_count >= 0),
    history_month_count INTEGER NOT NULL CHECK(history_month_count >= 0),
    observed_area_count INTEGER NOT NULL CHECK(observed_area_count >= 0),
    region_area_count INTEGER NOT NULL CHECK(region_area_count >= 0),
    source_diversity INTEGER NOT NULL CHECK(source_diversity >= 0),
    model_basis TEXT,
    model_version TEXT NOT NULL,
    input_fingerprint TEXT NOT NULL,
    insufficiency_reasons_json TEXT NOT NULL,
    provenance TEXT NOT NULL,
    generated_at TEXT NOT NULL,
    CHECK(
      (evidence_status='SUFFICIENT_OBSERVED'
       AND expected_rounds_low IS NOT NULL
       AND expected_rounds_mid IS NOT NULL
       AND expected_rounds_high IS NOT NULL
       AND expected_rounds_low <= expected_rounds_mid
       AND expected_rounds_mid <= expected_rounds_high)
      OR
      (evidence_status='DATA_INSUFFICIENT'
       AND expected_rounds_low IS NULL
       AND expected_rounds_mid IS NULL
       AND expected_rounds_high IS NULL)
    ),
    UNIQUE(region_id, service_type, target_month, model_version, input_fingerprint)
);

CREATE INDEX idx_forecasts_region_month
    ON demand_forecasts(region_id, service_type, target_month);
"""

_MIGRATION_6 = """
ALTER TABLE schedule_runs ADD COLUMN planning_policy_json TEXT NOT NULL DEFAULT '{}';
"""

_MIGRATION_7 = """
ALTER TABLE schedule_runs ADD COLUMN region_id TEXT NOT NULL DEFAULT 'pilot:홍성군 장곡면';
"""

_MIGRATION_8 = """
CREATE TABLE provider_date_availability (
    provider_id TEXT NOT NULL REFERENCES providers(provider_id) ON DELETE CASCADE,
    available_date TEXT NOT NULL,
    service_type TEXT NOT NULL REFERENCES service_types(service_type_id),
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    provenance TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY(provider_id, available_date, service_type, start_time),
    CHECK(start_time < end_time)
);
CREATE INDEX idx_provider_date_availability
    ON provider_date_availability(provider_id, available_date, service_type);

CREATE TABLE import_batches (
    batch_id TEXT PRIMARY KEY,
    import_type TEXT NOT NULL CHECK(import_type IN ('demand_observations','provider_availability')),
    content_sha256 TEXT NOT NULL,
    total_rows INTEGER NOT NULL CHECK(total_rows >= 0),
    valid_rows INTEGER NOT NULL DEFAULT 0 CHECK(valid_rows >= 0),
    needs_review_rows INTEGER NOT NULL DEFAULT 0 CHECK(needs_review_rows >= 0),
    failed_rows INTEGER NOT NULL DEFAULT 0 CHECK(failed_rows >= 0),
    provenance TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(import_type, content_sha256)
);

CREATE TABLE import_rows (
    row_id TEXT PRIMARY KEY,
    batch_id TEXT NOT NULL REFERENCES import_batches(batch_id) ON DELETE CASCADE,
    row_number INTEGER NOT NULL CHECK(row_number >= 2),
    status TEXT NOT NULL CHECK(status IN ('IMPORTED','NEEDS_REVIEW','FAILED')),
    record_json TEXT NOT NULL,
    issues_json TEXT NOT NULL,
    redacted INTEGER NOT NULL CHECK(redacted IN (0,1)),
    imported_record_id TEXT,
    reviewed_at TEXT,
    UNIQUE(batch_id, row_number)
);
CREATE INDEX idx_import_rows_batch_status ON import_rows(batch_id, status, row_number);
"""

_MIGRATION_9 = """
ALTER TABLE surveys ADD COLUMN structured_data_json TEXT NOT NULL DEFAULT '{}';

CREATE TABLE demand_structuring_drafts (
    draft_id TEXT PRIMARY KEY,
    area_id TEXT NOT NULL REFERENCES village_service_areas(area_id),
    survey_type TEXT NOT NULL CHECK(survey_type IN ('phone','village_meeting','proxy','field')),
    survey_date TEXT NOT NULL,
    source_text_redacted TEXT NOT NULL,
    source_text_was_redacted INTEGER NOT NULL CHECK(source_text_was_redacted IN (0,1)),
    structured_json TEXT NOT NULL,
    approved_json TEXT,
    status TEXT NOT NULL CHECK(status IN ('DRAFT','APPROVING','APPROVED','REJECTED')),
    approved_survey_ids_json TEXT NOT NULL DEFAULT '[]',
    provenance TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    reviewed_at TEXT
);
CREATE INDEX idx_demand_drafts_area_status
    ON demand_structuring_drafts(area_id, status, created_at DESC);
"""

_MIGRATION_10 = """
PRAGMA foreign_keys = OFF;
BEGIN;
CREATE TABLE import_batches_v10 (
    batch_id TEXT PRIMARY KEY,
    import_type TEXT NOT NULL CHECK(import_type IN
        ('demand_observations','provider_availability','existing_service_history')),
    content_sha256 TEXT NOT NULL,
    total_rows INTEGER NOT NULL CHECK(total_rows >= 0),
    valid_rows INTEGER NOT NULL DEFAULT 0 CHECK(valid_rows >= 0),
    needs_review_rows INTEGER NOT NULL DEFAULT 0 CHECK(needs_review_rows >= 0),
    failed_rows INTEGER NOT NULL DEFAULT 0 CHECK(failed_rows >= 0),
    provenance TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(import_type, content_sha256)
);
INSERT INTO import_batches_v10 SELECT * FROM import_batches;
DROP TABLE import_batches;
ALTER TABLE import_batches_v10 RENAME TO import_batches;

CREATE TABLE existing_service_history (
    history_id TEXT PRIMARY KEY,
    area_id TEXT NOT NULL REFERENCES village_service_areas(area_id),
    service_type TEXT NOT NULL REFERENCES service_types(service_type_id),
    program_name TEXT NOT NULL,
    monthly_rounds INTEGER NOT NULL CHECK(monthly_rounds BETWEEN 0 AND 31),
    as_of_date TEXT NOT NULL,
    provenance TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(area_id, service_type, program_name, as_of_date)
);
CREATE INDEX idx_existing_service_history_area_date
    ON existing_service_history(area_id, service_type, as_of_date DESC);
COMMIT;
PRAGMA foreign_keys = ON;
"""

_MIGRATION_11 = """
CREATE TABLE provider_participation_preferences (
    preference_id TEXT PRIMARY KEY,
    provider_id TEXT NOT NULL REFERENCES providers(provider_id) ON DELETE CASCADE,
    scope TEXT NOT NULL CHECK(scope IN ('MONTH', 'WEEK')),
    period_start TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('OPTED_IN', 'DECLINED')),
    updated_at TEXT NOT NULL,
    provenance TEXT NOT NULL,
    UNIQUE(provider_id, scope, period_start)
);
CREATE INDEX idx_provider_participation_preferences_provider_period
    ON provider_participation_preferences(provider_id, period_start);
"""


def database_path() -> Path:
    """Use a dedicated app database; keep the existing Kakao route cache separate."""
    configured = _load_config(APP_DATABASE_ENV)
    if configured:
        path = Path(configured).expanduser()
        return path if path.is_absolute() else ROOT / path
    return ROOT / "data" / "village_coverage_app.sqlite"


def _migrate(connection: sqlite3.Connection) -> None:
    version = int(connection.execute("PRAGMA user_version").fetchone()[0])
    if version > SCHEMA_VERSION:
        raise RuntimeError("app database schema is newer than this application")
    if version < 1:
        connection.executescript(_MIGRATION_1)
        connection.execute(
            "INSERT INTO schema_migrations(version, applied_at) VALUES (1, ?)",
            (_utc_now(),),
        )
        connection.execute("PRAGMA user_version = 1")
        version = 1
    if version < 2:
        connection.executescript(_MIGRATION_2)
        connection.execute(
            "INSERT INTO schema_migrations(version, applied_at) VALUES (2, ?)",
            (_utc_now(),),
        )
        connection.execute("PRAGMA user_version = 2")
        version = 2
    if version < 3:
        connection.executescript(_MIGRATION_3)
        connection.execute(
            "INSERT INTO schema_migrations(version, applied_at) VALUES (3, ?)",
            (_utc_now(),),
        )
        connection.execute("PRAGMA user_version = 3")
        version = 3
    if version < 4:
        connection.executescript(_MIGRATION_4)
        connection.execute(
            "INSERT INTO schema_migrations(version, applied_at) VALUES (4, ?)",
            (_utc_now(),),
        )
        connection.execute("PRAGMA user_version = 4")
        version = 4
    if version < 5:
        connection.executescript(_MIGRATION_5)
        connection.execute(
            "INSERT INTO schema_migrations(version, applied_at) VALUES (5, ?)",
            (_utc_now(),),
        )
        connection.execute("PRAGMA user_version = 5")
        version = 5
    if version < 6:
        connection.executescript(_MIGRATION_6)
        connection.execute(
            "INSERT INTO schema_migrations(version, applied_at) VALUES (6, ?)",
            (_utc_now(),),
        )
        connection.execute("PRAGMA user_version = 6")
        version = 6
    if version < 7:
        connection.executescript(_MIGRATION_7)
        connection.execute(
            "INSERT INTO schema_migrations(version, applied_at) VALUES (7, ?)",
            (_utc_now(),),
        )
        connection.execute("PRAGMA user_version = 7")
        version = 7
    if version < 8:
        connection.executescript(_MIGRATION_8)
        connection.execute(
            "INSERT INTO schema_migrations(version, applied_at) VALUES (8, ?)",
            (_utc_now(),),
        )
        connection.execute("PRAGMA user_version = 8")
        connection.commit()
        version = 8
    if version < 9:
        connection.executescript(_MIGRATION_9)
        connection.execute(
            "INSERT INTO schema_migrations(version, applied_at) VALUES (9, ?)",
            (_utc_now(),),
        )
        connection.execute("PRAGMA user_version = 9")
        connection.commit()
        version = 9
    if version < 10:
        connection.executescript(_MIGRATION_10)
        connection.execute(
            "INSERT INTO schema_migrations(version, applied_at) VALUES (10, ?)",
            (_utc_now(),),
        )
        connection.execute("PRAGMA user_version = 10")
        connection.commit()
        version = 10
    if version < 11:
        connection.executescript(_MIGRATION_11)
        connection.execute(
            "INSERT INTO schema_migrations(version, applied_at) VALUES (11, ?)",
            (_utc_now(),),
        )
        connection.execute("PRAGMA user_version = 11")
        connection.commit()


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    db_path = Path(path) if path is not None else database_path()
    with _CONNECT_LOCK:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(db_path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations "
            "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        _migrate(connection)
    return connection


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def seed_reference_data(connection: sqlite3.Connection, data: dict[str, Any]) -> None:
    """Persist all verified public region snapshots without facility contact fields."""
    areas = data.get("areas", [])
    if not areas:
        return
    for region in region_catalog(data):
        connection.execute(
            """INSERT INTO regions(region_id, province, county, town, provenance)
               VALUES (?, ?, ?, ?, 'REAL PUBLIC DATA')
               ON CONFLICT(region_id) DO UPDATE SET
                 province=excluded.province, county=excluded.county, town=excluded.town""",
            (
                region["region_id"],
                region["province"],
                region["county"],
                region["town"],
            ),
        )
    for area in areas:
        area_region_id = str(
            area.get("region_id")
            or make_region_id(str(area["county"]), str(area["town"]))
            or DEFAULT_REGION_ID
        )
        connection.execute(
            """INSERT INTO village_service_areas(
                 area_id, region_id, legal_code, name, facility_count, anchor_lat, anchor_lng,
                 provenance
               ) VALUES (?, ?, ?, ?, ?, ?, ?, 'REAL PUBLIC DATA')
               ON CONFLICT(area_id) DO UPDATE SET
                 region_id=excluded.region_id, legal_code=excluded.legal_code,
                 name=excluded.name, facility_count=excluded.facility_count,
                 anchor_lat=excluded.anchor_lat, anchor_lng=excluded.anchor_lng""",
            (
                area["id"],
                area_region_id,
                area["legal_code"],
                area["name"],
                int(area["facility_count"]),
                float(area["anchor_lat"]),
                float(area["anchor_lng"]),
            ),
        )
        population_date = str(area["public_data_reference_date"])
        connection.execute(
            """INSERT INTO population_snapshots VALUES (?, ?, ?, ?, ?, ?, 'REAL PUBLIC DATA')
               ON CONFLICT(area_id, reference_date) DO UPDATE SET
                 population_total=excluded.population_total,
                 population_65_plus=excluded.population_65_plus,
                 population_75_plus=excluded.population_75_plus,
                 population_80_plus=excluded.population_80_plus""",
            (
                area["id"],
                population_date,
                int(area["population_total"]),
                int(area["population_65_plus"]),
                int(area["population_75_plus"]),
                int(area["population_80_plus"]),
            ),
        )
        household_date = str(area["household_data_reference_date"])
        connection.execute(
            """INSERT INTO household_snapshots VALUES (?, ?, ?, ?, ?, ?, 'REAL PUBLIC DATA')
               ON CONFLICT(area_id, reference_date) DO UPDATE SET
                 households_total=excluded.households_total,
                 households_65_plus=excluded.households_65_plus,
                 households_75_plus=excluded.households_75_plus,
                 households_80_plus=excluded.households_80_plus""",
            (
                area["id"],
                household_date,
                int(area["single_households_total"]),
                int(area["single_households_65_plus"]),
                int(area["single_households_75_plus"]),
                int(area["single_households_80_plus"]),
            ),
        )
    for service in SERVICE_REGISTRY:
        connection.execute(
            """INSERT INTO service_types VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(service_type_id) DO UPDATE SET
                 label_ko=excluded.label_ko,
                 policy_status=excluded.policy_status,
                 policy_reason=excluded.policy_reason,
                 provenance=excluded.provenance""",
            (
                service.service_type_id,
                service.label_ko,
                service.policy_status,
                service.policy_reason,
                SERVICE_REGISTRY_PROVENANCE,
            ),
        )
    connection.commit()


def list_service_types(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    """Read the canonical persisted service policy registry."""
    return [
        dict(row)
        for row in connection.execute(
            """SELECT service_type_id, label_ko, policy_status, policy_reason, provenance
               FROM service_types ORDER BY
                 CASE policy_status WHEN 'ALLOWED' THEN 0 WHEN 'REGULATED' THEN 1 ELSE 2 END,
                 label_ko, service_type_id"""
        ).fetchall()
    ]


def seed_provider_data(connection: sqlite3.Connection, data: dict[str, Any]) -> None:
    """Create clearly synthetic provider profiles, history, availability and opportunities."""
    areas = data.get("areas", [])
    if not areas:
        return
    grouped_areas: dict[str, list[dict[str, Any]]] = {}
    for area in areas:
        identifier = str(
            area.get("region_id")
            or make_region_id(str(area.get("county", "")), str(area.get("town", "")))
        )
        grouped_areas.setdefault(identifier, []).append(area)
    if len(grouped_areas) > 1:
        for identifier, region_areas in grouped_areas.items():
            seed_provider_data(
                connection,
                {**data, "region_id": identifier, "areas": region_areas},
            )
        return
    selected_region_id = str(data.get("region_id") or next(iter(grouped_areas)))
    profiles = (
        {
            "id": "sim-provider-1",
            "name": "행복세탁",
            "services": ("laundry",),
            "weekdays": ("tuesday", "thursday"),
            "max_daily_hours": 6,
            "max_monthly_rounds": 12,
            "service_capacity": 4,
            "max_travel_time_minutes": 70,
            "minimum_compensation_won": 210_000,
            "base_area_index": 0,
        },
        {
            "id": "sim-provider-2",
            "name": "지역생활지원",
            "services": ("daily_necessities", "home_repair"),
            "weekdays": ("monday", "wednesday", "friday"),
            "max_daily_hours": 7,
            "max_monthly_rounds": 16,
            "service_capacity": 3,
            "max_travel_time_minutes": 60,
            "minimum_compensation_won": 240_000,
            "base_area_index": min(5, len(areas) - 1),
        },
        {
            "id": "sim-provider-3",
            "name": "마을생활협동조합",
            "services": ("laundry", "daily_necessities", "home_repair"),
            "weekdays": ("tuesday", "friday"),
            "max_daily_hours": 6,
            "max_monthly_rounds": 10,
            "service_capacity": 2,
            "max_travel_time_minutes": 80,
            "minimum_compensation_won": 180_000,
            "base_area_index": min(10, len(areas) - 1),
        },
    )
    weekdays = {
        "monday": 0,
        "tuesday": 1,
        "wednesday": 2,
        "thursday": 3,
        "friday": 4,
        "saturday": 5,
        "sunday": 6,
    }
    today = korea_today()
    for profile in profiles:
        provider_id = (
            str(profile["id"])
            if selected_region_id == DEFAULT_REGION_ID
            else f"{profile['id']}-{areas[0]['id']}"
        )
        area = areas[int(profile["base_area_index"])]
        connection.execute(
            """INSERT INTO providers(
                 provider_id, name, base_location, base_area_id, base_lat, base_lng,
                 max_daily_hours,
                 max_monthly_rounds, service_capacity, max_travel_time_minutes,
                 minimum_compensation_won, provenance
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'SIMULATED FOR PRE-R&D')
               ON CONFLICT(provider_id) DO UPDATE SET
                 name=excluded.name, base_location=excluded.base_location,
                 base_area_id=excluded.base_area_id,
                 base_lat=excluded.base_lat, base_lng=excluded.base_lng,
                 max_daily_hours=excluded.max_daily_hours,
                 max_monthly_rounds=excluded.max_monthly_rounds,
                 service_capacity=excluded.service_capacity,
                 max_travel_time_minutes=excluded.max_travel_time_minutes,
                 minimum_compensation_won=excluded.minimum_compensation_won""",
            (
                provider_id,
                profile["name"],
                f"{area['county']} {area['town']} 가상 거점",
                area["id"],
                area["anchor_lat"],
                area["anchor_lng"],
                profile["max_daily_hours"],
                profile["max_monthly_rounds"],
                profile["service_capacity"],
                profile["max_travel_time_minutes"],
                profile["minimum_compensation_won"],
            ),
        )
        for service in profile["services"]:
            connection.execute(
                "INSERT OR IGNORE INTO provider_services(provider_id, service_type) VALUES (?, ?)",
                (provider_id, service),
            )
        for weekday in profile["weekdays"]:
            connection.execute(
                """INSERT OR IGNORE INTO provider_availability(
                     provider_id, weekday, start_time, end_time
                   ) VALUES (?, ?, '09:00', '17:00')""",
                (provider_id, weekday),
            )

        service_type = profile["services"][0]
        for index in range(12):
            history_date = today - timedelta(days=(12 - index) * 7)
            round_id = f"sim-history-{provider_id}-{index + 1:02d}"
            area_for_round = areas[(index + int(profile["base_area_index"])) % len(areas)]
            connection.execute(
                """INSERT OR IGNORE INTO service_rounds(
                     round_id, provider_id, area_id, service_type, round_date, start_time,
                     duration_minutes, estimated_compensation_won, travel_time_minutes,
                     travel_distance_km, provenance
                   ) VALUES (?, ?, ?, ?, ?, '09:00', 60, ?, NULL, NULL,
                             'SIMULATED FOR PRE-R&D')""",
                (
                    round_id,
                    provider_id,
                    area_for_round["id"],
                    service_type,
                    history_date.isoformat(),
                    max(1, profile["minimum_compensation_won"] // 3),
                ),
            )
            status = "COMPLETED" if index < 9 else "CANCELLED" if index == 9 else "DECLINED"
            connection.execute(
                """INSERT OR IGNORE INTO provider_participations(
                     participation_id, provider_id, round_id, status, updated_at, provenance
                   ) VALUES (?, ?, ?, ?, ?, 'SIMULATED FOR PRE-R&D')""",
                (
                    f"sim-participation-{provider_id}-{index + 1:02d}",
                    provider_id,
                    round_id,
                    status,
                    _utc_now(),
                ),
            )

        opportunity_index = 0
        for weekday in profile["weekdays"]:
            target_weekday = weekdays[weekday]
            days_ahead = (target_weekday - today.weekday()) % 7
            first_date = today + timedelta(days=days_ahead)
            if first_date == today:
                first_date += timedelta(days=7)
            for week in range(2):
                round_date = first_date + timedelta(days=week * 7)
                area_for_round = areas[
                    (opportunity_index + int(profile["base_area_index"])) % len(areas)
                ]
                round_id = f"sim-opportunity-{provider_id}-{round_date:%Y%m%d}-{opportunity_index}"
                connection.execute(
                    """INSERT OR IGNORE INTO service_rounds(
                         round_id, provider_id, area_id, service_type, round_date, start_time,
                         duration_minutes, estimated_compensation_won, travel_time_minutes,
                         travel_distance_km, provenance
                       ) VALUES (?, ?, ?, ?, ?, '09:00', 60, ?, NULL, NULL,
                                 'SIMULATED FOR PRE-R&D')""",
                    (
                        round_id,
                        provider_id,
                        area_for_round["id"],
                        service_type,
                        round_date.isoformat(),
                        max(1, profile["minimum_compensation_won"] // 3),
                    ),
                )
                connection.execute(
                    """INSERT OR IGNORE INTO provider_participations(
                         participation_id, provider_id, round_id, status, updated_at, provenance
                       ) VALUES (?, ?, ?, 'AVAILABLE', ?, 'SIMULATED FOR PRE-R&D')""",
                    (
                        f"sim-participation-{round_id}",
                        provider_id,
                        round_id,
                        _utc_now(),
                    ),
                )
                opportunity_index += 1
    connection.commit()


def list_providers(
    connection: sqlite3.Connection, region_id: str | None = None
) -> list[dict[str, Any]]:
    rows = connection.execute(
        """SELECT p.*, a.region_id, r.province, r.county, r.town,
                  r.county || ' ' || r.town AS region_name,
                  COUNT(DISTINCT s.service_type) AS service_count
           FROM providers p LEFT JOIN provider_services s USING(provider_id)
           JOIN village_service_areas a ON a.area_id=p.base_area_id
           JOIN regions r USING(region_id)
           WHERE (? IS NULL OR a.region_id=?)
           GROUP BY p.provider_id ORDER BY p.name""",
        (region_id, region_id),
    ).fetchall()
    return [dict(row) for row in rows]


def _provider_demand_forecast(
    connection: sqlite3.Connection,
    supported_services: list[str],
    region_id: str | None = None,
) -> dict[str, Any]:
    regions = [
        dict(row)
        for row in connection.execute(
            """SELECT r.region_id, r.province, r.county, r.town,
                      COUNT(DISTINCT a.area_id) AS region_area_count
               FROM regions r LEFT JOIN village_service_areas a USING(region_id)
               WHERE (? IS NULL OR r.region_id=?)
               GROUP BY r.region_id ORDER BY r.province, r.county, r.town""",
            (region_id, region_id),
        ).fetchall()
    ]
    forecast_months: list[dict[str, Any]] = []
    for region in regions:
        region_name = " ".join(
            part for part in (region["province"], region["county"], region["town"]) if part
        )
        for service_type in supported_services:
            observations = [
                dict(row)
                for row in connection.execute(
                    """SELECT o.area_id, o.occurred_on, o.source_type, o.provenance,
                              s.frequency_per_month, s.created_at
                       FROM demand_observations o
                       JOIN village_service_areas a USING(area_id)
                       LEFT JOIN surveys s ON s.survey_id=o.survey_id
                       WHERE a.region_id=? AND o.service_type=?
                       ORDER BY o.occurred_on, s.created_at""",
                    (region["region_id"], service_type),
                ).fetchall()
            ]
            result = forecast_region_service(
                region_id=str(region["region_id"]),
                region_name=region_name,
                service_type=service_type,
                region_area_count=int(region["region_area_count"]),
                observations=observations,
            )
            for month in result["months"]:
                connection.execute(
                    """INSERT INTO demand_forecasts(
                         forecast_id, region_id, service_type, target_month,
                         expected_rounds_low, expected_rounds_mid, expected_rounds_high,
                         confidence, evidence_status, survey_required, observation_count,
                         history_month_count, observed_area_count, region_area_count,
                         source_diversity, model_basis, model_version, input_fingerprint,
                         insufficiency_reasons_json, provenance, generated_at
                       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(region_id, service_type, target_month, model_version,
                                   input_fingerprint) DO NOTHING""",
                    (
                        str(uuid4()),
                        region["region_id"],
                        service_type,
                        month["month"],
                        month["expected_rounds_low"],
                        month["expected_rounds_mid"],
                        month["expected_rounds_high"],
                        month["confidence"],
                        month["evidence_status"],
                        int(month["survey_required"]),
                        month["observation_count"],
                        month["history_month_count"],
                        month["observed_area_count"],
                        month["region_area_count"],
                        month["source_diversity"],
                        month["model_basis"],
                        MODEL_VERSION,
                        month["input_fingerprint"],
                        json.dumps(month["insufficiency_reasons"], ensure_ascii=False),
                        month["provenance"],
                        _utc_now(),
                    ),
                )
                forecast_months.append(month)
    if forecast_months:
        connection.commit()
    available_count = sum(
        month["evidence_status"] == "SUFFICIENT_OBSERVED" for month in forecast_months
    )
    if available_count == len(forecast_months) and available_count:
        message = "최근 연속 관측 이력의 중앙값과 변동폭으로 산출했습니다."
    elif available_count:
        message = "전망 가능 지역·서비스만 범위를 표시했습니다. 나머지는 추가 조사가 필요합니다."
    else:
        message = "관측 이력이 충분하지 않아 전망값을 만들지 않았습니다. 추가 조사가 필요합니다."
    return {
        "status": "AVAILABLE" if available_count else "DATA_INSUFFICIENT",
        "survey_required": not forecast_months or available_count < len(forecast_months),
        "months": forecast_months,
        "message": message,
        "provenance": "SURVEY INPUT; DETERMINISTIC FORECAST; SIMULATED FOR PRE-R&D",
        "model_version": MODEL_VERSION,
    }


def provider_detail(connection: sqlite3.Connection, provider_id: str) -> dict[str, Any] | None:
    provider_row = connection.execute(
        """SELECT p.*, a.region_id, r.province, r.county, r.town,
                  r.county || ' ' || r.town AS region_name
           FROM providers p JOIN village_service_areas a ON a.area_id=p.base_area_id
           JOIN regions r USING(region_id) WHERE p.provider_id=?""",
        (provider_id,),
    ).fetchone()
    if provider_row is None:
        return None
    provider = dict(provider_row)
    provider["supported_services"] = [
        row[0]
        for row in connection.execute(
            "SELECT service_type FROM provider_services WHERE provider_id=? ORDER BY service_type",
            (provider_id,),
        ).fetchall()
    ]
    provider["service_count"] = len(provider["supported_services"])
    provider["availability"] = [
        dict(row)
        for row in connection.execute(
            """SELECT weekday, start_time, end_time FROM provider_availability
               WHERE provider_id=? ORDER BY weekday, start_time""",
            (provider_id,),
        ).fetchall()
    ]
    provider["date_availability"] = [
        dict(row)
        for row in connection.execute(
            """SELECT available_date, service_type, start_time, end_time, provenance
               FROM provider_date_availability
               WHERE provider_id=? AND available_date>=?
               ORDER BY available_date, start_time, service_type""",
            (provider_id, korea_today().isoformat()),
        ).fetchall()
    ]
    history = connection.execute(
        """SELECT r.round_id, r.round_date, r.area_id, a.name AS area_name,
                  r.service_type, r.duration_minutes, r.estimated_compensation_won,
                  r.travel_time_minutes, r.travel_distance_km, p.status, p.provenance
           FROM provider_participations p JOIN service_rounds r USING(round_id)
           JOIN village_service_areas a USING(area_id)
           WHERE p.provider_id=? AND r.round_date<?
           ORDER BY r.round_date DESC, r.round_id DESC""",
        (provider_id, korea_today().isoformat()),
    ).fetchall()
    provider["history"] = [dict(row) for row in history]
    counts = {
        status: 0 for status in ("COMPLETED", "OPTED_IN", "DECLINED", "CANCELLED", "UNAVAILABLE")
    }
    for row in history:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    accepted = counts["COMPLETED"] + counts["OPTED_IN"] + counts["CANCELLED"]
    provider["participation"] = {
        "opportunities": len(history),
        "accepted": accepted,
        "completed": counts["COMPLETED"],
        "declined": counts["DECLINED"],
        "cancelled": counts["CANCELLED"],
        "completion_rate": counts["COMPLETED"] / accepted if accepted else None,
        "reliability_label": "반복 참여 안정적"
        if accepted >= 10 and counts["COMPLETED"] / accepted >= 0.8
        else "참여 이력 축적 중",
        "long_term_agreement_candidate": accepted >= 10 and counts["COMPLETED"] / accepted >= 0.8,
    }
    provider["participation_preferences"] = [
        dict(row)
        for row in connection.execute(
            """SELECT scope, period_start, status, updated_at, provenance
               FROM provider_participation_preferences
               WHERE provider_id=? ORDER BY period_start, scope""",
            (provider_id,),
        ).fetchall()
    ]
    upcoming_rows = connection.execute(
            """SELECT r.round_id, r.round_date, r.start_time, r.area_id, a.name AS area_name,
                      r.service_type, r.duration_minutes, r.estimated_compensation_won,
                      r.travel_time_minutes, r.travel_distance_km,
                      p.status AS stored_status,
                      p.provenance AS participation_provenance, r.provenance
               FROM service_rounds r JOIN village_service_areas a USING(area_id)
               LEFT JOIN provider_participations p
                 ON p.provider_id=r.provider_id AND p.round_id=r.round_id
               LEFT JOIN scheduled_rounds sr ON sr.service_round_id=r.round_id
               WHERE r.provider_id=? AND r.round_date>=?
                 AND (sr.schedule_id IS NULL OR sr.schedule_id=(
                   SELECT schedule_id FROM schedule_runs ORDER BY rowid DESC LIMIT 1
                 ))
               ORDER BY r.round_date, r.start_time""",
            (provider_id, korea_today().isoformat()),
        ).fetchall()
    preferences = {
        (row["scope"], row["period_start"]): row["status"]
        for row in provider["participation_preferences"]
    }
    upcoming_rounds = []
    for row in upcoming_rows:
        item = dict(row)
        round_date = date.fromisoformat(item["round_date"])
        month_start = round_date.replace(day=1).isoformat()
        week_start = (round_date - timedelta(days=round_date.weekday())).isoformat()
        week_key = ("WEEK", week_start)
        month_key = ("MONTH", month_start)
        if item["stored_status"] not in (None, "AVAILABLE"):
            item["status"] = item["stored_status"]
            if "PROVIDER WEEK PREFERENCE" in item.get("participation_provenance", ""):
                item["participation_source"] = "WEEK"
            elif "PROVIDER MONTH PREFERENCE" in item.get("participation_provenance", ""):
                item["participation_source"] = "MONTH"
            else:
                item["participation_source"] = "ROUND"
        elif week_key in preferences:
            item["status"] = preferences[week_key]
            item["participation_source"] = "WEEK"
        elif month_key in preferences:
            item["status"] = preferences[month_key]
            item["participation_source"] = "MONTH"
        else:
            item["status"] = "AVAILABLE"
            item["participation_source"] = None
        item.pop("stored_status")
        item.pop("participation_provenance", None)
        upcoming_rounds.append(item)
    provider["upcoming_rounds"] = upcoming_rounds
    provider["forecast"] = _provider_demand_forecast(
        connection, provider["supported_services"], str(provider["region_id"])
    )
    return provider


def save_schedule_plan(
    connection: sqlite3.Connection,
    *,
    scenario: str,
    budget_won: int,
    plan: dict[str, Any],
    planning_policy: dict[str, Any] | None = None,
    region_id: str = DEFAULT_REGION_ID,
) -> str:
    schedule_id = str(uuid4())
    created_at = _utc_now()
    provenance = "OPTIMIZATION RESULT; SIMULATED FOR PRE-R&D"
    summary = {key: value for key, value in plan.items() if key not in {"rounds", "routes"}}
    policy_snapshot = planning_policy or asdict(PlanningPolicy())
    connection.execute(
        """INSERT INTO schedule_runs(
             schedule_id, scenario_key, budget_won, summary_json, provenance, created_at,
             planning_policy_json, region_id
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            schedule_id,
            scenario,
            budget_won,
            json.dumps(summary, ensure_ascii=False),
            provenance,
            created_at,
            json.dumps(policy_snapshot, ensure_ascii=False, sort_keys=True),
            region_id,
        ),
    )
    round_ids: dict[tuple[str, str, str], str] = {}
    for index, item in enumerate(plan["rounds"], start=1):
        service_round_id = f"{schedule_id}-round-{index:03d}"
        round_provenance = provenance
        if item.get("time_window_source"):
            round_provenance += "; SURVEY INPUT; HUMAN REVIEW"
        round_ids[(str(item["provider_id"]), str(item["scheduled_date"]), str(item["area_id"]))] = (
            service_round_id
        )
        compensation = int(item["service_cost_won"]) + int(item["minimum_compensation_topup_won"])
        travel_seconds = int(item["travel_before_s"]) + int(item["travel_after_s"])
        connection.execute(
            """INSERT INTO service_rounds(
                 round_id, provider_id, area_id, service_type, round_date, start_time,
                 duration_minutes, estimated_compensation_won, travel_time_minutes,
                 travel_distance_km, provenance
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                service_round_id,
                item["provider_id"],
                item["area_id"],
                item["service_type"],
                item["scheduled_date"],
                item["service_start_time"],
                item["duration_minutes"],
                compensation,
                (travel_seconds + 59) // 60,
                item["travel_distance_m"] / 1000,
                round_provenance,
            ),
        )
        connection.execute(
            """INSERT INTO provider_participations(
                 participation_id, provider_id, round_id, status, updated_at, provenance
               ) VALUES (?, ?, ?, ?, ?, ?)""",
            (
                str(uuid4()),
                item["provider_id"],
                service_round_id,
                str(item.get("participation_status", "AVAILABLE")),
                created_at,
                (
                    f"{provenance}; PROVIDER {item['participation_source']} PREFERENCE"
                    if item.get("participation_source")
                    else provenance
                ),
            ),
        )
        connection.execute(
            """INSERT INTO scheduled_rounds(
                 scheduled_round_id, schedule_id, service_round_id, provider_id, area_id,
                 service_type, scheduled_date, departure_time, service_start_time,
                 service_end_time, duration_minutes, service_units, travel_before_s,
                 travel_after_s, travel_distance_m, service_cost_won, travel_cost_won,
                 minimum_compensation_topup_won, total_cost_won, provenance,
                 route_sequence, route_type
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                service_round_id,
                schedule_id,
                service_round_id,
                item["provider_id"],
                item["area_id"],
                item["service_type"],
                item["scheduled_date"],
                item["departure_time"],
                item["service_start_time"],
                item["service_end_time"],
                item["duration_minutes"],
                item["service_units"],
                item["travel_before_s"],
                item["travel_after_s"],
                item["travel_distance_m"],
                item["service_cost_won"],
                item["travel_cost_won"],
                item["minimum_compensation_topup_won"],
                item["total_cost_won"],
                round_provenance,
                int(item.get("route_sequence", 1)),
                str(item.get("route_type", "HUB_ROUND_TRIP")),
            ),
        )
    for route_index, route in enumerate(plan.get("routes", []), start=1):
        route_id = f"{schedule_id}-route-{route_index:03d}"
        connection.execute(
            """INSERT INTO routes(
                 route_id, schedule_id, provider_id, scheduled_date, route_type,
                 base_area_id, distance_m, duration_s, cost_won, old_distance_m,
                 old_duration_s, old_cost_won, distance_savings_m,
                 duration_savings_s, cost_savings_won, provenance
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                route_id,
                schedule_id,
                route["provider_id"],
                route["scheduled_date"],
                route["route_type"],
                route["base_area_id"],
                int(route["distance_m"]),
                int(route["duration_s"]),
                int(route["cost_won"]),
                int(route["old_hub_round_trip_distance_m"]),
                int(route["old_hub_round_trip_duration_s"]),
                int(route["old_hub_round_trip_cost_won"]),
                int(route["distance_savings_m"]),
                int(route["duration_savings"]),
                int(route["cost_savings_won"]),
                str(route.get("provenance", provenance)),
            ),
        )
        for stop in route["stops"]:
            round_key = (
                str(route["provider_id"]),
                str(route["scheduled_date"]),
                str(stop["area_id"]),
            )
            service_round_id = round_ids.get(round_key)
            if service_round_id is None:
                raise ValueError("route stop does not match a scheduled service round")
            connection.execute(
                """UPDATE scheduled_rounds
                   SET route_id=?, route_sequence=?, route_type=?
                   WHERE service_round_id=?""",
                (route_id, int(stop["sequence"]), route["route_type"], service_round_id),
            )
            connection.execute(
                """INSERT INTO route_stops(
                     route_stop_id, route_id, service_round_id, incoming_from_area_id,
                     area_id, outgoing_to_area_id, sequence, service_start_time,
                     service_end_time, incoming_time_s,
                     outgoing_time_s, incoming_distance_m, outgoing_distance_m
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    f"{route_id}-stop-{int(stop['sequence']):03d}",
                    route_id,
                    service_round_id,
                    stop["incoming_from_area_id"],
                    stop["area_id"],
                    stop["outgoing_to_area_id"],
                    int(stop["sequence"]),
                    stop["service_start_time"],
                    stop["service_end_time"],
                    int(stop["travel_before_s"]),
                    int(stop["travel_after_s"]),
                    int(stop["travel_before_distance_m"]),
                    int(stop["travel_after_distance_m"]),
                ),
            )
    connection.commit()
    return schedule_id


def get_schedule_plan(connection: sqlite3.Connection, schedule_id: str) -> dict[str, Any] | None:
    run = connection.execute(
        "SELECT * FROM schedule_runs WHERE schedule_id=?", (schedule_id,)
    ).fetchone()
    if run is None:
        return None
    result = dict(run)
    result["summary"] = json.loads(result.pop("summary_json"))
    result["planning_policy"] = json.loads(result.pop("planning_policy_json"))
    region = connection.execute(
        "SELECT county || ' ' || town FROM regions WHERE region_id=?",
        (result["region_id"],),
    ).fetchone()
    result["region_name"] = str(region[0]) if region is not None else ""
    result["rounds"] = [
        dict(row)
        for row in connection.execute(
            """SELECT sr.*, p.name AS provider_name, a.name AS area_name,
                      s.status AS participation_status,
                      CASE
                        WHEN s.provenance LIKE '%PROVIDER WEEK PREFERENCE%' THEN 'WEEK'
                        WHEN s.provenance LIKE '%PROVIDER MONTH PREFERENCE%' THEN 'MONTH'
                        WHEN s.status <> 'AVAILABLE' THEN 'ROUND'
                        ELSE NULL
                      END AS participation_source
               FROM scheduled_rounds sr
               JOIN providers p USING(provider_id)
               JOIN village_service_areas a USING(area_id)
               JOIN provider_participations s
                 ON s.provider_id=sr.provider_id AND s.round_id=sr.service_round_id
               WHERE sr.schedule_id=? ORDER BY sr.scheduled_date, sr.departure_time""",
            (schedule_id,),
        ).fetchall()
    ]
    result["routes"] = []
    for route_row in connection.execute(
        """SELECT r.*, p.name AS provider_name
           FROM routes r JOIN providers p USING(provider_id)
           WHERE r.schedule_id=?
           ORDER BY r.scheduled_date, r.provider_id, r.route_id""",
        (schedule_id,),
    ).fetchall():
        route = dict(route_row)
        route["stops"] = [
            dict(stop_row)
            for stop_row in connection.execute(
                """SELECT rs.*, a.name AS area_name, i.name AS incoming_from_area_name,
                          o.name AS outgoing_to_area_name
                   FROM route_stops rs JOIN village_service_areas a USING(area_id)
                   JOIN village_service_areas i ON i.area_id=rs.incoming_from_area_id
                   JOIN village_service_areas o ON o.area_id=rs.outgoing_to_area_id
                   WHERE rs.route_id=? ORDER BY rs.sequence""",
                (route["route_id"],),
            ).fetchall()
        ]
        result["routes"].append(route)
    return result


def list_schedule_history(
    connection: sqlite3.Connection, *, region_id: str | None = None, limit: int = 20
) -> list[dict[str, Any]]:
    rows = connection.execute(
        """SELECT sr.schedule_id, sr.scenario_key, sr.budget_won, sr.summary_json,
                  sr.planning_policy_json, sr.provenance, sr.created_at, sr.region_id,
                  r.county || ' ' || r.town AS region_name,
                  (SELECT COUNT(*) FROM scheduled_rounds rounds
                   WHERE rounds.schedule_id=sr.schedule_id) AS round_count
           FROM schedule_runs sr JOIN regions r USING(region_id)
           WHERE (? IS NULL OR sr.region_id=?)
           ORDER BY sr.created_at DESC, sr.rowid DESC LIMIT ?""",
        (region_id, region_id, limit),
    ).fetchall()
    result: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["summary"] = json.loads(item.pop("summary_json"))
        item["planning_policy"] = json.loads(item.pop("planning_policy_json"))
        result.append(item)
    return result


def update_participation(
    connection: sqlite3.Connection, *, provider_id: str, round_id: str, status: str
) -> bool:
    if status not in {"OPTED_IN", "DECLINED", "UNAVAILABLE", "AVAILABLE"}:
        raise ValueError("unsupported participation transition")
    round_row = connection.execute(
        """SELECT r.round_id, r.provider_id, r.round_date, r.start_time, r.duration_minutes,
                  r.service_type, p.max_monthly_rounds, p.max_daily_hours
           FROM service_rounds r JOIN providers p USING(provider_id)
           WHERE r.round_id=? AND r.provider_id=?""",
        (round_id, provider_id),
    ).fetchone()
    if round_row is None:
        return False
    if status == "OPTED_IN":
        scheduled = connection.execute(
            "SELECT schedule_id FROM scheduled_rounds WHERE service_round_id=?", (round_id,)
        ).fetchone()
        if scheduled is not None:
            latest_schedule = connection.execute(
                "SELECT schedule_id FROM schedule_runs ORDER BY rowid DESC LIMIT 1"
            ).fetchone()
            if (
                latest_schedule is None
                or scheduled["schedule_id"] != latest_schedule["schedule_id"]
            ):
                raise ValueError("this opportunity belongs to a superseded schedule")
        supported = connection.execute(
            "SELECT 1 FROM provider_services WHERE provider_id=? AND service_type=?",
            (provider_id, round_row["service_type"]),
        ).fetchone()
        if supported is None:
            raise ValueError("provider does not support this service")
        weekday = date.fromisoformat(round_row["round_date"]).strftime("%A").lower()
        dated_availability = connection.execute(
            """SELECT service_type, start_time, end_time FROM provider_date_availability
               WHERE provider_id=? AND available_date=?""",
            (provider_id, round_row["round_date"]),
        ).fetchall()
        availability = (
            [row for row in dated_availability if row["service_type"] == round_row["service_type"]]
            if dated_availability
            else connection.execute(
                """SELECT start_time, end_time FROM provider_availability
                   WHERE provider_id=? AND weekday=?""",
                (provider_id, weekday),
            ).fetchall()
        )
        start = datetime.strptime(round_row["start_time"], "%H:%M")
        end_minutes = start.hour * 60 + start.minute + int(round_row["duration_minutes"])
        if not any(
            datetime.strptime(row["start_time"], "%H:%M") <= start
            and datetime.strptime(row["end_time"], "%H:%M").hour * 60
            + datetime.strptime(row["end_time"], "%H:%M").minute
            >= end_minutes
            for row in availability
        ):
            raise ValueError("provider is unavailable during this round")
        if round_row["duration_minutes"] > round_row["max_daily_hours"] * 60:
            raise ValueError("round exceeds provider daily working hours")
        month_count = connection.execute(
            """SELECT COUNT(*) FROM provider_participations p
               JOIN service_rounds r USING(round_id)
               WHERE p.provider_id=? AND substr(r.round_date,1,7)=substr(?,1,7)
                 AND p.status IN ('OPTED_IN','COMPLETED') AND r.round_id<>?""",
            (provider_id, round_row["round_date"], round_id),
        ).fetchone()[0]
        if month_count >= round_row["max_monthly_rounds"]:
            raise ValueError("provider monthly round capacity is full")
    existing = connection.execute(
        "SELECT participation_id FROM provider_participations WHERE provider_id=? AND round_id=?",
        (provider_id, round_id),
    ).fetchone()
    participation_id = existing[0] if existing else str(uuid4())
    connection.execute(
        """INSERT INTO provider_participations(
             participation_id, provider_id, round_id, status, updated_at, provenance
           ) VALUES (?, ?, ?, ?, ?, 'SIMULATED FOR PRE-R&D')
           ON CONFLICT(provider_id, round_id) DO UPDATE SET
             status=excluded.status, updated_at=excluded.updated_at,
             provenance=excluded.provenance""",
        (participation_id, provider_id, round_id, status, _utc_now()),
    )
    connection.commit()
    return True


def set_participation_preference(
    connection: sqlite3.Connection,
    *,
    provider_id: str,
    scope: str,
    period_start: str,
    status: str,
) -> int:
    """Save a non-binding month/week preference without replacing round choices."""
    if scope not in {"MONTH", "WEEK"}:
        raise ValueError("unsupported participation preference scope")
    if status not in {"OPTED_IN", "DECLINED", "AVAILABLE"}:
        raise ValueError("unsupported participation preference status")
    try:
        start = date.fromisoformat(period_start)
    except ValueError as exc:
        raise ValueError("participation preference period is invalid") from exc
    if scope == "MONTH" and start.day != 1:
        raise ValueError("month preference must start on the first day of the month")
    if scope == "WEEK" and start.weekday() != 0:
        raise ValueError("week preference must start on Monday")
    if connection.execute(
        "SELECT 1 FROM providers WHERE provider_id=?", (provider_id,)
    ).fetchone() is None:
        raise ValueError("provider was not found")
    try:
        if scope == "WEEK":
            end = start + timedelta(days=7)
        else:
            end = date(start.year + (start.month == 12), start.month % 12 + 1, 1)
    except OverflowError as exc:
        raise ValueError("participation preference period is out of range") from exc
    eligible = connection.execute(
        """SELECT COUNT(*) FROM service_rounds r
           LEFT JOIN provider_participations p
             ON p.provider_id=r.provider_id AND p.round_id=r.round_id
           LEFT JOIN scheduled_rounds sr ON sr.service_round_id=r.round_id
           WHERE r.provider_id=? AND r.round_date>=? AND r.round_date<?
             AND r.round_date>=?
             AND (p.status IS NULL OR p.status='AVAILABLE')
             AND (sr.schedule_id IS NULL OR sr.schedule_id=(
               SELECT schedule_id FROM schedule_runs ORDER BY rowid DESC LIMIT 1
             ))""",
        (provider_id, start.isoformat(), end.isoformat(), korea_today().isoformat()),
    ).fetchone()[0]
    if status != "AVAILABLE" and eligible == 0:
        raise ValueError("no unreviewed opportunities exist in this period")
    if status == "AVAILABLE":
        connection.execute(
            """DELETE FROM provider_participation_preferences
               WHERE provider_id=? AND scope=? AND period_start=?""",
            (provider_id, scope, start.isoformat()),
        )
    else:
        connection.execute(
            """INSERT INTO provider_participation_preferences(
                 preference_id, provider_id, scope, period_start, status, updated_at, provenance
               ) VALUES (?, ?, ?, ?, ?, ?, 'SIMULATED FOR PRE-R&D')
               ON CONFLICT(provider_id, scope, period_start) DO UPDATE SET
                 status=excluded.status, updated_at=excluded.updated_at,
                 provenance=excluded.provenance""",
            (str(uuid4()), provider_id, scope, start.isoformat(), status, _utc_now()),
        )
    connection.commit()
    return int(eligible)


def insert_survey(
    connection: sqlite3.Connection,
    *,
    area_id: str,
    survey_type: str,
    survey_date: str,
    service_type: str,
    frequency_per_month: int | None,
    preferred_period: str | None,
    preferred_days: list[str],
    constraints: list[str],
    free_text_note: str,
    source_text_was_redacted: bool,
    structured_data: dict[str, Any] | None = None,
    provenance: str = "SIMULATED FOR PRE-R&D",
) -> str:
    survey_id = str(uuid4())
    observation_id = str(uuid4())
    evidence_id = str(uuid4())
    created_at = _utc_now()
    facts = {
        "service_type": service_type,
        "frequency_per_month": frequency_per_month,
        "preferred_period": preferred_period,
        "preferred_days": preferred_days,
        "constraints": constraints,
        "evidence_source": survey_type,
        "source_text_was_redacted": source_text_was_redacted,
        "follow_up_required": (
            bool(structured_data.get("needs_followup_survey", True))
            if structured_data is not None
            else True
        ),
    }
    if structured_data is not None:
        facts["structured_data"] = structured_data
    connection.execute(
        """INSERT INTO surveys(
             survey_id, area_id, survey_type, survey_date, service_type, frequency_per_month,
             preferred_period, preferred_days_json, constraints_json, free_text_note,
             source_text_was_redacted, provenance, created_at, structured_data_json
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            survey_id,
            area_id,
            survey_type,
            survey_date,
            service_type,
            frequency_per_month,
            preferred_period,
            json.dumps(preferred_days, ensure_ascii=False),
            json.dumps(constraints, ensure_ascii=False),
            free_text_note,
            int(source_text_was_redacted),
            provenance,
            created_at,
            json.dumps(structured_data or {}, ensure_ascii=False),
        ),
    )
    connection.execute(
        """INSERT INTO demand_observations(
             observation_id, area_id, survey_id, occurred_on, source_type, service_type,
             provenance, created_at
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            observation_id,
            area_id,
            survey_id,
            survey_date,
            survey_type,
            service_type,
            provenance,
            created_at,
        ),
    )
    connection.execute(
        """INSERT INTO demand_evidence(
             evidence_id, observation_id, evidence_type, payload_json, provenance, created_at
           ) VALUES (?, ?, 'survey_form', ?, ?, ?)""",
        (
            evidence_id,
            observation_id,
            json.dumps(facts, ensure_ascii=False),
            provenance,
            created_at,
        ),
    )
    return survey_id


def list_surveys(
    connection: sqlite3.Connection, area_id: str, service_type: str | None = None
) -> list[dict[str, Any]]:
    if service_type is None:
        rows = connection.execute(
            """SELECT survey_id, survey_type, survey_date, service_type, frequency_per_month,
                  preferred_period, preferred_days_json, constraints_json, free_text_note,
                  source_text_was_redacted, provenance, structured_data_json
               FROM surveys WHERE area_id = ? ORDER BY survey_date DESC, created_at DESC""",
            (area_id,),
        ).fetchall()
    else:
        rows = connection.execute(
            """SELECT survey_id, survey_type, survey_date, service_type, frequency_per_month,
                      preferred_period, preferred_days_json, constraints_json, free_text_note,
                      source_text_was_redacted, provenance, structured_data_json
               FROM surveys WHERE area_id = ? AND service_type = ?
               ORDER BY survey_date DESC, created_at DESC""",
            (area_id, service_type),
        ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["preferred_days"] = json.loads(item.pop("preferred_days_json"))
        item["constraints"] = json.loads(item.pop("constraints_json"))
        item["structured_data"] = json.loads(item.pop("structured_data_json"))
        item["source_text_was_redacted"] = bool(item["source_text_was_redacted"])
        result.append(item)
    return result


def insert_demand_structuring_draft(
    connection: sqlite3.Connection,
    *,
    area_id: str,
    survey_type: str,
    survey_date: str,
    source_text_redacted: str,
    source_text_was_redacted: bool,
    structured: dict[str, Any],
) -> str:
    draft_id = str(uuid4())
    now = _utc_now()
    connection.execute(
        """INSERT INTO demand_structuring_drafts(
             draft_id, area_id, survey_type, survey_date, source_text_redacted,
             source_text_was_redacted, structured_json, status, provenance, created_at, updated_at
           ) VALUES (?, ?, ?, ?, ?, ?, ?, 'DRAFT', 'SIMULATED HUMAN REVIEW', ?, ?)""",
        (
            draft_id,
            area_id,
            survey_type,
            survey_date,
            source_text_redacted,
            int(source_text_was_redacted),
            json.dumps(structured, ensure_ascii=False),
            now,
            now,
        ),
    )
    connection.commit()
    return draft_id


def get_demand_structuring_draft(
    connection: sqlite3.Connection, draft_id: str
) -> dict[str, Any] | None:
    row = connection.execute(
        "SELECT * FROM demand_structuring_drafts WHERE draft_id=?", (draft_id,)
    ).fetchone()
    if row is None:
        return None
    item = dict(row)
    item["source_text_was_redacted"] = bool(item["source_text_was_redacted"])
    item["structured"] = json.loads(item.pop("structured_json"))
    item["approved_survey_ids"] = json.loads(item.pop("approved_survey_ids_json"))
    approved_json = item.pop("approved_json")
    item["approved"] = json.loads(approved_json) if approved_json else None
    return item


def list_demand_structuring_drafts(
    connection: sqlite3.Connection, area_id: str, *, limit: int = 20
) -> list[dict[str, Any]]:
    rows = connection.execute(
        """SELECT draft_id FROM demand_structuring_drafts
           WHERE area_id=? AND status='DRAFT'
           ORDER BY created_at DESC LIMIT ?""",
        (area_id, limit),
    ).fetchall()
    return [
        draft
        for row in rows
        if (draft := get_demand_structuring_draft(connection, str(row["draft_id"]))) is not None
    ]


def claim_demand_structuring_draft(connection: sqlite3.Connection, draft_id: str) -> bool:
    cursor = connection.execute(
        """UPDATE demand_structuring_drafts SET status='APPROVING', updated_at=?
           WHERE draft_id=? AND status='DRAFT'""",
        (_utc_now(), draft_id),
    )
    return cursor.rowcount == 1


def approve_demand_structuring_draft(
    connection: sqlite3.Connection,
    *,
    draft_id: str,
    survey_ids: list[str],
    approved: dict[str, Any],
) -> bool:
    now = _utc_now()
    cursor = connection.execute(
        """UPDATE demand_structuring_drafts
           SET approved_json=?, status='APPROVED', approved_survey_ids_json=?,
               updated_at=?, reviewed_at=?
           WHERE draft_id=? AND status='APPROVING'""",
        (json.dumps(approved, ensure_ascii=False), json.dumps(survey_ids), now, now, draft_id),
    )
    return cursor.rowcount == 1


def save_assessment(
    connection: sqlite3.Connection,
    *,
    area_id: str,
    service_type: str,
    assessment: dict[str, Any],
    provenance: str = "SIMULATED FOR PRE-R&D",
    commit: bool = True,
) -> None:
    connection.execute(
        """INSERT INTO demand_assessments(
             area_id, service_type, observation_count, survey_count, source_diversity, missingness,
             latest_observation_date, deterministic_confidence, combined_confidence, status,
             needs_survey, limited_planning_allowed, evidence_reasons_json, provenance,
             calculated_at
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(area_id, service_type) DO UPDATE SET
             observation_count=excluded.observation_count, survey_count=excluded.survey_count,
             source_diversity=excluded.source_diversity, missingness=excluded.missingness,
             latest_observation_date=excluded.latest_observation_date,
             deterministic_confidence=excluded.deterministic_confidence,
             combined_confidence=excluded.combined_confidence, status=excluded.status,
             needs_survey=excluded.needs_survey,
             limited_planning_allowed=excluded.limited_planning_allowed,
             evidence_reasons_json=excluded.evidence_reasons_json,
             provenance=excluded.provenance,
             calculated_at=excluded.calculated_at""",
        (
            area_id,
            service_type,
            assessment["observation_count"],
            assessment["survey_count"],
            assessment["source_diversity"],
            assessment["missingness"],
            assessment["latest_observation_date"],
            assessment["deterministic_confidence"],
            assessment["combined_confidence"],
            assessment["status"],
            int(assessment["needs_survey"]),
            int(assessment["limited_planning_allowed"]),
            json.dumps(assessment["evidence_reasons"], ensure_ascii=False),
            provenance,
            _utc_now(),
        ),
    )
    if commit:
        connection.commit()


def upsert_existing_service_history(
    connection: sqlite3.Connection,
    *,
    history_id: str,
    area_id: str,
    service_type: str,
    program_name: str,
    monthly_rounds: int,
    as_of_date: str,
    provenance: str = "CSV_IMPORT",
) -> str:
    connection.execute(
        """INSERT INTO existing_service_history(
             history_id, area_id, service_type, program_name, monthly_rounds,
             as_of_date, provenance, created_at
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(area_id, service_type, program_name, as_of_date) DO UPDATE SET
             monthly_rounds=excluded.monthly_rounds,
             provenance=excluded.provenance,
             created_at=excluded.created_at""",
        (
            history_id,
            area_id,
            service_type,
            program_name,
            monthly_rounds,
            as_of_date,
            provenance,
            _utc_now(),
        ),
    )
    return history_id


def latest_existing_service_history(
    connection: sqlite3.Connection, area_id: str, service_type: str | None = None
) -> list[dict[str, Any]]:
    query = """SELECT history_id, area_id, service_type, program_name, monthly_rounds,
                      as_of_date, provenance
               FROM existing_service_history WHERE area_id=?"""
    parameters: tuple[Any, ...] = (area_id,)
    if service_type is not None:
        query += " AND service_type=?"
        parameters += (service_type,)
    query += " ORDER BY as_of_date DESC, created_at DESC"
    rows = connection.execute(query, parameters).fetchall()
    latest: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        item = dict(row)
        key = (str(item["service_type"]), str(item["program_name"]))
        latest.setdefault(key, item)
    return list(latest.values())


def find_import_batch(
    connection: sqlite3.Connection, import_type: str, content_sha256: str
) -> dict[str, Any] | None:
    row = connection.execute(
        "SELECT * FROM import_batches WHERE import_type=? AND content_sha256=?",
        (import_type, content_sha256),
    ).fetchone()
    return dict(row) if row is not None else None


def create_import_batch(
    connection: sqlite3.Connection,
    *,
    batch_id: str,
    import_type: str,
    content_sha256: str,
    total_rows: int,
) -> None:
    connection.execute(
        """INSERT INTO import_batches(
             batch_id, import_type, content_sha256, total_rows, provenance, created_at
           ) VALUES (?, ?, ?, ?, 'CSV_IMPORT', ?)""",
        (batch_id, import_type, content_sha256, total_rows, _utc_now()),
    )


def create_import_row(
    connection: sqlite3.Connection,
    *,
    row_id: str,
    batch_id: str,
    row_number: int,
    status: str,
    record: dict[str, Any],
    issues: list[str],
    redacted: bool,
    imported_record_id: str | None = None,
) -> None:
    connection.execute(
        """INSERT INTO import_rows(
             row_id, batch_id, row_number, status, record_json, issues_json,
             redacted, imported_record_id
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            row_id,
            batch_id,
            row_number,
            status,
            json.dumps(record, ensure_ascii=False, sort_keys=True),
            json.dumps(issues, ensure_ascii=False),
            int(redacted),
            imported_record_id,
        ),
    )


def update_import_batch_counts(connection: sqlite3.Connection, batch_id: str) -> None:
    counts = connection.execute(
        """SELECT COUNT(*) AS total_rows,
                  SUM(status='IMPORTED') AS valid_rows,
                  SUM(status='NEEDS_REVIEW') AS needs_review_rows,
                  SUM(status='FAILED') AS failed_rows
           FROM import_rows WHERE batch_id=?""",
        (batch_id,),
    ).fetchone()
    connection.execute(
        """UPDATE import_batches SET total_rows=?, valid_rows=?, needs_review_rows=?,
                  failed_rows=? WHERE batch_id=?""",
        (
            int(counts["total_rows"] or 0),
            int(counts["valid_rows"] or 0),
            int(counts["needs_review_rows"] or 0),
            int(counts["failed_rows"] or 0),
            batch_id,
        ),
    )


def _import_row_dict(row: sqlite3.Row) -> dict[str, Any]:
    result = dict(row)
    result["record"] = json.loads(result.pop("record_json"))
    result["issues"] = json.loads(result.pop("issues_json"))
    result["redacted"] = bool(result["redacted"])
    return result


def get_import_batch(connection: sqlite3.Connection, batch_id: str) -> dict[str, Any] | None:
    row = connection.execute(
        "SELECT * FROM import_batches WHERE batch_id=?", (batch_id,)
    ).fetchone()
    if row is None:
        return None
    result = dict(row)
    result["rows"] = [
        _import_row_dict(item)
        for item in connection.execute(
            "SELECT * FROM import_rows WHERE batch_id=? ORDER BY row_number", (batch_id,)
        ).fetchall()
    ]
    return result


def list_import_batches(connection: sqlite3.Connection, limit: int = 10) -> list[dict[str, Any]]:
    rows = connection.execute(
        "SELECT * FROM import_batches ORDER BY created_at DESC, rowid DESC LIMIT ?",
        (max(1, min(limit, 50)),),
    ).fetchall()
    return [dict(row) for row in rows]


def get_import_row(
    connection: sqlite3.Connection, batch_id: str, row_number: int
) -> dict[str, Any] | None:
    row = connection.execute(
        "SELECT * FROM import_rows WHERE batch_id=? AND row_number=?",
        (batch_id, row_number),
    ).fetchone()
    return _import_row_dict(row) if row is not None else None


def mark_import_row_imported(
    connection: sqlite3.Connection,
    *,
    batch_id: str,
    row_number: int,
    record: dict[str, Any],
    imported_record_id: str,
    redacted: bool,
) -> None:
    connection.execute(
        """UPDATE import_rows SET status='IMPORTED', record_json=?, issues_json='[]',
                  imported_record_id=?, reviewed_at=?, redacted=MAX(redacted, ?)
           WHERE batch_id=? AND row_number=? AND status='NEEDS_REVIEW'""",
        (
            json.dumps(record, ensure_ascii=False, sort_keys=True),
            imported_record_id,
            _utc_now(),
            int(redacted),
            batch_id,
            row_number,
        ),
    )
    update_import_batch_counts(connection, batch_id)


def import_date_availability(
    connection: sqlite3.Connection,
    *,
    provider_id: str,
    available_date: str,
    service_type: str,
    start_time: str,
    end_time: str,
) -> None:
    connection.execute(
        """INSERT INTO provider_date_availability(
             provider_id, available_date, service_type, start_time, end_time, provenance, updated_at
           ) VALUES (?, ?, ?, ?, ?, 'CSV_IMPORT', ?)
           ON CONFLICT(provider_id, available_date, service_type, start_time) DO UPDATE SET
             end_time=excluded.end_time, provenance=excluded.provenance,
             updated_at=excluded.updated_at""",
        (provider_id, available_date, service_type, start_time, end_time, _utc_now()),
    )
