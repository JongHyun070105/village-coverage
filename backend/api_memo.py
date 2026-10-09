"""Decision Memo API: JSON, print-ready HTML and PDF."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, Request, Response

from backend import database, decision_memo, governance, resident_feedback

router = APIRouter(prefix="/api")


def _memo(schedule_id: str, compare_with: list[str], request: Request) -> dict[str, Any]:
    from backend import main

    plan, areas = main._plan_with_areas(schedule_id, request)
    merged = {**plan["summary"], "rounds": plan["rounds"]}
    explanations = governance.area_explanations(merged, areas)
    alternatives = []
    for other_id in dict.fromkeys(compare_with):
        if other_id == schedule_id:
            continue
        other, other_areas = main._plan_with_areas(other_id, request)
        if other["region_id"] != plan["region_id"]:
            raise HTTPException(status_code=422, detail="같은 지역의 계획만 비교할 수 있습니다.")
        other_merged = {**other["summary"], "rounds": other["rounds"]}
        alternatives.append((other, governance.area_explanations(other_merged, other_areas)))
    connection = database.connect()
    try:
        events = governance.list_audit_events(connection, subject_id=schedule_id, limit=50)
        attention = resident_feedback.attention_counts(connection, plan["region_id"])
    finally:
        connection.close()
    return decision_memo.build_memo(
        plan, explanations, governance.fairness_metrics(areas, plan["rounds"]),
        areas=areas, audit_events=list(reversed(events)),
        alternatives=alternatives, attention=attention,
    )


CompareWith = Annotated[list[str], Query(max_length=3)]


@router.get("/schedules/{schedule_id}/decision-memo")
def decision_memo_json(
    schedule_id: str, request: Request, compare_with: CompareWith = []  # noqa: B006
) -> dict[str, Any]:  # noqa: B006
    return _memo(schedule_id, compare_with, request)


@router.get("/schedules/{schedule_id}/decision-memo.html")
def decision_memo_html(
    schedule_id: str, request: Request, compare_with: CompareWith = []  # noqa: B006
) -> Response:  # noqa: B006
    html_text = decision_memo.render_html(_memo(schedule_id, compare_with, request))
    return Response(html_text, media_type="text/html; charset=utf-8")


@router.get("/schedules/{schedule_id}/decision-memo.pdf")
def decision_memo_pdf(
    schedule_id: str, request: Request, compare_with: CompareWith = []  # noqa: B006
) -> Response:  # noqa: B006
    pdf = decision_memo.render_pdf(_memo(schedule_id, compare_with, request))
    return Response(
        pdf, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="decision-memo-{schedule_id}.pdf"'},
    )
