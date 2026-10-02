from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import database
from backend.demand import assess_evidence
from backend.evidence_policy import (
    evidence_age_days,
    evidence_freshness,
    forecast_evidence_eligible,
    planning_evidence_eligible,
)
from backend.main import _apply_existing_service_history, _assessment_for_area, app

ROOT = Path(__file__).resolve().parents[1]


def _demo_data() -> dict:
    return json.loads((ROOT / "data" / "demo.json").read_text(encoding="utf-8"))


def _connect(path: Path):
    connection = database.connect(path)
    data = _demo_data()
    database.seed_reference_data(connection, data)
    area = dict(data["areas"][0])
    return connection, area


def _insert_survey(connection, area_id: str, survey_date: date, *, source: str, frequency: int):
    return database.insert_survey(
        connection,
        area_id=area_id,
        survey_type=source,
        survey_date=survey_date.isoformat(),
        service_type="laundry",
        frequency_per_month=frequency,
        preferred_period=None,
        preferred_days=[],
        constraints=[],
        free_text_note=f"{source} 조사, 월 {frequency}회 요청",
        source_text_was_redacted=False,
        provenance="TEST_EVIDENCE",
    )


def test_evidence_age_boundaries_and_future_date_rejection() -> None:
    today = date(2026, 10, 2)

    assert evidence_freshness(today - timedelta(days=90), as_of=today) == "FRESH"
    assert evidence_freshness(today - timedelta(days=91), as_of=today) == "AGING"
    assert evidence_freshness(today - timedelta(days=180), as_of=today) == "AGING"
    assert evidence_freshness(today - timedelta(days=181), as_of=today) == "STALE"
    assert planning_evidence_eligible(today - timedelta(days=180), as_of=today)
    assert not planning_evidence_eligible(today - timedelta(days=181), as_of=today)
    assert forecast_evidence_eligible(today - timedelta(days=120), as_of=today)
    assert not forecast_evidence_eligible(today - timedelta(days=121), as_of=today)
    with pytest.raises(ValueError, match="future"):
        evidence_age_days(today + timedelta(days=1), as_of=today)


def test_stale_only_evidence_is_retained_but_excluded_from_planning_and_recommends_survey(
    tmp_path, monkeypatch
) -> None:
    today = date(2026, 10, 2)
    monkeypatch.setattr(database, "korea_today", lambda: today)
    monkeypatch.setattr("backend.main.korea_today", lambda: today)
    connection, area = _connect(tmp_path / "stale-only.sqlite")
    try:
        old_id = _insert_survey(
            connection, area["id"], today - timedelta(days=181), source="phone", frequency=3
        )

        review = database.evidence_review(connection, area["id"])
        assessment, surveys = _assessment_for_area(
            area, connection, baseline_count=0, service_type="laundry"
        )
        area["simulated_monthly_demand"] = 0
        area["population_adjusted_baseline_units"] = 0
        _apply_existing_service_history(area, connection, surveys=surveys)

        assert review["freshness_summary"] == {"FRESH": 0, "AGING": 0, "STALE": 1}
        assert review["resurvey_recommended"] is True
        assert review["evidence"][0]["freshness_status"] == "STALE"
        assert assessment["stale_evidence_count"] == 1
        assert assessment["needs_survey"] is True
        assert area["survey_frequency_floor_monthly"] is None
        assert database.list_surveys(connection, area["id"])[0]["survey_id"] == old_id
    finally:
        connection.close()


def test_fresh_and_stale_mix_downgrades_quality_and_new_survey_reassesses_planning(
    tmp_path, monkeypatch
) -> None:
    today = date(2026, 10, 2)
    monkeypatch.setattr(database, "korea_today", lambda: today)
    monkeypatch.setattr("backend.main.korea_today", lambda: today)
    connection, area = _connect(tmp_path / "fresh-plus-stale.sqlite")
    try:
        _insert_survey(
            connection, area["id"], today - timedelta(days=181), source="phone", frequency=2
        )
        initial_review = database.evidence_review(connection, area["id"])
        assert initial_review["resurvey_recommended"] is True

        _insert_survey(connection, area["id"], today, source="field", frequency=4)
        review = database.evidence_review(connection, area["id"])
        assessment, surveys = _assessment_for_area(
            area, connection, baseline_count=0, service_type="laundry"
        )
        area["simulated_monthly_demand"] = 0
        area["population_adjusted_baseline_units"] = 0
        _apply_existing_service_history(area, connection, surveys=surveys)

        assert review["freshness_summary"] == {"FRESH": 1, "AGING": 0, "STALE": 1}
        assert review["resurvey_recommended"] is False
        assert assessment["stale_evidence_count"] == 1
        no_stale_assessment = assess_evidence(
            observation_count=2,
            survey_count=2,
            fresh_evidence_count=1,
            source_diversity=2,
            missingness=0,
            latest_observation_date=today,
            today=today,
        )
        assert assessment["deterministic_confidence"] < no_stale_assessment.deterministic_confidence
        assert area["survey_frequency_observation_count"] == 1
        assert area["survey_frequency_floor_monthly"] == 4
    finally:
        connection.close()


def test_database_rejects_future_survey_and_draft_dates(tmp_path, monkeypatch) -> None:
    today = date(2026, 10, 2)
    monkeypatch.setattr(database, "korea_today", lambda: today)
    connection, area = _connect(tmp_path / "future-evidence.sqlite")
    try:
        with pytest.raises(ValueError, match="future"):
            _insert_survey(
                connection, area["id"], today + timedelta(days=1), source="phone", frequency=2
            )
        with pytest.raises(ValueError, match="future"):
            database.insert_demand_structuring_draft(
                connection,
                area_id=area["id"],
                survey_type="phone",
                survey_date=(today + timedelta(days=1)).isoformat(),
                source_text_redacted="세탁 요청",
                source_text_was_redacted=False,
                structured={"requests": []},
            )
    finally:
        connection.close()


def test_survey_api_rejects_future_date(tmp_path, monkeypatch) -> None:
    today = date(2026, 10, 2)
    area = _demo_data()["areas"][0]
    monkeypatch.setattr("backend.main.korea_today", lambda: today)
    monkeypatch.setattr(database, "korea_today", lambda: today)
    monkeypatch.setenv("VILLAGECOVERAGE_APP_DB", str(tmp_path / "future-survey-api.sqlite"))

    response = TestClient(app).post(
        f"/api/villages/{area['id']}/surveys",
        json={
            "survey_type": "phone",
            "survey_date": (today + timedelta(days=1)).isoformat(),
            "service_type": "laundry",
            "frequency_per_month": 2,
            "free_text_note": "future survey",
        },
    )

    assert response.status_code == 422
    assert "오늘 이후" in response.json()["detail"]
