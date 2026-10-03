"""Deterministic data quality model and overall status classification (§18, V4 §37).

Seven readiness dimensions drive the overall status. Two V4 support dimensions
(external empirical support, operational validation) are reported alongside but
never change readiness: an external survey prior is not local evidence, and
data quality says nothing about how high demand is.
"""

from __future__ import annotations

from typing import Any

QUALITY_LEVELS = ("GOOD", "LIMITED", "POOR", "UNKNOWN")
OVERALL_STATUSES = ("SUFFICIENT", "LIMITED", "SURVEY_REQUIRED")

DIMENSION_LABELS_KO: dict[str, str] = {
    "OBSERVATION_COVERAGE": "관측량",
    "RECENCY": "최신성",
    "SOURCE_DIVERSITY": "출처 다양성",
    "SURVEY_COMPLETENESS": "조사 완성도",
    "CONFLICT_STATUS": "충돌 상태",
    "DUPLICATE_REVIEW_STATUS": "중복 검토",
    "CALIBRATION_STATUS": "보정 상태",
    "EXTERNAL_EMPIRICAL_SUPPORT": "외부 실증 근거",
    "OPERATIONAL_VALIDATION": "운영 검증",
}

SUPPORT_DIMENSIONS = ("EXTERNAL_EMPIRICAL_SUPPORT", "OPERATIONAL_VALIDATION")

LEVEL_LABELS_KO: dict[str, str] = {
    "GOOD": "양호",
    "LIMITED": "제한적",
    "POOR": "미흡",
    "UNKNOWN": "확인 불가",
}

OVERALL_LABELS_KO: dict[str, str] = {
    "SUFFICIENT": "충분 (정상 계획 가능)",
    "LIMITED": "제한적 계획 가능",
    "SURVEY_REQUIRED": "현장 조사 필요",
}


def assess_area_data_quality(area_data: dict[str, Any]) -> dict[str, Any]:
    """Deterministically compute 7 quality dimensions without opaque numeric scoring.

    Expects area_data dictionary with optional fields:
      - observation_count: int
      - newest_evidence_age_days: int | None
      - source_types: list[str] | set[str]
      - needs_survey: bool
      - survey_completed: bool
      - unresolved_conflicts_count: int
      - unresolved_duplicates_count: int
      - calibration_status: str ("CALIBRATED", "PROVISIONAL", "UNCALIBRATED", None)
    """
    obs_count = int(area_data.get("observation_count", 0))
    age_days = area_data.get("newest_evidence_age_days")
    sources = set(area_data.get("source_types") or [])
    needs_survey = bool(area_data.get("needs_survey", False))
    survey_completed = bool(area_data.get("survey_completed", not needs_survey))
    conflicts = int(area_data.get("unresolved_conflicts_count", 0))
    duplicates = int(area_data.get("unresolved_duplicates_count", 0))
    calib = str(area_data.get("calibration_status") or "UNCALIBRATED").upper()
    external_support = area_data.get("external_empirical_support")
    operational_validation = bool(area_data.get("operational_validation", False))

    # 1. OBSERVATION_COVERAGE
    if obs_count >= 6:
        obs_dim = "GOOD"
    elif obs_count >= 2:
        obs_dim = "LIMITED"
    elif obs_count == 1:
        obs_dim = "POOR"
    else:
        obs_dim = "UNKNOWN"

    # 2. RECENCY
    if age_days is None:
        rec_dim = "UNKNOWN"
    elif age_days <= 90:
        rec_dim = "GOOD"
    elif age_days <= 180:
        rec_dim = "LIMITED"
    else:
        rec_dim = "POOR"

    # 3. SOURCE_DIVERSITY
    source_count = len(sources)
    if source_count >= 3:
        div_dim = "GOOD"
    elif source_count == 2:
        div_dim = "LIMITED"
    elif source_count == 1:
        div_dim = "POOR"
    else:
        div_dim = "UNKNOWN"

    # 4. SURVEY_COMPLETENESS
    if survey_completed and not needs_survey:
        surv_dim = "GOOD"
    elif survey_completed and needs_survey:
        surv_dim = "LIMITED"
    elif needs_survey:
        surv_dim = "POOR"
    else:
        surv_dim = "UNKNOWN"

    # 5. CONFLICT_STATUS
    if conflicts == 0:
        conf_dim = "GOOD"
    elif conflicts == 1:
        conf_dim = "LIMITED"
    else:
        conf_dim = "POOR"

    # 6. DUPLICATE_REVIEW_STATUS
    if duplicates == 0:
        dup_dim = "GOOD"
    elif duplicates <= 2:
        dup_dim = "LIMITED"
    else:
        dup_dim = "POOR"

    # 7. CALIBRATION_STATUS
    if calib == "CALIBRATED":
        cal_dim = "GOOD"
    elif calib in {"PROVISIONAL", "PARTIAL"}:
        cal_dim = "LIMITED"
    elif calib == "UNCALIBRATED":
        cal_dim = "LIMITED" if obs_count >= 2 else "POOR"
    else:
        cal_dim = "UNKNOWN"

    dimensions = {
        "OBSERVATION_COVERAGE": obs_dim,
        "RECENCY": rec_dim,
        "SOURCE_DIVERSITY": div_dim,
        "SURVEY_COMPLETENESS": surv_dim,
        "CONFLICT_STATUS": conf_dim,
        "DUPLICATE_REVIEW_STATUS": dup_dim,
        "CALIBRATION_STATUS": cal_dim,
    }

    # Deterministic overall classification rules (§16)
    # Rule 1: Needs immediate field survey if observation < 2, or stale only,
    # or needs_survey is True
    if needs_survey or obs_dim in {"POOR", "UNKNOWN"} or rec_dim == "POOR" or conf_dim == "POOR":
        overall = "SURVEY_REQUIRED"
        explanation = "현장 조사 또는 전화 확인을 통한 수요 검증이 필요합니다."
    # Rule 2: Limited planning if conflicts or duplicates or limited observations exist
    elif (
        obs_dim == "LIMITED"
        or rec_dim == "LIMITED"
        or conf_dim == "LIMITED"
        or dup_dim in {"LIMITED", "POOR"}
        or div_dim in {"POOR", "UNKNOWN"}
    ):
        overall = "LIMITED"
        explanation = "제한적 계획 가능 상태입니다 (최신성 및 일부 데이터 보완 권장)."
    # Rule 3: Sufficient
    else:
        overall = "SUFFICIENT"
        explanation = "계획 수립에 충분한 신뢰도를 확보한 데이터입니다."

    support_dimensions = {
        "EXTERNAL_EMPIRICAL_SUPPORT": (
            "GOOD" if external_support else "UNKNOWN" if external_support is None else "POOR"
        ),
        "OPERATIONAL_VALIDATION": "GOOD" if operational_validation else "UNKNOWN",
    }

    provenance_warnings = []
    if calib == "UNCALIBRATED":
        provenance_warnings.append("수요 모형 미보정 상태 (공공데이터 기반 기본 추정치 사용)")
    if rec_dim == "LIMITED":
        provenance_warnings.append("근거 자료 수집 90일 경과 (노후화 진행 중)")
    if conf_dim == "LIMITED":
        provenance_warnings.append("검토 중인 경미한 수요 차이 존재")

    return {
        "area_id": str(area_data.get("id") or area_data.get("area_id") or ""),
        "overall_status": overall,
        "overall_label_ko": OVERALL_LABELS_KO[overall],
        "explanation": explanation,
        "provenance_warnings": provenance_warnings,
        "dimensions": dimensions,
        "dimension_labels_ko": {
            dim: {
                "name": DIMENSION_LABELS_KO[dim],
                "level": level,
                "label": LEVEL_LABELS_KO[level],
            }
            for dim, level in {**dimensions, **support_dimensions}.items()
        },
        "support_dimensions": support_dimensions,
        "support_dimensions_note": (
            "외부 실증 근거·운영 검증은 참고 표시이며 계획 가능 상태를 바꾸지 않습니다. "
            "데이터 품질은 수요 크기와 무관합니다."
        ),
    }
