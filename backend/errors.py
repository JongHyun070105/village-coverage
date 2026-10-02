"""Unified API Error Model & Sanitization for VillageCoverage."""

from __future__ import annotations

import re
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from starlette.responses import JSONResponse

from backend.demand import redact_pii

# Minimum required error codes (§24)
VALIDATION_ERROR = "VALIDATION_ERROR"
DATA_INSUFFICIENT = "DATA_INSUFFICIENT"
EVIDENCE_CONFLICT = "EVIDENCE_CONFLICT"
ROUTE_UNAVAILABLE = "ROUTE_UNAVAILABLE"
PLAN_INFEASIBLE = "PLAN_INFEASIBLE"
BUDGET_INSUFFICIENT = "BUDGET_INSUFFICIENT"
PROVIDER_CAPACITY_EXCEEDED = "PROVIDER_CAPACITY_EXCEEDED"
PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
VERSION_CONFLICT = "VERSION_CONFLICT"
IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"

STANDARD_ERROR_CODES = {
    VALIDATION_ERROR,
    DATA_INSUFFICIENT,
    EVIDENCE_CONFLICT,
    ROUTE_UNAVAILABLE,
    PLAN_INFEASIBLE,
    BUDGET_INSUFFICIENT,
    PROVIDER_CAPACITY_EXCEEDED,
    PROVIDER_UNAVAILABLE,
    VERSION_CONFLICT,
    IDEMPOTENCY_CONFLICT,
}

_SECRET_KEY_PATTERN = re.compile(
    r"(api[_-]?key|secret|token|auth|password|credential|kakao_key)", re.IGNORECASE
)
_FULL_TEXT_KEY_PATTERN = re.compile(
    r"(source_text|raw_text|full_text|survey_text|free_text)", re.IGNORECASE
)


def sanitize_error_details(data: Any, max_str_length: int = 120) -> Any:
    """Sanitize error details to prevent leakage of API keys, PII,
    and full survey source texts (§24).
    """
    if isinstance(data, dict):
        sanitized: dict[str, Any] = {}
        for key, value in data.items():
            key_str = str(key)
            if _SECRET_KEY_PATTERN.search(key_str):
                sanitized[key_str] = "[REDACTED_SECRET]"
            elif _FULL_TEXT_KEY_PATTERN.search(key_str):
                # Truncate and redact any PII in raw survey text
                if isinstance(value, str):
                    redacted, _ = redact_pii(value)
                    sanitized[key_str] = (
                        redacted[:50] + "..." if len(redacted) > 50 else redacted
                    )
                else:
                    sanitized[key_str] = "[REDACTED_SOURCE_TEXT]"
            else:
                sanitized[key_str] = sanitize_error_details(value, max_str_length=max_str_length)
        return sanitized

    if isinstance(data, (list, tuple)):
        return [sanitize_error_details(item, max_str_length=max_str_length) for item in data]

    if isinstance(data, str):
        # Mask PII (phone, resident registration number, etc.)
        redacted, _ = redact_pii(data)
        # Also redact any apparent authorization tokens or long hex/key strings
        if len(redacted) > max_str_length:
            return redacted[:max_str_length] + "..."
        return redacted

    return data


class AppError(Exception):
    """Domain-specific structured application error conforming to §24 API error envelope."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 400,
        details: dict[str, Any] | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        self.retryable = retryable


def _infer_error_code(status_code: int, detail: Any) -> str:
    """Infer the most specific §24 error code from status code and message."""
    text = str(detail).lower() if detail is not None else ""
    if "conflict" in text or "충돌" in text:
        return EVIDENCE_CONFLICT
    if "용량" in text or "capacity" in text:
        return PROVIDER_CAPACITY_EXCEEDED
    if "예산" in text or "budget" in text:
        return BUDGET_INSUFFICIENT
    if "도로" in text or "route" in text or "road" in text or "matrix" in text:
        return ROUTE_UNAVAILABLE
    if "공급자" in text and ("없음" in text or "불가" in text or "unavailable" in text):
        return PROVIDER_UNAVAILABLE
    if "idempotent" in text or "중복 요청" in text:
        return IDEMPOTENCY_CONFLICT
    if "version" in text or "버전" in text:
        return VERSION_CONFLICT
    if "실행 가능" in text or "infeasible" in text:
        return PLAN_INFEASIBLE
    if "데이터" in text or "수요" in text or "evidence" in text or "insufficient" in text:
        return DATA_INSUFFICIENT

    if status_code == 422:
        return VALIDATION_ERROR
    if status_code == 409:
        return VERSION_CONFLICT
    if status_code == 404:
        return "NOT_FOUND"
    if status_code == 413:
        return "PAYLOAD_TOO_LARGE"
    if status_code == 503:
        return "SERVICE_UNAVAILABLE"
    return f"HTTP_{status_code}"


def register_error_handlers(app: FastAPI) -> None:
    """Register FastAPI exception handlers for AppError, RequestValidationError,
    and HTTPException.
    """

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        sanitized = sanitize_error_details(exc.details)
        payload = {
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": sanitized,
                "retryable": exc.retryable,
            },
            "detail": exc.message,
        }
        return JSONResponse(status_code=exc.status_code, content=payload)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        sanitized_errors = [
            {
                "type": sanitize_error_details(error.get("type", "validation_error")),
                "loc": sanitize_error_details(error.get("loc", [])),
                "msg": sanitize_error_details(error.get("msg", "입력값 검증 실패")),
            }
            for error in exc.errors()
        ]
        first_error_msg = (
            str(sanitized_errors[0]["msg"])
            if sanitized_errors
            else "입력값 검증에 실패했습니다."
        )
        payload = {
            "error": {
                "code": VALIDATION_ERROR,
                "message": f"입력값 검증 오류: {first_error_msg}",
                "details": {"validation_errors": sanitized_errors},
                "retryable": False,
            },
            # Preserve FastAPI's top-level compatibility field without echoing raw
            # request input or Pydantic context objects (which may be non-JSON values).
            "detail": sanitized_errors,
        }
        return JSONResponse(status_code=422, content=payload)

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        explicit_code = getattr(exc, "error_code", None)
        code = explicit_code or _infer_error_code(exc.status_code, exc.detail)
        message = (
            str(exc.detail) if isinstance(exc.detail, str) else "요청 처리 중 오류가 발생했습니다."
        )
        details = sanitize_error_details(getattr(exc, "details", {}))
        retryable = getattr(exc, "retryable", False)
        payload = {
            "error": {
                "code": code,
                "message": message,
                "details": details,
                "retryable": retryable,
            },
            "detail": exc.detail,
        }
        return JSONResponse(status_code=exc.status_code, content=payload)
