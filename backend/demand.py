"""Privacy-conscious, schema-first resident-request structuring and evidence policy."""

from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.service_registry import SERVICE_REGISTRY

ServiceType = Literal[
    "laundry",
    "daily_necessities",
    "home_repair",
    "mobility_support",
    "medical_service",
    "legal_service",
    "unknown",
]


class ServiceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    service_type: ServiceType
    requested_period: str | None = Field(
        default=None,
        max_length=80,
        description="Explicit season or calendar period; never calculate relative periods.",
    )
    frequency_per_month: int | None = Field(default=None, ge=0, le=31)
    desired_date: str | None = Field(
        default=None,
        description="Explicit date only: YYYY-MM-DD with a stated year, otherwise MM-DD.",
    )
    desired_time: str | None = Field(
        default=None, description="Explicit local time normalized to HH:MM."
    )
    recurring_pattern: Literal["weekly", "monthly", "seasonal", "one_time"] | None = None
    urgency: Literal["urgent"] | None = None
    urgency_evidence: str | None = Field(
        default=None, description="Exact urgency phrase from the note."
    )
    preferred_days: list[str] = Field(
        default_factory=list, max_length=7, description="Explicit weekdays in lowercase English."
    )
    excluded_days: list[str] = Field(
        default_factory=list,
        max_length=7,
        description="Explicit excluded weekdays in lowercase English.",
    )
    constraints: list[Annotated[str, Field(max_length=300)]] = Field(
        default_factory=list,
        max_length=10,
        description=(
            "Use the canonical ID avoid_hospital_visit_day when explicit; other constraints "
            "must be copied exactly from the source note."
        ),
    )


class StructuredDemand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    requests: list[ServiceRequest] = Field(default_factory=list, max_length=8)
    confidence: float | None = Field(default=None, ge=0, le=1)
    needs_followup_survey: bool = True
    followup_reason: str | None = None
    source_text_was_redacted: bool = False
    method: Literal["gemini_structured_output", "deterministic_fallback"] = "deterministic_fallback"


class EvidenceAssessment(BaseModel):
    observation_count: int = Field(ge=0)
    survey_count: int = Field(default=0, ge=0)
    source_diversity: int = Field(ge=0)
    missingness: float = Field(ge=0, le=1)
    latest_observation_date: date | None = None
    model_confidence: float | None = Field(default=None, ge=0, le=1)
    deterministic_confidence: float = Field(ge=0, le=1)
    combined_confidence: float = Field(ge=0, le=1)
    status: Literal["충분", "주의", "조사 필요", "제한적 계획 가능"]
    needs_survey: bool
    limited_planning_allowed: bool
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


def _explicit_dates(text: str) -> list[str]:
    found: list[str] = []
    patterns = (
        (re.compile(r"(?<!\d)(20\d{2})-(\d{1,2})-(\d{1,2})(?!\d)"), True),
        (re.compile(r"(?:(20\d{2})년\s*)?(\d{1,2})월\s*(\d{1,2})일"), False),
    )
    for pattern, iso_format in patterns:
        for match in pattern.finditer(text):
            year_text, month_text, day_text = match.groups()
            if iso_format and not year_text:
                continue
            year = int(year_text) if year_text else 2000
            month, day = int(month_text), int(day_text)
            try:
                date(year, month, day)
            except ValueError:
                continue
            value = f"{year:04d}-{month:02d}-{day:02d}" if year_text else f"{month:02d}-{day:02d}"
            found.append(value)
    return list(dict.fromkeys(found))


def _explicit_times(text: str) -> list[str]:
    found: list[str] = []
    korean_time = re.compile(r"(?:(오전|오후)\s*)?(\d{1,2})\s*시(?:\s*(\d{1,2})\s*분)?")
    for match in korean_time.finditer(text):
        meridiem, hour_text, minute_text = match.groups()
        hour, minute = int(hour_text), int(minute_text or 0)
        if minute > 59 or (meridiem and not 1 <= hour <= 12) or (not meridiem and hour > 23):
            continue
        if meridiem == "오전":
            hour = 0 if hour == 12 else hour
        elif meridiem == "오후":
            hour = 12 if hour == 12 else hour + 12
        found.append(f"{hour:02d}:{minute:02d}")
    for match in re.finditer(r"(?<!\d)([01]?\d|2[0-3]):([0-5]\d)(?!\d)", text):
        hour, minute = (int(part) for part in match.groups())
        found.append(f"{hour:02d}:{minute:02d}")
    return list(dict.fromkeys(found))


def _explicit_period(text: str) -> tuple[str | None, bool]:
    periods: list[str] = []
    if any(word in text for word in ("겨울", "동절기")):
        periods.append("winter")
    if any(word in text for word in ("여름", "하절기")):
        periods.append("summer")
    for match in re.finditer(r"(?:(20\d{2})년\s*)?(\d{1,2})월", text):
        year_text, month_text = match.groups()
        month = int(month_text)
        if 1 <= month <= 12:
            periods.append(f"{year_text}-{month:02d}" if year_text else f"{month}월")
    for phrase in ("다음 달", "이번 달", "다음 주", "이번 주", "상반기", "하반기"):
        if phrase in text:
            periods.append(phrase)
    unique = list(dict.fromkeys(periods))
    return (unique[0] if len(unique) == 1 else None, len(unique) > 1)


def _explicit_weekdays(text: str, translations: dict[str, str]) -> tuple[list[str], list[str]]:
    preferred: list[str] = []
    excluded: list[str] = []
    negative_markers = ("피", "제외", "불가", "말고", "안 됨", "안됨")
    preferred_markers = ("선호", "희망", "원함", "좋", "가능", "하고 싶", "했으면")
    for korean, english in translations.items():
        for match in re.finditer(korean, text):
            later_days = [
                next_match.start()
                for day in translations
                if (next_match := re.search(day, text[match.end() :]))
            ]
            next_day_start = match.end() + min(later_days) if later_days else match.end() + 14
            local = text[match.start() : min(match.end() + 14, next_day_start)]
            tail = local[len(korean) :]
            if any(marker in tail for marker in negative_markers):
                if english not in excluded:
                    excluded.append(english)
                break
            if any(marker in tail for marker in preferred_markers):
                if english not in preferred:
                    preferred.append(english)
                break
    return preferred, excluded


def _explicit_recurring_pattern(text: str) -> str | None:
    patterns = {
        "weekly": ("매주", "주마다"),
        "monthly": ("매월", "매달", "월마다"),
        "seasonal": ("겨울마다", "여름마다", "계절마다", "매년 겨울", "매년 여름"),
        "one_time": ("이번만", "한 번만", "한번만", "일회성", "딱 한 번", "딱 한번"),
    }
    matched = [
        key for key, markers in patterns.items() if any(marker in text for marker in markers)
    ]
    if re.search(r"월\s*\d+\s*회", text):
        matched.append("monthly")
    matched = list(dict.fromkeys(matched))
    return matched[0] if len(matched) == 1 else None


def _explicit_urgency(text: str) -> str | None:
    negative_suffix = re.compile(
        r"^(?:하지\s*않|하지는\s*않|은\s*아니|는\s*아니|이\s*아니|가\s*아니|은\s*아님|는\s*아님|할\s*필요\s*없)"
    )
    for match in re.finditer(r"긴급|시급|응급|급히", text):
        if negative_suffix.match(text[match.end() : match.end() + 16]):
            continue
        return match.group(0)
    return None


def _normalized_constraints(
    values: list[str], expected_values: list[str], source_text: str | None
) -> list[str] | None:
    allowed = set(expected_values)
    result: set[str] = set()
    for value in values:
        original = value.strip()
        clean = original.lower().replace(" ", "")
        if original in allowed:
            result.add(original)
        elif (
            "avoid_hospital_visit_day" in allowed
            and ("hospital" in clean and any(word in clean for word in ("avoid", "skip", "not")))
        ) or (
            "avoid_hospital_visit_day" in allowed
            and "병원" in clean
            and any(word in clean for word in ("피", "제외", "불가"))
        ):
            result.add("avoid_hospital_visit_day")
        elif original and source_text is not None and original in source_text:
            result.add(original)
        else:
            return None
    return sorted(result)


def deterministic_structure(text: str, redacted: bool = False) -> StructuredDemand:
    clean = text.strip()
    if not clean:
        return StructuredDemand(
            followup_reason="기록이 비어 있어 기초조사가 필요합니다.",
            source_text_was_redacted=redacted,
        )

    service_patterns = tuple(
        (service.service_type_id, service.keywords) for service in SERVICE_REGISTRY
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
    preferred_days, excluded_days = _explicit_weekdays(clean, day_translation)
    frequency_matches = [int(value) for value in re.findall(r"월\s*(\d+)\s*회", clean)]
    date_matches = _explicit_dates(clean)
    time_matches = _explicit_times(clean)
    recurrence = _explicit_recurring_pattern(clean)
    period, period_conflict = _explicit_period(clean)
    recurrence_markers = (
        "매주",
        "주마다",
        "매월",
        "매달",
        "월마다",
        "겨울마다",
        "여름마다",
        "계절마다",
        "매년 겨울",
        "매년 여름",
        "이번만",
        "한 번만",
        "한번만",
        "일회성",
        "딱 한 번",
        "딱 한번",
    )
    recurrence_conflict = (
        any(marker in clean for marker in recurrence_markers) and recurrence is None
    )
    conflicts = []
    if len(set(frequency_matches)) > 1:
        conflicts.append("빈도")
    if len(date_matches) > 1:
        conflicts.append("날짜")
    if len(time_matches) > 1:
        conflicts.append("시간")
    if recurrence_conflict:
        conflicts.append("반복 방식")
    if period_conflict:
        conflicts.append("시기")
    frequency = (
        frequency_matches[0] if len(set(frequency_matches)) == 1 and frequency_matches else None
    )
    if period_conflict:
        period = None
    constraints: list[str] = []
    if re.search(r"병원.{0,20}(?:피|제외|불가|말고)", clean):
        constraints.append("avoid_hospital_visit_day")
    urgency_evidence = _explicit_urgency(clean)
    requests = [
        ServiceRequest(
            service_type=service,
            requested_period=period,
            frequency_per_month=frequency,
            desired_date=date_matches[0] if len(date_matches) == 1 else None,
            desired_time=time_matches[0] if len(time_matches) == 1 else None,
            recurring_pattern=recurrence,
            urgency="urgent" if urgency_evidence else None,
            urgency_evidence=urgency_evidence,
            preferred_days=preferred_days,
            excluded_days=excluded_days,
            constraints=constraints,
        )
        for service in service_types
    ]
    reason = (
        f"서로 다른 {'·'.join(conflicts)} 표현이 있어 담당자 확인이 필요합니다."
        if conflicts
        else None
    )
    if not requests:
        reason = reason or "서비스 수요가 명시되지 않아 추가 확인이 필요합니다."
    return StructuredDemand(
        requests=requests,
        needs_followup_survey=bool(conflicts) or not requests,
        followup_reason=reason,
        source_text_was_redacted=redacted,
        method="deterministic_fallback",
    )


def _matches_explicit_facts(
    parsed: StructuredDemand,
    fallback: StructuredDemand,
    source_text: str | None = None,
) -> bool:
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

    for service_type, expected_request in expected.items():
        candidate = actual[service_type]
        period = candidate.requested_period
        canonical_period = (
            period_aliases.get(period.strip().lower(), period.strip()) if period else None
        )
        expected_period = expected_request.requested_period
        if period is not None and canonical_period != expected_period:
            return False
        if (
            candidate.frequency_per_month is not None
            and candidate.frequency_per_month != expected_request.frequency_per_month
        ):
            return False
        for field_name in (
            "desired_date",
            "desired_time",
            "recurring_pattern",
            "urgency",
            "urgency_evidence",
        ):
            candidate_value = getattr(candidate, field_name)
            if candidate_value is not None and candidate_value != getattr(
                expected_request, field_name
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
        constraints = _normalized_constraints(
            candidate.constraints, expected_request.constraints, source_text
        )
        if constraints is None:
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
                "Do not infer frequency, dates, times, recurrence, urgency, or constraints. "
                "Extract urgency only with an exact source phrase in urgency_evidence. "
                "Copy non-canonical constraint text exactly from the source. "
                "Return seasons as winter or summer, keep explicit non-season periods verbatim, "
                "and weekday values in lowercase English. "
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
        if len(parsed.requests) > 8 or not _matches_explicit_facts(parsed, fallback, redacted_text):
            return fallback
        verified = {item.service_type: item for item in fallback.requests}
        for request in parsed.requests:
            local = verified[request.service_type]
            request.requested_period = local.requested_period
            request.frequency_per_month = local.frequency_per_month
            request.desired_date = local.desired_date
            request.desired_time = local.desired_time
            request.recurring_pattern = local.recurring_pattern
            request.urgency = local.urgency
            request.urgency_evidence = local.urgency_evidence
            request.preferred_days = local.preferred_days.copy()
            request.excluded_days = local.excluded_days.copy()
            verified_constraints = (
                _normalized_constraints(request.constraints, local.constraints, redacted_text) or []
            )
            request.constraints = list(dict.fromkeys([*local.constraints, *verified_constraints]))
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
    survey_count: int = 0,
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
        age_days = None
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
        if (
            survey_count > 0
            and diversity >= 2
            and age_days is not None
            and age_days <= 180
            and missing < 1
        ):
            status: Literal["충분", "주의", "조사 필요", "제한적 계획 가능"] = "제한적 계획 가능"
            reasons.append("기초조사 근거가 추가되어 제한적 계획에 사용할 수 있습니다.")
            reasons.append("관측 규모가 작아 추가 조사가 필요합니다.")
        else:
            status = "조사 필요"
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
        survey_count=max(survey_count, 0),
        needs_survey=status in {"조사 필요", "제한적 계획 가능"},
        limited_planning_allowed=status in {"주의", "충분", "제한적 계획 가능"},
        evidence_reasons=reasons,
    )
