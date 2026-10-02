"""Tests for 7-dimension data quality model and overall status rules (§18)."""

from __future__ import annotations

from backend.data_quality import (
    LEVEL_LABELS_KO,
    OVERALL_LABELS_KO,
    QUALITY_LEVELS,
    assess_area_data_quality,
)


def test_data_quality_dimensions_and_levels() -> None:
    # 1. Ideal area: all dimensions good
    good_area = {
        "id": "area-good",
        "observation_count": 8,
        "newest_evidence_age_days": 30,
        "source_types": ["phone", "field", "village_meeting"],
        "needs_survey": False,
        "survey_completed": True,
        "unresolved_conflicts_count": 0,
        "unresolved_duplicates_count": 0,
        "calibration_status": "CALIBRATED",
    }
    res = assess_area_data_quality(good_area)
    assert res["overall_status"] == "SUFFICIENT"
    assert res["overall_label_ko"] == OVERALL_LABELS_KO["SUFFICIENT"]
    for dim, level in res["dimensions"].items():
        assert level in QUALITY_LEVELS
        assert level == "GOOD"
        assert res["dimension_labels_ko"][dim]["label"] == LEVEL_LABELS_KO["GOOD"]


def test_data_quality_uncalibrated_is_provenance_warning_not_hard_block() -> None:
    # Area has sufficient observations and no conflicts, but uncalibrated
    area = {
        "id": "area-uncalibrated",
        "observation_count": 6,
        "newest_evidence_age_days": 45,
        "source_types": ["phone", "field", "village_meeting"],
        "needs_survey": False,
        "survey_completed": True,
        "unresolved_conflicts_count": 0,
        "unresolved_duplicates_count": 0,
        "calibration_status": "UNCALIBRATED",
    }
    res = assess_area_data_quality(area)
    assert res["overall_status"] == "SUFFICIENT"
    assert any("미보정" in w for w in res["provenance_warnings"])


def test_data_quality_stale_or_conflicts_trigger_survey_required() -> None:
    # 1. Stale evidence (> 180 days)
    stale_area = {
        "id": "area-stale",
        "observation_count": 10,
        "newest_evidence_age_days": 210,
        "source_types": ["phone", "field"],
        "needs_survey": False,
        "unresolved_conflicts_count": 0,
    }
    res_stale = assess_area_data_quality(stale_area)
    assert res_stale["overall_status"] == "SURVEY_REQUIRED"
    assert res_stale["dimensions"]["RECENCY"] == "POOR"

    # 2. Unresolved conflicts
    conflict_area = {
        "id": "area-conflict",
        "observation_count": 6,
        "newest_evidence_age_days": 20,
        "source_types": ["phone", "field"],
        "unresolved_conflicts_count": 2,
    }
    res_conflict = assess_area_data_quality(conflict_area)
    assert res_conflict["overall_status"] == "SURVEY_REQUIRED"
    assert res_conflict["dimensions"]["CONFLICT_STATUS"] == "POOR"


def test_data_quality_aging_or_sparse_observations_trigger_limited() -> None:
    # Aging evidence (120 days) with 3 observations
    limited_area = {
        "id": "area-limited",
        "observation_count": 3,
        "newest_evidence_age_days": 120,
        "source_types": ["phone", "village_meeting"],
        "needs_survey": False,
        "survey_completed": True,
        "unresolved_conflicts_count": 0,
        "unresolved_duplicates_count": 0,
    }
    res = assess_area_data_quality(limited_area)
    assert res["overall_status"] == "LIMITED"
    assert res["overall_label_ko"] == "제한적 계획 가능"
    assert res["dimensions"]["OBSERVATION_COVERAGE"] == "LIMITED"
    assert res["dimensions"]["RECENCY"] == "LIMITED"
