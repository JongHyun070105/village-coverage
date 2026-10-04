from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import database, home_repair
from backend.demand import deterministic_structure
from backend.main import app
from backend.service_registry import (
    POLICY_FOR_REGULATION,
    REGULATION_LEVELS,
    SERVICE_REGISTRY,
    SERVICE_UNIT_TYPES,
)

ROOT = Path(__file__).resolve().parents[1]
DEMO = json.loads((ROOT / "data" / "demo.json").read_text(encoding="utf-8"))


@pytest.fixture
def conn(tmp_path):
    connection = database.connect(tmp_path / "repair.sqlite")
    database.seed_reference_data(connection, DEMO)
    database.seed_provider_data(connection, DEMO)
    yield connection
    connection.close()


@pytest.mark.parametrize(
    "text",
    [
        "보일러 수리가 필요합니다",
        "보일러가 고장나서 고쳐 주세요",
        "가스 레인지 점검과 수리",
        "누전 차단기가 자꾸 내려가요",
        "전기 수리 부탁드립니다",
        "전기 배선 교체",
        "지붕 슬레이트 보수",
        "욕실 누수 방수 작업",
        "천장 석면 철거",
        "고소 작업이 필요한 처마 수리",
        "전구 교체하고 보일러도 봐주세요",
    ],
)
def test_risky_text_is_never_simple_repair(text) -> None:
    result = home_repair.classify_repair_text(text)
    assert result["classification"] in ("LICENSE_REQUIRED", "EXCLUDED")
    assert result["matched_jobs"] == []
    structured = deterministic_structure(text)
    services = {request.service_type for request in structured.requests}
    assert "home_repair" not in services
    assert "licensed_repair" in services


def test_mixed_request_keeps_simple_job_only_as_information() -> None:
    result = home_repair.classify_repair_text("전구 교체하고 보일러도 봐주세요")
    assert result["simple_jobs_detected"] == ["bulb_replace"]
    assert result["matched_jobs"] == []


@pytest.mark.parametrize(
    ("text", "jobs"),
    [
        ("전구가 나갔어요", ["bulb_replace"]),
        ("방충망이 찢어졌어요", ["screen_door_patch"]),
        ("문고리 교체 요청", ["door_handle"]),
        ("형광등 교체와 방충망 보수", ["bulb_replace", "screen_door_patch"]),
    ],
)
def test_simple_jobs_are_accepted(text, jobs) -> None:
    result = home_repair.classify_repair_text(text)
    assert result["classification"] == "SIMPLE_REPAIR"
    assert result["regulation_level"] == "LIMITED"
    assert result["matched_jobs"] == jobs
    assert {r.service_type for r in deterministic_structure(text).requests} >= {"home_repair"}


def test_generic_repair_word_needs_review_not_auto_accept() -> None:
    result = home_repair.classify_repair_text("집에 고장난 게 있어요")
    assert result["classification"] == "NEEDS_REVIEW"
    assert result["matched_jobs"] == []
    assert home_repair.classify_repair_text("세탁 서비스 문의")["classification"] == "NOT_REPAIR"


def test_whitespace_does_not_hide_risky_terms() -> None:
    assert home_repair.classify_repair_text("전 기 배 선")["classification"] == "LICENSE_REQUIRED"
    assert home_repair.classify_repair_text("누  수")["classification"] == "LICENSE_REQUIRED"


def test_registry_regulation_levels_are_consistent() -> None:
    for service in SERVICE_REGISTRY:
        assert service.regulation_level in REGULATION_LEVELS
        assert service.unit_type in SERVICE_UNIT_TYPES
        assert POLICY_FOR_REGULATION[service.regulation_level] == service.policy_status
    by_id = {service.service_type_id: service for service in SERVICE_REGISTRY}
    assert by_id["home_repair"].regulation_level == "LIMITED"
    assert by_id["home_repair"].unit_type == "JOB"
    assert by_id["licensed_repair"].regulation_level == "LICENSE_REQUIRED"
    assert by_id["laundry"].unit_type == "ROUND"


def test_persisted_service_types_carry_regulation_and_unit(conn) -> None:
    rows = {row["service_type_id"]: row for row in database.list_service_types(conn)}
    assert rows["home_repair"]["regulation_level"] == "LIMITED"
    assert rows["home_repair"]["unit_type"] == "JOB"
    assert rows["licensed_repair"]["policy_status"] == "REGULATED"
    assert rows["mobility_support"]["regulation_level"] == "EXCLUDED"
    assert conn.execute("PRAGMA user_version").fetchone()[0] == database.SCHEMA_VERSION


def test_catalog_mix_and_uncertainty_are_well_formed() -> None:
    assert sum(job.share for job in home_repair.JOB_CATALOG) == pytest.approx(1.0)
    for job in home_repair.JOB_CATALOG:
        assert job.minutes_min <= job.minutes_likely <= job.minutes_max
        assert job.material_level in home_repair.MATERIAL_LEVELS
        assert job.material_cost_won[0] <= job.material_cost_won[1]
    payload = home_repair.profile_payload()
    assert payload["provenance"].startswith("SIMULATED")
    assert all(job["provenance"].startswith("SIMULATED") for job in payload["jobs"])


def test_job_demand_is_ordered_and_not_the_laundry_model() -> None:
    area = DEMO["areas"][0]
    estimate = home_repair.estimate_area_job_demand(area)
    jobs = estimate["jobs_per_month"]
    assert jobs["low"] < jobs["mid"] < jobs["high"]
    hours = estimate["work_hours_per_month"]
    assert hours["low"] < hours["mid"] < hours["high"]
    assert estimate["bounds_are_quantiles"] is False
    assert estimate["provenance"].startswith("SIMULATED")
    assert "laundry" not in json.dumps(estimate)
    assert estimate["material_cost_won_per_month"]["low"] <= (
        estimate["material_cost_won_per_month"]["high"]
    )


def test_job_demand_without_households_stays_unknown_not_zero() -> None:
    estimate = home_repair.estimate_area_job_demand({"id": "x", "single_households_65_plus": 0})
    assert estimate["jobs_per_month"] is None
    assert estimate["status"] == "INSUFFICIENT_INPUT"


def test_apply_to_area_is_opt_in_and_only_for_home_repair() -> None:
    laundry = {"id": "a", "service_type": "laundry", "service_duration_minutes": 60}
    assert home_repair.apply_to_area(dict(laundry)) == laundry
    repair = home_repair.apply_to_area({"id": "b", "service_type": "home_repair"})
    assert repair["service_duration_minutes"] == home_repair.planned_visit_minutes()
    assert repair["service_duration_minutes"] % 5 == 0
    assert repair["home_repair_profile"] == home_repair.PROFILE_ID


def test_provider_fit_statuses() -> None:
    faucet = home_repair.job_by_id("faucet_part")
    full = {"max_job_minutes": 180, "material_handling": "HIGH", "tools_available": 1}
    assert home_repair.provider_job_fit(full, faucet)["status"] == "FIT"
    short = {"max_job_minutes": 40, "material_handling": "HIGH", "tools_available": 1}
    assert home_repair.provider_job_fit(short, faucet)["status"] == "NOT_FIT"
    risky = {"max_job_minutes": 60, "material_handling": "HIGH", "tools_available": 1}
    assert home_repair.provider_job_fit(risky, home_repair.job_by_id("door_handle"))[
        "status"
    ] == "FIT_WITH_DURATION_RISK"
    no_material = {"max_job_minutes": 180, "material_handling": "NONE", "tools_available": 1}
    assert home_repair.provider_job_fit(no_material, faucet)["status"] == "NOT_FIT"
    no_tools = {"max_job_minutes": 180, "material_handling": "HIGH", "tools_available": 0}
    assert home_repair.provider_job_fit(no_tools, faucet)["reasons"] == ["TOOLS_MISSING"]


def test_unknown_capability_is_unverified_never_fit() -> None:
    unknown = {"max_job_minutes": None, "material_handling": "UNKNOWN", "tools_available": None}
    profile = home_repair.provider_profile_fit(unknown)
    assert profile["eligible_job_ids"] == []
    assert profile["all_jobs_verified"] is False
    assert all(fit["status"] == "UNVERIFIED" for fit in profile["job_fits"])


def test_capability_defaults_for_seeded_providers_are_unspecified(conn) -> None:
    row = conn.execute(
        "SELECT provider_id FROM provider_services WHERE service_type='home_repair' LIMIT 1"
    ).fetchone()
    assert row is not None
    capability = home_repair.get_capability(conn, row["provider_id"])
    assert capability["capability_provenance"] == "UNSPECIFIED"
    assert capability["material_handling"] == "UNKNOWN"
    assert capability["max_job_minutes"] is None


def test_set_capability_rejects_provider_without_home_repair(conn) -> None:
    assert home_repair.set_capability(
        conn, "no-such-provider", max_job_minutes=60, material_handling="LOW",
        tools_available=True, provenance="SIMULATED",
    ) is False


def test_api_profile_classify_and_capability(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("VILLAGECOVERAGE_APP_DB", str(tmp_path / "api-repair.sqlite"))
    client = TestClient(app)
    profile = client.get("/api/home-repair/profile").json()
    assert profile["profile_id"] == "SIMPLE_HOME_REPAIR"
    risky = client.post("/api/home-repair/classify", json={"text": "보일러 교체"}).json()
    assert risky["auto_accepted"] is False and risky["classification"] == "LICENSE_REQUIRED"
    simple = client.post("/api/home-repair/classify", json={"text": "전구 교체"}).json()
    assert simple["auto_accepted"] is True
    region = DEMO["default_region_id"]
    demand = client.get(f"/api/regions/{region}/home-repair/demand")
    assert demand.status_code == 200
    assert demand.json()["areas"] and demand.json()["provenance"].startswith("SIMULATED")
    missing = client.put(
        "/api/providers/nope/home-repair-capability", json={"material_handling": "LOW"}
    )
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "VALIDATION_ERROR"
    bad = client.put(
        "/api/providers/nope/home-repair-capability", json={"material_handling": "HUGE"}
    )
    assert bad.status_code == 422


def test_api_capability_roundtrip(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("VILLAGECOVERAGE_APP_DB", str(tmp_path / "api-cap.sqlite"))
    client = TestClient(app)
    assert client.get("/api/home-repair/profile").status_code == 200
    seed = client.put("/api/providers/nope/home-repair-capability", json={})
    assert seed.status_code == 404
    connection = database.connect()
    try:
        provider_id = connection.execute(
            "SELECT provider_id FROM provider_services WHERE service_type='home_repair' LIMIT 1"
        ).fetchone()["provider_id"]
    finally:
        connection.close()
    unknown = client.get(f"/api/providers/{provider_id}/home-repair-capability").json()
    assert unknown["eligible_job_ids"] == [] and unknown["all_jobs_verified"] is False
    saved = client.put(
        f"/api/providers/{provider_id}/home-repair-capability",
        json={"max_job_minutes": 180, "material_handling": "HIGH", "tools_available": True},
    )
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["capability"]["capability_provenance"] == "SIMULATED"
    assert len(body["eligible_job_ids"]) == len(home_repair.JOB_CATALOG)
