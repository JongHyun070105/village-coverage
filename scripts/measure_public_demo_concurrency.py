"""Compare isolated visitor sessions with the legacy shared 20/minute demo budget."""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import resource
import sys
import tempfile
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx
from fastapi import FastAPI

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["VILLAGE_COVERAGE_PUBLIC_DEMO"] = "true"
os.environ["PUBLIC_DEMO_COOKIE_SECURE"] = "false"

from backend import database, travel  # noqa: E402
from backend import main as backend_main  # noqa: E402
from backend.public_demo import (  # noqa: E402
    PUBLIC_DEMO_SESSION_COOKIE,
    PublicDemoBoundaryMiddleware,
    PublicDemoRateLimiter,
    PublicDemoSessionStore,
    SolverCapacityGate,
)

VISITOR_COUNTS = (1, 3, 5, 10)
REGION_ID = "pilot:홍성군 장곡면"
BUDGET = 4_000_000
SCENARIOS = ("efficiency", "balanced", "minimum_coverage", "underserved_first")


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(fraction * len(ordered)) - 1)]


def sqlite_storage_bytes(path: Path) -> int:
    return sum(
        candidate.stat().st_size
        for suffix in ("", "-wal", "-shm")
        if (candidate := Path(f"{path}{suffix}")).exists()
    )


def make_local_app(*, global_limit: int) -> FastAPI:
    app = FastAPI()
    app.include_router(backend_main.app.router)
    app.add_middleware(
        PublicDemoBoundaryMiddleware,
        limiter=PublicDemoRateLimiter(limit=global_limit),
        session_limiter=PublicDemoRateLimiter(limit=20),
        session_store=PublicDemoSessionStore(),
        solver_gate=SolverCapacityGate(active_limit=4, waiting_limit=6, wait_seconds=15),
    )
    return app


async def run_case(visitor_count: int, root: Path, *, legacy_shared: bool) -> dict[str, Any]:
    app_path = root / "app.sqlite"
    route_path = root / "routes.sqlite"
    database.database_path = lambda: app_path
    travel.route_database_path = lambda: route_path
    backend_main.route_database_path = lambda: route_path
    backend_main.initialize_public_demo_storage()

    app = make_local_app(global_limit=20 if legacy_shared else 120)
    transport = httpx.ASGITransport(app=app)
    clients = [
        httpx.AsyncClient(
            transport=transport,
            base_url="http://public-demo.local",
            timeout=httpx.Timeout(180),
        )
        for _ in range(visitor_count)
    ]
    if legacy_shared:
        await clients[0].get("/api/regions")
        shared_token = clients[0].cookies.get(PUBLIC_DEMO_SESSION_COOKIE)
        if not shared_token:
            raise RuntimeError("legacy baseline could not issue its shared visitor session")
        for client in clients[1:]:
            client.cookies.set(PUBLIC_DEMO_SESSION_COOKIE, shared_token, path="/api")
    else:
        await asyncio.gather(*(client.get("/api/regions") for client in clients))

    started = time.perf_counter()
    records: list[dict[str, Any]] = []
    visitor_states: list[dict[str, Any]] = [
        {"schedule_ids": [], "complete": False, "stop_reason": None} for _ in range(visitor_count)
    ]
    timeouts = 0

    async def call(
        index: int,
        action: str,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        *,
        solver: bool = False,
    ) -> dict[str, Any] | None:
        nonlocal timeouts
        started_request = time.perf_counter()
        try:
            response = await clients[index].request(method, path, json=body)
        except (httpx.TimeoutException, asyncio.TimeoutError):
            timeouts += 1
            records.append(
                {
                    "visitor": index + 1,
                    "action": action,
                    "status": "TIMEOUT",
                    "latency_ms": round((time.perf_counter() - started_request) * 1000, 3),
                    "solver": solver,
                }
            )
            visitor_states[index]["stop_reason"] = "TIMEOUT"
            return None
        elapsed = round((time.perf_counter() - started_request) * 1000, 3)
        try:
            payload = response.json()
        except ValueError:
            payload = None
        records.append(
            {
                "visitor": index + 1,
                "action": action,
                "status": response.status_code,
                "latency_ms": elapsed,
                "solver": solver,
                "retry_after": response.headers.get("retry-after"),
            }
        )
        if response.status_code < 200 or response.status_code >= 300:
            visitor_states[index]["stop_reason"] = (
                payload.get("code", payload.get("detail", f"HTTP_{response.status_code}"))
                if isinstance(payload, dict)
                else f"HTTP_{response.status_code}"
            )
            return None
        return payload if isinstance(payload, dict) else {}

    async def workflow(index: int) -> None:
        state = visitor_states[index]
        query = f"budget={BUDGET}&region_id={quote(REGION_ID, safe='')}"
        dashboard = await call(index, "dashboard", "GET", f"/api/overview?{query}", solver=True)
        if dashboard is None:
            return

        for scenario in SCENARIOS:
            plan = await call(
                index,
                f"scenario_{scenario}",
                "POST",
                "/api/schedules",
                {"scenario": scenario, "budget_won": BUDGET, "region_id": REGION_ID},
                solver=True,
            )
            if plan is None:
                return
            state["schedule_ids"].append(plan["schedule_id"])
            explanations = await call(
                index,
                f"scenario_{scenario}_explanations",
                "GET",
                f"/api/schedules/{quote(plan['schedule_id'], safe='')}/explanations",
            )
            if explanations is None:
                return

        minimum = await call(
            index,
            "scenario_minimum_coverage_analysis",
            "POST",
            "/api/minimum-coverage/analysis",
            {"budget_won": BUDGET, "region_id": REGION_ID},
            solver=True,
        )
        if minimum is None:
            return
        state["schedule_ids"].append(minimum["schedule_id"])

        plan = await call(
            index,
            "plan_create",
            "POST",
            "/api/schedules",
            {"scenario": "balanced", "budget_won": BUDGET, "region_id": REGION_ID},
            solver=True,
        )
        if plan is None:
            return
        state["schedule_ids"].append(plan["schedule_id"])
        if not plan.get("rounds"):
            state["stop_reason"] = "NO_PLAN_ROUNDS"
            return
        round_item = plan["rounds"][0]
        decline = await call(
            index,
            "provider_decline",
            "POST",
            f"/api/providers/{quote(round_item['provider_id'], safe='')}/rounds/"
            f"{quote(round_item['service_round_id'], safe='')}/participation",
            {
                "status": "DECLINED",
                "expected_status": round_item.get("participation_status", "AVAILABLE"),
            },
        )
        if decline is None:
            return
        replanned = await call(
            index,
            "replan",
            "POST",
            f"/api/schedules/{quote(plan['schedule_id'], safe='')}/replan",
            {"expected_plan_version": plan["plan_version"]},
            solver=True,
        )
        if replanned is None:
            return
        state["schedule_ids"].append(replanned["schedule_id"])
        detail = await call(
            index,
            "plan_detail",
            "GET",
            f"/api/schedules/{quote(replanned['schedule_id'], safe='')}",
        )
        if detail is None:
            return
        state["complete"] = True

    try:
        await asyncio.gather(*(workflow(index) for index in range(visitor_count)))
        histories = await asyncio.gather(
            *(client.get("/api/schedules", params={"region_id": REGION_ID}) for client in clients)
        )
        history_ids = [
            {str(plan["schedule_id"]) for plan in response.json().get("plans", [])}
            if response.status_code == 200
            else set()
            for response in histories
        ]
        all_owned_ids = {
            schedule_id for state in visitor_states for schedule_id in state["schedule_ids"]
        }
        isolation_leak_visitors = sum(
            bool(history_ids[index] & (all_owned_ids - set(visitor_states[index]["schedule_ids"])))
            for index in range(visitor_count)
        )
    finally:
        await asyncio.gather(*(client.aclose() for client in clients))

    elapsed_seconds = time.perf_counter() - started
    statuses = [record["status"] for record in records]
    latencies = [record["latency_ms"] for record in records]
    solver_latencies = [record["latency_ms"] for record in records if record["solver"]]
    failures = [
        record
        for record in records
        if not isinstance(record["status"], int) or record["status"] >= 400
    ]
    workflow_requests = len(records)
    session_issuance_requests = 1 if legacy_shared else visitor_count
    isolation_check_requests = visitor_count
    max_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    rss_mb = max_rss / (1024 * 1024 if sys.platform == "darwin" else 1024)
    return {
        "visitor_count": visitor_count,
        "requests": workflow_requests
        + session_issuance_requests
        + isolation_check_requests,
        "workflow_requests": workflow_requests,
        "session_issuance_requests": session_issuance_requests,
        "isolation_check_requests": isolation_check_requests,
        "successful_workflow_requests": sum(
            isinstance(status, int) and 200 <= status < 300 for status in statuses
        ),
        "rate_limited_429_count": sum(status == 429 for status in statuses),
        "timeouts": timeouts,
        "other_failures": len(failures)
        - sum(status == 429 for status in statuses if isinstance(status, int)),
        "successful_visitors": sum(bool(state["complete"]) for state in visitor_states),
        "failed_visitors": [
            {"visitor": index + 1, "reason": state["stop_reason"]}
            for index, state in enumerate(visitor_states)
            if not state["complete"]
        ],
        "cross_session_history_leak_visitors": isolation_leak_visitors,
        "elapsed_seconds": round(elapsed_seconds, 3),
        "throughput_visitors_per_second": round(
            sum(bool(state["complete"]) for state in visitor_states) / elapsed_seconds,
            3 if elapsed_seconds else 0,
        ),
        "latency_ms": {
            "average": round(sum(latencies) / len(latencies), 3) if latencies else 0,
            "p50": round(percentile(latencies, 0.5) or 0, 3),
            "p95": round(percentile(latencies, 0.95) or 0, 3),
            "sample_count": len(latencies),
        },
        "solver_latency_ms": {
            "average": round(sum(solver_latencies) / len(solver_latencies), 3)
            if solver_latencies
            else 0,
            "p50": round(percentile(solver_latencies, 0.5) or 0, 3),
            "p95": round(percentile(solver_latencies, 0.95) or 0, 3),
            "sample_count": len(solver_latencies),
        },
        "app_database_bytes_after_run": sqlite_storage_bytes(app_path),
        "route_database_bytes_after_run": sqlite_storage_bytes(route_path),
        "total_sqlite_bytes_after_run": sqlite_storage_bytes(app_path)
        + sqlite_storage_bytes(route_path),
        "process_peak_rss_mb": round(rss_mb, 2),
        "limiter_global_limit_per_minute": 20 if legacy_shared else 120,
        "request_records": records,
    }


async def run_suite() -> dict[str, Any]:
    modes = ("legacy_shared_20_per_minute", "isolated_sessions_120_global_20_per_session")
    results: dict[str, dict[str, Any]] = {mode: {} for mode in modes}
    for mode in modes:
        legacy_shared = mode == "legacy_shared_20_per_minute"
        for visitor_count in VISITOR_COUNTS:
            with tempfile.TemporaryDirectory(prefix="villagecoverage-concurrency-") as directory:
                results[mode][str(visitor_count)] = await run_case(
                    visitor_count,
                    Path(directory),
                    legacy_shared=legacy_shared,
                )
    return {
        "schema_version": 1,
        "scope": "LOCAL SYNTHETIC API LOAD ONLY; TEMPORARY SQLITE; NO PUBLIC RENDER LOAD",
        "fixture": {
            "region_id": REGION_ID,
            "budget_won": BUDGET,
            "seed": 2026,
            "routing": "same seeded straight-line synthetic routes per fresh case",
            "solver_workers": 1,
            "solver_limit_seconds": 3.0,
        },
        "methodology": {
            "workflow": [
                "dashboard overview",
                "four scenario plans plus explanations",
                "minimum coverage analysis",
                "plan create",
                "provider decline",
                "replan",
                "plan detail",
            ],
            "arrival_pattern": (
                "Each visitor completes the same sequential flow concurrently with other visitors."
            ),
            "legacy_baseline": (
                "Current local API with one server-issued session shared by all visitors "
                "and the former 20/minute global ceiling."
            ),
            "post_change": (
                "Distinct server-issued sessions, 20/minute per session, 120/minute global "
                "ceiling, and a 4-active/6-waiting bounded solver gate."
            ),
            "retries": "No automatic retries.",
            "latency": (
                "Local in-process ASGI latency; excludes browser, network and Render."
            ),
            "memory": "Process peak RSS high-water mark, not per-visitor memory.",
        },
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "artifacts" / "concurrency" / "public_demo_load_test.json",
    )
    args = parser.parse_args()
    result = asyncio.run(run_suite())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    summary = {
        mode: {
            count: {
                key: case[key]
                for key in (
                    "successful_visitors",
                    "requests",
                    "workflow_requests",
                    "rate_limited_429_count",
                    "elapsed_seconds",
                    "latency_ms",
                    "solver_latency_ms",
                )
            }
            for count, case in cases.items()
        }
        for mode, cases in result["results"].items()
    }
    print(
        json.dumps({"output": str(args.output), "summary": summary}, ensure_ascii=False, indent=2)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
