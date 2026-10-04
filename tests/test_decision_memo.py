import json

import pytest
from fastapi.testclient import TestClient

from backend import decision_memo
from backend.main import app
from backend.regions import DEFAULT_REGION_ID

client = TestClient(app)
FORBIDDEN = ("권고", "추천", "recommend")


@pytest.fixture
def plans(tmp_path, monkeypatch):
    monkeypatch.setenv("VILLAGECOVERAGE_APP_DB", str(tmp_path / "memo.sqlite"))
    monkeypatch.setattr("backend.main._load_config", lambda _name: "")
    ids = []
    for scenario in ("balanced", "efficiency"):
        response = client.post("/api/schedules", json={
            "scenario": scenario, "budget_won": 4_000_000, "region_id": DEFAULT_REGION_ID})
        assert response.status_code == 201, response.text
        ids.append(response.json()["schedule_id"])
    return ids


def test_memo_json_structure_and_wording(plans):
    first, second = plans
    memo = client.get(f"/api/schedules/{first}/decision-memo",
                      params={"compare_with": [second]}).json()
    assert [o["label"] for o in memo["options"]] == ["검토안", "비교안"]
    assert memo["approval_status"] == "DRAFT"
    assert memo["funding"]["label"] in {"추가재원 검토 필요", "추가재원 검토 항목 없음"}
    assert any(c.startswith("정책 선택 필요") for c in memo["policy_choices"])
    assert {e["label"] for e in memo["evidence_legend"]} == {
        "PUBLIC DATA", "EXTERNAL EMPIRICAL", "LOCAL OBSERVATION", "MODEL ESTIMATE", "SIMULATION"}
    text = json.dumps(memo, ensure_ascii=False)
    assert not any(word in text for word in FORBIDDEN)
    assert "위험" not in json.dumps(memo["zero_service_areas"], ensure_ascii=False)


def test_unknown_costs_are_not_rendered_as_zero(plans):
    memo = client.get(f"/api/schedules/{plans[0]}/decision-memo").json()
    amounts = {c["component"]: c["amount_won"] for c in memo["funding"]["cost_components"]}
    assert amounts["MATERIAL"] == "UNKNOWN"
    assert memo["funding"]["gap"]["gap_won"] is None
    html_text = client.get(f"/api/schedules/{plans[0]}/decision-memo.html").text
    assert "알 수 없음" in html_text


def test_html_is_print_ready_escaped_and_pdf_renders(plans):
    html_response = client.get(f"/api/schedules/{plans[0]}/decision-memo.html")
    assert html_response.headers["content-type"].startswith("text/html")
    assert "@media print" in html_response.text and "<h1>의사결정 메모" in html_response.text
    assert not any(word in html_response.text for word in FORBIDDEN)
    pdf = client.get(f"/api/schedules/{plans[0]}/decision-memo.pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")


def test_html_escapes_untrusted_text() -> None:
    memo = {"title": "t", "schedule_id": "<script>alert(1)</script>", "plan_version": 1,
            "region": "<b>x</b>", "created_at": "2026-06-01", "approval_status": "DRAFT",
            "approval_label": "초안", "options": [], "funding": {
                "cost_components": [], "known_cost_floor_won": 0, "label": "x",
                "extra_funding_items": [],
                "gap": {"status": "UNKNOWN_BOTH_SIDES"}},
            "policy_choices": [], "zero_service_areas": [], "survey_needed_area_ids": [],
            "attention": {}, "approval_trail": [], "evidence_legend": [], "limits": [],
            "input_snapshot": {"public_data_sha256": "", "route_matrix": ""}}
    rendered = decision_memo.render_html(memo)
    assert "<script>" not in rendered and "&lt;script&gt;" in rendered


def test_memo_status_follows_approval_and_audit_trail(plans):
    plan_id = plans[0]
    client.post(f"/api/schedules/{plan_id}/approval", json={"action": "submit",
                                                            "role": "PLANNER"})
    client.post(f"/api/schedules/{plan_id}/approval", json={
        "action": "request_changes", "role": "REVIEWER", "comment": "재원 확인"})
    memo = client.get(f"/api/schedules/{plan_id}/decision-memo").json()
    assert memo["approval_status"] == "CHANGES_REQUESTED"
    assert memo["approval_label"] == "수정 요청"
    kinds = [e["event_type"] for e in memo["approval_trail"]]
    assert kinds.index("PLAN_SUBMITTED_FOR_REVIEW") < kinds.index("PLAN_CHANGES_REQUESTED")
    assert "재원 확인" not in json.dumps(memo, ensure_ascii=False)


def test_requested_changes_create_a_new_plan_version(plans):
    original_id = plans[0]
    client.post(f"/api/schedules/{original_id}/approval", json={
        "action": "submit", "role": "PLANNER"})
    response = client.post(f"/api/schedules/{original_id}/approval", json={
        "action": "request_changes", "role": "REVIEWER", "comment": "예산 검토"})
    assert response.status_code == 200
    original = client.get(f"/api/schedules/{original_id}").json()
    revised_response = client.post(f"/api/schedules/{original_id}/revision", json={
        "scenario": original["scenario_key"],
        "budget_won": original["budget_won"] - 100_000,
        "planning_policy": original["planning_policy"],
        "region_id": original["region_id"],
    })
    assert revised_response.status_code == 201, revised_response.text
    revised = revised_response.json()
    assert revised["parent_schedule_id"] == original_id
    assert revised["plan_version"] == original["plan_version"] + 1
    assert revised["change_kind"] == "REVISION_AFTER_CHANGES_REQUESTED"
    assert revised["change_reason"] == "REVIEWER_REQUESTED_CHANGES"
    final_original = client.get(f"/api/schedules/{original_id}").json()
    assert final_original["approval_effective_status"] == "CHANGES_REQUESTED"


def test_compare_with_other_region_or_missing_plan_rejected(plans):
    assert client.get(f"/api/schedules/{plans[0]}/decision-memo",
                      params={"compare_with": ["missing"]}).status_code == 404
    assert client.get("/api/schedules/missing/decision-memo").status_code == 404
    too_many = client.get(f"/api/schedules/{plans[0]}/decision-memo",
                          params={"compare_with": ["a", "b", "c", "d"]})
    assert too_many.status_code == 422
