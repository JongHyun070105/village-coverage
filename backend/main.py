"""FastAPI entry point for the VillageCoverage prototype."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field

from backend.demand import assess_evidence, structure_demand
from backend.optimization import evaluate_scenarios
from backend.travel import connect, matrix_summary
from scripts.api_smoke_test import _load_config

ROOT = Path(__file__).resolve().parents[1]
DEMO_DATA_PATH = ROOT / "data" / "demo.json"
QUALITY_PATH = ROOT / "artifacts" / "data_quality_report.json"
SCHEMA_PATH = ROOT / "artifacts" / "public_schema_manifest.json"
DEFAULT_BUDGET = 5_000_000


class DemandInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(max_length=10000)


app = FastAPI(
    title="VillageCoverage API",
    version="0.1.0",
    description="Rural service coverage planning prototype with low-data protection.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in _load_config("FRONTEND_ORIGINS").split(",")
        if origin.strip()
    ] or [
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


def _scenario_data(budget: int) -> tuple[dict[str, Any], dict[str, Any]]:
    data = _load_demo()
    try:
        connection = connect()
        summary = matrix_summary(connection)
        if summary["route_count"] < len(data["areas"]) ** 2:
            raise ValueError("travel cache incomplete")
        scenarios = evaluate_scenarios(data["areas"], data["providers"], connection, budget)
        connection.close()
        return data, scenarios
    except Exception:
        raise HTTPException(
            status_code=503,
            detail=(
                "실제 도로 이동 캐시가 없습니다. "
                "먼저 scripts/build_travel_matrix.py 를 실행해 주세요."
            ),
        ) from None


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
def overview(budget: int = Query(default=DEFAULT_BUDGET, ge=0, le=100_000_000)) -> dict[str, Any]:
    data, scenarios = _scenario_data(budget)
    return {
        "region": data["region"],
        "budget_won": budget,
        "planning_defaults": data["planning_defaults"],
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
    data, scenarios = _scenario_data(budget)
    area = next((item for item in data["areas"] if item["id"] == area_id), None)
    if area is None:
        raise HTTPException(status_code=404, detail="해당 서비스 권역을 찾을 수 없습니다.")
    assessments = {
        scenario: next(row for row in result["assignments"] if row["area_id"] == area_id)
        for scenario, result in scenarios["scenario_results"].items()
    }
    evidence = assess_evidence(
        observation_count=int(area["demand_observation_count"]),
        source_diversity=1,
        missingness=0.0,
        model_confidence=None,
    )
    return {
        "area": area,
        "scenario_assessments": assessments,
        "evidence": evidence.model_dump(mode="json"),
        "survey_recommendation": (
            "전화·회의 기록을 추가 확인하고 계절별 수요를 조사하세요."
            if evidence.needs_survey
            else "요청 기록의 최근성과 출처 다양성을 계속 확인하세요."
        ),
    }


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
