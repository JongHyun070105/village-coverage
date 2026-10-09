"""Underserved-history API: policy, simulated demo seed, area status, policy comparison."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator

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
    last_served_date: date | None = None
    unmet_rounds: int | None = Field(default=None, ge=0, le=62)
    demand_rounds: int | None = Field(default=None, ge=0, le=62)
    provenance: Literal["REAL_REPORTED"] = "REAL_REPORTED"

    @model_validator(mode="after")
    def validate_history_detail(self) -> "HistoryMonthInput":
        if self.last_served_date is not None:
            if self.last_served_date.strftime("%Y-%m") != self.month or self.rounds_delivered == 0:
                raise ValueError("last_served_date must be in the month with delivered service")
        if (
            self.unmet_rounds is not None
            and self.demand_rounds is not None
            and self.unmet_rounds > self.demand_rounds
        ):
            raise ValueError("unmet_rounds cannot exceed demand_rounds")
        return self


@router.get("/underserved/policy")
def underserved_policy() -> dict[str, Any]:
    return underserved.policy_payload()


@router.post("/underserved/history", status_code=201)
def record_history_month(item: HistoryMonthInput) -> dict[str, Any]:
    from backend import main

    connection = database.connect()
    try:
        database.seed_reference_data(connection, main._load_demo())
        underserved.upsert_history_month(connection, **item.model_dump(mode="json"))
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
    request: Request,
    region_id: str,
    budget: Annotated[int, Query(ge=0, le=100_000_000)] = 5_000_000,
) -> dict[str, Any]:
    from backend import main

    data, scenarios = main._scenario_data(
        budget,
        region_id=region_id or DEFAULT_REGION_ID,
        owner_session_hash=main._public_demo_owner_hash(request),
    )
    return {
        "region_id": data["region_id"],
        "budget_won": budget,
        **scenarios["underserved_comparison"],
    }
