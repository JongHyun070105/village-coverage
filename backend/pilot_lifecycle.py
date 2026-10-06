"""Context-scoped pilot promotion and operational lifecycle records.

Pilot rows remain linked to their immutable import batch and row fingerprint.  This
module never reads demo fixtures; callers must provide a pilot context explicitly.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import uuid4

from backend.demand import assess_evidence, redact_pii
from backend.scheduling import generate_provider_schedule
from backend.settings import PlanningPolicy
from backend.timeutils import korea_today
from backend.travel import cache_key, get_cached
from backend.travel import connect as connect_travel_cache

DOMAIN_TYPES = {
    "region_areas": "VillageServiceArea",
    "demand_observations": "DemandEvidence",
    "surveys": "Survey",
    "provider_organizations": "ProviderOrganization",
    "provider_services": "ProviderService",
    "provider_availability": "ProviderAvailability",
    "provider_capacity": "ProviderCapacityConstraint",
    "provider_prices": "ProviderPriceInput",
    "provider_participation": "ProviderParticipation",
    "service_execution_logs": "ServiceExecutionLog",
}


class PilotLifecycleError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def create_context(
    connection: sqlite3.Connection,
    *,
    context_name: str,
    region_code: str,
    data_mode: str = "PILOT",
) -> dict[str, Any]:
    name, _ = redact_pii(context_name.strip())
    region = region_code.strip()
    if not name or len(name) > 120:
        raise PilotLifecycleError("INVALID_CONTEXT_NAME", "데이터셋 이름을 확인해 주세요.")
    if not region or len(region) > 80:
        raise PilotLifecycleError("INVALID_REGION_CODE", "지역 코드를 확인해 주세요.")
    if data_mode not in {"PILOT", "SYNTHETIC_REHEARSAL"}:
        raise PilotLifecycleError("INVALID_DATA_MODE", "파일럿 데이터 모드를 확인해 주세요.")
    context_id = f"pilot-{uuid4().hex[:20]}"
    now = _now()
    connection.execute(
        """INSERT INTO pilot_contexts(
             context_id,context_name,region_code,data_mode,created_at,updated_at
           ) VALUES (?,?,?,?,?,?)""",
        (context_id, name, region, data_mode, now, now),
    )
    return get_context(connection, context_id) or {}


def get_context(connection: sqlite3.Connection, context_id: str) -> dict[str, Any] | None:
    row = connection.execute(
        "SELECT * FROM pilot_contexts WHERE context_id=?", (context_id,)
    ).fetchone()
    if row is None:
        return None
    result = dict(row)
    result["import_batch_ids"] = [
        str(item[0])
        for item in connection.execute(
            """SELECT batch_id FROM pilot_context_batches WHERE context_id=?
               ORDER BY linked_at,batch_id""",
            (context_id,),
        )
    ]
    result["promoted_record_count"] = int(
        connection.execute(
            "SELECT COUNT(*) FROM pilot_promoted_records WHERE context_id=?", (context_id,)
        ).fetchone()[0]
    )
    snapshot = context_snapshot(connection, context_id)
    result["snapshot_id"] = snapshot["snapshot_id"]
    result["resident_feedback"] = snapshot["resident_feedback"]
    return result


def list_contexts(connection: sqlite3.Connection, limit: int = 50) -> list[dict[str, Any]]:
    ids = [
        str(row[0])
        for row in connection.execute(
            "SELECT context_id FROM pilot_contexts ORDER BY created_at DESC LIMIT ?", (limit,)
        )
    ]
    return [item for context_id in ids if (item := get_context(connection, context_id))]


def context_records(
    connection: sqlite3.Connection,
    context_id: str,
    template_type: str | None = None,
) -> list[dict[str, Any]]:
    params: tuple[Any, ...] = (context_id,)
    predicate = "context_id=?"
    if template_type is not None:
        predicate += " AND template_type=?"
        params = (context_id, template_type)
    result = []
    for row in connection.execute(
        f"""SELECT promoted_id,record_id,batch_id,template_type,domain_type,row_fingerprint,
                   source_type,provenance,payload_json,promoted_at
            FROM pilot_promoted_records WHERE {predicate}
            ORDER BY promoted_at,template_type,row_fingerprint""",
        params,
    ):
        item = dict(row)
        item["payload"] = json.loads(item.pop("payload_json"))
        result.append(item)
    return result


def context_batches(connection: sqlite3.Connection, context_id: str) -> list[str]:
    return [
        str(row[0])
        for row in connection.execute(
            """SELECT pcb.batch_id FROM pilot_context_batches pcb
               JOIN pilot_import_batches pib USING(batch_id)
               WHERE pcb.context_id=? AND pib.confirmed_at IS NOT NULL
               ORDER BY pib.confirmed_at,pib.batch_id""",
            (context_id,),
        )
    ]


def context_feedback(connection: sqlite3.Connection, context_id: str) -> list[dict[str, Any]]:
    """Return a privacy-minimized view of resident feedback linked to this pilot."""
    result = []
    rows = connection.execute(
        """SELECT rf.feedback_id,rf.feedback_type,rf.service_type,rf.status,rf.submitted_at,
                  va.legal_code AS area_code
           FROM pilot_context_feedback pcf
           JOIN resident_feedback rf USING(feedback_id)
           JOIN village_service_areas va ON va.area_id=rf.area_id
           WHERE pcf.context_id=? ORDER BY rf.submitted_at,rf.feedback_id""",
        (context_id,),
    )
    for row in rows:
        conflicts = [
            {
                "conflict_type": str(conflict["conflict_type"]),
                "status": str(conflict["status"]),
            }
            for conflict in connection.execute(
                """SELECT conflict_type,status FROM resident_feedback_conflicts
                   WHERE feedback_id=? ORDER BY conflict_type,conflict_id""",
                (row["feedback_id"],),
            )
        ]
        result.append(
            {
                "feedback_id": str(row["feedback_id"]),
                "feedback_type": str(row["feedback_type"]),
                "service_type": row["service_type"],
                "status": str(row["status"]),
                "submitted_at": str(row["submitted_at"]),
                "area_code": str(row["area_code"]),
                "source_type": "RESIDENT_FEEDBACK",
                "conflicts": conflicts,
                "unresolved_conflict_count": sum(
                    conflict["status"] == "REVIEW_REQUIRED" for conflict in conflicts
                ),
            }
        )
    return result


def link_resident_feedback(
    connection: sqlite3.Connection, *, context_id: str, feedback_id: str
) -> dict[str, Any]:
    context = get_context(connection, context_id)
    if context is None:
        raise PilotLifecycleError("CONTEXT_NOT_FOUND", "파일럿 데이터셋을 찾을 수 없습니다.")
    feedback = connection.execute(
        """SELECT rf.feedback_id,va.legal_code AS area_code
           FROM resident_feedback rf
           JOIN village_service_areas va ON va.area_id=rf.area_id
           WHERE rf.feedback_id=?""",
        (feedback_id,),
    ).fetchone()
    if feedback is None:
        raise PilotLifecycleError("FEEDBACK_NOT_FOUND", "연결할 주민 의견을 찾을 수 없습니다.")
    imported_area = connection.execute(
        """SELECT 1 FROM pilot_promoted_records
           WHERE context_id=? AND template_type='region_areas'
             AND json_extract(payload_json,'$.area_code')=? LIMIT 1""",
        (context_id, str(feedback["area_code"])),
    ).fetchone()
    if imported_area is None:
        raise PilotLifecycleError(
            "FEEDBACK_AREA_NOT_IN_CONTEXT",
            "의견의 법정동 코드와 일치하는 지역이 이 데이터셋에 없습니다.",
        )
    connection.execute(
        """INSERT OR IGNORE INTO pilot_context_feedback(context_id,feedback_id,linked_at)
           VALUES (?,?,?)""",
        (context_id, feedback_id, _now()),
    )
    connection.execute(
        "UPDATE pilot_contexts SET updated_at=? WHERE context_id=?", (_now(), context_id)
    )
    return next(
        item for item in context_feedback(connection, context_id)
        if item["feedback_id"] == feedback_id
    )


def context_snapshot(connection: sqlite3.Connection, context_id: str) -> dict[str, Any]:
    records = context_records(connection, context_id)
    batches = context_batches(connection, context_id)
    assumptions = [
        {
            "assumption_id": str(row["assumption_id"]),
            "assumption_key": str(row["assumption_key"]),
            "value": json.loads(row["value_json"]),
            "provenance": str(row["provenance"]),
            "reason": str(row["reason"]),
            "created_at": str(row["created_at"]),
        }
        for row in connection.execute(
            """SELECT * FROM pilot_scenario_assumptions WHERE context_id=?
               ORDER BY created_at,assumption_id""",
            (context_id,),
        )
    ]
    mapping_reviews = [
        dict(row)
        for row in connection.execute(
            """SELECT provider_org_id,service_type,decision,reviewer_role,note,reviewed_at
               FROM pilot_service_mapping_reviews WHERE context_id=?
               ORDER BY provider_org_id,service_type""",
            (context_id,),
        )
    ]
    feedback = context_feedback(connection, context_id)
    material = {
        "context_id": context_id,
        "import_batch_ids": batches,
        "records": [
            {
                "template_type": row["template_type"],
                "row_fingerprint": row["row_fingerprint"],
                "source_type": row["source_type"],
                "provenance": row["provenance"],
            }
            for row in records
        ],
        "assumptions": assumptions,
        "mapping_reviews": mapping_reviews,
        "resident_feedback": feedback,
    }
    digest = hashlib.sha256(
        json.dumps(material, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return {
        "snapshot_id": f"pilot-snapshot-{digest[:24]}",
        "import_batch_ids": batches,
        "record_count": len(records),
        "assumptions": assumptions,
        "mapping_reviews": mapping_reviews,
        "resident_feedback": feedback,
        "content_sha256": digest,
    }


def record_assumption(
    connection: sqlite3.Connection,
    *,
    context_id: str,
    assumption_key: str,
    value: Any,
    reason: str,
    provenance: str = "SCENARIO_ASSUMPTION",
) -> dict[str, Any]:
    if assumption_key not in {
        "route_matrix",
        "provider_base_locations",
        "service_prices_won",
        "service_duration_minutes",
    }:
        raise PilotLifecycleError("UNSUPPORTED_ASSUMPTION", "지원하지 않는 시나리오 가정입니다.")
    if provenance not in {"SCENARIO_ASSUMPTION", "SIMULATED"}:
        raise PilotLifecycleError("INVALID_ASSUMPTION_PROVENANCE", "가정 출처를 확인해 주세요.")
    reason, _ = redact_pii(reason.strip())
    if not reason or len(reason) > 500:
        raise PilotLifecycleError("ASSUMPTION_REASON_REQUIRED", "가정의 사유를 입력해 주세요.")
    if assumption_key == "route_matrix":
        if not isinstance(value, list) or not value:
            raise PilotLifecycleError("INVALID_ROUTE_MATRIX", "경로 행렬 자료가 필요합니다.")
        seen: set[tuple[str, str]] = set()
        for leg in value:
            try:
                origin = str(leg["origin_id"])
                destination = str(leg["destination_id"])
                distance = int(leg["distance_m"])
                duration = int(leg["duration_s"])
            except (KeyError, TypeError, ValueError):
                raise PilotLifecycleError(
                    "INVALID_ROUTE_MATRIX", "경로 행렬 형식이 올바르지 않습니다."
                ) from None
            if not origin or not destination or distance < 0 or duration < 0:
                raise PilotLifecycleError("INVALID_ROUTE_MATRIX", "경로 값은 0 이상이어야 합니다.")
            if (origin, destination) in seen:
                raise PilotLifecycleError(
                    "INVALID_ROUTE_MATRIX", "경로 행렬에 중복 구간이 있습니다."
                )
            seen.add((origin, destination))
    elif assumption_key == "provider_base_locations":
        if not isinstance(value, dict) or not value:
            raise PilotLifecycleError("INVALID_PROVIDER_LOCATION", "공급자 기준 위치가 필요합니다.")
        if any(
            not str(provider).strip() or not str(area).strip() for provider, area in value.items()
        ):
            raise PilotLifecycleError(
                "INVALID_PROVIDER_LOCATION", "공급자와 경로 노드를 확인해 주세요."
            )
    elif assumption_key == "service_prices_won":
        if not isinstance(value, dict) or not value:
            raise PilotLifecycleError("INVALID_SERVICE_PRICE", "서비스 가격 가정이 필요합니다.")
        try:
            if any(int(amount) <= 0 for prices in value.values() for amount in prices.values()):
                raise ValueError
        except (AttributeError, TypeError, ValueError):
            raise PilotLifecycleError(
                "INVALID_SERVICE_PRICE",
                "공급 단가는 1원 이상의 원 단위여야 합니다. "
                "미확인 가격을 0원으로 가정할 수 없습니다.",
            ) from None
    elif assumption_key == "service_duration_minutes":
        try:
            if (
                not isinstance(value, dict)
                or not value
                or any(isinstance(minutes, bool) or int(minutes) <= 0 for minutes in value.values())
            ):
                raise ValueError
        except (AttributeError, TypeError, ValueError):
            raise PilotLifecycleError(
                "INVALID_SERVICE_DURATION", "서비스 소요시간은 1분 이상의 정수여야 합니다."
            ) from None
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True)
    assumption_id = f"assumption-{uuid4().hex}"
    now = _now()
    connection.execute(
        """INSERT INTO pilot_scenario_assumptions(
             assumption_id,context_id,assumption_key,value_json,provenance,reason,created_at
           ) VALUES (?,?,?,?,?,?,?)""",
        (assumption_id, context_id, assumption_key, encoded, provenance, reason, now),
    )
    connection.execute(
        "UPDATE pilot_contexts SET updated_at=? WHERE context_id=?", (now, context_id)
    )
    return {
        "assumption_id": assumption_id,
        "context_id": context_id,
        "assumption_key": assumption_key,
        "value": json.loads(encoded),
        "provenance": provenance,
        "reason": reason,
        "created_at": now,
    }


def latest_assumptions(
    connection: sqlite3.Connection, context_id: str
) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for row in connection.execute(
        """SELECT * FROM pilot_scenario_assumptions WHERE context_id=?
           ORDER BY rowid""",
        (context_id,),
    ):
        latest[str(row["assumption_key"])] = {
            "assumption_id": str(row["assumption_id"]),
            "value": json.loads(row["value_json"]),
            "provenance": str(row["provenance"]),
            "reason": str(row["reason"]),
            "created_at": str(row["created_at"]),
        }
    return latest


def review_service_mapping(
    connection: sqlite3.Connection,
    *,
    context_id: str,
    provider_org_id: str,
    service_type: str,
    decision: str,
    reviewer_role: str,
    note: str | None = None,
) -> dict[str, Any]:
    if decision not in {"VERIFIED_MAPPING", "REJECTED_MAPPING"}:
        raise PilotLifecycleError("INVALID_MAPPING_DECISION", "매핑 검토 결과를 확인해 주세요.")
    if reviewer_role not in {"PLANNER", "REVIEWER"}:
        raise PilotLifecycleError("INVALID_REVIEWER_ROLE", "검토자 역할을 확인해 주세요.")
    exists = connection.execute(
        """SELECT 1 FROM pilot_promoted_records WHERE context_id=?
           AND template_type='provider_organizations'
           AND json_extract(payload_json,'$.provider_org_id')=?""",
        (context_id, provider_org_id),
    ).fetchone()
    if exists is None:
        raise PilotLifecycleError("PROVIDER_NOT_FOUND", "이 데이터셋에 공급자 조직이 없습니다.")
    offered = connection.execute(
        """SELECT 1 FROM pilot_promoted_records WHERE context_id=?
           AND template_type='provider_services'
           AND json_extract(payload_json,'$.provider_org_id')=?
           AND json_extract(payload_json,'$.service_type')=?
           AND json_extract(payload_json,'$.mapping_status') IN
               ('UNMAPPED','MAPPING_SUGGESTED')""",
        (context_id, provider_org_id, service_type),
    ).fetchone()
    if offered is None:
        raise PilotLifecycleError("SERVICE_MAPPING_NOT_FOUND", "검토할 서비스 제안이 없습니다.")
    safe_note, _ = redact_pii((note or "").strip())
    now = _now()
    connection.execute(
        """INSERT INTO pilot_service_mapping_reviews(
             context_id,provider_org_id,service_type,decision,reviewer_role,note,reviewed_at
           ) VALUES (?,?,?,?,?,?,?)
           ON CONFLICT(context_id,provider_org_id,service_type) DO UPDATE SET
             decision=excluded.decision,reviewer_role=excluded.reviewer_role,
             note=excluded.note,reviewed_at=excluded.reviewed_at""",
        (
            context_id,
            provider_org_id,
            service_type,
            decision,
            reviewer_role,
            safe_note or None,
            now,
        ),
    )
    return {
        "context_id": context_id,
        "provider_org_id": provider_org_id,
        "service_type": service_type,
        "decision": decision,
        "reviewer_role": reviewer_role,
        "reviewed_at": now,
    }


def promote_batch(connection: sqlite3.Connection, batch_id: str) -> dict[str, Any]:
    batch = connection.execute(
        "SELECT batch_id,status,template_type FROM pilot_import_batches WHERE batch_id=?",
        (batch_id,),
    ).fetchone()
    if batch is None:
        raise PilotLifecycleError("BATCH_NOT_FOUND", "확정할 가져오기 batch를 찾을 수 없습니다.")
    if batch["status"] not in {"IMPORTED", "IMPORTED_WITH_ERRORS"}:
        raise PilotLifecycleError(
            "BATCH_NOT_CONFIRMED", "먼저 미리보기를 명시적으로 확정해 주세요."
        )
    context_ids = [
        str(row[0])
        for row in connection.execute(
            "SELECT context_id FROM pilot_context_batches WHERE batch_id=? ORDER BY context_id",
            (batch_id,),
        )
    ]
    promoted_counts: dict[str, int] = {}
    for context_id in context_ids:
        context = get_context(connection, context_id)
        if context is None:
            raise PilotLifecycleError("CONTEXT_NOT_FOUND", "연결된 파일럿 데이터셋이 없습니다.")
        template_type = str(batch["template_type"])
        row_values = connection.execute(
            """SELECT ir.record_id,ir.row_fingerprint,ir.source_type,ir.provenance,
                      ir.normalized_json,ir.row_number
               FROM pilot_import_rows r JOIN pilot_import_records ir
                 ON ir.record_id=r.imported_record_id
               WHERE r.batch_id=? AND r.status IN ('VALID','WARNING')
               ORDER BY r.row_number""",
            (batch_id,),
        ).fetchall()
        inserted = 0
        for row in row_values:
            payload = json.loads(row["normalized_json"])
            _validate_promotion_target(connection, context, template_type, payload)
            before = connection.total_changes
            connection.execute(
                """INSERT OR IGNORE INTO pilot_promoted_records(
                     promoted_id,context_id,record_id,batch_id,template_type,domain_type,row_fingerprint,
                     source_type,provenance,payload_json,promoted_at
                   ) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    f"promoted-{uuid4().hex}",
                    context_id,
                    row["record_id"],
                    batch_id,
                    template_type,
                    DOMAIN_TYPES.get(template_type, "PilotRecord"),
                    row["row_fingerprint"],
                    row["source_type"],
                    str(payload.get("provenance") or row["provenance"]),
                    json.dumps(payload, ensure_ascii=False, sort_keys=True),
                    _now(),
                ),
            )
            inserted += int(connection.total_changes > before)
            if connection.total_changes > before:
                from backend.governance import record_audit_event

                record_audit_event(
                    connection,
                    event_type="IMPORT_ROW_APPROVED",
                    subject_type="pilot_record",
                    subject_id=str(row["record_id"]),
                    actor_role="PLANNER",
                    details={
                        "context_id": context_id,
                        "batch_id": batch_id,
                        "domain_type": DOMAIN_TYPES.get(template_type, "PilotRecord"),
                        "row_fingerprint": str(row["row_fingerprint"]),
                        "source_type": str(row["source_type"]),
                        "provenance": str(payload.get("provenance") or row["provenance"]),
                    },
                )
        if template_type == "service_execution_logs":
            _promote_execution_logs(connection, context_id, batch_id, row_values)
        promoted_counts[context_id] = inserted
    return {
        "batch_id": batch_id,
        "template_type": str(batch["template_type"]),
        "contexts": [
            {"context_id": context_id, "promoted_records": count}
            for context_id, count in sorted(promoted_counts.items())
        ],
        "idempotent": all(count == 0 for count in promoted_counts.values()),
    }


def _validate_promotion_target(
    connection: sqlite3.Connection,
    context: dict[str, Any],
    template_type: str,
    payload: dict[str, Any],
) -> None:
    context_id = str(context["context_id"])
    if template_type == "provider_organizations" and payload.get("provenance") == "REAL_DIRECTORY":
        directory_entry = connection.execute(
            """SELECT 1 FROM provider_directory_entries
               WHERE source_id=? AND source_record_id=? AND name=?
                 AND existence_provenance='REAL_DIRECTORY' LIMIT 1""",
            (
                str(payload.get("source_id", "")),
                str(payload.get("source_record_id", "")),
                str(payload.get("official_name", "")),
            ),
        ).fetchone()
        if directory_entry is None:
            raise PilotLifecycleError(
                "PROVIDER_DIRECTORY_UNVERIFIED",
                "공식 디렉터리 출처·레코드와 일치하는 조직을 찾을 수 없습니다.",
            )
    if template_type in {"demand_observations", "surveys"}:
        known = connection.execute(
            """SELECT 1 FROM pilot_promoted_records WHERE context_id=?
               AND template_type='region_areas'
               AND json_extract(payload_json,'$.area_code')=? LIMIT 1""",
            (context_id, str(payload.get("area_code", ""))),
        ).fetchone()
        if known is None:
            raise PilotLifecycleError(
                "AREA_MAPPING_INVALID", "수요·조사 행의 법정동 코드가 이 데이터셋에 없습니다."
            )
    if template_type in {
        "provider_services",
        "provider_availability",
        "provider_capacity",
        "provider_prices",
        "provider_participation",
    }:
        organization = connection.execute(
            """SELECT 1 FROM pilot_promoted_records WHERE context_id=?
               AND template_type='provider_organizations'
               AND json_extract(payload_json,'$.provider_org_id')=? LIMIT 1""",
            (context_id, str(payload.get("provider_org_id", ""))),
        ).fetchone()
        if organization is None:
            raise PilotLifecycleError(
                "PROVIDER_MAPPING_INVALID", "공급자 조직을 이 데이터셋에서 찾을 수 없습니다."
            )


def _promote_execution_logs(
    connection: sqlite3.Connection,
    context_id: str,
    batch_id: str,
    rows: list[sqlite3.Row],
) -> None:
    for row in rows:
        payload = json.loads(
            connection.execute(
                "SELECT normalized_json FROM pilot_import_records WHERE record_id=?",
                (row["record_id"],),
            ).fetchone()[0]
        )
        plan = connection.execute(
            """SELECT * FROM pilot_plans WHERE plan_id=? AND context_id=?
               AND approval_status='APPROVED'""",
            (str(payload.get("plan_id", "")), context_id),
        ).fetchone()
        if plan is None:
            raise PilotLifecycleError(
                "APPROVED_PLAN_REQUIRED",
                "수행로그는 같은 데이터셋의 승인된 계획에 연결해야 합니다.",
            )
        if payload.get("plan_version") and int(payload["plan_version"]) != int(
            plan["plan_version"]
        ):
            raise PilotLifecycleError("PLAN_VERSION_MISMATCH", "계획 버전이 일치하지 않습니다.")
        provider_id = f"pilot:{context_id}:{payload['provider_org_id']}"
        matching_rounds = [
            item
            for item in json.loads(plan["plan_json"]).get("rounds", [])
            if str(item.get("provider_id")) == provider_id
            and str(item.get("area_code") or item.get("area_id")) == str(payload["area_code"])
            and str(item.get("service_type")) == str(payload["service_type"])
            and str(item.get("scheduled_date")) == str(payload["scheduled_date"])
        ]
        if payload.get("round_id"):
            matching_rounds = [
                item for item in matching_rounds if str(item.get("round_id")) == payload["round_id"]
            ]
        if len(matching_rounds) != 1:
            raise PilotLifecycleError(
                "EXECUTION_ROUND_UNMATCHED", "계획에서 수행 회차를 하나로 연결할 수 없습니다."
            )
        round_item = matching_rounds[0]
        actual_status = str(payload["execution_status"])
        completion = payload.get("completion_percent")
        if completion in {None, ""}:
            completion = (
                100
                if actual_status == "COMPLETED"
                else 0
                if actual_status in {"CANCELLED", "NO_SHOW", "PROVIDER_CANCELLED"}
                else None
            )
        connection.execute(
            """INSERT OR IGNORE INTO pilot_execution_logs(
                 execution_id,context_id,plan_id,plan_version,round_id,provider_id,area_code,
                 service_type,scheduled_date,actual_date,status,actual_duration_minutes,
                 actual_cost_won,completion_percent,cancel_reason,source_type,batch_id,
                 row_fingerprint,recorded_at
               ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                f"execution-{uuid4().hex}",
                context_id,
                str(plan["plan_id"]),
                int(plan["plan_version"]),
                str(round_item.get("round_id") or payload.get("round_id") or ""),
                provider_id,
                str(payload["area_code"]),
                str(payload["service_type"]),
                str(payload["scheduled_date"]),
                payload.get("actual_date") or payload.get("executed_date") or None,
                actual_status,
                int(payload["actual_duration_minutes"])
                if payload.get("actual_duration_minutes")
                else None,
                int(payload["actual_cost_won"]) if payload.get("actual_cost_won") else None,
                int(completion) if completion not in {None, ""} else None,
                payload.get("cancel_reason") or None,
                "SERVICE_EXECUTION_LOG",
                batch_id,
                str(row["row_fingerprint"]),
                _now(),
            ),
        )


def _group_key(payload: dict[str, Any], fields: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(str(payload.get(field, "")) for field in fields)


def _latest_records(records: list[dict[str, Any]], fields: tuple[str, ...]) -> list[dict[str, Any]]:
    latest: dict[tuple[str, ...], dict[str, Any]] = {}
    for record in records:
        latest[_group_key(record["payload"], fields)] = record
    return list(latest.values())


def _assumption_value(assumptions: dict[str, dict[str, Any]], key: str) -> Any:
    return assumptions.get(key, {}).get("value")


def _planning_inputs(
    connection: sqlite3.Connection, context_id: str
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    context = get_context(connection, context_id)
    if context is None:
        raise PilotLifecycleError("CONTEXT_NOT_FOUND", "파일럿 데이터셋을 찾을 수 없습니다.")
    records = context_records(connection, context_id)
    by_type = {
        template: [item for item in records if item["template_type"] == template]
        for template in DOMAIN_TYPES
    }
    if context["data_mode"] == "PILOT":
        for template, items in by_type.items():
            by_type[template] = [item for item in items if item["source_type"] != "SIMULATED"]
    areas_by_code = {
        str(item["payload"]["area_code"]): item
        for item in _latest_records(by_type["region_areas"], ("area_code",))
    }
    if not areas_by_code:
        raise PilotLifecycleError("REGION_DATA_MISSING", "확정된 지역 자료가 없습니다.")

    today = korea_today()
    lookback = today - timedelta(days=180)
    planning_cutoff = today - timedelta(days=30)
    demand_groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    survey_groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    stale_survey_count = 0
    for item in by_type["demand_observations"]:
        payload = item["payload"]
        try:
            observed = date.fromisoformat(str(payload["observed_date"]))
        except (KeyError, ValueError):
            continue
        if observed < lookback or observed > today:
            continue
        key = (str(payload["area_code"]), str(payload["service_type"]))
        demand_groups.setdefault(key, []).append({**item, "observed_on": observed})
    for item in by_type["surveys"]:
        payload = item["payload"]
        try:
            surveyed = date.fromisoformat(str(payload["survey_date"]))
        except (KeyError, ValueError):
            continue
        if surveyed < lookback:
            stale_survey_count += 1
            continue
        if surveyed > today:
            continue
        key = (str(payload["area_code"]), str(payload["service_type"]))
        survey_groups.setdefault(key, []).append({**item, "observed_on": surveyed})

    used_services = {service for _area, service in demand_groups if service in DOMAIN_SERVICE_TYPES}
    if not used_services:
        raise PilotLifecycleError("DATA_INSUFFICIENT", "최근 180일 안의 수요 관측 자료가 없습니다.")
    assumptions = latest_assumptions(connection, context_id)
    durations = _assumption_value(assumptions, "service_duration_minutes") or {}
    areas: list[dict[str, Any]] = []
    demand_snapshot_records: list[dict[str, Any]] = []
    missing_demand: list[str] = []
    evidence_warnings: list[dict[str, Any]] = []
    for area_code, imported_area in sorted(areas_by_code.items()):
        for service_type in sorted(used_services):
            demands = demand_groups.get((area_code, service_type), [])
            surveys = survey_groups.get((area_code, service_type), [])
            recent = [item for item in demands if item["observed_on"] >= planning_cutoff]
            if not demands and not surveys:
                continue
            if not recent:
                evidence_warnings.append(
                    {
                        "area_code": area_code,
                        "service_type": service_type,
                        "warning": "NO_RECENT_REQUEST_COUNT",
                    }
                )
                continue
            source_types = {str(item["source_type"]) for item in demands + surveys}
            latest_date = max([item["observed_on"] for item in demands + surveys], default=None)
            assessment = assess_evidence(
                observation_count=len(demands) + len(surveys),
                survey_count=len(surveys),
                source_diversity=len(source_types),
                missingness=0.0,
                fresh_evidence_count=sum(
                    (today - item["observed_on"]).days <= 90 for item in demands + surveys
                ),
                aging_evidence_count=sum(
                    90 < (today - item["observed_on"]).days <= 180 for item in demands + surveys
                ),
                stale_evidence_count=0,
                latest_observation_date=latest_date,
                today=today,
            ).model_dump(mode="json")
            if assessment["status"] == "조사 필요":
                missing_demand.append(f"{area_code}:{service_type}")
                continue
            if (
                not source_types.intersection(
                    {"LOCAL_AUTHORITY_INPUT", "SURVEY_INPUT", "PUBLIC_DATA"}
                )
                and context["data_mode"] != "SYNTHETIC_REHEARSAL"
            ):
                missing_demand.append(f"{area_code}:{service_type}:UNVERIFIED_SOURCE")
                continue
            demand_units = sum(int(item["payload"].get("observed_count") or 0) for item in recent)
            if demand_units <= 0:
                missing_demand.append(f"{area_code}:{service_type}:NO_REQUEST_COUNT")
                continue
            if service_type not in durations:
                raise PilotLifecycleError(
                    "SERVICE_DURATION_UNKNOWN",
                    f"{service_type} 서비스 소요시간은 확인된 값 또는 명시적 가정이 필요합니다.",
                )
            source_date = str(imported_area["payload"].get("source_date", ""))
            area_payload = imported_area["payload"]
            area_id = area_code if len(used_services) == 1 else f"{area_code}:{service_type}"
            area = {
                "id": area_id,
                "area_code": area_code,
                "region_id": f"pilot:{context_id}",
                "name": str(area_payload["area_name"]),
                "anchor_lat": float(area_payload["latitude"]),
                "anchor_lng": float(area_payload["longitude"]),
                "population_total": int(area_payload["population_total"]),
                "population_65_plus": int(area_payload["population_65_plus"]),
                "elderly_ratio_65": (
                    int(area_payload["population_65_plus"])
                    / max(1, int(area_payload["population_total"]))
                ),
                "service_type": service_type,
                "simulated_monthly_demand": demand_units,
                "service_duration_minutes": int(durations[service_type]),
                "demand_confidence": assessment["status"],
                "needs_survey": assessment["status"] != "충분",
                "demand_evidence": {
                    "observation_count_180d": len(demands),
                    "survey_count_180d": len(surveys),
                    "planning_count_30d": demand_units,
                    "source_types": sorted(source_types),
                    "latest_date": latest_date.isoformat() if latest_date else None,
                    "assessment": assessment,
                },
                "source_date": source_date,
                "provenance": sorted(
                    {str(item["provenance"]) for item in [imported_area, *demands, *surveys]}
                ),
            }
            areas.append(area)
            demand_snapshot_records.extend([*demands, *surveys])
            if area["needs_survey"]:
                evidence_warnings.append(
                    {
                        "area_code": area_code,
                        "service_type": service_type,
                        "warning": "LIMITED_EVIDENCE",
                    }
                )
    represented_areas = {str(item["area_code"]) for item in areas}
    missing_demand.extend(
        f"{area_code}:NO_DEMAND_EVIDENCE"
        for area_code in sorted(set(areas_by_code) - represented_areas)
    )
    if missing_demand:
        raise PilotLifecycleError(
            "DATA_INSUFFICIENT",
            "수요 근거가 낮은 데이터 gate를 통과하지 못했습니다: " + ", ".join(missing_demand[:8]),
        )
    if not areas:
        raise PilotLifecycleError("DATA_INSUFFICIENT", "계획에 사용할 최근 관측 수요가 없습니다.")

    mapping_rows = {
        (str(row["provider_org_id"]), str(row["service_type"])): str(row["decision"])
        for row in connection.execute(
            "SELECT * FROM pilot_service_mapping_reviews WHERE context_id=?", (context_id,)
        )
    }
    organizations = {
        str(item["payload"]["provider_org_id"]): item
        for item in _latest_records(by_type["provider_organizations"], ("provider_org_id",))
    }
    service_rows = _latest_records(
        by_type["provider_services"], ("provider_org_id", "service_type")
    )
    availability_rows = by_type["provider_availability"]
    capacity_rows = by_type["provider_capacity"]
    price_rows = _latest_records(by_type["provider_prices"], ("provider_org_id", "service_type"))
    base_locations = _assumption_value(assumptions, "provider_base_locations") or {}
    assumed_prices = _assumption_value(assumptions, "service_prices_won") or {}
    providers: list[dict[str, Any]] = []
    unknown_prices: list[dict[str, str]] = []
    for provider_org_id, organization in organizations.items():
        if context["data_mode"] == "PILOT" and (
            organization["source_type"]
            not in {"OFFICIAL_DIRECTORY", "PUBLIC_DATA", "LOCAL_AUTHORITY_INPUT"}
            or organization["provenance"] == "SIMULATED"
        ):
            continue
        base_area_id = str(base_locations.get(provider_org_id, ""))
        if not base_area_id:
            continue
        capacity_by_service: dict[str, list[int]] = {}
        for item in capacity_rows:
            payload = item["payload"]
            if str(payload.get("provider_org_id")) != provider_org_id:
                continue
            if str(payload.get("capacity_unit", "")).strip() not in {"회", "방문", "건"}:
                continue
            try:
                starts = date.fromisoformat(str(payload["period_start"]))
                ends = date.fromisoformat(str(payload["period_end"]))
                count = int(payload["capacity_count"])
            except (KeyError, ValueError, TypeError):
                continue
            if starts <= today + timedelta(days=28) and ends >= today:
                capacity_by_service.setdefault(str(payload["service_type"]), []).append(count)
        operational_availability: list[dict[str, str]] = []
        max_daily_hours = 0.0
        for item in availability_rows:
            payload = item["payload"]
            if str(payload.get("provider_org_id")) != provider_org_id or str(
                payload.get("available")
            ).lower() not in {"true", "1", "yes"}:
                continue
            try:
                available_day = date.fromisoformat(str(payload["available_date"]))
                start_time = str(payload["start_time"])
                end_time = str(payload["end_time"])
                start_hour, start_minute = (int(part) for part in start_time.split(":"))
                end_hour, end_minute = (int(part) for part in end_time.split(":"))
                minutes = (end_hour * 60 + end_minute) - (start_hour * 60 + start_minute)
            except (KeyError, ValueError, TypeError):
                continue
            if not today < available_day <= today + timedelta(days=28) or minutes <= 0:
                continue
            max_daily_hours = max(max_daily_hours, minutes / 60)
            operational_availability.append(
                {
                    "available_date": available_day.isoformat(),
                    "service_type": str(payload["service_type"]),
                    "start_time": start_time,
                    "end_time": end_time,
                }
            )
        offered: list[str] = []
        service_prices: dict[str, int] = {}
        service_price_sources: dict[str, str] = {}
        for item in service_rows:
            payload = item["payload"]
            service_type = str(payload.get("service_type", ""))
            if (
                str(payload.get("provider_org_id")) != provider_org_id
                or service_type not in used_services
            ):
                continue
            if payload.get("mapping_status") == "REJECTED_MAPPING":
                continue
            if mapping_rows.get((provider_org_id, service_type)) != "VERIFIED_MAPPING":
                continue
            raw_price = next(
                (
                    row["payload"].get("price_won")
                    for row in reversed(price_rows)
                    if str(row["payload"].get("provider_org_id")) == provider_org_id
                    and str(row["payload"].get("service_type")) == service_type
                    and row["payload"].get("price_won") not in {None, ""}
                    and str(row["payload"].get("price_basis", "")).strip()
                    in {"회당", "건당", "1회", "방문 1회"}
                ),
                None,
            )
            price_source = "PROVIDER_PRICE_IMPORT"
            if raw_price is None:
                raw_price = assumed_prices.get(provider_org_id, {}).get(service_type)
                price_source = assumptions.get("service_prices_won", {}).get(
                    "provenance", "UNKNOWN"
                )
            if raw_price is None:
                unknown_prices.append(
                    {"provider_org_id": provider_org_id, "service_type": service_type}
                )
                continue
            if service_type not in capacity_by_service or not capacity_by_service[service_type]:
                continue
            if not any(slot["service_type"] == service_type for slot in operational_availability):
                continue
            offered.append(service_type)
            service_prices[service_type] = int(raw_price)
            service_price_sources[service_type] = price_source
        if not offered or max_daily_hours <= 0:
            continue
        capacities = [
            min(values)
            for service, values in capacity_by_service.items()
            if service in offered and values
        ]
        if not capacities:
            continue
        max_monthly_rounds = min(capacities)
        internal_provider_id = f"pilot:{context_id}:{provider_org_id}"
        providers.append(
            {
                "id": internal_provider_id,
                "provider_id": internal_provider_id,
                "provider_org_id": provider_org_id,
                "name": str(organization["payload"]["official_name"]),
                "base_location": base_area_id,
                "base_area_id": base_area_id,
                "base_lat": 0.0,
                "base_lng": 0.0,
                "max_daily_hours": max_daily_hours,
                "max_monthly_rounds": max(0, max_monthly_rounds),
                "capacity_per_month": max(0, max_monthly_rounds),
                "service_capacity": 1,
                "max_travel_time_minutes": 360,
                "minimum_compensation_won": 0,
                "supported_services": sorted(set(offered)),
                "service_prices": service_prices,
                "service_price_sources": service_price_sources,
                "availability": [],
                "date_availability": operational_availability,
                "date_availability_exclusive": True,
                "participation_preferences": [],
                "provenance": organization["provenance"],
            }
        )
    if not providers:
        if unknown_prices:
            raise PilotLifecycleError(
                "COST_UNKNOWN",
                "공급자 단가가 없어 optimizer 입력을 만들 수 없습니다. "
                "실제 가격 또는 별도 가정을 기록해 주세요.",
            )
        raise PilotLifecycleError(
            "NO_VERIFIED_PROVIDER",
            "검증된 서비스 mapping과 availability·capacity를 가진 공급자가 없습니다.",
        )
    if stale_survey_count:
        evidence_warnings.append({"warning": "STALE_SURVEYS_EXCLUDED", "count": stale_survey_count})
    if unknown_prices:
        evidence_warnings.append(
            {"warning": "UNKNOWN_PROVIDER_PRICES", "providers": unknown_prices}
        )
    return (
        context,
        areas,
        providers,
        {
            "records": records,
            "by_type": by_type,
            "assumptions": assumptions,
            "areas_by_code": areas_by_code,
            "demand_records": demand_snapshot_records,
            "route_source": None,
            "evidence_warnings": evidence_warnings,
            "unknown_prices": unknown_prices,
        },
    )


DOMAIN_SERVICE_TYPES = frozenset({"laundry", "daily_necessities", "home_repair"})


def _snapshot_id(records: list[dict[str, Any]], prefix: str) -> str:
    fingerprints = sorted(str(item["row_fingerprint"]) for item in records)
    digest = hashlib.sha256("\n".join(fingerprints).encode()).hexdigest()
    return f"{prefix}-{digest[:24]}"


def _build_route_connection(
    areas: list[dict[str, Any]], providers: list[dict[str, Any]], meta: dict[str, Any]
) -> tuple[sqlite3.Connection, str, dict[str, Any]]:
    assumptions = meta["assumptions"]
    route_assumption = assumptions.get("route_matrix")
    explicit_routes = {
        (str(item["origin_id"]), str(item["destination_id"])): (
            int(item["distance_m"]),
            int(item["duration_s"]),
        )
        for item in (route_assumption or {}).get("value", [])
    }
    route_source = str((route_assumption or {}).get("provenance", ""))
    nodes = {str(item["id"]) for item in areas}
    nodes.update(str(item["base_area_id"]) for item in providers)
    physical_by_node = {str(item["id"]): str(item["area_code"]) for item in areas}
    physical_by_node.update(
        {str(item["base_area_id"]): str(item["base_area_id"]) for item in providers}
    )
    by_code = {str(item["area_code"]): item for item in areas}
    context_ids = {
        node: by_code[code] for node, code in physical_by_node.items() if code in by_code
    }
    cache_connection = connect_travel_cache()
    result = sqlite3.connect(":memory:")
    result.execute(
        """CREATE TABLE travel_matrix(
             origin_id TEXT,destination_id TEXT,distance_m INTEGER,duration_s INTEGER
           )"""
    )
    sources: set[str] = set()
    cache_fetch_times: list[str] = []
    missing: list[tuple[str, str]] = []
    try:
        for origin in sorted(nodes):
            for destination in sorted(nodes):
                if origin == destination:
                    distance_s = (0, 0)
                    source = "IDENTITY"
                else:
                    distance_s = explicit_routes.get((origin, destination))
                    if distance_s is None:
                        physical_origin = physical_by_node.get(origin, origin)
                        physical_destination = physical_by_node.get(destination, destination)
                        distance_s = explicit_routes.get((physical_origin, physical_destination))
                    source = route_source if distance_s is not None else ""
                    if distance_s is None and origin in context_ids and destination in context_ids:
                        cache_origin = {
                            **context_ids[origin],
                            "id": physical_by_node[origin],
                        }
                        cache_destination = {
                            **context_ids[destination],
                            "id": physical_by_node[destination],
                        }
                        cached = get_cached(cache_connection, cache_origin, cache_destination)
                        if cached is not None:
                            distance_s = (cached.distance_m, cached.duration_s)
                            source = "KAKAO_MOBILITY_CACHE"
                            cached_row = cache_connection.execute(
                                "SELECT fetched_at FROM travel_matrix WHERE cache_key=?",
                                (cache_key(cache_origin, cache_destination),),
                            ).fetchone()
                            if cached_row and cached_row[0]:
                                cache_fetch_times.append(str(cached_row[0]))
                    if distance_s is None:
                        missing.append((origin, destination))
                        continue
                result.execute(
                    "INSERT INTO travel_matrix VALUES (?,?,?,?)",
                    (origin, destination, int(distance_s[0]), int(distance_s[1])),
                )
                sources.add(source)
        if missing:
            raise PilotLifecycleError(
                "ROUTE_MATRIX_UNAVAILABLE",
                "명시된 도로 구간이 없어 계획을 만들 수 없습니다 "
                f"({len(missing)} directed legs missing). 직선거리 대체는 하지 않았습니다.",
            )
        result.commit()
    except Exception:
        result.close()
        raise
    finally:
        cache_connection.close()
    label = "+".join(sorted(sources - {"IDENTITY"})) or "NO_ROUTES"
    route_cache_provenance = {
        "cached_directed_leg_count": len(cache_fetch_times),
        "last_successful_fetch": max(cache_fetch_times, default=None),
        "cache_fetched_date": max(
            (value[:10] for value in cache_fetch_times), default=None
        ),
        "source_snapshot_date": None,
        "cache_reason": (
            "Exact route cache key matched provider/area coordinates and routing version."
            if cache_fetch_times
            else None
        ),
    }
    return result, label, route_cache_provenance


def _plan_detail(connection: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
    result = dict(row)
    plan_json = json.loads(result.pop("plan_json"))
    snapshot = json.loads(result.pop("data_snapshot_json"))
    result["plan"] = plan_json
    result["data_snapshot"] = snapshot
    result["data_mode"] = snapshot["data_mode"]
    result["pilot_context_id"] = result["context_id"]
    result["post_plan_metrics"] = execution_metrics(connection, str(result["plan_id"]))
    return result


def create_pilot_plan(
    connection: sqlite3.Connection,
    *,
    context_id: str,
    scenario: str,
    budget_won: int,
    parent_plan_id: str | None = None,
    change_reason: str | None = None,
    excluded_provider_services: set[tuple[str, str]] | None = None,
) -> dict[str, Any]:
    if scenario not in {"efficiency", "balanced", "underserved_first", "minimum_coverage"}:
        raise PilotLifecycleError("INVALID_SCENARIO", "지원하지 않는 최적화 시나리오입니다.")
    if budget_won < 0:
        raise PilotLifecycleError("INVALID_BUDGET", "예산은 0 이상이어야 합니다.")
    context, areas, providers, meta = _planning_inputs(connection, context_id)
    route_connection, route_source, route_cache_provenance = _build_route_connection(
        areas, providers, meta
    )
    plan_id = f"pilot-plan-{uuid4().hex}"
    try:
        excluded_slots: set[tuple[str, str, str, str]] = set()
        if excluded_provider_services:
            for provider in providers:
                if (str(provider["provider_org_id"]), "*") in excluded_provider_services:
                    for area in areas:
                        if str(area["service_type"]) in provider["supported_services"]:
                            for offset in range(1, 29):
                                excluded_slots.add(
                                    (
                                        str(provider["provider_id"]),
                                        str(area["id"]),
                                        str(area["service_type"]),
                                        (korea_today() + timedelta(days=offset)).isoformat(),
                                    )
                                )
                else:
                    declined = {
                        service
                        for provider_id, service in excluded_provider_services
                        if provider_id == str(provider["provider_org_id"])
                    }
                    for area in areas:
                        if (
                            str(area["service_type"]) in declined
                            and str(area["service_type"]) in provider["supported_services"]
                        ):
                            for offset in range(1, 29):
                                excluded_slots.add(
                                    (
                                        str(provider["provider_id"]),
                                        str(area["id"]),
                                        str(area["service_type"]),
                                        (korea_today() + timedelta(days=offset)).isoformat(),
                                    )
                                )
        schedule = generate_provider_schedule(
            areas,
            providers,
            route_connection,
            budget_won,
            scenario,
            PlanningPolicy(),
            excluded_provider_slots=excluded_slots,
            route_strategy="decomposed",
            planning_strategy="baseline",
            include_profile=True,
        )
    except ValueError as exc:
        if isinstance(exc, PilotLifecycleError):
            raise
        raise PilotLifecycleError(
            "PILOT_OPTIMIZATION_FAILED", "파일럿 입력으로 일정을 계산하지 못했습니다."
        ) from None
    finally:
        route_connection.close()

    provider_org_by_id = {
        str(item["provider_id"]): str(item["provider_org_id"]) for item in providers
    }
    area_by_id = {str(item["id"]): item for item in areas}
    for index, round_item in enumerate(schedule.get("rounds", []), start=1):
        round_item["round_id"] = f"{plan_id}-round-{index:04d}"
        round_item["provider_org_id"] = provider_org_by_id.get(str(round_item["provider_id"]))
        round_item["area_code"] = area_by_id[str(round_item["area_id"])]["area_code"]
    served_codes = {
        str(item["area_code"])
        for item in schedule.get("rounds", [])
        if int(item.get("service_units", 0)) > 0
    }
    all_area_codes = sorted({str(item["area_code"]) for item in areas})
    schedule["planned_coverage"] = {
        "label": "PLANNED_COVERAGE",
        "area_count": len(all_area_codes),
        "served_area_count": len(served_codes),
        "zero_service_area_count": len(set(all_area_codes) - served_codes),
        "served_area_codes": sorted(served_codes),
        "zero_service_area_codes": sorted(set(all_area_codes) - served_codes),
        "reduced_exclusion_count": int(schedule.get("reduced_exclusion_count", 0)),
    }
    schedule["optimizer_version"] = "V5.1_BASELINE_DECOMPOSED"
    schedule["data_mode"] = str(context["data_mode"])
    schedule["pilot_context_id"] = context_id
    schedule["route_source"] = route_source
    schedule["route_cache_provenance"] = route_cache_provenance
    schedule["provider_cost_sources"] = {
        str(provider["provider_org_id"]): provider["service_price_sources"]
        for provider in providers
    }
    schedule["provider_inputs"] = [
        {
            "provider_org_id": provider["provider_org_id"],
            "provider_id": provider["provider_id"],
            "provider_name": provider["name"],
            "supported_services": provider["supported_services"],
            "capacity_per_month": provider["max_monthly_rounds"],
            "availability_source": "CONFIRMED_PILOT_IMPORT",
            "price_sources": provider["service_price_sources"],
            "provenance": provider["provenance"],
        }
        for provider in providers
    ]
    schedule["demand_inputs"] = [
        {
            "area_code": area["area_code"],
            "service_type": area["service_type"],
            "observed_request_count_30d": area["simulated_monthly_demand"],
            "assessment": area["demand_confidence"],
            "source_types": area["demand_evidence"]["source_types"],
        }
        for area in areas
    ]
    schedule["evidence_warnings"] = meta["evidence_warnings"]

    parent = None
    if parent_plan_id:
        parent = connection.execute(
            "SELECT * FROM pilot_plans WHERE plan_id=? AND context_id=?",
            (parent_plan_id, context_id),
        ).fetchone()
        if parent is None:
            raise PilotLifecycleError(
                "PARENT_PLAN_NOT_FOUND", "같은 데이터셋의 상위 계획이 없습니다."
            )
        if parent["approval_status"] in {"UNDER_REVIEW", "SUPERSEDED"}:
            raise PilotLifecycleError(
                "PARENT_PLAN_LOCKED", "검토 중이거나 대체된 계획은 바로 수정할 수 없습니다."
            )
        if parent["approval_status"] in {"CHANGES_REQUESTED", "APPROVED"} and not change_reason:
            raise PilotLifecycleError("CHANGE_REASON_REQUIRED", "수정 요청 사유를 확인해 주세요.")
    connection.execute("BEGIN IMMEDIATE")
    if parent is None:
        lineage_root_id = plan_id
        version = 1
    else:
        lineage_root_id = str(parent["lineage_root_id"])
        version = int(
            connection.execute(
                "SELECT COALESCE(MAX(plan_version),0)+1 FROM pilot_plans WHERE lineage_root_id=?",
                (lineage_root_id,),
            ).fetchone()[0]
        )

    snapshot = context_snapshot(connection, context_id)
    region_records = meta["by_type"]["region_areas"]
    provider_records = [
        item for item in meta["records"] if item["template_type"].startswith("provider_")
    ]
    snapshot_payload = {
        "data_mode": str(context["data_mode"]),
        "pilot_context_id": context_id,
        "pilot_context_snapshot_id": snapshot["snapshot_id"],
        "region_snapshot_id": _snapshot_id(region_records, "region-snapshot"),
        "demand_snapshot_id": _snapshot_id(meta["demand_records"], "demand-snapshot"),
        "provider_snapshot_id": _snapshot_id(provider_records, "provider-snapshot"),
        "import_batch_ids": snapshot["import_batch_ids"],
        "source_snapshot_date": max(
            (
                str(item["payload"].get(field) or "")
                for item in meta["records"]
                for field in (
                    "source_date",
                    "survey_date",
                    "source_snapshot",
                    "effective_date",
                )
                if item["payload"].get(field)
            ),
            default=None,
        ),
        "provenance_records": [
            {
                "template_type": item["template_type"],
                "record_id": item["record_id"],
                "batch_id": item["batch_id"],
                "row_fingerprint": item["row_fingerprint"],
                "source_type": item["source_type"],
                "provenance": item["provenance"],
                "source_id": item["payload"].get("source_id"),
                "source_record_id": item["payload"].get("source_record_id"),
                "source_date": item["payload"].get("source_date")
                or item["payload"].get("source_snapshot")
                or item["payload"].get("survey_date")
                or item["payload"].get("effective_date"),
                "area_code": item["payload"].get("area_code"),
                "provider_org_id": item["payload"].get("provider_org_id"),
                "service_type": item["payload"].get("service_type"),
            }
            for item in meta["records"]
        ],
        "route_matrix_fingerprint": schedule.get("route_matrix_fingerprint"),
        "route_source": route_source,
        "route_cache_provenance": route_cache_provenance,
        "scenario_assumptions": snapshot["assumptions"],
        "active_scenario_assumptions": latest_assumptions(connection, context_id),
        "provider_service_mapping_reviews": snapshot["mapping_reviews"],
        "resident_feedback": snapshot["resident_feedback"],
        "resident_feedback_unresolved_conflict_count": sum(
            int(item["unresolved_conflict_count"])
            for item in snapshot["resident_feedback"]
        ),
        "optimizer_version": schedule["optimizer_version"],
        "source_provenance": sorted({str(item["provenance"]) for item in meta["records"]}),
        "data_freshness_warnings": meta["evidence_warnings"],
    }
    has_explicit_assumptions = bool(snapshot["assumptions"])
    provenance = (
        "SYNTHETIC FIELD-PILOT REHEARSAL; SIMULATED INPUTS"
        if context["data_mode"] == "SYNTHETIC_REHEARSAL"
        else "PILOT DATA WITH EXPLICIT SCENARIO ASSUMPTIONS; NOT FIELD EXECUTION"
        if has_explicit_assumptions
        else "PILOT DATA; SOURCE ATTRIBUTION STORED PER IMPORT RECORD"
    )
    schedule["provenance"] = provenance
    schedule["plan_id"] = plan_id
    schedule["plan_version"] = version
    schedule["approval_status"] = "DRAFT"
    connection.execute(
        """INSERT INTO pilot_plans(
             plan_id,context_id,scenario_key,budget_won,plan_version,lineage_root_id,
             parent_plan_id,change_reason,plan_json,data_snapshot_json,provenance,
             approval_status,created_at
           ) VALUES (?,?,?,?,?,?,?,?,?,?,?,'DRAFT',?)""",
        (
            plan_id,
            context_id,
            scenario,
            budget_won,
            version,
            lineage_root_id,
            parent_plan_id,
            change_reason,
            json.dumps(schedule, ensure_ascii=False, sort_keys=True),
            json.dumps(snapshot_payload, ensure_ascii=False, sort_keys=True),
            provenance,
            _now(),
        ),
    )
    from backend.governance import record_audit_event

    record_audit_event(
        connection,
        event_type="PLAN_GENERATED",
        subject_type="pilot_plan",
        subject_id=plan_id,
        actor_role="PLANNER",
        details={
            "pilot_context_id": context_id,
            "plan_version": version,
            "scenario": scenario,
            "solver_status": schedule.get("solver_status"),
            "route_source": route_source,
            "parent_plan_id": parent_plan_id,
        },
    )
    row = connection.execute("SELECT * FROM pilot_plans WHERE plan_id=?", (plan_id,)).fetchone()
    assert row is not None
    return _plan_detail(connection, row)


def list_pilot_plans(connection: sqlite3.Connection, context_id: str) -> list[dict[str, Any]]:
    if get_context(connection, context_id) is None:
        raise PilotLifecycleError("CONTEXT_NOT_FOUND", "파일럿 데이터셋을 찾을 수 없습니다.")
    rows = connection.execute(
        "SELECT * FROM pilot_plans WHERE context_id=? ORDER BY created_at,plan_version",
        (context_id,),
    )
    return [_plan_detail(connection, row) for row in rows]


def get_pilot_plan(connection: sqlite3.Connection, plan_id: str) -> dict[str, Any] | None:
    row = connection.execute("SELECT * FROM pilot_plans WHERE plan_id=?", (plan_id,)).fetchone()
    return _plan_detail(connection, row) if row else None


def replan_pilot_plan(
    connection: sqlite3.Connection, *, plan_id: str, change_reason: str | None = None
) -> dict[str, Any]:
    parent = connection.execute("SELECT * FROM pilot_plans WHERE plan_id=?", (plan_id,)).fetchone()
    if parent is None:
        raise PilotLifecycleError("PLAN_NOT_FOUND", "파일럿 계획을 찾을 수 없습니다.")
    if parent["approval_status"] in {"UNDER_REVIEW", "SUPERSEDED"}:
        raise PilotLifecycleError(
            "PARENT_PLAN_LOCKED", "검토 중이거나 대체된 계획은 바로 수정할 수 없습니다."
        )
    if (
        parent["approval_status"] in {"CHANGES_REQUESTED", "APPROVED"}
        and not (change_reason or "").strip()
    ):
        raise PilotLifecycleError("CHANGE_REASON_REQUIRED", "수정 요청 사유를 입력해 주세요.")
    context_id = str(parent["context_id"])
    lineage_ids = {
        str(item[0])
        for item in connection.execute(
            "SELECT plan_id FROM pilot_plans WHERE lineage_root_id=?",
            (parent["lineage_root_id"],),
        )
    }
    participation_statuses: dict[tuple[str, str], str] = {}
    for item in context_records(connection, context_id, "provider_participation"):
        payload = item["payload"]
        if str(payload.get("plan_id")) not in lineage_ids:
            continue
        key = (str(payload.get("provider_org_id", "")), str(payload.get("service_type", "")))
        participation_statuses[key] = str(payload.get("participation_status", ""))
    declines = {
        key
        for key, status in participation_statuses.items()
        if status in {"DECLINED", "UNAVAILABLE"}
    }
    safe_change_reason, _ = redact_pii((change_reason or "PROVIDER_FAILURE_OR_DECLINE").strip())
    return create_pilot_plan(
        connection,
        context_id=context_id,
        scenario=str(parent["scenario_key"]),
        budget_won=int(parent["budget_won"]),
        parent_plan_id=plan_id,
        change_reason=safe_change_reason,
        excluded_provider_services=declines,
    )


def transition_pilot_plan(
    connection: sqlite3.Connection,
    *,
    plan_id: str,
    action: str,
    role: str,
    comment: str | None = None,
) -> dict[str, Any]:
    row = connection.execute("SELECT * FROM pilot_plans WHERE plan_id=?", (plan_id,)).fetchone()
    if row is None:
        raise PilotLifecycleError("PLAN_NOT_FOUND", "파일럿 계획을 찾을 수 없습니다.")
    current = str(row["approval_status"])
    transitions = {
        ("DRAFT", "submit"): ("UNDER_REVIEW", "PLANNER"),
        ("CHANGES_REQUESTED", "submit"): ("UNDER_REVIEW", "PLANNER"),
        ("UNDER_REVIEW", "approve"): ("APPROVED", "REVIEWER"),
        ("UNDER_REVIEW", "request_changes"): ("CHANGES_REQUESTED", "REVIEWER"),
    }
    transition = transitions.get((current, action))
    if transition is None:
        raise PilotLifecycleError(
            "INVALID_APPROVAL_TRANSITION", "현재 계획 상태에서는 이 작업을 할 수 없습니다."
        )
    target, required_role = transition
    if role != required_role:
        raise PilotLifecycleError(
            "ROLE_NOT_PERMITTED", "계획 담당자 또는 검토자 역할이 필요합니다."
        )
    safe_comment, _ = redact_pii((comment or "").strip())
    if action == "request_changes" and not safe_comment:
        raise PilotLifecycleError("CHANGE_COMMENT_REQUIRED", "수정 요청 사유를 입력해 주세요.")
    now = _now()
    if action == "request_changes":
        connection.execute(
            """INSERT INTO pilot_plan_change_requests(
                 request_id,plan_id,comment,requested_by_role,requested_at
               ) VALUES (?,?,?,'REVIEWER',?)""",
            (f"pilot-change-{uuid4().hex}", plan_id, safe_comment[:500], now),
        )
    if action == "submit":
        connection.execute(
            """UPDATE pilot_plan_change_requests SET resolved_at=?
               WHERE plan_id=? AND resolved_at IS NULL""",
            (now, plan_id),
        )
    superseded: list[str] = []
    if target == "APPROVED":
        previous_rows = connection.execute(
            """SELECT plan_id FROM pilot_plans WHERE lineage_root_id=?
               AND approval_status='APPROVED' AND plan_id<>?""",
            (row["lineage_root_id"], plan_id),
        ).fetchall()
        superseded = [str(item[0]) for item in previous_rows]
        for previous_id in superseded:
            connection.execute(
                """UPDATE pilot_plans SET approval_status='SUPERSEDED',approval_updated_at=?
                   WHERE plan_id=?""",
                (now, previous_id),
            )
    connection.execute(
        """UPDATE pilot_plans SET approval_status=?,approval_updated_at=?,approved_by_role=?
           WHERE plan_id=?""",
        (target, now, "REVIEWER" if target == "APPROVED" else None, plan_id),
    )
    from backend.governance import record_audit_event

    record_audit_event(
        connection,
        event_type={
            "submit": "PLAN_SUBMITTED_FOR_REVIEW",
            "approve": "PLAN_APPROVED",
            "request_changes": "PLAN_CHANGES_REQUESTED",
        }[action],
        subject_type="pilot_plan",
        subject_id=plan_id,
        actor_role=role,
        details={"from": current, "to": target, "superseded": superseded},
    )
    return {
        "plan_id": plan_id,
        "previous_status": current,
        "approval_status": target,
        "approval_updated_at": now,
        "superseded_plan_ids": superseded,
    }


def execution_metrics(connection: sqlite3.Connection, plan_id: str) -> dict[str, Any]:
    row = connection.execute("SELECT * FROM pilot_plans WHERE plan_id=?", (plan_id,)).fetchone()
    if row is None:
        raise PilotLifecycleError("PLAN_NOT_FOUND", "파일럿 계획을 찾을 수 없습니다.")
    plan = json.loads(row["plan_json"])
    rounds = list(plan.get("rounds", []))
    logs = [
        dict(item)
        for item in connection.execute(
            """SELECT * FROM pilot_execution_logs WHERE plan_id=?
               ORDER BY scheduled_date,execution_id""",
            (plan_id,),
        )
    ]
    if not logs:
        return {
            "status": "UNKNOWN",
            "actual_served_areas": "UNKNOWN",
            "actual_zero_service_areas": "UNKNOWN",
            "completion_rate": "UNKNOWN",
            "planned_coverage": plan.get("planned_coverage", "UNKNOWN"),
            "planned_duration_minutes": sum(
                int(item.get("duration_minutes") or 0) for item in rounds
            ),
            "actual_duration_minutes": "UNKNOWN",
            "provider_decline_rate": "UNKNOWN",
            "actual_cost_won": "UNKNOWN",
            "cost_variance_won": "UNKNOWN",
            "schedule_variance_days": "UNKNOWN",
            "unmet_services": "UNKNOWN",
            "execution_log_count": 0,
        }
    planned_round_ids = {str(item.get("round_id")) for item in rounds}
    recorded_round_ids = {str(item.get("round_id")) for item in logs if item.get("round_id")}
    complete_log_coverage = bool(planned_round_ids) and planned_round_ids <= recorded_round_ids
    completed = [
        item
        for item in logs
        if item["status"] in {"COMPLETED", "PARTIALLY_COMPLETED"}
        and (item["completion_percent"] is None or int(item["completion_percent"]) > 0)
    ]
    served_codes = {str(item["area_code"]) for item in completed}
    coverage = plan.get("planned_coverage", {})
    planned_codes = set(coverage.get("served_area_codes", [])) | set(
        coverage.get("zero_service_area_codes", [])
    )
    if not planned_codes:
        planned_codes = {str(item.get("area_code") or item.get("area_id")) for item in rounds}
    completion_rate: int | str = (
        round(100 * len(completed) / len(rounds), 1)
        if complete_log_coverage and rounds
        else "UNKNOWN"
    )
    all_costs_known = all(item["actual_cost_won"] is not None for item in logs)
    actual_cost: int | str = (
        sum(int(item["actual_cost_won"]) for item in logs) if all_costs_known else "UNKNOWN"
    )
    planned_cost = int(
        plan.get("total_cost_won")
        or plan.get("budget_spent_won")
        or (plan.get("summary") or {}).get("total_cost_won")
        or 0
    )
    cost_variance: int | str = (
        int(actual_cost) - planned_cost
        if complete_log_coverage and isinstance(actual_cost, int)
        else "UNKNOWN"
    )
    date_deltas: list[int] = []
    for item in logs:
        if not item["actual_date"]:
            continue
        date_deltas.append(
            (
                date.fromisoformat(str(item["actual_date"]))
                - date.fromisoformat(str(item["scheduled_date"]))
            ).days
        )
    schedule_variance: float | str = (
        round(sum(date_deltas) / len(date_deltas), 2)
        if complete_log_coverage and date_deltas
        else "UNKNOWN"
    )
    planned_duration = sum(int(item.get("duration_minutes") or 0) for item in rounds)
    actual_duration: int | str = (
        sum(int(item["actual_duration_minutes"]) for item in logs)
        if all(item["actual_duration_minutes"] is not None for item in logs)
        else "UNKNOWN"
    )
    context_id = str(row["context_id"])
    lineage_ids = {
        str(item[0])
        for item in connection.execute(
            "SELECT plan_id FROM pilot_plans WHERE lineage_root_id=?",
            (row["lineage_root_id"],),
        )
    }
    participation = [
        item["payload"]
        for item in context_records(connection, context_id, "provider_participation")
        if str(item["payload"].get("plan_id")) in lineage_ids
    ]
    considered = [
        item
        for item in participation
        if item.get("participation_status") in {"INVITED", "OPTED_IN", "DECLINED", "UNAVAILABLE"}
    ]
    decline_rate: float | str = (
        round(
            100
            * sum(
                item["participation_status"] in {"DECLINED", "UNAVAILABLE"} for item in considered
            )
            / len(considered),
            1,
        )
        if considered
        else "UNKNOWN"
    )
    failed = sum(item["status"] in {"CANCELLED", "NO_SHOW", "PROVIDER_CANCELLED"} for item in logs)
    unmet: int | str = failed if complete_log_coverage else "UNKNOWN"
    actual_zero: int | str = (
        len(planned_codes - served_codes) if complete_log_coverage else "UNKNOWN"
    )
    return {
        "status": "COMPLETE" if complete_log_coverage else "PARTIAL",
        "actual_served_areas": len(served_codes),
        "actual_served_area_codes": sorted(served_codes),
        "actual_zero_service_areas": actual_zero,
        "planned_coverage": coverage,
        "completion_rate": completion_rate,
        "provider_decline_rate": decline_rate,
        "planned_cost_won": planned_cost,
        "actual_cost_won": actual_cost,
        "cost_variance_won": cost_variance,
        "planned_duration_minutes": planned_duration,
        "actual_duration_minutes": actual_duration,
        "schedule_variance_days": schedule_variance,
        "unmet_services": unmet,
        "execution_log_count": len(logs),
        "completed_round_count": len(completed),
        "planned_round_count": len(rounds),
    }
