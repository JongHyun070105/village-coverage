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
from backend.regions import DEFAULT_REGION_ID

ROOT = Path(__file__).resolve().parents[1]


def test_app_database_migrates_once_and_contains_traceable_v9_tables(tmp_path) -> None:
    path = tmp_path / "app.sqlite"
    connection = connect(path)
    try:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 9
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
            "routes",
            "route_stops",
            "demand_forecasts",
            "provider_date_availability",
            "import_batches",
            "import_rows",
            "demand_structuring_drafts",
        } <= tables
        survey_columns = {row[1] for row in connection.execute("PRAGMA table_info(surveys)")}
        assert "structured_data_json" in survey_columns
        columns = {row[1] for row in connection.execute("PRAGMA table_info(schedule_runs)")}
        assert "planning_policy_json" in columns
        assert "region_id" in columns
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
    assert versions == [9] * 5


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
        assert upgraded.execute("PRAGMA user_version").fetchone()[0] == 9
        assert upgraded.execute("SELECT region_id FROM regions").fetchone()[0] == "existing-v1"
        assert upgraded.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0] == 9
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
        assert upgraded.execute("PRAGMA user_version").fetchone()[0] == 9
        assert upgraded.execute("SELECT region_id FROM regions").fetchone()[0] == "existing"
        assert upgraded.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0] == 9
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
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 9
        assert connection.execute("SELECT count(*) FROM schema_migrations").fetchone()[0] == 9
    finally:
        connection.close()


def test_reference_seed_keeps_public_snapshots_and_excluded_service_policy(tmp_path) -> None:
    data = json.loads((ROOT / "data" / "demo.json").read_text(encoding="utf-8"))
    connection = connect(tmp_path / "app.sqlite")
    try:
        seed_reference_data(connection, data)
        expected_area_count = len(data["areas"])
        assert (
            connection.execute("SELECT count(*) FROM village_service_areas").fetchone()[0]
            == expected_area_count
        )
        assert (
            connection.execute("SELECT count(*) FROM population_snapshots").fetchone()[0]
            == expected_area_count
        )
        assert (
            connection.execute("SELECT count(*) FROM household_snapshots").fetchone()[0]
            == expected_area_count
        )
        service = connection.execute(
            "SELECT policy_status FROM service_types WHERE service_type_id='mobility_support'"
        ).fetchone()
        assert service[0] == "EXCLUDED"
        registry = {
            row["service_type_id"]: row["policy_status"]
            for row in database.list_service_types(connection)
        }
        assert registry == {
            "laundry": "ALLOWED",
            "daily_necessities": "ALLOWED",
            "home_repair": "ALLOWED",
            "medical_service": "REGULATED",
            "legal_service": "REGULATED",
            "mobility_support": "EXCLUDED",
        }
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
        default_areas = [area for area in data["areas"] if area["region_id"] == DEFAULT_REGION_ID]
        assert provider is not None
        assert provider["name"] == "행복세탁"
        assert provider["supported_services"] == ["laundry"]
        assert provider["base_area_id"] == default_areas[0]["id"]
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
        assert len(provider["forecast"]["months"]) == 3
        assert all(month["expected_rounds_mid"] is None for month in provider["forecast"]["months"])
        forecast_rows = connection.execute(
            """SELECT target_month, evidence_status, expected_rounds_low,
                      expected_rounds_mid, expected_rounds_high, input_fingerprint
               FROM demand_forecasts ORDER BY target_month"""
        ).fetchall()
        assert len(forecast_rows) == 3
        assert all(row["evidence_status"] == "DATA_INSUFFICIENT" for row in forecast_rows)
        assert all(row["expected_rounds_low"] is None for row in forecast_rows)
        assert all(len(row["input_fingerprint"]) == 64 for row in forecast_rows)
        round_id = provider["upcoming_rounds"][0]["round_id"]
        assert update_participation(
            connection,
            provider_id="sim-provider-1",
            round_id=round_id,
            status="OPTED_IN",
        )
        updated = provider_detail(connection, "sim-provider-1")
        assert updated["upcoming_rounds"][0]["status"] == "OPTED_IN"
        assert connection.execute("SELECT count(*) FROM demand_forecasts").fetchone()[0] == 3
    finally:
        connection.close()


def test_sufficient_provider_forecast_is_returned_and_persisted(tmp_path) -> None:
    data = json.loads((ROOT / "data" / "demo.json").read_text(encoding="utf-8"))
    connection = connect(tmp_path / "forecast.sqlite")
    try:
        seed_reference_data(connection, data)
        seed_provider_data(connection, data)
        region_id = DEFAULT_REGION_ID
        area_ids = [
            row[0]
            for row in connection.execute(
                "SELECT area_id FROM village_service_areas WHERE region_id=? ORDER BY area_id",
                (region_id,),
            ).fetchall()
        ]
        panel_size = max(3, (len(area_ids) * 6 + 9) // 10)
        assert panel_size <= len(area_ids)
        today = date.today()
        month_start = date(today.year, today.month, 1)
        for month_offset in range(6, 0, -1):
            absolute_month = month_start.year * 12 + month_start.month - 1 - month_offset
            survey_date = date(absolute_month // 12, absolute_month % 12 + 1, 15).isoformat()
            for area_index, area_id in enumerate(area_ids[:panel_size]):
                insert_survey(
                    connection,
                    area_id=area_id,
                    survey_type="phone" if area_index % 2 == 0 else "field",
                    survey_date=survey_date,
                    service_type="laundry",
                    frequency_per_month=1 + area_index % 3,
                    preferred_period=None,
                    preferred_days=[],
                    constraints=[],
                    free_text_note="합성 forecast 테스트 자료",
                    source_text_was_redacted=False,
                )

        provider = provider_detail(connection, "sim-provider-1")

        assert provider is not None
        assert provider["forecast"]["status"] == "AVAILABLE"
        assert provider["forecast"]["survey_required"] is False
        assert len(provider["forecast"]["months"]) == 3
        assert all(
            month["evidence_status"] == "SUFFICIENT_OBSERVED"
            and month["expected_rounds_low"] is not None
            and month["expected_rounds_mid"] is not None
            and month["expected_rounds_high"] is not None
            for month in provider["forecast"]["months"]
        )
        persisted = connection.execute(
            "SELECT count(*) FROM demand_forecasts WHERE evidence_status='SUFFICIENT_OBSERVED'"
        ).fetchone()[0]
        assert persisted == 3
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
            "route_sequence": 1,
            "route_type": "MULTI_STOP",
        }
        schedule_id = save_schedule_plan(
            connection,
            scenario="efficiency",
            budget_won=1_000_000,
            region_id=data.get("default_region_id", "pilot:홍성군 장곡면"),
            plan={
                "served_units": 2,
                "total_cost_won": 535000,
                "travel_source": "Kakao road cache",
                "rounds": [round_item],
                "routes": [
                    {
                        "provider_id": "sim-provider-1",
                        "scheduled_date": round_date,
                        "route_type": "MULTI_STOP",
                        "base_area_id": data["areas"][0]["id"],
                        "distance_m": 10000,
                        "duration_s": 1200,
                        "cost_won": 25000,
                        "old_hub_round_trip_distance_m": 20000,
                        "old_hub_round_trip_duration_s": 2400,
                        "old_hub_round_trip_cost_won": 50000,
                        "distance_savings_m": 10000,
                        "duration_savings": 1200,
                        "cost_savings_won": 25000,
                        "provenance": "OR-TOOLS ROUTING; KAKAO ROAD CACHE",
                        "stops": [
                            {
                                "area_id": data["areas"][0]["id"],
                                "incoming_from_area_id": data["areas"][0]["id"],
                                "outgoing_to_area_id": data["areas"][0]["id"],
                                "sequence": 1,
                                "service_start_time": "09:10",
                                "service_end_time": "10:10",
                                "travel_before_s": 600,
                                "travel_after_s": 600,
                                "travel_before_distance_m": 5000,
                                "travel_after_distance_m": 5000,
                            }
                        ],
                    }
                ],
            },
        )
        saved = get_schedule_plan(connection, schedule_id)
        assert saved is not None
        assert saved["scenario_key"] == "efficiency"
        assert saved["region_id"] == data.get("default_region_id", "pilot:홍성군 장곡면")
        assert saved["summary"]["served_units"] == 2
        assert saved["planning_policy"]["minimum_services_per_area"] == 1
        assert "laundry" in saved["planning_policy"]["allowed_services"]
        assert saved["rounds"][0]["service_units"] == 2
        assert saved["rounds"][0]["total_cost_won"] == 535000
        assert saved["rounds"][0]["participation_status"] == "AVAILABLE"
        assert saved["rounds"][0]["provenance"] == "OPTIMIZATION RESULT; SIMULATED FOR PRE-R&D"
        assert saved["rounds"][0]["route_type"] == "MULTI_STOP"
        assert saved["rounds"][0]["route_sequence"] == 1
        assert saved["rounds"][0]["route_id"] == saved["routes"][0]["route_id"]
        assert saved["routes"][0]["distance_savings_m"] == 10000
        assert saved["routes"][0]["stops"][0]["area_name"] == data["areas"][0]["name"]
        assert saved["routes"][0]["stops"][0]["incoming_from_area_name"] == data["areas"][0]["name"]
        assert saved["routes"][0]["stops"][0]["incoming_time_s"] == 600

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
