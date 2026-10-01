import csv
import io
import json
from copy import deepcopy
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from backend import database
from backend import main as main_module
from backend.main import app
from backend.regions import DEFAULT_REGION_ID, region_catalog, select_region
from backend.travel import Route, put_cached
from backend.travel import connect as connect_travel

client = TestClient(app)


def test_health_and_public_quality_routes_do_not_need_external_calls() -> None:
    health = client.get("/api/health")
    quality = client.get("/api/data-quality")
    assert health.status_code == 200
    assert health.json()["demo_data_available"] is True
    assert quality.status_code == 200
    assert quality.json()["metrics"]["full_source_join_rate"] == 1.0


def test_demand_api_uses_schema_valid_local_fallback_without_credentials(monkeypatch) -> None:
    monkeypatch.setattr("backend.main._load_config", lambda _name: "")
    result = client.post(
        "/api/demand/structure",
        json={"text": "겨울 세탁 서비스를 월 2회 제공하고 화요일은 피하고 싶음."},
    )
    assert result.status_code == 200
    body = result.json()
    assert body["requests"][0]["service_type"] == "laundry"
    assert body["needs_followup_survey"] is False
    assert body["confidence"] is None
    assert body["evidence_assessment"]["observation_count"] == 1
    assert body["evidence_assessment"]["status"] == "조사 필요"
    assert not {"GEMINI_API_KEY", "DATA_GO_KR_SERVICE_KEY", "KAKAO_REST_API_KEY"}.intersection(body)


def test_service_registry_marks_regulated_and_excluded_requests_before_planning(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(main_module, "_load_config", lambda _name: "")
    monkeypatch.setenv("VILLAGECOVERAGE_APP_DB", str(tmp_path / "service-policy.sqlite"))

    registry = client.get("/api/services")
    assert registry.status_code == 200
    registry_body = registry.json()
    assert set(registry_body["allowed_service_codes"]) == {
        "laundry",
        "daily_necessities",
        "home_repair",
    }
    statuses = {
        service["service_type_id"]: service["policy_status"]
        for service in registry_body["services"]
    }
    assert statuses["medical_service"] == "REGULATED"
    assert statuses["legal_service"] == "REGULATED"
    assert statuses["mobility_support"] == "EXCLUDED"

    for text, service_id, expected_status in (
        ("의료 서비스 상담을 월 1회 요청함.", "medical_service", "REGULATED"),
        ("법률 상담을 월 1회 요청함.", "legal_service", "REGULATED"),
        ("병원 동행 이동지원을 월 1회 요청함.", "mobility_support", "EXCLUDED"),
    ):
        response = client.post("/api/demand/structure", json={"text": text})
        assert response.status_code == 200
        body = response.json()
        request = next(item for item in body["requests"] if item["service_type"] == service_id)
        assert request["service_policy"]["policy_status"] == expected_status
        assert body["requires_service_scope_review"] is True
        assert body["needs_followup_survey"] is True
        assert "초기 지원 범위" in body["followup_reason"]


def test_demand_api_rejects_unbounded_input() -> None:
    response = client.post("/api/demand/structure", json={"text": "x" * 10001})
    assert response.status_code == 422


def test_demand_draft_requires_a_verified_area_and_non_future_survey_date(
    tmp_path, monkeypatch
) -> None:
    data = json.loads(database.ROOT.joinpath("data", "demo.json").read_text(encoding="utf-8"))
    monkeypatch.setenv("VILLAGECOVERAGE_APP_DB", str(tmp_path / "demand-drafts.sqlite"))
    monkeypatch.setattr("backend.main._load_config", lambda _name: "")
    payload = {
        "area_id": data["areas"][0]["id"],
        "survey_type": "phone",
        "survey_date": date.today().isoformat(),
        "text": "세탁 월 2회 요청",
    }
    assert (
        client.post("/api/demand/drafts", json={**payload, "area_id": "unknown"}).status_code == 404
    )
    assert (
        client.post("/api/demand/drafts", json={**payload, "survey_date": "2999-01-01"}).status_code
        == 422
    )


@pytest.mark.parametrize("source_type", ["phone", "village_meeting", "proxy", "field"])
def test_demand_draft_preserves_each_evidence_source(source_type, tmp_path, monkeypatch) -> None:
    data = json.loads(database.ROOT.joinpath("data", "demo.json").read_text(encoding="utf-8"))
    monkeypatch.setenv("VILLAGECOVERAGE_APP_DB", str(tmp_path / "demand-drafts.sqlite"))
    monkeypatch.setattr("backend.main._load_config", lambda _name: "")
    response = client.post(
        "/api/demand/drafts",
        json={
            "area_id": data["areas"][0]["id"],
            "survey_type": source_type,
            "survey_date": date.today().isoformat(),
            "text": "세탁 월 1회 요청",
        },
    )
    assert response.status_code == 201
    draft = response.json()
    assert draft["survey_type"] == source_type
    stored = client.get(f"/api/demand/drafts/{draft['draft_id']}")
    assert stored.status_code == 200
    assert stored.json()["survey_type"] == source_type
    assert stored.json()["status"] == "DRAFT"


def test_demand_draft_approval_persists_redacted_source_human_edits_and_evidence(
    tmp_path, monkeypatch
) -> None:
    data = json.loads(database.ROOT.joinpath("data", "demo.json").read_text(encoding="utf-8"))
    area = next(row for row in data["areas"] if row["demand_observation_count"] == 1)
    monkeypatch.setenv("VILLAGECOVERAGE_APP_DB", str(tmp_path / "demand-drafts.sqlite"))
    monkeypatch.setattr("backend.main._load_config", lambda _name: "")
    created = client.post(
        "/api/demand/drafts",
        json={
            "area_id": area["id"],
            "survey_type": "phone",
            "survey_date": date.today().isoformat(),
            "text": (
                "김영희님 010-1234-5678은 10월 8일 오후 2시 세탁 월 2회를 원함. "
                "화요일은 피하고 싶음."
            ),
        },
    )
    assert created.status_code == 201
    draft = created.json()
    assert draft["status"] == "DRAFT"
    assert draft["source_text_was_redacted"] is True
    assert "010-1234-5678" not in draft["source_text_redacted"]
    saved = client.get(f"/api/demand/drafts?area_id={area['id']}")
    assert saved.status_code == 200
    assert [row["draft_id"] for row in saved.json()["drafts"]] == [draft["draft_id"]]
    resumed = client.get(f"/api/demand/drafts/{draft['draft_id']}")
    assert resumed.status_code == 200
    assert resumed.json()["source_text_redacted"] == draft["source_text_redacted"]
    structured = draft["structured"]
    assert structured["requests"][0]["desired_date"] == "10-08"
    assert structured["requests"][0]["desired_time"] == "14:00"
    assert structured["requests"][0]["recurring_pattern"] == "monthly"

    connection = database.connect(tmp_path / "demand-drafts.sqlite")
    try:
        assert connection.execute("SELECT count(*) FROM surveys").fetchone()[0] == 0
        assert connection.execute("SELECT count(*) FROM demand_observations").fetchone()[0] == 0
        assert connection.execute("SELECT count(*) FROM demand_evidence").fetchone()[0] == 0
    finally:
        connection.close()

    request = structured["requests"][0]
    request.update({"frequency_per_month": 3, "excluded_days": ["tuesday"]})
    approval_payload = {
        "requests": [
            {
                key: request[key]
                for key in (
                    "service_type",
                    "requested_period",
                    "frequency_per_month",
                    "desired_date",
                    "desired_time",
                    "recurring_pattern",
                    "urgency",
                    "urgency_evidence",
                    "preferred_days",
                    "excluded_days",
                    "constraints",
                )
            }
        ],
        "needs_followup_survey": False,
        "followup_reason": None,
    }
    approved = client.post(
        f"/api/demand/drafts/{draft['draft_id']}/approve",
        json=approval_payload,
    )
    assert approved.status_code == 200
    approval = approved.json()
    assert approval["status"] == "APPROVED"
    expected_observations = 1 + (
        area["demand_observation_count"] if area["service_type"] == "laundry" else 0
    )
    assert approval["evidence_assessments"]["laundry"]["observation_count"] == expected_observations
    connection = database.connect(tmp_path / "demand-drafts.sqlite")
    try:
        survey = database.list_surveys(connection, area["id"], "laundry")[0]
        assert survey["frequency_per_month"] == 3
        assert survey["structured_data"]["desired_date"] == "10-08"
        assert survey["structured_data"]["desired_time"] == "14:00"
        assert survey["structured_data"]["original_ai_request"]["frequency_per_month"] == 2
        assert survey["structured_data"]["evidence_source"] == "phone"
        assert survey["provenance"] == "SIMULATED HUMAN REVIEW"
        assert "010-1234-5678" not in survey["free_text_note"]
        observation = connection.execute(
            "SELECT source_type FROM demand_observations WHERE survey_id=?", (survey["survey_id"],)
        ).fetchone()
        assert observation["source_type"] == "phone"
        evidence = connection.execute(
            "SELECT payload_json FROM demand_evidence WHERE observation_id=("
            "SELECT observation_id FROM demand_observations WHERE survey_id=?)",
            (survey["survey_id"],),
        ).fetchone()
        assert json.loads(evidence["payload_json"])["structured_data"]["frequency_per_month"] == 3
        assert (
            connection.execute(
                "SELECT status FROM demand_structuring_drafts WHERE draft_id=?",
                (draft["draft_id"],),
            ).fetchone()["status"]
            == "APPROVED"
        )
    finally:
        connection.close()
    assert (
        client.post(
            f"/api/demand/drafts/{draft['draft_id']}/approve", json=approval_payload
        ).status_code
        == 409
    )


def test_demand_draft_cannot_approve_a_regulated_service_or_unsupported_urgency(
    tmp_path, monkeypatch
) -> None:
    data = json.loads(database.ROOT.joinpath("data", "demo.json").read_text(encoding="utf-8"))
    area = data["areas"][0]
    monkeypatch.setenv("VILLAGECOVERAGE_APP_DB", str(tmp_path / "demand-drafts.sqlite"))
    monkeypatch.setattr("backend.main._load_config", lambda _name: "")
    source = {
        "area_id": area["id"],
        "survey_type": "proxy",
        "survey_date": date.today().isoformat(),
    }
    regulated = client.post(
        "/api/demand/drafts", json={**source, "text": "의료 서비스 월 1회 요청"}
    ).json()
    restricted = client.post(
        f"/api/demand/drafts/{regulated['draft_id']}/approve",
        json={
            "requests": [{"service_type": "medical_service"}],
            "needs_followup_survey": True,
            "followup_reason": "서비스 범위 확인 필요",
        },
    )
    assert restricted.status_code == 422

    ordinary = client.post("/api/demand/drafts", json={**source, "text": "세탁 월 1회 요청"}).json()
    unsupported_urgency = client.post(
        f"/api/demand/drafts/{ordinary['draft_id']}/approve",
        json={
            "requests": [
                {
                    "service_type": "laundry",
                    "urgency": "urgent",
                    "urgency_evidence": "긴급",
                }
            ],
            "needs_followup_survey": False,
            "followup_reason": None,
        },
    )
    assert unsupported_urgency.status_code == 422
    connection = database.connect(tmp_path / "demand-drafts.sqlite")
    try:
        assert connection.execute("SELECT count(*) FROM demand_observations").fetchone()[0] == 0
        assert (
            connection.execute(
                "SELECT count(*) FROM demand_structuring_drafts WHERE status='DRAFT'"
            ).fetchone()[0]
            == 2
        )
    finally:
        connection.close()


def test_import_templates_publish_exact_column_and_policy_codes() -> None:
    response = client.get("/api/imports/templates")
    assert response.status_code == 200
    body = response.json()
    assert body["templates"]["demand_observations"]["headers"] == [
        "village_code",
        "date",
        "service_type",
        "source_type",
        "note",
    ]
    assert body["templates"]["provider_availability"]["headers"] == [
        "provider_id",
        "date",
        "start_time",
        "end_time",
        "service_type",
    ]
    assert body["templates"]["existing_service_history"]["headers"] == [
        "village_code",
        "service_type",
        "program_name",
        "monthly_rounds",
        "as_of_date",
    ]
    assert "medical" not in body["service_codes"]
    assert {item["policy_status"] for item in body["service_registry"]} == {
        "ALLOWED",
        "REGULATED",
        "EXCLUDED",
    }


def test_demand_csv_import_tracks_rows_redacts_notes_updates_evidence_and_is_idempotent(
    tmp_path, monkeypatch
) -> None:
    demo = json.loads(database.ROOT.joinpath("data", "demo.json").read_text(encoding="utf-8"))
    area = demo["areas"][0]
    today = date.today().isoformat()
    payload = (
        "village_code,date,service_type,source_type,note\n"
        f"{area['legal_code']},{today},{area['service_type']},phone,세탁 요청 기록\n"
        f"9999999999,{today},laundry,phone,010-1111-2222 요청\n"
        f"{area['legal_code']},{today},{area['service_type']},phone,\n"
        f"{area['legal_code']},{today},{area['service_type']},phone,010-1234-5678 연락 요청\n"
        f"{area['legal_code']},{today},medical,phone,의료 요청\n"
    )
    monkeypatch.setenv("VILLAGECOVERAGE_APP_DB", str(tmp_path / "csv-import.sqlite"))

    response = client.post(
        "/api/imports/demand_observations",
        content=payload,
        headers={"Content-Type": "text/csv; charset=utf-8"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert (
        body["total_rows"],
        body["valid_rows"],
        body["needs_review_rows"],
        body["failed_rows"],
    ) == (
        5,
        1,
        2,
        2,
    )
    assert body["rows"][1]["status"] == "FAILED"
    assert body["rows"][1]["record"]["note"] == "[전화번호] 요청"
    assert "010-1111-2222" not in json.dumps(body, ensure_ascii=False)
    assert body["rows"][2]["issues"] == ["NOTE_REQUIRED"]
    assert body["rows"][3]["status"] == "NEEDS_REVIEW"
    assert body["rows"][3]["record"]["note"].startswith("[전화번호]")
    history = client.get("/api/imports")
    assert history.status_code == 200
    assert history.json()["batches"][0]["batch_id"] == body["batch_id"]
    restored = client.get(f"/api/imports/{body['batch_id']}")
    assert restored.status_code == 200
    assert restored.json()["rows"][2]["status"] == "NEEDS_REVIEW"

    connection = database.connect()
    try:
        saved = connection.execute(
            "SELECT COUNT(*) FROM surveys WHERE provenance='CSV_IMPORT'"
        ).fetchone()[0]
        assessment = connection.execute(
            """SELECT observation_count, provenance FROM demand_assessments
               WHERE area_id=? AND service_type=?""",
            (area["id"], area["service_type"]),
        ).fetchone()
        rows_blob = " ".join(
            row[0] for row in connection.execute("SELECT record_json FROM import_rows").fetchall()
        )
        assert saved == 1
        assert assessment["observation_count"] == int(area["demand_observation_count"]) + 1
        assert "CSV_IMPORT" in assessment["provenance"]
        assert "010-1234-5678" not in rows_blob
    finally:
        connection.close()

    batch_id = body["batch_id"]
    approved_empty = client.post(
        f"/api/imports/{batch_id}/rows/4/approve",
        json={"note": "010-5555-6666 전화로 세탁 수요 확인"},
    )
    assert approved_empty.status_code == 200, approved_empty.text
    approved_redacted = client.post(f"/api/imports/{batch_id}/rows/5/approve", json={})
    assert approved_redacted.status_code == 200, approved_redacted.text
    final = approved_redacted.json()
    assert (final["valid_rows"], final["needs_review_rows"], final["failed_rows"]) == (3, 0, 2)
    assert final["rows"][2]["record"]["note"].startswith("[전화번호]")
    assert final["rows"][2]["redacted"] is True
    assert final["rows"][3]["record"]["note"].startswith("[전화번호]")

    repeated = client.post(
        "/api/imports/demand_observations",
        content=payload,
        headers={"Content-Type": "text/csv; charset=utf-8"},
    )
    assert repeated.status_code == 201
    assert repeated.json()["already_imported"] is True
    assert repeated.json()["batch_id"] == batch_id


def test_existing_service_history_import_refreshes_planning_demand_and_reviews_stale_rows(
    tmp_path, monkeypatch
) -> None:
    demo = json.loads(database.ROOT.joinpath("data", "demo.json").read_text(encoding="utf-8"))
    area = demo["areas"][0]
    today = date.today()
    stale = today - timedelta(days=181)
    monkeypatch.setenv("VILLAGECOVERAGE_APP_DB", str(tmp_path / "service-history.sqlite"))
    payload = (
        "village_code,service_type,program_name,monthly_rounds,as_of_date\n"
        f"{area['legal_code']},{area['service_type']},세탁지원,3,{today.isoformat()}\n"
        f"{area['legal_code']},{area['service_type']},오래된지원,2,{stale.isoformat()}\n"
        f"9999999999,{area['service_type']},미확인지역,1,{today.isoformat()}\n"
    )

    response = client.post(
        "/api/imports/existing_service_history",
        content=payload,
        headers={"Content-Type": "text/csv; charset=utf-8"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert (
        body["total_rows"],
        body["valid_rows"],
        body["needs_review_rows"],
        body["failed_rows"],
    ) == (
        3,
        1,
        1,
        1,
    )
    assert body["rows"][0]["imported_record_id"]
    assert "STALE_EXISTING_SERVICE_SNAPSHOT" in body["rows"][1]["issues"]

    connection = database.connect()
    try:
        existing = database.latest_existing_service_history(
            connection, str(area["id"]), str(area["service_type"])
        )
        assert len(existing) == 1
        main_module._apply_existing_service_history(area, connection)
        assert area["baseline_monthly_demand"] == area["simulated_monthly_demand"] + 3
        assert area["existing_service_monthly_rounds"] == 3
        assert area["existing_service_status"] == "CURRENT_REPORTED_SNAPSHOT"
        assert "CSV_IMPORT" in area["planning_demand_provenance"]
    finally:
        connection.close()

    planned_demands: dict[str, int] = {}

    class FakeRoadConnection:
        def close(self) -> None:
            pass

    def capture_provider_schedule(areas, *_args):
        planned_demands.update(
            {str(item["id"]): int(item["simulated_monthly_demand"]) for item in areas}
        )
        return {"rounds": [], "routes": [], "solver_status": "OPTIMAL"}

    monkeypatch.setattr("backend.main.connect", FakeRoadConnection)
    monkeypatch.setattr("backend.main.get_cached", lambda *_args: object())
    monkeypatch.setattr("backend.main.generate_provider_schedule", capture_provider_schedule)
    schedule = client.post(
        "/api/schedules",
        json={
            "scenario": "efficiency",
            "budget_won": 1_000_000,
            "region_id": area["region_id"],
        },
    )
    assert schedule.status_code == 201, schedule.text
    assert planned_demands[str(area["id"])] == int(area["simulated_monthly_demand"])

    approved_stale = client.post(f"/api/imports/{body['batch_id']}/rows/3/approve", json={})
    assert approved_stale.status_code == 200, approved_stale.text
    assert approved_stale.json()["rows"][1]["status"] == "IMPORTED"

    connection = database.connect()
    try:
        latest = database.latest_existing_service_history(
            connection, str(area["id"]), str(area["service_type"])
        )
        assert {item["program_name"]: item["monthly_rounds"] for item in latest} == {
            "세탁지원": 3,
            "오래된지원": 2,
        }
        main_module._apply_existing_service_history(area, connection)
        assert area["simulated_monthly_demand"] == area["baseline_monthly_demand"] - 3
    finally:
        connection.close()

    repeated = client.post(
        "/api/imports/existing_service_history",
        content=payload,
        headers={"Content-Type": "text/csv; charset=utf-8"},
    )
    assert repeated.status_code == 201
    assert repeated.json()["already_imported"] is True


def test_provider_availability_csv_validates_provider_and_persists_date_override(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("VILLAGECOVERAGE_APP_DB", str(tmp_path / "provider-import.sqlite"))
    provider_response = client.get("/api/providers")
    assert provider_response.status_code == 200
    provider_id = next(
        item["provider_id"]
        for item in provider_response.json()["providers"]
        if item["service_count"] < 3
    )
    provider = client.get(f"/api/providers/{provider_id}").json()
    connection = database.connect()
    try:
        supported = {
            row[0]
            for row in connection.execute(
                "SELECT service_type FROM provider_services WHERE provider_id=?",
                (provider["provider_id"],),
            ).fetchall()
        }
        unsupported = next(
            service
            for service in ("laundry", "daily_necessities", "home_repair")
            if service not in supported
        )
    finally:
        connection.close()
    target = (date.today() + timedelta(days=1)).isoformat()
    payload = (
        "provider_id,date,start_time,end_time,service_type\n"
        f"{provider['provider_id']},{target},13:00,17:00,{provider['supported_services'][0]}\n"
        f"missing-provider,{target},09:00,17:00,laundry\n"
        f"{provider['provider_id']},{target},09:00,17:00,{unsupported}\n"
    )
    imported = client.post(
        "/api/imports/provider_availability",
        content=payload,
        headers={"Content-Type": "text/csv; charset=utf-8"},
    )
    assert imported.status_code == 201, imported.text
    body = imported.json()
    assert (body["total_rows"], body["valid_rows"], body["failed_rows"]) == (3, 1, 2)
    detail = client.get(f"/api/providers/{provider['provider_id']}")
    assert detail.status_code == 200
    matching = [
        item for item in detail.json()["date_availability"] if item["available_date"] == target
    ]
    assert matching == [
        {
            "available_date": target,
            "service_type": provider["supported_services"][0],
            "start_time": "13:00",
            "end_time": "17:00",
            "provenance": "CSV_IMPORT",
        }
    ]


def test_import_rejects_malformed_headers_and_excessive_body(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("VILLAGECOVERAGE_APP_DB", str(tmp_path / "bad-import.sqlite"))
    missing_column = client.post(
        "/api/imports/demand_observations",
        content="village_code,date,service_type,note\n",
        headers={"Content-Type": "text/csv"},
    )
    assert missing_column.status_code == 422
    too_large = client.post(
        "/api/imports/demand_observations",
        content=b"x" * (5 * 1024 * 1024 + 1),
        headers={"Content-Type": "text/csv"},
    )
    assert too_large.status_code == 413


def test_survey_persists_synthetic_evidence_and_refreshes_low_data_assessment(
    tmp_path, monkeypatch
) -> None:
    demo = json.loads(database.ROOT.joinpath("data", "demo.json").read_text(encoding="utf-8"))
    area = next(row for row in demo["areas"] if row["demand_observation_count"] == 1)
    monkeypatch.setenv("VILLAGECOVERAGE_APP_DB", str(tmp_path / "surveys.sqlite"))

    def fake_scenario_data(_budget, *_args, **_kwargs):
        data = json.loads(database.ROOT.joinpath("data", "demo.json").read_text(encoding="utf-8"))
        results = {}
        for scenario in ("efficiency", "balanced", "minimum_coverage"):
            results[scenario] = {
                "assignments": [
                    {
                        "area_id": item["id"],
                        "served_units": 0,
                        "demand_units": item["simulated_monthly_demand"],
                        "cost_won": 0,
                        "status": "미충족",
                        "needs_survey": item["needs_survey"],
                    }
                    for item in data["areas"]
                ]
            }
        return data, {"scenario_results": results}

    live_scenario_data = main_module._scenario_data
    monkeypatch.setattr("backend.main._scenario_data", fake_scenario_data)
    payload = {
        "survey_type": "phone",
        "survey_date": date.today().isoformat(),
        "service_type": area["service_type"],
        "frequency_per_month": 2,
        "preferred_period": "겨울",
        "preferred_days": ["tuesday"],
        "constraints": ["병원 방문일 제외", "김영희님 전화 010-1234-5678 제외"],
        "free_text_note": "김영희님 010-1234-5678은 겨울 세탁 월 2회를 요청함.",
    }
    saved = client.post(f"/api/villages/{area['id']}/surveys", json=payload)
    assert saved.status_code == 201
    body = saved.json()
    assert body["message"].endswith("시연용 합성 자료입니다.")
    assert body["survey"]["source_text_was_redacted"] is True
    assert "010-1234-5678" not in body["survey"]["free_text_note"]
    assert "010-1234-5678" not in " ".join(body["survey"]["constraints"])
    assert body["evidence"]["observation_count"] == 2
    assert body["evidence"]["survey_count"] == 1
    assert body["evidence"]["source_diversity"] == 2
    assert body["evidence"]["status"] == "제한적 계획 가능"
    assert body["evidence"]["limited_planning_allowed"] is True
    assert body["evidence"]["needs_survey"] is True

    detail = client.get(f"/api/villages/{area['id']}")
    assert detail.status_code == 200
    assert detail.json()["evidence"]["observation_count"] == 2
    assert detail.json()["surveys"][0]["survey_type"] == "phone"
    assert detail.json()["survey_recommendation"].startswith("기초조사 근거")

    observed_plan_inputs = {}

    class FakeTravelConnection:
        def close(self):
            pass

    def capture_scenario_inputs(areas, _providers, _connection, _budget, _policy=None):
        observed_plan_inputs.update(next(row for row in areas if row["id"] == area["id"]))
        assignments = [
            {
                "area_id": row["id"],
                "served_units": 0,
                "demand_units": row["simulated_monthly_demand"],
                "cost_won": 0,
                "status": "미충족",
                "needs_survey": row["needs_survey"],
            }
            for row in areas
        ]
        return {
            "scenario_results": {
                key: {"assignments": assignments}
                for key in ("efficiency", "balanced", "minimum_coverage")
            },
            "request_count_baseline": {},
            "hub_area_id": area["id"],
            "travel_source": "test road routes",
        }

    monkeypatch.setattr("backend.main._scenario_data", live_scenario_data)
    monkeypatch.setattr("backend.main.connect", FakeTravelConnection)
    monkeypatch.setattr(
        "backend.main.get_cached",
        lambda _connection, origin, destination: Route(origin["id"], destination["id"], 0, 0),
    )
    monkeypatch.setattr("backend.main.evaluate_scenarios", capture_scenario_inputs)
    main_module._scenario_data(5_000_000, region_id=area.get("region_id", DEFAULT_REGION_ID))
    assert observed_plan_inputs["demand_observation_count"] == 2
    assert observed_plan_inputs["demand_confidence"] == "제한적 계획 가능"
    assert observed_plan_inputs["needs_survey"] is True

    connection = database.connect(tmp_path / "surveys.sqlite")
    try:
        assert connection.execute("SELECT count(*) FROM demand_observations").fetchone()[0] == 1
        assert connection.execute("SELECT count(*) FROM demand_evidence").fetchone()[0] == 1
        assessment = connection.execute(
            "SELECT status FROM demand_assessments WHERE area_id=?", (area["id"],)
        ).fetchone()
        assert assessment[0] == "제한적 계획 가능"
    finally:
        connection.close()


def test_survey_rejects_out_of_scope_service_and_unknown_area(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("VILLAGECOVERAGE_APP_DB", str(tmp_path / "surveys.sqlite"))
    payload = {
        "survey_type": "phone",
        "survey_date": date.today().isoformat(),
        "service_type": "mobility_support",
        "frequency_per_month": 1,
    }
    unsupported = client.post("/api/villages/area-1/surveys", json=payload)
    assert unsupported.status_code == 422

    payload["service_type"] = "laundry"
    unknown_area = client.post("/api/villages/not-a-real-area/surveys", json=payload)
    assert unknown_area.status_code == 404


def test_survey_rejects_future_dates(tmp_path, monkeypatch) -> None:
    demo = json.loads(database.ROOT.joinpath("data", "demo.json").read_text(encoding="utf-8"))
    area = demo["areas"][0]
    monkeypatch.setenv("VILLAGECOVERAGE_APP_DB", str(tmp_path / "surveys.sqlite"))
    response = client.post(
        f"/api/villages/{area['id']}/surveys",
        json={
            "survey_type": "field",
            "survey_date": "2999-01-01",
            "service_type": "laundry",
            "frequency_per_month": 1,
        },
    )
    assert response.status_code == 422


def test_overview_accepts_and_returns_explicit_policy_choices(monkeypatch) -> None:
    data = json.loads(database.ROOT.joinpath("data", "demo.json").read_text(encoding="utf-8"))
    observed: dict[str, object] = {}

    def scenario_data(budget, policy, region_id=DEFAULT_REGION_ID):
        observed["budget"] = budget
        observed["policy"] = policy
        selected_data = select_region(data, region_id)
        observed["region_id"] = region_id
        return selected_data, {
            "planning_policy": {
                "minimum_services_per_area": policy.minimum_services_per_area,
                "elderly_priority_weight": policy.elderly_priority_weight,
                "single_elderly_household_priority_weight": (
                    policy.single_elderly_household_priority_weight
                ),
                "survey_required_protection_weight": policy.survey_required_protection_weight,
                "maximum_round_trip_travel_minutes": policy.maximum_round_trip_travel_minutes,
                "allowed_services": list(policy.allowed_services),
                "minimum_provider_compensation_won": policy.minimum_provider_compensation_won,
            },
            "scenario_results": {},
            "request_count_baseline": {},
            "hub_area_id": data["areas"][0]["id"],
            "travel_source": "test road routes",
        }

    monkeypatch.setattr("backend.main._scenario_data", scenario_data)
    response = client.get(
        "/api/overview",
        params=[
            ("budget", "4200000"),
            ("minimum_services_per_area", "2"),
            ("elderly_priority_weight", "800"),
            ("single_elderly_household_priority_weight", "300"),
            ("survey_required_protection_weight", "600"),
            ("maximum_round_trip_travel_minutes", "90"),
            ("allowed_services", "laundry"),
            ("allowed_services", "home_repair"),
            ("minimum_provider_compensation_won", "320000"),
        ],
    )

    assert response.status_code == 200
    assert observed["budget"] == 4_200_000
    assert observed["region_id"] == DEFAULT_REGION_ID
    policy = observed["policy"]
    assert policy.minimum_services_per_area == 2
    assert policy.elderly_priority_weight == 800
    assert policy.single_elderly_household_priority_weight == 300
    assert policy.survey_required_protection_weight == 600
    assert policy.maximum_round_trip_travel_minutes == 90
    assert policy.allowed_services == ("home_repair", "laundry")
    assert policy.minimum_provider_compensation_won == 320_000
    assert response.json()["planning_policy"]["minimum_services_per_area"] == 2


def test_overview_rejects_regulated_or_unknown_allowed_services() -> None:
    response = client.get("/api/overview", params={"allowed_services": "mobility_support"})
    assert response.status_code == 422


def test_region_catalog_and_provider_directory_are_scoped_to_verified_towns(
    tmp_path, monkeypatch
) -> None:
    demo = json.loads(database.ROOT.joinpath("data", "demo.json").read_text(encoding="utf-8"))
    options = region_catalog(demo)
    monkeypatch.setenv("VILLAGECOVERAGE_APP_DB", str(tmp_path / "regional-providers.sqlite"))

    catalog = client.get("/api/regions")
    assert catalog.status_code == 200
    assert catalog.json()["default_region_id"] == DEFAULT_REGION_ID
    assert {item["region_id"] for item in catalog.json()["regions"]} == {
        item["region_id"] for item in options
    }
    assert all(item["full_source_join_rate"] == 1.0 for item in options)

    for option in options:
        response = client.get("/api/providers", params={"region_id": option["region_id"]})
        assert response.status_code == 200
        assert response.json()["region_id"] == option["region_id"]
        providers = response.json()["providers"]
        assert len(providers) == 3
        assert {provider["region_id"] for provider in providers} == {option["region_id"]}
        assert {provider["region_name"] for provider in providers} == {option["name"]}

    unknown = client.get("/api/providers", params={"region_id": "pilot:unverified"})
    assert unknown.status_code == 422


def test_provider_schedule_is_saved_for_the_selected_region(tmp_path, monkeypatch) -> None:
    demo = json.loads(database.ROOT.joinpath("data", "demo.json").read_text(encoding="utf-8"))
    option = next(item for item in region_catalog(demo) if item["region_id"] != DEFAULT_REGION_ID)
    area_ids = {
        str(area["id"]) for area in demo["areas"] if area["region_id"] == option["region_id"]
    }
    monkeypatch.setenv("VILLAGECOVERAGE_APP_DB", str(tmp_path / "regional-schedule.sqlite"))

    response = client.post(
        "/api/schedules",
        json={
            "scenario": "balanced",
            "budget_won": 5_000_000,
            "region_id": option["region_id"],
        },
    )

    assert response.status_code == 201, response.text
    plan = response.json()
    assert plan["scenario_key"] == "balanced"
    assert plan["region_id"] == option["region_id"]
    assert plan["region_name"] == option["name"]
    assert plan["rounds"]
    assert all(round_item["area_id"] in area_ids for round_item in plan["rounds"])
    provider_ids = {
        provider["provider_id"]
        for provider in client.get(
            "/api/providers", params={"region_id": option["region_id"]}
        ).json()["providers"]
    }
    assert {round_item["provider_id"] for round_item in plan["rounds"]} <= provider_ids


def test_schedule_history_and_csv_export_are_region_scoped_and_auditable(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("VILLAGECOVERAGE_APP_DB", str(tmp_path / "schedule-history.sqlite"))
    created = client.post(
        "/api/schedules",
        json={"scenario": "efficiency", "budget_won": 5_000_000},
    )
    assert created.status_code == 201, created.text
    plan = created.json()

    history = client.get("/api/schedules", params={"region_id": DEFAULT_REGION_ID})
    assert history.status_code == 200
    assert history.json()["provenance"] == "OPTIMIZATION RESULT; SIMULATED FOR PRE-R&D"
    assert len(history.json()["plans"]) == 1
    history_item = history.json()["plans"][0]
    assert history_item["schedule_id"] == plan["schedule_id"]
    assert history_item["summary"]["total_cost_won"] == plan["summary"]["total_cost_won"]
    assert history_item["provenance"] == plan["provenance"]

    exported = client.get(f"/api/schedules/{plan['schedule_id']}/export.csv")
    assert exported.status_code == 200
    assert exported.headers["content-type"].startswith("text/csv")
    assert "attachment;" in exported.headers["content-disposition"]
    rows = list(csv.reader(io.StringIO(exported.content.decode("utf-8-sig"))))
    assert len(rows) == len(plan["rounds"]) + 1
    assert rows[0][0:6] == [
        "record_type",
        "schedule_id",
        "region",
        "scenario",
        "budget_won",
        "created_at",
    ]
    assert all(row[0] == "ROUND" for row in rows[1:])
    assert all(row[1] == plan["schedule_id"] for row in rows[1:])
    assert all(row[-1] == "OPTIMIZATION RESULT; SIMULATED FOR PRE-R&D" for row in rows[1:])
    assert int(rows[1][rows[0].index("plan_total_cost_won")]) == plan["summary"]["total_cost_won"]

    no_service = client.post(
        "/api/schedules",
        json={"scenario": "efficiency", "budget_won": 0},
    )
    assert no_service.status_code == 201, no_service.text
    empty_export = client.get(f"/api/schedules/{no_service.json()['schedule_id']}/export.csv")
    empty_rows = list(csv.reader(io.StringIO(empty_export.content.decode("utf-8-sig"))))
    assert len(empty_rows) == 2
    assert empty_rows[1][0] == "PLAN_SUMMARY"
    assert empty_rows[1][empty_rows[0].index("plan_total_cost_won")] == "0"

    assert client.get("/api/schedules", params={"region_id": "pilot:unknown"}).status_code == 422
    assert client.get("/api/schedules/missing/export.csv").status_code == 404


def test_csv_export_text_escapes_spreadsheet_formulas() -> None:
    from backend.main import _csv_safe_text

    assert _csv_safe_text("=1+1") == "'=1+1"
    assert _csv_safe_text("  @SUM(A1:A2)") == "'  @SUM(A1:A2)"
    assert _csv_safe_text('\v=HYPERLINK("https://invalid")') == '\'\v=HYPERLINK("https://invalid")'
    assert _csv_safe_text("\ufeff+1") == "'\ufeff+1"
    assert _csv_safe_text("홍성군") == "홍성군"


def test_provider_directory_detail_and_round_opt_in_are_persistent(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("VILLAGECOVERAGE_APP_DB", str(tmp_path / "providers.sqlite"))
    listing = client.get("/api/providers")
    assert listing.status_code == 200
    providers = listing.json()["providers"]
    assert [provider["name"] for provider in providers] == [
        "마을생활협동조합",
        "지역생활지원",
        "행복세탁",
    ]
    assert listing.json()["provenance"] == "SIMULATED FOR PRE-R&D"

    detail = client.get("/api/providers/sim-provider-1")
    assert detail.status_code == 200
    provider = detail.json()
    assert provider["supported_services"] == ["laundry"]
    assert provider["minimum_compensation_won"] == 210000
    assert provider["participation"]["long_term_agreement_candidate"] is True
    assert provider["forecast"]["status"] == "DATA_INSUFFICIENT"
    assert provider["forecast"]["survey_required"] is True
    assert len(provider["forecast"]["months"]) == 3
    assert all(
        month["evidence_status"] == "DATA_INSUFFICIENT" and month["expected_rounds_mid"] is None
        for month in provider["forecast"]["months"]
    )
    opportunity = provider["upcoming_rounds"][0]
    assert opportunity["status"] == "AVAILABLE"
    assert opportunity["travel_time_minutes"] is None

    opted_in = client.post(
        f"/api/providers/sim-provider-1/rounds/{opportunity['round_id']}/participation",
        json={"status": "OPTED_IN"},
    )
    assert opted_in.status_code == 200
    assert opted_in.json()["provenance"] == "SIMULATED FOR PRE-R&D"
    assert (
        next(
            row
            for row in opted_in.json()["provider"]["upcoming_rounds"]
            if row["round_id"] == opportunity["round_id"]
        )["status"]
        == "OPTED_IN"
    )

    connection = database.connect(tmp_path / "providers.sqlite")
    try:
        status = connection.execute(
            "SELECT status FROM provider_participations WHERE round_id=?",
            (opportunity["round_id"],),
        ).fetchone()[0]
        assert status == "OPTED_IN"
    finally:
        connection.close()


def test_provider_opt_in_rejects_unsupported_service_and_unknown_round(
    tmp_path, monkeypatch
) -> None:
    path = tmp_path / "providers.sqlite"
    monkeypatch.setenv("VILLAGECOVERAGE_APP_DB", str(path))
    detail = client.get("/api/providers/sim-provider-1").json()
    round_id = detail["upcoming_rounds"][0]["round_id"]
    connection = database.connect(path)
    try:
        connection.execute(
            "UPDATE service_rounds SET service_type='daily_necessities' WHERE round_id=?",
            (round_id,),
        )
        connection.commit()
    finally:
        connection.close()
    response = client.post(
        f"/api/providers/sim-provider-1/rounds/{round_id}/participation",
        json={"status": "OPTED_IN"},
    )
    assert response.status_code == 409
    assert "does not support" in response.json()["detail"]

    unknown = client.post(
        "/api/providers/sim-provider-1/rounds/not-a-round/participation",
        json={"status": "OPTED_IN"},
    )
    assert unknown.status_code == 404


def test_survey_evidence_is_assessed_only_for_its_service_type(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "service-scoped-surveys.sqlite"
    monkeypatch.setenv("VILLAGECOVERAGE_APP_DB", str(db_path))
    demo = json.loads(database.ROOT.joinpath("data", "demo.json").read_text(encoding="utf-8"))
    area = next(row for row in demo["areas"] if row["service_type"] == "laundry")
    response = client.post(
        f"/api/villages/{area['id']}/surveys",
        json={
            "survey_type": "phone",
            "survey_date": date.today().isoformat(),
            "service_type": "home_repair",
            "frequency_per_month": 1,
            "preferred_period": "가을",
            "preferred_days": ["wednesday"],
            "constraints": [],
            "free_text_note": "간단한 주거 수리를 요청함.",
        },
    )
    assert response.status_code == 201
    assert response.json()["evidence"]["observation_count"] == 1
    assert response.json()["evidence"]["status"] == "조사 필요"

    detail = client.get(f"/api/villages/{area['id']}").json()
    assert detail["evidence"]["observation_count"] == area["demand_observation_count"]
    assert detail["evidence"]["survey_count"] == 0
    assert detail["surveys"][0]["service_type"] == "home_repair"

    connection = database.connect(db_path)
    try:
        assessments = [
            dict(row)
            for row in connection.execute(
                "SELECT service_type, observation_count FROM demand_assessments WHERE area_id=?",
                (area["id"],),
            ).fetchall()
        ]
        assert {row["service_type"]: row["observation_count"] for row in assessments}[
            "home_repair"
        ] == 1
    finally:
        connection.close()


def test_schedule_plan_uses_cached_provider_roads_persists_and_shows_opt_in(
    tmp_path, monkeypatch
) -> None:
    demo = json.loads(database.ROOT.joinpath("data", "demo.json").read_text(encoding="utf-8"))
    one_area_data = deepcopy(demo)
    one_area_data["areas"] = [
        row
        for row in one_area_data["areas"]
        if row["region_id"] == DEFAULT_REGION_ID and row["service_type"] == "laundry"
    ][:1]
    area = one_area_data["areas"][0]
    app_path = tmp_path / "schedule-app.sqlite"
    travel_path = tmp_path / "schedule-travel.sqlite"
    monkeypatch.setenv("VILLAGECOVERAGE_APP_DB", str(app_path))
    monkeypatch.setattr("backend.main._load_demo", lambda: deepcopy(one_area_data))

    travel_connection = connect_travel(travel_path)
    try:
        put_cached(
            travel_connection,
            area,
            area,
            Route(area["id"], area["id"], 0, 0),
        )
    finally:
        travel_connection.close()
    monkeypatch.setattr("backend.main.connect", lambda: connect_travel(travel_path))

    response = client.post(
        "/api/schedules",
        json={
            "scenario": "efficiency",
            "budget_won": 5_000_000,
            "planning_policy": {
                "minimum_services_per_area": 2,
                "elderly_priority_weight": 800,
                "single_elderly_household_priority_weight": 300,
                "survey_required_protection_weight": 600,
                "maximum_round_trip_travel_minutes": 30,
                "allowed_services": ["laundry"],
                "minimum_provider_compensation_won": 480_000,
            },
        },
    )
    assert response.status_code == 201, response.text
    plan = response.json()
    assert plan["scenario_key"] == "efficiency"
    assert plan["planning_policy"]["minimum_services_per_area"] == 2
    assert plan["planning_policy"]["allowed_services"] == ["laundry"]
    assert plan["planning_policy"]["minimum_provider_compensation_won"] == 480_000
    assert plan["summary"]["travel_source"].startswith("Kakao Mobility")
    assert plan["summary"]["budget_gap_won"] is None
    assert plan["rounds"]
    assert all(row["participation_status"] == "AVAILABLE" for row in plan["rounds"])
    assert all(row["provenance"].startswith("OPTIMIZATION RESULT") for row in plan["rounds"])

    round_item = plan["rounds"][0]
    opted_in = client.post(
        f"/api/providers/{round_item['provider_id']}/rounds/{round_item['service_round_id']}/participation",
        json={"status": "OPTED_IN"},
    )
    assert opted_in.status_code == 200
    saved_plan = client.get(f"/api/schedules/{plan['schedule_id']}")
    assert saved_plan.status_code == 200
    updated_round = next(
        row
        for row in saved_plan.json()["rounds"]
        if row["service_round_id"] == round_item["service_round_id"]
    )
    assert updated_round["participation_status"] == "OPTED_IN"


def test_schedule_rejects_services_outside_the_policy_registry() -> None:
    response = client.post(
        "/api/schedules",
        json={
            "scenario": "balanced",
            "budget_won": 1_000_000,
            "planning_policy": {"allowed_services": ["medical_care"]},
        },
    )
    assert response.status_code == 422


def test_schedule_plan_fails_closed_without_provider_road_routes(tmp_path, monkeypatch) -> None:
    demo = json.loads(database.ROOT.joinpath("data", "demo.json").read_text(encoding="utf-8"))
    one_area_data = deepcopy(demo)
    one_area_data["areas"] = [
        row
        for row in demo["areas"]
        if row["region_id"] == DEFAULT_REGION_ID and row["service_type"] == "laundry"
    ][:1]
    monkeypatch.setenv("VILLAGECOVERAGE_APP_DB", str(tmp_path / "schedule-app.sqlite"))
    monkeypatch.setattr("backend.main._load_demo", lambda: deepcopy(one_area_data))
    monkeypatch.setattr(
        "backend.main.connect", lambda: connect_travel(tmp_path / "empty-travel.sqlite")
    )
    response = client.post(
        "/api/schedules",
        json={"scenario": "efficiency", "budget_won": 5_000_000},
    )
    assert response.status_code == 503
    assert "road cache is incomplete" in response.json()["detail"]
