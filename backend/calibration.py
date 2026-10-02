"""Demand calibration profile framework (V3 §2).

Population-based priors and survey frequency floors are planning aids, not
observed demand. This module tracks whether a region/service pair has ever
been calibrated against real observed data, and refuses to label anything
"calibrated" unless a real observation source meets a documented minimum
sample size. Until real observation data exists, every profile stays
UNCALIBRATED by construction.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

CalibrationStatus = Literal["UNCALIBRATED", "LIMITED_SAMPLE", "CALIBRATED"]

CalibrationSourceType = Literal["SIMULATED_PRIOR", "SURVEY_OBSERVED", "FIELD_OBSERVED"]

REAL_OBSERVATION_SOURCE_TYPES: frozenset[str] = frozenset({"SURVEY_OBSERVED", "FIELD_OBSERVED"})

# Documented thresholds (V3 §2 requires config, not hidden magic numbers).
MIN_SAMPLE_SIZE_FOR_LIMITED_SAMPLE = 5
MIN_SAMPLE_SIZE_FOR_CALIBRATED = 30

STATUS_MESSAGES: dict[CalibrationStatus, str] = {
    "UNCALIBRATED": "실제 관측 기반 보정: 아직 없음 (합성 사전값 사용 중)",
    "LIMITED_SAMPLE": "실제 관측 기반 보정: 제한적 표본 (참고용, 계획 확정에는 추가 관측 필요)",
    "CALIBRATED": "실제 관측 기반 보정: 완료",
}


def compute_calibration_status(
    *, sample_size: int, source_type: str, has_rate: bool = True
) -> CalibrationStatus:
    """Classify a calibration attempt without ever claiming calibration from a synthetic prior.

    A profile can only leave UNCALIBRATED when it is backed by a real
    observation source (survey or field), includes a measured rate, and meets
    the sample-size floor.
    """
    if sample_size <= 0 or not has_rate or source_type not in REAL_OBSERVATION_SOURCE_TYPES:
        return "UNCALIBRATED"
    if sample_size < MIN_SAMPLE_SIZE_FOR_LIMITED_SAMPLE:
        return "UNCALIBRATED"
    if sample_size < MIN_SAMPLE_SIZE_FOR_CALIBRATED:
        return "LIMITED_SAMPLE"
    return "CALIBRATED"


def calibration_confidence(*, sample_size: int, status: CalibrationStatus) -> float | None:
    """Deterministic, threshold-based confidence; None when there is nothing to be confident of."""
    if status == "UNCALIBRATED":
        return None
    return round(min(1.0, max(0, sample_size) / MIN_SAMPLE_SIZE_FOR_CALIBRATED), 3)


class DemandCalibrationProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile_id: str
    region_id: str
    service_type: str
    sample_size: int = Field(ge=0)
    observed_period_start: str | None = None
    observed_period_end: str | None = None
    raw_rate: float | None = Field(default=None, ge=0)
    calibrated_rate: float | None = Field(default=None, ge=0)
    confidence: float | None = Field(default=None, ge=0, le=1)
    status: CalibrationStatus
    source_type: CalibrationSourceType
    provenance: str
    version: int = Field(ge=1)
    created_at: str
