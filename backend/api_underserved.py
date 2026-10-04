"""Underserved-history API: policy, simulated demo seed, area status, policy comparison."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict, Field

from backend import database, underserved
from backend.regions import DEFAULT_REGION_ID, select_region
from backend.timeutils import korea_today

router = APIRouter(prefix="/api")


class HistoryMonthInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    area_id: str = Field(min_length=1, max_length=120)
    service_type: str = Field(min_length=1, max_length=60)
    month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    rounds_delivered: int = Field(ge=0, le=62)
    provenance: Literal["REAL_REPORTED"] = "REAL_REPORTED"


@router.get("/underserved/policy")
def underserved_policy() -> dict[str, Any]:
    return underserved.policy_payload()


@router.post("/underserved/history", status_code=201)
def record_history_month(item: HistoryMonthInput) -> dict[str, Any]:
    from backend import main

    connection = database.connect()
    try:
        database.seed_reference_data(connection, main._load_demo())
        underserved.upsert_history_month(connection, **item.model_dump())
        connection.commit()
        return {"recorded": True, "provenance": item.provenance}
    finally:
        connection.close()


@router.post("/regions/{region_id}/underserved/demo-seed")
def seed_demo_history(region_id: str) -> dict[str, Any]:
    from backend import main

    demo = main._load_demo()
    data = select_region(demo, region_id)
    connection = database.connect()
    try:
        database.seed_reference_data(connection, demo)
        month = underserved.current_month(korea_today())
        inserted = underserved.seed_simulated_history(
            connection, data["areas"], as_of_month=month
        )
        return {
            "region_id": region_id,
            "as_of_month": month,
            "rows_written": inserted,
            "provenance": "SIMULATED",
            "notice": "데모용 가상 이력입니다. 실제 서비스 이력이 아닙니다.",
        }
    finally:
        connection.close()


@router.get("/regions/{region_id}/underserved")
def region_underserved(region_id: str) -> dict[str, Any]:
    from backend import main

    demo = main._load_demo()
    data = select_region(demo, region_id)
    connection = database.connect()
    try:
        database.seed_reference_data(connection, demo)
        today = korea_today()
        rows = []
        for area in data["areas"]:
            area = dict(area)
            underserved.apply_to_area(area, connection, today=today)
            rows.append(
                {"area_id": area["id"], "area_name": area.get("name"), **area["underserved_metric"]}
            )
        return {
            "region_id": region_id,
            "policy": underserved.policy_payload(),
            "areas": rows,
            "status_counts": {
                status: sum(1 for row in rows if row["underserved_status"] == status)
                for status in underserved.UNDERSERVED_STATUSES
            },
        }
    finally:
        connection.close()


@router.get("/regions/{region_id}/underserved/comparison")
def region_underserved_comparison(
    region_id: str,
    budget: Annotated[int, Query(ge=0, le=100_000_000)] = 5_000_000,
) -> dict[str, Any]:
    from backend import main

    data, scenarios = main._scenario_data(budget, region_id=region_id or DEFAULT_REGION_ID)
    return {
        "region_id": data["region_id"],
        "budget_won": budget,
        **scenarios["underserved_comparison"],
    }
