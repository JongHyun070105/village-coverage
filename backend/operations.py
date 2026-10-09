"""Operations Mode Attention Layer for VillageCoverage (§25)."""

from __future__ import annotations

import sqlite3
from typing import Any

from backend import database
from backend.feasibility import explain_area_feasibility


def build_operations_attention(
    connection: sqlite3.Connection,
    region_id: str,
    scenario_results: dict[str, Any] | None = None,
    *,
    public_demo_owner_hash: str | None = None,
) -> list[dict[str, Any]]:
    """Generate high-priority attention action items for operations personnel (§25)."""
    items: list[dict[str, Any]] = []
    area_names = {
        str(row["area_id"]): str(row["name"])
        for row in connection.execute(
            "SELECT area_id, name FROM village_service_areas WHERE region_id=?",
            (region_id,),
        ).fetchall()
    }

    # Current balanced comparison: make zero-service areas visible as a planning
    # fact without labeling them as risks or turning the comparison into a decision.
    balanced = (scenario_results or {}).get("balanced") or {}
    for assignment in balanced.get("assignments", []):
        if assignment.get("covered") is not False:
            continue
        area_id = str(assignment.get("area_id", ""))
        area_name = str(assignment.get("area_name") or area_names.get(area_id, "권역"))
        items.append(
            {
                "id": f"zero-service-{area_id}",
                "category": "ZERO_SERVICE_AREA",
                "severity": "MEDIUM",
                "title": f"{area_name} — 현재 균형 비교안에서 서비스 미배정",
                "description": (
                    "비교안에서 서비스가 배정되지 않았습니다. 효율·소외 최소화·"
                    "최소보장 결과와 원인을 함께 검토하세요."
                ),
                "action_label": "비교안 보기",
                "action_url": "/scenarios",
            }
        )
        if len(items) >= 3:
            break

    feedback_status_labels = {
        "SUBMITTED": "신규 주민 의견",
        "UNDER_REVIEW": "검토 중인 주민 의견",
        "NEEDS_MORE_INFO": "추가 확인이 필요한 주민 의견",
    }
    feedback = connection.execute(
        """SELECT feedback_id, area_id, status FROM resident_feedback
           WHERE region_id=? AND status IN ('SUBMITTED','UNDER_REVIEW','NEEDS_MORE_INFO')
           ORDER BY CASE status WHEN 'SUBMITTED' THEN 0 WHEN 'NEEDS_MORE_INFO' THEN 1 ELSE 2 END,
                    submitted_at ASC LIMIT 3""",
        (region_id,),
    ).fetchall()
    for row in feedback:
        area_id = str(row["area_id"])
        area_name = area_names.get(area_id, "권역")
        items.append(
            {
                "id": f"resident-feedback-{row['feedback_id']}",
                "category": "RESIDENT_FEEDBACK",
                "severity": "MEDIUM",
                "title": f"{area_name} — {feedback_status_labels[str(row['status'])]}",
                "description": "주민 주장은 담당자 검토 전까지 수요·예측·계획에 반영되지 않습니다.",
                "action_label": "의견 검토",
                "action_url": f"/feedback?area_id={area_id}",
            }
        )

    # Approval queue is independent from scenario results. Change requests are
    # stored as draft plans plus an open reviewer request.
    owner_clause = (
        "AND EXISTS (SELECT 1 FROM public_demo_plan_owners owner "
        "WHERE owner.schedule_id=s.schedule_id AND owner.session_hash=?) "
        if public_demo_owner_hash is not None
        else ""
    )
    approval_parameters: tuple[Any, ...] = (region_id,)
    if public_demo_owner_hash is not None:
        approval_parameters += (public_demo_owner_hash,)
    approvals = connection.execute(
        """SELECT s.schedule_id, s.plan_version,
                  CASE WHEN EXISTS(
                      SELECT 1 FROM plan_change_requests r
                      WHERE r.schedule_id=s.schedule_id AND r.resolved_at IS NULL
                  ) THEN 'CHANGES_REQUESTED' ELSE s.approval_status END AS effective_status
           FROM schedule_runs s
           WHERE s.region_id=? AND (
               s.approval_status='UNDER_REVIEW' OR EXISTS(
                   SELECT 1 FROM plan_change_requests r
                   WHERE r.schedule_id=s.schedule_id AND r.resolved_at IS NULL
               )
           ) """
        + owner_clause
        + """
           ORDER BY s.rowid DESC LIMIT 3""",
        approval_parameters,
    ).fetchall()
    for row in approvals:
        status = str(row["effective_status"])
        label = "수정 요청" if status == "CHANGES_REQUESTED" else "승인 대기"
        items.append(
            {
                "id": f"approval-{row['schedule_id']}",
                "category": "APPROVAL_PENDING",
                "severity": "MEDIUM",
                "title": f"계획 v{row['plan_version']} — {label}",
                "description": "승인 상태와 변경 이력을 확인하고 담당 기관이 최종 결정합니다.",
                "action_label": "계획 검토",
                "action_url": f"/plans?id={row['schedule_id']}",
            }
        )

    minimum = (scenario_results or {}).get("minimum_coverage") or {}
    budget_gap = minimum.get("budget_gap_won")
    if minimum.get("guarantee_feasible") is True and isinstance(budget_gap, int) and budget_gap > 0:
        items.append(
            {
                "id": f"funding-gap-{region_id}-{budget_gap}",
                "category": "ADDITIONAL_FUNDING",
                "severity": "MEDIUM",
                "title": "최소보장 비교안 — 추가재원 검토 필요",
                "description": (
                    f"월간 집계 기준 최소 서비스를 검토하려면 추가 {budget_gap:,}원이 필요합니다. "
                    "실제 일정·공급자 제약은 별도 확인이 필요합니다."
                ),
                "action_label": "비교안 보기",
                "action_url": "/scenarios",
            }
        )

    # 1. Unresolved evidence conflicts
    conflicts = connection.execute(
        """SELECT c.conflict_id, c.area_id, a.name AS area_name, c.conflict_type
           FROM demand_evidence_conflicts c
           JOIN village_service_areas a ON a.area_id=c.area_id
           WHERE a.region_id=? AND c.status='REVIEW_REQUIRED'
           ORDER BY c.created_at ASC""",
        (region_id,),
    ).fetchall()
    for row in conflicts:
        items.append(
            {
                "id": f"conflict-{row['conflict_id']}",
                "category": "EVIDENCE_CONFLICT",
                "severity": "HIGH",
                "title": f"{row['area_name']} — 조사자료 충돌",
                "description": "동일 서비스 항목에 대해 상충하는 조사 근거가 확인되었습니다.",
                "action_label": "검토",
                "action_url": f"/demand?area_id={row['area_id']}",
            }
        )

    # 2. Provider decline / replan triggers from latest schedule
    latest_parameters: tuple[Any, ...] = (region_id,)
    if public_demo_owner_hash is not None:
        latest_parameters += (public_demo_owner_hash,)
    latest_run = connection.execute(
        """SELECT schedule_runs.schedule_id FROM schedule_runs
           WHERE region_id=? """
        + owner_clause.replace("s.schedule_id", "schedule_runs.schedule_id")
        + "ORDER BY rowid DESC LIMIT 1",
        latest_parameters,
    ).fetchone()
    if latest_run:
        sched_id = str(latest_run["schedule_id"])
        triggers = database.get_schedule_replan_triggers(
            connection,
            sched_id,
            public_demo_owner_hash=public_demo_owner_hash,
        )
        if triggers:
            for trigger in triggers[:3]:
                provider_name = trigger.get("provider_name") or "공급자"
                date_str = trigger.get("scheduled_date") or ""
                items.append(
                    {
                        "id": f"replan-{sched_id}-{trigger.get('round_id', '')}",
                        "category": "PROVIDER_DECLINE",
                        "severity": "HIGH",
                        "title": f"{provider_name} — {date_str} 회차 불참",
                        "description": "공급자 불참으로 계획 재생성이 필요합니다.",
                        "action_label": "재계획",
                        "action_url": f"/calendar?schedule_id={sched_id}",
                    }
                )

    # 3. Unmet minimum coverage areas
    if scenario_results and "minimum_coverage" in scenario_results:
        min_res = scenario_results["minimum_coverage"]
        budget_gap = min_res.get("budget_gap_won")
        monthly_guarantee_money_shortage = (
            min_res.get("guarantee_feasible") is True
            and isinstance(budget_gap, int)
            and budget_gap > 0
        )
        for assignment in min_res.get("assignments", []):
            minimum_met = assignment.get("minimum_frequency_met")
            assignment_unmet = minimum_met is False or (
                minimum_met is None and not assignment.get("covered", False)
            )
            if assignment_unmet:
                if monthly_guarantee_money_shortage:
                    # The exact monthly guarantee model proved a feasible plan and
                    # quantified its budget gap. Per-area assignments can still be
                    # missing under the current budget because cost is shared.
                    feasibility = explain_area_feasibility("MONEY_SHORTAGE")
                    reason = (
                        "월간 집계 최소 서비스 기준을 충족하려면 "
                        f"{budget_gap:,}원의 예산이 추가로 필요합니다."
                    )
                    suggested_action = f"추가 재원 {budget_gap:,}원 검토"
                else:
                    feasibility = assignment.get("feasibility_explanation")
                    if not feasibility:
                        feasibility = explain_area_feasibility(
                            assignment.get("primary_reason")
                            or assignment.get("constraint_reason"),
                            service_type=str(
                                assignment.get("service_type", "daily_necessities")
                            ),
                            secondary_codes=assignment.get("secondary_reasons"),
                        )
                    reason = (
                        assignment.get("reason_explanation")
                        or feasibility.get("reason_explanation")
                        or "최소 서비스 기준을 충족하지 못했습니다."
                    )
                    suggested_action = (
                        assignment.get("suggested_action")
                        or feasibility.get("suggested_action")
                        or "공급자 및 일정 조건을 검토해 주세요."
                    )
                money_resolvable = (
                    monthly_guarantee_money_shortage
                    or assignment.get("money_resolvable", feasibility.get("money_resolvable"))
                )
                budget_note = (
                    "예산 추가로 해결 가능."
                    if money_resolvable
                    else "예산 추가만으로 해결되지 않음."
                )
                area_id = str(assignment.get("area_id", ""))
                area_name = str(assignment.get("area_name") or area_names.get(area_id, "권역"))
                items.append(
                    {
                        "id": f"unmet-{area_id}",
                        "category": "UNMET_COVERAGE",
                        "severity": "MEDIUM",
                        "title": f"{area_name} — 최소 서비스 미충족",
                        "description": f"{reason} {budget_note} 권장: {suggested_action}.",
                        "action_label": "상세",
                        "action_url": f"/villages/{area_id}",
                    }
                )
            if len(items) >= 10:
                break

    return items
