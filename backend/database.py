"""Versioned SQLite persistence for operational evidence and planning inputs."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from scripts.api_smoke_test import _load_config

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = 1
APP_DATABASE_ENV = "VILLAGECOVERAGE_APP_DB"

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
    if version == 0:
        connection.executescript(_MIGRATION_1)
        connection.execute(
            "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
            (SCHEMA_VERSION, _utc_now()),
        )
        connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        connection.commit()


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    db_path = Path(path) if path is not None else database_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path, timeout=5)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations "
        "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    _migrate(connection)
    return connection


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def seed_reference_data(connection: sqlite3.Connection, data: dict[str, Any]) -> None:
    """Persist the current public pilot reference snapshots without contact fields."""
    areas = data.get("areas", [])
    if not areas:
        return
    first = areas[0]
    region_id = "pilot:" + str(data.get("region") or first["town"])
    connection.execute(
        """INSERT INTO regions(region_id, province, county, town, provenance)
           VALUES (?, ?, ?, ?, 'REAL PUBLIC DATA')
           ON CONFLICT(region_id) DO UPDATE SET
             province=excluded.province, county=excluded.county, town=excluded.town""",
        (region_id, first["province"], first["county"], first["town"]),
    )
    for area in areas:
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
                region_id,
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
    allowed_services = (
        ("laundry", "세탁", "초기 지원 서비스"),
        ("daily_necessities", "생활용품 전달·지원", "초기 지원 서비스"),
        ("home_repair", "간단한 주거생활 지원", "초기 지원 서비스"),
    )
    for service_id, label, reason in allowed_services:
        connection.execute(
            """INSERT INTO service_types VALUES (?, ?, 'ALLOWED', ?, 'SIMULATED FOR PRE-R&D')
               ON CONFLICT(service_type_id) DO UPDATE SET
                 label_ko=excluded.label_ko,
                 policy_status='ALLOWED',
                 policy_reason=excluded.policy_reason""",
            (service_id, label, reason),
        )
    connection.execute(
        """INSERT INTO service_types VALUES
             ('mobility_support', '이동 지원', 'EXCLUDED', '초기 지원 범위 정책 검토 필요',
              'SIMULATED FOR PRE-R&D')
           ON CONFLICT(service_type_id) DO UPDATE SET
             policy_status='EXCLUDED', policy_reason=excluded.policy_reason"""
    )
    connection.commit()


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
) -> str:
    survey_id = str(uuid4())
    observation_id = str(uuid4())
    evidence_id = str(uuid4())
    created_at = _utc_now()
    provenance = "SIMULATED FOR PRE-R&D"
    facts = {
        "service_type": service_type,
        "frequency_per_month": frequency_per_month,
        "preferred_period": preferred_period,
        "preferred_days": preferred_days,
        "constraints": constraints,
        "follow_up_required": True,
    }
    connection.execute(
        """INSERT INTO surveys(
             survey_id, area_id, survey_type, survey_date, service_type, frequency_per_month,
             preferred_period, preferred_days_json, constraints_json, free_text_note,
             source_text_was_redacted, provenance, created_at
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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


def list_surveys(connection: sqlite3.Connection, area_id: str) -> list[dict[str, Any]]:
    rows = connection.execute(
        """SELECT survey_id, survey_type, survey_date, service_type, frequency_per_month,
                  preferred_period, preferred_days_json, constraints_json, free_text_note,
                  source_text_was_redacted, provenance
           FROM surveys WHERE area_id = ? ORDER BY survey_date DESC, created_at DESC""",
        (area_id,),
    ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["preferred_days"] = json.loads(item.pop("preferred_days_json"))
        item["constraints"] = json.loads(item.pop("constraints_json"))
        item["source_text_was_redacted"] = bool(item["source_text_was_redacted"])
        result.append(item)
    return result


def save_assessment(
    connection: sqlite3.Connection, *, area_id: str, service_type: str, assessment: dict[str, Any]
) -> None:
    connection.execute(
        """INSERT INTO demand_assessments(
             area_id, service_type, observation_count, survey_count, source_diversity, missingness,
             latest_observation_date, deterministic_confidence, combined_confidence, status,
             needs_survey, limited_planning_allowed, evidence_reasons_json, provenance,
             calculated_at
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'SIMULATED FOR PRE-R&D', ?)
           ON CONFLICT(area_id, service_type) DO UPDATE SET
             observation_count=excluded.observation_count, survey_count=excluded.survey_count,
             source_diversity=excluded.source_diversity, missingness=excluded.missingness,
             latest_observation_date=excluded.latest_observation_date,
             deterministic_confidence=excluded.deterministic_confidence,
             combined_confidence=excluded.combined_confidence, status=excluded.status,
             needs_survey=excluded.needs_survey,
             limited_planning_allowed=excluded.limited_planning_allowed,
             evidence_reasons_json=excluded.evidence_reasons_json,
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
            _utc_now(),
        ),
    )
    connection.commit()
