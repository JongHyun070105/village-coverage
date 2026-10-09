"""Fail-closed request policy for the anonymous competition demo."""

from __future__ import annotations

import asyncio
import hashlib
import re
import secrets
import threading
import time
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse

from scripts.api_smoke_test import _load_config

PUBLIC_DEMO_READ = "PUBLIC_DEMO_READ"
PUBLIC_DEMO_SAFE_WRITE = "PUBLIC_DEMO_SAFE_WRITE"
PUBLIC_DEMO_BLOCKED = "PUBLIC_DEMO_BLOCKED"
PUBLIC_DEMO_SESSION_COOKIE = "vc_demo_session"
PUBLIC_DEMO_SESSION_IDLE_SECONDS = 30 * 60
PUBLIC_DEMO_MAX_ACTIVE_SESSIONS = 256
PUBLIC_DEMO_MAX_PLANS_PER_SESSION = 20
PUBLIC_DEMO_MAX_DATABASE_BYTES = 64 * 1024 * 1024


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
    ("POST", r"/api/schedules/[^/]+/cost-model-v3", PUBLIC_DEMO_SAFE_WRITE),
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


def session_hash(request: Request) -> str | None:
    """Return the server-verified public demo owner set by the boundary middleware."""
    value = getattr(request.state, "public_demo_session_hash", None)
    return str(value) if value else None


def owns_plan(connection: Any, schedule_id: str, owner_hash: str | None) -> bool:
    if not owner_hash:
        return False
    row = connection.execute(
        "SELECT 1 FROM public_demo_plan_owners WHERE schedule_id=? AND session_hash=?",
        (schedule_id, owner_hash),
    ).fetchone()
    return row is not None


def record_plan_owner(connection: Any, schedule_id: str, owner_hash: str | None) -> None:
    if not owner_hash:
        raise ValueError("public demo plan has no verified session")
    connection.execute(
        "INSERT INTO public_demo_plan_owners(schedule_id, session_hash, created_at) "
        "VALUES (?, ?, ?)",
        (schedule_id, owner_hash, datetime.now(timezone.utc).isoformat(timespec="seconds")),
    )


def owned_round(
    connection: Any, *, provider_id: str, round_id: str, owner_hash: str | None
) -> bool:
    if not owner_hash:
        return False
    row = connection.execute(
        """SELECT 1 FROM scheduled_rounds rounds
           JOIN public_demo_plan_owners owners ON owners.schedule_id=rounds.schedule_id
           WHERE rounds.service_round_id=? AND rounds.provider_id=? AND owners.session_hash=?""",
        (round_id, provider_id, owner_hash),
    ).fetchone()
    return row is not None


def round_participation(
    connection: Any, *, provider_id: str, round_id: str, owner_hash: str | None
) -> str | None:
    if not owner_hash:
        return None
    row = connection.execute(
        "SELECT status FROM public_demo_provider_participations "
        "WHERE session_hash=? AND provider_id=? AND round_id=?",
        (owner_hash, provider_id, round_id),
    ).fetchone()
    return str(row[0]) if row is not None else None


def set_round_participation(
    connection: Any,
    *,
    provider_id: str,
    round_id: str,
    owner_hash: str | None,
    status: str,
    expected_status: str | None = None,
) -> bool:
    if not owner_hash:
        raise ValueError("public demo participation has no verified session")
    if status not in {"DECLINED", "AVAILABLE"}:
        raise ValueError("unsupported public demo participation transition")
    connection.execute("BEGIN IMMEDIATE")
    current = round_participation(
        connection, provider_id=provider_id, round_id=round_id, owner_hash=owner_hash
    ) or "AVAILABLE"
    if expected_status is not None and current != expected_status:
        raise ValueError("provider participation changed; refresh the plan before retrying")
    connection.execute(
        "INSERT INTO public_demo_provider_participations "
        "(session_hash, provider_id, round_id, status, updated_at) "
        "VALUES (?, ?, ?, ?, ?) ON CONFLICT(session_hash, provider_id, round_id) "
        "DO UPDATE SET status=excluded.status, updated_at=excluded.updated_at",
        (
            owner_hash,
            provider_id,
            round_id,
            status,
            datetime.now(timezone.utc).isoformat(timespec="seconds"),
        ),
    )
    connection.commit()
    return True


def session_plan_count(connection: Any, owner_hash: str | None) -> int:
    if not owner_hash:
        return 0
    return PublicDemoSessionStore.plan_count(connection, owner_hash)


def database_size_bytes() -> int:
    from backend import database

    path = database.database_path()
    total = 0
    for suffix in ("", "-wal", "-shm"):
        try:
            total += Path(f"{path}{suffix}").stat().st_size
        except OSError:
            continue
    return total


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


class SessionCapacityError(RuntimeError):
    """Raised when the public demo session store has reached its bounded capacity."""


class SessionIssueRateLimitError(RuntimeError):
    def __init__(self, retry_after: int) -> None:
        self.retry_after = retry_after


class PublicDemoSessionStore:
    """Issue opaque server-registered visitor sessions and expire only demo-owned rows."""

    def __init__(
        self,
        *,
        max_active_sessions: int = PUBLIC_DEMO_MAX_ACTIVE_SESSIONS,
        idle_seconds: int = PUBLIC_DEMO_SESSION_IDLE_SECONDS,
        issuance_limit: int = 30,
    ) -> None:
        self.max_active_sessions = max_active_sessions
        self.idle_seconds = idle_seconds
        self.issuance_limiter = PublicDemoRateLimiter(limit=issuance_limit)

    @staticmethod
    def _hash(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    def ensure_schema(connection: Any) -> None:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS public_demo_sessions (
                session_hash TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                expires_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS public_demo_plan_owners (
                schedule_id TEXT PRIMARY KEY,
                session_hash TEXT NOT NULL REFERENCES public_demo_sessions(session_hash)
                    ON DELETE CASCADE,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_public_demo_plan_owners_session
                ON public_demo_plan_owners(session_hash, created_at DESC);
            CREATE TABLE IF NOT EXISTS public_demo_provider_participations (
                session_hash TEXT NOT NULL REFERENCES public_demo_sessions(session_hash)
                    ON DELETE CASCADE,
                provider_id TEXT NOT NULL,
                round_id TEXT NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('DECLINED', 'AVAILABLE')),
                updated_at TEXT NOT NULL,
                PRIMARY KEY (session_hash, provider_id, round_id)
            );
            CREATE INDEX IF NOT EXISTS idx_public_demo_participations_round
                ON public_demo_provider_participations(round_id, session_hash);
            """
        )

    def ensure(self, supplied_token: str | None) -> tuple[str, str | None]:
        """Return the registered owner hash and a replacement token only when needed."""
        from backend import database

        now = datetime.now(timezone.utc).replace(microsecond=0)
        now_text = now.isoformat()
        expires_text = (now + timedelta(seconds=self.idle_seconds)).isoformat()
        connection = database.connect()
        try:
            self.ensure_schema(connection)
            connection.execute("BEGIN IMMEDIATE")
            expired = [
                str(row["session_hash"])
                for row in connection.execute(
                    "SELECT session_hash FROM public_demo_sessions WHERE expires_at<=?",
                    (now_text,),
                ).fetchall()
            ]
            for owner_hash in expired:
                schedule_ids = [
                    str(row[0])
                    for row in connection.execute(
                        "SELECT owners.schedule_id FROM public_demo_plan_owners owners "
                        "JOIN schedule_runs plans USING(schedule_id) "
                        "WHERE owners.session_hash=? ORDER BY plans.created_at DESC",
                        (owner_hash,),
                    ).fetchall()
                ]
                for schedule_id in schedule_ids:
                    connection.execute(
                        "DELETE FROM schedule_runs WHERE schedule_id=?", (schedule_id,)
                    )
                    connection.execute(
                        "DELETE FROM audit_events WHERE subject_type='schedule' AND subject_id=?",
                        (schedule_id,),
                    )
                connection.execute(
                    "DELETE FROM public_demo_provider_participations WHERE session_hash=?",
                    (owner_hash,),
                )
                connection.execute(
                    "DELETE FROM public_demo_sessions WHERE session_hash=?", (owner_hash,)
                )

            if supplied_token and len(supplied_token) <= 128:
                supplied_hash = self._hash(supplied_token)
                existing = connection.execute(
                    "SELECT 1 FROM public_demo_sessions WHERE session_hash=? AND expires_at>?",
                    (supplied_hash, now_text),
                ).fetchone()
                if existing is not None:
                    connection.execute(
                        "UPDATE public_demo_sessions SET last_seen_at=?, expires_at=? "
                        "WHERE session_hash=?",
                        (now_text, expires_text, supplied_hash),
                    )
                    connection.commit()
                    return supplied_hash, None

            retry_after = self.issuance_limiter.retry_after("public-demo-session-issuance")
            if retry_after is not None:
                connection.rollback()
                raise SessionIssueRateLimitError(retry_after)

            active_count = int(
                connection.execute("SELECT COUNT(*) FROM public_demo_sessions").fetchone()[0]
            )
            if active_count >= self.max_active_sessions:
                connection.rollback()
                raise SessionCapacityError("public demo session capacity reached")

            token = secrets.token_urlsafe(32)
            owner_hash = self._hash(token)
            connection.execute(
                "INSERT INTO public_demo_sessions("
                "session_hash, created_at, last_seen_at, expires_at) "
                "VALUES (?, ?, ?, ?)",
                (owner_hash, now_text, now_text, expires_text),
            )
            connection.commit()
            return owner_hash, token
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def plan_count(connection: Any, owner_hash: str) -> int:
        PublicDemoSessionStore.ensure_schema(connection)
        return int(
            connection.execute(
                "SELECT COUNT(*) FROM public_demo_plan_owners WHERE session_hash=?",
                (owner_hash,),
            ).fetchone()[0]
        )


class SolverCapacityGate:
    """Bound active and queued expensive operations, rejecting excess work promptly."""

    def __init__(
        self,
        *,
        active_limit: int = 4,
        waiting_limit: int = 6,
        wait_seconds: float = 15.0,
    ):
        self.active_limit = active_limit
        self.waiting_limit = waiting_limit
        self.wait_seconds = wait_seconds
        self._active = 0
        self._waiting = 0
        self._condition = asyncio.Condition()

    async def acquire(self) -> bool:
        async with self._condition:
            if self._active < self.active_limit:
                self._active += 1
                return True
            if self._waiting >= self.waiting_limit:
                return False
            self._waiting += 1
            try:
                await asyncio.wait_for(
                    self._condition.wait_for(lambda: self._active < self.active_limit),
                    timeout=self.wait_seconds,
                )
            except TimeoutError:
                return False
            finally:
                self._waiting -= 1
            self._active += 1
            return True

    async def release(self) -> None:
        async with self._condition:
            self._active -= 1
            self._condition.notify(1)


def _is_limited_operation(method: str, path: str) -> bool:
    return (method == "GET" and path in {
        "/api/overview",
        "/api/operations/attention",
    }) or (
        method == "GET"
        and bool(
            re.fullmatch(
                r"(?:/api/regions/[^/]+/(?:reserve-comparison|underserved/comparison)"
                r"|/api/villages/[^/]+)",
                path,
            )
        )
    ) or (
        classify(method, path) == PUBLIC_DEMO_SAFE_WRITE
    )


def _is_solver_operation(method: str, path: str) -> bool:
    if method == "POST":
        return path in {"/api/schedules", "/api/minimum-coverage/analysis"} or bool(
            re.fullmatch(r"/api/schedules/[^/]+/replan", path)
        )
    return method == "GET" and (
        path in {"/api/overview", "/api/operations/attention"}
        or bool(
            re.fullmatch(
                r"(?:/api/regions/[^/]+/(?:reserve-comparison|underserved/comparison)"
                r"|/api/villages/[^/]+)",
                path,
            )
        )
    )


class PublicDemoBoundaryMiddleware:
    """Enforce the demo API allowlist before endpoint handlers run."""

    def __init__(
        self,
        app: Any,
        *,
        limiter: PublicDemoRateLimiter | None = None,
        session_limiter: PublicDemoRateLimiter | None = None,
        session_store: PublicDemoSessionStore | None = None,
        solver_gate: SolverCapacityGate | None = None,
    ) -> None:
        self.app = app
        self.limiter = limiter or PublicDemoRateLimiter()
        self.session_limiter = session_limiter or PublicDemoRateLimiter(limit=20)
        self.session_store = session_store
        self.solver_gate = solver_gate or SolverCapacityGate()

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http" or not enabled():
            await self.app(scope, receive, send)
            return

        method = str(scope.get("method", "GET")).upper()
        path = str(scope.get("path", "/"))
        classification = classify(method, path)
        if method != "OPTIONS" and (path.startswith("/api/") or path == "/health"):
            if classification == PUBLIC_DEMO_BLOCKED:
                response = JSONResponse(
                    {"detail": "DEMO_MODE_RESTRICTED", "code": "DEMO_MODE_RESTRICTED"},
                    status_code=404,
                )
                await self._send_with_headers(response, scope, receive, send)
                return

        owner_hash: str | None = None
        set_cookie: bytes | None = None
        if (
            self.session_store is not None
            and method != "OPTIONS"
            and classification in {PUBLIC_DEMO_READ, PUBLIC_DEMO_SAFE_WRITE}
        ):
            token = Request(scope).cookies.get(PUBLIC_DEMO_SESSION_COOKIE)
            try:
                owner_hash, replacement_token = self.session_store.ensure(token)
            except SessionCapacityError:
                response = JSONResponse(
                    {"detail": "DEMO_SESSION_CAPACITY", "code": "DEMO_SESSION_CAPACITY"},
                    status_code=503,
                    headers={"Retry-After": "60"},
                )
                await self._send_with_headers(response, scope, receive, send)
                return
            except SessionIssueRateLimitError as exc:
                response = JSONResponse(
                    {"detail": "DEMO_SESSION_RATE_LIMITED", "code": "DEMO_SESSION_RATE_LIMITED"},
                    status_code=429,
                    headers={"Retry-After": str(exc.retry_after)},
                )
                await self._send_with_headers(response, scope, receive, send)
                return
            except Exception:
                response = JSONResponse(
                    {"detail": "DEMO_SESSION_UNAVAILABLE", "code": "DEMO_SESSION_UNAVAILABLE"},
                    status_code=503,
                    headers={"Retry-After": "5"},
                )
                await self._send_with_headers(response, scope, receive, send)
                return
            state = scope.setdefault("state", {})
            state["public_demo_session_hash"] = owner_hash
            if token and replacement_token is not None:
                state["public_demo_session_reissued"] = True
            cookie_token = replacement_token or token
            if cookie_token is not None:
                secure_setting = _load_config("PUBLIC_DEMO_COOKIE_SECURE").casefold()
                secure = secure_setting == "true" or (
                    secure_setting != "false" and Request(scope).url.scheme == "https"
                )
                cookie = (
                    f"{PUBLIC_DEMO_SESSION_COOKIE}={cookie_token}; Path=/api; "
                    f"Max-Age={self.session_store.idle_seconds}; HttpOnly; SameSite=Lax"
                    + ("; Secure" if secure else "")
                )
                set_cookie = cookie.encode("ascii")

        if _is_limited_operation(method, path):
            retry_after = None
            if owner_hash is not None:
                retry_after = self.session_limiter.retry_after(owner_hash)
            if retry_after is None:
                retry_after = self.limiter.retry_after("shared-public-demo-budget")
            if retry_after is not None:
                response = JSONResponse(
                    {"detail": "DEMO_RATE_LIMITED", "code": "DEMO_RATE_LIMITED"},
                    status_code=429,
                    headers={"Retry-After": str(retry_after)},
                )
                await self._send_with_headers(response, scope, receive, send, set_cookie)
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
                if set_cookie is not None:
                    headers.append((b"set-cookie", set_cookie))
                message["headers"] = headers
            await send(message)

        solver_operation = _is_solver_operation(method, path)
        if solver_operation and not await self.solver_gate.acquire():
            response = JSONResponse(
                {"detail": "DEMO_SOLVER_CAPACITY", "code": "DEMO_SOLVER_CAPACITY"},
                status_code=503,
                headers={"Retry-After": "2"},
            )
            await self._send_with_headers(response, scope, receive, send, set_cookie)
            return

        try:
            await self.app(scope, receive, send_with_headers)
        finally:
            if solver_operation:
                await self.solver_gate.release()

    async def _send_with_headers(
        self,
        response: JSONResponse,
        scope: dict[str, Any],
        receive: Any,
        send: Any,
        set_cookie: bytes | None = None,
    ) -> None:
        await response(scope, receive, self._header_sender(send, set_cookie))

    @staticmethod
    def _header_sender(send: Any, set_cookie: bytes | None = None) -> Any:
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
                if set_cookie is not None:
                    headers.append((b"set-cookie", set_cookie))
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


def cors_exposed_headers(*, public_demo: bool) -> list[str]:
    """Expose only the public retry hint needed by cross-origin demo clients."""
    return ["Retry-After"] if public_demo else []
