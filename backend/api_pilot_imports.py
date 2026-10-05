"""Preview-first pilot data import API."""

from __future__ import annotations

import csv
import io
import json
import sqlite3
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict
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

router = APIRouter(prefix="/api/pilot-imports")
setup_router = APIRouter(prefix="/api/pilot-setup")


class ConfirmInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirm: bool


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
            )
        except ValueError as exc:
            connection.rollback()
            raise HTTPException(status_code=422, detail=str(exc)) from None
        connection.commit()
        batch["already_exists"] = already_exists
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
        connection.commit()
        batch["already_confirmed"] = already_confirmed
        return batch
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
) -> dict[str, Any]:
    connection = database.connect()
    try:
        counts = {
            str(row["template_type"]): int(row["count"])
            for row in connection.execute(
                """SELECT template_type,COUNT(*) AS count FROM pilot_import_records
                   GROUP BY template_type"""
            )
        }
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
                "status": "LIMITED; 현재 intake를 기존 optimizer에 자동 연결하지 않음",
            },
        ]
        return {
            "workspace_label": "파일럿 자료 준비",
            "dimensions": dimensions,
            "calibration": calibration,
            "steps": steps,
            "planning_gate": (
                "LIMITED_PLANNING; confirmed pilot import records are not automatically "
                "injected into the current demo optimizer"
            ),
            "note": "조직 등재, 운영조건, 실제 수행, 계획 승인 상태를 서로 구별합니다.",
        }
    except sqlite3.Error:
        raise HTTPException(status_code=503, detail="파일럿 준비도를 읽지 못했습니다.") from None
    finally:
        connection.close()
