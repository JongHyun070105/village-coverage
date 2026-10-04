"""SIMPLE_HOME_REPAIR demo profile API: catalog, regulation gate, job demand, provider fit."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from backend import database, errors, home_repair
from backend.errors import AppError
from backend.regions import select_region

router = APIRouter(prefix="/api")


class ClassifyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: Annotated[str, Field(min_length=1, max_length=1000)]


class CapabilityInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    max_job_minutes: int | None = Field(default=None, ge=1, le=480)
    material_handling: Literal["NONE", "LOW", "MEDIUM", "HIGH", "UNKNOWN"] = "UNKNOWN"
    tools_available: bool | None = None
    provenance: Literal["SIMULATED", "PROVIDER_REPORTED"] = "SIMULATED"


@router.get("/home-repair/profile")
def home_repair_profile() -> dict[str, Any]:
    return home_repair.profile_payload()


@router.post("/home-repair/classify")
def classify_home_repair(item: ClassifyInput) -> dict[str, Any]:
    result = home_repair.classify_repair_text(item.text)
    result["auto_accepted"] = result["classification"] == "SIMPLE_REPAIR"
    return result


@router.get("/regions/{region_id}/home-repair/demand")
def region_home_repair_demand(region_id: str) -> dict[str, Any]:
    from backend import main

    data = select_region(main._load_demo(), region_id)
    areas = [home_repair.estimate_area_job_demand(area) for area in data["areas"]]
    return {
        "region_id": region_id,
        "profile_id": home_repair.PROFILE_ID,
        "areas": areas,
        "provenance": home_repair.PROVENANCE,
        "notice": "세탁 수요 모형과 별개인 작업 단위 시뮬레이션 추정이며 실측값이 아닙니다.",
    }


@router.put("/providers/{provider_id}/home-repair-capability")
def put_capability(provider_id: str, item: CapabilityInput) -> dict[str, Any]:
    from backend import main

    connection = database.connect()
    try:
        demo = main._load_demo()
        database.seed_reference_data(connection, demo)
        database.seed_provider_data(connection, demo)
        if not home_repair.set_capability(
            connection,
            provider_id,
            max_job_minutes=item.max_job_minutes,
            material_handling=item.material_handling,
            tools_available=item.tools_available,
            provenance=item.provenance,
        ):
            raise AppError(
                errors.VALIDATION_ERROR,
                "간단 수리를 제공하지 않는 제공자이거나 존재하지 않습니다.",
                status_code=404,
                details={"provider_id": provider_id},
            )
        connection.commit()
        capability = home_repair.get_capability(connection, provider_id) or {}
        return home_repair.provider_profile_fit(capability)
    finally:
        connection.close()


@router.get("/providers/{provider_id}/home-repair-capability")
def get_capability(provider_id: str) -> dict[str, Any]:
    from backend import main

    connection = database.connect()
    try:
        demo = main._load_demo()
        database.seed_reference_data(connection, demo)
        database.seed_provider_data(connection, demo)
        capability = home_repair.get_capability(connection, provider_id)
        if capability is None:
            raise AppError(
                errors.VALIDATION_ERROR,
                "간단 수리를 제공하지 않는 제공자이거나 존재하지 않습니다.",
                status_code=404,
                details={"provider_id": provider_id},
            )
        return home_repair.provider_profile_fit(capability)
    finally:
        connection.close()
