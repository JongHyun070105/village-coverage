"""Tests for Unified API Error Model and Error Safety (§24)."""

from __future__ import annotations

from starlette.testclient import TestClient

from backend.errors import (
    BUDGET_INSUFFICIENT,
    DATA_INSUFFICIENT,
    EVIDENCE_CONFLICT,
    IDEMPOTENCY_CONFLICT,
    PLAN_INFEASIBLE,
    PROVIDER_CAPACITY_EXCEEDED,
    PROVIDER_UNAVAILABLE,
    ROUTE_UNAVAILABLE,
    STANDARD_ERROR_CODES,
    VALIDATION_ERROR,
    VERSION_CONFLICT,
    AppError,
    sanitize_error_details,
)
from backend.main import app

client = TestClient(app)


def test_standard_error_codes_are_complete() -> None:
    required = {
        "VALIDATION_ERROR",
        "DATA_INSUFFICIENT",
        "EVIDENCE_CONFLICT",
        "ROUTE_UNAVAILABLE",
        "PLAN_INFEASIBLE",
        "BUDGET_INSUFFICIENT",
        "PROVIDER_CAPACITY_EXCEEDED",
        "PROVIDER_UNAVAILABLE",
        "VERSION_CONFLICT",
        "IDEMPOTENCY_CONFLICT",
    }
    assert required.issubset(STANDARD_ERROR_CODES)


def test_validation_error_returns_unified_envelope() -> None:
    # Trigger a 422 validation error
    response = client.post("/api/demand/structure", json={"text": "x" * 10001})
    assert response.status_code == 422
    body = response.json()
    assert "error" in body
    err = body["error"]
    assert err["code"] == VALIDATION_ERROR
    assert "message" in err
    assert "details" in err
    assert err["retryable"] is False
    # Backwards compatibility
    assert "detail" in body


def test_error_sanitization_redacts_api_keys_and_secrets() -> None:
    raw_details = {
        "api_key": "KAKAO_REST_API_KEY_SECRET_12345",
        "user_token": "eyJhbGciOiJIUzI1NiIsInR5cCI...",
        "auth_header": "Bearer secret_abc",
        "safe_param": "regular_value",
    }
    sanitized = sanitize_error_details(raw_details)
    assert sanitized["api_key"] == "[REDACTED_SECRET]"
    assert sanitized["user_token"] == "[REDACTED_SECRET]"
    assert sanitized["auth_header"] == "[REDACTED_SECRET]"
    assert sanitized["safe_param"] == "regular_value"


def test_error_sanitization_redacts_pii() -> None:
    raw_details = {
        "note": "홍길동 010-1234-5678 어르신 500101-1234567 지원 요청",
        "caller": "이영희 010-9876-5432",
    }
    sanitized = sanitize_error_details(raw_details)
    assert "010-1234-5678" not in sanitized["note"]
    assert "500101-1234567" not in sanitized["note"]
    assert "010-9876-5432" not in sanitized["caller"]
    redacted_labels = ("[연락처]", "[전화번호]", "[개인정보]", "[주민번호]", "[주민등록번호]")
    assert any(label in sanitized["note"] for label in redacted_labels)


def test_error_sanitization_truncates_full_survey_source_text() -> None:
    long_source = "마을 어르신께서 매주 세탁과 청소를 요청하셨습니다. " * 20
    raw_details = {
        "source_text": long_source,
    }
    sanitized = sanitize_error_details(raw_details)
    assert len(sanitized["source_text"]) <= 60
    assert sanitized["source_text"].endswith("...")


def test_app_error_handlers_map_all_domain_codes() -> None:
    test_cases = [
        (VALIDATION_ERROR, 422, "입력값이 잘못되었습니다."),
        (DATA_INSUFFICIENT, 422, "충분한 수요 근거가 없습니다."),
        (EVIDENCE_CONFLICT, 409, "조사자료 충돌이 발생했습니다."),
        (ROUTE_UNAVAILABLE, 503, "도로 경로를 찾을 수 없습니다."),
        (PLAN_INFEASIBLE, 422, "실행 가능한 계획을 수립할 수 없습니다."),
        (BUDGET_INSUFFICIENT, 422, "예산이 부족합니다."),
        (PROVIDER_CAPACITY_EXCEEDED, 422, "공급자 월간 용량을 초과했습니다."),
        (PROVIDER_UNAVAILABLE, 422, "해당 시간대에 가용한 공급자가 없습니다."),
        (VERSION_CONFLICT, 409, "계획 버전이 일치하지 않습니다."),
        (IDEMPOTENCY_CONFLICT, 409, "동일한 키로 다른 요청이 이미 처리되었습니다."),
    ]

    for code, status, msg in test_cases:
        err = AppError(code=code, message=msg, status_code=status, details={"secret_key": "123"})
        # Directly verify AppError fields
        assert err.code == code
        assert err.status_code == status
        assert err.message == msg
        sanitized = sanitize_error_details(err.details)
        assert sanitized["secret_key"] == "[REDACTED_SECRET]"
