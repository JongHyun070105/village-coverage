from __future__ import annotations

from http.cookies import SimpleCookie
from pathlib import Path

from fastapi.testclient import TestClient

from backend import database, travel
from backend.main import app
from backend.public_demo import (
    PUBLIC_DEMO_SESSION_COOKIE,
    PublicDemoRateLimiter,
    PublicDemoSessionStore,
    SessionCapacityError,
    SolverCapacityGate,
)


def _session_request(
    client: TestClient,
    token: str | None,
    method: str,
    path: str,
    **kwargs,
) -> tuple[object, str | None]:
    client.cookies.clear()
    headers = dict(kwargs.pop("headers", {}))
    if token:
        headers["Cookie"] = f"{PUBLIC_DEMO_SESSION_COOKIE}={token}"
    response = client.request(method, path, headers=headers, **kwargs)
    cookie_header = response.headers.get("set-cookie")
    if cookie_header:
        cookie = SimpleCookie()
        cookie.load(cookie_header)
        token = cookie[PUBLIC_DEMO_SESSION_COOKIE].value
    client.cookies.clear()
    return response, token


def _configure_demo_storage(tmp_path: Path, monkeypatch) -> tuple[Path, Path]:
    monkeypatch.setenv("VILLAGE_COVERAGE_PUBLIC_DEMO", "true")
    monkeypatch.setenv("PUBLIC_DEMO_COOKIE_SECURE", "false")
    app_db = tmp_path / "public-demo-session.sqlite"
    route_db = tmp_path / "public-demo-session-routes.sqlite"
    monkeypatch.setattr(database, "database_path", lambda: app_db)
    monkeypatch.setattr(travel, "route_database_path", lambda: route_db)
    monkeypatch.setattr("backend.main.route_database_path", lambda: route_db)
    return app_db, route_db


def _create_plan(client: TestClient, token: str, *, scenario: str = "balanced"):
    response, token = _session_request(
        client,
        token,
        "POST",
        "/api/schedules",
        json={
            "scenario": scenario,
            "budget_won": 4_000_000,
            "region_id": "pilot:홍성군 장곡면",
        },
    )
    assert response.status_code == 201, response.text
    assert token is not None
    return response.json(), token


def test_public_demo_visitors_cannot_read_or_change_each_others_plans(
    tmp_path: Path, monkeypatch
) -> None:
    _configure_demo_storage(tmp_path, monkeypatch)

    with TestClient(app) as client:
        response_a, token_a = _session_request(client, None, "GET", "/api/regions")
        response_b, token_b = _session_request(client, None, "GET", "/api/regions")
        assert response_a.status_code == response_b.status_code == 200
        assert token_a and token_b and token_a != token_b
        cookie_header = response_a.headers["set-cookie"]
        assert "HttpOnly" in cookie_header and "SameSite=Lax" in cookie_header
        assert "Path=/api" in cookie_header

        plan_a, token_a = _create_plan(client, token_a)
        plan_b, token_b = _create_plan(client, token_b)
        plan_a_id = plan_a["schedule_id"]
        plan_b_id = plan_b["schedule_id"]
        assert plan_a["rounds"]
        assert plan_b["rounds"]

        history_a, token_a = _session_request(client, token_a, "GET", "/api/schedules")
        history_b, token_b = _session_request(client, token_b, "GET", "/api/schedules")
        assert [item["schedule_id"] for item in history_a.json()["plans"]] == [plan_a_id]
        assert [item["schedule_id"] for item in history_b.json()["plans"]] == [plan_b_id]

        foreign_plan_routes = [
            ("GET", f"/api/schedules/{plan_a_id}"),
            ("GET", f"/api/schedules/{plan_a_id}/explanations"),
            ("GET", f"/api/schedules/{plan_a_id}/export.csv"),
            ("GET", f"/api/schedules/{plan_a_id}/export/budget.csv"),
            ("GET", f"/api/schedules/{plan_a_id}/export/unmet.csv"),
            ("GET", f"/api/schedules/{plan_a_id}/export/summary.pdf"),
            ("GET", f"/api/schedules/{plan_a_id}/decision-memo"),
            ("GET", f"/api/schedules/{plan_a_id}/decision-memo.html"),
            ("GET", f"/api/schedules/{plan_a_id}/decision-memo.pdf"),
            ("POST", f"/api/schedules/{plan_a_id}/replan"),
            (
                "POST",
                f"/api/schedules/{plan_a_id}/approval",
            ),
            ("POST", f"/api/schedules/{plan_a_id}/cost-model-v3"),
        ]
        for method, path in foreign_plan_routes:
            body = (
                {"action": "submit", "role": "PLANNER"}
                if path.endswith("/approval")
                else {}
            )
            response, token_b = _session_request(
                client, token_b, method, path, json=body if method == "POST" else None
            )
            assert response.status_code == 404, (method, path, response.text)

        round_a = plan_a["rounds"][0]
        foreign_decline, token_b = _session_request(
            client,
            token_b,
            "POST",
            f"/api/providers/{round_a['provider_id']}/rounds/{round_a['service_round_id']}/participation",
            json={"status": "DECLINED"},
        )
        assert foreign_decline.status_code == 404

        decline, token_a = _session_request(
            client,
            token_a,
            "POST",
            f"/api/providers/{round_a['provider_id']}/rounds/{round_a['service_round_id']}/participation",
            json={"status": "DECLINED", "expected_status": "AVAILABLE"},
        )
        assert decline.status_code == 200, decline.text
        connection = database.connect()
        try:
            shared_status = connection.execute(
                "SELECT status FROM provider_participations WHERE provider_id=? AND round_id=?",
                (round_a["provider_id"], round_a["service_round_id"]),
            ).fetchone()
            session_status = connection.execute(
                "SELECT status FROM public_demo_provider_participations "
                "WHERE session_hash=? AND provider_id=? AND round_id=?",
                (
                    PublicDemoSessionStore._hash(token_a),
                    round_a["provider_id"],
                    round_a["service_round_id"],
                ),
            ).fetchone()
            assert shared_status is not None and shared_status["status"] != "DECLINED"
            assert session_status is not None and session_status["status"] == "DECLINED"
        finally:
            connection.close()

        plan_b_detail, token_b = _session_request(
            client, token_b, "GET", f"/api/schedules/{plan_b_id}"
        )
        assert all(
            row["participation_status"] != "DECLINED"
            for row in plan_b_detail.json()["rounds"]
        )
        history_b, token_b = _session_request(client, token_b, "GET", "/api/schedules")
        assert history_b.json()["plans"][0]["replan_available"] is False

        replan, token_a = _session_request(
            client,
            token_a,
            "POST",
            f"/api/schedules/{plan_a_id}/replan",
            json={"expected_plan_version": plan_a["plan_version"]},
        )
        assert replan.status_code == 201, replan.text
        assert replan.json()["schedule_id"] != plan_a_id
        duplicate_replan, token_a = _session_request(
            client,
            token_a,
            "POST",
            f"/api/schedules/{plan_a_id}/replan",
            json={"expected_plan_version": plan_a["plan_version"]},
        )
        assert duplicate_replan.status_code == 201
        assert duplicate_replan.json()["schedule_id"] == replan.json()["schedule_id"]

        foreign_compare, token_b = _session_request(
            client,
            token_b,
            "GET",
            f"/api/schedules/{plan_b_id}/decision-memo?compare_with={plan_a_id}",
        )
        assert foreign_compare.status_code == 404

        submit, token_b = _session_request(
            client,
            token_b,
            "POST",
            f"/api/schedules/{plan_b_id}/approval",
            json={"action": "submit", "role": "PLANNER", "expected_plan_version": 1},
        )
        assert submit.status_code == 200, submit.text
        approve, token_b = _session_request(
            client,
            token_b,
            "POST",
            f"/api/schedules/{plan_b_id}/approval",
            json={"action": "approve", "role": "REVIEWER", "expected_plan_version": 1},
        )
        assert approve.status_code == 200, approve.text
        approved_replan, token_b = _session_request(
            client,
            token_b,
            "POST",
            f"/api/schedules/{plan_b_id}/replan",
            json={"expected_plan_version": 1},
        )
        assert approved_replan.status_code == 409
        foreign_approved, token_a = _session_request(
            client, token_a, "GET", f"/api/schedules/{plan_b_id}"
        )
        assert foreign_approved.status_code == 404

        history_a, token_a = _session_request(client, token_a, "GET", "/api/schedules")
        history_b, token_b = _session_request(client, token_b, "GET", "/api/schedules")
        assert all(item["schedule_id"] != plan_b_id for item in history_a.json()["plans"])
        assert all(item["schedule_id"] != plan_a_id for item in history_b.json()["plans"])


def test_public_demo_session_tampering_expiry_and_cleanup(tmp_path: Path, monkeypatch) -> None:
    app_db, _route_db = _configure_demo_storage(tmp_path, monkeypatch)
    with TestClient(app) as client:
        _, token_a = _session_request(client, None, "GET", "/api/regions")
        _, token_b = _session_request(client, None, "GET", "/api/regions")
        assert token_a and token_b
        plan, token_a = _create_plan(client, token_a)
        altered = token_a[:-1] + ("A" if token_a[-1] != "A" else "B")
        tampered, replacement = _session_request(
            client, altered, "GET", f"/api/schedules/{plan['schedule_id']}"
        )
        assert tampered.status_code == 410
        assert replacement and replacement != altered

        connection = database.connect(app_db)
        try:
            owner_hash = PublicDemoSessionStore._hash(token_a)
            connection.execute(
                "UPDATE public_demo_sessions SET expires_at='2000-01-01T00:00:00+00:00' "
                "WHERE session_hash=?",
                (owner_hash,),
            )
            connection.commit()
        finally:
            connection.close()

        expired, token_after_expiry = _session_request(
            client, token_a, "GET", f"/api/schedules/{plan['schedule_id']}"
        )
        assert expired.status_code == 410
        assert token_after_expiry and token_after_expiry != token_a
        connection = database.connect(app_db)
        try:
            assert connection.execute(
                "SELECT 1 FROM schedule_runs WHERE schedule_id=?", (plan["schedule_id"],)
            ).fetchone() is None
            assert connection.execute(
                "SELECT 1 FROM public_demo_plan_owners WHERE schedule_id=?",
                (plan["schedule_id"],),
            ).fetchone() is None
            assert connection.execute(
                "SELECT 1 FROM public_demo_provider_participations WHERE session_hash=?",
                (owner_hash,),
            ).fetchone() is None
        finally:
            connection.close()


def test_public_demo_session_and_solver_caps_are_bounded(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VILLAGE_COVERAGE_PUBLIC_DEMO", "true")
    monkeypatch.setenv("PUBLIC_DEMO_COOKIE_SECURE", "false")
    monkeypatch.setattr(database, "database_path", lambda: tmp_path / "session-cap.sqlite")
    store = PublicDemoSessionStore(max_active_sessions=1, issuance_limit=10)
    owner_hash, token = store.ensure(None)
    assert token
    assert store.ensure(token) == (owner_hash, None)
    try:
        store.ensure(None)
    except SessionCapacityError:
        pass
    else:
        raise AssertionError("session capacity must reject excess sessions")


def test_public_demo_rate_limit_is_per_session_with_a_global_ceiling(
    tmp_path: Path, monkeypatch
) -> None:
    _configure_demo_storage(tmp_path, monkeypatch)
    with TestClient(app) as client:
        _, token_a = _session_request(client, None, "GET", "/api/regions")
        _, token_b = _session_request(client, None, "GET", "/api/regions")
        assert token_a and token_b

        path = "/api/schedules/not-owned/approval"
        for _ in range(20):
            response, token_a = _session_request(
                client,
                token_a,
                "POST",
                path,
                json={"action": "submit", "role": "PLANNER"},
            )
            assert response.status_code == 404

        throttled, token_a = _session_request(
            client,
            token_a,
            "POST",
            path,
            json={"action": "submit", "role": "PLANNER"},
        )
        assert throttled.status_code == 429
        assert int(throttled.headers["retry-after"]) > 0

        other_visitor, token_b = _session_request(
            client,
            token_b,
            "POST",
            path,
            json={"action": "submit", "role": "PLANNER"},
        )
        assert other_visitor.status_code == 404

    limiter = PublicDemoRateLimiter(limit=1, window_seconds=60)
    assert limiter.retry_after("visitor-a", now=10) is None
    assert limiter.retry_after("visitor-a", now=11) == 59
    assert limiter.retry_after("visitor-b", now=11) is None

    async def check_solver_gate() -> None:
        gate = SolverCapacityGate(active_limit=1, waiting_limit=0)
        assert await gate.acquire()
        assert not await gate.acquire()
        await gate.release()

    import asyncio

    asyncio.run(check_solver_gate())
