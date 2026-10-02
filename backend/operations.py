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
    latest_run = connection.execute(
        """SELECT schedule_id FROM schedule_runs
           WHERE region_id=? ORDER BY rowid DESC LIMIT 1""",
        (region_id,),
    ).fetchone()
    if latest_run:
        sched_id = str(latest_run["schedule_id"])
        triggers = database.get_schedule_replan_triggers(connection, sched_id)
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
                    suggested_action = f"추가 예산 {budget_gap:,}원 확보"
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
