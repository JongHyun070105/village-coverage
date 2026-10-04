"""Cost model V3 API: itemised stored-plan cost and funding gap."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from backend import cost_model_v3, database

router = APIRouter(prefix="/api")
Won = Annotated[int | None, Field(default=None, ge=0, le=10_000_000_000)]


class CostAssumptions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    setup_per_round_won: Won = None
    material_per_unit_won: Won = None
    vehicle_per_round_won: Won = None
    fixed_participation_per_provider_month_won: Won = None
    other_funding_won: dict[str, Annotated[int | None, Field(ge=0, le=10_000_000_000)]] = Field(
        default_factory=dict, max_length=10
    )


@router.post("/schedules/{schedule_id}/cost-model-v3")
def schedule_cost_model(schedule_id: str, item: CostAssumptions) -> dict[str, Any]:
    connection = database.connect()
    try:
        plan = database.get_schedule_plan(connection, schedule_id)
    finally:
        connection.close()
    if plan is None:
        raise HTTPException(status_code=404, detail="공급 일정 계획을 찾을 수 없습니다.")
    assumptions = item.model_dump(exclude={"other_funding_won"})
    model = cost_model_v3.plan_cost_model(plan["rounds"], assumptions)
    gap = cost_model_v3.funding_gap(
        model, budget_won=int(plan["budget_won"]), other_funding=item.other_funding_won
    )
    return {"schedule_id": schedule_id, "cost_model": model, "funding_gap": gap}
