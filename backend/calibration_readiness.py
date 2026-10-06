"""Conservative local calibration readiness from confirmed pilot imports."""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from datetime import date
from typing import Any

LOCAL_OBSERVATION_SOURCES = frozenset(
    {"LOCAL_AUTHORITY_INPUT", "SURVEY_INPUT", "RESIDENT_FEEDBACK"}
)
CALIBRATION_MIN_SAMPLE = 30
CALIBRATION_MIN_DAYS = 90
CALIBRATION_MAX_AGE_DAYS = 180
OPERATIONAL_MIN_LOGS = 30
OPERATIONAL_SOURCE_TYPES = frozenset({"LOCAL_AUTHORITY_INPUT", "PROVIDER_SELF_REPORTED"})
OPERATIONAL_MAX_AGE_DAYS = 180
OPERATIONAL_FUTURE_WINDOW_DAYS = 90


def _fresh_operational_count(records: list[dict[str, Any]], date_field: str, today: date) -> int:
    count = 0
    for item in records:
        try:
            recorded = date.fromisoformat(str(item.get(date_field)))
        except (ValueError, TypeError):
            continue
        age = (today - recorded).days
        if -OPERATIONAL_FUTURE_WINDOW_DAYS <= age <= OPERATIONAL_MAX_AGE_DAYS:
            count += 1
    return count


def _confirmed_records(
    connection: sqlite3.Connection, template_type: str, context_id: str | None = None
) -> list[dict[str, Any]]:
    if context_id is not None:
        rows = connection.execute(
            """SELECT promoted_id AS record_id,row_fingerprint,source_type,payload_json
               FROM pilot_promoted_records WHERE context_id=? AND template_type=?""",
            (context_id, template_type),
        )
        result = []
        for row in rows:
            record = json.loads(row["payload_json"])
            result.append(
                {
                    "record_id": str(row["record_id"]),
                    "row_fingerprint": str(row["row_fingerprint"]),
                    "source_type": str(row["source_type"]),
                    **record,
                }
            )
        return result
    rows = connection.execute(
        """SELECT record_id,row_fingerprint,source_type,normalized_json
           FROM pilot_import_records WHERE template_type=?""",
        (template_type,),
    )
    result = []
    for row in rows:
        record = json.loads(row["normalized_json"])
        result.append(
            {
                "record_id": str(row["record_id"]),
                "row_fingerprint": str(row["row_fingerprint"]),
                "source_type": str(row["source_type"]),
                **record,
            }
        )
    return result


def _matches(
    record: dict[str, Any], region_code: str | None, area_code: str | None, service_type: str
) -> bool:
    if record.get("service_type") not in {None, "", service_type}:
        return False
    if area_code and record.get("area_code") not in {None, "", area_code}:
        return False
    if region_code and record.get("region_code") not in {None, "", region_code}:
        return False
    return True


def calibration_readiness(
    connection: sqlite3.Connection,
    *,
    service_type: str,
    region_code: str | None = None,
    area_code: str | None = None,
    context_id: str | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    """Report dimensions and gate status; never recalibrates forecasts."""
    today = today or date.today()
    demand = [
        item
        for item in _confirmed_records(connection, "demand_observations", context_id)
        if _matches(item, region_code, area_code, service_type)
        and item.get("source_type") in LOCAL_OBSERVATION_SOURCES
    ]
    surveys = [
        item
        for item in _confirmed_records(connection, "surveys", context_id)
        if _matches(item, region_code, area_code, service_type)
        and item.get("source_type") in LOCAL_OBSERVATION_SOURCES
    ]
    observation_records = demand + surveys
    unique_fingerprints = {item["row_fingerprint"] for item in observation_records}
    observation_dates: list[date] = []
    source_types: set[str] = set()
    for item in observation_records:
        value = item.get("observed_date") or item.get("survey_date")
        try:
            observation_dates.append(date.fromisoformat(str(value)))
            source_types.add(str(item["source_type"]))
        except (ValueError, TypeError):
            continue
    time_span = (
        (max(observation_dates) - min(observation_dates)).days if len(observation_dates) >= 2 else 0
    )
    latest = max(observation_dates) if observation_dates else None
    age_days = (today - latest).days if latest else None
    survey_coverages = []
    populations = []
    for item in surveys:
        try:
            population = int(item.get("eligible_population") or 0)
            respondents = int(item.get("survey_count") or 0)
            populations.append(population)
            if population > 0:
                survey_coverages.append(min(1.0, respondents / population))
        except (ValueError, TypeError):
            continue
    denominator = max(populations, default=0)
    survey_completeness = max(survey_coverages, default=None)

    conflict_groups: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    for item in observation_records:
        event_date = str(item.get("observed_date") or item.get("survey_date") or "")
        area = str(item.get("area_code") or area_code or "")
        value = str(item.get("observed_count") or item.get("survey_count") or "")
        conflict_groups[(area, event_date, service_type)].add(value)
    conflict_count = sum(len(values) > 1 for values in conflict_groups.values())

    execution = [
        item
        for item in _confirmed_records(connection, "service_execution_logs", context_id)
        if _matches(item, region_code, area_code, service_type)
        and item.get("source_type") == "SERVICE_EXECUTION_LOG"
        and item.get("execution_status") == "COMPLETED"
    ]
    execution_dates = []
    for item in execution:
        try:
            execution_dates.append(
                date.fromisoformat(str(item.get("executed_date") or item.get("scheduled_date")))
            )
        except (ValueError, TypeError):
            continue
    execution_span = (
        (max(execution_dates) - min(execution_dates)).days if len(execution_dates) >= 2 else 0
    )

    availability = [
        item
        for item in _confirmed_records(connection, "provider_availability", context_id)
        if _matches(item, region_code, area_code, service_type)
        and item.get("source_type") in OPERATIONAL_SOURCE_TYPES
    ]
    fresh_availability = _fresh_operational_count(availability, "available_date", today)
    capacity = [
        item
        for item in _confirmed_records(connection, "provider_capacity", context_id)
        if _matches(item, region_code, area_code, service_type)
        and item.get("source_type") in OPERATIONAL_SOURCE_TYPES
    ]
    fresh_capacity = _fresh_operational_count(capacity, "period_end", today)
    prices = [
        item
        for item in _confirmed_records(connection, "provider_prices", context_id)
        if _matches(item, region_code, area_code, service_type)
        and item.get("source_type") in OPERATIONAL_SOURCE_TYPES
        and item.get("price_won") not in {None, ""}
    ]
    fresh_prices = _fresh_operational_count(prices, "effective_date", today)
    participation = [
        item
        for item in _confirmed_records(connection, "provider_participation", context_id)
        if _matches(item, region_code, area_code, service_type)
        and item.get("source_type") in OPERATIONAL_SOURCE_TYPES
        and item.get("participation_status") in {"OPTED_IN", "DECLINED", "UNAVAILABLE"}
    ]
    fresh_participation = _fresh_operational_count(participation, "recorded_at", today)

    requirements = {
        "unique_observations": len(unique_fingerprints) >= CALIBRATION_MIN_SAMPLE,
        "observation_period": time_span >= CALIBRATION_MIN_DAYS,
        "eligible_population": denominator > 0,
        "survey_completeness": survey_completeness is not None and survey_completeness >= 0.8,
        "source_diversity": len(source_types) >= 2,
        "freshness": age_days is not None and 0 <= age_days <= CALIBRATION_MAX_AGE_DAYS,
        "unresolved_conflicts": conflict_count == 0,
    }
    if observation_records and not all(requirements.values()):
        status = "LIMITED_SAMPLE"
    elif observation_records:
        status = "LOCAL_CALIBRATED"
    else:
        status = "UNCALIBRATED"
    operational_requirements = {
        "completed_execution_logs": len({item["row_fingerprint"] for item in execution})
        >= OPERATIONAL_MIN_LOGS,
        "operational_period": execution_span >= CALIBRATION_MIN_DAYS,
        "provider_availability": fresh_availability > 0,
        "provider_capacity": fresh_capacity > 0,
        "actual_price": fresh_prices > 0,
        "participation_decision": fresh_participation > 0,
    }
    if status == "LOCAL_CALIBRATED" and all(operational_requirements.values()):
        status = "LOCAL_VALIDATED_OPERATIONAL"

    return {
        "status": status,
        "region_code": region_code,
        "area_code": area_code,
        "service_type": service_type,
        "dimensions": {
            "local_observations": {
                "status": "READY" if observation_records else "MISSING",
                "unique_count": len(unique_fingerprints),
            },
            "observation_period": {
                "status": "READY" if time_span >= CALIBRATION_MIN_DAYS else "LIMITED",
                "days": time_span,
                "required_days": CALIBRATION_MIN_DAYS,
            },
            "eligible_population": {
                "status": "READY" if denominator > 0 else "MISSING",
                "eligible_population": denominator or None,
                "survey_completeness": survey_completeness,
            },
            "source_diversity": {
                "status": "READY" if len(source_types) >= 2 else "LIMITED",
                "source_types": sorted(source_types),
                "required_sources": 2,
            },
            "freshness": {
                "status": "READY" if requirements["freshness"] else "MISSING",
                "age_days": age_days,
                "maximum_days": CALIBRATION_MAX_AGE_DAYS,
            },
            "conflicts": {
                "status": "READY" if conflict_count == 0 else "REVIEW_REQUIRED",
                "unresolved_count": conflict_count,
            },
            "operational_execution": {
                "status": "READY" if all(operational_requirements.values()) else "MISSING",
                "completed_logs": len(execution),
                "period_days": execution_span,
                "required_logs": OPERATIONAL_MIN_LOGS,
            },
            "provider_availability": {
                "status": "READY" if fresh_availability else "MISSING",
                "recent_records": fresh_availability,
            },
            "provider_capacity": {
                "status": "READY" if fresh_capacity else "MISSING",
                "recent_records": fresh_capacity,
            },
            "provider_price": {
                "status": "READY" if fresh_prices else "MISSING",
                "recent_records": fresh_prices,
            },
            "provider_participation": {
                "status": "READY" if fresh_participation else "MISSING",
                "recent_records": fresh_participation,
            },
        },
        "missing_requirements": [key for key, ready in requirements.items() if not ready],
        "operational_missing_requirements": [
            key for key, ready in operational_requirements.items() if not ready
        ],
        "promotion_policy": {
            "minimum_unique_observations": CALIBRATION_MIN_SAMPLE,
            "minimum_observation_period_days": CALIBRATION_MIN_DAYS,
            "minimum_source_types": 2,
            "minimum_survey_completeness": 0.8,
            "maximum_age_days": CALIBRATION_MAX_AGE_DAYS,
            "minimum_completed_execution_logs": OPERATIONAL_MIN_LOGS,
            "minimum_operational_period_days": CALIBRATION_MIN_DAYS,
            "maximum_operational_fact_age_days": OPERATIONAL_MAX_AGE_DAYS,
            "operational_fact_future_window_days": OPERATIONAL_FUTURE_WINDOW_DAYS,
            "volume_alone_promotes": False,
            "automatic_model_recalibration": False,
        },
        "note": "준비도 보고서이며 예측값·계획 입력을 자동 보정하지 않습니다.",
    }
