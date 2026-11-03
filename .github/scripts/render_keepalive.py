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
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Callable
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
WINDOW_START_MINUTE = 8 * 60 + 55  # scheduled 08:55 pre-warm
WINDOW_END_MINUTE = 18 * 60
LAST_SCHEDULED_PING_MINUTE = 17 * 60 + 45
IDLE_SHUTDOWN_MINUTES = 15
MAX_ATTEMPTS = 3
REQUEST_TIMEOUT_SECONDS = 75
MAX_RETRY_AFTER_SECONDS = 30
MAX_SCHEDULE_DELAY_SECONDS = 5 * 60
MAX_BODY_BYTES = 4096
USER_AGENT = "villagecoverage-render-free-keepalive/1"
SCHEDULE_RULES = {
    "55 23 * * *": ((23,), (55,)),
    "5,15,25,35,45,55 0-7 * * *": (tuple(range(8)), (5, 15, 25, 35, 45, 55)),
    "5,15,25,35,45 8 * * *": ((8,), (5, 15, 25, 35, 45)),
}


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


def scheduled_delay_seconds(cron: str, now: datetime) -> int:
    """Return seconds since the most recent expected UTC firing for a known cron."""
    if cron not in SCHEDULE_RULES:
        raise ValueError("unknown scheduled cron")
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    instant = now.astimezone(timezone.utc)
    hours, minutes = SCHEDULE_RULES[cron]
    due_instants = []
    for day_offset in (1, 0):
        date = instant.date() - timedelta(days=day_offset)
        for hour in hours:
            for minute in minutes:
                due = datetime(date.year, date.month, date.day, hour, minute, tzinfo=timezone.utc)
                if due <= instant:
                    due_instants.append(due)
    if not due_instants:
        raise ValueError("no prior scheduled instant")
    return int((instant - max(due_instants)).total_seconds())


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


def probe(
    endpoint: Endpoint,
    *,
    now_fn: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    sleep_fn: Callable[[float], None] = time.sleep,
    emit: Callable[[str], None] = print,
    opener=None,
) -> tuple[bool, bool, bool]:  # type: ignore[no-untyped-def]
    """Return (healthy, attempted_recovery, skipped_for_time); endpoint is isolated."""
    if endpoint.url not in ALLOWED_URLS:
        emit(f"service={endpoint.name} outcome=blocked_url")
        return False, False, False
    recovery = False
    if opener is None:
        opener = urllib.request.build_opener(NoRedirectHandler())
    for attempt in range(1, MAX_ATTEMPTS + 1):
        if not in_window(now_fn()):
            emit(f"service={endpoint.name} outcome=skipped_window")
            return False, recovery, True
        request = urllib.request.Request(
            endpoint.url,
            method="GET",
            headers={"Accept": "text/html, application/json", "User-Agent": USER_AGENT},
        )
        started = time.monotonic()
        status: int | None = None
        retry_after: str | None = None
        failure = "network_error"
        try:
            response = opener.open(request, timeout=REQUEST_TIMEOUT_SECONDS)
            status = response.getcode()
            headers = response.headers
            retry_after = headers.get("Retry-After")
            body = _read_bounded(response)
            healthy, failure = validate_response(endpoint, status, headers, body)
            elapsed_ms = int((time.monotonic() - started) * 1000)
            emit(
                f"service={endpoint.name} attempt={attempt} status={status} "
                f"elapsed_ms={elapsed_ms} outcome={'ok' if healthy else failure}"
            )
            if healthy:
                return True, recovery, False
            transient_contract = failure in {
                "unexpected_content_type",
                "unexpected_body",
                "invalid_json",
                "unhealthy_json",
            }
            if not (_retryable_status(status) or transient_contract) or attempt == MAX_ATTEMPTS:
                return False, recovery, False
        except urllib.error.HTTPError as error:
            status = error.code
            retry_after = error.headers.get("Retry-After") if error.headers else None
            error.close()
            failure = "http_status"
            elapsed_ms = int((time.monotonic() - started) * 1000)
            emit(
                f"service={endpoint.name} attempt={attempt} status={status} "
                f"elapsed_ms={elapsed_ms} outcome={failure}"
            )
            if not _retryable_status(status) or attempt == MAX_ATTEMPTS:
                return False, recovery, False
        except (TimeoutError, OSError, urllib.error.URLError) as error:
            # Log only the error type; exception messages may contain URLs or proxy details.
            failure = type(error).__name__
            elapsed_ms = int((time.monotonic() - started) * 1000)
            emit(
                f"service={endpoint.name} attempt={attempt} status=none "
                f"elapsed_ms={elapsed_ms} outcome={failure}"
            )
            if attempt == MAX_ATTEMPTS:
                return False, recovery, False
        recovery = True
        delay = retry_after_seconds(retry_after, now_fn())
        if delay is not None and delay > MAX_RETRY_AFTER_SECONDS:
            emit(f"service={endpoint.name} outcome=retry_after_exceeds_bound")
            return False, recovery, False
        if delay is None:
            delay = min(2 ** (attempt - 1), 8)
        if attempt < MAX_ATTEMPTS:
            if not in_window(now_fn()):
                emit(f"service={endpoint.name} outcome=skipped_window_before_retry")
                return False, recovery, True
            sleep_fn(delay)
    return False, recovery, False


def run(
    *,
    integrated: bool = False,
    scheduled_cron: str | None = None,
    now_fn: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    sleep_fn: Callable[[float], None] = time.sleep,
    emit: Callable[[str], None] = print,
    opener_factory: Callable[[], object] | None = None,
) -> int:
    now = now_fn()
    if scheduled_cron is not None:
        try:
            delay = scheduled_delay_seconds(scheduled_cron, now)
        except ValueError:
            emit("outcome=invalid_schedule")
            return 2
        emit(f"outcome=schedule_delay delay_seconds={delay}")
        if delay > MAX_SCHEDULE_DELAY_SECONDS:
            emit(f"outcome=skipped_late_schedule delay_seconds={delay}")
            return 0
    if not in_window(now):
        emit(f"outcome=skipped_window kst={current_kst(now_fn()).isoformat(timespec='minutes')}")
        return 0
    factory = opener_factory or (lambda: urllib.request.build_opener(NoRedirectHandler()))
    failed = False
    recovery = False
    for endpoint in (WEB, API):
        if not in_window(now_fn()):
            emit(f"service={endpoint.name} outcome=skipped_window_remaining")
            break
        healthy, had_recovery, skipped = probe(
            endpoint, now_fn=now_fn, sleep_fn=sleep_fn, emit=emit, opener=factory()
        )
        if skipped:
            failed = failed or had_recovery
            recovery = recovery or had_recovery
            break
        failed = failed or not healthy
        recovery = recovery or had_recovery or not healthy
    if (integrated or recovery) and in_window(now_fn()):
        healthy, _, skipped = probe(
            INTEGRATED, now_fn=now_fn, sleep_fn=sleep_fn, emit=emit, opener=factory()
        )
        if not skipped:
            failed = failed or not healthy
    elif integrated or recovery:
        emit("service=integrated-health outcome=skipped_window")
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
        help="GitHub schedule expression; events more than five minutes late are skipped",
    )
    arguments = parser.parse_args(argv)
    return run(integrated=arguments.integrated, scheduled_cron=arguments.scheduled_cron)


if __name__ == "__main__":
    sys.exit(main())
