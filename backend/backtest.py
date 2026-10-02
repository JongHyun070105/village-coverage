"""Rolling-origin evaluation for evidence-gated regional demand forecasts."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any

from backend.evidence_policy import freshness_policy_payload
from backend.forecast import forecast_region_service

BACKTEST_HORIZONS = (1, 2, 3)
MAX_BACKTEST_ORIGINS = 24


def _month_start(value: date) -> date:
    return date(value.year, value.month, 1)


def _shift_month(value: date, offset: int) -> date:
    absolute_month = value.year * 12 + value.month - 1 + offset
    return date(absolute_month // 12, absolute_month % 12 + 1, 1)


def _month_key(value: date) -> str:
    return value.strftime("%Y-%m")


def _normalize_rows(observations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = []
    for row in observations:
        try:
            occurred_on = date.fromisoformat(str(row["occurred_on"]))
            area_id = str(row["area_id"])
            frequency = row.get("frequency_per_month")
            frequency = int(frequency) if frequency is not None else None
        except (KeyError, TypeError, ValueError):
            continue
        if not area_id or frequency is not None and frequency < 0:
            continue
        normalized.append({**row, "area_id": area_id, "occurred_on": occurred_on})
    return normalized


def _monthly_latest(
    observations: list[dict[str, Any]],
) -> dict[tuple[str, date], dict[str, Any]]:
    latest: dict[tuple[str, date], dict[str, Any]] = {}
    for row in observations:
        frequency = row.get("frequency_per_month")
        if frequency is None:
            continue
        month = _month_start(row["occurred_on"])
        key = (str(row["area_id"]), month)
        current = latest.get(key)
        if current is None or (row["occurred_on"], str(row.get("created_at", ""))) > (
            current["occurred_on"],
            str(current.get("created_at", "")),
        ):
            latest[key] = row
    return latest


def _provenance_label(observations: list[dict[str, Any]]) -> str:
    if not observations:
        return "NO_EVIDENCE"
    provenances = [str(row.get("provenance", "")).upper() for row in observations]
    if all("SIMULATED" in value or "SYNTHETIC" in value for value in provenances):
        return "SYNTHETIC BACKTEST"
    if any("CSV_IMPORT" in value for value in provenances):
        return "USER_IMPORTED; REALITY NOT VERIFIED"
    return "PROVENANCE_UNVERIFIED"


def _metrics(cases: list[dict[str, Any]]) -> dict[str, Any]:
    truth_cases = [case for case in cases if case["actual"] is not None]
    scored = [case for case in truth_cases if case["forecast_mid"] is not None]
    unavailable_count = len(truth_cases) - len(scored)
    absolute_errors = [abs(case["forecast_mid"] - case["actual"]) for case in scored]
    signed_errors = [case["forecast_mid"] - case["actual"] for case in scored]
    actual_total = sum(case["actual"] for case in scored)
    wape = sum(absolute_errors) / actual_total if actual_total > 0 else None
    interval_cases = [
        case
        for case in scored
        if case["forecast_low"] is not None and case["forecast_high"] is not None
    ]
    interval_hits = sum(
        case["forecast_low"] <= case["actual"] <= case["forecast_high"] for case in interval_cases
    )
    case_count = len(truth_cases)
    available_count = len(scored)
    return {
        "evaluation_case_count": case_count,
        "accuracy_scored_count": available_count,
        "forecast_unavailable_count": unavailable_count,
        "actual_unavailable_count": sum(case["actual"] is None for case in cases),
        "forecast_availability_rate": available_count / case_count if case_count else None,
        "insufficient_data_rate": unavailable_count / case_count if case_count else None,
        "mae": sum(absolute_errors) / len(absolute_errors) if absolute_errors else None,
        "wape": wape,
        "wape_status": (
            "NO_AVAILABLE_FORECASTS"
            if not scored
            else "UNDEFINED_ZERO_ACTUAL_TOTAL"
            if actual_total == 0
            else "DEFINED"
        ),
        "bias": sum(signed_errors) / len(signed_errors) if signed_errors else None,
        "interval_coverage": interval_hits / len(interval_cases) if interval_cases else None,
        "interval_scored_count": len(interval_cases),
        "accuracy_scope": (
            "MAE, WAPE, bias and interval coverage score only generated forecasts with an observed "
            "holdout actual. Unavailable forecasts are counted in availability and "
            "insufficient-data "
            "rates; missing holdout actuals are reported separately."
        ),
    }


def run_rolling_origin_backtest(
    *,
    region_id: str,
    region_name: str,
    service_type: str,
    region_area_count: int,
    observations: list[dict[str, Any]],
    max_origins: int = MAX_BACKTEST_ORIGINS,
) -> dict[str, Any]:
    """Train through each cutoff month and evaluate the next three holdout months."""
    rows = _normalize_rows(observations)
    month_rows: dict[date, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        month_rows[_month_start(row["occurred_on"])].append(row)
    observed_months = set(month_rows)
    cutoffs = [
        month
        for month in sorted(observed_months)
        if all(_shift_month(month, horizon) in observed_months for horizon in BACKTEST_HORIZONS)
    ][-max_origins:]
    monthly_latest = _monthly_latest(rows)
    cases: list[dict[str, Any]] = []
    origin_reports: list[dict[str, Any]] = []

    for cutoff in cutoffs:
        target_start = _shift_month(cutoff, 1)
        training_rows = [row for row in rows if row["occurred_on"] < target_start]
        forecast = forecast_region_service(
            region_id=region_id,
            region_name=region_name,
            service_type=service_type,
            region_area_count=region_area_count,
            observations=training_rows,
            as_of=target_start,
            horizon_months=len(BACKTEST_HORIZONS),
            include_panel_area_ids=True,
        )
        month_results = {item["month"]: item for item in forecast["months"]}
        panel_area_ids = set(
            month_results.get(_month_key(target_start), {}).get("panel_area_ids", [])
        )
        origin_cases = []
        for horizon in BACKTEST_HORIZONS:
            target_month = _shift_month(cutoff, horizon)
            key = _month_key(target_month)
            prediction = month_results.get(key, {})
            actual_by_area = {
                area_id: int(monthly_latest[(area_id, target_month)]["frequency_per_month"])
                for area_id in panel_area_ids
                if (area_id, target_month) in monthly_latest
            }
            actual = (
                sum(actual_by_area.values())
                if panel_area_ids and len(actual_by_area) == len(panel_area_ids)
                else None
            )
            case = {
                "cutoff_month": _month_key(cutoff),
                "horizon": horizon,
                "target_month": key,
                "training_through_month": _month_key(cutoff),
                "training_observation_count": len(training_rows),
                "actual": actual,
                "actual_status": "OBSERVED" if actual is not None else "HOLDOUT_PANEL_INCOMPLETE",
                "forecast_status": prediction.get("evidence_status", "NO_FORECAST_RESULT"),
                "forecast_low": prediction.get("expected_rounds_low"),
                "forecast_mid": prediction.get("expected_rounds_mid"),
                "forecast_high": prediction.get("expected_rounds_high"),
                "model_basis": prediction.get("model_basis"),
            }
            origin_cases.append(case)
            cases.append(case)
        origin_reports.append(
            {
                "cutoff_month": _month_key(cutoff),
                "training_through_month": _month_key(cutoff),
                "training_observation_count": len(training_rows),
                "training_latest_date": max(
                    (row["occurred_on"] for row in training_rows), default=None
                ).isoformat()
                if training_rows
                else None,
                "forecast_status": forecast["status"],
                "holdouts": origin_cases,
            }
        )

    metrics = _metrics(cases)
    return {
        "region_id": region_id,
        "region_name": region_name,
        "service_type": service_type,
        "backtest_type": _provenance_label(rows),
        "method": "ROLLING_ORIGIN; TRAIN THROUGH CUTOFF; HOLDOUT T+1/T+2/T+3",
        "model": "EVIDENCE_GATED_REGIONAL_FORECAST",
        "freshness_policy": freshness_policy_payload(),
        "origin_count": len(origin_reports),
        "holdout_case_count": len(cases),
        "observed_holdout_case_count": sum(case["actual"] is not None for case in cases),
        "metrics": metrics,
        "metrics_by_horizon": {
            str(horizon): _metrics([case for case in cases if case["horizon"] == horizon])
            for horizon in BACKTEST_HORIZONS
        },
        "origins": origin_reports,
    }
