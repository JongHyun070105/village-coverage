"""Resident feedback correction workflow.

Feedback is a claim, not a survey. It never mutates DemandAssessment, forecasts or plans by
itself: staff review -> evidence acceptance -> bounded claim evidence -> plan marked stale ->
planner replans. Contact data lives in a separate table and is never exported.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import sqlite3
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from backend import errors
from backend.demand import redact_pii
from backend.errors import AppError
from backend.evidence_policy import evidence_freshness
from backend.evidence_source_policy import bounded_observation_contribution
from backend.governance import record_audit_event

logger = logging.getLogger("village_coverage.resident_feedback")

FEEDBACK_AREA_DAILY_LIMIT = 30
FEEDBACK_REGION_DAILY_LIMIT = 200
EXACT_DUPLICATE_WINDOW_DAYS = 30
NEAR_DUPLICATE_WINDOW_DAYS = 30
NEAR_DUPLICATE_SIMILARITY = 0.6
FREQUENCY_CONFLICT_MIN_ABS_DIFF = 2
FREQUENCY_CONFLICT_MIN_RATIO = 1.5
REVIEW_ROLES = ("PLANNER", "REVIEWER")
STALE_REASON = "RESIDENT_EVIDENCE_ACCEPTED"

STATUS_LABELS_KO = {
    "SUBMITTED": "접수됨",
    "UNDER_REVIEW": "검토 중",
    "NEEDS_MORE_INFO": "추가 확인 필요",
    "ACCEPTED_AS_EVIDENCE": "근거로 채택(검증 전)",
    "REJECTED": "반려",
    "RESOLVED": "처리 완료",
}
# (from_status, action) -> to_status
FEEDBACK_TRANSITIONS: dict[tuple[str, str], str] = {
    ("SUBMITTED", "start_review"): "UNDER_REVIEW",
    ("SUBMITTED", "reject"): "REJECTED",
    ("UNDER_REVIEW", "request_info"): "NEEDS_MORE_INFO",
    ("UNDER_REVIEW", "accept"): "ACCEPTED_AS_EVIDENCE",
    ("UNDER_REVIEW", "reject"): "REJECTED",
    ("NEEDS_MORE_INFO", "start_review"): "UNDER_REVIEW",
    ("NEEDS_MORE_INFO", "reject"): "REJECTED",
    ("ACCEPTED_AS_EVIDENCE", "resolve"): "RESOLVED",
}
ACTION_AUDIT_EVENTS = {
    "start_review": "FEEDBACK_REVIEW_STARTED",
    "request_info": "FEEDBACK_NEEDS_MORE_INFO",
    "accept": "FEEDBACK_ACCEPTED",
    "reject": "FEEDBACK_REJECTED",
    "resolve": "FEEDBACK_RESOLVED",
}
CONFLICT_RESOLUTIONS = ("KEEP_OFFICIAL_EVIDENCE", "FURTHER_SURVEY", "ACCEPT_AS_RANGE")

_WS = re.compile(r"\s+")
_TOKEN = re.compile(r"[0-9A-Za-z가-힣]+")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _normalize(text: str) -> str:
    return _WS.sub(" ", text.strip().lower())


def content_fingerprint(
    area_id: str, service_type: str | None, feedback_type: str, description: str
) -> str:
    raw = "|".join((area_id, service_type or "", feedback_type, _normalize(description)))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _tokens(text: str) -> set[str]:
    return set(_TOKEN.findall(_normalize(text)))


def _similarity(left: str, right: str) -> float:
    a, b = _tokens(left), _tokens(right)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _days_ago_iso(days: int) -> str:
    from datetime import timedelta

    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")


def _public_row(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    item["claim"] = json.loads(item.pop("claim_json"))
    item["evidence_attachment_metadata"] = json.loads(
        item.pop("evidence_attachment_metadata_json")
    )
    item["description_was_redacted"] = bool(item["description_was_redacted"])
    item["status_label_ko"] = STATUS_LABELS_KO[item["status"]]
    item["freshness"] = evidence_freshness(str(item["submitted_at"])[:10])
    item.pop("content_fingerprint", None)
    return item


def _area(connection: sqlite3.Connection, area_id: str) -> sqlite3.Row:
    row = connection.execute(
        "SELECT area_id, region_id FROM village_service_areas WHERE area_id=?", (area_id,)
    ).fetchone()
    if row is None:
        raise AppError(
            errors.VALIDATION_ERROR, "존재하지 않는 생활권입니다.", status_code=404,
            details={"area_id": area_id},
        )
    return row


def _service(connection: sqlite3.Connection, service_type: str) -> sqlite3.Row:
    row = connection.execute(
        "SELECT service_type_id, label_ko, policy_status FROM service_types "
        "WHERE service_type_id=?",
        (service_type,),
    ).fetchone()
    if row is None:
        raise AppError(
            errors.VALIDATION_ERROR, "알 수 없는 서비스 유형입니다.", status_code=422,
            details={"service_type": service_type},
        )
    return row


def _validated_claim(raw: dict[str, Any] | None) -> dict[str, Any]:
    claim: dict[str, Any] = {}
    raw = raw or {}
    frequency = raw.get("claimed_frequency_per_month")
    if frequency is not None:
        valid = isinstance(frequency, int) and not isinstance(frequency, bool)
        if not valid or not 1 <= frequency <= 31:
            raise AppError(
                errors.VALIDATION_ERROR, "주장 빈도는 월 1~31회 정수여야 합니다.",
                status_code=422,
            )
        claim["claimed_frequency_per_month"] = frequency
    if raw.get("claims_demand") is not None:
        claim["claims_demand"] = bool(raw["claims_demand"])
    return claim


def _latest_official_survey(
    connection: sqlite3.Connection, area_id: str, service_type: str
) -> dict[str, Any] | None:
    row = connection.execute(
        """SELECT survey_id, survey_date, frequency_per_month, structured_data_json
           FROM surveys WHERE area_id=? AND service_type=?
           ORDER BY survey_date DESC, created_at DESC LIMIT 1""",
        (area_id, service_type),
    ).fetchone()
    if row is None:
        return None
    structured = json.loads(row["structured_data_json"] or "{}")
    return {
        "survey_id": row["survey_id"],
        "survey_date": row["survey_date"],
        "frequency_per_month": row["frequency_per_month"],
        "demand_status": structured.get("demand_status"),
    }


def detect_conflicts(
    connection: sqlite3.Connection,
    area_id: str,
    service_type: str | None,
    claim: dict[str, Any],
) -> list[dict[str, Any]]:
    """Compare a claim with the latest official survey; never overwrites either side."""
    if service_type is None:
        return []
    official = _latest_official_survey(connection, area_id, service_type)
    if official is None:
        return []
    found: list[dict[str, Any]] = []
    claims_demand = bool(claim.get("claims_demand")) or "claimed_frequency_per_month" in claim
    if official["demand_status"] == "NO_DEMAND" and claims_demand:
        found.append(
            {"conflict_type": "RESIDENT_CLAIM_VS_NO_OFFICIAL_DEMAND", "official": official}
        )
    claimed = claim.get("claimed_frequency_per_month")
    surveyed = official["frequency_per_month"]
    if claimed is not None and surveyed is not None:
        diff = abs(int(claimed) - int(surveyed))
        ratio = max(claimed, surveyed) / max(1, min(claimed, surveyed))
        if diff >= FREQUENCY_CONFLICT_MIN_ABS_DIFF and ratio >= FREQUENCY_CONFLICT_MIN_RATIO:
            found.append(
                {"conflict_type": "RESIDENT_CLAIM_VS_SURVEY_FREQUENCY", "official": official}
            )
    return found


def duplicate_candidates(
    connection: sqlite3.Connection,
    feedback_id: str,
    area_id: str,
    service_type: str | None,
    feedback_type: str,
    description: str,
) -> list[dict[str, Any]]:
    rows = connection.execute(
        """SELECT feedback_id, description, status, submitted_at FROM resident_feedback
           WHERE area_id=? AND feedback_id<>? AND feedback_type=?
             AND COALESCE(service_type,'')=COALESCE(?,'') AND submitted_at>=?""",
        (area_id, feedback_id, feedback_type, service_type,
         _days_ago_iso(NEAR_DUPLICATE_WINDOW_DAYS)),
    ).fetchall()
    candidates = []
    for row in rows:
        score = _similarity(description, str(row["description"]))
        if score >= NEAR_DUPLICATE_SIMILARITY:
            other = str(row["feedback_id"])
            a, b = sorted((feedback_id, other))
            decision = connection.execute(
                "SELECT state, canonical_feedback_id FROM resident_feedback_duplicate_decisions "
                "WHERE feedback_id_a=? AND feedback_id_b=?",
                (a, b),
            ).fetchone()
            candidates.append({
                "feedback_id": other,
                "similarity": round(score, 2),
                "status": row["status"],
                "submitted_at": row["submitted_at"],
                "decision": decision["state"] if decision else "UNREVIEWED",
                "canonical_feedback_id": decision["canonical_feedback_id"] if decision else None,
            })
    candidates.sort(key=lambda item: (-item["similarity"], item["feedback_id"]))
    return candidates


def submit_feedback(connection: sqlite3.Connection, payload: dict[str, Any]) -> dict[str, Any]:
    area = _area(connection, str(payload["area_id"]))
    service_type = payload.get("service_type")
    if service_type:
        _service(connection, service_type)
    else:
        service_type = None
    claim = _validated_claim(payload.get("claim"))
    description, was_redacted = redact_pii(str(payload["description"]).strip())
    requested_change = payload.get("requested_change")
    if requested_change:
        requested_change, _ = redact_pii(str(requested_change).strip())
    feedback_type = str(payload["feedback_type"])
    fingerprint = content_fingerprint(area["area_id"], service_type, feedback_type, description)
    since = _days_ago_iso(1)
    area_count = connection.execute(
        "SELECT COUNT(*) FROM resident_feedback WHERE area_id=? AND submitted_at>=?",
        (area["area_id"], since),
    ).fetchone()[0]
    region_count = connection.execute(
        "SELECT COUNT(*) FROM resident_feedback WHERE region_id=? AND submitted_at>=?",
        (area["region_id"], since),
    ).fetchone()[0]
    if area_count >= FEEDBACK_AREA_DAILY_LIMIT or region_count >= FEEDBACK_REGION_DAILY_LIMIT:
        logger.warning("feedback_rate_limited area=%s", area["area_id"])
        raise AppError(
            errors.FEEDBACK_RATE_LIMITED,
            "짧은 시간에 접수된 의견이 한도를 넘었습니다. 기존 의견 검토 후 다시 시도해 주세요.",
            status_code=429,
            details={"area_id": area["area_id"], "daily_limit": FEEDBACK_AREA_DAILY_LIMIT},
            retryable=True,
        )
    existing = connection.execute(
        "SELECT feedback_id FROM resident_feedback WHERE area_id=? AND content_fingerprint=? "
        "AND status NOT IN ('REJECTED') AND submitted_at>=?",
        (area["area_id"], fingerprint, _days_ago_iso(EXACT_DUPLICATE_WINDOW_DAYS)),
    ).fetchone()
    if existing is not None:
        raise AppError(
            errors.FEEDBACK_DUPLICATE,
            "같은 내용의 의견이 이미 접수되어 있습니다.",
            status_code=409,
            details={"existing_feedback_id": existing["feedback_id"]},
        )
    now = _now()
    feedback_id = f"fb-{uuid4().hex}"
    connection.execute(
        """INSERT INTO resident_feedback(
               feedback_id, region_id, area_id, service_type, feedback_type, submitted_at,
               submitter_role, intake_channel, description, description_was_redacted,
               requested_change, claim_json, evidence_attachment_metadata_json, status,
               content_fingerprint, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,'SUBMITTED',?,?,?)""",
        (
            feedback_id, area["region_id"], area["area_id"], service_type, feedback_type, now,
            payload.get("submitter_role", "RESIDENT"),
            payload.get("intake_channel", "PUBLIC_FORM"),
            description, int(was_redacted), requested_change or None,
            json.dumps(claim, ensure_ascii=False, sort_keys=True),
            json.dumps(payload.get("evidence_attachment_metadata") or [], ensure_ascii=False),
            fingerprint, now, now,
        ),
    )
    contact = (payload.get("contact") or "").strip()
    if contact:
        connection.execute(
            "INSERT INTO resident_feedback_contacts(feedback_id, contact_text, created_at) "
            "VALUES (?,?,?)",
            (feedback_id, contact[:200], now),
        )
    conflicts = []
    for found in detect_conflicts(connection, area["area_id"], service_type, claim):
        conflict_id = f"fbc-{uuid4().hex}"
        connection.execute(
            """INSERT INTO resident_feedback_conflicts(
                   conflict_id, feedback_id, area_id, service_type, conflict_type, official_json,
                   claim_json, status, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,'REVIEW_REQUIRED',?,?)""",
            (conflict_id, feedback_id, area["area_id"], service_type, found["conflict_type"],
             json.dumps(found["official"], ensure_ascii=False, sort_keys=True),
             json.dumps(claim, ensure_ascii=False, sort_keys=True), now, now),
        )
        conflicts.append(conflict_id)
        record_audit_event(
            connection, event_type="FEEDBACK_CONFLICT_CREATED", subject_type="resident_feedback",
            subject_id=feedback_id, actor_role="SYSTEM",
            details={"conflict_id": conflict_id, "conflict_type": found["conflict_type"]},
        )
    record_audit_event(
        connection, event_type="FEEDBACK_SUBMITTED", subject_type="resident_feedback",
        subject_id=feedback_id, actor_role="RESIDENT",
        details={
            "area_id": area["area_id"], "service_type": service_type,
            "feedback_type": feedback_type, "intake_channel": payload.get("intake_channel"),
        },
    )
    connection.commit()
    logger.info("feedback_submitted id=%s area=%s type=%s", feedback_id, area["area_id"],
                feedback_type)
    result = get_feedback(connection, feedback_id)
    result["conflict_ids"] = conflicts
    return result


def get_feedback(connection: sqlite3.Connection, feedback_id: str) -> dict[str, Any]:
    row = connection.execute(
        "SELECT * FROM resident_feedback WHERE feedback_id=?", (feedback_id,)
    ).fetchone()
    if row is None:
        raise AppError(
            errors.VALIDATION_ERROR, "의견을 찾을 수 없습니다.", status_code=404,
            details={"feedback_id": feedback_id},
        )
    item = _public_row(row)
    item["has_contact"] = connection.execute(
        "SELECT 1 FROM resident_feedback_contacts WHERE feedback_id=?", (feedback_id,)
    ).fetchone() is not None
    item["conflicts"] = [
        _conflict_row(c) for c in connection.execute(
            "SELECT * FROM resident_feedback_conflicts WHERE feedback_id=? ORDER BY created_at",
            (feedback_id,),
        ).fetchall()
    ]
    item["duplicate_candidates"] = duplicate_candidates(
        connection, feedback_id, item["area_id"], item["service_type"], item["feedback_type"],
        item["description"],
    )
    return item


def get_contact(connection: sqlite3.Connection, feedback_id: str) -> str | None:
    """Staff-only contact lookup; intentionally absent from list/export payloads."""
    row = connection.execute(
        "SELECT contact_text FROM resident_feedback_contacts WHERE feedback_id=?", (feedback_id,)
    ).fetchone()
    return None if row is None else str(row["contact_text"])


def _conflict_row(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    item["official"] = json.loads(item.pop("official_json"))
    item["claim"] = json.loads(item.pop("claim_json"))
    return item


def list_feedback(
    connection: sqlite3.Connection,
    *,
    region_id: str | None = None,
    area_id: str | None = None,
    status: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    clauses, params = [], []
    for column, value in (("region_id", region_id), ("area_id", area_id), ("status", status)):
        if value:
            clauses.append(f"{column}=?")
            params.append(value)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = connection.execute(
        f"SELECT * FROM resident_feedback {where} ORDER BY submitted_at DESC, feedback_id "
        "LIMIT ?",
        (*params, min(max(limit, 1), 500)),
    ).fetchall()
    return [_public_row(row) for row in rows]


def export_feedback_rows(
    connection: sqlite3.Connection, region_id: str | None = None
) -> list[dict[str, Any]]:
    """Export view: no contact, no attachment metadata, no reviewer free text."""
    keep = (
        "feedback_id", "region_id", "area_id", "service_type", "feedback_type", "submitted_at",
        "status", "freshness", "description", "claim",
    )
    return [{key: row[key] for key in keep} for row in list_feedback(
        connection, region_id=region_id, limit=500)]


def transition_feedback(
    connection: sqlite3.Connection,
    feedback_id: str,
    action: str,
    role: str,
    note: str | None = None,
) -> dict[str, Any]:
    row = connection.execute(
        "SELECT * FROM resident_feedback WHERE feedback_id=?", (feedback_id,)
    ).fetchone()
    if row is None:
        raise AppError(errors.VALIDATION_ERROR, "의견을 찾을 수 없습니다.", status_code=404)
    if role not in REVIEW_ROLES:
        raise AppError(
            errors.REVIEW_REQUIRED, "담당자 또는 검토자만 의견을 처리할 수 있습니다.",
            status_code=403,
        )
    current = str(row["status"])
    target = FEEDBACK_TRANSITIONS.get((current, action))
    if target is None:
        raise AppError(
            errors.REVIEW_REQUIRED,
            f"'{STATUS_LABELS_KO[current]}' 상태에서는 이 작업을 할 수 없습니다.",
            status_code=409,
            details={"status": current, "action": action},
        )
    note = (redact_pii(note.strip())[0] if note else None) or None
    if action in ("reject", "request_info", "accept", "resolve") and not note:
        raise AppError(
            errors.VALIDATION_ERROR, "처리 사유(메모)를 입력해야 합니다.", status_code=422,
        )
    now = _now()
    stale_plan_ids: list[str] = []
    evidence_id: str | None = None
    if action == "accept":
        evidence_id, stale_plan_ids = _accept_as_evidence(connection, row, role, now)
    connection.execute(
        """UPDATE resident_feedback SET status=?, reviewer_id=?, reviewed_at=?,
               resolution=COALESCE(?, resolution),
               linked_demand_evidence_id=COALESCE(?, linked_demand_evidence_id), updated_at=?
           WHERE feedback_id=?""",
        (target, role, now, note, evidence_id, now, feedback_id),
    )
    record_audit_event(
        connection, event_type=ACTION_AUDIT_EVENTS[action], subject_type="resident_feedback",
        subject_id=feedback_id, actor_role=role,  # type: ignore[arg-type]
        details={"from": current, "to": target, "evidence_id": evidence_id,
                 "stale_plan_ids": stale_plan_ids},
    )
    connection.commit()
    result = get_feedback(connection, feedback_id)
    result["stale_plan_ids"] = stale_plan_ids
    return result


def _accept_as_evidence(
    connection: sqlite3.Connection, row: sqlite3.Row, role: str, now: str
) -> tuple[str, list[str]]:
    service_type = row["service_type"]
    if service_type is None:
        raise AppError(
            errors.VALIDATION_ERROR, "서비스 유형이 없는 의견은 근거로 채택할 수 없습니다.",
            status_code=422,
        )
    service = _service(connection, str(service_type))
    if service["policy_status"] != "ALLOWED":
        raise AppError(
            errors.REGULATED_SERVICE,
            "규제·제외 서비스에 대한 의견은 수요 근거로 채택할 수 없습니다.",
            status_code=422,
            details={"service_type": service_type, "policy_status": service["policy_status"]},
        )
    open_conflicts = connection.execute(
        "SELECT conflict_id FROM resident_feedback_conflicts WHERE feedback_id=? "
        "AND status='REVIEW_REQUIRED'",
        (row["feedback_id"],),
    ).fetchall()
    if open_conflicts:
        raise AppError(
            errors.FEEDBACK_CONFLICT,
            "공식 근거와 충돌하는 의견입니다. 충돌을 먼저 해결해야 채택할 수 있습니다.",
            status_code=409,
            details={"conflict_ids": [c["conflict_id"] for c in open_conflicts]},
        )
    if connection.execute(
        "SELECT 1 FROM resident_feedback_conflicts WHERE feedback_id=? "
        "AND resolution_method IN ('KEEP_OFFICIAL_EVIDENCE','FURTHER_SURVEY')",
        (row["feedback_id"],),
    ).fetchone():
        raise AppError(
            errors.FEEDBACK_CONFLICT,
            "충돌 해결 결과가 이 의견의 채택을 허용하지 않습니다.", status_code=409,
        )
    evidence_id = f"rce-{uuid4().hex}"
    payload = {
        "claim": json.loads(row["claim_json"]),
        "feedback_type": row["feedback_type"],
        "verification": "UNVERIFIED_CLAIM",
        "accepted_by_role": role,
    }
    connection.execute(
        """INSERT INTO resident_claim_evidence(
               evidence_id, feedback_id, area_id, service_type, payload_json, occurred_on,
               provenance, created_at)
           VALUES (?,?,?,?,?,?,?,?)""",
        (evidence_id, row["feedback_id"], row["area_id"], service_type,
         json.dumps(payload, ensure_ascii=False, sort_keys=True),
         str(row["submitted_at"])[:10], f"RESIDENT_FEEDBACK:{row['feedback_id']}", now),
    )
    return evidence_id, mark_plans_stale(connection, str(row["region_id"]), STALE_REASON)


def mark_plans_stale(connection: sqlite3.Connection, region_id: str, reason: str) -> list[str]:
    """Flag live plans as stale; approved plans stay immutable (only the flag changes)."""
    rows = connection.execute(
        """SELECT schedule_id FROM schedule_runs
           WHERE region_id=? AND approval_status<>'SUPERSEDED' AND stale_since IS NULL""",
        (region_id,),
    ).fetchall()
    ids = [str(r["schedule_id"]) for r in rows]
    if ids:
        now = _now()
        connection.executemany(
            "UPDATE schedule_runs SET stale_since=?, stale_reason=? WHERE schedule_id=?",
            [(now, reason, schedule_id) for schedule_id in ids],
        )
        record_audit_event(
            connection, event_type="PLAN_MARKED_STALE", subject_type="region",
            subject_id=region_id, actor_role="SYSTEM",
            details={"reason": reason, "schedule_ids": ids},
        )
    return ids


def resolve_conflict(
    connection: sqlite3.Connection,
    conflict_id: str,
    resolution_method: str,
    role: str,
    reason: str,
) -> dict[str, Any]:
    if resolution_method not in CONFLICT_RESOLUTIONS:
        raise AppError(
            errors.VALIDATION_ERROR, "알 수 없는 충돌 해결 방식입니다.", status_code=422
        )
    if role not in REVIEW_ROLES:
        raise AppError(errors.REVIEW_REQUIRED, "담당자 또는 검토자만 해결할 수 있습니다.",
                       status_code=403)
    reason = redact_pii((reason or "").strip())[0]
    if not reason:
        raise AppError(errors.VALIDATION_ERROR, "해결 사유를 입력해야 합니다.", status_code=422)
    row = connection.execute(
        "SELECT * FROM resident_feedback_conflicts WHERE conflict_id=?", (conflict_id,)
    ).fetchone()
    if row is None:
        raise AppError(errors.VALIDATION_ERROR, "충돌을 찾을 수 없습니다.", status_code=404)
    if row["status"] != "REVIEW_REQUIRED":
        raise AppError(errors.FEEDBACK_CONFLICT, "이미 해결된 충돌입니다.", status_code=409)
    now = _now()
    connection.execute(
        """UPDATE resident_feedback_conflicts SET status='RESOLVED', resolution_method=?,
               reason=?, resolved_by=?, updated_at=? WHERE conflict_id=?""",
        (resolution_method, reason, role, now, conflict_id),
    )
    follow_up = {"FURTHER_SURVEY": "NEEDS_MORE_INFO", "KEEP_OFFICIAL_EVIDENCE": "REJECTED"}.get(
        resolution_method
    )
    feedback = connection.execute(
        "SELECT status FROM resident_feedback WHERE feedback_id=?", (row["feedback_id"],)
    ).fetchone()
    if follow_up and feedback["status"] in ("SUBMITTED", "UNDER_REVIEW", "NEEDS_MORE_INFO"):
        connection.execute(
            "UPDATE resident_feedback SET status=?, resolution=?, reviewer_id=?, reviewed_at=?, "
            "updated_at=? WHERE feedback_id=?",
            (follow_up, reason, role, now, now, row["feedback_id"]),
        )
    record_audit_event(
        connection, event_type="FEEDBACK_CONFLICT_RESOLVED", subject_type="resident_feedback",
        subject_id=str(row["feedback_id"]), actor_role=role,  # type: ignore[arg-type]
        details={"conflict_id": conflict_id, "resolution_method": resolution_method},
    )
    connection.commit()
    return _conflict_row(connection.execute(
        "SELECT * FROM resident_feedback_conflicts WHERE conflict_id=?", (conflict_id,)
    ).fetchone())


def decide_duplicate(
    connection: sqlite3.Connection,
    feedback_id: str,
    other_feedback_id: str,
    state: str,
    role: str,
    reason: str,
    canonical_feedback_id: str | None = None,
) -> dict[str, Any]:
    if state not in ("LINKED_DUPLICATE", "CONFIRMED_DISTINCT"):
        raise AppError(errors.VALIDATION_ERROR, "알 수 없는 중복 판정입니다.", status_code=422)
    if role not in REVIEW_ROLES:
        raise AppError(errors.REVIEW_REQUIRED, "담당자 또는 검토자만 판정할 수 있습니다.",
                       status_code=403)
    if feedback_id == other_feedback_id:
        raise AppError(errors.VALIDATION_ERROR, "서로 다른 의견을 지정해야 합니다.",
                       status_code=422)
    for fid in (feedback_id, other_feedback_id):
        get_feedback_row = connection.execute(
            "SELECT 1 FROM resident_feedback WHERE feedback_id=?", (fid,)
        ).fetchone()
        if get_feedback_row is None:
            raise AppError(errors.VALIDATION_ERROR, "의견을 찾을 수 없습니다.", status_code=404)
    canonical = None
    if state == "LINKED_DUPLICATE":
        canonical = canonical_feedback_id or sorted((feedback_id, other_feedback_id))[0]
        if canonical not in (feedback_id, other_feedback_id):
            raise AppError(errors.VALIDATION_ERROR, "대표 의견은 두 의견 중 하나여야 합니다.",
                           status_code=422)
    reason = redact_pii((reason or "").strip())[0]
    if not reason:
        raise AppError(errors.VALIDATION_ERROR, "판정 사유를 입력해야 합니다.", status_code=422)
    a, b = sorted((feedback_id, other_feedback_id))
    connection.execute(
        """INSERT INTO resident_feedback_duplicate_decisions(
               feedback_id_a, feedback_id_b, state, canonical_feedback_id, reason, actor_role,
               decided_at) VALUES (?,?,?,?,?,?,?)
           ON CONFLICT(feedback_id_a, feedback_id_b) DO UPDATE SET state=excluded.state,
               canonical_feedback_id=excluded.canonical_feedback_id, reason=excluded.reason,
               actor_role=excluded.actor_role, decided_at=excluded.decided_at""",
        (a, b, state, canonical, reason, role, _now()),
    )
    record_audit_event(
        connection, event_type="FEEDBACK_DUPLICATE_DECIDED", subject_type="resident_feedback",
        subject_id=feedback_id, actor_role=role,  # type: ignore[arg-type]
        details={"other_feedback_id": other_feedback_id, "state": state},
    )
    connection.commit()
    return {"feedback_id_a": a, "feedback_id_b": b, "state": state,
            "canonical_feedback_id": canonical}


def area_feedback_signal(
    connection: sqlite3.Connection, area_id: str, service_type: str | None = None
) -> dict[str, Any]:
    """Read-only signal for assessments. It can request a survey; it never raises demand."""
    params: list[Any] = [area_id]
    service_clause = ""
    if service_type:
        service_clause = " AND service_type=?"
        params.append(service_type)
    claims = connection.execute(
        f"""SELECT c.evidence_id, c.feedback_id, c.service_type, c.occurred_on
            FROM resident_claim_evidence c
            WHERE c.area_id=? {service_clause.replace('service_type', 'c.service_type')}
              AND c.verification_state='UNVERIFIED_CLAIM'""",
        params,
    ).fetchall()
    unverified = []
    for claim in claims:
        survey = connection.execute(
            "SELECT 1 FROM surveys WHERE area_id=? AND service_type=? AND survey_date>=?",
            (area_id, claim["service_type"], claim["occurred_on"]),
        ).fetchone()
        if survey is None:
            unverified.append(claim)
    pending = connection.execute(
        f"SELECT COUNT(*) FROM resident_feedback WHERE area_id=?{service_clause} "
        "AND status IN ('SUBMITTED','UNDER_REVIEW','NEEDS_MORE_INFO')",
        params,
    ).fetchone()[0]
    open_conflicts = connection.execute(
        f"SELECT COUNT(*) FROM resident_feedback_conflicts WHERE area_id=?{service_clause} "
        "AND status='REVIEW_REQUIRED'",
        params,
    ).fetchone()[0]
    return {
        "accepted_claim_count": len(claims),
        "unverified_claim_count": len(unverified),
        "bounded_observation_contribution": bounded_observation_contribution(
            "RESIDENT_FEEDBACK", len(unverified)
        ),
        "pending_feedback_count": int(pending),
        "open_conflict_count": int(open_conflicts),
        "needs_survey": bool(unverified or pending or open_conflicts),
        "evidence_grade": "UNVERIFIED_CLAIM" if unverified else "NONE",
        "calibrated": False,
    }


def area_feedback_summary(
    connection: sqlite3.Connection, area_id: str, recent_limit: int = 5
) -> dict[str, Any]:
    _area(connection, area_id)
    counts = {status: 0 for status in STATUS_LABELS_KO}
    for row in connection.execute(
        "SELECT status, COUNT(*) AS n FROM resident_feedback WHERE area_id=? GROUP BY status",
        (area_id,),
    ).fetchall():
        counts[str(row["status"])] = int(row["n"])
    return {
        "area_id": area_id,
        "counts": counts,
        "total": sum(counts.values()),
        "recent": list_feedback(connection, area_id=area_id, limit=recent_limit),
        "signal": area_feedback_signal(connection, area_id),
        "note": "주민 의견은 검증 전 주장이며 조사 결과와 동급이 아닙니다.",
    }


def attention_counts(connection: sqlite3.Connection, region_id: str) -> dict[str, int]:
    row = connection.execute(
        """SELECT
             SUM(CASE WHEN status='SUBMITTED' THEN 1 ELSE 0 END) AS new_count,
             SUM(CASE WHEN status IN ('UNDER_REVIEW','NEEDS_MORE_INFO') THEN 1 ELSE 0 END)
               AS in_review_count
           FROM resident_feedback WHERE region_id=?""",
        (region_id,),
    ).fetchone()
    conflicts = connection.execute(
        "SELECT COUNT(*) FROM resident_feedback_conflicts k JOIN village_service_areas a "
        "ON a.area_id=k.area_id WHERE a.region_id=? AND k.status='REVIEW_REQUIRED'",
        (region_id,),
    ).fetchone()[0]
    return {
        "new_feedback": int(row["new_count"] or 0),
        "in_review_feedback": int(row["in_review_count"] or 0),
        "open_conflicts": int(conflicts),
    }
