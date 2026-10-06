"""Preview-first pilot data import API."""

from __future__ import annotations

import csv
import io
import json
import sqlite3
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from starlette.responses import Response

from backend import database
from backend.calibration_readiness import calibration_readiness
from backend.pilot_imports import (
    MAX_PILOT_CSV_BYTES,
    PILOT_TEMPLATES,
    SOURCE_TYPES,
    confirm_preview,
    create_preview,
    template_manifest,
)
from backend.pilot_lifecycle import (
    PilotLifecycleError,
    create_context,
    create_pilot_plan,
    execution_metrics,
    get_context,
    get_pilot_plan,
    link_resident_feedback,
    list_contexts,
    list_pilot_plans,
    promote_batch,
    record_assumption,
    replan_pilot_plan,
    review_service_mapping,
    transition_pilot_plan,
)

router = APIRouter(prefix="/api/pilot-imports")
setup_router = APIRouter(prefix="/api/pilot-setup")
context_router = APIRouter(prefix="/api/pilot-contexts")


class ConfirmInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirm: bool


class ContextInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    context_name: str = Field(min_length=1, max_length=120)
    region_code: str = Field(min_length=1, max_length=80)
    data_mode: Literal["PILOT", "SYNTHETIC_REHEARSAL"] = "PILOT"


class AssumptionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    assumption_key: Literal[
        "route_matrix",
        "provider_base_locations",
        "service_prices_won",
        "service_duration_minutes",
    ]
    value: dict[str, Any] | list[dict[str, Any]]
    reason: str = Field(min_length=1, max_length=500)
    provenance: Literal["SCENARIO_ASSUMPTION", "SIMULATED"] = "SCENARIO_ASSUMPTION"


class MappingReviewInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider_org_id: str = Field(min_length=1, max_length=120)
    service_type: Literal["laundry", "daily_necessities", "home_repair"]
    decision: Literal["VERIFIED_MAPPING", "REJECTED_MAPPING"]
    reviewer_role: Literal["PLANNER", "REVIEWER"]
    note: str | None = Field(default=None, max_length=500)


class PilotPlanInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scenario: Literal["efficiency", "balanced", "underserved_first", "minimum_coverage"]
    budget_won: int = Field(ge=0, le=100_000_000)


class PilotPlanApprovalInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["submit", "approve", "request_changes"]
    role: Literal["PLANNER", "REVIEWER"]
    comment: str | None = Field(default=None, max_length=500)


class PilotReplanInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    change_reason: str | None = Field(default=None, max_length=500)


@router.get("/templates")
def pilot_import_templates() -> dict[str, Any]:
    return {"templates": template_manifest(), "source_types": sorted(SOURCE_TYPES)}


@router.get("")
def pilot_import_batches(limit: int = Query(default=20, ge=1, le=100)) -> dict[str, Any]:
    connection = database.connect()
    try:
        batches = [
            dict(row)
            for row in connection.execute(
                """SELECT batch_id,file_name,content_sha256,template_type,uploaded_at,
                          validated_at,confirmed_at,rows_total,rows_valid,rows_warning,
                          rows_error,rows_imported,status,source_type,snapshot_id
                   FROM pilot_import_batches ORDER BY uploaded_at DESC LIMIT ?""",
                (limit,),
            )
        ]
        return {"batches": batches}
    except sqlite3.Error:
        raise HTTPException(
            status_code=503, detail="파일럿 가져오기 이력을 읽지 못했습니다."
        ) from None
    finally:
        connection.close()


@router.post("/{template_type}/preview", status_code=201)
async def preview_pilot_import(
    template_type: str,
    request: Request,
    file_name: str = Query(default="upload.csv", max_length=255),
    source_type: Literal[
        "PUBLIC_DATA",
        "OFFICIAL_DIRECTORY",
        "LOCAL_AUTHORITY_INPUT",
        "SURVEY_INPUT",
        "PROVIDER_SELF_REPORTED",
        "SERVICE_EXECUTION_LOG",
        "RESIDENT_FEEDBACK",
        "SIMULATED",
    ] = "LOCAL_AUTHORITY_INPUT",
    snapshot_id: str | None = Query(default=None, max_length=160),
    context_id: str | None = Query(default=None, max_length=80),
) -> dict[str, Any]:
    if template_type not in PILOT_TEMPLATES:
        raise HTTPException(status_code=404, detail="지원하지 않는 파일럿 CSV 양식입니다.")
    content_length = request.headers.get("content-length")
    if content_length and content_length.isdigit() and int(content_length) > MAX_PILOT_CSV_BYTES:
        raise HTTPException(status_code=413, detail="CSV 파일은 10MB 이하만 가져올 수 있습니다.")
    payload = await request.body()
    connection = database.connect()
    try:
        try:
            batch, already_exists = create_preview(
                connection,
                template_type=template_type,
                file_name=file_name,
                payload=payload,
                source_type=source_type,
                snapshot_id=snapshot_id,
                context_id=context_id,
            )
        except ValueError as exc:
            connection.rollback()
            raise HTTPException(status_code=422, detail=str(exc)) from None
        connection.commit()
        batch["already_exists"] = already_exists
        batch["context_id"] = context_id
        return batch
    except sqlite3.Error:
        connection.rollback()
        raise HTTPException(status_code=503, detail="CSV 미리보기를 저장하지 못했습니다.") from None
    finally:
        connection.close()


@router.get("/{batch_id}")
def pilot_import_detail(batch_id: str) -> dict[str, Any]:
    connection = database.connect()
    try:
        row = connection.execute(
            "SELECT batch_id FROM pilot_import_batches WHERE batch_id=?", (batch_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(
                status_code=404, detail="파일럿 가져오기 미리보기를 찾을 수 없습니다."
            )
        from backend.pilot_imports import _batch_dict

        batch = _batch_dict(connection, batch_id)
        assert batch is not None
        return batch
    except sqlite3.Error:
        raise HTTPException(status_code=503, detail="미리보기를 읽지 못했습니다.") from None
    finally:
        connection.close()


@router.post("/{batch_id}/confirm")
def confirm_pilot_import(batch_id: str, item: ConfirmInput) -> dict[str, Any]:
    if not item.confirm:
        raise HTTPException(status_code=422, detail="명시적인 confirm=true가 필요합니다.")
    connection = database.connect()
    try:
        batch, already_confirmed = confirm_preview(connection, batch_id)
        if batch is None:
            raise HTTPException(
                status_code=404, detail="파일럿 가져오기 미리보기를 찾을 수 없습니다."
            )
        promotion = promote_batch(connection, batch_id)
        connection.commit()
        batch["already_confirmed"] = already_confirmed
        batch["promotion"] = promotion
        return batch
    except PilotLifecycleError as exc:
        connection.rollback()
        raise HTTPException(
            status_code=422, detail={"code": exc.code, "message": str(exc)}
        ) from None
    except sqlite3.Error:
        connection.rollback()
        raise HTTPException(
            status_code=503, detail="확정된 파일럿 자료를 저장하지 못했습니다."
        ) from None
    finally:
        connection.close()


@router.get("/{batch_id}/failed.csv")
def download_failed_pilot_rows(batch_id: str) -> Response:
    connection = database.connect()
    try:
        batch = connection.execute(
            "SELECT template_type FROM pilot_import_batches WHERE batch_id=?", (batch_id,)
        ).fetchone()
        if batch is None:
            raise HTTPException(
                status_code=404, detail="파일럿 가져오기 미리보기를 찾을 수 없습니다."
            )
        from backend.pilot_imports import _batch_dict

        details = _batch_dict(connection, batch_id)
        assert details is not None
        headers = list(PILOT_TEMPLATES[str(batch["template_type"])]) + [
            "extra_columns",
            "row_status",
            "issues",
        ]
        output = io.StringIO(newline="")
        writer = csv.DictWriter(output, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        for row in details["rows"]:
            if row["status"] != "ERROR":
                continue
            values = dict(row["normalized_record"])
            for key, value in values.items():
                if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
                    values[key] = "'" + value
            values["row_status"] = row["status"]
            values["issues"] = json.dumps(row["issues"], ensure_ascii=False)
            writer.writerow(values)
        return Response(
            "\ufeff" + output.getvalue(),
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="pilot-import-{batch_id}-failed.csv"'
            },
        )
    except sqlite3.Error:
        raise HTTPException(status_code=503, detail="실패 행을 내보내지 못했습니다.") from None
    finally:
        connection.close()


@setup_router.get("/readiness")
def pilot_setup_readiness(
    service_type: Literal["laundry", "daily_necessities", "home_repair"] = "laundry",
    region_code: str | None = Query(default=None, max_length=80),
    area_code: str | None = Query(default=None, pattern=r"^\d{10}$"),
    context_id: str | None = Query(default=None, max_length=80),
) -> dict[str, Any]:
    connection = database.connect()
    try:
        if context_id:
            if get_context(connection, context_id) is None:
                raise HTTPException(status_code=404, detail="파일럿 데이터셋을 찾을 수 없습니다.")
            counts = {
                str(row["template_type"]): int(row["count"])
                for row in connection.execute(
                    """SELECT template_type,COUNT(*) AS count FROM pilot_promoted_records
                       WHERE context_id=? GROUP BY template_type""",
                    (context_id,),
                )
            }
        else:
            counts = {
                str(row["template_type"]): int(row["count"])
                for row in connection.execute(
                    """SELECT template_type,COUNT(*) AS count FROM pilot_import_records
                       GROUP BY template_type"""
                )
            }
        if context_id:
            provider_count = int(
                connection.execute(
                    """SELECT COUNT(*) FROM pilot_promoted_records
                       WHERE context_id=? AND template_type='provider_organizations'
                       AND provenance='REAL_DIRECTORY'""",
                    (context_id,),
                ).fetchone()[0]
            )
            mapping_count = int(
                connection.execute(
                    """SELECT COUNT(*) FROM pilot_service_mapping_reviews
                       WHERE context_id=? AND decision='VERIFIED_MAPPING'""",
                    (context_id,),
                ).fetchone()[0]
            )
        else:
            provider_count = int(
                connection.execute(
                    """SELECT COUNT(*) FROM provider_directory_entries
                       WHERE existence_provenance='REAL_DIRECTORY'"""
                ).fetchone()[0]
            )
            mapping_count = int(
                connection.execute(
                    """SELECT COUNT(*) FROM provider_service_mapping_reviews
                       WHERE status='VERIFIED_MAPPING'"""
                ).fetchone()[0]
            )
        calibration = calibration_readiness(
            connection,
            service_type=service_type,
            region_code=region_code,
            area_code=area_code,
            context_id=context_id,
        )

        def state(count: int) -> str:
            return "READY" if count else "MISSING"

        dimensions = [
            {
                "id": "region",
                "label": "지역 기본자료",
                "status": state(counts.get("region_areas", 0)),
                "records": counts.get("region_areas", 0),
            },
            {
                "id": "provider_directory",
                "label": "공식 공급자 조직",
                "status": state(provider_count),
                "records": provider_count,
                "detail": "조직 존재만 확인; 운영조건은 별도",
            },
            {
                "id": "service_mapping",
                "label": "서비스 mapping 검토",
                "status": state(mapping_count),
                "records": mapping_count,
            },
            {
                "id": "demand",
                "label": "지역 수요 근거",
                "status": state(counts.get("demand_observations", 0) + counts.get("surveys", 0)),
                "records": counts.get("demand_observations", 0) + counts.get("surveys", 0),
            },
            {
                "id": "provider_conditions",
                "label": "공급자 운영조건",
                "status": state(
                    sum(
                        counts.get(name, 0)
                        for name in ("provider_availability", "provider_capacity")
                    )
                ),
                "records": counts.get("provider_availability", 0)
                + counts.get("provider_capacity", 0),
            },
            {
                "id": "prices",
                "label": "실제 공급단가",
                "status": state(counts.get("provider_prices", 0)),
                "records": counts.get("provider_prices", 0),
                "detail": "누락 단가는 UNKNOWN",
            },
            {
                "id": "execution",
                "label": "서비스 수행로그",
                "status": state(counts.get("service_execution_logs", 0)),
                "records": counts.get("service_execution_logs", 0),
            },
        ]
        steps = [
            {
                "step": 1,
                "label": "지역 선택",
                "status": "READY" if region_code or area_code else "NEEDS_SELECTION",
            },
            {"step": 2, "label": "공공자료 확인", "status": state(counts.get("region_areas", 0))},
            {"step": 3, "label": "공식 공급자 확인", "status": state(provider_count)},
            {
                "step": 4,
                "label": "수요자료 미리보기·확정",
                "status": state(counts.get("demand_observations", 0) + counts.get("surveys", 0)),
            },
            {
                "step": 5,
                "label": "공급조건·가격 확인",
                "status": state(
                    counts.get("provider_availability", 0)
                    + counts.get("provider_capacity", 0)
                    + counts.get("provider_prices", 0)
                ),
            },
            {"step": 6, "label": "자료 품질 검토", "status": "REVIEW_IN_IMPORT_PREVIEW"},
            {"step": 7, "label": "부족자료 확인", "status": "READY"},
            {
                "step": 8,
                "label": "기초계획 검토",
                "status": "READY_FOR_PILOT_PLAN"
                if context_id and counts.get("demand_observations", 0)
                else "DATA_INSUFFICIENT",
            },
        ]
        return {
            "workspace_label": "파일럿 자료 준비",
            "context_id": context_id,
            "dimensions": dimensions,
            "calibration": calibration,
            "steps": steps,
            "planning_gate": "PILOT_CONTEXT_SCOPED; DEMO DATA EXCLUDED"
            if context_id
            else "LIMITED_PLANNING; legacy workspace data is not a pilot optimizer input",
            "note": "조직 등재, 운영조건, 실제 수행, 계획 승인 상태를 서로 구별합니다.",
        }
    except sqlite3.Error:
        raise HTTPException(status_code=503, detail="파일럿 준비도를 읽지 못했습니다.") from None
    finally:
        connection.close()


@context_router.post("", status_code=201)
def create_pilot_context(item: ContextInput) -> dict[str, Any]:
    connection = database.connect()
    try:
        context = create_context(
            connection,
            context_name=item.context_name,
            region_code=item.region_code,
            data_mode=item.data_mode,
        )
        connection.commit()
        return context
    except PilotLifecycleError as exc:
        connection.rollback()
        raise HTTPException(
            status_code=422, detail={"code": exc.code, "message": str(exc)}
        ) from None
    except sqlite3.Error:
        connection.rollback()
        raise HTTPException(
            status_code=503, detail="파일럿 데이터셋을 만들지 못했습니다."
        ) from None
    finally:
        connection.close()


@context_router.get("")
def pilot_context_list(limit: int = Query(default=50, ge=1, le=200)) -> dict[str, Any]:
    connection = database.connect()
    try:
        return {"contexts": list_contexts(connection, limit)}
    finally:
        connection.close()


@context_router.get("/{context_id}")
def pilot_context_detail(context_id: str) -> dict[str, Any]:
    connection = database.connect()
    try:
        context = get_context(connection, context_id)
        if context is None:
            raise HTTPException(status_code=404, detail="파일럿 데이터셋을 찾을 수 없습니다.")
        return context
    finally:
        connection.close()


@context_router.post("/{context_id}/feedback/{feedback_id}", status_code=201)
def attach_context_feedback(context_id: str, feedback_id: str) -> dict[str, Any]:
    connection = database.connect()
    try:
        linked = link_resident_feedback(
            connection, context_id=context_id, feedback_id=feedback_id
        )
        connection.commit()
        return linked
    except PilotLifecycleError as exc:
        connection.rollback()
        status = 404 if exc.code in {"CONTEXT_NOT_FOUND", "FEEDBACK_NOT_FOUND"} else 409
        raise HTTPException(
            status_code=status, detail={"code": exc.code, "message": str(exc)}
        ) from None
    except sqlite3.Error:
        connection.rollback()
        raise HTTPException(status_code=503, detail="주민 의견을 연결하지 못했습니다.") from None
    finally:
        connection.close()


@context_router.post("/{context_id}/assumptions", status_code=201)
def add_pilot_assumption(context_id: str, item: AssumptionInput) -> dict[str, Any]:
    connection = database.connect()
    try:
        if get_context(connection, context_id) is None:
            raise HTTPException(status_code=404, detail="파일럿 데이터셋을 찾을 수 없습니다.")
        result = record_assumption(
            connection,
            context_id=context_id,
            assumption_key=item.assumption_key,
            value=item.value,
            reason=item.reason,
            provenance=item.provenance,
        )
        connection.commit()
        return result
    except PilotLifecycleError as exc:
        connection.rollback()
        raise HTTPException(
            status_code=422, detail={"code": exc.code, "message": str(exc)}
        ) from None
    except sqlite3.Error:
        connection.rollback()
        raise HTTPException(
            status_code=503, detail="시나리오 가정을 저장하지 못했습니다."
        ) from None
    finally:
        connection.close()


@context_router.post("/{context_id}/provider-service-mappings", status_code=201)
def decide_pilot_service_mapping(context_id: str, item: MappingReviewInput) -> dict[str, Any]:
    connection = database.connect()
    try:
        result = review_service_mapping(
            connection,
            context_id=context_id,
            provider_org_id=item.provider_org_id,
            service_type=item.service_type,
            decision=item.decision,
            reviewer_role=item.reviewer_role,
            note=item.note,
        )
        connection.commit()
        return result
    except PilotLifecycleError as exc:
        connection.rollback()
        status = 404 if exc.code in {"PROVIDER_NOT_FOUND", "SERVICE_MAPPING_NOT_FOUND"} else 422
        raise HTTPException(
            status_code=status, detail={"code": exc.code, "message": str(exc)}
        ) from None
    except sqlite3.Error:
        connection.rollback()
        raise HTTPException(
            status_code=503, detail="서비스 매핑 검토를 저장하지 못했습니다."
        ) from None
    finally:
        connection.close()


@context_router.post("/{context_id}/plans", status_code=201)
def create_context_plan(context_id: str, item: PilotPlanInput) -> dict[str, Any]:
    connection = database.connect()
    try:
        result = create_pilot_plan(
            connection,
            context_id=context_id,
            scenario=item.scenario,
            budget_won=item.budget_won,
        )
        connection.commit()
        return result
    except PilotLifecycleError as exc:
        connection.rollback()
        status = 404 if exc.code == "CONTEXT_NOT_FOUND" else 409
        raise HTTPException(
            status_code=status, detail={"code": exc.code, "message": str(exc)}
        ) from None
    except sqlite3.Error:
        connection.rollback()
        raise HTTPException(status_code=503, detail="파일럿 계획을 저장하지 못했습니다.") from None
    finally:
        connection.close()


@context_router.get("/{context_id}/plans")
def context_plan_list(context_id: str) -> dict[str, Any]:
    connection = database.connect()
    try:
        return {"plans": list_pilot_plans(connection, context_id)}
    except PilotLifecycleError as exc:
        raise HTTPException(
            status_code=404, detail={"code": exc.code, "message": str(exc)}
        ) from None
    finally:
        connection.close()


@context_router.get("/plans/{plan_id}")
def context_plan_detail(plan_id: str) -> dict[str, Any]:
    connection = database.connect()
    try:
        result = get_pilot_plan(connection, plan_id)
        if result is None:
            raise HTTPException(status_code=404, detail="파일럿 계획을 찾을 수 없습니다.")
        return result
    finally:
        connection.close()


@context_router.post("/plans/{plan_id}/replan", status_code=201)
def context_plan_replan(plan_id: str, item: PilotReplanInput) -> dict[str, Any]:
    connection = database.connect()
    try:
        result = replan_pilot_plan(connection, plan_id=plan_id, change_reason=item.change_reason)
        connection.commit()
        return result
    except PilotLifecycleError as exc:
        connection.rollback()
        status = 404 if exc.code in {"PLAN_NOT_FOUND", "PARENT_PLAN_NOT_FOUND"} else 409
        raise HTTPException(
            status_code=status, detail={"code": exc.code, "message": str(exc)}
        ) from None
    except sqlite3.Error:
        connection.rollback()
        raise HTTPException(
            status_code=503, detail="파일럿 재계획을 저장하지 못했습니다."
        ) from None
    finally:
        connection.close()


@context_router.post("/plans/{plan_id}/approval")
def context_plan_approval(plan_id: str, item: PilotPlanApprovalInput) -> dict[str, Any]:
    connection = database.connect()
    try:
        result = transition_pilot_plan(
            connection,
            plan_id=plan_id,
            action=item.action,
            role=item.role,
            comment=item.comment,
        )
        connection.commit()
        return result
    except PilotLifecycleError as exc:
        connection.rollback()
        status = 404 if exc.code == "PLAN_NOT_FOUND" else 409
        raise HTTPException(
            status_code=status, detail={"code": exc.code, "message": str(exc)}
        ) from None
    except sqlite3.Error:
        connection.rollback()
        raise HTTPException(
            status_code=503, detail="파일럿 계획 상태를 저장하지 못했습니다."
        ) from None
    finally:
        connection.close()


@context_router.get("/plans/{plan_id}/actuals")
def context_plan_actuals(plan_id: str) -> dict[str, Any]:
    connection = database.connect()
    try:
        result = execution_metrics(connection, plan_id)
        return {"plan_id": plan_id, **result}
    except PilotLifecycleError as exc:
        raise HTTPException(
            status_code=404, detail={"code": exc.code, "message": str(exc)}
        ) from None
    finally:
        connection.close()
