"""Per-source evidence eligibility. Resident feedback is a claim, never a verified survey."""

from __future__ import annotations

from typing import Any

SOURCE_EVIDENCE_POLICY: dict[str, dict[str, Any]] = {
    "SURVEY": {
        "label_ko": "담당자 조사",
        "max_observation_contribution": None,
        "frequency_floor_eligible": True,
        "calibration_eligible": True,
        "forecast_eligible": True,
        "requires_verification": False,
    },
    "RESIDENT_FEEDBACK": {
        "label_ko": "주민 의견(검증 전 주장)",
        # Any number of accepted resident claims adds at most this many pseudo-observations.
        "max_observation_contribution": 1,
        "frequency_floor_eligible": False,
        "calibration_eligible": False,
        "forecast_eligible": False,
        "requires_verification": True,
    },
}


def source_policy(source: str) -> dict[str, Any]:
    try:
        return dict(SOURCE_EVIDENCE_POLICY[source])
    except KeyError:
        raise ValueError(f"unknown evidence source: {source}") from None


def bounded_observation_contribution(source: str, accepted_count: int) -> int:
    """Observation weight a source may add; resident claims are capped, not summed."""
    if accepted_count <= 0:
        return 0
    cap = SOURCE_EVIDENCE_POLICY[source]["max_observation_contribution"]
    return accepted_count if cap is None else min(accepted_count, int(cap))


def source_policy_payload() -> dict[str, Any]:
    return {"sources": SOURCE_EVIDENCE_POLICY, "note": "주민 의견은 조사와 동급이 아닙니다."}
