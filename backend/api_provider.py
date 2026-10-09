"""Provider realism API: directory sources, fallback candidates, reserve comparison."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query, Request
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


class ProviderMappingReviewInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["VERIFIED_MAPPING", "REJECTED_MAPPING"]
    review_note: Annotated[str, Field(default="", max_length=500)]


class ProviderDuplicateReviewInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["CONFIRMED_SAME", "CONFIRMED_DISTINCT"]


def _planning_context(region_id: str, *, owner_session_hash: str | None = None):
    from backend import main

    demo = main._load_demo()
    try:
        data = select_region(demo, region_id)
    except ValueError as exc:
        raise AppError(errors.VALIDATION_ERROR, str(exc), status_code=422) from None
    app_connection = database.connect()
    database.seed_reference_data(app_connection, demo)
    database.seed_provider_data(app_connection, demo)
    providers = main._prepare_planning_inputs(
        app_connection, data, owner_session_hash=owner_session_hash
    )
    travel_connection = travel_connect()
    if any(
        get_cached(travel_connection, origin, destination) is None
        for origin in data["areas"]
        for destination in data["areas"]
    ):
        app_connection.close()
        travel_connection.close()
        raise AppError(
            errors.ROUTE_UNAVAILABLE,
            "선택 지역의 도로 경로 캐시가 불완전합니다.",
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
    connection = database.connect()
    try:
        sources = provider_directory.registry_source_report(connection)
        connection.commit()
        return {"sources": sources, "note": provider_directory.BADGE_NOTE}
    finally:
        connection.close()


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
        if (
            connection.execute(
                "SELECT 1 FROM providers WHERE provider_id=?", (item.provider_id,)
            ).fetchone()
            is None
        ):
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
        return {
            "entry": provider_directory.linked_entry(connection, item.provider_id),
            "badges": provider_directory.provider_badges(connection, item.provider_id),
            "note": provider_directory.BADGE_NOTE,
        }
    finally:
        connection.close()


@router.get("/provider-directory/entries")
def directory_entries(
    region_id: str | None = None,
    source_id: str | None = None,
    search: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, Any]:
    connection = database.connect()
    try:
        return {
            "entries": provider_directory.list_entries(
                connection,
                region_id,
                source_id=source_id,
                search=search,
                limit=limit,
                offset=offset,
            ),
            "note": provider_directory.BADGE_NOTE,
        }
    finally:
        connection.close()


@router.get("/provider-directory/duplicates")
def directory_duplicate_candidates(
    status: Literal["POSSIBLE_DUPLICATE", "CONFIRMED_SAME", "CONFIRMED_DISTINCT"] | None = None,
) -> dict[str, Any]:
    connection = database.connect()
    try:
        rows = connection.execute(
            """SELECT c.candidate_id, c.entry_id_a, c.entry_id_b, c.match_signals_json,
                      c.status, a.name AS name_a, a.source_id AS source_a,
                      b.name AS name_b, b.source_id AS source_b
               FROM provider_duplicate_candidates c
               JOIN provider_directory_entries a ON a.entry_id=c.entry_id_a
               JOIN provider_directory_entries b ON b.entry_id=c.entry_id_b
               WHERE (? IS NULL OR c.status=?) ORDER BY c.created_at DESC LIMIT 200""",
            (status, status),
        ).fetchall()
        return {"candidates": [dict(row) for row in rows]}
    finally:
        connection.close()


@router.post("/provider-directory/duplicates/{candidate_id}/review")
def review_directory_duplicate_candidate(
    candidate_id: str, item: ProviderDuplicateReviewInput
) -> dict[str, Any]:
    connection = database.connect()
    try:
        cursor = connection.execute(
            """UPDATE provider_duplicate_candidates
               SET status=?, reviewed_at=strftime('%Y-%m-%dT%H:%M:%SZ','now')
               WHERE candidate_id=? AND status='POSSIBLE_DUPLICATE'""",
            (item.status, candidate_id),
        )
        if cursor.rowcount == 0:
            raise AppError(
                errors.VALIDATION_ERROR,
                "검토 대기 중인 중복 후보가 없습니다.",
                status_code=404,
            )
        connection.commit()
        return {
            "candidate_id": candidate_id,
            "status": item.status,
            "automatic_merge": False,
        }
    finally:
        connection.close()


@router.get("/provider-directory/service-mappings")
def directory_service_mappings(
    status: Literal["UNMAPPED", "MAPPING_SUGGESTED", "VERIFIED_MAPPING", "REJECTED_MAPPING"]
    | None = None,
) -> dict[str, Any]:
    connection = database.connect()
    try:
        rows = connection.execute(
            """SELECT m.*, e.name AS organization_name, e.source_id
               FROM provider_service_mapping_reviews m
               JOIN provider_directory_entries e ON e.entry_id=m.entry_id
               WHERE (? IS NULL OR m.status=?) ORDER BY m.created_at DESC LIMIT 500""",
            (status, status),
        ).fetchall()
        return {"mappings": [dict(row) for row in rows]}
    finally:
        connection.close()


@router.post("/provider-directory/service-mappings/{mapping_id}/review")
def review_directory_service_mapping(
    mapping_id: str, item: ProviderMappingReviewInput
) -> dict[str, Any]:
    connection = database.connect()
    try:
        mapping = connection.execute(
            """SELECT mapping_id, suggested_service_type, regulation_level
               FROM provider_service_mapping_reviews WHERE mapping_id=?""",
            (mapping_id,),
        ).fetchone()
        if mapping is None:
            raise AppError(errors.VALIDATION_ERROR, "서비스 매핑 후보가 없습니다.", status_code=404)
        if item.status == "VERIFIED_MAPPING":
            if mapping["regulation_level"] not in {"UNREGULATED", "LIMITED"}:
                raise AppError(
                    errors.VALIDATION_ERROR,
                    "LICENSE_REQUIRED 또는 EXCLUDED 작업은 초기 scope에서 확정할 수 없습니다.",
                    status_code=422,
                )
            policy = connection.execute(
                "SELECT policy_status FROM service_types WHERE service_type_id=?",
                (mapping["suggested_service_type"],),
            ).fetchone()
            if policy is None or policy["policy_status"] != "ALLOWED":
                raise AppError(
                    errors.VALIDATION_ERROR,
                    "현재 허용된 서비스 범위만 매핑을 확인할 수 있습니다.",
                    status_code=422,
                )
        connection.execute(
            """UPDATE provider_service_mapping_reviews
               SET status=?, review_note=?, reviewed_at=strftime('%Y-%m-%dT%H:%M:%SZ','now')
               WHERE mapping_id=?""",
            (item.status, item.review_note.strip() or None, mapping_id),
        )
        connection.commit()
        return {"mapping_id": mapping_id, "status": item.status}
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
        if (
            connection.execute(
                "SELECT 1 FROM providers WHERE provider_id=?", (provider_id,)
            ).fetchone()
            is None
        ):
            raise AppError(errors.VALIDATION_ERROR, "존재하지 않는 제공자입니다.", status_code=404)
        return {
            "provider_id": provider_id,
            "badges": provider_directory.provider_badges(connection, provider_id),
            "directory_entry": provider_directory.linked_entry(connection, provider_id),
            "note": provider_directory.BADGE_NOTE,
        }
    finally:
        connection.close()


def _run_inputs(region_id: str, budget_won: int, scenario: str, depth: int):
    data, providers, app_connection, travel_connection, capabilities = _planning_context(region_id)
    try:
        policy = PlanningPolicy()
        plan = scheduling_module.generate_provider_schedule(
            data["areas"],
            providers,
            travel_connection,
            budget_won,
            scenario,
            policy,
            allow_route_fallback=True,
        )
        routes = scheduling_module._route_rows(travel_connection)
        result = provider_fallback.fallback_candidates(
            data["areas"],
            providers,
            routes,
            policy,
            plan["rounds"],
            capabilities=capabilities,
            depth=depth,
        )
        if plan["rounds"] and len(providers) < 2:
            raise AppError(
                errors.NO_FALLBACK_PROVIDER,
                "대체 후보로 둘 수 있는 제공자가 없습니다.",
                status_code=409,
            )
        badges = {
            str(p["provider_id"]): provider_directory.provider_badges(
                app_connection, str(p["provider_id"])
            )
            for p in providers
        }
        return {
            "region_id": region_id,
            "scenario": scenario,
            "budget_won": budget_won,
            "provider_badges": badges,
            **result,
        }
    finally:
        app_connection.close()
        travel_connection.close()


@router.post("/regions/{region_id}/fallback-candidates")
def fallback_candidates(region_id: str, item: FallbackInput) -> dict[str, Any]:
    return _run_inputs(region_id, item.budget_won, item.scenario, item.depth)


@router.get("/regions/{region_id}/reserve-comparison")
def reserve_comparison(
    request: Request,
    region_id: str,
    budget_won: Annotated[int, Query(ge=0, le=10_000_000_000)],
    reserve_pct: Annotated[int, Query()] = 10,
    scenario: PlanScenario = "balanced",
) -> dict[str, Any]:
    if reserve_pct not in provider_fallback.RESERVE_RATIOS_PCT:
        raise AppError(
            errors.VALIDATION_ERROR,
            "예비 비율은 0, 5, 10, 15 중 담당자가 선택해야 합니다.",
            status_code=422,
            details={"allowed": list(provider_fallback.RESERVE_RATIOS_PCT)},
        )
    from backend import main

    owner_hash = main._public_demo_owner_hash(request)
    data, providers, app_connection, travel_connection, capabilities = _planning_context(
        region_id, owner_session_hash=owner_hash
    )
    try:
        return {
            "region_id": region_id,
            **provider_fallback.compare_reserve_policies(
                data["areas"],
                providers,
                travel_connection,
                budget_won,
                reserve_pct=reserve_pct,
                scenario=scenario,
                capabilities=capabilities,
                max_solver_seconds=RESERVE_SOLVER_SECONDS,
            ),
        }
    finally:
        app_connection.close()
        travel_connection.close()
