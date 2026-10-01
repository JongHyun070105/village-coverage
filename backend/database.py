"""Versioned SQLite persistence for operational evidence and planning inputs."""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from scripts.api_smoke_test import _load_config

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = 3
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


def seed_provider_data(connection: sqlite3.Connection, data: dict[str, Any]) -> None:
    """Create clearly synthetic provider profiles, history, availability and opportunities."""
    areas = data.get("areas", [])
    if not areas:
        return
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
    today = date.today()
    for profile in profiles:
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
                profile["id"],
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
                (profile["id"], service),
            )
        for weekday in profile["weekdays"]:
            connection.execute(
                """INSERT OR IGNORE INTO provider_availability(
                     provider_id, weekday, start_time, end_time
                   ) VALUES (?, ?, '09:00', '17:00')""",
                (profile["id"], weekday),
            )

        service_type = profile["services"][0]
        for index in range(12):
            history_date = today - timedelta(days=(12 - index) * 7)
            round_id = f"sim-history-{profile['id']}-{index + 1:02d}"
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
                    profile["id"],
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
                    f"sim-participation-{profile['id']}-{index + 1:02d}",
                    profile["id"],
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
                round_id = (
                    f"sim-opportunity-{profile['id']}-{round_date:%Y%m%d}-{opportunity_index}"
                )
                connection.execute(
                    """INSERT OR IGNORE INTO service_rounds(
                         round_id, provider_id, area_id, service_type, round_date, start_time,
                         duration_minutes, estimated_compensation_won, travel_time_minutes,
                         travel_distance_km, provenance
                       ) VALUES (?, ?, ?, ?, ?, '09:00', 60, ?, NULL, NULL,
                                 'SIMULATED FOR PRE-R&D')""",
                    (
                        round_id,
                        profile["id"],
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
                        profile["id"],
                        round_id,
                        _utc_now(),
                    ),
                )
                opportunity_index += 1
    connection.commit()


def list_providers(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = connection.execute(
        """SELECT p.*, COUNT(DISTINCT s.service_type) AS service_count
           FROM providers p LEFT JOIN provider_services s USING(provider_id)
           GROUP BY p.provider_id ORDER BY p.name"""
    ).fetchall()
    return [dict(row) for row in rows]


def provider_detail(connection: sqlite3.Connection, provider_id: str) -> dict[str, Any] | None:
    provider_row = connection.execute(
        "SELECT * FROM providers WHERE provider_id=?", (provider_id,)
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
    history = connection.execute(
        """SELECT r.round_id, r.round_date, r.area_id, a.name AS area_name,
                  r.service_type, r.duration_minutes, r.estimated_compensation_won,
                  r.travel_time_minutes, r.travel_distance_km, p.status, p.provenance
           FROM provider_participations p JOIN service_rounds r USING(round_id)
           JOIN village_service_areas a USING(area_id)
           WHERE p.provider_id=? AND r.round_date<?
           ORDER BY r.round_date DESC, r.round_id DESC""",
        (provider_id, date.today().isoformat()),
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
    provider["upcoming_rounds"] = [
        dict(row)
        for row in connection.execute(
            """SELECT r.round_id, r.round_date, r.start_time, r.area_id, a.name AS area_name,
                      r.service_type, r.duration_minutes, r.estimated_compensation_won,
                      r.travel_time_minutes, r.travel_distance_km,
                      COALESCE(p.status, 'AVAILABLE') AS status, r.provenance
               FROM service_rounds r JOIN village_service_areas a USING(area_id)
               LEFT JOIN provider_participations p
                 ON p.provider_id=r.provider_id AND p.round_id=r.round_id
               LEFT JOIN scheduled_rounds sr ON sr.service_round_id=r.round_id
               WHERE r.provider_id=? AND r.round_date>=?
                 AND (sr.schedule_id IS NULL OR sr.schedule_id=(
                   SELECT schedule_id FROM schedule_runs ORDER BY rowid DESC LIMIT 1
                 ))
               ORDER BY r.round_date, r.start_time""",
            (provider_id, date.today().isoformat()),
        ).fetchall()
    ]
    provider["forecast"] = {
        "status": "DATA_INSUFFICIENT",
        "survey_required": True,
        "months": [],
        "message": "관측 이력이 부족해 3개월 수요 회차 범위를 산출하지 않았습니다.",
        "provenance": "SIMULATED FOR PRE-R&D",
    }
    return provider


def save_schedule_plan(
    connection: sqlite3.Connection, *, scenario: str, budget_won: int, plan: dict[str, Any]
) -> str:
    schedule_id = str(uuid4())
    created_at = _utc_now()
    provenance = "OPTIMIZATION RESULT; SIMULATED FOR PRE-R&D"
    summary = {key: value for key, value in plan.items() if key != "rounds"}
    connection.execute(
        """INSERT INTO schedule_runs(
             schedule_id, scenario_key, budget_won, summary_json, provenance, created_at
           ) VALUES (?, ?, ?, ?, ?, ?)""",
        (
            schedule_id,
            scenario,
            budget_won,
            json.dumps(summary, ensure_ascii=False),
            provenance,
            created_at,
        ),
    )
    for index, item in enumerate(plan["rounds"], start=1):
        service_round_id = f"{schedule_id}-round-{index:03d}"
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
                provenance,
            ),
        )
        connection.execute(
            """INSERT INTO provider_participations(
                 participation_id, provider_id, round_id, status, updated_at, provenance
               ) VALUES (?, ?, ?, 'AVAILABLE', ?, ?)""",
            (str(uuid4()), item["provider_id"], service_round_id, created_at, provenance),
        )
        connection.execute(
            """INSERT INTO scheduled_rounds(
                 scheduled_round_id, schedule_id, service_round_id, provider_id, area_id,
                 service_type, scheduled_date, departure_time, service_start_time,
                 service_end_time, duration_minutes, service_units, travel_before_s,
                 travel_after_s, travel_distance_m, service_cost_won, travel_cost_won,
                 minimum_compensation_topup_won, total_cost_won, provenance
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
                provenance,
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
    result["rounds"] = [
        dict(row)
        for row in connection.execute(
            """SELECT sr.*, p.name AS provider_name, a.name AS area_name,
                      s.status AS participation_status
               FROM scheduled_rounds sr
               JOIN providers p USING(provider_id)
               JOIN village_service_areas a USING(area_id)
               JOIN provider_participations s
                 ON s.provider_id=sr.provider_id AND s.round_id=sr.service_round_id
               WHERE sr.schedule_id=? ORDER BY sr.scheduled_date, sr.departure_time""",
            (schedule_id,),
        ).fetchall()
    ]
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
        availability = connection.execute(
            """SELECT start_time, end_time FROM provider_availability
               WHERE provider_id=? AND weekday=?""",
            (provider_id, weekday),
        ).fetchall()
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
             status=excluded.status, updated_at=excluded.updated_at""",
        (participation_id, provider_id, round_id, status, _utc_now()),
    )
    connection.commit()
    return True


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


def list_surveys(
    connection: sqlite3.Connection, area_id: str, service_type: str | None = None
) -> list[dict[str, Any]]:
    if service_type is None:
        rows = connection.execute(
            """SELECT survey_id, survey_type, survey_date, service_type, frequency_per_month,
                  preferred_period, preferred_days_json, constraints_json, free_text_note,
                  source_text_was_redacted, provenance
               FROM surveys WHERE area_id = ? ORDER BY survey_date DESC, created_at DESC""",
            (area_id,),
        ).fetchall()
    else:
        rows = connection.execute(
            """SELECT survey_id, survey_type, survey_date, service_type, frequency_per_month,
                      preferred_period, preferred_days_json, constraints_json, free_text_note,
                      source_text_was_redacted, provenance
               FROM surveys WHERE area_id = ? AND service_type = ?
               ORDER BY survey_date DESC, created_at DESC""",
            (area_id, service_type),
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
