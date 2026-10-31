"""Synthetic-time v18 admission tests; never send load to public services."""

from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend import public_demo as demo


def admit(global_budget, sessions, visitor, now=100):
    return demo.PublicDemoRateLimiter.admit(
        ((global_budget, "global"), (sessions, visitor)), now=now
    )


def test_independent_visitors_and_exact_global_70_with_retry_after():
    shared = demo.PublicDemoRateLimiter(limit=70)
    visitors = demo.PublicDemoRateLimiter(limit=20)
    for visitor in ["a", "b", "c"]:
        for _ in range(20):
            assert admit(shared, visitors, visitor) is None
        assert admit(shared, visitors, visitor) == 60
    for _ in range(10):
        assert admit(shared, visitors, "d") is None
    assert admit(shared, visitors, "new", now=101) == 59
    assert "new" not in visitors._requests or not visitors._requests["new"]
    assert len(visitors._requests["d"]) == 10
    assert admit(shared, visitors, "new", now=160) is None


def test_global_rejection_does_not_consume_session_or_reverse():
    shared = demo.PublicDemoRateLimiter(limit=1)
    visitors = demo.PublicDemoRateLimiter(limit=1)
    assert admit(shared, visitors, "a") is None
    assert admit(shared, visitors, "b", now=101) == 59
    assert visitors.retry_after("b", now=101) is None
    shared = demo.PublicDemoRateLimiter(limit=2)
    visitors = demo.PublicDemoRateLimiter(limit=1)
    assert admit(shared, visitors, "a") is None
    assert admit(shared, visitors, "a") == 60
    assert admit(shared, visitors, "b") is None


def test_concurrent_admission_never_overspends():
    shared = demo.PublicDemoRateLimiter(limit=70)
    visitors = demo.PublicDemoRateLimiter(limit=20)
    with ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(lambda n: admit(shared, visitors, str(n % 4)), range(200)))
    assert results.count(None) == 70
    assert len(shared._requests["global"]) == 70
    assert max(map(len, visitors._requests.values())) <= 20


def test_limiter_reclaims_idle_keys_and_rejects_new_keys_at_bound():
    limiter = demo.PublicDemoRateLimiter(limit=1)
    for n in range(1024):
        assert limiter.retry_after(str(n), now=100) is None
    assert limiter.retry_after("overflow", now=101) == 60
    assert len(limiter._requests) == 1024
    assert limiter.retry_after("fresh", now=160) is None
    assert set(limiter._requests) == {"fresh"}


def test_cost_inventory_is_explicit_and_covers_every_allowed_route():
    assert demo.operation_cost("GET", "/api/regions") == "A"
    assert demo.operation_cost("GET", "/api/health") == "A"
    assert demo.operation_cost("GET", "/api/schedules") == "B"
    assert demo.operation_cost("GET", "/api/regions/comparison") == "C"
    assert demo.operation_cost("GET", "/api/schedules/a/decision-memo.pdf") == "C"
    assert demo.operation_cost("POST", "/api/schedules/a/approval") == "D"
    assert demo.operation_cost("GET", "/api/private") is None
    import re

    from backend.main import app

    for path, methods in app.openapi()["paths"].items():
        concrete = re.sub(r"\{[^}]+\}", "demo-id", path)
        for method in methods:
            if demo.classify(method, concrete) != demo.PUBLIC_DEMO_BLOCKED:
                assert demo.operation_cost(method.upper(), concrete) in {"A", "B", "C", "D"}


class RegisteredSessions:
    idle_seconds = 1800

    def ensure(self, token):
        return (token or "visitor-a"), None


def test_global_full_does_not_block_regions_and_xff_cannot_rotate_session(monkeypatch):
    monkeypatch.setattr(demo, "enabled", lambda: True)
    app = FastAPI()
    app.add_middleware(
        demo.PublicDemoBoundaryMiddleware,
        limiter=demo.PublicDemoRateLimiter(limit=70),
        session_store=RegisteredSessions(),
    )

    @app.get("/api/regions")
    @app.get("/api/overview")
    def data():
        return {"ok": True}

    with TestClient(app) as client:
        for visitor in ["a", "b", "c", "d"]:
            for _ in range(20 if visitor != "d" else 10):
                assert (
                    client.get(
                        "/api/overview", headers={"Cookie": f"vc_demo_session={visitor}"}
                    ).status_code
                    == 200
                )
        limited = client.get("/api/overview", headers={"Cookie": "vc_demo_session=new"})
        assert limited.status_code == 429
        assert limited.json()["code"] == "DEMO_RATE_LIMITED"
        assert 1 <= int(limited.headers["retry-after"]) <= 60
        assert client.get("/api/regions").status_code == 200

    other = FastAPI()
    other.add_middleware(demo.PublicDemoBoundaryMiddleware, session_store=RegisteredSessions())
    other.add_api_route("/api/overview", data)
    with TestClient(other) as client:
        for n in range(20):
            assert (
                client.get("/api/overview", headers={"X-Forwarded-For": f"192.0.2.{n}"}).status_code
                == 200
            )
        assert (
            client.get("/api/overview", headers={"X-Forwarded-For": "2001:db8::1"}).status_code
            == 429
        )
        assert (
            client.get(
                "/api/overview",
                headers={"Cookie": "vc_demo_session=visitor-b", "X-Forwarded-For": "2001:db8::1"},
            ).status_code
            == 200
        )


def test_capacity_rejection_does_not_consume_admission(monkeypatch):
    monkeypatch.setattr(demo, "enabled", lambda: True)
    shared = demo.PublicDemoRateLimiter(limit=70)
    sessions = demo.PublicDemoRateLimiter(limit=20)
    app = FastAPI()
    app.add_middleware(
        demo.PublicDemoBoundaryMiddleware,
        limiter=shared,
        session_limiter=sessions,
        session_store=RegisteredSessions(),
        solver_gate=demo.SolverCapacityGate(active_limit=0, waiting_limit=0),
    )
    app.add_api_route("/api/overview", lambda: {"unreachable": True})
    with TestClient(app) as client:
        response = client.get("/api/overview")
        assert response.status_code == 503
        assert response.json()["code"] == "DEMO_SOLVER_CAPACITY"
    assert not shared._requests
    assert not sessions._requests


def test_regions_can_hit_session_issuance_429_before_compute(monkeypatch, tmp_path):
    from backend import database

    monkeypatch.setattr(demo, "enabled", lambda: True)
    monkeypatch.setattr(database, "database_path", lambda: tmp_path / "issuance.sqlite")
    store = demo.PublicDemoSessionStore(issuance_limit=1)
    app = FastAPI()
    app.add_middleware(demo.PublicDemoBoundaryMiddleware, session_store=store)
    app.add_api_route("/api/regions", lambda: {"regions": []})
    with TestClient(app) as client:
        assert client.get("/api/regions").status_code == 200
        client.cookies.clear()
        response = client.get("/api/regions", headers={"X-Forwarded-For": "192.0.2.99"})
        assert response.status_code == 429
        assert response.json()["code"] == "DEMO_SESSION_RATE_LIMITED"
        assert int(response.headers["Retry-After"]) > 0
        assert "set-cookie" not in response.headers


def test_exhausted_session_is_rejected_before_joining_solver_queue(monkeypatch):
    monkeypatch.setattr(demo, "enabled", lambda: True)
    sessions = demo.PublicDemoRateLimiter(limit=1)
    assert sessions.retry_after("visitor-a") is None
    app = FastAPI()
    app.add_middleware(
        demo.PublicDemoBoundaryMiddleware,
        session_limiter=sessions,
        session_store=RegisteredSessions(),
        solver_gate=demo.SolverCapacityGate(active_limit=0, waiting_limit=0),
    )
    app.add_api_route("/api/overview", lambda: {"unreachable": True})
    with TestClient(app) as client:
        assert client.get("/api/overview").status_code == 429


def test_competing_admission_after_queue_wait_releases_capacity(monkeypatch):
    monkeypatch.setattr(demo, "enabled", lambda: True)
    shared = demo.PublicDemoRateLimiter(limit=1)

    class CompetingGate(demo.SolverCapacityGate):
        async def acquire(self):
            assert shared.retry_after("shared-public-demo-budget") is None
            return await super().acquire()

    gate = CompetingGate(active_limit=1, waiting_limit=0)
    app = FastAPI()
    app.add_middleware(
        demo.PublicDemoBoundaryMiddleware,
        limiter=shared,
        session_store=RegisteredSessions(),
        solver_gate=gate,
    )
    app.add_api_route("/api/overview", lambda: {"unreachable": True})
    with TestClient(app) as client:
        assert client.get("/api/overview").status_code == 429
    assert gate._active == 0
    assert gate._waiting == 0


def test_general_read_budget_is_separate_from_basic_lookup_and_compute(monkeypatch):
    monkeypatch.setattr(demo, "enabled", lambda: True)
    app = FastAPI()
    app.add_middleware(demo.PublicDemoBoundaryMiddleware, session_store=RegisteredSessions())
    for path in ["/api/regions", "/api/providers", "/api/overview"]:
        app.add_api_route(path, lambda: {"ok": True})
    with TestClient(app) as client:
        for _ in range(120):
            assert client.get("/api/providers").status_code == 200
        assert client.get("/api/providers").status_code == 429
        assert client.get("/api/regions").status_code == 200
        assert client.get("/api/overview").status_code == 200
