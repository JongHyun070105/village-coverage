"""Plan approval workflow, audit trail, snapshot binding, fairness and explanations.

Demo roles only (PLANNER / REVIEWER); there is no authentication. Approved plans
are immutable: changes always create a new plan version, and approving a newer
version in the same lineage marks the older approved one SUPERSEDED.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
Role = Literal["PLANNER", "REVIEWER", "SYSTEM"]
APPROVAL_STATUSES = ("DRAFT", "UNDER_REVIEW", "APPROVED", "SUPERSEDED")
APPROVAL_LABELS_KO = {
    "DRAFT": "초안",
    "UNDER_REVIEW": "검토 중",
    "APPROVED": "승인됨",
    "SUPERSEDED": "대체됨",
}
# (from_status, action) -> (to_status, role allowed, audit event)
TRANSITIONS: dict[tuple[str, str], tuple[str, str, str]] = {
    ("DRAFT", "submit"): ("UNDER_REVIEW", "PLANNER", "PLAN_SUBMITTED_FOR_REVIEW"),
    ("UNDER_REVIEW", "approve"): ("APPROVED", "REVIEWER", "PLAN_APPROVED"),
    ("UNDER_REVIEW", "return"): ("DRAFT", "REVIEWER", "PLAN_RETURNED_TO_DRAFT"),
}


class ApprovalError(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def record_audit_event(
    connection: sqlite3.Connection,
    *,
    event_type: str,
    subject_type: str,
    subject_id: str,
    actor_role: Role = "PLANNER",
    details: dict[str, Any] | None = None,
) -> str:
    """Append-only audit row. Details must not contain raw resident text or secrets."""
    event_id = f"audit-{uuid4().hex}"
    connection.execute(
        """INSERT INTO audit_events(event_id, event_type, subject_type, subject_id, actor_role,
                                    occurred_at, details_json)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (event_id, event_type, subject_type, subject_id, actor_role, _now(),
         json.dumps(details or {}, ensure_ascii=False, sort_keys=True)),
    )
    return event_id


def list_audit_events(
    connection: sqlite3.Connection, *, subject_id: str | None = None, limit: int = 100
) -> list[dict[str, Any]]:
    query = "SELECT * FROM audit_events"
    params: tuple[Any, ...] = ()
    if subject_id:
        query += " WHERE subject_id=?"
        params = (subject_id,)
    query += " ORDER BY occurred_at DESC, rowid DESC LIMIT ?"
    rows = connection.execute(query, (*params, limit)).fetchall()
    return [{**dict(row), "details": json.loads(row["details_json"])} for row in rows]


def transition_plan(
    connection: sqlite3.Connection, schedule_id: str, action: str, role: str
) -> dict[str, Any]:
    row = connection.execute(
        "SELECT schedule_id, approval_status, lineage_root_id FROM schedule_runs "
        "WHERE schedule_id=?",
        (schedule_id,),
    ).fetchone()
    if row is None:
        raise ApprovalError("PLAN_NOT_FOUND", "계획을 찾을 수 없습니다.")
    current = str(row["approval_status"])
    transition = TRANSITIONS.get((current, action))
    if transition is None:
        raise ApprovalError(
            "INVALID_APPROVAL_TRANSITION",
            f"'{APPROVAL_LABELS_KO.get(current, current)}' 상태에서는 이 작업을 할 수 없습니다.",
        )
    target, allowed_role, event_type = transition
    if role != allowed_role:
        raise ApprovalError(
            "ROLE_NOT_PERMITTED",
            "이 작업은 "
            + ("검토자" if allowed_role == "REVIEWER" else "계획 담당자")
            + "만 할 수 있습니다.",
        )
    now = _now()
    superseded: list[str] = []
    if target == "APPROVED":
        for previous in connection.execute(
            "SELECT schedule_id FROM schedule_runs WHERE lineage_root_id=? "
            "AND approval_status='APPROVED' AND schedule_id<>?",
            (row["lineage_root_id"], schedule_id),
        ).fetchall():
            superseded.append(str(previous["schedule_id"]))
        for previous_id in superseded:
            connection.execute(
                "UPDATE schedule_runs SET approval_status='SUPERSEDED', approval_updated_at=? "
                "WHERE schedule_id=?",
                (now, previous_id),
            )
            record_audit_event(connection, event_type="PLAN_SUPERSEDED",
                               subject_type="schedule", subject_id=previous_id,
                               actor_role="SYSTEM", details={"superseded_by": schedule_id})
    connection.execute(
        "UPDATE schedule_runs SET approval_status=?, approval_updated_at=?, "
        "approved_by_role=? WHERE schedule_id=?",
        (target, now, role if target == "APPROVED" else None, schedule_id),
    )
    record_audit_event(connection, event_type=event_type, subject_type="schedule",
                       subject_id=schedule_id, actor_role=role,  # type: ignore[arg-type]
                       details={"from": current, "to": target, "superseded": superseded})
    return {"schedule_id": schedule_id, "previous_status": current, "approval_status": target,
            "superseded_schedule_ids": superseded}


def is_approved(connection: sqlite3.Connection, schedule_id: str) -> bool:
    row = connection.execute(
        "SELECT approval_status FROM schedule_runs WHERE schedule_id=?", (schedule_id,)
    ).fetchone()
    return bool(row) and row["approval_status"] == "APPROVED"


def _file_hash(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def data_snapshot_binding(route_matrix_fingerprint: str | None) -> dict[str, Any]:
    """Hashes of every input source a plan was computed from (V4 §97)."""
    artifacts = ROOT / "artifacts"
    snapshots = {}
    for name in ("empirical_prior_snapshot.json", "kosis_snapshot.json",
                 "home_doctor_snapshot.json"):
        snapshots[name] = _file_hash(artifacts / name)
    return {
        "public_data_fixture_sha256": _file_hash(ROOT / "data" / "demo.json"),
        "route_matrix_fingerprint": route_matrix_fingerprint,
        "evidence_snapshots_sha256": snapshots,
        "bound_at": _now(),
    }


def fairness_metrics(
    areas: list[dict[str, Any]], rounds: list[dict[str, Any]], *, month_start: date | None = None
) -> dict[str, Any]:
    """Descriptive distribution metrics; not a moral judgement of the plan."""
    demand = {str(a["id"]): max(0, int(a.get("simulated_monthly_demand") or 0)) for a in areas}
    served: dict[str, int] = defaultdict(int)
    first_day: dict[str, date] = {}
    for item in rounds:
        area_id = str(item.get("area_id"))
        served[area_id] += int(item.get("service_units") or item.get("units") or 1)
        day = date.fromisoformat(str(item["scheduled_date"]))
        first_day[area_id] = min(first_day.get(area_id, day), day)
    ratios = [min(1.0, served[a] / d) for a, d in demand.items() if d > 0]
    total_served = sum(served.values())
    shares = sorted(served.get(a, 0) / total_served for a in demand) if total_served else []
    n = len(shares)
    gini = (
        sum((2 * (i + 1) - n - 1) * share for i, share in enumerate(shares)) / n
        if n and total_served else None
    )
    start = month_start or (min(first_day.values()) if first_day else None)
    waits = sorted((first_day[a] - start).days for a in first_day) if start else []
    return {
        "coverage_gap_areas": sum(1 for a, d in demand.items() if d > 0 and served[a] == 0),
        "max_min_fulfillment_gap": round(max(ratios) - min(ratios), 3) if ratios else None,
        "min_fulfillment_ratio": round(min(ratios), 3) if ratios else None,
        "allocation_concentration_gini": round(gini, 3) if gini is not None else None,
        "waiting_days_min": waits[0] if waits else None,
        "waiting_days_max": waits[-1] if waits else None,
        "waiting_time_disparity_days": (waits[-1] - waits[0]) if waits else None,
        "note": "분배 상태를 설명하는 기술 지표이며 형평성의 정답을 뜻하지 않습니다.",
    }


INCLUSION_REASON_KO = {
    "MINIMUM_GUARANTEE_RULE": "최소보장 규칙",
    "DEMAND_SERVED": "수요 충족 배정",
    "SURVEY_REQUIRED_PROTECTION": "조사필요 권역 보호 가중",
    "VULNERABILITY_PRIORITY": "고령·1인가구 우선 가중",
    "UNDERSERVED_PRIORITY": "서비스 공백 기간 우선 가중",
}


def area_explanations(plan: dict[str, Any], areas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deterministic why-included / why-excluded text per area (no LLM)."""
    from backend.feasibility import explain_area_feasibility

    served: dict[str, int] = defaultdict(int)
    for item in plan.get("rounds", []):
        served[str(item.get("area_id"))] += 1
    breakdown = plan.get("feasibility_breakdown") or {}
    scenario = plan.get("scenario")
    rows = []
    for area in areas:
        area_id = str(area["id"])
        if served[area_id]:
            reasons = ["DEMAND_SERVED"]
            if scenario == "minimum_coverage":
                reasons.insert(0, "MINIMUM_GUARANTEE_RULE")
            if area.get("needs_survey") and scenario == "balanced":
                reasons.append("SURVEY_REQUIRED_PROTECTION")
            if scenario == "balanced" and int(area.get("single_households_65_plus") or 0) > 0:
                reasons.append("VULNERABILITY_PRIORITY")
            if scenario in {"balanced", "underserved_first"} and int(
                area.get("underserved_points") or 0
            ) > 0:
                reasons.append("UNDERSERVED_PRIORITY")
            rows.append({"area_id": area_id, "included": True, "rounds": served[area_id],
                         "reasons": reasons,
                         "reasons_ko": [INCLUSION_REASON_KO[r] for r in reasons]})
        else:
            explanation = breakdown.get(area_id) or explain_area_feasibility(
                "SCENARIO_PRIORITY", service_type=str(area.get("service_type")))
            rows.append({"area_id": area_id, "included": False, "rounds": 0,
                         "reasons": [explanation["primary_reason"],
                                     *explanation["secondary_reasons"]],
                         "reasons_ko": [explanation["reason_explanation"]],
                         "suggested_action": explanation["suggested_action"],
                         "money_resolvable": explanation["money_resolvable"]})
    return rows


POLICY_PRESETS = (
    {
        "preset_id": "efficiency_first",
        "label": "효율 중심",
        "scenario": "efficiency",
        "policy": {"minimum_services_per_area": 1, "elderly_priority_weight": 0,
                   "single_elderly_household_priority_weight": 0,
                   "survey_required_protection_weight": 0},
    },
    {
        "preset_id": "balanced",
        "label": "균형",
        "scenario": "balanced",
        "policy": {"minimum_services_per_area": 1, "elderly_priority_weight": 500,
                   "single_elderly_household_priority_weight": 500,
                   "survey_required_protection_weight": 1000},
    },
    {
        "preset_id": "vulnerable_first",
        "label": "취약지역 우선",
        "scenario": "balanced",
        "policy": {"minimum_services_per_area": 1, "elderly_priority_weight": 1000,
                   "single_elderly_household_priority_weight": 1000,
                   "survey_required_protection_weight": 1000},
    },
    {
        "preset_id": "gap_reduction",
        "label": "격차 완화",
        "scenario": "minimum_coverage",
        "policy": {"minimum_services_per_area": 1, "elderly_priority_weight": 500,
                   "single_elderly_household_priority_weight": 500,
                   "survey_required_protection_weight": 1000},
    },
    {
        "preset_id": "underserved_first",
        "label": "소외 최소화",
        "scenario": "underserved_first",
        "policy": {"minimum_services_per_area": 1, "elderly_priority_weight": 500,
                   "single_elderly_household_priority_weight": 500,
                   "survey_required_protection_weight": 1000},
    },
)


def policy_presets_payload() -> dict[str, Any]:
    from backend.scheduling import BALANCED_SCHEDULE_SCORE_WEIGHTS

    return {
        "presets": list(POLICY_PRESETS),
        "notice": (
            "프리셋은 추천이나 정답이 아니라 시작 설정입니다. "
            "모든 값은 화면에서 확인·수정할 수 있습니다."
        ),
        "balanced_objective_weights": dict(BALANCED_SCHEDULE_SCORE_WEIGHTS),
        "weight_semantics": {
            "service_volume": "서비스 회차(단위) 비중",
            "area_coverage": "서비스 권역 수 비중",
            "survey_protection": "조사필요 권역 보호",
            "vulnerability": "고령·1인가구 가중",
            "underserved": "서비스 공백 기간(소외) 가중",
            "concentration": "한 권역 집중 완화",
            "travel_cost": "이동비용 절감",
        },
    }
