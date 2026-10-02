from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from backend import database
from backend.calibration import (
    MIN_SAMPLE_SIZE_FOR_CALIBRATED,
    MIN_SAMPLE_SIZE_FOR_LIMITED_SAMPLE,
    calibration_confidence,
    compute_calibration_status,
)
from backend.database import latest_calibration_profiles, record_calibration_profile
from backend.main import app
from backend.regions import DEFAULT_REGION_ID

ROOT = Path(__file__).resolve().parents[1]


def _demo_data() -> dict:
    return json.loads((ROOT / "data" / "demo.json").read_text(encoding="utf-8"))


def test_synthetic_prior_never_counts_as_calibrated() -> None:
    assert compute_calibration_status(sample_size=10_000, source_type="SIMULATED_PRIOR") == (
        "UNCALIBRATED"
    )


def test_zero_sample_is_uncalibrated_regardless_of_source() -> None:
    assert compute_calibration_status(sample_size=0, source_type="FIELD_OBSERVED") == "UNCALIBRATED"


def test_small_real_sample_is_limited_sample() -> None:
    status = compute_calibration_status(
        sample_size=MIN_SAMPLE_SIZE_FOR_LIMITED_SAMPLE, source_type="SURVEY_OBSERVED"
    )
    assert status == "LIMITED_SAMPLE"


def test_below_limited_floor_stays_uncalibrated() -> None:
    status = compute_calibration_status(
        sample_size=MIN_SAMPLE_SIZE_FOR_LIMITED_SAMPLE - 1, source_type="SURVEY_OBSERVED"
    )
    assert status == "UNCALIBRATED"


def test_sufficient_real_sample_is_calibrated() -> None:
    status = compute_calibration_status(
        sample_size=MIN_SAMPLE_SIZE_FOR_CALIBRATED, source_type="FIELD_OBSERVED"
    )
    assert status == "CALIBRATED"


def test_confidence_is_none_when_uncalibrated() -> None:
    assert calibration_confidence(sample_size=500, status="UNCALIBRATED") is None
    assert calibration_confidence(sample_size=15, status="LIMITED_SAMPLE") is not None


def test_recorded_profile_rejects_caller_supplied_status(tmp_path) -> None:
    connection = database.connect(tmp_path / "calibration.sqlite")
    try:
        database.seed_reference_data(connection, _demo_data())
        profile = record_calibration_profile(
            connection,
            region_id=DEFAULT_REGION_ID,
            service_type="laundry",
            sample_size=3,
            observed_period_start="2026-01-01",
            observed_period_end="2026-03-01",
            raw_rate=1.2,
            source_type="SURVEY_OBSERVED",
            provenance="TEST",
        )
        assert profile["status"] == "UNCALIBRATED"
        assert profile["calibrated_rate"] is None
        assert profile["version"] == 1

        second = record_calibration_profile(
            connection,
            region_id=DEFAULT_REGION_ID,
            service_type="laundry",
            sample_size=MIN_SAMPLE_SIZE_FOR_CALIBRATED,
            observed_period_start="2026-01-01",
            observed_period_end="2026-06-01",
            raw_rate=1.5,
            source_type="FIELD_OBSERVED",
            provenance="TEST",
        )
        assert second["status"] == "CALIBRATED"
        assert second["calibrated_rate"] == 1.5
        assert second["version"] == 2
    finally:
        connection.close()


def test_sample_without_rate_remains_uncalibrated(tmp_path) -> None:
    connection = database.connect(tmp_path / "calibration-without-rate.sqlite")
    try:
        database.seed_reference_data(connection, _demo_data())
        profile = record_calibration_profile(
            connection,
            region_id=DEFAULT_REGION_ID,
            service_type="laundry",
            sample_size=MIN_SAMPLE_SIZE_FOR_CALIBRATED,
            observed_period_start="2026-01-01",
            observed_period_end="2026-06-01",
            raw_rate=None,
            source_type="SURVEY_OBSERVED",
            provenance="TEST",
        )

        assert profile["status"] == "UNCALIBRATED"
        assert profile["calibrated_rate"] is None
    finally:
        connection.close()


def test_latest_profiles_cover_every_registered_service_even_without_attempts(tmp_path) -> None:
    connection = database.connect(tmp_path / "calibration.sqlite")
    try:
        profiles = latest_calibration_profiles(connection, DEFAULT_REGION_ID)
        statuses = {profile["service_type"]: profile["status"] for profile in profiles}
        assert statuses["laundry"] == "UNCALIBRATED"
        assert all(status == "UNCALIBRATED" for status in statuses.values())
    finally:
        connection.close()


def test_calibration_api_exposes_uncalibrated_state_by_default(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("VILLAGECOVERAGE_APP_DB", str(tmp_path / "api-calibration.sqlite"))
    client = TestClient(app)
    response = client.get(f"/api/regions/{DEFAULT_REGION_ID}/calibration")
    assert response.status_code == 200
    body = response.json()
    assert body["planning_demand_label"] == "Synthetic prior"
    assert all(profile["status"] == "UNCALIBRATED" for profile in body["profiles"])


def test_calibration_api_records_and_reflects_new_observation(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("VILLAGECOVERAGE_APP_DB", str(tmp_path / "api-calibration-2.sqlite"))
    client = TestClient(app)
    response = client.post(
        f"/api/regions/{DEFAULT_REGION_ID}/calibration",
        json={
            "service_type": "laundry",
            "sample_size": MIN_SAMPLE_SIZE_FOR_CALIBRATED,
            "observed_period_start": "2026-01-01",
            "observed_period_end": "2026-06-01",
            "raw_rate": 2.0,
            "source_type": "FIELD_OBSERVED",
        },
    )
    assert response.status_code == 201
    assert response.json()["profile"]["status"] == "CALIBRATED"

    listing = client.get(f"/api/regions/{DEFAULT_REGION_ID}/calibration")
    laundry = next(p for p in listing.json()["profiles"] if p["service_type"] == "laundry")
    assert laundry["status"] == "CALIBRATED"


def test_calibration_api_rejects_unknown_region() -> None:
    client = TestClient(app)
    response = client.get("/api/regions/not-a-real-region/calibration")
    assert response.status_code == 422


def test_calibration_api_rejects_unknown_service_type() -> None:
    client = TestClient(app)
    response = client.post(
        f"/api/regions/{DEFAULT_REGION_ID}/calibration",
        json={
            "service_type": "not_a_service",
            "sample_size": 10,
            "source_type": "SURVEY_OBSERVED",
        },
    )
    assert response.status_code == 422


def test_calibration_api_rejects_inverted_period() -> None:
    client = TestClient(app)
    response = client.post(
        f"/api/regions/{DEFAULT_REGION_ID}/calibration",
        json={
            "service_type": "laundry",
            "sample_size": 10,
            "observed_period_start": "2026-06-01",
            "observed_period_end": "2026-01-01",
            "source_type": "SURVEY_OBSERVED",
        },
    )
    assert response.status_code == 422
