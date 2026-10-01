from __future__ import annotations

import json
from pathlib import Path

from backend.database import connect, insert_survey, seed_reference_data

ROOT = Path(__file__).resolve().parents[1]


def test_app_database_migrates_once_and_contains_traceable_v2_tables(tmp_path) -> None:
    path = tmp_path / "app.sqlite"
    connection = connect(path)
    try:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 1
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert {
            "regions",
            "village_service_areas",
            "population_snapshots",
            "household_snapshots",
            "service_types",
            "surveys",
            "demand_observations",
            "demand_evidence",
            "demand_assessments",
            "schema_migrations",
        } <= tables
    finally:
        connection.close()

    connection = connect(path)
    try:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 1
        assert connection.execute("SELECT count(*) FROM schema_migrations").fetchone()[0] == 1
    finally:
        connection.close()


def test_reference_seed_keeps_public_snapshots_and_excluded_service_policy(tmp_path) -> None:
    data = json.loads((ROOT / "data" / "demo.json").read_text(encoding="utf-8"))
    connection = connect(tmp_path / "app.sqlite")
    try:
        seed_reference_data(connection, data)
        assert connection.execute("SELECT count(*) FROM village_service_areas").fetchone()[0] == 16
        assert connection.execute("SELECT count(*) FROM population_snapshots").fetchone()[0] == 16
        assert connection.execute("SELECT count(*) FROM household_snapshots").fetchone()[0] == 16
        service = connection.execute(
            "SELECT policy_status FROM service_types WHERE service_type_id='mobility_support'"
        ).fetchone()
        assert service[0] == "EXCLUDED"
        columns = {row[1] for row in connection.execute("PRAGMA table_info(village_service_areas)")}
        assert {"phone", "phone_number", "address", "manager_name"}.isdisjoint(columns)
    finally:
        connection.close()


def test_survey_creates_observation_and_evidence_rows(tmp_path) -> None:
    data = json.loads((ROOT / "data" / "demo.json").read_text(encoding="utf-8"))
    area = data["areas"][0]
    connection = connect(tmp_path / "app.sqlite")
    try:
        seed_reference_data(connection, data)
        survey_id = insert_survey(
            connection,
            area_id=area["id"],
            survey_type="phone",
            survey_date="2026-10-01",
            service_type="laundry",
            frequency_per_month=2,
            preferred_period="겨울",
            preferred_days=["tuesday"],
            constraints=["병원 방문일 제외"],
            free_text_note="화요일은 피하고 싶다고 함.",
            source_text_was_redacted=False,
        )
        assert (
            connection.execute(
                "SELECT survey_id FROM surveys WHERE survey_id=?", (survey_id,)
            ).fetchone()[0]
            == survey_id
        )
        assert (
            connection.execute(
                "SELECT count(*) FROM demand_observations WHERE survey_id=?", (survey_id,)
            ).fetchone()[0]
            == 1
        )
        evidence = connection.execute("SELECT payload_json FROM demand_evidence").fetchone()
        assert json.loads(evidence[0])["frequency_per_month"] == 2
        connection.commit()
    finally:
        connection.close()
