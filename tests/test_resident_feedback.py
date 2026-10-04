from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import database, resident_feedback
from backend.errors import AppError
from backend.evidence_source_policy import bounded_observation_contribution
from backend.main import app
from backend.timeutils import korea_today

ROOT = Path(__file__).resolve().parents[1]
DEMO = json.loads((ROOT / "data" / "demo.json").read_text(encoding="utf-8"))
AREA_ID = str(DEMO["areas"][0]["id"])


@pytest.fixture
def conn(tmp_path):
    connection = database.connect(tmp_path / "feedback.sqlite")
    database.seed_reference_data(connection, DEMO)
    yield connection
    connection.close()


def _payload(description: str = "세탁 서비스가 필요합니다", **overrides):
    payload = {
        "area_id": AREA_ID,
        "service_type": "laundry",
        "feedback_type": "SERVICE_REQUEST",
        "description": description,
        "claim": {"claims_demand": True},
    }
    payload.update(overrides)
    return payload


def _to_review(conn, feedback_id):
    return resident_feedback.transition_feedback(conn, feedback_id, "start_review", "PLANNER")


def _accept(conn, feedback_id, role="REVIEWER"):
    return resident_feedback.transition_feedback(
        conn, feedback_id, "accept", role, "현장 확인 필요한 주장으로 채택"
    )


def _insert_survey(conn, *, frequency: int | None, structured: dict | None = None):
    conn.execute(
        """INSERT INTO surveys(survey_id, area_id, survey_type, survey_date, service_type,
               frequency_per_month, preferred_period, preferred_days_json, constraints_json,
               free_text_note, source_text_was_redacted, provenance, created_at,
               structured_data_json)
           VALUES (?,?,?,?,?,?,NULL,'[]','[]','',0,'TEST',?,?)""",
        (f"sv-{frequency}-{json.dumps(structured)}", AREA_ID, "phone",
         korea_today().isoformat(), "laundry", frequency,
         "2026-01-01T00:00:00+00:00", json.dumps(structured or {})),
    )
    conn.commit()


def _region(conn) -> str:
    return str(conn.execute(
        "SELECT region_id FROM village_service_areas WHERE area_id=?", (AREA_ID,)
    ).fetchone()[0])


def _insert_plan(conn, schedule_id="sched-test", status="APPROVED") -> str:
    conn.execute(
        """INSERT INTO schedule_runs(schedule_id, scenario_key, budget_won, summary_json,
               provenance, created_at, region_id, lineage_root_id, approval_status)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (schedule_id, "balanced", 1000, "{}", "TEST", "2026-01-01T00:00:00+00:00",
         _region(conn), schedule_id, status),
    )
    conn.commit()
    return schedule_id


def test_submit_redacts_pii_and_keeps_contact_separate(conn) -> None:
    result = resident_feedback.submit_feedback(
        conn,
        _payload("연락은 010-1234-5678 로 주세요. 김영희님 댁입니다.", contact="010-1234-5678"),
    )
    assert result["status"] == "SUBMITTED"
    assert "010-1234-5678" not in result["description"]
    assert result["description_was_redacted"] is True
    assert result["has_contact"] is True
    assert "contact_text" not in json.dumps(result)
    assert resident_feedback.get_contact(conn, result["feedback_id"]) == "010-1234-5678"
    listed = resident_feedback.list_feedback(conn)
    exported = resident_feedback.export_feedback_rows(conn)
    for rows in (listed, exported):
        assert "010-1234-5678" not in json.dumps(rows, ensure_ascii=False)
    assert "has_contact" not in exported[0] and "reviewer_id" not in exported[0]


def test_audit_events_never_contain_feedback_text(conn) -> None:
    text = "마을회관 앞 정류장이 너무 멀어요 특별한문장"
    result = resident_feedback.submit_feedback(conn, _payload(text))
    _to_review(conn, result["feedback_id"])
    dump = json.dumps([dict(row) for row in conn.execute("SELECT * FROM audit_events")],
                      ensure_ascii=False)
    assert "특별한문장" not in dump
    assert "FEEDBACK_SUBMITTED" in dump and "FEEDBACK_REVIEW_STARTED" in dump


def test_state_machine_rejects_skips_and_requires_notes(conn) -> None:
    fid = resident_feedback.submit_feedback(conn, _payload())["feedback_id"]
    with pytest.raises(AppError) as skipped:
        _accept(conn, fid)
    assert skipped.value.code == "REVIEW_REQUIRED"
    _to_review(conn, fid)
    with pytest.raises(AppError) as no_note:
        resident_feedback.transition_feedback(conn, fid, "reject", "PLANNER")
    assert no_note.value.code == "VALIDATION_ERROR"
    rejected = resident_feedback.transition_feedback(conn, fid, "reject", "PLANNER", "중복 접수")
    assert rejected["status"] == "REJECTED"
    with pytest.raises(AppError):
        _to_review(conn, fid)


def test_feedback_does_not_touch_demand_tables_or_plans(conn) -> None:
    plan_id = _insert_plan(conn, status="DRAFT")
    tables = ("demand_observations", "demand_evidence", "surveys", "demand_assessments")
    existing = {
        t for t in tables
        if conn.execute("SELECT 1 FROM sqlite_master WHERE name=?", (t,)).fetchone()
    }
    before = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in existing}
    fid = resident_feedback.submit_feedback(conn, _payload())["feedback_id"]
    _to_review(conn, fid)
    assert resident_feedback.get_feedback(conn, fid)["status"] == "UNDER_REVIEW"
    after = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in existing}
    assert before == after
    assert conn.execute(
        "SELECT stale_since FROM schedule_runs WHERE schedule_id=?", (plan_id,)
    ).fetchone()[0] is None
    _accept(conn, fid)
    after_accept = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in existing}
    assert before == after_accept


def test_accept_creates_unverified_claim_and_marks_plans_stale_without_mutating_them(conn) -> None:
    plan_id = _insert_plan(conn, status="APPROVED")
    fid = resident_feedback.submit_feedback(conn, _payload())["feedback_id"]
    _to_review(conn, fid)
    accepted = _accept(conn, fid)
    assert accepted["status"] == "ACCEPTED_AS_EVIDENCE"
    assert accepted["stale_plan_ids"] == [plan_id]
    row = conn.execute(
        "SELECT verification_state, source_type FROM resident_claim_evidence WHERE feedback_id=?",
        (fid,),
    ).fetchone()
    assert tuple(row) == ("UNVERIFIED_CLAIM", "RESIDENT_FEEDBACK")
    plan = conn.execute(
        "SELECT approval_status, stale_since, stale_reason, summary_json FROM schedule_runs"
        " WHERE schedule_id=?", (plan_id,)).fetchone()
    assert plan["approval_status"] == "APPROVED"
    assert plan["stale_since"] and plan["stale_reason"] == "RESIDENT_EVIDENCE_ACCEPTED"
    assert plan["summary_json"] == "{}"
    with pytest.raises(sqlite3.DatabaseError, match="APPROVED_PLAN_IMMUTABLE"):
        conn.execute("UPDATE schedule_runs SET budget_won=1 WHERE schedule_id=?", (plan_id,))
    types = [r[0] for r in conn.execute("SELECT event_type FROM audit_events")]
    assert "PLAN_MARKED_STALE" in types and "FEEDBACK_ACCEPTED" in types


def test_regulated_service_feedback_cannot_become_evidence(conn) -> None:
    fid = resident_feedback.submit_feedback(
        conn, _payload("주사를 놓아 주세요", service_type="medical_service")
    )["feedback_id"]
    _to_review(conn, fid)
    with pytest.raises(AppError) as exc:
        _accept(conn, fid)
    assert exc.value.code == "REGULATED_SERVICE"
    assert conn.execute("SELECT COUNT(*) FROM resident_claim_evidence").fetchone()[0] == 0


def test_feedback_without_service_type_cannot_be_evidence(conn) -> None:
    fid = resident_feedback.submit_feedback(
        conn, _payload(service_type=None, claim=None)
    )["feedback_id"]
    _to_review(conn, fid)
    with pytest.raises(AppError) as exc:
        _accept(conn, fid)
    assert exc.value.code == "VALIDATION_ERROR"


def test_frequency_conflict_blocks_accept_until_resolved(conn) -> None:
    _insert_survey(conn, frequency=2)
    result = resident_feedback.submit_feedback(
        conn, _payload("한 달에 열 번은 필요해요", claim={"claimed_frequency_per_month": 10})
    )
    assert [c["conflict_type"] for c in result["conflicts"]] == [
        "RESIDENT_CLAIM_VS_SURVEY_FREQUENCY"
    ]
    assert result["conflicts"][0]["official"]["frequency_per_month"] == 2
    fid = result["feedback_id"]
    _to_review(conn, fid)
    with pytest.raises(AppError) as blocked:
        _accept(conn, fid)
    assert blocked.value.code == "FEEDBACK_CONFLICT"
    resolved = resident_feedback.resolve_conflict(
        conn, result["conflicts"][0]["conflict_id"], "ACCEPT_AS_RANGE", "REVIEWER",
        "공식 조사와 범위로 병기"
    )
    assert resolved["status"] == "RESOLVED"
    assert _accept(conn, fid)["status"] == "ACCEPTED_AS_EVIDENCE"
    survey = conn.execute(
        "SELECT frequency_per_month FROM surveys WHERE area_id=?", (AREA_ID,)
    ).fetchone()
    assert survey[0] == 2


def test_keep_official_resolution_rejects_feedback_and_further_survey_requests_info(conn) -> None:
    _insert_survey(conn, frequency=1, structured={"demand_status": "NO_DEMAND"})
    first = resident_feedback.submit_feedback(conn, _payload("정말 필요한 서비스입니다 첫번째"))
    types = {c["conflict_type"] for c in first["conflicts"]}
    assert types == {"RESIDENT_CLAIM_VS_NO_OFFICIAL_DEMAND"}
    resident_feedback.resolve_conflict(
        conn, first["conflicts"][0]["conflict_id"], "KEEP_OFFICIAL_EVIDENCE", "PLANNER",
        "조사 결과 유지"
    )
    assert resident_feedback.get_feedback(conn, first["feedback_id"])["status"] == "REJECTED"
    second = resident_feedback.submit_feedback(conn, _payload("다른 마을 사정이 있어요 두번째"))
    resident_feedback.resolve_conflict(
        conn, second["conflicts"][0]["conflict_id"], "FURTHER_SURVEY", "PLANNER", "재조사"
    )
    assert resident_feedback.get_feedback(conn, second["feedback_id"])["status"] == (
        "NEEDS_MORE_INFO"
    )
    with pytest.raises(AppError):
        resident_feedback.resolve_conflict(
            conn, second["conflicts"][0]["conflict_id"], "FURTHER_SURVEY", "PLANNER", "재조사"
        )


def test_exact_duplicate_is_refused_and_near_duplicate_is_never_auto_merged(conn) -> None:
    first = resident_feedback.submit_feedback(conn, _payload("세탁 서비스가 매주 필요합니다"))
    with pytest.raises(AppError) as exact:
        resident_feedback.submit_feedback(conn, _payload("세탁  서비스가 매주 필요합니다 "))
    assert exact.value.code == "FEEDBACK_DUPLICATE"
    assert exact.value.details["existing_feedback_id"] == first["feedback_id"]
    near = resident_feedback.submit_feedback(conn, _payload("세탁 서비스가 매주 정말 필요합니다"))
    candidates = near["duplicate_candidates"]
    assert [c["feedback_id"] for c in candidates] == [first["feedback_id"]]
    assert candidates[0]["decision"] == "UNREVIEWED"
    assert resident_feedback.get_feedback(conn, near["feedback_id"])["status"] == "SUBMITTED"
    resident_feedback.decide_duplicate(
        conn, near["feedback_id"], first["feedback_id"], "CONFIRMED_DISTINCT", "PLANNER",
        "다른 가구"
    )
    decided = resident_feedback.get_feedback(conn, near["feedback_id"])["duplicate_candidates"]
    assert decided[0]["decision"] == "CONFIRMED_DISTINCT"
    assert conn.execute("SELECT COUNT(*) FROM resident_feedback").fetchone()[0] == 2


def test_flood_of_100_submissions_is_capped_and_changes_nothing_else(conn) -> None:
    plan_id = _insert_plan(conn, status="DRAFT")
    accepted = limited = 0
    for index in range(100):
        try:
            resident_feedback.submit_feedback(
                conn, _payload(f"고유한 의견 번호 {index} 알파{index * 7919}")
            )
            accepted += 1
        except AppError as exc:
            assert exc.code == "FEEDBACK_RATE_LIMITED" and exc.status_code == 429
            limited += 1
    assert accepted == resident_feedback.FEEDBACK_AREA_DAILY_LIMIT
    assert limited == 100 - accepted
    assert conn.execute(
        "SELECT stale_since FROM schedule_runs WHERE schedule_id=?", (plan_id,)
    ).fetchone()[0] is None
    signal = resident_feedback.area_feedback_signal(conn, AREA_ID)
    assert signal["accepted_claim_count"] == 0 and signal["bounded_observation_contribution"] == 0
    assert signal["needs_survey"] is True


def test_many_accepted_claims_add_at_most_one_observation_and_are_never_calibrated(conn) -> None:
    for index in range(20):
        fid = resident_feedback.submit_feedback(
            conn, _payload(f"서로 다른 요청 {index} 베타{index * 104729}")
        )["feedback_id"]
        _to_review(conn, fid)
        _accept(conn, fid)
    signal = resident_feedback.area_feedback_signal(conn, AREA_ID, "laundry")
    assert signal["accepted_claim_count"] == 20
    assert signal["unverified_claim_count"] == 20
    assert signal["bounded_observation_contribution"] == 1
    assert signal["calibrated"] is False and signal["evidence_grade"] == "UNVERIFIED_CLAIM"
    assert bounded_observation_contribution("RESIDENT_FEEDBACK", 20) == 1
    assert bounded_observation_contribution("SURVEY", 20) == 20


def test_later_official_survey_verifies_the_claim(conn) -> None:
    fid = resident_feedback.submit_feedback(conn, _payload())["feedback_id"]
    _to_review(conn, fid)
    _accept(conn, fid)
    assert resident_feedback.area_feedback_signal(conn, AREA_ID)["unverified_claim_count"] == 1
    _insert_survey(conn, frequency=4)
    signal = resident_feedback.area_feedback_signal(conn, AREA_ID)
    assert signal["unverified_claim_count"] == 0
    assert signal["bounded_observation_contribution"] == 0


def test_api_workflow_keeps_assessment_demand_fixed(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("VILLAGECOVERAGE_APP_DB", str(tmp_path / "api-feedback.sqlite"))
    client = TestClient(app)
    before = client.get(f"/api/villages/{AREA_ID}").json()
    created = client.post("/api/feedback", json={
        "area_id": AREA_ID, "service_type": "laundry", "feedback_type": "UNMET_SERVICE",
        "description": "세탁 서비스를 받지 못했습니다", "contact": "010-9999-8888",
        "claim": {"claims_demand": True},
    })
    assert created.status_code == 201, created.text
    fid = created.json()["feedback_id"]
    assert "010-9999-8888" not in created.text
    acted = client.post(f"/api/feedback/{fid}/action", json={"action": "start_review",
                                                              "role": "PLANNER"})
    assert acted.json()["status"] == "UNDER_REVIEW"
    accepted = client.post(f"/api/feedback/{fid}/action", json={
        "action": "accept", "role": "REVIEWER", "note": "검증 전 주장으로 채택"})
    assert accepted.status_code == 200, accepted.text
    after = client.get(f"/api/villages/{AREA_ID}").json()
    evidence = after["evidence"]
    assert evidence["resident_feedback"]["bounded_observation_contribution"] == 1
    assert evidence["needs_survey"] is True
    assert after["area"] == before["area"]
    assert after["scenario_assessments"] == before["scenario_assessments"]
    for key in ("status", "observation_count", "survey_count", "confidence"):
        assert evidence.get(key) == before["evidence"].get(key)
    summary = client.get(f"/api/villages/{AREA_ID}/feedback").json()
    assert summary["total"] == 1 and summary["signal"]["calibrated"] is False
    assert client.get(f"/api/feedback/{fid}/contact", params={"role": "PLANNER"}).json()[
        "contact"] == "010-9999-8888"
    assert "010-9999-8888" not in client.get("/api/feedback/export").text


def test_api_error_envelope_for_duplicate_and_unknown_area(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("VILLAGECOVERAGE_APP_DB", str(tmp_path / "api-errors.sqlite"))
    client = TestClient(app)
    body = {"area_id": AREA_ID, "service_type": "laundry", "feedback_type": "OTHER",
            "description": "같은 문장"}
    assert client.post("/api/feedback", json=body).status_code == 201
    duplicate = client.post("/api/feedback", json=body)
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "FEEDBACK_DUPLICATE"
    missing = client.post("/api/feedback", json={**body, "area_id": "no-such-area"})
    assert missing.status_code == 404
    invalid = client.post("/api/feedback", json={**body, "description": ""})
    assert invalid.status_code == 422
    assert client.post("/api/feedback", json={**body, "extra": 1}).status_code == 422
