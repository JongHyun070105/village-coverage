import json
from datetime import date

import pytest
from fastapi.testclient import TestClient

from backend import database, governance
from backend.main import app
from backend.regions import DEFAULT_REGION_ID

client = TestClient(app)


@pytest.fixture
def plan_id(tmp_path, monkeypatch):
    monkeypatch.setenv("VILLAGECOVERAGE_APP_DB", str(tmp_path / "governance.sqlite"))
    monkeypatch.setattr("backend.main._load_config", lambda _name: "")
    response = client.post("/api/schedules", json={
        "scenario": "balanced", "budget_won": 4_000_000, "region_id": DEFAULT_REGION_ID})
    assert response.status_code == 201, response.text
    return response.json()["schedule_id"]


def approval(schedule_id, action, role):
    return client.post(f"/api/schedules/{schedule_id}/approval",
                       json={"action": action, "role": role})


def test_new_plan_is_draft_bound_to_snapshot_and_audited(plan_id):
    plan = client.get(f"/api/schedules/{plan_id}").json()
    assert plan["approval_status"] == "DRAFT"
    snapshot = plan["data_snapshot"]
    assert len(snapshot["public_data_fixture_sha256"]) == 64
    assert snapshot["route_matrix_fingerprint"]
    events = client.get("/api/audit-events", params={"subject_id": plan_id}).json()["events"]
    assert [event["event_type"] for event in events] == ["PLAN_GENERATED"]


def test_approval_requires_review_and_correct_roles(plan_id):
    assert approval(plan_id, "approve", "REVIEWER").status_code == 409  # not submitted
    assert approval(plan_id, "submit", "REVIEWER").status_code == 409  # wrong role
    assert approval(plan_id, "submit", "PLANNER").json()["approval_status"] == "UNDER_REVIEW"
    assert approval(plan_id, "approve", "PLANNER").status_code == 409  # wrong role
    approved = approval(plan_id, "approve", "REVIEWER").json()
    assert approved["approval_status"] == "APPROVED"
    # Approved plans are immutable: no further transitions.
    assert approval(plan_id, "return", "REVIEWER").status_code == 409
    types = [e["event_type"] for e in client.get(
        "/api/audit-events", params={"subject_id": plan_id}).json()["events"]]
    assert {"PLAN_SUBMITTED_FOR_REVIEW", "PLAN_APPROVED", "PLAN_GENERATED"} <= set(types)


def test_plan_history_includes_current_approval_and_snapshot_state(plan_id):
    history = client.get("/api/schedules", params={"region_id": DEFAULT_REGION_ID}).json()
    row = next(item for item in history["plans"] if item["schedule_id"] == plan_id)
    assert row["approval_status"] == "DRAFT"
    assert row["approved_by_role"] is None
    assert row["data_snapshot"]["route_matrix_fingerprint"]

    approval(plan_id, "submit", "PLANNER")
    history = client.get("/api/schedules", params={"region_id": DEFAULT_REGION_ID}).json()
    row = next(item for item in history["plans"] if item["schedule_id"] == plan_id)
    assert row["approval_status"] == "UNDER_REVIEW"
    assert row["approval_updated_at"]

    approval(plan_id, "approve", "REVIEWER")
    history = client.get("/api/schedules", params={"region_id": DEFAULT_REGION_ID}).json()
    row = next(item for item in history["plans"] if item["schedule_id"] == plan_id)
    assert row["approval_status"] == "APPROVED"
    assert row["approved_by_role"] == "REVIEWER"


def test_reviewer_can_return_plan_to_draft(plan_id):
    approval(plan_id, "submit", "PLANNER")
    assert approval(plan_id, "return", "REVIEWER").json()["approval_status"] == "DRAFT"


def test_approving_new_version_supersedes_previous_approval(plan_id, tmp_path):
    approval(plan_id, "submit", "PLANNER")
    approval(plan_id, "approve", "REVIEWER")
    connection = database.connect()
    try:
        parent = database.get_schedule_plan(connection, plan_id)
        child_id = database.save_schedule_plan(
            connection, scenario="balanced", budget_won=4_000_000,
            plan={**parent["summary"], "rounds": [], "routes": []},
            region_id=parent["region_id"], parent_schedule_id=plan_id,
            change_kind="PROVIDER_REPLAN", change_reason="PROVIDER_FAILURE_OR_DECLINE",
        )
    finally:
        connection.close()
    approval(child_id, "submit", "PLANNER")
    result = approval(child_id, "approve", "REVIEWER").json()
    assert result["superseded_schedule_ids"] == [plan_id]
    assert client.get(f"/api/schedules/{plan_id}").json()["approval_status"] == "SUPERSEDED"


def test_unknown_plan_approval_is_404(plan_id):
    assert approval("missing", "submit", "PLANNER").status_code == 404


def test_explanations_cover_every_area_with_deterministic_reasons(plan_id):
    body = client.get(f"/api/schedules/{plan_id}/explanations").json()
    assert body["method"].startswith("DETERMINISTIC_RULES")
    assert body["areas"]
    for row in body["areas"]:
        assert row["reasons"] and row["reasons_ko"]
        if not row["included"]:
            assert "suggested_action" in row
    assert "정답" in body["fairness"]["note"]


def test_exports_are_csv_safe_and_pdf_is_valid(plan_id):
    budget = client.get(f"/api/schedules/{plan_id}/export/budget.csv")
    assert budget.status_code == 200 and "TOTAL" in budget.text
    unmet = client.get(f"/api/schedules/{plan_id}/export/unmet.csv")
    assert unmet.status_code == 200 and unmet.text.lstrip("﻿").startswith("area_id")
    pdf = client.get(f"/api/schedules/{plan_id}/export/summary.pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")


def test_survey_audit_event_never_stores_free_text(tmp_path, monkeypatch):
    monkeypatch.setenv("VILLAGECOVERAGE_APP_DB", str(tmp_path / "audit-survey.sqlite"))
    demo = json.loads(database.ROOT.joinpath("data", "demo.json").read_text(encoding="utf-8"))
    area_id = demo["areas"][0]["id"]
    secret_note = "홍길동 어르신 010-1234-5678 이불 빨래 필요"
    response = client.post(f"/api/villages/{area_id}/surveys", json={
        "survey_type": "phone", "survey_date": date.today().isoformat(),
        "service_type": "laundry", "frequency_per_month": 2, "free_text_note": secret_note})
    assert response.status_code == 201, response.text
    events = client.get("/api/audit-events", params={"subject_id": area_id}).json()["events"]
    assert events[0]["event_type"] == "SURVEY_CREATED"
    assert "010" not in json.dumps(events, ensure_ascii=False)
    assert "홍길동" not in json.dumps(events, ensure_ascii=False)


def test_policy_presets_are_starting_points_not_answers():
    body = client.get("/api/policy/presets").json()
    assert {p["label"] for p in body["presets"]} == {
        "효율 중심", "균형", "취약지역 우선", "격차 완화", "소외 최소화"
    }
    assert "정답이 아니라" in body["notice"]
    weights = dict(body["balanced_objective_weights"])
    assert weights.pop("underserved") == 4
    assert sum(weights.values()) == 100


def test_fairness_metrics_are_descriptive():
    areas = [{"id": "a", "simulated_monthly_demand": 2}, {"id": "b", "simulated_monthly_demand": 2}]
    rounds = [{"area_id": "a", "scheduled_date": "2026-10-05", "service_units": 2}]
    metrics = governance.fairness_metrics(areas, rounds, month_start=date(2026, 10, 1))
    assert metrics["coverage_gap_areas"] == 1
    assert metrics["max_min_fulfillment_gap"] == 1.0
    assert metrics["allocation_concentration_gini"] == 0.5
    assert metrics["waiting_days_max"] == 4
