"""Work-plan exports: CSV (assignments, budget, unmet areas) and a PDF plan summary.

Exports never include raw resident free text (V4 §46). Numbers follow the
public-sector display format (₩4,608,959; 2026. 10. 03.).
"""

from __future__ import annotations

import csv
import io
from datetime import date
from typing import Any

from backend.governance import APPROVAL_LABELS_KO
from backend.service_modes import COST_CATEGORY_LABELS_KO

SOLVER_STATUS_KO = {
    "OPTIMAL": "최적성 확인 완료",
    "FEASIBLE": "실행 가능한 계획 (최적성 미확인)",
    "TIME_LIMIT": "실행 가능한 계획 (제한시간 도달, 최적성 미확인)",
    "INFEASIBLE": "실행 가능한 계획 없음",
    "UNKNOWN": "상태 확인 불가",
}


def csv_safe_text(value: Any) -> str:
    """Neutralize spreadsheet formula injection in exported cells."""
    text = str(value if value is not None else "")
    first_significant = next(
        (
            character
            for character in text
            if not character.isspace() and ord(character) >= 32 and character != "﻿"
        ),
        "",
    )
    if first_significant in {"=", "+", "-", "@"}:
        return "'" + text
    return text


def won(value: int | float | None) -> str:
    return "미정" if value is None else f"₩{int(round(value)):,}"


def korean_date(value: str | date | None) -> str:
    if value is None:
        return "-"
    day = value if isinstance(value, date) else date.fromisoformat(str(value)[:10])
    return f"{day.year}. {day.month:02d}. {day.day:02d}."


def _csv(header: list[str], rows: list[list[Any]]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header)
    for row in rows:
        writer.writerow([csv_safe_text(cell) for cell in row])
    return "﻿" + buffer.getvalue()


def budget_breakdown_csv(plan: dict[str, Any]) -> str:
    summary = plan["summary"]
    items = [
        ("SERVICE_EXECUTION_COST", summary.get("service_cost_won")),
        ("TRAVEL_DISTANCE_COST", summary.get("travel_cost_won")),
        ("STAFF_COST", summary.get("minimum_compensation_topup_won")),
    ]
    rows = [[key, COST_CATEGORY_LABELS_KO[key], value if value is not None else "UNKNOWN",
             "OPTIMIZATION RESULT"] for key, value in items]
    rows.append(["TOTAL", "총 비용", summary.get("total_cost_won"), "OPTIMIZATION RESULT"])
    rows.append(["BUDGET", "예산", plan.get("budget_won"), "PLANNER INPUT"])
    return _csv(["category", "label_ko", "amount_won", "provenance"], rows)


def unmet_areas_csv(plan: dict[str, Any], explanations: list[dict[str, Any]]) -> str:
    rows = [
        [row["area_id"], "; ".join(row["reasons"]), "; ".join(row["reasons_ko"]),
         row.get("suggested_action", ""), row.get("money_resolvable")]
        for row in explanations if not row["included"]
    ]
    return _csv(["area_id", "reason_codes", "reasons_ko", "suggested_action",
                 "money_resolvable"], rows)


def plan_summary_pdf(
    plan: dict[str, Any], explanations: list[dict[str, Any]], fairness: dict[str, Any]
) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    font = "HYSMyeongJo-Medium"
    if font not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(UnicodeCIDFont(font))
    title = ParagraphStyle("t", fontName=font, fontSize=15, leading=20)
    body = ParagraphStyle("b", fontName=font, fontSize=9.5, leading=13)
    small = ParagraphStyle("s", fontName=font, fontSize=8, leading=11, textColor=colors.grey)
    summary = plan["summary"]
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm,
                            topMargin=14 * mm, bottomMargin=14 * mm,
                            title="VillageCoverage 계획 요약")
    status = str(summary.get("solver_status"))
    facts = [
        ["지역", plan.get("region_name") or plan.get("region_id")],
        ["계획 버전", f"v{plan.get('plan_version', 1)} · {plan.get('scenario_key')}"],
        ["승인 상태", APPROVAL_LABELS_KO.get(str(plan.get("approval_status")), "-")],
        ["작성일", korean_date(plan.get("created_at"))],
        ["예산", won(plan.get("budget_won"))],
        ["총 비용 (최적화 결과)", won(summary.get("total_cost_won"))],
        ["서비스 단위 / 수요",
         f"{summary.get('served_units')} / {summary.get('total_demand_units')}"],
        ["서비스 권역",
         f"{summary.get('covered_areas')} (미충족 {summary.get('uncovered_areas')})"],
        ["계획 상태", SOLVER_STATUS_KO.get(status, status)],
        ["최소보장 일정 기준 비용", won(summary.get("required_budget_won"))],
    ]
    table = Table([[Paragraph(str(a), body), Paragraph(str(b), body)] for a, b in facts],
                  colWidths=[55 * mm, 120 * mm])
    table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                               ("BACKGROUND", (0, 0), (0, -1), colors.whitesmoke)]))
    unmet = [row for row in explanations if not row["included"]]
    unmet_rows = [[Paragraph(row["area_id"], body), Paragraph("; ".join(row["reasons_ko"]), body),
                   Paragraph(str(row.get("suggested_action") or ""), body)] for row in unmet[:40]]
    story = [
        Paragraph("VillageCoverage 업무용 계획 요약", title),
        Paragraph("공급자 운영조건·수요는 Pre-R&D 모의 데이터를 포함합니다. "
                  "외부 조사 기준값은 마을 실제 수요가 아닙니다.", small),
        Spacer(1, 6 * mm), table, Spacer(1, 6 * mm),
        Paragraph("분배 지표 (기술 지표, 형평성의 정답 아님)", body),
        Paragraph(f"미충족 권역 {fairness.get('coverage_gap_areas')} · 충족률 격차 "
                  f"{fairness.get('max_min_fulfillment_gap')} · 집중도 "
                  f"{fairness.get('allocation_concentration_gini')} · 첫 방문 대기 격차 "
                  f"{fairness.get('waiting_time_disparity_days')}일", body),
        Spacer(1, 5 * mm),
        Paragraph(f"미충족 권역과 사유 ({len(unmet)}곳)", body),
    ]
    if unmet_rows:
        unmet_table = Table([[Paragraph("권역", body), Paragraph("사유", body),
                              Paragraph("권장 조치", body)], *unmet_rows],
                            colWidths=[30 * mm, 80 * mm, 65 * mm], repeatRows=1)
        unmet_table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
                                         ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke)]))
        story.append(unmet_table)
    snapshot = plan.get("data_snapshot") or {}
    public_hash = str(snapshot.get("public_data_fixture_sha256"))[:12]
    route_hash = str(snapshot.get("route_matrix_fingerprint"))[:12]
    story.extend([Spacer(1, 5 * mm),
                  Paragraph(f"입력 스냅샷: 공공데이터 {public_hash} · 경로 {route_hash}", small)])
    doc.build(story)
    return buffer.getvalue()
