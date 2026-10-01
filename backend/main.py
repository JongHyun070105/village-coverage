"""FastAPI entry point for the VillageCoverage prototype."""

from __future__ import annotations

import csv
import io
import json
import sqlite3
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, Any, Literal
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field, field_validator
from starlette.responses import Response

from backend import database
from backend.csv_imports import (
    IMPORT_HEADERS,
    MAX_CSV_BYTES,
    CSVImportFormatError,
    parse_csv,
    prepare_import_rows,
)
from backend.demand import assess_evidence, redact_pii, structure_demand
from backend.optimization import evaluate_scenarios
from backend.regions import DEFAULT_REGION_ID, region_catalog, select_region
from backend.scheduling import generate_provider_schedule
from backend.settings import DEFAULT_ALLOWED_SERVICES, PlanningPolicy
from backend.travel import connect, get_cached, matrix_summary
from scripts.api_smoke_test import _load_config

ROOT = Path(__file__).resolve().parents[1]
DEMO_DATA_PATH = ROOT / "data" / "demo.json"
QUALITY_PATH = ROOT / "artifacts" / "data_quality_report.json"
SCHEMA_PATH = ROOT / "artifacts" / "public_schema_manifest.json"
DEFAULT_BUDGET = 5_000_000
_ALLOWED_SERVICES_QUERY = Query(default_factory=lambda: list(DEFAULT_ALLOWED_SERVICES))


class DemandInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(max_length=10000)


class DemandDraftInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    area_id: str = Field(min_length=1, max_length=120)
    survey_type: Literal["phone", "village_meeting", "proxy", "field"]
    survey_date: date
    text: str = Field(min_length=1, max_length=10000)


class ReviewedDemandRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    service_type: Literal["laundry", "daily_necessities", "home_repair"]
    requested_period: str | None = Field(default=None, max_length=80)
    frequency_per_month: int | None = Field(default=None, ge=1, le=31)
    desired_date: str | None = Field(default=None, pattern=r"^(?:\d{4}-\d{2}-\d{2}|\d{2}-\d{2})$")
    desired_time: str | None = Field(default=None, pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    recurring_pattern: Literal["weekly", "monthly", "seasonal", "one_time"] | None = None
    urgency: Literal["urgent"] | None = None
    urgency_evidence: str | None = Field(default=None, max_length=120)
    preferred_days: list[
        Literal["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    ] = Field(default_factory=list, max_length=7)
    excluded_days: list[
        Literal["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    ] = Field(default_factory=list, max_length=7)
    constraints: list[Annotated[str, Field(max_length=300)]] = Field(
        default_factory=list, max_length=10
    )

    @field_validator("desired_date")
    @classmethod
    def validate_desired_date(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            date.fromisoformat(value if len(value) == 10 else f"2000-{value}")
        except ValueError as exc:
            raise ValueError("desired_date는 유효한 YYYY-MM-DD 또는 MM-DD여야 합니다.") from exc
        return value


class DemandApprovalInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    requests: list[ReviewedDemandRequest] = Field(min_length=1, max_length=8)
    needs_followup_survey: bool
    followup_reason: str | None = Field(default=None, max_length=500)


class ImportRowReviewInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    note: str | None = Field(default=None, max_length=3000)


class SurveyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    survey_type: Literal["phone", "village_meeting", "proxy", "field"]
    survey_date: date
    service_type: Literal["laundry", "daily_necessities", "home_repair"]
    frequency_per_month: int | None = Field(default=None, ge=1, le=31)
    preferred_period: str | None = Field(default=None, max_length=80)
    preferred_days: list[
        Literal["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    ] = Field(default_factory=list, max_length=7)
    constraints: list[Annotated[str, Field(max_length=300)]] = Field(
        default_factory=list, max_length=10
    )
    free_text_note: str = Field(default="", max_length=3000)


class ParticipationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["OPTED_IN", "DECLINED", "UNAVAILABLE", "AVAILABLE"]


class ParticipationPreferenceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scope: Literal["MONTH", "WEEK"]
    period: str = Field(min_length=7, max_length=10)
    status: Literal["OPTED_IN", "DECLINED", "AVAILABLE"]


class PlanningPolicyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    minimum_services_per_area: int = Field(default=1, ge=1, le=8)
    elderly_priority_weight: int = Field(default=500, ge=0, le=1000)
    single_elderly_household_priority_weight: int = Field(default=500, ge=0, le=1000)
    survey_required_protection_weight: int = Field(default=1000, ge=0, le=1000)
    maximum_round_trip_travel_minutes: int | None = Field(default=None, ge=1, le=360)
    allowed_services: list[Literal["laundry", "daily_necessities", "home_repair"]] = Field(
        default_factory=lambda: list(DEFAULT_ALLOWED_SERVICES), min_length=1, max_length=3
    )
    minimum_provider_compensation_won: int = Field(default=0, ge=0, le=10_000_000)

    def to_domain(self) -> PlanningPolicy:
        return PlanningPolicy(
            minimum_services_per_area=self.minimum_services_per_area,
            elderly_priority_weight=self.elderly_priority_weight,
            single_elderly_household_priority_weight=(
                self.single_elderly_household_priority_weight
            ),
            survey_required_protection_weight=self.survey_required_protection_weight,
            maximum_round_trip_travel_minutes=self.maximum_round_trip_travel_minutes,
            allowed_services=tuple(sorted(set(self.allowed_services))),
            minimum_provider_compensation_won=self.minimum_provider_compensation_won,
        )


class SchedulePlanInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scenario: Literal["efficiency", "balanced", "minimum_coverage"]
    budget_won: int = Field(ge=0, le=100_000_000)
    planning_policy: PlanningPolicyInput = Field(default_factory=PlanningPolicyInput)
    region_id: str = DEFAULT_REGION_ID


SURVEY_TYPE_LABELS = {
    "phone": "전화",
    "village_meeting": "마을회의",
    "proxy": "이장·대리조사",
    "field": "현장조사",
}


app = FastAPI(
    title="VillageCoverage API",
    version="0.1.0",
    description="Rural service coverage planning prototype with low-data protection.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip() for origin in _load_config("FRONTEND_ORIGINS").split(",") if origin.strip()
    ]
    or [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


def _load_demo() -> dict[str, Any]:
    try:
        return json.loads(DEMO_DATA_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise HTTPException(
            status_code=503,
            detail="데모 공공데이터를 찾을 수 없습니다. 데이터 생성 스크립트를 실행해 주세요.",
        ) from None


def _read_json(path: Path, unavailable: str) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise HTTPException(status_code=503, detail=unavailable) from None


def _assessment_for_area(
    area: dict[str, Any],
    connection: sqlite3.Connection,
    *,
    baseline_count: int | None = None,
    service_type: str | None = None,
    commit: bool = True,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    assessed_service = service_type or str(area["service_type"])
    surveys = database.list_surveys(connection, str(area["id"]), assessed_service)
    base_observations = (
        int(area["demand_observation_count"]) if baseline_count is None else baseline_count
    )
    source_types = {"request_history"} if base_observations else set()
    source_types.update(str(item["survey_type"]) for item in surveys)
    optional_answers = 0
    optional_fields = 5 * len(surveys)
    for item in surveys:
        optional_answers += int(item["frequency_per_month"] is not None)
        optional_answers += int(item["preferred_period"] is not None)
        optional_answers += int(bool(item["preferred_days"]))
        optional_answers += int(bool(item["constraints"]))
        optional_answers += int(bool(item["free_text_note"]))
    missingness = (optional_fields - optional_answers) / optional_fields if optional_fields else 0.0
    survey_dates = [date.fromisoformat(str(item["survey_date"])) for item in surveys]
    latest_date = max(survey_dates, default=None)
    assessment = assess_evidence(
        observation_count=base_observations + len(surveys),
        survey_count=len(surveys),
        source_diversity=len(source_types),
        missingness=missingness,
        latest_observation_date=latest_date,
    ).model_dump(mode="json")
    survey_provenance = {str(item.get("provenance", "")) for item in surveys}
    assessment_provenance = (
        "CSV_IMPORT + SIMULATED FOR PRE-R&D"
        if "CSV_IMPORT" in survey_provenance
        else "SIMULATED FOR PRE-R&D"
    )
    database.save_assessment(
        connection,
        area_id=str(area["id"]),
        service_type=assessed_service,
        assessment=assessment,
        provenance=assessment_provenance,
        commit=commit,
    )
    return assessment, surveys


def _apply_existing_service_history(area: dict[str, Any], connection: sqlite3.Connection) -> None:
    """Subtract fresh, reported service deliveries from the demo planning baseline."""
    baseline = max(0, int(area.get("simulated_monthly_demand", 0)))
    area["baseline_monthly_demand"] = baseline
    history = database.latest_existing_service_history(
        connection, str(area["id"]), str(area["service_type"])
    )
    latest_date = max((str(item["as_of_date"]) for item in history), default=None)
    fresh_records = [
        item
        for item in history
        if 0 <= (date.today() - date.fromisoformat(str(item["as_of_date"]))).days <= 180
    ]
    known_delivered_rounds = sum(int(item["monthly_rounds"]) for item in fresh_records)
    area["existing_service_status"] = (
        "CURRENT_REPORTED_SNAPSHOT" if fresh_records else "STALE" if history else "UNKNOWN"
    )
    area["existing_service_monthly_rounds"] = known_delivered_rounds if fresh_records else None
    area["existing_service_as_of_date"] = latest_date
    area["existing_service_program_count"] = len(fresh_records)
    area["simulated_monthly_demand"] = max(0, baseline - known_delivered_rounds)
    area["planning_demand_provenance"] = (
        "SIMULATED BASELINE + CSV_IMPORT EXISTING SERVICE HISTORY"
        if fresh_records
        else "SIMULATED BASELINE; EXISTING SERVICE HISTORY UNKNOWN"
        if not history
        else "SIMULATED BASELINE; EXISTING SERVICE SNAPSHOT STALE"
    )


def _scenario_data(
    budget: int,
    policy: PlanningPolicy | None = None,
    region_id: str = DEFAULT_REGION_ID,
) -> tuple[dict[str, Any], dict[str, Any]]:
    source_data = _load_demo()
    try:
        data = select_region(source_data, region_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    app_connection: sqlite3.Connection | None = None
    travel_connection: sqlite3.Connection | None = None
    try:
        app_connection = database.connect()
        database.seed_reference_data(app_connection, source_data)
        database.seed_provider_data(app_connection, source_data)
        provider_profiles = []
        for summary in database.list_providers(app_connection, data["region_id"]):
            provider = database.provider_detail(app_connection, summary["provider_id"])
            if provider is not None:
                provider_profiles.append(
                    {
                        "id": provider["provider_id"],
                        "capacity_per_month": (
                            int(provider["max_monthly_rounds"]) * int(provider["service_capacity"])
                        ),
                        "minimum_compensation_won": int(provider["minimum_compensation_won"]),
                        "supported_services": provider["supported_services"],
                    }
                )
        data["providers"] = provider_profiles
        for area in data["areas"]:
            assessment, _ = _assessment_for_area(area, app_connection)
            area["demand_observation_count"] = assessment["observation_count"]
            area["demand_data_count"] = assessment["observation_count"]
            area["demand_confidence"] = assessment["status"]
            area["needs_survey"] = assessment["needs_survey"]
            _apply_existing_service_history(area, app_connection)
    except (sqlite3.Error, RuntimeError):
        if app_connection is not None:
            app_connection.close()
            app_connection = None
        raise HTTPException(
            status_code=503,
            detail="조사·계획 자료 데이터베이스를 읽을 수 없습니다.",
        ) from None

    try:
        travel_connection = connect()
        if any(
            get_cached(travel_connection, origin, destination) is None
            for origin in data["areas"]
            for destination in data["areas"]
        ):
            raise ValueError("selected-region road cache incomplete")
        scenarios = evaluate_scenarios(
            data["areas"], data["providers"], travel_connection, budget, policy
        )
        return data, scenarios
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=503,
            detail=(
                "실제 도로 이동 캐시가 없습니다. "
                "먼저 scripts/build_travel_matrix.py 를 실행해 주세요."
            ),
        ) from None
    finally:
        if travel_connection is not None:
            travel_connection.close()
        if app_connection is not None:
            app_connection.close()


@app.get("/api/health")
def health() -> dict[str, Any]:
    cache: dict[str, Any] = {"route_count": 0, "origin_count": 0}
    try:
        connection = connect()
        cache = matrix_summary(connection)
        connection.close()
    except Exception:
        pass
    return {
        "status": "ok",
        "demo_data_available": DEMO_DATA_PATH.exists(),
        "road_routes_cached": cache["route_count"],
        "road_route_origins": cache["origin_count"],
    }


@app.get("/api/regions")
def regions() -> dict[str, Any]:
    data = _load_demo()
    options = region_catalog(data)
    if not options:
        raise HTTPException(status_code=503, detail="검증된 지역 자료가 없습니다.")
    return {
        "regions": options,
        "default_region_id": data.get("default_region_id", DEFAULT_REGION_ID),
        "provenance": "REAL PUBLIC DATA; EXACT LEGAL-CODE JOIN",
    }


@app.get("/api/areas")
def service_areas(
    region_id: str = Query(default=DEFAULT_REGION_ID, min_length=1, max_length=100),
) -> dict[str, Any]:
    try:
        data = select_region(_load_demo(), region_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    return {
        "region_id": data["region_id"],
        "areas": [
            {
                "area_id": str(area["id"]),
                "name": str(area["name"]),
                "legal_code": str(area["legal_code"]),
                "region_id": str(area.get("region_id", data["region_id"])),
            }
            for area in data["areas"]
        ],
        "provenance": "REAL PUBLIC DATA; EXACT LEGAL-CODE JOIN",
    }


@app.get("/api/overview")
def overview(
    budget: int = Query(default=DEFAULT_BUDGET, ge=0, le=100_000_000),
    region_id: str = Query(default=DEFAULT_REGION_ID, min_length=1, max_length=100),
    minimum_services_per_area: int = Query(default=1, ge=1, le=8),
    elderly_priority_weight: int = Query(default=500, ge=0, le=1000),
    single_elderly_household_priority_weight: int = Query(default=500, ge=0, le=1000),
    survey_required_protection_weight: int = Query(default=1000, ge=0, le=1000),
    maximum_round_trip_travel_minutes: int | None = Query(default=None, ge=1, le=360),
    allowed_services: list[Literal["laundry", "daily_necessities", "home_repair"]] = (
        _ALLOWED_SERVICES_QUERY
    ),
    minimum_provider_compensation_won: int = Query(default=0, ge=0, le=10_000_000),
) -> dict[str, Any]:
    budget_policy = PlanningPolicy(
        minimum_services_per_area=minimum_services_per_area,
        elderly_priority_weight=elderly_priority_weight,
        single_elderly_household_priority_weight=single_elderly_household_priority_weight,
        survey_required_protection_weight=survey_required_protection_weight,
        maximum_round_trip_travel_minutes=maximum_round_trip_travel_minutes,
        allowed_services=tuple(sorted(set(allowed_services))),
        minimum_provider_compensation_won=minimum_provider_compensation_won,
    )
    data, scenarios = _scenario_data(budget, budget_policy, region_id)
    return {
        "region": data["region"],
        "region_id": data["region_id"],
        "regions": region_catalog(data),
        "budget_won": budget,
        "planning_defaults": data["planning_defaults"],
        "planning_policy": scenarios["planning_policy"],
        "areas": data["areas"],
        "scenario_results": scenarios["scenario_results"],
        "request_count_baseline": scenarios["request_count_baseline"],
        "hub_area_id": scenarios["hub_area_id"],
        "travel_source": scenarios["travel_source"],
        "scenario_labels": {
            "efficiency": "효율 우선",
            "balanced": "균형",
            "minimum_coverage": "최소 서비스 보장",
        },
    }


@app.get("/api/villages/{area_id}")
def village_detail(
    area_id: str, budget: int = Query(default=DEFAULT_BUDGET, ge=0, le=100_000_000)
) -> dict[str, Any]:
    baseline_data = _load_demo()
    baseline_area = next((row for row in baseline_data["areas"] if row["id"] == area_id), None)
    if baseline_area is None:
        raise HTTPException(status_code=404, detail="해당 서비스 권역을 찾을 수 없습니다.")
    area_region_id = str(baseline_area.get("region_id", DEFAULT_REGION_ID))
    data, scenarios = _scenario_data(budget, region_id=area_region_id)
    area = next((item for item in data["areas"] if item["id"] == area_id), None)
    if area is None:
        raise HTTPException(status_code=404, detail="해당 서비스 권역을 찾을 수 없습니다.")
    assessments = {
        scenario: next(row for row in result["assignments"] if row["area_id"] == area_id)
        for scenario, result in scenarios["scenario_results"].items()
    }
    connection = database.connect()
    try:
        database.seed_reference_data(connection, data)
        evidence, _ = _assessment_for_area(
            area,
            connection,
            baseline_count=int(baseline_area["demand_observation_count"]) if baseline_area else 0,
        )
        all_surveys = database.list_surveys(connection, area_id)
    finally:
        connection.close()
    return {
        "area": area,
        "scenario_assessments": assessments,
        "evidence": evidence,
        "surveys": all_surveys,
        "survey_recommendation": (
            "기초조사 근거로 제한적 계획이 가능합니다. 더 많은 요청·계절 자료를 확인하세요."
            if evidence["status"] == "제한적 계획 가능"
            else "전화·회의 기록을 추가 확인하고 계절별 수요를 조사하세요."
            if evidence["needs_survey"]
            else "요청 기록의 최근성과 출처 다양성을 계속 확인하세요."
        ),
    }


@app.post("/api/villages/{area_id}/surveys", status_code=201)
def create_survey(area_id: str, item: SurveyInput) -> dict[str, Any]:
    data = _load_demo()
    area = next((row for row in data["areas"] if str(row["id"]) == area_id), None)
    if area is None:
        raise HTTPException(status_code=404, detail="해당 서비스 권역을 찾을 수 없습니다.")
    if item.survey_date > datetime.now(timezone.utc).date():
        raise HTTPException(status_code=422, detail="조사일은 오늘 이후 날짜일 수 없습니다.")

    redacted_note, was_redacted = redact_pii(item.free_text_note.strip())
    redacted_period, period_was_redacted = redact_pii((item.preferred_period or "").strip())
    redacted_constraints = []
    constraints_were_redacted = False
    for value in item.constraints:
        redacted_value, changed = redact_pii(value.strip())
        if redacted_value:
            redacted_constraints.append(redacted_value)
        constraints_were_redacted = constraints_were_redacted or changed
    was_redacted = was_redacted or period_was_redacted or constraints_were_redacted
    connection = database.connect()
    try:
        database.seed_reference_data(connection, data)
        survey_id = database.insert_survey(
            connection,
            area_id=area_id,
            survey_type=item.survey_type,
            survey_date=item.survey_date.isoformat(),
            service_type=item.service_type,
            frequency_per_month=item.frequency_per_month,
            preferred_period=redacted_period or None,
            preferred_days=item.preferred_days,
            constraints=redacted_constraints,
            free_text_note=redacted_note,
            source_text_was_redacted=was_redacted,
        )
        baseline_count = (
            int(area["demand_observation_count"])
            if item.service_type == area["service_type"]
            else 0
        )
        evidence, surveys = _assessment_for_area(
            area,
            connection,
            baseline_count=baseline_count,
            service_type=item.service_type,
        )
        survey = next(row for row in surveys if row["survey_id"] == survey_id)
    except sqlite3.Error:
        connection.rollback()
        raise HTTPException(status_code=503, detail="조사 자료를 저장하지 못했습니다.") from None
    finally:
        connection.close()
    return {
        "survey": survey,
        "evidence": evidence,
        "message": "기초조사를 저장했습니다. 시연용 합성 자료입니다.",
    }


def _seed_providers(connection: sqlite3.Connection) -> None:
    data = _load_demo()
    database.seed_reference_data(connection, data)
    database.seed_provider_data(connection, data)


@app.get("/api/providers")
def providers(
    region_id: str = Query(default=DEFAULT_REGION_ID, min_length=1, max_length=100),
) -> dict[str, Any]:
    try:
        selected_region = select_region(_load_demo(), region_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    connection = database.connect()
    try:
        _seed_providers(connection)
        return {
            "region_id": selected_region["region_id"],
            "region": selected_region["region"],
            "providers": database.list_providers(connection, selected_region["region_id"]),
            "provenance": "SIMULATED FOR PRE-R&D",
        }
    except sqlite3.Error:
        raise HTTPException(status_code=503, detail="공급자 자료를 읽을 수 없습니다.") from None
    finally:
        connection.close()


@app.get("/api/providers/{provider_id}")
def provider(provider_id: str) -> dict[str, Any]:
    connection = database.connect()
    try:
        _seed_providers(connection)
        result = database.provider_detail(connection, provider_id)
        if result is None:
            raise HTTPException(status_code=404, detail="공급자를 찾을 수 없습니다.")
        return result
    except sqlite3.Error:
        raise HTTPException(status_code=503, detail="공급자 자료를 읽을 수 없습니다.") from None
    finally:
        connection.close()


@app.post("/api/providers/{provider_id}/rounds/{round_id}/participation")
def set_provider_participation(
    provider_id: str, round_id: str, item: ParticipationInput
) -> dict[str, Any]:
    connection = database.connect()
    try:
        _seed_providers(connection)
        try:
            updated = database.update_participation(
                connection, provider_id=provider_id, round_id=round_id, status=item.status
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from None
        if not updated:
            raise HTTPException(
                status_code=404, detail="해당 공급자의 회차 기회를 찾을 수 없습니다."
            )
        result = database.provider_detail(connection, provider_id)
        assert result is not None
        return {
            "provider": result,
            "message": "이번 회차 참여 상태를 저장했습니다.",
            "provenance": "SIMULATED FOR PRE-R&D",
        }
    except sqlite3.Error:
        connection.rollback()
        raise HTTPException(status_code=503, detail="참여 상태를 저장하지 못했습니다.") from None
    finally:
        connection.close()


@app.post("/api/providers/{provider_id}/participation-preferences")
def set_provider_participation_preference(
    provider_id: str, item: ParticipationPreferenceInput
) -> dict[str, Any]:
    if item.scope == "MONTH":
        try:
            if len(item.period) != 7 or item.period[4] != "-":
                raise ValueError
            normalized_period = date.fromisoformat(f"{item.period}-01").isoformat()
        except ValueError:
            raise HTTPException(status_code=422, detail="월은 YYYY-MM 형식이어야 합니다.") from None
    else:
        try:
            week_date = date.fromisoformat(item.period)
            if week_date.isoformat() != item.period:
                raise ValueError
            normalized_period = (
                week_date - timedelta(days=week_date.weekday())
            ).isoformat()
        except ValueError:
            raise HTTPException(
                status_code=422, detail="주는 YYYY-MM-DD 날짜 형식이어야 합니다."
            ) from None
    connection = database.connect()
    try:
        _seed_providers(connection)
        try:
            affected = database.set_participation_preference(
                connection,
                provider_id=provider_id,
                scope=item.scope,
                period_start=normalized_period,
                status=item.status,
            )
        except ValueError as exc:
            detail = str(exc)
            if detail == "provider was not found":
                raise HTTPException(status_code=404, detail="공급자를 찾을 수 없습니다.") from None
            status_code = 409 if "no unreviewed" in detail else 422
            raise HTTPException(status_code=status_code, detail=detail) from None
        result = database.provider_detail(connection, provider_id)
        assert result is not None
        scope_label = "월" if item.scope == "MONTH" else "주"
        status_label = {
            "OPTED_IN": "참여 의사 표시",
            "DECLINED": "불참 의사 표시",
            "AVAILABLE": "그룹 설정 해제",
        }[item.status]
        return {
            "provider": result,
            "preference": {
                "scope": item.scope,
                "period_start": normalized_period,
                "status": item.status,
                "provenance": "SIMULATED FOR PRE-R&D",
            },
            "affected_round_count": affected,
            "message": (
                f"{normalized_period} {scope_label} 기회에 {status_label}를 저장했습니다. "
                "개별 회차 설정은 유지됩니다."
            ),
            "provenance": "SIMULATED FOR PRE-R&D",
        }
    except sqlite3.Error:
        connection.rollback()
        raise HTTPException(status_code=503, detail="참여 선호를 저장하지 못했습니다.") from None
    finally:
        connection.close()


@app.get("/api/schedules")
def schedule_history(
    region_id: str | None = None, limit: int = Query(default=20, ge=1, le=100)
) -> dict[str, Any]:
    if region_id is not None:
        try:
            region_options = region_catalog(_load_demo())
        except HTTPException:
            raise
        if region_id not in {str(option["region_id"]) for option in region_options}:
            raise HTTPException(status_code=422, detail="검증된 시범 지역이 아닙니다.")
    connection = database.connect()
    try:
        return {
            "plans": database.list_schedule_history(connection, region_id=region_id, limit=limit),
            "provenance": "OPTIMIZATION RESULT; SIMULATED FOR PRE-R&D",
        }
    except sqlite3.Error:
        raise HTTPException(
            status_code=503, detail="저장된 계획 이력을 읽을 수 없습니다."
        ) from None
    finally:
        connection.close()


@app.post("/api/schedules", status_code=201)
def create_schedule_plan(item: SchedulePlanInput) -> dict[str, Any]:
    try:
        source_data = _load_demo()
        data = select_region(source_data, item.region_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    app_connection: sqlite3.Connection | None = None
    travel_connection: sqlite3.Connection | None = None
    try:
        app_connection = database.connect()
        database.seed_reference_data(app_connection, source_data)
        database.seed_provider_data(app_connection, source_data)
        providers = []
        for summary in database.list_providers(app_connection, data["region_id"]):
            provider_data = database.provider_detail(app_connection, summary["provider_id"])
            if provider_data is not None:
                providers.append(provider_data)
        for area in data["areas"]:
            _apply_existing_service_history(area, app_connection)
            surveys = database.list_surveys(
                app_connection, str(area["id"]), str(area["service_type"])
            )
            area["preferred_days"] = sorted(
                {day for survey in surveys for day in survey["preferred_days"]}
            )
        travel_connection = connect()
        if any(
            get_cached(travel_connection, origin, destination) is None
            for origin in data["areas"]
            for destination in data["areas"]
        ):
            raise ValueError("selected-region provider road cache is incomplete")
        policy = item.planning_policy.to_domain()
        plan = generate_provider_schedule(
            data["areas"], providers, travel_connection, item.budget_won, item.scenario, policy
        )
        schedule_id = database.save_schedule_plan(
            app_connection,
            scenario=item.scenario,
            budget_won=item.budget_won,
            plan=plan,
            planning_policy=asdict(policy),
            region_id=data["region_id"],
        )
        result = database.get_schedule_plan(app_connection, schedule_id)
        assert result is not None
        return result
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
    except RuntimeError:
        raise HTTPException(
            status_code=503,
            detail=(
                "공급자 일정에서 실행 가능한 해를 찾지 못했습니다. 입력·도로 캐시를 확인해 주세요."
            ),
        ) from None
    except sqlite3.Error:
        if app_connection is not None:
            app_connection.rollback()
        raise HTTPException(
            status_code=503, detail="공급 일정 자료를 저장하지 못했습니다."
        ) from None
    finally:
        if travel_connection is not None:
            travel_connection.close()
        if app_connection is not None:
            app_connection.close()


def _csv_safe_text(value: Any) -> str:
    text = str(value if value is not None else "")
    first_significant = next(
        (
            character
            for character in text
            if not character.isspace() and ord(character) >= 32 and character != "\ufeff"
        ),
        "",
    )
    if first_significant in {"=", "+", "-", "@"}:
        return "'" + text
    return text


@app.get("/api/schedules/{schedule_id}/export.csv")
def export_schedule_csv(schedule_id: str) -> Response:
    connection = database.connect()
    try:
        plan = database.get_schedule_plan(connection, schedule_id)
        if plan is None:
            raise HTTPException(status_code=404, detail="공급 일정 계획을 찾을 수 없습니다.")
        output = io.StringIO(newline="")
        writer = csv.writer(output, lineterminator="\r\n")
        round_headers = [
            "scheduled_date",
            "provider_id",
            "provider_name",
            "area_id",
            "area_name",
            "service_type",
            "route_type",
            "route_sequence",
            "departure_time",
            "service_start_time",
            "service_end_time",
            "duration_minutes",
            "service_units",
            "travel_distance_m",
            "travel_before_s",
            "travel_after_s",
            "service_cost_won",
            "travel_cost_won",
            "minimum_compensation_topup_won",
            "round_total_cost_won",
            "round_provenance",
        ]
        writer.writerow(
            [
                "record_type",
                "schedule_id",
                "region",
                "scenario",
                "budget_won",
                "created_at",
                "plan_round_count",
                "plan_budget_spent_won",
                "plan_budget_remaining_won",
                "plan_budget_gap_won",
                "plan_required_budget_won",
                "plan_service_cost_won",
                "plan_travel_cost_won",
                "plan_minimum_compensation_topup_won",
                "plan_total_cost_won",
                "plan_covered_areas",
                "plan_uncovered_areas",
                "plan_minimum_frequency_met_areas",
                "plan_unmet_minimum_frequency_areas",
                "plan_required_capacity",
                "plan_available_capacity",
                "plan_missing_capacity",
                "solver_status",
                "optimality_proven",
                *round_headers,
                "plan_provenance",
            ]
        )
        summary = plan["summary"]
        plan_metadata = [
            plan["schedule_id"],
            _csv_safe_text(plan["region_name"]),
            plan["scenario_key"],
            plan["budget_won"],
            plan["created_at"],
            len(plan["rounds"]),
            summary["budget_spent_won"],
            summary["budget_remaining_won"],
            summary["budget_gap_won"],
            summary["required_budget_won"],
            summary["service_cost_won"],
            summary["travel_cost_won"],
            summary["minimum_compensation_topup_won"],
            summary["total_cost_won"],
            summary["covered_areas"],
            summary["uncovered_areas"],
            summary["minimum_frequency_met_areas"],
            summary["unmet_minimum_frequency_areas"],
            summary["required_capacity"],
            summary["available_capacity"],
            summary["missing_capacity"],
            summary["solver_status"],
            summary["optimality_proven"],
        ]
        for round_item in plan["rounds"]:
            writer.writerow(
                [
                    "ROUND",
                    *plan_metadata,
                    round_item["scheduled_date"],
                    _csv_safe_text(round_item["provider_id"]),
                    _csv_safe_text(round_item["provider_name"]),
                    _csv_safe_text(round_item["area_id"]),
                    _csv_safe_text(round_item["area_name"]),
                    round_item["service_type"],
                    round_item["route_type"],
                    round_item["route_sequence"],
                    round_item["departure_time"],
                    round_item["service_start_time"],
                    round_item["service_end_time"],
                    round_item["duration_minutes"],
                    round_item["service_units"],
                    round_item["travel_distance_m"],
                    round_item["travel_before_s"],
                    round_item["travel_after_s"],
                    round_item["service_cost_won"],
                    round_item["travel_cost_won"],
                    round_item["minimum_compensation_topup_won"],
                    round_item["total_cost_won"],
                    _csv_safe_text(round_item["provenance"]),
                    _csv_safe_text(plan["provenance"]),
                ]
            )
        if not plan["rounds"]:
            writer.writerow(
                [
                    "PLAN_SUMMARY",
                    *plan_metadata,
                    *("" for _ in round_headers),
                    _csv_safe_text(plan["provenance"]),
                ]
            )
        body = "\ufeff" + output.getvalue()
        download_name = f"villagecoverage-plan-{schedule_id}.csv"
        return Response(
            content=body,
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="{download_name}"',
                "Cache-Control": "no-store",
            },
        )
    except sqlite3.Error:
        raise HTTPException(status_code=503, detail="계획 CSV를 만들지 못했습니다.") from None
    finally:
        connection.close()


@app.get("/api/schedules/{schedule_id}")
def schedule_plan(schedule_id: str) -> dict[str, Any]:
    connection = database.connect()
    try:
        result = database.get_schedule_plan(connection, schedule_id)
        if result is None:
            raise HTTPException(status_code=404, detail="공급 일정 계획을 찾을 수 없습니다.")
        return result
    except sqlite3.Error:
        raise HTTPException(status_code=503, detail="공급 일정 자료를 읽을 수 없습니다.") from None
    finally:
        connection.close()


@app.get("/api/data-quality")
def data_quality() -> dict[str, Any]:
    return _read_json(QUALITY_PATH, "데이터 품질 보고서를 찾을 수 없습니다.")


@app.get("/api/data-dictionary")
def data_dictionary() -> dict[str, Any]:
    return _read_json(SCHEMA_PATH, "공개데이터 스키마 목록을 찾을 수 없습니다.")


def _service_registry(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    database.seed_reference_data(connection, _load_demo())
    return database.list_service_types(connection)


@app.get("/api/services")
def service_registry() -> dict[str, Any]:
    connection = database.connect()
    try:
        services = _service_registry(connection)
        return {
            "services": services,
            "allowed_service_codes": [
                item["service_type_id"] for item in services if item["policy_status"] == "ALLOWED"
            ],
            "provenance": "POLICY: INITIAL DEMO SCOPE",
        }
    except sqlite3.Error:
        raise HTTPException(
            status_code=503, detail="서비스 범위 정책을 읽을 수 없습니다."
        ) from None
    finally:
        connection.close()


def _public_import_batch(
    batch: dict[str, Any], *, already_imported: bool = False
) -> dict[str, Any]:
    result = {key: value for key, value in batch.items() if key != "content_sha256"}
    result["already_imported"] = already_imported
    return result


@app.get("/api/imports/templates")
def import_templates() -> dict[str, Any]:
    connection = database.connect()
    try:
        services = _service_registry(connection)
        return {
            "templates": {
                import_type: {
                    "filename": f"{import_type}.csv",
                    "headers": list(headers),
                }
                for import_type, headers in IMPORT_HEADERS.items()
            },
            "service_codes": [
                service["service_type_id"]
                for service in services
                if service["policy_status"] == "ALLOWED"
            ],
            "service_registry": services,
            "source_codes": ["phone", "village_meeting", "proxy", "field"],
        }
    except sqlite3.Error:
        raise HTTPException(
            status_code=503, detail="가져오기 서비스 정책을 읽을 수 없습니다."
        ) from None
    finally:
        connection.close()


@app.get("/api/imports")
def list_imports(limit: int = Query(default=10, ge=1, le=50)) -> dict[str, Any]:
    connection = database.connect()
    try:
        batches = database.list_import_batches(connection, limit)
        return {"batches": [_public_import_batch(batch) for batch in batches]}
    except sqlite3.Error:
        raise HTTPException(status_code=503, detail="가져오기 이력을 읽을 수 없습니다.") from None
    finally:
        connection.close()


@app.get("/api/imports/{batch_id}")
def import_detail(batch_id: str) -> dict[str, Any]:
    connection = database.connect()
    try:
        batch = database.get_import_batch(connection, batch_id)
        if batch is None:
            raise HTTPException(status_code=404, detail="가져오기 이력을 찾을 수 없습니다.")
        return _public_import_batch(batch)
    except sqlite3.Error:
        raise HTTPException(status_code=503, detail="가져오기 이력을 읽을 수 없습니다.") from None
    finally:
        connection.close()


@app.post("/api/imports/{import_type}", status_code=201)
async def create_csv_import(import_type: str, request: Request) -> dict[str, Any]:
    if import_type not in IMPORT_HEADERS:
        raise HTTPException(status_code=404, detail="지원하지 않는 CSV 가져오기 유형입니다.")
    content_length = request.headers.get("content-length")
    if content_length and content_length.isdigit() and int(content_length) > MAX_CSV_BYTES:
        raise HTTPException(status_code=413, detail="CSV 파일은 5MB 이하만 가져올 수 있습니다.")
    payload = await request.body()
    try:
        content_sha256, parsed_rows = parse_csv(payload, import_type)
    except CSVImportFormatError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None

    connection = database.connect()
    try:
        previous = database.find_import_batch(connection, import_type, content_sha256)
        if previous is not None:
            existing = database.get_import_batch(connection, str(previous["batch_id"]))
            assert existing is not None
            return _public_import_batch(existing, already_imported=True)

        source_data = _load_demo()
        database.seed_reference_data(connection, source_data)
        database.seed_provider_data(connection, source_data)
        area_by_code = {
            str(area["legal_code"]): area
            for area in source_data.get("areas", [])
            if area.get("legal_code")
        }
        provider_services: dict[str, set[str]] = {}
        for row in connection.execute(
            "SELECT provider_id, service_type FROM provider_services"
        ).fetchall():
            provider_services.setdefault(str(row["provider_id"]), set()).add(
                str(row["service_type"])
            )
        service_policy = {
            str(item["service_type_id"]): str(item["policy_status"])
            for item in database.list_service_types(connection)
        }
        rows = prepare_import_rows(
            import_type,
            parsed_rows,
            area_by_code=area_by_code,
            provider_services=provider_services,
            service_policy=service_policy,
        )
        batch_id = str(uuid4())
        database.create_import_batch(
            connection,
            batch_id=batch_id,
            import_type=import_type,
            content_sha256=content_sha256,
            total_rows=len(rows),
        )
        affected_assessments: dict[tuple[str, str], dict[str, Any]] = {}
        for row in rows:
            record = row["record"]
            imported_record_id: str | None = None
            if row["status"] == "IMPORTED" and import_type == "demand_observations":
                area = area_by_code[record["village_code"]]
                imported_record_id = database.insert_survey(
                    connection,
                    area_id=str(area["id"]),
                    survey_type=str(record["source_type"]),
                    survey_date=str(record["date"]),
                    service_type=str(record["service_type"]),
                    frequency_per_month=None,
                    preferred_period=None,
                    preferred_days=[],
                    constraints=[],
                    free_text_note=str(record["note"]),
                    source_text_was_redacted=bool(row["redacted"]),
                    provenance="CSV_IMPORT",
                )
                affected_assessments[(str(area["id"]), str(record["service_type"]))] = area
            elif row["status"] == "IMPORTED" and import_type == "provider_availability":
                database.import_date_availability(
                    connection,
                    provider_id=str(record["provider_id"]),
                    available_date=str(record["date"]),
                    service_type=str(record["service_type"]),
                    start_time=str(record["start_time"]),
                    end_time=str(record["end_time"]),
                )
                imported_record_id = "|".join(
                    (
                        str(record["provider_id"]),
                        str(record["date"]),
                        str(record["service_type"]),
                        str(record["start_time"]),
                    )
                )
            elif row["status"] == "IMPORTED" and import_type == "existing_service_history":
                area = area_by_code[record["village_code"]]
                imported_record_id = database.upsert_existing_service_history(
                    connection,
                    history_id=str(uuid4()),
                    area_id=str(area["id"]),
                    service_type=str(record["service_type"]),
                    program_name=str(record["program_name"]),
                    monthly_rounds=int(record["monthly_rounds"]),
                    as_of_date=str(record["as_of_date"]),
                )
            database.create_import_row(
                connection,
                row_id=str(uuid4()),
                batch_id=batch_id,
                row_number=int(row["row_number"]),
                status=str(row["status"]),
                record=record,
                issues=list(row["issues"]),
                redacted=bool(row["redacted"]),
                imported_record_id=imported_record_id,
            )
        for (_area_id, service_type), area in affected_assessments.items():
            baseline_count = (
                int(area["demand_observation_count"]) if service_type == area["service_type"] else 0
            )
            _assessment_for_area(
                area,
                connection,
                baseline_count=baseline_count,
                service_type=service_type,
                commit=False,
            )
        database.update_import_batch_counts(connection, batch_id)
        connection.commit()
        result = database.get_import_batch(connection, batch_id)
        assert result is not None
        return _public_import_batch(result)
    except sqlite3.Error:
        connection.rollback()
        raise HTTPException(status_code=503, detail="CSV 자료를 저장하지 못했습니다.") from None
    finally:
        connection.close()


@app.post("/api/imports/{batch_id}/rows/{row_number}/approve")
def approve_import_row(
    batch_id: str, row_number: int, item: ImportRowReviewInput
) -> dict[str, Any]:
    connection = database.connect()
    try:
        batch = database.get_import_batch(connection, batch_id)
        if batch is None:
            raise HTTPException(status_code=404, detail="가져오기 이력을 찾을 수 없습니다.")
        row = database.get_import_row(connection, batch_id, row_number)
        if row is None:
            raise HTTPException(status_code=404, detail="가져오기 행을 찾을 수 없습니다.")
        if row["status"] != "NEEDS_REVIEW":
            raise HTTPException(
                status_code=409, detail="확인 대기 중인 가져오기 행만 반영할 수 있습니다."
            )
        record = dict(row["record"])
        if batch["import_type"] == "existing_service_history":
            source_data = _load_demo()
            area = next(
                (
                    candidate
                    for candidate in source_data.get("areas", [])
                    if str(candidate.get("legal_code")) == str(record["village_code"])
                ),
                None,
            )
            if area is None:
                raise HTTPException(status_code=409, detail="현재 pilot에 없는 법정동 코드입니다.")
            service_status = {
                str(item["service_type_id"]): str(item["policy_status"])
                for item in database.list_service_types(connection)
            }.get(str(record["service_type"]))
            if service_status != "ALLOWED":
                raise HTTPException(
                    status_code=422, detail="초기 지원 서비스만 반영할 수 있습니다."
                )
            try:
                as_of_date = date.fromisoformat(str(record["as_of_date"]))
                monthly_rounds = int(record["monthly_rounds"])
            except (TypeError, ValueError):
                raise HTTPException(
                    status_code=422, detail="서비스 실적의 날짜와 회차를 확인해 주세요."
                ) from None
            if as_of_date.isoformat() != record["as_of_date"] or as_of_date > date.today():
                raise HTTPException(status_code=422, detail="서비스 실적 기준일을 확인해 주세요.")
            if not 0 <= monthly_rounds <= 31 or not str(record.get("program_name", "")).strip():
                raise HTTPException(
                    status_code=422, detail="서비스명과 월 실적 회차를 확인해 주세요."
                )
            history_id = database.upsert_existing_service_history(
                connection,
                history_id=str(uuid4()),
                area_id=str(area["id"]),
                service_type=str(record["service_type"]),
                program_name=str(record["program_name"]).strip(),
                monthly_rounds=monthly_rounds,
                as_of_date=as_of_date.isoformat(),
            )
            database.mark_import_row_imported(
                connection,
                batch_id=batch_id,
                row_number=row_number,
                record=record,
                imported_record_id=history_id,
                redacted=bool(row["redacted"]),
            )
            connection.commit()
            result = database.get_import_batch(connection, batch_id)
            assert result is not None
            return _public_import_batch(result)
        if batch["import_type"] != "demand_observations":
            raise HTTPException(status_code=409, detail="이 가져오기 행은 검토할 수 없습니다.")
        note = item.note.strip() if item.note is not None else str(record.get("note", "")).strip()
        safe_note, was_redacted = redact_pii(note)
        if not safe_note:
            raise HTTPException(status_code=422, detail="확인 후 사용할 조사 메모를 입력해 주세요.")
        source_data = _load_demo()
        area = next(
            (
                candidate
                for candidate in source_data.get("areas", [])
                if str(candidate.get("legal_code")) == str(record["village_code"])
            ),
            None,
        )
        if area is None:
            raise HTTPException(status_code=409, detail="현재 pilot에 없는 법정동 코드입니다.")
        database.seed_reference_data(connection, source_data)
        survey_id = database.insert_survey(
            connection,
            area_id=str(area["id"]),
            survey_type=str(record["source_type"]),
            survey_date=str(record["date"]),
            service_type=str(record["service_type"]),
            frequency_per_month=None,
            preferred_period=None,
            preferred_days=[],
            constraints=[],
            free_text_note=safe_note,
            source_text_was_redacted=bool(row["redacted"] or was_redacted),
            provenance="CSV_IMPORT",
        )
        record["note"] = safe_note
        database.mark_import_row_imported(
            connection,
            batch_id=batch_id,
            row_number=row_number,
            record=record,
            imported_record_id=survey_id,
            redacted=bool(row["redacted"] or was_redacted),
        )
        baseline_count = (
            int(area["demand_observation_count"])
            if str(record["service_type"]) == area["service_type"]
            else 0
        )
        _assessment_for_area(
            area,
            connection,
            baseline_count=baseline_count,
            service_type=str(record["service_type"]),
            commit=False,
        )
        connection.commit()
        result = database.get_import_batch(connection, batch_id)
        assert result is not None
        return _public_import_batch(result)
    except sqlite3.Error:
        connection.rollback()
        raise HTTPException(
            status_code=503, detail="검토한 수요 자료를 저장하지 못했습니다."
        ) from None
    finally:
        connection.close()


@app.post("/api/demand/structure")
def structure_demand_endpoint(item: DemandInput) -> dict[str, Any]:
    # Secrets are read for server-side use only and are never included in responses.
    result = structure_demand(
        item.text,
        api_key=_load_config("GEMINI_API_KEY"),
        model=_load_config("GEMINI_MODEL") or "gemini-3.5-flash-lite",
        use_remote=True,
    )
    body = result.model_dump(mode="json")
    connection = database.connect()
    try:
        services = _service_registry(connection)
    except sqlite3.Error:
        raise HTTPException(
            status_code=503, detail="서비스 범위 정책을 확인하지 못했습니다."
        ) from None
    finally:
        connection.close()
    service_by_id = {str(service["service_type_id"]): service for service in services}
    policy_reviews: list[str] = []
    for request_item in body["requests"]:
        service_id = str(request_item["service_type"])
        service = service_by_id.get(service_id)
        policy = (
            {
                "service_type_id": service_id,
                "label_ko": "서비스 확인 필요",
                "policy_status": "UNCLASSIFIED",
                "policy_reason": "등록된 서비스 정책이 없어 계획에 사용할 수 없습니다.",
                "provenance": "POLICY CHECK REQUIRED",
            }
            if service is None
            else service
        )
        request_item["service_policy"] = policy
        if policy["policy_status"] != "ALLOWED":
            policy_reviews.append(f"{policy['label_ko']}: {policy['policy_reason']}")
    body["service_registry"] = services
    body["requires_service_scope_review"] = bool(policy_reviews)
    if policy_reviews:
        body["needs_followup_survey"] = True
        review_reason = (
            "초기 지원 범위에서 제외되거나 인허가 검토가 필요한 서비스가 포함되었습니다. "
            + " ".join(policy_reviews)
        )
        body["followup_reason"] = " ".join(
            value for value in (body.get("followup_reason"), review_reason) if value
        )
    has_note = bool(item.text.strip())
    body["evidence_assessment"] = assess_evidence(
        observation_count=1 if has_note else 0,
        source_diversity=1 if has_note else 0,
        missingness=0,
        latest_observation_date=datetime.now(timezone.utc).date() if has_note else None,
        model_confidence=(
            result.confidence if result.method == "gemini_structured_output" else None
        ),
    ).model_dump(mode="json")
    return body


@app.post("/api/demand/drafts", status_code=201)
def create_demand_draft(item: DemandDraftInput) -> dict[str, Any]:
    source_data = _load_demo()
    area = next((row for row in source_data["areas"] if row["id"] == item.area_id), None)
    if area is None:
        raise HTTPException(status_code=404, detail="해당 서비스 권역을 찾을 수 없습니다.")
    if item.survey_date > datetime.now(timezone.utc).date():
        raise HTTPException(status_code=422, detail="조사일은 오늘 이후 날짜일 수 없습니다.")

    safe_source, was_redacted = redact_pii(item.text.strip())
    structured = structure_demand_endpoint(DemandInput(text=item.text))
    connection = database.connect()
    try:
        database.seed_reference_data(connection, source_data)
        draft_id = database.insert_demand_structuring_draft(
            connection,
            area_id=item.area_id,
            survey_type=item.survey_type,
            survey_date=item.survey_date.isoformat(),
            source_text_redacted=safe_source,
            source_text_was_redacted=(was_redacted or bool(structured["source_text_was_redacted"])),
            structured=structured,
        )
    except sqlite3.Error:
        connection.rollback()
        raise HTTPException(status_code=503, detail="구조화 초안을 저장하지 못했습니다.") from None
    finally:
        connection.close()
    return {
        "draft_id": draft_id,
        "area_id": item.area_id,
        "survey_type": item.survey_type,
        "survey_date": item.survey_date.isoformat(),
        "source_text_redacted": safe_source,
        "source_text_was_redacted": was_redacted,
        "status": "DRAFT",
        "provenance": "SIMULATED HUMAN REVIEW",
        "structured": structured,
    }


@app.get("/api/demand/drafts")
def list_demand_drafts(
    area_id: str = Query(min_length=1, max_length=120),
) -> dict[str, Any]:
    known_area = next((area for area in _load_demo()["areas"] if str(area["id"]) == area_id), None)
    if known_area is None:
        raise HTTPException(status_code=404, detail="해당 서비스 권역을 찾을 수 없습니다.")
    connection = database.connect()
    try:
        drafts = database.list_demand_structuring_drafts(connection, area_id)
        return {"drafts": drafts}
    except sqlite3.Error:
        raise HTTPException(status_code=503, detail="미검토 초안을 읽지 못했습니다.") from None
    finally:
        connection.close()


@app.get("/api/demand/drafts/{draft_id}")
def get_demand_draft(draft_id: str) -> dict[str, Any]:
    connection = database.connect()
    try:
        draft = database.get_demand_structuring_draft(connection, draft_id)
        if draft is None:
            raise HTTPException(status_code=404, detail="구조화 초안을 찾을 수 없습니다.")
        return draft
    except sqlite3.Error:
        raise HTTPException(status_code=503, detail="구조화 초안을 읽지 못했습니다.") from None
    finally:
        connection.close()


@app.post("/api/demand/drafts/{draft_id}/approve")
def approve_demand_draft(draft_id: str, item: DemandApprovalInput) -> dict[str, Any]:
    source_data = _load_demo()
    connection = database.connect()
    try:
        database.seed_reference_data(connection, source_data)
        connection.commit()
        policies = {
            service["service_type_id"]: service for service in _service_registry(connection)
        }
        connection.commit()
        connection.execute("BEGIN IMMEDIATE")
        draft = database.get_demand_structuring_draft(connection, draft_id)
        if draft is None:
            raise HTTPException(status_code=404, detail="구조화 초안을 찾을 수 없습니다.")
        if draft["status"] != "DRAFT":
            raise HTTPException(status_code=409, detail="이미 검토가 완료된 초안입니다.")
        area = next((row for row in source_data["areas"] if row["id"] == draft["area_id"]), None)
        if area is None:
            raise HTTPException(status_code=404, detail="해당 서비스 권역을 찾을 수 없습니다.")
        if not database.claim_demand_structuring_draft(connection, draft_id):
            raise HTTPException(status_code=409, detail="초안 상태가 변경되어 승인할 수 없습니다.")

        safe_followup_reason, followup_was_redacted = redact_pii(
            (item.followup_reason or "").strip()
        )
        safe_followup_reason = safe_followup_reason or None
        original_requests = {
            request["service_type"]: request for request in draft["structured"].get("requests", [])
        }
        approved_requests: list[dict[str, Any]] = []
        survey_ids: list[str] = []
        assessments: dict[str, dict[str, Any]] = {}
        if len({request.service_type for request in item.requests}) != len(item.requests):
            raise HTTPException(
                status_code=422, detail="서비스 종류별 요청은 한 건씩 검토해 주세요."
            )

        for request in item.requests:
            policy = policies.get(request.service_type)
            if policy is None or policy["policy_status"] != "ALLOWED":
                raise HTTPException(
                    status_code=422,
                    detail="초기 허용 서비스만 조사 evidence로 승인할 수 있습니다.",
                )
            urgency_evidence, urgency_was_redacted = redact_pii(
                (request.urgency_evidence or "").strip()
            )
            if request.urgency and (
                not urgency_evidence
                or urgency_evidence.casefold() not in draft["source_text_redacted"].casefold()
            ):
                raise HTTPException(
                    status_code=422,
                    detail="긴급도는 저장된 원문에 포함된 근거 표현과 함께 승인해야 합니다.",
                )
            if not request.urgency and urgency_evidence:
                raise HTTPException(
                    status_code=422, detail="긴급도 근거에는 긴급 표시가 필요합니다."
                )

            period, period_was_redacted = redact_pii((request.requested_period or "").strip())
            constraints: list[str] = []
            constraints_were_redacted = False
            for value in request.constraints:
                safe_value, changed = redact_pii(value.strip())
                if safe_value:
                    constraints.append(safe_value)
                constraints_were_redacted = constraints_were_redacted or changed
            request_data = request.model_dump(mode="json")
            request_data["requested_period"] = period or None
            request_data["constraints"] = constraints
            request_data["urgency_evidence"] = urgency_evidence or None
            approved_requests.append(request_data)

            survey_data = {
                **request_data,
                "evidence_source": draft["survey_type"],
                "structuring_confidence": draft["structured"].get("confidence"),
                "structuring_method": draft["structured"].get("method"),
                "review_status": "APPROVED",
                "followup_reason": safe_followup_reason,
                "original_ai_request": original_requests.get(request.service_type),
            }
            survey_id = database.insert_survey(
                connection,
                area_id=str(draft["area_id"]),
                survey_type=str(draft["survey_type"]),
                survey_date=str(draft["survey_date"]),
                service_type=request.service_type,
                frequency_per_month=request.frequency_per_month,
                preferred_period=period or None,
                preferred_days=request.preferred_days,
                constraints=constraints,
                free_text_note=str(draft["source_text_redacted"]),
                source_text_was_redacted=(
                    bool(draft["source_text_was_redacted"])
                    or urgency_was_redacted
                    or period_was_redacted
                    or constraints_were_redacted
                    or followup_was_redacted
                ),
                structured_data={
                    **survey_data,
                    "needs_followup_survey": item.needs_followup_survey,
                },
                provenance="SIMULATED HUMAN REVIEW",
            )
            survey_ids.append(survey_id)
            baseline_count = (
                int(area["demand_observation_count"])
                if request.service_type == area["service_type"]
                else 0
            )
            assessment, _ = _assessment_for_area(
                area,
                connection,
                baseline_count=baseline_count,
                service_type=request.service_type,
                commit=False,
            )
            assessments[request.service_type] = assessment

        approved = {
            "requests": approved_requests,
            "needs_followup_survey": item.needs_followup_survey,
            "followup_reason": safe_followup_reason,
            "confidence": draft["structured"].get("confidence"),
            "method": draft["structured"].get("method"),
            "evidence_source": draft["survey_type"],
            "review_status": "APPROVED",
        }
        if not database.approve_demand_structuring_draft(
            connection,
            draft_id=draft_id,
            survey_ids=survey_ids,
            approved=approved,
        ):
            raise HTTPException(status_code=409, detail="초안 상태가 변경되어 승인할 수 없습니다.")
        connection.commit()
        return {
            "draft_id": draft_id,
            "status": "APPROVED",
            "approved_requests": approved_requests,
            "survey_ids": survey_ids,
            "evidence_assessments": assessments,
            "provenance": "SIMULATED HUMAN REVIEW",
        }
    except HTTPException:
        connection.rollback()
        raise
    except sqlite3.Error:
        connection.rollback()
        raise HTTPException(
            status_code=503, detail="검토한 수요 evidence를 저장하지 못했습니다."
        ) from None
    finally:
        connection.close()
