import json
from datetime import date

from fastapi.testclient import TestClient

from backend import database
from backend import main as main_module
from backend.main import app

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


def test_demand_api_rejects_unbounded_input() -> None:
    response = client.post("/api/demand/structure", json={"text": "x" * 10001})
    assert response.status_code == 422


def test_survey_persists_synthetic_evidence_and_refreshes_low_data_assessment(
    tmp_path, monkeypatch
) -> None:
    demo = json.loads(database.ROOT.joinpath("data", "demo.json").read_text(encoding="utf-8"))
    area = next(row for row in demo["areas"] if row["demand_observation_count"] == 1)
    monkeypatch.setenv("VILLAGECOVERAGE_APP_DB", str(tmp_path / "surveys.sqlite"))

    def fake_scenario_data(_budget):
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

    def capture_scenario_inputs(areas, _providers, _connection, _budget):
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
        "backend.main.matrix_summary",
        lambda _connection: {"route_count": len(demo["areas"]) ** 2},
    )
    monkeypatch.setattr("backend.main.evaluate_scenarios", capture_scenario_inputs)
    main_module._scenario_data(5_000_000)
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
