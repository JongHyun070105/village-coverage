"""Decision Memo: a print-ready comparison of options for the approving reviewer.

The memo presents 검토안/비교안 and flags 추가재원 검토 필요 and 정책 선택 필요 items. It never
names a "recommended" option: choosing among options is the planner's and reviewer's decision.
"""

from __future__ import annotations

import html
import io
from typing import Any

from backend import cost_model_v3
from backend.exports import SOLVER_STATUS_KO, korean_date, won
from backend.governance import APPROVAL_LABELS_KO

MEMO_VERSION = "DECISION_MEMO_V1"
EVIDENCE_LEGEND = (
    ("PUBLIC DATA", "공공데이터 원자료"),
    ("EXTERNAL EMPIRICAL", "외부 실증 기준값(해당 마을의 실제 수요가 아님)"),
    ("LOCAL OBSERVATION", "현장 조사·주민 의견 등 지역 관측"),
    ("MODEL ESTIMATE", "모형 추정 결과"),
    ("SIMULATION", "모의 자료(공급자 운영조건 등)"),
)
LIMITS_KO = (
    "이 메모는 의사결정 지원 자료이며 최종 판단은 담당자와 검토자가 합니다.",
    "공급자 가용성·용량·가격은 모의 자료입니다. 계약·실사로 확인되기 전에는 확정값이 아닙니다.",
    "알 수 없는 비용·재원은 0원으로 처리하지 않고 '알 수 없음'으로 표시합니다.",
    "시범 검토용이며 운영 수준의 검증을 마친 시스템이 아닙니다.",
)
POLICY_CHOICES_KO = (
    "정책 선택 필요: 계획 시나리오(효율/균형/최소보장/소외 우선)는 담당자가 선택합니다.",
    "정책 선택 필요: 예비 재원 비율(0/5/10/15%)은 담당자가 선택하며 AI가 정하지 않습니다.",
    "정책 선택 필요: 조사 필요 마을과 서비스 미배정 마을의 처리 방식은 검토자가 판단합니다.",
)


def _option_row(label: str, plan: dict[str, Any], uncovered: int) -> dict[str, Any]:
    summary = plan["summary"]
    status = str(summary.get("solver_status"))
    return {
        "label": label,
        "schedule_id": plan["schedule_id"],
        "plan_version": plan.get("plan_version"),
        "scenario": plan.get("scenario_key"),
        "budget_won": plan.get("budget_won"),
        "total_cost_won": summary.get("total_cost_won"),
        "served_units": summary.get("served_units"),
        "total_demand_units": summary.get("total_demand_units"),
        "covered_areas": summary.get("covered_areas"),
        "zero_service_areas": uncovered,
        "solver_status": status,
        "solver_status_ko": SOLVER_STATUS_KO.get(status, status),
    }


def build_memo(
    plan: dict[str, Any],
    explanations: list[dict[str, Any]],
    fairness: dict[str, Any],
    *,
    areas: list[dict[str, Any]],
    audit_events: list[dict[str, Any]],
    alternatives: list[tuple[dict[str, Any], list[dict[str, Any]]]] | None = None,
    attention: dict[str, int] | None = None,
    cost_assumptions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    unmet = [row for row in explanations if not row["included"]]
    model = cost_model_v3.plan_cost_model(plan["rounds"], cost_assumptions)
    gap = cost_model_v3.funding_gap(model, budget_won=int(plan["budget_won"]))
    options = [_option_row("검토안", plan, len(unmet))]
    for alt_plan, alt_explanations in alternatives or []:
        options.append(
            _option_row("비교안", alt_plan, sum(1 for r in alt_explanations if not r["included"]))
        )
    money_unmet = [row["area_id"] for row in unmet if row.get("money_resolvable")]
    extra_funding_items = []
    if gap["status"] == "EXACT" and gap["gap_won"]:
        extra_funding_items.append(f"계산된 재원 부족액 {won(gap['gap_won'])}")
    if gap["gap_at_least_won"]:
        extra_funding_items.append(f"확인된 비용만으로도 최소 {won(gap['gap_at_least_won'])} 부족")
    if money_unmet:
        extra_funding_items.append(f"예산으로 해소 가능한 서비스 미배정 마을 {len(money_unmet)}곳")
    summary = plan["summary"]
    if (summary.get("budget_gap_won") or 0) > 0:
        extra_funding_items.append(
            f"최소보장 일정 기준 예산 격차 {won(summary['budget_gap_won'])}"
        )
    survey_needed = [str(a["id"]) for a in areas if a.get("needs_survey")]
    snapshot = plan.get("data_snapshot") or {}
    return {
        "memo_version": MEMO_VERSION,
        "title": "의사결정 메모 (검토용)",
        "schedule_id": plan["schedule_id"],
        "plan_version": plan.get("plan_version"),
        "region": plan.get("region_name") or plan.get("region_id"),
        "created_at": plan.get("created_at"),
        "approval_status": plan.get("approval_effective_status") or plan.get("approval_status"),
        "approval_label": APPROVAL_LABELS_KO.get(
            str(plan.get("approval_effective_status") or plan.get("approval_status")), "-"
        ),
        "options": options,
        "funding": {
            "cost_components": model["components"],
            "known_cost_floor_won": model["known_cost_floor_won"],
            "cost_status": model["cost_status"],
            "gap": gap,
            "extra_funding_review_needed": bool(extra_funding_items),
            "extra_funding_items": extra_funding_items,
            "label": "추가재원 검토 필요" if extra_funding_items else "추가재원 검토 항목 없음",
        },
        "policy_choices": list(POLICY_CHOICES_KO),
        "zero_service_areas": [
            {
                "area_id": row["area_id"],
                "reasons_ko": row["reasons_ko"],
                "review_action": row.get("suggested_action", ""),
                "money_resolvable": row.get("money_resolvable"),
            }
            for row in unmet
        ],
        "survey_needed_area_ids": survey_needed,
        "fairness": {
            key: fairness.get(key)
            for key in ("coverage_gap_areas", "max_min_fulfillment_gap",
                        "allocation_concentration_gini", "waiting_time_disparity_days")
        },
        "attention": attention or {},
        "approval_trail": [
            {"event_type": e["event_type"], "actor_role": e["actor_role"],
             "occurred_at": e["occurred_at"]}
            for e in audit_events
        ],
        "input_snapshot": {
            "public_data_sha256": str(snapshot.get("public_data_fixture_sha256") or "")[:12],
            "route_matrix": str(snapshot.get("route_matrix_fingerprint") or "")[:12],
        },
        "evidence_legend": [{"label": k, "meaning": v} for k, v in EVIDENCE_LEGEND],
        "limits": list(LIMITS_KO),
        "provenance": "OPTIMIZATION RESULT; MODEL ESTIMATE; SIMULATION (PROVIDER OPERATIONS)",
    }


def _esc(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def _gap_text(gap: dict[str, Any]) -> str:
    status = gap["status"]
    if status == "EXACT":
        return f"재원 격차 {won(gap['gap_won'])}"
    if status == "LOWER_BOUND_UNKNOWN_COSTS":
        return (
            "알 수 없는 비용이 있어 격차는 최소 "
            f"{won(gap['gap_at_least_won'])} 이상으로만 표시"
        )
    if status == "UPPER_BOUND_UNKNOWN_FUNDING":
        return (
            "알 수 없는 재원이 있어 격차는 최대 "
            f"{won(gap['gap_at_most_won'])} 이하로만 표시"
        )
    return "비용과 재원 모두 일부 알 수 없어 격차 범위를 계산할 수 없음"


def render_html(memo: dict[str, Any]) -> str:
    def table(header: list[str], rows: list[list[Any]]) -> str:
        head = "".join(f"<th scope=\"col\">{_esc(h)}</th>" for h in header)
        body = "".join(
            "<tr>" + "".join(f"<td>{_esc(c)}</td>" for c in row) + "</tr>" for row in rows
        )
        return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"

    funding = memo["funding"]
    gap = funding["gap"]
    options = table(
        ["구분", "시나리오", "예산", "총 비용", "서비스 단위/수요", "서비스 미배정", "계획 상태"],
        [[o["label"], o["scenario"], won(o["budget_won"]), won(o["total_cost_won"]),
          f"{o['served_units']}/{o['total_demand_units']}", o["zero_service_areas"],
          o["solver_status_ko"]] for o in memo["options"]],
    )
    components = table(
        ["항목", "금액", "출처"],
        [[c["label"], "알 수 없음" if c["amount_won"] == "UNKNOWN" else won(c["amount_won"]),
          c["provenance"]] for c in funding["cost_components"]],
    )
    gap_text = _gap_text(gap)
    unserved = table(
        ["마을", "사유", "검토 조치", "예산으로 해소 가능"],
        [[r["area_id"], "; ".join(r["reasons_ko"]), r["review_action"],
          {True: "예", False: "아니오"}.get(r["money_resolvable"], "-")]
         for r in memo["zero_service_areas"]],
    ) if memo["zero_service_areas"] else "<p>현재 계획에서 서비스 미배정 마을이 없습니다.</p>"
    trail = table(
        ["일시", "이벤트", "역할"],
        [[e["occurred_at"], e["event_type"], e["actor_role"]] for e in memo["approval_trail"]],
    ) if memo["approval_trail"] else "<p>기록된 승인 이력이 없습니다.</p>"
    attention = memo["attention"]
    attention_text = (
        f"신규 주민 의견 {attention.get('new_feedback', 0)}건 · 검토 중 "
        f"{attention.get('in_review_feedback', 0)}건 · 근거 충돌 "
        f"{attention.get('open_conflicts', 0)}건" if attention else "집계 없음"
    )
    items = "".join(f"<li>{_esc(i)}</li>" for i in funding["extra_funding_items"])
    legend = "".join(
        f"<li><strong>{_esc(e['label'])}</strong> {_esc(e['meaning'])}</li>"
        for e in memo["evidence_legend"]
    )
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<title>{_esc(memo['title'])} - {_esc(memo['schedule_id'])}</title>
<style>
body{{font-family:'Apple SD Gothic Neo','Malgun Gothic',sans-serif;max-width:900px;
margin:24px auto;padding:0 16px;color:#111;line-height:1.5}}
table{{border-collapse:collapse;width:100%;margin:8px 0}}
th,td{{border:1px solid #666;padding:4px 8px;text-align:left;font-size:13px}}
th{{background:#eee}}
.status{{border:2px solid #111;padding:6px 10px;display:inline-block}}
@media print{{body{{margin:0;max-width:none}}section{{break-inside:avoid}}}}
</style></head><body>
<h1>{_esc(memo['title'])}</h1>
<p class="status">상태: {_esc(memo['approval_label'])} ({_esc(memo['approval_status'])})</p>
<p>지역 {_esc(memo['region'])} · 계획 v{_esc(memo['plan_version'])} ·
작성일 {_esc(korean_date(memo['created_at']))} · 계획 {_esc(memo['schedule_id'])}</p>
<section><h2>1. 검토안과 비교안</h2>{options}</section>
<section><h2>2. 비용과 재원 [MODEL ESTIMATE]</h2>{components}
<p>확인된 비용 합계(하한): {_esc(won(funding['known_cost_floor_won']))}</p>
<p><strong>{_esc(funding['label'])}</strong> — {_esc(gap_text)}</p><ul>{items}</ul></section>
<section><h2>3. 정책 선택 필요</h2><ul>
{''.join(f'<li>{_esc(c)}</li>' for c in memo['policy_choices'])}</ul></section>
<section><h2>4. 현재 계획에서 서비스 미배정 마을</h2>{unserved}
<p>조사 필요 마을: {_esc(', '.join(memo['survey_needed_area_ids']) or '없음')}</p>
<p>검토 대기: {_esc(attention_text)}</p></section>
<section><h2>5. 승인 이력 (데모 역할)</h2>{trail}</section>
<section><h2>6. 근거 표기와 한계</h2><ul>{legend}</ul>
<ul>{''.join(f'<li>{_esc(t)}</li>' for t in memo['limits'])}</ul>
<p>입력 스냅샷: 공공데이터 {_esc(memo['input_snapshot']['public_data_sha256'])} ·
경로 {_esc(memo['input_snapshot']['route_matrix'])}</p></section>
</body></html>"""


def render_pdf(memo: dict[str, Any]) -> bytes:
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
    head = ParagraphStyle("h", fontName=font, fontSize=11, leading=15)
    body = ParagraphStyle("b", fontName=font, fontSize=9, leading=12)

    def p(text: Any, style: ParagraphStyle = body) -> Paragraph:
        return Paragraph(html.escape(str(text)), style)

    def grid(rows: list[list[Any]], widths: list[float]) -> Table:
        table = Table([[p(c) for c in row] for row in rows], colWidths=widths, repeatRows=1)
        table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
                                   ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke)]))
        return table

    funding = memo["funding"]
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm,
                            topMargin=14 * mm, bottomMargin=14 * mm, title=memo["title"])
    story: list[Any] = [
        p(memo["title"], title),
        p(f"상태: {memo['approval_label']} · 지역 {memo['region']} · 계획 v{memo['plan_version']}"),
        Spacer(1, 4 * mm),
        p("1. 검토안과 비교안", head),
        grid([["구분", "시나리오", "총 비용", "서비스 단위/수요", "서비스 미배정"],
              *[[o["label"], o["scenario"], won(o["total_cost_won"]),
                 f"{o['served_units']}/{o['total_demand_units']}", o["zero_service_areas"]]
                for o in memo["options"]]], [22 * mm, 40 * mm, 40 * mm, 40 * mm, 32 * mm]),
        Spacer(1, 4 * mm),
        p("2. 비용과 재원 [MODEL ESTIMATE]", head),
        grid([["항목", "금액"],
              *[[c["label"], "알 수 없음" if c["amount_won"] == "UNKNOWN" else won(c["amount_won"])]
                for c in funding["cost_components"]]], [90 * mm, 70 * mm]),
        p(f"{funding['label']} · 확인된 비용 하한 {won(funding['known_cost_floor_won'])}"),
        *[p(f"- {item}") for item in funding["extra_funding_items"]],
        Spacer(1, 4 * mm),
        p("3. 정책 선택 필요", head),
        *[p(f"- {c}") for c in memo["policy_choices"]],
        Spacer(1, 4 * mm),
        p(f"4. 현재 계획에서 서비스 미배정 마을 ({len(memo['zero_service_areas'])}곳)", head),
    ]
    if memo["zero_service_areas"]:
        story.append(grid([["마을", "사유", "검토 조치"],
                           *[[r["area_id"], "; ".join(r["reasons_ko"]), r["review_action"]]
                             for r in memo["zero_service_areas"][:40]]],
                          [30 * mm, 80 * mm, 55 * mm]))
    story.extend([Spacer(1, 4 * mm), p("5. 근거 표기와 한계", head),
                  *[p(f"[{e['label']}] {e['meaning']}") for e in memo["evidence_legend"]],
                  *[p(f"- {t}") for t in memo["limits"]]])
    doc.build(story)
    return buffer.getvalue()
