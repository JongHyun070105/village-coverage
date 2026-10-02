from __future__ import annotations

from datetime import date

from backend.forecast import forecast_region_service


def month_shift(value: date, offset: int) -> date:
    absolute_month = value.year * 12 + value.month - 1 + offset
    return date(absolute_month // 12, absolute_month % 12 + 1, 1)


def balanced_history(as_of: date, months: int = 6) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for offset in range(months, 0, -1):
        month = month_shift(date(as_of.year, as_of.month, 1), -offset)
        for area_index in range(3):
            rows.append(
                {
                    "area_id": f"area-{area_index + 1}",
                    "occurred_on": date(month.year, month.month, 15).isoformat(),
                    "source_type": "phone" if area_index < 2 else "field",
                    "frequency_per_month": 2 + area_index + (month.month % 2),
                    "created_at": f"{month.year}-{month.month:02d}-16T00:00:00+00:00",
                }
            )
    return rows


def test_insufficient_history_returns_no_forecast_values() -> None:
    rows = balanced_history(date(2026, 10, 1), months=5)
    result = forecast_region_service(
        region_id="region-1",
        region_name="충청남도 홍성군 장곡면",
        service_type="laundry",
        region_area_count=3,
        observations=rows,
        as_of=date(2026, 10, 1),
    )

    assert result["status"] == "DATA_INSUFFICIENT"
    assert len(result["months"]) == 3
    assert all(month["expected_rounds_low"] is None for month in result["months"])
    assert all(month["expected_rounds_mid"] is None for month in result["months"])
    assert all(month["expected_rounds_high"] is None for month in result["months"])
    assert all(month["survey_required"] for month in result["months"])


def test_sufficient_balanced_history_returns_deterministic_three_month_ranges() -> None:
    rows = balanced_history(date(2026, 10, 1))
    arguments = {
        "region_id": "region-1",
        "region_name": "충청남도 홍성군 장곡면",
        "service_type": "laundry",
        "region_area_count": 3,
        "observations": rows,
        "as_of": date(2026, 10, 1),
    }

    result = forecast_region_service(**arguments)
    repeated = forecast_region_service(**arguments)
    reordered = forecast_region_service(**{**arguments, "observations": list(reversed(rows))})

    assert result == repeated
    assert result == reordered
    assert result["status"] == "AVAILABLE"
    assert [month["month"] for month in result["months"]] == ["2026-10", "2026-11", "2026-12"]
    assert all(month["expected_rounds_low"] is not None for month in result["months"])
    assert all(
        month["expected_rounds_low"] <= month["expected_rounds_mid"] for month in result["months"]
    )
    assert all(
        month["expected_rounds_mid"] <= month["expected_rounds_high"] for month in result["months"]
    )
    assert all(month["confidence"] == "MEDIUM" for month in result["months"])
    assert all(month["model_basis"] == "ROLLING_MEDIAN_MAD" for month in result["months"])
    assert all(month["latest_evidence_freshness"] == "FRESH" for month in result["months"])
    assert all(month["latest_evidence_age_days"] == 16 for month in result["months"])


def test_sparse_area_panel_is_not_extrapolated_to_a_region_forecast() -> None:
    rows = balanced_history(date(2026, 10, 1))
    result = forecast_region_service(
        region_id="region-1",
        region_name="충청남도 홍성군 장곡면",
        service_type="laundry",
        region_area_count=16,
        observations=rows,
        as_of=date(2026, 10, 1),
    )

    assert result["status"] == "DATA_INSUFFICIENT"
    assert all(month["expected_rounds_mid"] is None for month in result["months"])
    assert all(
        "AREA_COVERAGE_TOO_LOW" in month["insufficiency_reasons"] for month in result["months"]
    )


def test_incomplete_month_or_small_area_panel_does_not_become_zero_demand() -> None:
    as_of = date(2026, 10, 1)
    rows = balanced_history(as_of)
    rows = [
        row
        for row in rows
        if not (row["area_id"] == "area-1" and row["occurred_on"] == "2026-07-15")
    ]
    result = forecast_region_service(
        region_id="region-1",
        region_name="충청남도 홍성군 장곡면",
        service_type="laundry",
        region_area_count=3,
        observations=rows,
        as_of=as_of,
    )

    assert result["status"] == "DATA_INSUFFICIENT"
    assert all(month["expected_rounds_mid"] is None for month in result["months"])
    assert all(
        "AREA_PANEL_TOO_SMALL" in month["insufficiency_reasons"] for month in result["months"]
    )


def test_repeated_seasonal_observations_use_the_same_month_feature() -> None:
    as_of = date(2026, 10, 1)
    rows = balanced_history(as_of, months=24)
    result = forecast_region_service(
        region_id="region-1",
        region_name="충청남도 홍성군 장곡면",
        service_type="laundry",
        region_area_count=3,
        observations=rows,
        as_of=as_of,
    )

    assert result["status"] == "AVAILABLE"
    assert result["months"][0]["month"] == "2026-10"
    assert result["months"][0]["model_basis"] == "SEASONAL_MEDIAN_MAD"
    assert result["months"][0]["history_month_count"] == 24
