"""Reproducible, evidence-gated service-demand outlooks."""

from __future__ import annotations

import hashlib
import json
import math
import statistics
from datetime import date
from typing import Any

from backend.evidence_policy import (
    FORECAST_MAX_EVIDENCE_AGE_DAYS,
    evidence_age_days,
    evidence_freshness,
    forecast_evidence_eligible,
    freshness_policy_payload,
)
from backend.timeutils import korea_today

MODEL_VERSION = "rolling_median_mad_v1"
CURRENT_FORECAST_MODEL = "CURRENT_EVIDENCE_GATED"
BASELINE_FORECAST_MODELS = (
    "LAST_VALUE",
    "ROLLING_MEDIAN",
    "SEASONAL_MEDIAN_MAD",
    "SIMPLE_EXPONENTIAL_SMOOTHING",
)
MIN_HISTORY_MONTHS = 6
FORECAST_MODEL_PARAMETERS = {
    "CURRENT_EVIDENCE_GATED": {"current_method": "seasonal_median_mad_else_rolling_median_mad"},
    "LAST_VALUE": {
        "lookback_months": MIN_HISTORY_MONTHS,
        "interval": "MAD_OF_ADJACENT_CHANGES",
    },
    "ROLLING_MEDIAN": {
        "lookback_months": MIN_HISTORY_MONTHS,
        "interval": "MEDIAN_ABSOLUTE_DEVIATION",
    },
    "SEASONAL_MEDIAN_MAD": {"minimum_same_calendar_month_observations": 2},
    "SIMPLE_EXPONENTIAL_SMOOTHING": {
        "alpha": 0.3,
        "lookback_months": MIN_HISTORY_MONTHS,
    },
}
MIN_PANEL_AREAS = 3
MIN_REGION_AREA_COVERAGE = 0.6
MIN_SOURCE_TYPES = 2
# Compatibility alias; the authoritative forecast age limit lives in evidence_policy.
MAX_EVIDENCE_AGE_DAYS = FORECAST_MAX_EVIDENCE_AGE_DAYS


def _month_start(value: date) -> date:
    return date(value.year, value.month, 1)


def _shift_month(value: date, offset: int) -> date:
    absolute_month = value.year * 12 + value.month - 1 + offset
    return date(absolute_month // 12, absolute_month % 12 + 1, 1)


def _month_key(value: date) -> str:
    return value.strftime("%Y-%m")


def _month_dates(as_of: date, horizon: int) -> list[date]:
    current_month = _month_start(as_of)
    return [_shift_month(current_month, offset) for offset in range(horizon)]


def _fingerprint(records: list[dict[str, Any]]) -> str:
    stable = [
        {
            "area_id": str(row["area_id"]),
            "occurred_on": str(row["occurred_on"]),
            "source_type": str(row["source_type"]),
            "frequency_per_month": row.get("frequency_per_month"),
            "created_at": str(row.get("created_at", "")),
        }
        for row in records
    ]
    stable.sort(
        key=lambda row: (
            row["area_id"],
            row["occurred_on"],
            row["source_type"],
            str(row["frequency_per_month"]),
            row["created_at"],
        )
    )
    payload = json.dumps(stable, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _range(values: list[int]) -> tuple[int, int, int]:
    center = statistics.median(values)
    deviation = statistics.median(abs(value - center) for value in values)
    radius = 1.4826 * deviation
    return max(0, math.floor(center - radius)), int(round(center)), math.ceil(center + radius)


def _residual_interval(center: float, absolute_residuals: list[float]) -> tuple[int, int, int]:
    residual_median = statistics.median(absolute_residuals) if absolute_residuals else 0.0
    radius = 1.4826 * residual_median
    return max(0, math.floor(center - radius)), int(round(center)), math.ceil(center + radius)


def _simple_exponential_smoothing(
    values: list[int], alpha: float = 0.3
) -> tuple[float, list[float]]:
    level = float(values[0])
    residuals = []
    for observed in values[1:]:
        residuals.append(abs(float(observed) - level))
        level = alpha * float(observed) + (1 - alpha) * level
    return level, residuals


def _predict_with_model(
    model: str, values: list[int], seasonal_values: list[int]
) -> tuple[int | None, int | None, int | None, str | None]:
    if model == CURRENT_FORECAST_MODEL:
        selected = seasonal_values if len(seasonal_values) >= 2 else values
        basis = "SEASONAL_MEDIAN_MAD" if len(seasonal_values) >= 2 else "ROLLING_MEDIAN_MAD"
        low, mid, high = _range(selected)
        return low, mid, high, basis
    if model == "LAST_VALUE":
        residuals = [
            abs(float(right - left)) for left, right in zip(values, values[1:], strict=False)
        ]
        low, mid, high = _residual_interval(float(values[-1]), residuals)
        return low, mid, high, model
    if model == "ROLLING_MEDIAN":
        low, mid, high = _range(values)
        return low, mid, high, model
    if model == "SEASONAL_MEDIAN_MAD":
        if len(seasonal_values) < 2:
            return None, None, None, None
        low, mid, high = _range(seasonal_values)
        return low, mid, high, model
    if model == "SIMPLE_EXPONENTIAL_SMOOTHING":
        if len(values) < MIN_HISTORY_MONTHS:
            return None, None, None, None
        level, residuals = _simple_exponential_smoothing(values)
        low, mid, high = _residual_interval(level, residuals)
        return low, mid, high, model
    raise ValueError(f"unsupported forecast model: {model}")


def forecast_model_parameters(model: str) -> dict[str, Any]:
    if model not in FORECAST_MODEL_PARAMETERS:
        raise ValueError(f"unsupported forecast model: {model}")
    return dict(FORECAST_MODEL_PARAMETERS[model])


def forecast_region_service(
    *,
    region_id: str,
    region_name: str,
    service_type: str,
    region_area_count: int,
    observations: list[dict[str, Any]],
    as_of: date | None = None,
    horizon_months: int = 3,
    include_panel_area_ids: bool = False,
    model: str = CURRENT_FORECAST_MODEL,
) -> dict[str, Any]:
    """Forecast a recent balanced panel; never fill missing months with zero."""
    if model != CURRENT_FORECAST_MODEL and model not in BASELINE_FORECAST_MODELS:
        raise ValueError(f"unsupported forecast model: {model}")
    reference_date = as_of or korea_today()
    current_month = _month_start(reference_date)
    target_months = _month_dates(reference_date, horizon_months)
    fingerprint = _fingerprint(observations)
    normalized: list[dict[str, Any]] = []
    for row in observations:
        raw_frequency = row.get("frequency_per_month")
        if raw_frequency is None:
            continue
        try:
            occurred_on = date.fromisoformat(str(row["occurred_on"]))
            frequency = int(raw_frequency)
        except (KeyError, TypeError, ValueError):
            continue
        if occurred_on >= current_month or frequency < 0:
            continue
        normalized.append(
            {
                "area_id": str(row["area_id"]),
                "occurred_on": occurred_on,
                "month": _month_start(occurred_on),
                "source_type": str(row.get("source_type", "unknown")),
                "frequency": frequency,
                "created_at": str(row.get("created_at", "")),
            }
        )

    # Use the most recent reported monthly frequency per area and month. Repeated calls
    # in the same month replace that area's report; they do not inflate the regional sum.
    latest_by_area_month: dict[tuple[str, date], dict[str, Any]] = {}
    for row in normalized:
        key = (row["area_id"], row["month"])
        current = latest_by_area_month.get(key)
        if current is None or (row["occurred_on"], row["created_at"]) > (
            current["occurred_on"],
            current["created_at"],
        ):
            latest_by_area_month[key] = row

    recent_months = [
        _shift_month(current_month, -offset) for offset in range(MIN_HISTORY_MONTHS, 0, -1)
    ]
    recent_area_sets = [
        {area_id for (area_id, month) in latest_by_area_month if month == history_month}
        for history_month in recent_months
    ]
    panel_area_ids = set.intersection(*recent_area_sets) if recent_area_sets else set()
    recent_panel_rows = [
        row
        for history_month in recent_months
        for area_id in sorted(panel_area_ids)
        if (row := latest_by_area_month.get((area_id, history_month))) is not None
    ]
    source_diversity = len({row["source_type"] for row in recent_panel_rows})
    latest_observed = max((row["occurred_on"] for row in recent_panel_rows), default=None)
    latest_age_days = (
        evidence_age_days(latest_observed, as_of=reference_date)
        if latest_observed is not None
        else None
    )
    latest_freshness = (
        evidence_freshness(latest_observed, as_of=reference_date)
        if latest_observed is not None
        else None
    )
    reasons: list[str] = []
    if len(panel_area_ids) < MIN_PANEL_AREAS:
        reasons.append("AREA_PANEL_TOO_SMALL")
    if region_area_count <= 0:
        reasons.append("REGION_AREA_COUNT_UNAVAILABLE")
    elif len(panel_area_ids) < math.ceil(region_area_count * MIN_REGION_AREA_COVERAGE):
        reasons.append("AREA_COVERAGE_TOO_LOW")
    if len(recent_panel_rows) != MIN_HISTORY_MONTHS * len(panel_area_ids):
        reasons.append("SIX_CONSECUTIVE_MONTHS_REQUIRED")
    if source_diversity < MIN_SOURCE_TYPES:
        reasons.append("SOURCE_DIVERSITY_TOO_LOW")
    if latest_observed is None or not forecast_evidence_eligible(
        latest_observed, as_of=reference_date
    ):
        reasons.append("OBSERVATIONS_STALE")

    complete_month_totals: dict[date, int] = {}
    if panel_area_ids:
        for month in sorted({month for _, month in latest_by_area_month}):
            month_rows = [latest_by_area_month.get((area_id, month)) for area_id in panel_area_ids]
            if all(row is not None for row in month_rows):
                complete_month_totals[month] = sum(int(row["frequency"]) for row in month_rows)
    recent_totals = [complete_month_totals.get(month) for month in recent_months]
    if any(value is None for value in recent_totals):
        reasons.append("SIX_CONSECUTIVE_MONTHS_REQUIRED")

    evidence_gate_available = not reasons
    model_history_months = len(complete_month_totals)
    confidence = (
        "HIGH"
        if evidence_gate_available
        and model_history_months >= 12
        and len(panel_area_ids) >= 5
        and source_diversity >= 3
        else "MEDIUM"
        if evidence_gate_available
        else None
    )
    months: list[dict[str, Any]] = []
    for target_month in target_months:
        seasonal_values = [
            total
            for observed_month, total in complete_month_totals.items()
            if observed_month.month == target_month.month and observed_month < current_month
        ]
        recent_values = [int(value) for value in recent_totals if value is not None]
        low = mid = high = None
        model_basis = None
        model_reason = None
        if evidence_gate_available:
            low, mid, high, model_basis = _predict_with_model(model, recent_values, seasonal_values)
            if mid is None:
                model_reason = (
                    "SEASONAL_HISTORY_INSUFFICIENT"
                    if model == "SEASONAL_MEDIAN_MAD"
                    else "MODEL_HISTORY_INSUFFICIENT"
                )
        month_available = evidence_gate_available and mid is not None
        month_reasons = list(reasons)
        if model_reason:
            month_reasons.append(model_reason)
        month_result = {
            "region_id": region_id,
            "region_name": region_name,
            "service_type": service_type,
            "month": _month_key(target_month),
            "expected_rounds_low": low,
            "expected_rounds_mid": mid,
            "expected_rounds_high": high,
            "confidence": confidence if month_available else None,
            "evidence_status": "SUFFICIENT_OBSERVED" if month_available else "DATA_INSUFFICIENT",
            "survey_required": not month_available,
            "observation_count": len(recent_panel_rows),
            "latest_evidence_age_days": latest_age_days,
            "latest_evidence_freshness": latest_freshness,
            "history_month_count": model_history_months,
            "observed_area_count": len(panel_area_ids),
            "region_area_count": region_area_count,
            "source_diversity": source_diversity,
            "model_basis": model_basis,
            "model_version": (
                MODEL_VERSION if model == CURRENT_FORECAST_MODEL else f"{model.lower()}_v1"
            ),
            "input_fingerprint": fingerprint,
            "insufficiency_reasons": sorted(set(month_reasons)),
            "provenance": "SURVEY INPUT; DETERMINISTIC FORECAST; SIMULATED FOR PRE-R&D",
        }
        if include_panel_area_ids:
            month_result["panel_area_ids"] = sorted(panel_area_ids)
        months.append(month_result)
    available_month_count = sum(
        month["evidence_status"] == "SUFFICIENT_OBSERVED" for month in months
    )
    return {
        "status": "AVAILABLE" if available_month_count else "DATA_INSUFFICIENT",
        "survey_required": available_month_count < len(months),
        "model": model,
        "model_parameters": forecast_model_parameters(model),
        "months": months,
        "freshness_policy": freshness_policy_payload(),
        "message": (
            "최근 6개월 연속 관측 패널의 중앙값과 변동폭으로 산출했습니다."
            if available_month_count == len(months) and available_month_count
            else "일부 예측 구간의 모델별 자료 요건이 충족되지 않아 추가 조사가 필요합니다."
            if available_month_count
            else (
                "서비스 빈도·권역 범위·출처가 충분한 최근 연속 관측이 없어 "
                "전망값을 만들지 않았습니다."
            )
        ),
        "provenance": "SURVEY INPUT; DETERMINISTIC FORECAST; SIMULATED FOR PRE-R&D",
    }
