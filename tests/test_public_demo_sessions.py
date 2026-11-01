from __future__ import annotations

import asyncio
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from http.cookies import SimpleCookie
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from backend import database, governance, travel
from backend.main import app, initialize_public_demo_storage
from backend.public_demo import (
    PUBLIC_DEMO_MAX_ACTIVE_SESSIONS,
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


def test_public_demo_blocks_ai_and_private_pilot_endpoints(
    tmp_path: Path, monkeypatch
) -> None:
    _configure_demo_storage(tmp_path, monkeypatch)

    with TestClient(app) as client:
        blocked_requests = (
            ("POST", "/api/demand/structure", {"text": "synthetic test note"}),
            ("POST", "/api/demand/drafts", {}),
            ("GET", "/api/demand/drafts", None),
            ("POST", "/api/pilot-imports/provider_capacity/preview", {}),
            ("GET", "/api/feedback/private-id/contact?role=PLANNER", None),
        )
        for method, path, payload in blocked_requests:
            response = client.request(method, path, json=payload)
            assert response.status_code == 404
            assert response.json()["code"] == "DEMO_MODE_RESTRICTED"


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


def test_schedule_creation_rolls_back_plan_when_governance_audit_fails(
    tmp_path: Path, monkeypatch
) -> None:
    app_db, _route_db = _configure_demo_storage(tmp_path, monkeypatch)
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

    with TestClient(app) as client:
        _, token = _session_request(client, None, "GET", "/api/regions")
        assert token
        connection = database.connect(app_db)
        try:
            before = {
                table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in tracked_tables
            }
        finally:
            connection.close()

        def fail_audit(*_args, **_kwargs):
            raise sqlite3.OperationalError("injected governance audit failure")

        monkeypatch.setattr(governance, "record_audit_event", fail_audit)
        response, _ = _session_request(
            client,
            token,
            "POST",
            "/api/schedules",
            json={
                "scenario": "balanced",
                "budget_won": 4_000_000,
                "region_id": "pilot:홍성군 장곡면",
            },
        )

    assert response.status_code == 503
    connection = database.connect(app_db)
    try:
        for table, count in before.items():
            assert connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == count, table
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        connection.close()


@pytest.mark.parametrize(
    ("failure_stage", "table"),
    [
        ("plan body", "schedule_runs"),
        ("scheduled round", "scheduled_rounds"),
        ("route", "routes"),
        ("ownership", "public_demo_plan_owners"),
        ("audit event", "audit_events"),
    ],
)
def test_schedule_creation_rolls_back_after_each_persisted_stage_fails(
    tmp_path: Path, monkeypatch, failure_stage: str, table: str
) -> None:
    app_db, _route_db = _configure_demo_storage(tmp_path, monkeypatch)
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

    with TestClient(app) as client:
        _, token = _session_request(client, None, "GET", "/api/regions")
        assert token
        connection = database.connect(app_db)
        try:
            before = {
                name: connection.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
                for name in tracked_tables
            }
            connection.execute(
                f"CREATE TRIGGER injected_{table}_failure BEFORE INSERT ON {table} "
                "BEGIN SELECT RAISE(ABORT, 'injected plan write failure'); END"
            )
            connection.commit()
        finally:
            connection.close()

        response, _ = _session_request(
            client,
            token,
            "POST",
            "/api/schedules",
            json={
                "scenario": "balanced",
                "budget_won": 4_000_000,
                "region_id": "pilot:홍성군 장곡면",
            },
        )

    assert response.status_code == 503, failure_stage
    connection = database.connect(app_db)
    try:
        for name, count in before.items():
            assert connection.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0] == count, name
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        connection.close()


def test_sqlite_session_lock_does_not_block_health_event_loop(
    tmp_path: Path, monkeypatch
) -> None:
    app_db, _route_db = _configure_demo_storage(tmp_path, monkeypatch)
    initialize_public_demo_storage()
    lock_connection = sqlite3.connect(app_db, timeout=5, check_same_thread=False)
    lock_connection.execute("BEGIN IMMEDIATE")

    def release_lock() -> None:
        try:
            lock_connection.rollback()
            lock_connection.close()
        except sqlite3.Error:
            pass

    release = threading.Timer(0.6, release_lock)
    release.start()

    async def exercise_requests() -> tuple[float, int, int]:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            started = time.perf_counter()
            session_request = asyncio.create_task(client.get("/api/regions"))
            await asyncio.sleep(0)
            health_request = asyncio.create_task(client.get("/health"))
            health = await asyncio.wait_for(health_request, timeout=0.35)
            health_elapsed = time.perf_counter() - started
            regions = await asyncio.wait_for(session_request, timeout=3)
            return health_elapsed, health.status_code, regions.status_code

    try:
        health_elapsed, health_status, regions_status = asyncio.run(exercise_requests())
    finally:
        release.cancel()
        release_lock()

    assert health_status == 200
    assert regions_status == 200
    assert health_elapsed < 0.35


def test_concurrent_new_session_issuance_registers_distinct_tokens(
    tmp_path: Path, monkeypatch
) -> None:
    app_db, _route_db = _configure_demo_storage(tmp_path, monkeypatch)
    store = PublicDemoSessionStore(max_active_sessions=16, issuance_limit=16)
    connection = database.connect(app_db)
    try:
        store.ensure_schema(connection)
        connection.commit()
    finally:
        connection.close()

    barrier = threading.Barrier(8)

    def issue_session() -> tuple[str, str | None]:
        barrier.wait(timeout=5)
        return store.ensure(None)

    with ThreadPoolExecutor(max_workers=8) as pool:
        issued = list(pool.map(lambda _index: issue_session(), range(8)))

    owner_hashes = {owner_hash for owner_hash, _token in issued}
    tokens = {token for _owner_hash, token in issued}
    assert len(owner_hashes) == 8
    assert len(tokens) == 8 and None not in tokens
    assert all(PublicDemoSessionStore._hash(token) == owner_hash for owner_hash, token in issued)

    connection = database.connect(app_db)
    try:
        assert connection.execute("SELECT COUNT(*) FROM public_demo_sessions").fetchone()[0] == 8
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        connection.close()


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


def test_public_demo_health_probes_do_not_consume_or_require_session_capacity(
    tmp_path: Path, monkeypatch
) -> None:
    app_db, _route_db = _configure_demo_storage(tmp_path, monkeypatch)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    now_text = now.isoformat()
    expires_text = (now + timedelta(minutes=30)).isoformat()

    with TestClient(app) as client:
        connection = database.connect(app_db)
        try:
            PublicDemoSessionStore.ensure_schema(connection)
            connection.executemany(
                "INSERT INTO public_demo_sessions("
                "session_hash, created_at, last_seen_at, expires_at) "
                "VALUES (?, ?, ?, ?)",
                [
                    (f"active-session-{index}", now_text, now_text, expires_text)
                    for index in range(PUBLIC_DEMO_MAX_ACTIVE_SESSIONS)
                ],
            )
            connection.commit()
        finally:
            connection.close()

        for _ in range(PUBLIC_DEMO_MAX_ACTIVE_SESSIONS + 44):
            response = client.get("/health")
            assert response.status_code == 200
            assert "set-cookie" not in response.headers

        api_health = client.get("/api/health")
        assert api_health.status_code == 200
        assert "set-cookie" not in api_health.headers

        connection = database.connect(app_db)
        try:
            active_count = connection.execute(
                "SELECT COUNT(*) FROM public_demo_sessions"
            ).fetchone()[0]
        finally:
            connection.close()
        assert active_count == PUBLIC_DEMO_MAX_ACTIVE_SESSIONS

        new_visitor = client.get("/api/regions")
        assert new_visitor.status_code == 503
        assert new_visitor.json()["code"] == "DEMO_SESSION_CAPACITY"

        for path in ("/api/schedules", "/api/schedules/not-owned"):
            blocked_read = client.get(path)
            assert blocked_read.status_code == 503
            assert blocked_read.json()["code"] == "DEMO_SESSION_CAPACITY"


def test_database_state_reset_expires_old_plan_without_exposing_it_to_new_session(
    tmp_path: Path, monkeypatch
) -> None:
    _configure_demo_storage(tmp_path, monkeypatch)

    with TestClient(app) as client:
        _, token = _session_request(client, None, "GET", "/api/regions")
        assert token
        plan, token = _create_plan(client, token)

        reset_db = tmp_path / "public-demo-session-after-reset.sqlite"
        monkeypatch.setattr(database, "database_path", lambda: reset_db)
        initialize_public_demo_storage()

        stale_plan, replacement_token = _session_request(
            client, token, "GET", f"/api/schedules/{plan['schedule_id']}"
        )
        assert stale_plan.status_code == 410
        assert stale_plan.json()["detail"] == "DEMO_SESSION_EXPIRED"
        assert replacement_token and replacement_token != token

        new_history, replacement_token = _session_request(
            client, replacement_token, "GET", "/api/schedules"
        )
        assert new_history.status_code == 200
        assert new_history.json()["plans"] == []
        assert replacement_token


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


def test_fallback_uses_same_private_participation_as_reserve_comparison(
    tmp_path: Path, monkeypatch
) -> None:
    """Both computations must see only the requesting visitor's actual DB overlay."""
    from backend import api_provider

    _configure_demo_storage(tmp_path, monkeypatch)
    captured = []
    original = api_provider._planning_context

    def capture_context(region_id, *, owner_session_hash=None):
        context = original(region_id, owner_session_hash=owner_session_hash)
        captured.append(context[1])
        return context

    monkeypatch.setattr(api_provider, "_planning_context", capture_context)
    # Isolate solver cost while exercising real middleware, storage and context loading.
    monkeypatch.setattr(api_provider.provider_fallback, "fallback_candidates", lambda *a, **k: {})
    monkeypatch.setattr(
        api_provider.provider_fallback, "compare_reserve_policies", lambda *a, **k: {}
    )
    with TestClient(app) as client:
        _, token_a = _session_request(client, None, "GET", "/api/regions")
        _, token_b = _session_request(client, None, "GET", "/api/regions")
        plan, token_a = _create_plan(client, token_a)
        monkeypatch.setattr(
            api_provider.scheduling_module,
            "generate_provider_schedule",
            lambda *a, **k: {"rounds": []},
        )
        # Seed one visitor overlay while preserving the shared provider state.
        connection = database.connect()
        try:
            provider = plan["rounds"][0]["provider_id"]
            round_id = plan["rounds"][0]["service_round_id"]
            connection.execute(
                "INSERT INTO public_demo_provider_participations "
                "(session_hash, provider_id, round_id, status, updated_at) VALUES (?, ?, ?, ?, ?)",
                (
                    PublicDemoSessionStore._hash(token_a),
                    provider,
                    round_id,
                    "DECLINED",
                    "2026-10-31",
                ),
            )
            connection.commit()
        finally:
            connection.close()
        del plan
        base = "/api/regions/pilot:홍성군 장곡면"
        snapshots = []
        for token, method, endpoint in (
            (token_a, "POST", "/fallback-candidates"),
            (token_a, "GET", "/reserve-comparison?budget_won=4000000"),
            (token_b, "POST", "/fallback-candidates"),
            (token_a, "POST", "/fallback-candidates"),
        ):
            response, _ = _session_request(
                client,
                token,
                method,
                base + endpoint,
                **({"json": {"budget_won": 4_000_000}} if method == "POST" else {}),
            )
            assert response.status_code == 200
            snapshots.append(captured[-1])
        assert snapshots[0] == snapshots[1] == snapshots[3]
        assert snapshots[0] != snapshots[2]
