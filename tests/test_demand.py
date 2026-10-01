from __future__ import annotations

import json
from datetime import date, timedelta
from types import SimpleNamespace

from backend.demand import (
    ServiceRequest,
    StructuredDemand,
    _matches_explicit_facts,
    assess_evidence,
    deterministic_structure,
    structure_demand,
)


def test_explicit_request_is_schema_valid_and_separated_from_route_planning() -> None:
    result = structure_demand(
        "겨울 세탁 서비스를 월 2회 제공하고 화요일은 피하고 싶음.", use_remote=False
    )
    assert result.requests[0].service_type == "laundry"
    assert result.requests[0].requested_period == "winter"
    assert result.requests[0].frequency_per_month == 2
    assert result.requests[0].excluded_days == ["tuesday"]
    assert result.method == "deterministic_fallback"
    assert result.model_dump()["needs_followup_survey"] is False


def test_multiple_services_are_kept_as_distinct_requests() -> None:
    result = structure_demand("세탁과 생필품을 월 2회 요청함.", use_remote=False)
    assert {request.service_type for request in result.requests} == {
        "laundry",
        "daily_necessities",
    }
    assert all(request.frequency_per_month == 2 for request in result.requests)


def test_empty_and_non_request_notes_require_followup() -> None:
    empty = structure_demand("  ", use_remote=False)
    meeting = structure_demand("다음 회의는 다음 달 첫째 주에 열기로 함.", use_remote=False)
    assert empty.requests == [] and empty.needs_followup_survey
    assert meeting.requests == [] and meeting.needs_followup_survey


def test_contradictory_frequency_does_not_get_guessed() -> None:
    result = structure_demand("세탁 월 2회, 다른 의견은 월 4회라고 함.", use_remote=False)
    assert len(result.requests) == 1
    assert result.requests[0].frequency_per_month is None
    assert result.needs_followup_survey
    assert "빈도" in (result.followup_reason or "")


def test_pii_is_redacted_and_never_sent_to_remote_provider() -> None:
    # A supplied API key proves this path still falls back locally when redaction occurred.
    result = structure_demand(
        "김영희님 010-1234-5678은 겨울에 세탁을 월 2회 원함.",
        api_key="test-only",
        use_remote=True,
    )
    assert result.source_text_was_redacted
    assert result.method == "deterministic_fallback"
    assert result.requests[0].service_type == "laundry"
    assert result.requests[0].frequency_per_month == 2


def test_model_output_must_match_locally_supported_facts() -> None:
    fallback = deterministic_structure(
        "겨울 세탁 서비스를 월 2회 요청하고 병원 가는 화요일은 피하고 싶음."
    )
    supported = StructuredDemand(
        requests=[
            ServiceRequest(
                service_type="laundry",
                requested_period="겨울",
                frequency_per_month=2,
                excluded_days=["화요일"],
                constraints=["병원 가는 화요일은 피했으면 좋겠음"],
            )
        ],
        confidence=0.94,
        needs_followup_survey=False,
    )
    invented_frequency = StructuredDemand(
        requests=[ServiceRequest(service_type="laundry", frequency_per_month=12)],
        confidence=0.99,
        needs_followup_survey=False,
    )
    invented_service = StructuredDemand(
        requests=[ServiceRequest(service_type="home_repair")],
        confidence=0.99,
        needs_followup_survey=False,
    )
    assert _matches_explicit_facts(supported, fallback)
    assert not _matches_explicit_facts(invented_frequency, fallback)
    assert not _matches_explicit_facts(invented_service, fallback)


def test_remote_output_uses_json_schema_and_returns_canonical_verified_facts(monkeypatch) -> None:
    from google import genai

    payload = {
        "requests": [
            {
                "service_type": "laundry",
                "requested_period": "겨울",
                "frequency_per_month": 2,
                "preferred_days": [],
                "excluded_days": [],
                "constraints": ["병원 가는 화요일은 피했으면 좋겠음"],
            }
        ],
        "confidence": 0.92,
        "needs_followup_survey": False,
        "followup_reason": None,
        "source_text_was_redacted": False,
        "method": "deterministic_fallback",
    }
    captured = {}

    class FakeModels:
        def generate_content(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(text=json.dumps(payload, ensure_ascii=False))

    class FakeClient:
        def __init__(self, *, api_key):
            assert api_key == "test-only"
            self.models = FakeModels()

    monkeypatch.setattr(genai, "Client", FakeClient)
    result = structure_demand(
        "겨울 세탁 서비스를 월 2회 제공하고 병원 가는 화요일은 피하고 싶음.",
        api_key="test-only",
        use_remote=True,
    )
    assert result.method == "gemini_structured_output"
    assert result.confidence == 0.92
    assert result.requests[0].requested_period == "winter"
    assert result.requests[0].excluded_days == ["tuesday"]
    assert result.requests[0].constraints == ["avoid_hospital_visit_day"]
    assert "response_json_schema" in captured["config"]
    assert "response_schema" not in captured["config"]


def test_deterministic_evidence_keeps_low_data_at_survey_required() -> None:
    result = assess_evidence(
        observation_count=2,
        source_diversity=1,
        missingness=0,
        latest_observation_date=date.today(),
        model_confidence=1.0,
    )
    assert result.status == "조사 필요"
    assert result.needs_survey
    assert result.combined_confidence < 1.0


def test_stale_or_missing_evidence_is_not_marked_sufficient() -> None:
    result = assess_evidence(
        observation_count=12,
        source_diversity=1,
        missingness=0.3,
        latest_observation_date=date.today() - timedelta(days=300),
    )
    assert result.status == "주의"
    assert any("180일" in reason for reason in result.evidence_reasons)


def test_recent_baseline_survey_moves_low_data_to_limited_planning() -> None:
    result = assess_evidence(
        observation_count=2,
        survey_count=1,
        source_diversity=2,
        missingness=0.2,
        latest_observation_date=date.today(),
    )

    assert result.status == "제한적 계획 가능"
    assert result.limited_planning_allowed
    assert result.needs_survey
    assert result.survey_count == 1
    assert result.observation_count == 2
