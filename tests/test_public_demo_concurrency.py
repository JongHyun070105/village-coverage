from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from http.cookies import SimpleCookie
from pathlib import Path
from threading import Barrier

from fastapi.testclient import TestClient

from backend import database, travel
from backend.main import app
from backend.public_demo import PUBLIC_DEMO_SESSION_COOKIE


def _new_public_visitor_plan(tmp_path: Path, monkeypatch) -> tuple[str, dict[str, object]]:
    monkeypatch.setenv("VILLAGE_COVERAGE_PUBLIC_DEMO", "true")
    monkeypatch.setenv("PUBLIC_DEMO_COOKIE_SECURE", "false")
    app_db = tmp_path / "concurrent-public-demo.sqlite"
    route_db = tmp_path / "concurrent-public-demo-routes.sqlite"
    monkeypatch.setattr(database, "database_path", lambda: app_db)
    monkeypatch.setattr(travel, "route_database_path", lambda: route_db)
    monkeypatch.setattr("backend.main.route_database_path", lambda: route_db)

    with TestClient(app) as client:
        issued = client.get("/api/regions")
        assert issued.status_code == 200
        cookie = SimpleCookie()
        cookie.load(issued.headers["set-cookie"])
        token = cookie[PUBLIC_DEMO_SESSION_COOKIE].value
        created = client.post(
            "/api/schedules",
            json={
                "scenario": "balanced",
                "budget_won": 4_000_000,
                "region_id": "pilot:홍성군 장곡면",
            },
        )
        assert created.status_code == 201, created.text
        return token, created.json()


def _decline_round(token: str, plan: dict[str, object]) -> None:
    round_item = plan["rounds"][0]
    response = TestClient(app).post(
        f"/api/providers/{round_item['provider_id']}/rounds/"
        f"{round_item['service_round_id']}/participation",
        headers={"Cookie": f"{PUBLIC_DEMO_SESSION_COOKIE}={token}"},
        json={"status": "DECLINED", "expected_status": "AVAILABLE"},
    )
    assert response.status_code == 200, response.text


def _parallel_request(
    barrier: Barrier,
    token: str,
    method: str,
    path: str,
    body: dict[str, object],
) -> tuple[int, dict[str, object]]:
    barrier.wait(timeout=10)
    response = TestClient(app).request(
        method,
        path,
        headers={"Cookie": f"{PUBLIC_DEMO_SESSION_COOKIE}={token}"},
        json=body,
    )
    return response.status_code, response.json()


def test_concurrent_duplicate_replans_return_the_same_child(
    tmp_path: Path, monkeypatch
) -> None:
    token, plan = _new_public_visitor_plan(tmp_path, monkeypatch)
    _decline_round(token, plan)
    schedule_id = str(plan["schedule_id"])
    barrier = Barrier(2)
    args = (
        barrier,
        token,
        "POST",
        f"/api/schedules/{schedule_id}/replan",
        {"expected_plan_version": plan["plan_version"]},
    )

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _index: _parallel_request(*args), range(2)))

    assert [status for status, _body in responses] == [201, 201]
    child_ids = {str(body["schedule_id"]) for _status, body in responses}
    assert len(child_ids) == 1


def test_failed_replan_rolls_back_child_and_can_be_retried(
    tmp_path: Path, monkeypatch
) -> None:
    token, plan = _new_public_visitor_plan(tmp_path, monkeypatch)
    _decline_round(token, plan)
    schedule_id = str(plan["schedule_id"])
    connection = database.connect()
    try:
        tracked_tables = (
            "schedule_runs",
            "scheduled_rounds",
            "service_rounds",
            "provider_participations",
            "routes",
            "route_stops",
            "public_demo_plan_owners",
            "audit_events",
        )
        before = {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in tracked_tables
        }
        connection.execute(
            "CREATE TRIGGER fail_replan_round BEFORE INSERT ON scheduled_rounds "
            "BEGIN SELECT RAISE(ABORT, 'injected replan write failure'); END"
        )
        connection.commit()
    finally:
        connection.close()

    response = TestClient(app).post(
        f"/api/schedules/{schedule_id}/replan",
        headers={"Cookie": f"{PUBLIC_DEMO_SESSION_COOKIE}={token}"},
        json={"expected_plan_version": plan["plan_version"]},
    )
    assert response.status_code == 503, response.text

    connection = database.connect()
    try:
        for table, count in before.items():
            assert connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == count
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        connection.execute("DROP TRIGGER fail_replan_round")
        connection.commit()
    finally:
        connection.close()

    retried = TestClient(app).post(
        f"/api/schedules/{schedule_id}/replan",
        headers={"Cookie": f"{PUBLIC_DEMO_SESSION_COOKIE}={token}"},
        json={"expected_plan_version": plan["plan_version"]},
    )
    assert retried.status_code == 201, retried.text
    assert retried.json()["parent_schedule_id"] == schedule_id
    connection = database.connect()
    try:
        assert connection.execute("SELECT COUNT(*) FROM schedule_runs").fetchone()[0] == before[
            "schedule_runs"
        ] + 1
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        connection.close()


def test_approval_and_replan_race_has_one_valid_winner(
    tmp_path: Path, monkeypatch
) -> None:
    token, plan = _new_public_visitor_plan(tmp_path, monkeypatch)
    _decline_round(token, plan)
    schedule_id = str(plan["schedule_id"])
    submitted = TestClient(app).post(
        f"/api/schedules/{schedule_id}/approval",
        headers={"Cookie": f"{PUBLIC_DEMO_SESSION_COOKIE}={token}"},
        json={"action": "submit", "role": "PLANNER"},
    )
    assert submitted.status_code == 200, submitted.text

    barrier = Barrier(2)
    requests = [
        (
            barrier,
            token,
            "POST",
            f"/api/schedules/{schedule_id}/approval",
            {"action": "approve", "role": "REVIEWER"},
        ),
        (
            barrier,
            token,
            "POST",
            f"/api/schedules/{schedule_id}/replan",
            {"expected_plan_version": plan["plan_version"]},
        ),
    ]
    with ThreadPoolExecutor(max_workers=2) as pool:
        approval_result, replan_result = list(
            pool.map(lambda request: _parallel_request(*request), requests)
        )

    assert (approval_result[0], replan_result[0]) in {(200, 409), (409, 201)}
    current = TestClient(app).get(
        f"/api/schedules/{schedule_id}",
        headers={"Cookie": f"{PUBLIC_DEMO_SESSION_COOKIE}={token}"},
    )
    assert current.status_code == 200
    if approval_result[0] == 200:
        assert current.json()["approval_status"] == "APPROVED"
