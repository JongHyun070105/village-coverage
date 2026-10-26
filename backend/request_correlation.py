"""Request correlation for diagnosing long-running public planning requests."""

from __future__ import annotations

import logging
import time
from uuid import UUID, uuid4

from starlette.types import ASGIApp, Message, Receive, Scope, Send

_REQUEST_ID_HEADER = b"x-request-id"
_OBSERVED_POST_PATHS = {"/api/schedules", "/api/minimum-coverage/analysis"}
_LOGGER = logging.getLogger("uvicorn.error.backend.request")
_LOGGER.setLevel(logging.INFO)


def _validated_request_id(headers: list[tuple[bytes, bytes]]) -> str:
    raw_value = next(
        (value for name, value in headers if name.lower() == _REQUEST_ID_HEADER),
        b"",
    )
    try:
        value = raw_value.decode("ascii")
        parsed = str(UUID(value))
    except (UnicodeDecodeError, ValueError):
        return str(uuid4())
    return parsed if value.lower() == parsed else str(uuid4())


class RequestCorrelationMiddleware:
    """Echo a UUID request ID and log completion for the solver write endpoints."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = _validated_request_id(scope.get("headers", []))
        scope.setdefault("state", {})["request_id"] = request_id
        started_at = time.perf_counter()
        status_code: int | None = None
        observe = (
            scope.get("method") == "POST"
            and scope.get("path") in _OBSERVED_POST_PATHS
        )

        async def send_with_request_id(message: Message) -> None:
            nonlocal status_code
            outgoing = message
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
                headers = [
                    (name, value)
                    for name, value in message.get("headers", [])
                    if name.lower() != _REQUEST_ID_HEADER
                ]
                headers.append((_REQUEST_ID_HEADER, request_id.encode("ascii")))
                outgoing = {**message, "headers": headers}

            try:
                await send(outgoing)
            except Exception as exc:
                if observe:
                    elapsed_ms = (time.perf_counter() - started_at) * 1000
                    _LOGGER.info(
                        "api_asgi_send_error request_id=%s method=POST path=%s "
                        "status_code=%s stage=%s error_type=%s duration_ms=%.1f",
                        request_id,
                        scope["path"],
                        status_code if status_code is not None else "unknown",
                        message["type"],
                        type(exc).__name__,
                        elapsed_ms,
                    )
                raise
            if observe and message["type"] == "http.response.body" and not message.get(
                "more_body", False
            ):
                elapsed_ms = (time.perf_counter() - started_at) * 1000
                _LOGGER.info(
                    "api_asgi_response_complete request_id=%s method=POST path=%s "
                    "status_code=%s duration_ms=%.1f",
                    request_id,
                    scope["path"],
                    status_code if status_code is not None else "unknown",
                    elapsed_ms,
                )

        await self.app(scope, receive, send_with_request_id)
