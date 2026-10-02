from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from backend.main import app
from backend.timeutils import korea_today

ROOT = Path(__file__).resolve().parents[1]


def _area_id() -> str:
    data = json.loads((ROOT / "data" / "demo.json").read_text(encoding="utf-8"))
    return str(data["areas"][0]["id"])


def _submit_survey(
    client: TestClient, area_id: str, *, survey_type: str, frequency: int, note: str
):
    response = client.post(
        f"/api/villages/{area_id}/surveys",
        json={
            "survey_type": survey_type,
            "survey_date": korea_today().isoformat(),
            "service_type": "laundry",
            "frequency_per_month": frequency,
            "preferred_period": None,
            "preferred_days": [],
            "constraints": [],
            "free_text_note": note,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_duplicate_resolution_api_links_records_and_preserves_them(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("VILLAGECOVERAGE_APP_DB", str(tmp_path / "duplicate-api.sqlite"))
    client = TestClient(app)
    area_id = _area_id()
    note = "세탁 서비스를 매달 두 차례 원함"
    first = _submit_survey(client, area_id, survey_type="phone", frequency=2, note=note)
    second = _submit_survey(client, area_id, survey_type="phone", frequency=2, note=note)
    candidate = second["evidence_review"]["duplicate_candidates"][0]

    response = client.post(
        f"/api/villages/{area_id}/evidence-review/duplicates",
        json={
            "first_survey_id": first["survey"]["survey_id"],
            "second_survey_id": second["survey"]["survey_id"],
            "decision": "LINKED_DUPLICATE",
            "reason": "동일 요청으로 확인",
        },
    )
    assert response.status_code == 200, response.text
    review = response.json()["review"]

    assert candidate["status"] == "POSSIBLE_DUPLICATE"
    assert len(review["evidence"]) == 2
    assert all(item["evidence_status"] == "LINKED_DUPLICATE" for item in review["evidence"])
    assert len({item["canonical_survey_id"] for item in review["evidence"]}) == 1
    assert review["audit"][-1]["actor_type"] == "DEMO_PLANNER"


def test_frequency_conflict_api_requires_explicit_range_resolution(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("VILLAGECOVERAGE_APP_DB", str(tmp_path / "conflict-api.sqlite"))
    client = TestClient(app)
    area_id = _area_id()
    _submit_survey(
        client,
        area_id,
        survey_type="phone",
        frequency=2,
        note="전화로 세탁 빈도 문의",
    )
    submitted = _submit_survey(
        client,
        area_id,
        survey_type="village_meeting",
        frequency=4,
        note="회의에서 세탁 횟수 보고",
    )
    conflict = next(
        item
        for item in submitted["evidence_review"]["conflicts"]
        if item["conflict_type"] == "FREQUENCY_CONFLICT"
    )

    response = client.post(
        f"/api/villages/{area_id}/evidence-review/conflicts/{conflict['conflict_id']}/resolve",
        json={"method": "ACCEPTED_AS_RANGE", "reason": "두 결과를 범위로 유지"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    saved = next(
        item
        for item in body["review"]["conflicts"]
        if item["conflict_id"] == conflict["conflict_id"]
    )

    assert saved["status"] == "ACCEPTED_AS_RANGE"
    assert (saved["frequency_min"], saved["frequency_max"]) == (2, 4)
    assert body["review"]["frequency_planning_policy"] == "CONSERVATIVE_LOW"
    assert body["review"]["audit"][-1]["new_state"] == "ACCEPTED_AS_RANGE"
