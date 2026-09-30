"""Privacy-conscious, schema-first resident-request structuring and evidence policy."""

from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ServiceType = Literal["laundry", "daily_necessities", "home_repair", "mobility_support", "unknown"]


class ServiceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    service_type: ServiceType
    requested_period: str | None = Field(
        default=None,
        description="Explicit season only: winter or summer, in lowercase English.",
    )
    frequency_per_month: int | None = Field(default=None, ge=0, le=31)
    preferred_days: list[str] = Field(
        default_factory=list, description="Explicit weekdays in lowercase English."
    )
    excluded_days: list[str] = Field(
        default_factory=list, description="Explicit excluded weekdays in lowercase English."
    )
    constraints: list[str] = Field(
        default_factory=list,
        description="Only use the canonical ID avoid_hospital_visit_day when explicit.",
    )


class StructuredDemand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    requests: list[ServiceRequest] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0, le=1)
    needs_followup_survey: bool = True
    followup_reason: str | None = None
    source_text_was_redacted: bool = False
    method: Literal["gemini_structured_output", "deterministic_fallback"] = "deterministic_fallback"


class EvidenceAssessment(BaseModel):
    observation_count: int = Field(ge=0)
    source_diversity: int = Field(ge=0)
    missingness: float = Field(ge=0, le=1)
    latest_observation_date: date | None = None
    model_confidence: float | None = Field(default=None, ge=0, le=1)
    deterministic_confidence: float = Field(ge=0, le=1)
    combined_confidence: float = Field(ge=0, le=1)
    status: Literal["충분", "주의", "조사 필요"]
    needs_survey: bool
    evidence_reasons: list[str]


PII_PATTERNS = (
    (re.compile(r"(?<!\d)01[016789][- ]?\d{3,4}[- ]?\d{4}(?!\d)"), "[전화번호]"),
    (re.compile(r"(?<!\d)\d{6}[- ]?[1-8]\d{6}(?!\d)"), "[식별번호]"),
    (re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I), "[이메일]"),
    (re.compile(r"([가-힣]{2,4})(?:님|씨)"), "[이름]"),
)


def redact_pii(text: str) -> tuple[str, bool]:
    redacted = text
    changed = False
    for pattern, replacement in PII_PATTERNS:
        redacted, count = pattern.subn(replacement, redacted)
        changed = changed or count > 0
    return redacted, changed


def deterministic_structure(text: str, redacted: bool = False) -> StructuredDemand:
    clean = text.strip()
    if not clean:
        return StructuredDemand(
            followup_reason="기록이 비어 있어 기초조사가 필요합니다.",
            source_text_was_redacted=redacted,
        )

    service_patterns: tuple[tuple[ServiceType, tuple[str, ...]], ...] = (
        ("laundry", ("세탁", "빨래")),
        ("daily_necessities", ("생필품", "장보기", "장 보러", "식료품", "장날")),
        ("home_repair", ("수리", "집수리", "전구", "보일러", "방충망")),
        ("mobility_support", ("이동지원", "병원동행", "병원 동행", "교통지원")),
    )
    service_types = [
        service for service, words in service_patterns if any(word in clean for word in words)
    ]
    day_translation = {
        "월요일": "monday",
        "화요일": "tuesday",
        "수요일": "wednesday",
        "목요일": "thursday",
        "금요일": "friday",
        "토요일": "saturday",
        "일요일": "sunday",
    }
    excluded_days = [
        english
        for korean, english in day_translation.items()
        if korean in clean and any(marker in clean for marker in ("피", "제외", "불가", "말고"))
    ]
    preferred_days = [
        english
        for korean, english in day_translation.items()
        if korean in clean and english not in excluded_days
    ]
    frequency_matches = [int(value) for value in re.findall(r"월\s*(\d+)\s*회", clean)]
    conflict = len(set(frequency_matches)) > 1
    frequency = (
        frequency_matches[0] if len(set(frequency_matches)) == 1 and frequency_matches else None
    )
    period = (
        "winter"
        if any(word in clean for word in ("겨울", "동절기"))
        else "summer"
        if any(word in clean for word in ("여름", "하절기"))
        else None
    )
    constraints: list[str] = []
    if "병원" in clean and any(word in clean for word in ("피", "제외", "불가", "말고")):
        constraints.append("avoid_hospital_visit_day")
    requests = [
        ServiceRequest(
            service_type=service,
            requested_period=period,
            frequency_per_month=frequency,
            preferred_days=preferred_days,
            excluded_days=excluded_days,
            constraints=constraints,
        )
        for service in service_types
    ]
    reason = "서로 다른 빈도 요청이 있어 담당자 확인이 필요합니다." if conflict else None
    if not requests:
        reason = reason or "서비스 수요가 명시되지 않아 추가 확인이 필요합니다."
    return StructuredDemand(
        requests=requests,
        needs_followup_survey=conflict or not requests,
        followup_reason=reason,
        source_text_was_redacted=redacted,
        method="deterministic_fallback",
    )


def _matches_explicit_facts(parsed: StructuredDemand, fallback: StructuredDemand) -> bool:
    """Reject model fields not independently supported by the local parser."""
    if len(parsed.requests) != len(fallback.requests):
        return False
    expected = {item.service_type: item for item in fallback.requests}
    actual = {item.service_type: item for item in parsed.requests}
    if len(expected) != len(fallback.requests) or len(actual) != len(parsed.requests):
        return False
    if actual.keys() != expected.keys():
        return False

    day_aliases = {
        "monday": "monday",
        "월요일": "monday",
        "tuesday": "tuesday",
        "화요일": "tuesday",
        "wednesday": "wednesday",
        "수요일": "wednesday",
        "thursday": "thursday",
        "목요일": "thursday",
        "friday": "friday",
        "금요일": "friday",
        "saturday": "saturday",
        "토요일": "saturday",
        "sunday": "sunday",
        "일요일": "sunday",
    }
    period_aliases = {
        "winter": "winter",
        "겨울": "winter",
        "겨울철": "winter",
        "동절기": "winter",
        "summer": "summer",
        "여름": "summer",
        "여름철": "summer",
        "하절기": "summer",
    }

    def normalized_days(values: list[str]) -> list[str] | None:
        normalized = [day_aliases.get(value.strip().lower()) for value in values]
        return sorted(set(normalized)) if all(normalized) else None

    def normalized_constraints(values: list[str], expected_values: list[str]) -> list[str] | None:
        allowed = set(expected_values)
        result: set[str] = set()
        for value in values:
            clean = value.strip().lower().replace(" ", "")
            if clean in allowed:
                result.add(clean)
                continue
            if (
                "avoid_hospital_visit_day" in allowed
                and "hospital" in clean
                and any(word in clean for word in ("avoid", "skip", "not"))
            ) or (
                "avoid_hospital_visit_day" in allowed
                and "병원" in clean
                and any(word in clean for word in ("피", "제외", "불가"))
            ):
                result.add("avoid_hospital_visit_day")
            else:
                return None
        return sorted(result)

    for service_type, expected_request in expected.items():
        candidate = actual[service_type]
        period = candidate.requested_period
        canonical_period = period_aliases.get(period.strip().lower()) if period else None
        expected_period = expected_request.requested_period
        if period is not None and canonical_period != expected_period:
            return False
        if (
            candidate.frequency_per_month is not None
            and candidate.frequency_per_month != expected_request.frequency_per_month
        ):
            return False
        preferred = normalized_days(candidate.preferred_days)
        excluded = normalized_days(candidate.excluded_days)
        expected_preferred = normalized_days(expected_request.preferred_days)
        expected_excluded = normalized_days(expected_request.excluded_days)
        if (
            preferred is None
            or expected_preferred is None
            or not set(preferred).issubset(expected_preferred)
        ):
            return False
        if (
            excluded is None
            or expected_excluded is None
            or not set(excluded).issubset(expected_excluded)
        ):
            return False
        constraints = normalized_constraints(candidate.constraints, expected_request.constraints)
        if constraints is None or not set(constraints).issubset(expected_request.constraints):
            return False
    return not fallback.needs_followup_survey or parsed.needs_followup_survey


def structure_demand(
    text: str,
    *,
    api_key: str | None = None,
    model: str = "gemini-3.5-flash-lite",
    use_remote: bool = True,
) -> StructuredDemand:
    clean = text.strip()
    if not clean:
        return deterministic_structure(clean)
    redacted_text, was_redacted = redact_pii(clean)
    # Local rule handling is safer for ambiguous or explicitly contradictory notes.
    fallback = deterministic_structure(redacted_text, was_redacted)
    if not use_remote or not api_key or was_redacted or fallback.needs_followup_survey:
        return fallback
    if not fallback.requests:
        return fallback
    try:
        from google import genai

        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=model,
            contents=(
                "Extract only explicitly stated resident service requests "
                "from this anonymized note. "
                "Do not infer frequency, dates, or constraints. "
                "Return season values as winter or summer and weekday values in lowercase English. "
                "Use constraint ID avoid_hospital_visit_day only when explicit; "
                "use service_type=unknown when unclear. "
                "If the note is ambiguous, contradictory, or contains no request, "
                "ask for a follow-up survey.\n\n"
                f"{redacted_text}"
            ),
            config={
                "response_mime_type": "application/json",
                "response_json_schema": StructuredDemand.model_json_schema(),
                "temperature": 0,
                "max_output_tokens": 768,
            },
        )
        parsed = StructuredDemand.model_validate_json(response.text or "")
        if len(parsed.requests) > 8 or not _matches_explicit_facts(parsed, fallback):
            return fallback
        verified = {item.service_type: item for item in fallback.requests}
        for request in parsed.requests:
            local = verified[request.service_type]
            request.requested_period = local.requested_period
            request.preferred_days = local.preferred_days.copy()
            request.excluded_days = local.excluded_days.copy()
            request.constraints = local.constraints.copy()
        parsed.source_text_was_redacted = was_redacted
        parsed.method = "gemini_structured_output"
        return parsed
    except Exception:
        # Provider errors can contain source text, so return the local result silently.
        return fallback


def assess_evidence(
    *,
    observation_count: int,
    source_diversity: int,
    missingness: float,
    latest_observation_date: date | None = None,
    model_confidence: float | None = None,
    today: date | None = None,
) -> EvidenceAssessment:
    now = today or datetime.now(timezone.utc).date()
    count = max(observation_count, 0)
    diversity = max(source_diversity, 0)
    missing = min(max(missingness, 0), 1)
    count_score = min(count / 8, 1) * 0.45
    diversity_score = min(diversity / 3, 1) * 0.2
    if latest_observation_date is None:
        recency_score = 0.0
    else:
        age_days = max((now - latest_observation_date).days, 0)
        recency_score = 0.25 if age_days <= 90 else 0.15 if age_days <= 180 else 0.05
    deterministic = round(
        max(0, min(1, count_score + diversity_score + recency_score + (1 - missing) * 0.1)), 3
    )
    model_value = None if model_confidence is None else min(max(model_confidence, 0), 1)
    combined = (
        round(0.75 * deterministic + 0.25 * model_value, 3)
        if model_value is not None
        else deterministic
    )
    reasons: list[str] = []
    if count < 5:
        status: Literal["충분", "주의", "조사 필요"] = "조사 필요"
        reasons.append("관측 기록이 5건 미만입니다.")
    elif count < 10 or combined < 0.65:
        status = "주의"
        reasons.append("관측 건수, 최근성, 출처 다양성 중 일부가 충분하지 않습니다.")
    else:
        status = "충분"
    if latest_observation_date is None or (now - latest_observation_date).days > 180:
        reasons.append("최근 수요 기록이 없거나 180일보다 오래되었습니다.")
    if diversity < 2:
        reasons.append("요청 출처가 한 가지 이하입니다.")
    if missing > 0.2:
        reasons.append("필수 항목 누락이 20%를 넘습니다.")
    if model_value is not None:
        reasons.append("모델 신뢰도는 보조 신호로만 반영했습니다.")
    return EvidenceAssessment(
        observation_count=count,
        source_diversity=diversity,
        missingness=missing,
        latest_observation_date=latest_observation_date,
        model_confidence=model_value,
        deterministic_confidence=deterministic,
        combined_confidence=combined,
        status=status,
        needs_survey=status == "조사 필요",
        evidence_reasons=reasons,
    )
