from __future__ import annotations

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from backend import database
from backend.database import (
    connect,
    find_existing_replan_child,
    get_schedule_replan_triggers,
    seed_reference_data,
)
from backend.main import app
from backend.regions import DEFAULT_REGION_ID

ROOT = Path(__file__).resolve().parents[1]


def test_duplicate_migration_is_idempotent(tmp_path: Path) -> None:
    db_file = tmp_path / "migration_test.sqlite"
    conn = connect(db_file)
    try:
        initial_version = conn.execute("PRAGMA user_version").fetchone()[0]
        assert initial_version == database.SCHEMA_VERSION

        # Calling _migrate on an already migrated database should be completely safe and no-op
        database._migrate(conn)
        assert conn.execute("PRAGMA user_version").fetchone()[0] == database.SCHEMA_VERSION
    finally:
        conn.close()


def test_foreign_key_violation_is_strictly_enforced(tmp_path: Path) -> None:
    db_file = tmp_path / "fk_test.sqlite"
    conn = connect(db_file)
    try:
        # Inserting a village_service_area with non-existent region_id must fail
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """INSERT INTO village_service_areas(
                     area_id, region_id, legal_code, name, facility_count,
                     anchor_lat, anchor_lng, provenance
                   ) VALUES (
                     'non-existent-area', 'fake-region-id', '1234567890',
                     'Test Area', 0, 36.0, 127.0, 'TEST'
                   )"""
            )
            conn.commit()
    finally:
        conn.close()


def test_duplicate_plan_version_index_enforcement(tmp_path: Path) -> None:
    db_file = tmp_path / "plan_version_test.sqlite"
    conn = connect(db_file)
    data = json.loads(database.ROOT.joinpath("data", "demo.json").read_text(encoding="utf-8"))
    try:
        seed_reference_data(conn, data)
        # Directly insert schedule_run with same lineage_root_id and plan_version
        conn.execute(
            """INSERT INTO schedule_runs(
                 schedule_id, scenario_key, budget_won, summary_json, provenance,
                 created_at, planning_policy_json, region_id, plan_version,
                 lineage_root_id, change_kind, change_reason
               ) VALUES ('sched-1', 'balanced', 1000000, '{}', 'TEST',
                         '2026-10-02T00:00:00Z', '{}', ?, 1, 'lineage-root-1',
                         'INITIAL', 'INITIAL_PLAN')""",
            (DEFAULT_REGION_ID,),
        )
        conn.commit()

        # Duplicate (lineage_root_id, plan_version) must raise IntegrityError
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """INSERT INTO schedule_runs(
                     schedule_id, scenario_key, budget_won, summary_json, provenance,
                     created_at, planning_policy_json, region_id, plan_version,
                     lineage_root_id, change_kind, change_reason
                   ) VALUES ('sched-2', 'balanced', 1000000, '{}', 'TEST',
                             '2026-10-02T00:00:00Z', '{}', ?, 1, 'lineage-root-1',
                             'PROVIDER_REPLAN', 'DUPLICATE')""",
                (DEFAULT_REGION_ID,),
            )
            conn.commit()
    finally:
        conn.close()


def test_concurrent_connections_do_not_corrupt_schema(tmp_path: Path) -> None:
    db_file = tmp_path / "concurrent_test.sqlite"

    def open_and_check() -> int:
        c = connect(db_file)
        try:
            ver = c.execute("PRAGMA user_version").fetchone()[0]
            return int(ver)
        finally:
            c.close()

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(lambda _: open_and_check(), range(16)))

    assert all(ver == database.SCHEMA_VERSION for ver in results)


def test_replan_idempotency_via_api_and_find_existing_child(tmp_path: Path, monkeypatch) -> None:
    db_file = tmp_path / "replan_idempotency.sqlite"
    monkeypatch.setenv("VILLAGECOVERAGE_APP_DB", str(db_file))
    client = TestClient(app)

    # 1. Create initial schedule
    initial_res = client.post(
        "/api/schedules",
        json={
            "scenario": "balanced",
            "budget_won": 1500000,
            "region_id": DEFAULT_REGION_ID,
        },
    )
    assert initial_res.status_code == 201, initial_res.text
    initial_plan = initial_res.json()
    schedule_id = initial_plan["schedule_id"]
    assert initial_plan["plan_version"] == 1

    # Mark first round as DECLINED
    first_round = initial_plan["rounds"][0]
    provider_id = first_round["provider_id"]
    round_id = first_round["service_round_id"]

    decline_res = client.post(
        f"/api/providers/{provider_id}/rounds/{round_id}/participation",
        json={"status": "DECLINED"},
    )
    assert decline_res.status_code == 200, decline_res.text

    # Verify triggers exist
    conn = connect(db_file)
    try:
        triggers = get_schedule_replan_triggers(conn, schedule_id)
        assert triggers is not None and len(triggers) >= 1

        # Initially, find_existing_replan_child should return None
        existing_before = find_existing_replan_child(
            conn, parent_schedule_id=schedule_id, replan_triggers=triggers
        )
        assert existing_before is None
    finally:
        conn.close()

    # 2. First replan call -> creates plan_version 2
    replan_1 = client.post(f"/api/schedules/{schedule_id}/replan")
    assert replan_1.status_code == 201, replan_1.text
    child_plan_1 = replan_1.json()
    assert child_plan_1["plan_version"] == 2
    assert child_plan_1["parent_schedule_id"] == schedule_id

    # 3. Second replan call with identical state -> must be IDEMPOTENT!
    # Returns the exact same child schedule without creating version 3
    replan_2 = client.post(f"/api/schedules/{schedule_id}/replan")
    assert replan_2.status_code in (200, 201), replan_2.text
    child_plan_2 = replan_2.json()
    assert child_plan_2["schedule_id"] == child_plan_1["schedule_id"]
    assert child_plan_2["plan_version"] == 2

    # Verify directly via find_existing_replan_child
    conn = connect(db_file)
    try:
        existing_after = find_existing_replan_child(
            conn, parent_schedule_id=schedule_id, replan_triggers=triggers
        )
        assert existing_after is not None
        assert existing_after["schedule_id"] == child_plan_1["schedule_id"]

        # Ensure no spurious version 3 was added
        total_runs = conn.execute(
            "SELECT COUNT(*) FROM schedule_runs WHERE lineage_root_id=?",
            (schedule_id,),
        ).fetchone()[0]
        assert total_runs == 2
    finally:
        conn.close()


def test_duplicate_participation_direct_insert_fails(tmp_path: Path) -> None:
    db_file = tmp_path / "part_test.sqlite"
    conn = connect(db_file)
    data = json.loads(database.ROOT.joinpath("data", "demo.json").read_text(encoding="utf-8"))
    try:
        database.seed_reference_data(conn, data)
        database.seed_provider_data(conn, data)
        row = conn.execute("SELECT provider_id, round_id FROM service_rounds LIMIT 1").fetchone()
        assert row is not None
        pid, rid = row["provider_id"], row["round_id"]

        # A participation record already exists from seed_provider_data.
        # Direct INSERT of duplicate (provider_id, round_id) must fail with IntegrityError!
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """INSERT INTO provider_participations(
                     participation_id, provider_id, round_id, status, updated_at, provenance
                   ) VALUES ('p1', ?, ?, 'OPTED_IN', '2026-10-02T00:00:00Z', 'TEST')""",
                (pid, rid),
            )
            conn.commit()
    finally:
        conn.close()


def test_participation_update_is_idempotent(tmp_path: Path) -> None:
    db_file = tmp_path / "part_update_test.sqlite"
    conn = connect(db_file)
    data = json.loads(database.ROOT.joinpath("data", "demo.json").read_text(encoding="utf-8"))
    try:
        database.seed_reference_data(conn, data)
        database.seed_provider_data(conn, data)
        row = conn.execute("SELECT provider_id, round_id FROM service_rounds LIMIT 1").fetchone()
        assert row is not None
        pid, rid = row["provider_id"], row["round_id"]

        # First decline
        ok1 = database.update_participation(conn, provider_id=pid, round_id=rid, status="DECLINED")
        assert ok1 is True
        conn.commit()

        # Second decline with identical parameters
        ok2 = database.update_participation(conn, provider_id=pid, round_id=rid, status="DECLINED")
        assert ok2 is True
        conn.commit()

        count = conn.execute(
            "SELECT COUNT(*) FROM provider_participations WHERE provider_id=? AND round_id=?",
            (pid, rid),
        ).fetchone()[0]
        assert count == 1
    finally:
        conn.close()
