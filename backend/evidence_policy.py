"""Shared evidence-age policy for quality, planning, and forecast eligibility."""

from __future__ import annotations

from datetime import date
from typing import Any

from backend.timeutils import korea_today

FRESH_MAX_AGE_DAYS = 90
AGING_MAX_AGE_DAYS = 180
FORECAST_MAX_EVIDENCE_AGE_DAYS = 120

FRESHNESS_STATUSES = ("FRESH", "AGING", "STALE")


def evidence_age_days(observed_on: date | str, *, as_of: date | None = None) -> int:
    """Return evidence age and reject dates that occur after the reference date."""
    observed = date.fromisoformat(observed_on) if isinstance(observed_on, str) else observed_on
    reference = as_of or korea_today()
    age = (reference - observed).days
    if age < 0:
        raise ValueError("evidence date cannot be in the future")
    return age


def evidence_freshness(observed_on: date | str, *, as_of: date | None = None) -> str:
    age = evidence_age_days(observed_on, as_of=as_of)
    if age <= FRESH_MAX_AGE_DAYS:
        return "FRESH"
    if age <= AGING_MAX_AGE_DAYS:
        return "AGING"
    return "STALE"


def planning_evidence_eligible(observed_on: date | str, *, as_of: date | None = None) -> bool:
    try:
        return evidence_freshness(observed_on, as_of=as_of) != "STALE"
    except ValueError:
        return False


def forecast_evidence_eligible(observed_on: date | str, *, as_of: date | None = None) -> bool:
    return evidence_age_days(observed_on, as_of=as_of) <= FORECAST_MAX_EVIDENCE_AGE_DAYS


def freshness_policy_payload() -> dict[str, Any]:
    return {
        "fresh_max_age_days": FRESH_MAX_AGE_DAYS,
        "aging_max_age_days": AGING_MAX_AGE_DAYS,
        "stale_after_days": AGING_MAX_AGE_DAYS,
        "forecast_max_evidence_age_days": FORECAST_MAX_EVIDENCE_AGE_DAYS,
        "planning_eligible_through_days": AGING_MAX_AGE_DAYS,
    }
