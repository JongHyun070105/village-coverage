#!/usr/bin/env python3
"""Bounded, KST-windowed GET health checks for the existing Render demo."""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Callable
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
WINDOW_START_MINUTE = 8 * 60 + 55  # scheduled 08:55 pre-warm
WINDOW_END_MINUTE = 18 * 60
LAST_SCHEDULED_PING_MINUTE = 17 * 60 + 45
IDLE_SHUTDOWN_MINUTES = 15
MAX_ATTEMPTS = 16
REQUEST_TIMEOUT_SECONDS = 10
ENDPOINT_RECOVERY_BUDGET_SECONDS = 4 * 60
MAX_RUN_SECONDS = 8 * 60
RETRY_BASE_SECONDS = 5
RETRY_MAX_SECONDS = 20
MAX_RETRY_AFTER_SECONDS = 3 * 60
MAX_BODY_BYTES = 4096
USER_AGENT = "villagecoverage-render-free-keepalive/1"
SCHEDULE_CRONS = frozenset(
    {
        "55 23 * * *",
        "5,15,25,35,45,55 0-7 * * *",
        "5,15,25,35,45 8 * * *",
    }
)


@dataclass(frozen=True)
class Endpoint:
    name: str
    url: str
    kind: str


WEB = Endpoint("web", "https://villagecoverage-public-demo-web.onrender.com/", "html")
API = Endpoint("api", "https://villagecoverage-public-demo-api.onrender.com/health", "health")
INTEGRATED = Endpoint(
    "integrated-health",
    "https://villagecoverage-public-demo-web.onrender.com/api/health",
    "health",
)
ENDPOINTS = (WEB, API, INTEGRATED)
ALLOWED_URLS = frozenset(endpoint.url for endpoint in ENDPOINTS)


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Return 3xx responses to the caller; never follow an external redirect."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


def current_kst(now: datetime | None = None) -> datetime:
    instant = now if now is not None else datetime.now(timezone.utc)
    if instant.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return instant.astimezone(KST)


def in_window(now: datetime | None = None) -> bool:
    local = current_kst(now)
    minute = local.hour * 60 + local.minute
    return WINDOW_START_MINUTE <= minute < WINDOW_END_MINUTE


def seconds_until_window_end(now: datetime | None = None) -> float:
    local = current_kst(now)
    end = local.replace(hour=18, minute=0, second=0, microsecond=0)
    return max(0.0, (end - local).total_seconds())


def estimate_scheduled_instance_hours(days: int) -> float:
    """Estimate one service's nominal monthly run time; excludes all other usage."""
    if days < 0:
        raise ValueError("days must be non-negative")
    daily_minutes = LAST_SCHEDULED_PING_MINUTE + IDLE_SHUTDOWN_MINUTES - WINDOW_START_MINUTE
    return daily_minutes * days / 60


def retry_after_seconds(value: str | None, now: datetime | None = None) -> int | None:
    if not value:
        return None
    try:
        seconds = int(value.strip())
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(value)
            if retry_at.tzinfo is None:
                retry_at = retry_at.replace(tzinfo=timezone.utc)
            reference = now if now is not None else datetime.now(timezone.utc)
            if reference.tzinfo is None:
                raise ValueError("now must be timezone-aware")
            seconds = int((retry_at - reference.astimezone(timezone.utc)).total_seconds())
        except (TypeError, ValueError, OverflowError):
            return None
    return max(0, seconds)


def _read_bounded(response) -> bytes:  # type: ignore[no-untyped-def]
    try:
        return response.read(MAX_BODY_BYTES)
    finally:
        close = getattr(response, "close", None)
        if close:
            close()


def validate_response(endpoint: Endpoint, status: int, headers, body: bytes) -> tuple[bool, str]:  # type: ignore[no-untyped-def]
    if status != 200:
        return False, "http_status"
    content_type = str(headers.get("Content-Type", "")).lower()
    if endpoint.kind == "html":
        if "text/html" not in content_type and "application/xhtml+xml" not in content_type:
            return False, "unexpected_content_type"
        if b"<html" not in body.lower() or b"villagecoverage" not in body.lower():
            return False, "unexpected_body"
        return True, "ok"
    if "json" not in content_type:
        return False, "unexpected_content_type"
    try:
        decoded = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return False, "invalid_json"
    if not isinstance(decoded, dict) or decoded.get("status") != "ok":
        return False, "unhealthy_json"
    return True, "ok"


def _retryable_status(status: int) -> bool:
    return status == 429 or 500 <= status <= 599


def _retry_delay(attempt: int) -> int:
    return min(RETRY_BASE_SECONDS * (2 ** (attempt - 1)), RETRY_MAX_SECONDS)


def probe(
    endpoint: Endpoint,
    *,
    now_fn: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    sleep_fn: Callable[[float], None] = time.sleep,
    monotonic_fn: Callable[[], float] = time.monotonic,
    emit: Callable[[str], None] = print,
    opener=None,
    run_deadline: float | None = None,
) -> tuple[bool, bool, bool]:  # type: ignore[no-untyped-def]
    """Return (healthy, attempted_recovery, skipped_for_time); endpoint is isolated."""
    if endpoint.url not in ALLOWED_URLS:
        emit(f"service={endpoint.name} outcome=blocked_url")
        return False, False, False
    recovery = False
    if opener is None:
        opener = urllib.request.build_opener(NoRedirectHandler())
    endpoint_started = monotonic_fn()
    endpoint_deadline = endpoint_started + ENDPOINT_RECOVERY_BUDGET_SECONDS
    if run_deadline is not None:
        endpoint_deadline = min(endpoint_deadline, run_deadline)
    last_status: int | None = None
    last_failure = "not_started"
    attempts = 0

    def finish(healthy: bool, outcome: str) -> tuple[bool, bool, bool]:
        elapsed_ms = int((monotonic_fn() - endpoint_started) * 1000)
        status_text = "none" if last_status is None else str(last_status)
        emit(
            f"service={endpoint.name} outcome={outcome} attempts={attempts} "
            f"status={status_text} failure={last_failure} elapsed_ms={elapsed_ms}"
        )
        return healthy, recovery, False

    for attempt in range(1, MAX_ATTEMPTS + 1):
        if not in_window(now_fn()):
            emit(f"service={endpoint.name} outcome=skipped_window")
            return False, recovery, True
        remaining = endpoint_deadline - monotonic_fn()
        if remaining <= 0:
            last_failure = "endpoint_or_run_budget_exhausted"
            return finish(False, "retry_budget_exhausted")
        request = urllib.request.Request(
            endpoint.url,
            method="GET",
            headers={"Accept": "text/html, application/json", "User-Agent": USER_AGENT},
        )
        attempts = attempt
        started = monotonic_fn()
        status: int | None = None
        retry_after: str | None = None
        failure = "network_error"
        try:
            response = opener.open(request, timeout=min(REQUEST_TIMEOUT_SECONDS, remaining))
            status = response.getcode()
            headers = response.headers
            retry_after = headers.get("Retry-After")
            body = _read_bounded(response)
            healthy, failure = validate_response(endpoint, status, headers, body)
            elapsed_ms = int((monotonic_fn() - started) * 1000)
            last_status = status
            last_failure = failure
            attempt_outcome = "ok" if healthy else failure
            if not healthy and _retryable_status(status):
                attempt_outcome = "retryable"
            emit(
                f"service={endpoint.name} attempt={attempt} status={status} "
                f"elapsed_ms={elapsed_ms} failure={failure} "
                f"outcome={attempt_outcome}"
            )
            if monotonic_fn() >= endpoint_deadline:
                last_failure = "request_completed_after_budget"
                return finish(False, "retry_budget_exhausted")
            if healthy:
                return finish(True, "recovered" if recovery else "healthy")
            transient_contract = failure in {
                "unexpected_content_type",
                "unexpected_body",
                "invalid_json",
                "unhealthy_json",
            }
            if not (_retryable_status(status) or transient_contract) or attempt == MAX_ATTEMPTS:
                return finish(False, "failed")
        except urllib.error.HTTPError as error:
            status = error.code
            retry_after = error.headers.get("Retry-After") if error.headers else None
            error.close()
            failure = "http_status"
            elapsed_ms = int((monotonic_fn() - started) * 1000)
            last_status = status
            last_failure = failure
            attempt_outcome = "retryable" if _retryable_status(status) else "failed"
            emit(
                f"service={endpoint.name} attempt={attempt} status={status} "
                f"elapsed_ms={elapsed_ms} failure={failure} outcome={attempt_outcome}"
            )
            if monotonic_fn() >= endpoint_deadline:
                last_failure = "request_completed_after_budget"
                return finish(False, "retry_budget_exhausted")
            if not _retryable_status(status) or attempt == MAX_ATTEMPTS:
                return finish(False, "failed")
        except (TimeoutError, OSError, urllib.error.URLError) as error:
            # Log only the error type; exception messages may contain URLs or proxy details.
            failure = type(error).__name__
            elapsed_ms = int((monotonic_fn() - started) * 1000)
            last_status = None
            last_failure = failure
            emit(
                f"service={endpoint.name} attempt={attempt} status=none "
                f"elapsed_ms={elapsed_ms} failure={failure} outcome=retryable"
            )
            if monotonic_fn() >= endpoint_deadline:
                last_failure = "request_completed_after_budget"
                return finish(False, "retry_budget_exhausted")
            if attempt == MAX_ATTEMPTS:
                return finish(False, "failed")
        recovery = True
        retry_after_delay = retry_after_seconds(retry_after, now_fn())
        if retry_after_delay is not None and retry_after_delay > MAX_RETRY_AFTER_SECONDS:
            last_failure = "retry_after_exceeds_bound"
            emit(
                f"service={endpoint.name} outcome=retry_after_exceeds_bound "
                f"status={last_status if last_status is not None else 'none'} "
                f"retry_after_s={retry_after_delay} max_retry_after_s={MAX_RETRY_AFTER_SECONDS}"
            )
            return finish(False, "failed")
        delay = (
            _retry_delay(attempt)
            if retry_after_delay is None
            else max(_retry_delay(attempt), retry_after_delay)
        )
        available_budget = endpoint_deadline - monotonic_fn()
        available_window = seconds_until_window_end(now_fn())
        if delay >= available_window:
            last_failure = "retry_would_cross_1800_kst"
            emit(
                f"service={endpoint.name} outcome=skipped_window_before_retry "
                f"status={last_status if last_status is not None else 'none'} retry_delay_s={delay}"
            )
            return False, recovery, True
        if delay >= available_budget:
            last_failure = "retry_delay_exceeds_remaining_budget"
            emit(
                f"service={endpoint.name} outcome=retry_budget_exhausted "
                f"status={last_status if last_status is not None else 'none'} "
                f"retry_delay_s={delay} remaining_budget_s={max(0, int(available_budget))}"
            )
            return finish(False, "retry_budget_exhausted")
        emit(
            f"service={endpoint.name} attempt={attempt} retry_in_s={delay} "
            f"retry_after={'true' if retry_after_delay is not None else 'false'}"
        )
        sleep_fn(delay)
    last_failure = "maximum_attempts_exhausted"
    return finish(False, "failed")


def run(
    *,
    integrated: bool = False,
    scheduled_cron: str | None = None,
    now_fn: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    sleep_fn: Callable[[float], None] = time.sleep,
    monotonic_fn: Callable[[], float] = time.monotonic,
    emit: Callable[[str], None] = print,
    opener_factory: Callable[[], object] | None = None,
) -> int:
    run_started = monotonic_fn()
    run_deadline = run_started + MAX_RUN_SECONDS
    now = now_fn()
    if scheduled_cron is not None:
        if scheduled_cron not in SCHEDULE_CRONS:
            emit("outcome=invalid_schedule")
            return 2
        # GitHub supplies the cron expression, not the occurrence timestamp.
        # Validate the expression without reporting the latest slot as event delay.
        emit("outcome=schedule_cron_validated")
    if not in_window(now):
        emit(f"outcome=skipped_window kst={current_kst(now_fn()).isoformat(timespec='minutes')}")
        return 0
    factory = opener_factory or (lambda: urllib.request.build_opener(NoRedirectHandler()))
    failed = False
    recovery = False
    for endpoint in (WEB, API):
        if not in_window(now_fn()):
            emit(f"service={endpoint.name} outcome=skipped_window_remaining")
            failed = True
            break
        if monotonic_fn() >= run_deadline:
            emit(f"service={endpoint.name} outcome=total_budget_exhausted")
            failed = True
            break
        healthy, had_recovery, skipped = probe(
            endpoint,
            now_fn=now_fn,
            sleep_fn=sleep_fn,
            monotonic_fn=monotonic_fn,
            emit=emit,
            opener=factory(),
            run_deadline=run_deadline,
        )
        if skipped:
            failed = True
            recovery = recovery or had_recovery
            break
        failed = failed or not healthy
        recovery = recovery or had_recovery or not healthy
    if (integrated or recovery) and in_window(now_fn()):
        healthy, _, skipped = probe(
            INTEGRATED,
            now_fn=now_fn,
            sleep_fn=sleep_fn,
            monotonic_fn=monotonic_fn,
            emit=emit,
            opener=factory(),
            run_deadline=run_deadline,
        )
        failed = failed or not healthy or skipped
    elif integrated or recovery:
        emit("service=integrated-health outcome=skipped_window")
        failed = True
    elapsed_ms = int((monotonic_fn() - run_started) * 1000)
    emit(f"outcome={'failed' if failed else 'complete'} elapsed_ms={elapsed_ms}")
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--integrated",
        action="store_true",
        help="also check the Web /api/health rewrite during scheduled pre-warm",
    )
    parser.add_argument(
        "--scheduled-cron",
        help="known GitHub schedule expression; actual occurrence time is not supplied",
    )
    arguments = parser.parse_args(argv)
    return run(integrated=arguments.integrated, scheduled_cron=arguments.scheduled_cron)


if __name__ == "__main__":
    sys.exit(main())
