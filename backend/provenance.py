"""V4 provenance taxonomy shared by evidence, demand, and UI labels.

Every demand-related number carries one evidence level and one display label.
The levels are ordered: a higher level never follows from a lower-level input
alone (for example, an external rural survey prior never becomes local
calibration by itself).
"""

from __future__ import annotations

from enum import IntEnum
from typing import Literal


class EvidenceLevel(IntEnum):
    SYNTHETIC = 0
    EXTERNAL_EMPIRICAL_PRIOR = 1
    LOCAL_LIMITED_OBSERVATION = 2
    LOCAL_CALIBRATED = 3
    LOCAL_VALIDATED_OPERATIONAL = 4


SourceRole = Literal[
    "PUBLIC_DATA",
    "EXTERNAL_EMPIRICAL_PRIOR",
    "EXTERNAL_CONTEXT",
    "EXTERNAL_OPERATIONAL_REFERENCE",
    "LOCAL_OBSERVATION",
    "LOCAL_OPERATIONAL",
    "SIMULATION",
]

# Display labels shown next to numbers (tooltip key -> Korean label).
ValueLabel = Literal[
    "PUBLIC_DATA",
    "EXTERNAL_EMPIRICAL",
    "EXTERNAL_OPERATIONAL_REFERENCE",
    "LOCAL_OBSERVATION",
    "MODEL_ESTIMATE",
    "SIMULATION",
    "OPTIMIZATION_RESULT",
]

VALUE_LABELS_KO: dict[str, str] = {
    "PUBLIC_DATA": "공공데이터",
    "EXTERNAL_EMPIRICAL": "농촌 외부 조사 기준값",
    "EXTERNAL_OPERATIONAL_REFERENCE": "외부 운영자료 참고",
    "LOCAL_OBSERVATION": "지역 조사",
    "MODEL_ESTIMATE": "모델 추정",
    "SIMULATION": "모의 데이터",
    "OPTIMIZATION_RESULT": "최적화 결과",
}

CalibrationStatusV4 = Literal[
    "SYNTHETIC_ONLY",
    "EXTERNAL_EMPIRICAL",
    "LOCAL_LIMITED",
    "LOCAL_CALIBRATED",
    "LOCAL_OPERATIONAL_VALIDATED",
]

CALIBRATION_STATUS_LEVEL: dict[str, EvidenceLevel] = {
    "SYNTHETIC_ONLY": EvidenceLevel.SYNTHETIC,
    "EXTERNAL_EMPIRICAL": EvidenceLevel.EXTERNAL_EMPIRICAL_PRIOR,
    "LOCAL_LIMITED": EvidenceLevel.LOCAL_LIMITED_OBSERVATION,
    "LOCAL_CALIBRATED": EvidenceLevel.LOCAL_CALIBRATED,
    "LOCAL_OPERATIONAL_VALIDATED": EvidenceLevel.LOCAL_VALIDATED_OPERATIONAL,
}

CALIBRATION_STATUS_KO: dict[str, str] = {
    "SYNTHETIC_ONLY": "모의 기준값만 있음",
    "EXTERNAL_EMPIRICAL": "외부 조사 기준값 적용 (지역 조사 없음)",
    "LOCAL_LIMITED": "지역 조사 반영 (표본 제한)",
    "LOCAL_CALIBRATED": "지역 조사로 보정됨",
    "LOCAL_OPERATIONAL_VALIDATED": "실제 운영기록으로 검증됨",
}

# V3 statuses map onto V4 without upgrading anything.
V3_TO_V4_STATUS: dict[str, str] = {
    "UNCALIBRATED": "SYNTHETIC_ONLY",
    "LIMITED_SAMPLE": "LOCAL_LIMITED",
    "CALIBRATED": "LOCAL_CALIBRATED",
}


def calibration_status_v4(
    *,
    has_external_prior: bool,
    local_status_v3: str,
    operational_validation: bool = False,
) -> CalibrationStatusV4:
    """Combine evidence layers; an external prior alone tops out at EXTERNAL_EMPIRICAL."""
    local = V3_TO_V4_STATUS.get(local_status_v3, "SYNTHETIC_ONLY")
    if local == "LOCAL_CALIBRATED" and operational_validation:
        return "LOCAL_OPERATIONAL_VALIDATED"
    if local in {"LOCAL_LIMITED", "LOCAL_CALIBRATED"}:
        return local  # type: ignore[return-value]
    return "EXTERNAL_EMPIRICAL" if has_external_prior else "SYNTHETIC_ONLY"
