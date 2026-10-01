from __future__ import annotations

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

from backend import database
from backend.database import (
    connect,
    get_schedule_plan,
    insert_survey,
    provider_detail,
    save_schedule_plan,
    seed_provider_data,
    seed_reference_data,
    update_participation,
)

ROOT = Path(__file__).resolve().parents[1]


def test_app_database_migrates_once_and_contains_traceable_v3_tables(tmp_path) -> None:
    path = tmp_path / "app.sqlite"
    connection = connect(path)
    try:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 3
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
            "providers",
            "provider_services",
            "provider_availability",
            "service_rounds",
            "provider_participations",
            "schedule_runs",
            "scheduled_rounds",
        } <= tables
    finally:
        connection.close()


def test_database_initialization_serializes_concurrent_first_connections(tmp_path) -> None:
    path = tmp_path / "parallel-init.sqlite"

    def open_and_read_version(_index):
        connection = connect(path)
        try:
            return connection.execute("PRAGMA user_version").fetchone()[0]
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=5) as executor:
        versions = list(executor.map(open_and_read_version, range(5)))
    assert versions == [3] * 5


def test_app_database_upgrades_schema_version_one_through_all_migrations(tmp_path) -> None:
    path = tmp_path / "v1.sqlite"
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        connection.executescript(database._MIGRATION_1)
        connection.execute(
            "INSERT INTO regions VALUES "
            "('existing-v1', '충청남도', '홍성군', '장곡면', 'REAL DATA')"
        )
        connection.execute("INSERT INTO schema_migrations VALUES (1, '2026-01-01T00:00:00+00:00')")
        connection.execute("PRAGMA user_version=1")
        connection.commit()
    finally:
        connection.close()

    upgraded = connect(path)
    try:
        assert upgraded.execute("PRAGMA user_version").fetchone()[0] == 3
        assert upgraded.execute("SELECT region_id FROM regions").fetchone()[0] == "existing-v1"
        assert upgraded.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0] == 3
        assert upgraded.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='scheduled_rounds'"
        ).fetchone()
    finally:
        upgraded.close()


def test_app_database_upgrades_schema_version_two_without_losing_existing_rows(tmp_path) -> None:
    path = tmp_path / "v2.sqlite"
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        connection.executescript(database._MIGRATION_1)
        connection.executescript(database._MIGRATION_2)
        connection.execute(
            "INSERT INTO regions VALUES ('existing', '충청남도', '홍성군', '장곡면', 'REAL DATA')"
        )
        connection.execute("INSERT INTO schema_migrations VALUES (1, '2026-01-01T00:00:00+00:00')")
        connection.execute("INSERT INTO schema_migrations VALUES (2, '2026-01-02T00:00:00+00:00')")
        connection.execute("PRAGMA user_version=2")
        connection.commit()
    finally:
        connection.close()

    upgraded = connect(path)
    try:
        assert upgraded.execute("PRAGMA user_version").fetchone()[0] == 3
        assert upgraded.execute("SELECT region_id FROM regions").fetchone()[0] == "existing"
        assert upgraded.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0] == 3
        assert (
            upgraded.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='providers'"
            ).fetchone()[0]
            == "providers"
        )
    finally:
        upgraded.close()

    connection = connect(path)
    try:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 3
        assert connection.execute("SELECT count(*) FROM schema_migrations").fetchone()[0] == 3
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


def test_provider_profiles_history_availability_and_opt_in_persist(tmp_path) -> None:
    data = json.loads((ROOT / "data" / "demo.json").read_text(encoding="utf-8"))
    connection = connect(tmp_path / "app.sqlite")
    try:
        seed_reference_data(connection, data)
        seed_provider_data(connection, data)
        provider = provider_detail(connection, "sim-provider-1")
        assert provider is not None
        assert provider["name"] == "행복세탁"
        assert provider["supported_services"] == ["laundry"]
        assert provider["base_area_id"] == data["areas"][0]["id"]
        assert provider["max_monthly_rounds"] == 12
        assert provider["max_travel_time_minutes"] == 70
        assert {row["weekday"] for row in provider["availability"]} == {"tuesday", "thursday"}
        assert provider["participation"] == {
            "opportunities": 12,
            "accepted": 10,
            "completed": 9,
            "declined": 2,
            "cancelled": 1,
            "completion_rate": 0.9,
            "reliability_label": "반복 참여 안정적",
            "long_term_agreement_candidate": True,
        }
        assert len(provider["upcoming_rounds"]) == 4
        assert all(row["status"] == "AVAILABLE" for row in provider["upcoming_rounds"])
        assert (
            connection.execute(
                """SELECT count(*) FROM provider_participations
                   WHERE provider_id=? AND status='AVAILABLE'""",
                ("sim-provider-1",),
            ).fetchone()[0]
            == 4
        )
        assert provider["forecast"]["status"] == "DATA_INSUFFICIENT"
        round_id = provider["upcoming_rounds"][0]["round_id"]
        assert update_participation(
            connection,
            provider_id="sim-provider-1",
            round_id=round_id,
            status="OPTED_IN",
        )
        updated = provider_detail(connection, "sim-provider-1")
        assert updated["upcoming_rounds"][0]["status"] == "OPTED_IN"
    finally:
        connection.close()


def test_provider_opt_in_rejects_unsupported_service_unavailability_and_capacity(tmp_path) -> None:
    data = json.loads((ROOT / "data" / "demo.json").read_text(encoding="utf-8"))
    connection = connect(tmp_path / "app.sqlite")
    try:
        seed_reference_data(connection, data)
        seed_provider_data(connection, data)
        provider = provider_detail(connection, "sim-provider-1")
        assert provider is not None
        round_id = provider["upcoming_rounds"][0]["round_id"]
        connection.execute(
            "UPDATE service_rounds SET service_type='daily_necessities' WHERE round_id=?",
            (round_id,),
        )
        try:
            update_participation(
                connection,
                provider_id="sim-provider-1",
                round_id=round_id,
                status="OPTED_IN",
            )
        except ValueError as exc:
            assert "does not support" in str(exc)
        else:
            raise AssertionError("unsupported service opt-in should fail")

        connection.execute(
            "UPDATE service_rounds SET service_type='laundry' WHERE round_id=?", (round_id,)
        )
        weekday = (
            date.fromisoformat(provider["upcoming_rounds"][0]["round_date"]).strftime("%A").lower()
        )
        connection.execute(
            "DELETE FROM provider_availability WHERE provider_id='sim-provider-1' AND weekday=?",
            (weekday,),
        )
        try:
            update_participation(
                connection,
                provider_id="sim-provider-1",
                round_id=round_id,
                status="OPTED_IN",
            )
        except ValueError as exc:
            assert "unavailable" in str(exc)
        else:
            raise AssertionError("unavailable provider opt-in should fail")

        connection.execute(
            "INSERT INTO provider_availability VALUES ('sim-provider-1', ?, '09:00', '17:00')",
            (weekday,),
        )
        connection.execute(
            "UPDATE providers SET max_monthly_rounds=0 WHERE provider_id='sim-provider-1'"
        )
        try:
            update_participation(
                connection,
                provider_id="sim-provider-1",
                round_id=round_id,
                status="OPTED_IN",
            )
        except ValueError as exc:
            assert "capacity is full" in str(exc)
        else:
            raise AssertionError("monthly capacity overflow should fail")
    finally:
        connection.close()


def test_schedule_plan_persists_round_cost_provenance_and_provider_opportunity(tmp_path) -> None:
    data = json.loads((ROOT / "data" / "demo.json").read_text(encoding="utf-8"))
    connection = connect(tmp_path / "app.sqlite")
    try:
        seed_reference_data(connection, data)
        seed_provider_data(connection, data)
        round_date = (date.today() + timedelta(days=1)).isoformat()
        round_item = {
            "provider_id": "sim-provider-1",
            "area_id": data["areas"][0]["id"],
            "service_type": "laundry",
            "scheduled_date": round_date,
            "departure_time": "09:00",
            "service_start_time": "09:10",
            "service_end_time": "10:10",
            "duration_minutes": 60,
            "service_units": 2,
            "travel_before_s": 600,
            "travel_after_s": 600,
            "travel_distance_m": 10000,
            "service_cost_won": 510000,
            "travel_cost_won": 25000,
            "minimum_compensation_topup_won": 0,
            "total_cost_won": 535000,
        }
        schedule_id = save_schedule_plan(
            connection,
            scenario="efficiency",
            budget_won=1_000_000,
            plan={
                "served_units": 2,
                "total_cost_won": 535000,
                "travel_source": "Kakao road cache",
                "rounds": [round_item],
            },
        )
        saved = get_schedule_plan(connection, schedule_id)
        assert saved is not None
        assert saved["scenario_key"] == "efficiency"
        assert saved["summary"]["served_units"] == 2
        assert saved["rounds"][0]["service_units"] == 2
        assert saved["rounds"][0]["total_cost_won"] == 535000
        assert saved["rounds"][0]["participation_status"] == "AVAILABLE"
        assert saved["rounds"][0]["provenance"] == "OPTIMIZATION RESULT; SIMULATED FOR PRE-R&D"

        next_round = {
            **round_item,
            "scheduled_date": (date.today() + timedelta(days=2)).isoformat(),
        }
        latest_schedule_id = save_schedule_plan(
            connection,
            scenario="balanced",
            budget_won=1_000_000,
            plan={"served_units": 2, "total_cost_won": 535000, "rounds": [next_round]},
        )
        latest_round_id = f"{latest_schedule_id}-round-001"
        provider = provider_detail(connection, "sim-provider-1")
        assert provider is not None
        upcoming_ids = {row["round_id"] for row in provider["upcoming_rounds"]}
        assert f"{schedule_id}-round-001" not in upcoming_ids
        assert latest_round_id in upcoming_ids
        try:
            update_participation(
                connection,
                provider_id="sim-provider-1",
                round_id=f"{schedule_id}-round-001",
                status="OPTED_IN",
            )
        except ValueError as exc:
            assert "superseded schedule" in str(exc)
        else:
            raise AssertionError("a superseded planning round must not accept opt-in")
    finally:
        connection.close()
