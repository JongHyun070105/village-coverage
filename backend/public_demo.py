"""Fail-closed request policy for the anonymous competition demo."""

from __future__ import annotations

import re
import threading
import time
from collections import deque
from typing import Any

from starlette.responses import JSONResponse

from scripts.api_smoke_test import _load_config

PUBLIC_DEMO_READ = "PUBLIC_DEMO_READ"
PUBLIC_DEMO_SAFE_WRITE = "PUBLIC_DEMO_SAFE_WRITE"
PUBLIC_DEMO_BLOCKED = "PUBLIC_DEMO_BLOCKED"


def enabled() -> bool:
    return _load_config("VILLAGE_COVERAGE_PUBLIC_DEMO").strip().casefold() in {
        "1",
        "true",
        "yes",
        "on",
    }


_RULES: tuple[tuple[str, str, str], ...] = (
    ("GET", r"/health", PUBLIC_DEMO_READ),
    ("GET", r"/api/health", PUBLIC_DEMO_READ),
    ("GET", r"/api/regions", PUBLIC_DEMO_READ),
    ("GET", r"/api/regions/comparison", PUBLIC_DEMO_READ),
    ("GET", r"/api/regions/[^/]+/reserve-comparison", PUBLIC_DEMO_READ),
    ("GET", r"/api/regions/[^/]+/home-repair/demand", PUBLIC_DEMO_READ),
    ("GET", r"/api/regions/[^/]+/underserved", PUBLIC_DEMO_READ),
    ("GET", r"/api/regions/[^/]+/underserved/comparison", PUBLIC_DEMO_READ),
    ("GET", r"/api/areas", PUBLIC_DEMO_READ),
    ("GET", r"/api/overview", PUBLIC_DEMO_READ),
    ("GET", r"/api/operations/attention", PUBLIC_DEMO_READ),
    ("GET", r"/api/villages/[^/]+", PUBLIC_DEMO_READ),
    ("GET", r"/api/villages/[^/]+/demand-v4", PUBLIC_DEMO_READ),
    ("GET", r"/api/providers", PUBLIC_DEMO_READ),
    ("GET", r"/api/providers/[^/]+", PUBLIC_DEMO_READ),
    ("GET", r"/api/providers/[^/]+/badges", PUBLIC_DEMO_READ),
    ("GET", r"/api/providers/[^/]+/home-repair-capability", PUBLIC_DEMO_READ),
    ("GET", r"/api/home-repair/profile", PUBLIC_DEMO_READ),
    ("GET", r"/api/schedules", PUBLIC_DEMO_READ),
    ("GET", r"/api/schedules/[^/]+", PUBLIC_DEMO_READ),
    ("GET", r"/api/schedules/[^/]+/decision-memo(?:\.html|\.pdf)?", PUBLIC_DEMO_READ),
    ("GET", r"/api/schedules/[^/]+/explanations", PUBLIC_DEMO_READ),
    ("GET", r"/api/schedules/[^/]+/export\.csv", PUBLIC_DEMO_READ),
    ("GET", r"/api/schedules/[^/]+/export/(?:budget|unmet)\.csv", PUBLIC_DEMO_READ),
    ("GET", r"/api/schedules/[^/]+/export/summary\.pdf", PUBLIC_DEMO_READ),
    ("GET", r"/api/forecasts/backtest", PUBLIC_DEMO_READ),
    ("GET", r"/api/data-quality", PUBLIC_DEMO_READ),
    ("GET", r"/api/data-dictionary", PUBLIC_DEMO_READ),
    ("GET", r"/api/services", PUBLIC_DEMO_READ),
    ("GET", r"/api/evidence/(?:sources|priors|kosis|home-doctor)", PUBLIC_DEMO_READ),
    ("GET", r"/api/policy/presets", PUBLIC_DEMO_READ),
    ("POST", r"/api/schedules", PUBLIC_DEMO_SAFE_WRITE),
    ("POST", r"/api/schedules/[^/]+/replan", PUBLIC_DEMO_SAFE_WRITE),
    ("POST", r"/api/schedules/[^/]+/approval", PUBLIC_DEMO_SAFE_WRITE),
    ("POST", r"/api/minimum-coverage/analysis", PUBLIC_DEMO_SAFE_WRITE),
    (
        "POST",
        r"/api/providers/[^/]+/rounds/[^/]+/participation",
        PUBLIC_DEMO_SAFE_WRITE,
    ),
)
_COMPILED_RULES = tuple(
    (method, re.compile(rf"\A(?:{pattern})\Z"), classification)
    for method, pattern, classification in _RULES
)


def classify(method: str, path: str) -> str:
    """Classify one concrete request path using the public demo allowlist."""
    method = method.upper()
    for allowed_method, pattern, classification in _COMPILED_RULES:
        if method == allowed_method and pattern.fullmatch(path):
            return classification
    return PUBLIC_DEMO_BLOCKED


def classify_route_template(method: str, path: str) -> str:
    """Classify a FastAPI route template for the acceptance inventory."""
    concrete_pattern = re.sub(r"\{[^}/]+\}", "demo-id", path)
    return classify(method, concrete_pattern)


class PublicDemoRateLimiter:
    """Small process-local sliding-window limit for optimizer and sandbox writes."""

    def __init__(self, limit: int = 20, window_seconds: int = 60) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._requests: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def retry_after(self, key: str, now: float | None = None) -> int | None:
        current = time.monotonic() if now is None else now
        cutoff = current - self.window_seconds
        with self._lock:
            events = self._requests.setdefault(key, deque())
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= self.limit:
                return max(1, int(events[0] + self.window_seconds - current + 0.999))
            events.append(current)
            if len(self._requests) > 1024:
                for old_key in tuple(self._requests):
                    if old_key != key and not self._requests[old_key]:
                        del self._requests[old_key]
                    if len(self._requests) <= 1024:
                        break
            return None


def _is_limited_operation(method: str, path: str) -> bool:
    return (method == "GET" and path == "/api/overview") or (
        classify(method, path) == PUBLIC_DEMO_SAFE_WRITE
    )


class PublicDemoBoundaryMiddleware:
    """Enforce the demo API allowlist before endpoint handlers run."""

    def __init__(self, app: Any, *, limiter: PublicDemoRateLimiter | None = None) -> None:
        self.app = app
        self.limiter = limiter or PublicDemoRateLimiter()

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http" or not enabled():
            await self.app(scope, receive, send)
            return

        method = str(scope.get("method", "GET")).upper()
        path = str(scope.get("path", "/"))
        if method != "OPTIONS" and (path.startswith("/api/") or path == "/health"):
            if classify(method, path) == PUBLIC_DEMO_BLOCKED:
                response = JSONResponse(
                    {"detail": "DEMO_MODE_RESTRICTED", "code": "DEMO_MODE_RESTRICTED"},
                    status_code=404,
                )
                await self._send_with_headers(response, scope, receive, send)
                return

            if _is_limited_operation(method, path):
                retry_after = self.limiter.retry_after("shared-public-demo-budget")
                if retry_after is not None:
                    response = JSONResponse(
                        {"detail": "DEMO_RATE_LIMITED", "code": "DEMO_RATE_LIMITED"},
                        status_code=429,
                        headers={"Retry-After": str(retry_after)},
                    )
                    await self._send_with_headers(response, scope, receive, send)
                    return

        async def send_with_headers(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                for name, value in (
                    (b"x-content-type-options", b"nosniff"),
                    (b"referrer-policy", b"strict-origin-when-cross-origin"),
                    (b"content-security-policy", b"frame-ancestors 'none'"),
                    (b"cache-control", b"no-store"),
                ):
                    if not any(existing.lower() == name for existing, _ in headers):
                        headers.append((name, value))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_headers)

    async def _send_with_headers(
        self, response: JSONResponse, scope: dict[str, Any], receive: Any, send: Any
    ) -> None:
        await response(scope, receive, self._header_sender(send))

    @staticmethod
    def _header_sender(send: Any) -> Any:
        async def send_with_headers(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                for name, value in (
                    (b"x-content-type-options", b"nosniff"),
                    (b"referrer-policy", b"strict-origin-when-cross-origin"),
                    (b"content-security-policy", b"frame-ancestors 'none'"),
                    (b"cache-control", b"no-store"),
                ):
                    if not any(existing.lower() == name for existing, _ in headers):
                        headers.append((name, value))
                message["headers"] = headers
            await send(message)

        return send_with_headers


def cors_origins(configured: str, *, public_demo: bool, allow_localhost: bool = False) -> list[str]:
    """Keep public demo CORS HTTPS-only and exact-origin; local defaults are dev-only."""
    origins = [origin.strip().rstrip("/") for origin in configured.split(",") if origin.strip()]
    if public_demo:
        return [
            origin
            for origin in origins
            if (origin.startswith("https://") and "*" not in origin and origin.count("/") == 2)
            or (
                allow_localhost
                and origin.startswith("http://")
                and "*" not in origin
                and origin.split("//", 1)[1].split(":", 1)[0] in {"localhost", "127.0.0.1"}
            )
        ]
    return origins or [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
    ]
