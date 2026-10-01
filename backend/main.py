"""FastAPI entry point for the VillageCoverage prototype."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field

from backend import database
from backend.demand import assess_evidence, redact_pii, structure_demand
from backend.optimization import evaluate_scenarios
from backend.scheduling import generate_provider_schedule
from backend.settings import DEFAULT_ALLOWED_SERVICES, PlanningPolicy
from backend.travel import connect, matrix_summary
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
    database.save_assessment(
        connection,
        area_id=str(area["id"]),
        service_type=assessed_service,
        assessment=assessment,
    )
    return assessment, surveys


def _scenario_data(
    budget: int, policy: PlanningPolicy | None = None
) -> tuple[dict[str, Any], dict[str, Any]]:
    data = _load_demo()
    app_connection: sqlite3.Connection | None = None
    travel_connection: sqlite3.Connection | None = None
    try:
        app_connection = database.connect()
        database.seed_reference_data(app_connection, data)
        database.seed_provider_data(app_connection, data)
        provider_rows = app_connection.execute(
            """SELECT p.provider_id, p.minimum_compensation_won,
                      GROUP_CONCAT(DISTINCT s.service_type) AS supported_services
               FROM providers p LEFT JOIN provider_services s USING(provider_id)
               GROUP BY p.provider_id"""
        ).fetchall()
        provider_profiles = {str(row["provider_id"]): row for row in provider_rows}
        for provider in data["providers"]:
            profile = provider_profiles.get(str(provider["id"]))
            if profile is not None:
                provider["minimum_compensation_won"] = int(profile["minimum_compensation_won"])
                provider["supported_services"] = sorted(
                    str(profile["supported_services"]).split(",")
                    if profile["supported_services"]
                    else []
                )
        for area in data["areas"]:
            assessment, _ = _assessment_for_area(area, app_connection)
            area["demand_observation_count"] = assessment["observation_count"]
            area["demand_data_count"] = assessment["observation_count"]
            area["demand_confidence"] = assessment["status"]
            area["needs_survey"] = assessment["needs_survey"]
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
        summary = matrix_summary(travel_connection)
        if summary["route_count"] < len(data["areas"]) ** 2:
            raise ValueError("travel cache incomplete")
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


@app.get("/api/overview")
def overview(
    budget: int = Query(default=DEFAULT_BUDGET, ge=0, le=100_000_000),
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
    data, scenarios = _scenario_data(budget, budget_policy)
    return {
        "region": data["region"],
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
    data, scenarios = _scenario_data(budget)
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
def providers() -> dict[str, Any]:
    connection = database.connect()
    try:
        _seed_providers(connection)
        return {
            "providers": database.list_providers(connection),
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


@app.post("/api/schedules", status_code=201)
def create_schedule_plan(item: SchedulePlanInput) -> dict[str, Any]:
    data = _load_demo()
    app_connection: sqlite3.Connection | None = None
    travel_connection: sqlite3.Connection | None = None
    try:
        app_connection = database.connect()
        database.seed_reference_data(app_connection, data)
        database.seed_provider_data(app_connection, data)
        providers = []
        for summary in database.list_providers(app_connection):
            provider_data = database.provider_detail(app_connection, summary["provider_id"])
            if provider_data is not None:
                providers.append(provider_data)
        for area in data["areas"]:
            surveys = database.list_surveys(
                app_connection, str(area["id"]), str(area["service_type"])
            )
            area["preferred_days"] = sorted(
                {day for survey in surveys for day in survey["preferred_days"]}
            )
        travel_connection = connect()
        route_count = matrix_summary(travel_connection)["route_count"]
        if route_count < len(data["areas"]) ** 2:
            raise ValueError("provider road route cache is incomplete")
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
