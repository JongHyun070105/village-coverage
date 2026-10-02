from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient

from backend.backtest import run_rolling_origin_backtest
from backend.main import app


def _shift_month(value: date, offset: int) -> date:
    absolute_month = value.year * 12 + value.month - 1 + offset
    return date(absolute_month // 12, absolute_month % 12 + 1, 1)


def history(*, area_count: int = 3, holdout_value: int = 8) -> list[dict[str, object]]:
    start = date(2025, 1, 1)
    rows: list[dict[str, object]] = []
    for month_offset in range(9):
        month = _shift_month(start, month_offset)
        for area_index in range(area_count):
            rows.append(
                {
                    "area_id": f"area-{area_index + 1}",
                    "occurred_on": date(month.year, month.month, 15).isoformat(),
                    "source_type": "phone" if area_index < 2 else "field",
                    "frequency_per_month": (
                        holdout_value if month_offset >= 6 else 2 + area_index + month_offset % 2
                    ),
                    "created_at": f"{month.year}-{month.month:02d}-16T00:00:00+00:00",
                    "provenance": "SIMULATED TEST HISTORY",
                }
            )
    return rows


def backtest(rows: list[dict[str, object]], *, area_count: int = 3) -> dict:
    return run_rolling_origin_backtest(
        region_id="test-region",
        region_name="테스트 지역",
        service_type="laundry",
        region_area_count=area_count,
        observations=rows,
    )


def test_rolling_origin_trains_only_through_cutoff_and_scores_three_holdout_months() -> None:
    rows = history(holdout_value=8)
    result = backtest(rows)
    cutoff = next(origin for origin in result["origins"] if origin["cutoff_month"] == "2025-06")
    changed_holdout = [
        {**row, "frequency_per_month": 99} if row["occurred_on"] >= "2025-07-01" else row
        for row in rows
    ]
    repeated = backtest(changed_holdout)
    repeated_cutoff = next(
        origin for origin in repeated["origins"] if origin["cutoff_month"] == "2025-06"
    )

    assert cutoff["training_observation_count"] == 18
    assert cutoff["training_latest_date"] == "2025-06-15"
    assert [item["target_month"] for item in cutoff["holdouts"]] == [
        "2025-07",
        "2025-08",
        "2025-09",
    ]
    assert [item["forecast_mid"] for item in cutoff["holdouts"]] == [
        item["forecast_mid"] for item in repeated_cutoff["holdouts"]
    ]
    assert [item["actual"] for item in cutoff["holdouts"]] == [24, 24, 24]
    assert result["backtest_type"] == "SYNTHETIC BACKTEST"
    assert result["metrics"]["evaluation_case_count"] == 3
    assert result["metrics"]["forecast_availability_rate"] == 1.0
    assert result["metrics"]["mae"] is not None
    assert result["metrics"]["interval_coverage"] is not None


def test_zero_actual_total_has_undefined_wape_without_division_error() -> None:
    result = backtest(history(holdout_value=0))

    assert result["metrics"]["evaluation_case_count"] == 3
    assert result["metrics"]["mae"] is not None
    assert result["metrics"]["wape"] is None
    assert result["metrics"]["wape_status"] == "UNDEFINED_ZERO_ACTUAL_TOTAL"


def test_unavailable_forecasts_count_against_availability_and_insufficiency() -> None:
    result = backtest(history(area_count=2), area_count=2)
    metrics = result["metrics"]

    assert result["metrics"]["evaluation_case_count"] == 3
    assert metrics["accuracy_scored_count"] == 0
    assert metrics["forecast_unavailable_count"] == 3
    assert metrics["forecast_availability_rate"] == 0.0
    assert metrics["insufficient_data_rate"] == 1.0
    assert metrics["mae"] is None
    assert metrics["accuracy_scope"]


def test_incomplete_holdout_truth_is_reported_outside_accuracy_denominator() -> None:
    rows = history()
    rows = [
        row
        for row in rows
        if not (row["occurred_on"] == "2025-08-15" and row["area_id"] == "area-3")
    ]
    result = backtest(rows)

    assert result["metrics"]["actual_unavailable_count"] > 0
    assert any(
        holdout["actual_status"] == "HOLDOUT_PANEL_INCOMPLETE"
        for origin in result["origins"]
        for holdout in origin["holdouts"]
    )


def test_backtest_api_marks_empty_history_as_insufficient(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("VILLAGECOVERAGE_APP_DB", str(tmp_path / "empty-backtest.sqlite"))

    response = TestClient(app).get("/api/forecasts/backtest")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "DATA_INSUFFICIENT"
    assert body["reports"]
    assert all(report["origin_count"] == 0 for report in body["reports"])
    assert all(report["backtest_type"] == "NO_EVIDENCE" for report in body["reports"])
