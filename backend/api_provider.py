"""Provider realism API: directory sources, fallback candidates, reserve comparison."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict, Field

from backend import database, errors, home_repair, provider_directory, provider_fallback
from backend import scheduling as scheduling_module
from backend.errors import AppError
from backend.regions import select_region
from backend.settings import PlanningPolicy
from backend.travel import connect as travel_connect
from backend.travel import get_cached

RESERVE_SOLVER_SECONDS = 5.0

router = APIRouter(prefix="/api")
PlanScenario = Literal["efficiency", "balanced", "minimum_coverage", "underserved_first"]


class IngestInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_id: Annotated[str, Field(min_length=1, max_length=80)]
    rows: Annotated[list[dict[str, Any]], Field(max_length=2000)]


class FallbackInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    budget_won: int = Field(ge=0, le=10_000_000_000)
    scenario: PlanScenario = "balanced"
    depth: int = Field(default=2, ge=1, le=2)


class LinkDirectoryEntryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider_id: Annotated[str, Field(min_length=1, max_length=120)]


def _planning_context(region_id: str):
    from backend import main

    demo = main._load_demo()
    try:
        data = select_region(demo, region_id)
    except ValueError as exc:
        raise AppError(errors.VALIDATION_ERROR, str(exc), status_code=422) from None
    app_connection = database.connect()
    database.seed_reference_data(app_connection, demo)
    database.seed_provider_data(app_connection, demo)
    providers = main._prepare_planning_inputs(app_connection, data)
    travel_connection = travel_connect()
    if any(
        get_cached(travel_connection, origin, destination) is None
        for origin in data["areas"]
        for destination in data["areas"]
    ):
        app_connection.close()
        travel_connection.close()
        raise AppError(
            errors.ROUTE_UNAVAILABLE, "선택 지역의 도로 경로 캐시가 불완전합니다.",
            status_code=503,
        )
    capabilities = {
        str(p["provider_id"]): cap
        for p in providers
        if (cap := home_repair.get_capability(app_connection, str(p["provider_id"])))
    }
    return data, providers, app_connection, travel_connection, capabilities


@router.get("/provider-directory/sources")
def directory_sources() -> dict[str, Any]:
    return {"sources": provider_directory.directory_source_report(),
            "note": provider_directory.BADGE_NOTE}


@router.post("/provider-directory/ingest", status_code=201)
def directory_ingest(item: IngestInput) -> dict[str, Any]:
    connection = database.connect()
    try:
        return provider_directory.ingest_rows(connection, item.source_id, item.rows)
    finally:
        connection.close()


@router.post("/provider-directory/entries/{entry_id}/link")
def link_directory_entry(entry_id: str, item: LinkDirectoryEntryInput) -> dict[str, Any]:
    from backend import main

    connection = database.connect()
    try:
        demo = main._load_demo()
        database.seed_reference_data(connection, demo)
        database.seed_provider_data(connection, demo)
        if connection.execute(
            "SELECT 1 FROM providers WHERE provider_id=?", (item.provider_id,)
        ).fetchone() is None:
            raise AppError(errors.VALIDATION_ERROR, "존재하지 않는 제공자입니다.", status_code=404)
        entry = connection.execute(
            "SELECT source_id FROM provider_directory_entries WHERE entry_id=?", (entry_id,)
        ).fetchone()
        if entry is None:
            raise AppError(errors.VALIDATION_ERROR, "디렉터리 항목이 없습니다.", status_code=404)
        lifecycle = provider_directory.source_lifecycle(str(entry["source_id"]))
        if lifecycle["status"] != "INGEST_ALLOWED":
            raise AppError(
                errors.VALIDATION_ERROR, "수집이 허용되지 않은 출처입니다.", status_code=422
            )
        provider_directory.link_entry(connection, entry_id, item.provider_id)
        return {"entry": provider_directory.linked_entry(connection, item.provider_id),
                "badges": provider_directory.provider_badges(connection, item.provider_id),
                "note": provider_directory.BADGE_NOTE}
    finally:
        connection.close()


@router.get("/provider-directory/entries")
def directory_entries(region_id: str | None = None) -> dict[str, Any]:
    connection = database.connect()
    try:
        return {"entries": provider_directory.list_entries(connection, region_id),
                "note": provider_directory.BADGE_NOTE}
    finally:
        connection.close()


@router.get("/providers/{provider_id}/badges")
def provider_badges(provider_id: str) -> dict[str, Any]:
    from backend import main

    connection = database.connect()
    try:
        demo = main._load_demo()
        database.seed_reference_data(connection, demo)
        database.seed_provider_data(connection, demo)
        if connection.execute(
            "SELECT 1 FROM providers WHERE provider_id=?", (provider_id,)
        ).fetchone() is None:
            raise AppError(errors.VALIDATION_ERROR, "존재하지 않는 제공자입니다.", status_code=404)
        return {"provider_id": provider_id,
                "badges": provider_directory.provider_badges(connection, provider_id),
                "directory_entry": provider_directory.linked_entry(connection, provider_id),
                "note": provider_directory.BADGE_NOTE}
    finally:
        connection.close()


def _run_inputs(region_id: str, budget_won: int, scenario: str, depth: int):
    data, providers, app_connection, travel_connection, capabilities = _planning_context(
        region_id
    )
    try:
        policy = PlanningPolicy()
        plan = scheduling_module.generate_provider_schedule(
            data["areas"], providers, travel_connection, budget_won, scenario, policy,
            allow_route_fallback=True,
        )
        routes = scheduling_module._route_rows(travel_connection)
        result = provider_fallback.fallback_candidates(
            data["areas"], providers, routes, policy, plan["rounds"],
            capabilities=capabilities, depth=depth,
        )
        if plan["rounds"] and len(providers) < 2:
            raise AppError(
                errors.NO_FALLBACK_PROVIDER, "대체 후보로 둘 수 있는 제공자가 없습니다.",
                status_code=409,
            )
        badges = {
            str(p["provider_id"]): provider_directory.provider_badges(
                app_connection, str(p["provider_id"]))
            for p in providers
        }
        return {"region_id": region_id, "scenario": scenario, "budget_won": budget_won,
                "provider_badges": badges, **result}
    finally:
        app_connection.close()
        travel_connection.close()


@router.post("/regions/{region_id}/fallback-candidates")
def fallback_candidates(region_id: str, item: FallbackInput) -> dict[str, Any]:
    return _run_inputs(region_id, item.budget_won, item.scenario, item.depth)


@router.get("/regions/{region_id}/reserve-comparison")
def reserve_comparison(
    region_id: str,
    budget_won: Annotated[int, Query(ge=0, le=10_000_000_000)],
    reserve_pct: Annotated[int, Query()] = 10,
    scenario: PlanScenario = "balanced",
) -> dict[str, Any]:
    if reserve_pct not in provider_fallback.RESERVE_RATIOS_PCT:
        raise AppError(
            errors.VALIDATION_ERROR, "예비 비율은 0, 5, 10, 15 중 담당자가 선택해야 합니다.",
            status_code=422, details={"allowed": list(provider_fallback.RESERVE_RATIOS_PCT)},
        )
    data, providers, app_connection, travel_connection, capabilities = _planning_context(
        region_id
    )
    try:
        return {
            "region_id": region_id,
            **provider_fallback.compare_reserve_policies(
                data["areas"], providers, travel_connection, budget_won,
                reserve_pct=reserve_pct, scenario=scenario, capabilities=capabilities,
                max_solver_seconds=RESERVE_SOLVER_SECONDS,
            ),
        }
    finally:
        app_connection.close()
        travel_connection.close()
