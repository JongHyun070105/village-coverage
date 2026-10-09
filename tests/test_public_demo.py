from __future__ import annotations

import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from backend import database, travel
from backend.main import app, initialize_public_demo_storage
from backend.public_demo import (
    PUBLIC_DEMO_BLOCKED,
    PUBLIC_DEMO_READ,
    PUBLIC_DEMO_SAFE_WRITE,
    PublicDemoBoundaryMiddleware,
    PublicDemoRateLimiter,
    _is_limited_operation,
    _is_solver_operation,
    classify,
    classify_route_template,
    cors_exposed_headers,
    cors_origins,
    enabled,
)


def test_public_demo_is_disabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv("VILLAGE_COVERAGE_PUBLIC_DEMO", raising=False)
    assert enabled() is False


def test_public_demo_request_policy_is_allowlist_based() -> None:
    assert classify("GET", "/api/overview") == PUBLIC_DEMO_READ
    assert classify("GET", "/api/schedules/a/decision-memo.pdf") == PUBLIC_DEMO_READ
    assert classify("POST", "/api/schedules") == PUBLIC_DEMO_SAFE_WRITE
    assert classify("POST", "/api/schedules/a/replan") == PUBLIC_DEMO_SAFE_WRITE
    assert classify("POST", "/api/providers/p/rounds/r/participation") == PUBLIC_DEMO_SAFE_WRITE
    assert classify("POST", "/api/providers/p/participation-preferences") == PUBLIC_DEMO_BLOCKED
    assert classify("GET", "/api/feedback/a/contact") == PUBLIC_DEMO_BLOCKED
    assert classify("GET", "/api/feedback") == PUBLIC_DEMO_BLOCKED
    assert classify("POST", "/api/pilot-imports/provider_capacity/preview") == PUBLIC_DEMO_BLOCKED
    assert classify("POST", "/api/schedules/a/revision") == PUBLIC_DEMO_BLOCKED
    assert classify("POST", "/api/schedules/a/approval") == PUBLIC_DEMO_SAFE_WRITE
    assert classify_route_template("GET", "/api/villages/{area_id}/feedback") == (
        PUBLIC_DEMO_BLOCKED
    )


def test_expensive_public_demo_reads_use_per_session_limit_and_solver_gate() -> None:
    expensive_reads = [
        "/api/overview",
        "/api/operations/attention",
        "/api/villages/area-1",
        "/api/regions/region-1/reserve-comparison",
        "/api/regions/region-1/underserved/comparison",
    ]
    for path in expensive_reads:
        assert _is_limited_operation("GET", path)
        assert _is_solver_operation("GET", path)


def test_every_state_changing_api_route_has_an_explicit_safe_or_blocked_classification() -> None:
    inventory = {
        (method, route.path): classify_route_template(method, route.path)
        for route in app.routes
        if isinstance(route, APIRoute)
        for method in route.methods or set()
        if method in {"POST", "PUT", "PATCH", "DELETE"}
    }

    assert inventory
    assert set(inventory.values()) <= {PUBLIC_DEMO_SAFE_WRITE, PUBLIC_DEMO_BLOCKED}
    assert {
        route
        for route, classification in inventory.items()
        if classification == PUBLIC_DEMO_SAFE_WRITE
    } == {
        ("POST", "/api/schedules"),
        ("POST", "/api/schedules/{schedule_id}/replan"),
        ("POST", "/api/schedules/{schedule_id}/approval"),
        ("POST", "/api/minimum-coverage/analysis"),
        ("POST", "/api/providers/{provider_id}/rounds/{round_id}/participation"),
    }


def test_cors_requires_exact_https_origin_for_public_demo() -> None:
    assert cors_origins(
        "https://demo.example,https://other.example/path,http://localhost:3000,*",
        public_demo=True,
    ) == ["https://demo.example"]
    assert cors_origins("http://127.0.0.1:3010", public_demo=True, allow_localhost=True) == [
        "http://127.0.0.1:3010"
    ]
    assert "http://localhost:3000" not in cors_origins("", public_demo=True)
    assert "http://localhost:3000" in cors_origins("", public_demo=False)
    assert cors_exposed_headers(public_demo=True) == ["Retry-After"]
    assert cors_exposed_headers(public_demo=False) == []


def test_public_demo_mode_uses_separate_ephemeral_database(monkeypatch) -> None:
    monkeypatch.setenv("VILLAGE_COVERAGE_PUBLIC_DEMO", "true")
    path = database.database_path()
    assert path.parent == Path(tempfile.gettempdir())
    assert path.name == "villagecoverage-public-demo.sqlite"
    assert path != database.ROOT / "data" / "village_coverage_app.sqlite"


def test_public_demo_storage_is_seeded_and_private_routes_fail_closed(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("VILLAGE_COVERAGE_PUBLIC_DEMO", "true")
    app_db = tmp_path / "public-demo.sqlite"
    route_db = tmp_path / "public-demo-routes.sqlite"
    monkeypatch.setattr(database, "database_path", lambda: app_db)
    monkeypatch.setattr(travel, "route_database_path", lambda: route_db)
    monkeypatch.setattr("backend.main.route_database_path", lambda: route_db)

    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}
        assert client.get("/api/regions").status_code == 200
        assert client.get("/api/areas").status_code == 200
        assert client.get("/api/providers").status_code == 200

        blocked = [
            client.get("/api/feedback/test-feedback/contact?role=PLANNER"),
            client.get("/api/feedback"),
            client.get("/api/audit-events"),
            client.post("/api/feedback", json={"contact": "010-2222-3333"}),
            client.post("/api/pilot-imports/provider_capacity/preview"),
            client.post("/api/schedules/example/revision", json={}),
            client.post(
                "/api/schedules/example/approval",
                json={"action": "request_changes", "role": "REVIEWER", "comment": "개인정보"},
            ),
        ]
        assert all(response.status_code == 404 for response in blocked)
        assert all("DEMO_MODE_RESTRICTED" in response.text for response in blocked[:7])
        assert blocked[0].headers["x-content-type-options"] == "nosniff"
        assert blocked[0].headers["referrer-policy"] == "strict-origin-when-cross-origin"
        assert blocked[0].headers["content-security-policy"] == "frame-ancestors 'none'"
        assert blocked[0].headers["cache-control"] == "no-store"

    assert app_db.exists()
    assert route_db.exists()
    with sqlite3.connect(app_db) as connection:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        sensitive_table_names = {
            name
            for name in tables
            if any(token in name.casefold() for token in ("survey", "feedback", "import", "pilot"))
        }
        assert sensitive_table_names
        assert all(
            connection.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0] == 0
            for name in sensitive_table_names
        )

        pii_patterns = (
            re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b"),
            re.compile(r"(?<!\d)(?:\+?82[- .]?)?0\d{1,2}[- .]?\d{3,4}[- .]?\d{4}(?!\d)"),
        )
        for table in tables:
            columns = connection.execute(f'PRAGMA table_info("{table}")').fetchall()
            for column in columns:
                if column[2].upper() not in {"TEXT", "VARCHAR"}:
                    continue
                for (value,) in connection.execute(
                    f'SELECT "{column[1]}" FROM "{table}" WHERE "{column[1]}" IS NOT NULL'
                ):
                    if isinstance(value, str):
                        if column[1] == "facility_id" and re.fullmatch(
                            r"public-facility-[a-f0-9]{24}", value
                        ):
                            continue
                        assert not any(pattern.search(value) for pattern in pii_patterns)

    with sqlite3.connect(route_db) as connection:
        route_count = connection.execute("SELECT COUNT(*) FROM travel_matrix").fetchone()[0]
        route_version = connection.execute(
            "SELECT DISTINCT routing_version FROM travel_matrix"
        ).fetchall()
    assert route_count == 54 * 54
    assert route_version == [("public-demo-straight-line-estimate-v1",)]


def test_public_demo_restart_preserves_live_session_and_plan(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("VILLAGE_COVERAGE_PUBLIC_DEMO", "true")
    app_db = tmp_path / "public-demo-restart.sqlite"
    route_db = tmp_path / "public-demo-restart-routes.sqlite"
    monkeypatch.setattr(database, "database_path", lambda: app_db)
    monkeypatch.setattr(travel, "route_database_path", lambda: route_db)
    monkeypatch.setattr("backend.main.route_database_path", lambda: route_db)

    with TestClient(app) as client:
        created = client.post(
            "/api/schedules",
            json={
                "scenario": "balanced",
                "budget_won": 4_000_000,
                "region_id": "pilot:홍성군 장곡면",
            },
        )
        assert created.status_code == 201
        schedule_id = created.json()["schedule_id"]
        assert client.get(f"/api/schedules/{schedule_id}").status_code == 200

        initialize_public_demo_storage()

        stale = client.get(f"/api/schedules/{schedule_id}")
        assert stale.status_code == 200
        assert stale.json()["schedule_id"] == schedule_id
        assert "DEMO_MODE_RESTRICTED" not in stale.text


def test_public_demo_plan_budget_and_region_boundaries(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("VILLAGE_COVERAGE_PUBLIC_DEMO", "true")
    app_db = tmp_path / "public-demo-boundaries.sqlite"
    route_db = tmp_path / "public-demo-boundaries-routes.sqlite"
    monkeypatch.setattr(database, "database_path", lambda: app_db)
    monkeypatch.setattr(travel, "route_database_path", lambda: route_db)
    monkeypatch.setattr("backend.main.route_database_path", lambda: route_db)

    with TestClient(app) as client:
        request_body = {
            "scenario": "balanced",
            "region_id": "pilot:홍성군 장곡면",
        }
        unknown_region = client.post(
            "/api/schedules",
            json={**request_body, "region_id": "not-a-real-region", "budget_won": 4_000_000},
        )
        assert unknown_region.status_code == 422

        over_limit = client.post(
            "/api/schedules",
            json={**request_body, "budget_won": 100_000_001},
        )
        assert over_limit.status_code == 422

        for budget_won in (0, 1, 100_000_000):
            response = client.post(
                "/api/schedules",
                json={**request_body, "budget_won": budget_won},
            )
            assert response.status_code == 201
            plan = response.json()
            assert plan["budget_won"] == budget_won
            assert plan["summary"]["budget_spent_won"] <= budget_won


def test_public_demo_rate_limiter_blocks_repeated_optimizer_actions() -> None:
    limiter = PublicDemoRateLimiter(limit=2, window_seconds=60)
    assert limiter.retry_after("sandbox", now=100.0) is None
    assert limiter.retry_after("sandbox", now=101.0) is None
    assert limiter.retry_after("sandbox", now=102.0) == 58
    assert limiter.retry_after("sandbox", now=161.0) is None


def test_public_demo_boundary_returns_retry_after_when_shared_budget_is_exhausted(
    monkeypatch,
) -> None:
    monkeypatch.setenv("VILLAGE_COVERAGE_PUBLIC_DEMO", "true")
    limited_app = FastAPI()
    limited_app.add_middleware(
        PublicDemoBoundaryMiddleware,
        limiter=PublicDemoRateLimiter(limit=1, window_seconds=60),
    )
    limited_app.add_api_route("/api/overview", lambda: {"ok": True}, methods=["GET"])

    with TestClient(limited_app) as client:
        allowed = client.get("/api/overview", headers={"X-Demo-Visitor": "visitor-a"})
        assert allowed.status_code == 200
        assert allowed.headers["x-content-type-options"] == "nosniff"
        assert allowed.headers["referrer-policy"] == "strict-origin-when-cross-origin"
        assert allowed.headers["content-security-policy"] == "frame-ancestors 'none'"
        assert allowed.headers["cache-control"] == "no-store"
        # A client-controlled visitor header cannot mint another limiter bucket.
        limited = client.get("/api/overview", headers={"X-Demo-Visitor": "visitor-b"})
        assert limited.status_code == 429
        assert limited.json()["code"] == "DEMO_RATE_LIMITED"
        assert limited.headers["retry-after"]


def test_public_demo_cors_accepts_only_the_configured_https_origin(monkeypatch) -> None:
    monkeypatch.setenv("VILLAGE_COVERAGE_PUBLIC_DEMO", "true")
    cors_app = FastAPI()
    cors_app.add_middleware(
        PublicDemoBoundaryMiddleware,
        limiter=PublicDemoRateLimiter(limit=1, window_seconds=60),
    )
    cors_app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins("https://demo.example", public_demo=True),
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
        expose_headers=["Retry-After"],
    )
    cors_app.add_api_route("/api/regions", lambda: {"ok": True}, methods=["GET"])
    cors_app.add_api_route("/api/overview", lambda: {"ok": True}, methods=["GET"])

    with TestClient(cors_app) as client:
        allowed = client.get("/api/regions", headers={"Origin": "https://demo.example"})
        denied = client.get("/api/regions", headers={"Origin": "https://attacker.example"})
        preflight = client.options(
            "/api/regions",
            headers={
                "Origin": "https://demo.example",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        denied_preflight = client.options(
            "/api/regions",
            headers={
                "Origin": "https://attacker.example",
                "Access-Control-Request-Method": "POST",
            },
        )
        client.get("/api/overview", headers={"Origin": "https://demo.example"})
        limited = client.get("/api/overview", headers={"Origin": "https://demo.example"})
    assert allowed.headers["access-control-allow-origin"] == "https://demo.example"
    assert allowed.headers["access-control-expose-headers"] == "Retry-After"
    assert "access-control-allow-origin" not in denied.headers
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == "https://demo.example"
    assert "DELETE" not in preflight.headers["access-control-allow-methods"]
    assert denied_preflight.status_code == 400
    assert "access-control-allow-origin" not in denied_preflight.headers
    assert limited.status_code == 429
    assert limited.headers["retry-after"]
    assert limited.headers["access-control-expose-headers"] == "Retry-After"


def test_public_demo_build_disables_schema_routes() -> None:
    environment = os.environ.copy()
    environment["VILLAGE_COVERAGE_PUBLIC_DEMO"] = "true"
    environment["FRONTEND_ORIGINS"] = "https://demo.example"
    script = (
        "from backend.main import app; "
        "print(json.dumps([app.docs_url, app.redoc_url, app.openapi_url]))"
    )
    completed = subprocess.run(
        [sys.executable, "-c", f"import json; {script}"],
        cwd=Path(__file__).resolve().parents[1],
        env=environment,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert json.loads(completed.stdout.strip().splitlines()[-1]) == [None, None, None]
