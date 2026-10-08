"""Measure public-demo limiter behavior against the real API on isolated SQLite."""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["VILLAGE_COVERAGE_PUBLIC_DEMO"] = "true"

from backend import database, travel  # noqa: E402
from backend import main as backend_main  # noqa: E402
from backend.public_demo import PublicDemoBoundaryMiddleware, PublicDemoRateLimiter  # noqa: E402

VISITOR_COUNTS = (1, 3, 5, 10)
REGION_ID = "pilot:홍성군 장곡면"
PLAN_INPUT = {
    "scenario": "balanced",
    "budget_won": 4_000_000,
    "region_id": REGION_ID,
}


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(fraction * len(ordered)) - 1)]


def create_app() -> FastAPI:
    app = FastAPI()
    app.include_router(backend_main.app.router)
    app.add_middleware(
        PublicDemoBoundaryMiddleware,
        limiter=PublicDemoRateLimiter(limit=20, window_seconds=60),
    )
    return app


async def measured_request(
    client: httpx.AsyncClient,
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
) -> tuple[httpx.Response, float]:
    started = time.perf_counter()
    response = await client.request(method, path, json=body)
    return response, round((time.perf_counter() - started) * 1000, 3)


async def measure_case(visitor_count: int, root: Path) -> dict[str, Any]:
    app_path = root / "app.sqlite"
    route_path = root / "routes.sqlite"
    database.database_path = lambda: app_path
    travel.route_database_path = lambda: route_path
    backend_main.route_database_path = lambda: route_path
    backend_main.initialize_public_demo_storage()

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    clients = [
        httpx.AsyncClient(
            transport=transport,
            base_url="http://public-demo.local",
            headers={"X-Demo-Visitor": f"untrusted-visitor-{index + 1}"},
        )
        for index in range(visitor_count)
    ]
    state: dict[int, dict[str, Any]] = {index: {} for index in range(visitor_count)}
    records: list[dict[str, Any]] = []
    retry_after_seconds: list[int] = []

    async def run_phase(
        action: str,
        method: str,
        path_for: Any,
        body_for: Any = None,
        *,
        active_only: bool = True,
    ) -> None:
        indices = [
            index
            for index in range(visitor_count)
            if not active_only or not state[index].get("stopped")
        ]

        async def send(index: int) -> tuple[int, httpx.Response, float]:
            path = path_for(index) if callable(path_for) else path_for
            body = body_for(index) if callable(body_for) else body_for
            response, elapsed = await measured_request(clients[index], method, path, body)
            return index, response, elapsed

        for index, response, elapsed in await asyncio.gather(*(send(i) for i in indices)):
            record = {
                "visitor": index + 1,
                "action": action,
                "status": response.status_code,
                "latency_ms": elapsed,
            }
            records.append(record)
            retry_after = response.headers.get("retry-after")
            if response.status_code == 429:
                state[index]["stopped"] = True
                if retry_after and retry_after.isdigit():
                    retry_after_seconds.append(int(retry_after))
                record["stop_reason"] = response.json().get("code", "HTTP_429")
                continue
            if response.status_code >= 400:
                state[index]["stopped"] = True
                record["stop_reason"] = response.json().get("code", f"HTTP_{response.status_code}")
                continue
            record["success"] = True
            try:
                state[index][action] = response.json()
            except ValueError:
                state[index][action] = None

    try:
        await run_phase(
            "dashboard",
            "GET",
            "/api/overview?budget=5000000&region_id="
            f"{httpx.QueryParams({'region_id': REGION_ID})['region_id']}",
        )
        await run_phase("scenario_calculation", "POST", "/api/schedules", PLAN_INPUT)

        def participation_path(index: int) -> str:
            plan = state[index].get("scenario_calculation", {})
            rounds = plan.get("rounds", [])
            if not rounds:
                return "/api/providers/invalid/rounds/invalid/participation"
            round_item = rounds[0]
            state[index]["round"] = round_item
            return (
                f"/api/providers/{round_item['provider_id']}/rounds/"
                f"{round_item['service_round_id']}/participation"
            )

        await run_phase(
            "provider_decline",
            "POST",
            participation_path,
            {"status": "DECLINED"},
        )
        await run_phase(
            "replan",
            "POST",
            lambda index: (
                f"/api/schedules/{state[index]['scenario_calculation']['schedule_id']}/replan"
            ),
        )
        await run_phase(
            "approval_submit",
            "POST",
            lambda index: f"/api/schedules/{state[index]['replan']['schedule_id']}/approval",
            {"action": "submit", "role": "PLANNER"},
        )
        await run_phase(
            "approval_simulation",
            "POST",
            lambda index: f"/api/schedules/{state[index]['replan']['schedule_id']}/approval",
            {"action": "approve", "role": "REVIEWER"},
        )
    finally:
        await asyncio.gather(*(client.aclose() for client in clients))

    statuses = [record["status"] for record in records]
    visitor_actions: dict[int, list[dict[str, Any]]] = {i: [] for i in range(visitor_count)}
    for record in records:
        visitor_actions[record["visitor"] - 1].append(record)
    successful_workflows = sum(
        1
        for actions in visitor_actions.values()
        if len(actions) == 6 and all(200 <= item["status"] < 300 for item in actions)
    )
    latencies = [record["latency_ms"] for record in records]
    return {
        "visitors": visitor_count,
        "requests": len(records),
        "rate_limited_429_count": sum(status == 429 for status in statuses),
        "successful_requests": sum(200 <= status < 300 for status in statuses),
        "successful_workflows": successful_workflows,
        "partial_or_failed_workflows": visitor_count - successful_workflows,
        "client_retries": 0,
        "unexpected_failures": sum(status not in {200, 201, 429} for status in statuses),
        "retry_after_seconds": retry_after_seconds,
        "latency_ms": {
            "p50": round(percentile(latencies, 0.5) or 0, 3),
            "p95": round(percentile(latencies, 0.95) or 0, 3),
            "max": round(max(latencies, default=0), 3),
            "sample_count": len(latencies),
            "interpretation": "Descriptive request latency under the bounded local workload.",
        },
        "request_records": records,
    }


async def run() -> dict[str, Any]:
    os.environ["VILLAGE_COVERAGE_PUBLIC_DEMO"] = "true"
    cases = []
    for count in VISITOR_COUNTS:
        with tempfile.TemporaryDirectory(prefix="villagecoverage-rate-limit-") as directory:
            cases.append(await measure_case(count, Path(directory)))
    return {
        "schema_version": 2,
        "scope": "SYNTHETIC LOCAL PUBLIC-DEMO API WORKLOAD; ISOLATED TEMP SQLITE; NO RENDER LOAD",
        "limiter": {
            "limit": 20,
            "window_seconds": 60,
            "scope": "shared process budget",
        },
        "methodology": {
            "workflow": [
                "GET dashboard overview",
                "POST calculate a balanced 4,000,000-won plan",
                "POST decline one assigned synthetic provider round",
                "POST replan from that decline",
                "POST request demo review",
                "POST simulate approval",
            ],
            "arrival_pattern": "Concurrent visitors issue each workflow step together.",
            "identity": (
                "Each client sends a distinct untrusted X-Demo-Visitor header. The server "
                "does not use it to partition limits."
            ),
            "retries": "No automatic client retries are modeled.",
            "latency_limit": (
                "Local API request latency includes solver/database work and excludes "
                "network/Render. "
                "p95 is descriptive for a small sample."
            ),
            "isolation": (
                "Each visitor-count case uses freshly seeded SQLite files in a temporary directory."
            ),
            "stop_rule": "Visitors stop their workflow after their first non-2xx response.",
        },
        "cases": cases,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "artifacts" / "research" / "public_demo_rate_limit_load.json",
    )
    args = parser.parse_args()
    result = asyncio.run(run())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "output": str(args.output),
                "cases": [
                    {key: value for key, value in case.items() if key != "request_records"}
                    for case in result["cases"]
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
