from __future__ import annotations

import json
from copy import deepcopy
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import database, provider_directory, provider_fallback, scheduling
from backend.main import app
from backend.settings import PlanningPolicy
from backend.travel import Route, connect, put_cached

ROOT = Path(__file__).resolve().parents[1]
DEMO = json.loads((ROOT / "data" / "demo.json").read_text(encoding="utf-8"))
DAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


@pytest.fixture(autouse=True)
def single_month_calendar(monkeypatch):
    monkeypatch.setattr(scheduling, "korea_today", lambda: date(2026, 6, 1))


def build_fixture(tmp_path, *, provider_count=3, service="laundry", monthly=3, demand=2):
    connection = connect(tmp_path / "travel.sqlite")
    nodes = {}
    areas = []
    for index in range(3):
        area_id = f"a{index + 1}"
        nodes[area_id] = {"id": area_id, "anchor_lat": 36.5 + index * 0.01, "anchor_lng": 126.61}
        areas.append({
            "id": area_id, "name": area_id, "service_type": service,
            "simulated_monthly_demand": demand, "needs_survey": False, "population_total": 100,
            "elderly_ratio_65": 0.4, "single_households_65_plus": 12,
        })
    providers = []
    for index in range(provider_count):
        base = f"b{index + 1}"
        nodes[base] = {"id": base, "anchor_lat": 36.55 + index * 0.01, "anchor_lng": 126.65}
        providers.append({
            "provider_id": f"p{index + 1}", "name": f"p{index + 1}", "base_area_id": base,
            "supported_services": [service],
            "availability": [
                {"weekday": day, "start_time": "09:00", "end_time": "17:00"} for day in DAYS
            ],
            "max_monthly_rounds": monthly, "service_capacity": 2, "max_daily_hours": 6,
            "max_travel_time_minutes": 90, "minimum_compensation_won": 0,
        })
    ids = list(nodes)
    for o_index, origin in enumerate(ids):
        for d_index, destination in enumerate(ids):
            if origin != destination:
                distance = 4000 + 1000 * ((o_index + d_index) % 3)
                duration = 500 + 60 * ((o_index + d_index) % 4)
                put_cached(connection, nodes[origin], nodes[destination],
                           Route(origin, destination, distance, duration))
    return areas, providers, connection


def make_plan(areas, providers, connection, budget=3_000_000, scenario="balanced"):
    return scheduling.generate_provider_schedule(
        deepcopy(areas), deepcopy(providers), connection, budget, scenario)


def test_source_lifecycle_is_license_first() -> None:
    assert provider_directory.source_lifecycle("DATA_GO_KR_15155661")["status"] == "INGEST_BLOCKED"
    assert provider_directory.source_lifecycle("DATA_GO_KR_15091502")["status"] == "INGEST_ALLOWED"
    assert provider_directory.source_lifecycle("DATA_GO_KR_15090110")["status"] == "INGEST_ALLOWED"
    assert provider_directory.source_lifecycle("DATA_GO_KR_15080745")["status"] == "INGEST_ALLOWED"
    assert (
        provider_directory.source_lifecycle("DATA_GO_KR_15064216")["status"]
        == "LICENSE_VERIFIED"
    )
    assert provider_directory.source_lifecycle("KREI_R2025_23")["status"] == "LICENSE_VERIFIED"
    assert provider_directory.source_lifecycle("SOMETHING_NEW")["status"] == "DISCOVERED"
    assert {s["status"] for s in provider_directory.directory_source_report()} <= set(
        provider_directory.SOURCE_STATUSES)


@pytest.mark.parametrize("source_id", [
    "DATA_GO_KR_15155661", "DATA_GO_KR_15064216", "SOMETHING_NEW", "KREI_R2025_23",
])
def test_ingest_refused_without_verified_candidate_license(tmp_path, source_id) -> None:
    connection = database.connect(tmp_path / "dir.sqlite")
    with pytest.raises(Exception) as caught:
        provider_directory.ingest_rows(connection, source_id, [{"name": "가상 조합"}])
    assert getattr(caught.value, "status_code", None) == 422
    assert provider_directory.list_entries(connection) == []


def test_ingest_drops_pii_and_marks_real_existence_only(tmp_path) -> None:
    connection = database.connect(tmp_path / "dir.sqlite")
    result = provider_directory.ingest_rows(
        connection, "DATA_GO_KR_15091502",
        [{"name": "행복자활기업", "service_hint": "청소", "region_id": "r1",
          "phone": "010-1111-2222", "representative": "홍길동"},
         {"name": ""}, {"name": "행복자활기업", "region_id": "r1"}],
    )
    assert result["inserted"] == 1 and result["skipped"] == 2
    assert result["dropped_pii_fields"] == 2
    entries = provider_directory.list_entries(connection)
    assert entries[0]["existence_provenance"] == "REAL_DIRECTORY"
    assert "010-1111-2222" not in json.dumps(entries, ensure_ascii=False)
    assert "홍길동" not in json.dumps(entries, ensure_ascii=False)


def test_badges_keep_operations_simulated_even_when_existence_is_real(tmp_path) -> None:
    connection = database.connect(tmp_path / "dir.sqlite")
    database.seed_reference_data(connection, DEMO)
    database.seed_provider_data(connection, DEMO)
    provider_id = connection.execute("SELECT provider_id FROM providers LIMIT 1").fetchone()[0]
    assert provider_directory.provider_badges(connection, provider_id) == {
        "existence": "SIMULATED", "availability": "SIMULATED",
        "capacity": "SIMULATED", "price": "SIMULATED"}
    provider_directory.ingest_rows(connection, "DATA_GO_KR_15091502", [{"name": "실존 조직"}])
    entry_id = provider_directory.list_entries(connection)[0]["entry_id"]
    assert provider_directory.link_entry(connection, entry_id, provider_id)
    badges = provider_directory.provider_badges(connection, provider_id)
    assert badges["existence"] == "REAL_DIRECTORY"
    assert (badges["availability"], badges["capacity"], badges["price"]) == (
        "SIMULATED", "SIMULATED", "SIMULATED")


def test_fallbacks_satisfy_the_same_hard_constraints(tmp_path) -> None:
    areas, providers, connection = build_fixture(tmp_path)
    plan = make_plan(areas, providers, connection)
    assert plan["rounds"]
    routes = scheduling._route_rows(connection)
    result = provider_fallback.fallback_candidates(
        areas, providers, routes, PlanningPolicy(), plan["rounds"])
    by_id = {p["provider_id"]: p for p in providers}
    assert result["status"] == "CANDIDATES_ONLY"
    for row in result["rounds"]:
        assert [f["tier"] for f in row["fallbacks"]] == ["SECONDARY", "TERTIARY"][
            : len(row["fallbacks"])]
        costs = [f["estimated_total_cost_won"] for f in row["fallbacks"]]
        assert costs == sorted(costs)
        for fallback in row["fallbacks"]:
            provider = by_id[fallback["provider_id"]]
            assert fallback["provider_id"] != row["primary_provider_id"]
            assert row["service_type"] in provider["supported_services"]
            assert fallback["auto_contract"] is False
            assert fallback["requires_provider_confirmation"] is True


def test_no_fallback_when_only_one_provider(tmp_path) -> None:
    areas, providers, connection = build_fixture(tmp_path, provider_count=1)
    plan = make_plan(areas, providers, connection)
    result = provider_fallback.fallback_candidates(
        areas, providers, scheduling._route_rows(connection), PlanningPolicy(), plan["rounds"])
    assert result["rounds_without_fallback"] == result["round_count"] > 0
    assert result["fallback_coverage"] == 0


def test_fallback_rejects_provider_without_supported_service(tmp_path) -> None:
    areas, providers, connection = build_fixture(tmp_path)
    providers[1]["supported_services"] = ["daily_necessities"]
    providers[2]["supported_services"] = ["daily_necessities"]
    plan = make_plan(areas, providers[:1], connection)
    result = provider_fallback.fallback_candidates(
        areas, providers, scheduling._route_rows(connection), PlanningPolicy(), plan["rounds"])
    assert all(not row["has_fallback"] for row in result["rounds"])


def test_home_repair_fallback_requires_verified_capability(tmp_path) -> None:
    areas, providers, connection = build_fixture(tmp_path, service="home_repair", demand=1)
    plan = make_plan(areas, providers[:1], connection)
    routes = scheduling._route_rows(connection)
    unverified = provider_fallback.fallback_candidates(
        areas, providers, routes, PlanningPolicy(), plan["rounds"], capabilities={})
    assert all(not row["has_fallback"] for row in unverified["rounds"])
    assert all(set(row["rejected_reasons"].values()) == {"CAPABILITY_UNVERIFIED"}
               for row in unverified["rounds"])
    capable = {"max_job_minutes": 180, "material_handling": "HIGH", "tools_available": 1}
    verified = provider_fallback.fallback_candidates(
        areas, providers, routes, PlanningPolicy(), plan["rounds"],
        capabilities={"p2": capable, "p3": {**capable, "tools_available": 0}})
    chosen = {f["provider_id"] for row in verified["rounds"] for f in row["fallbacks"]}
    assert chosen == {"p2"}
    assert all(row["rejected_reasons"].get("p3") == "CAPABILITY_LOW"
               for row in verified["rounds"])


def test_monthly_capacity_blocks_fallback(tmp_path) -> None:
    areas, providers, connection = build_fixture(tmp_path, monthly=1)
    plan = make_plan(areas, providers, connection)
    used = {r["provider_id"] for r in plan["rounds"]}
    result = provider_fallback.fallback_candidates(
        areas, providers, scheduling._route_rows(connection), PlanningPolicy(), plan["rounds"])
    for row in result["rounds"]:
        for fallback in row["fallbacks"]:
            assert fallback["provider_id"] not in used


def test_reserve_ratio_is_planner_choice_only(tmp_path) -> None:
    areas, providers, connection = build_fixture(tmp_path)
    with pytest.raises(ValueError):
        provider_fallback.compare_reserve_policies(
            areas, providers, connection, 3_000_000, reserve_pct=7)


def test_reserve_comparison_is_deterministic_and_within_budget(tmp_path) -> None:
    areas, providers, connection = build_fixture(tmp_path)
    first = provider_fallback.compare_reserve_policies(
        areas, providers, connection, 3_000_000, reserve_pct=10, max_solver_seconds=2.0)
    second = provider_fallback.compare_reserve_policies(
        areas, providers, connection, 3_000_000, reserve_pct=10, max_solver_seconds=2.0)
    assert first == second
    options = {o["option"]: o for o in first["options"]}
    assert set(options) == set(provider_fallback.RESERVE_OPTIONS)
    assert all(o["budget_never_exceeded"] for o in options.values())
    assert options["BUDGET_RESERVE"]["planned_budget_won"] == 2_700_000
    assert options["NO_RESERVE"]["planned_budget_won"] == 3_000_000
    assert first["reserve_chosen_by"] == "PLANNER" and first["label"] == "SIMULATION"
    assert all(o["budget_never_exceeded"] for o in second["options"])
    assert (options["PROVIDER_FALLBACK"]["worst_zero_service_after_decline"]
            <= options["NO_RESERVE"]["worst_zero_service_after_decline"])


def test_zero_reserve_matches_full_budget_plan(tmp_path) -> None:
    areas, providers, connection = build_fixture(tmp_path)
    result = provider_fallback.compare_reserve_policies(
        areas, providers, connection, 3_000_000, reserve_pct=0, max_solver_seconds=2.0)
    options = {o["option"]: o for o in result["options"]}
    assert options["BUDGET_RESERVE"]["no_decline"] == options["NO_RESERVE"]["no_decline"]
    assert options["BUDGET_RESERVE"]["planned_budget_won"] == 3_000_000


def test_all_providers_decline_leaves_zero_service_and_never_invents_supply(tmp_path) -> None:
    areas, providers, connection = build_fixture(tmp_path, provider_count=1)
    result = provider_fallback.compare_reserve_policies(
        areas, providers, connection, 3_000_000, reserve_pct=15, max_solver_seconds=2.0)
    for option in result["options"]:
        assert option["worst_served_units_after_decline"] == 0
        assert option["worst_zero_service_after_decline"] == 3


def test_api_directory_and_reserve_validation(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("VILLAGECOVERAGE_APP_DB", str(tmp_path / "api-provider.sqlite"))
    client = TestClient(app)
    sources = client.get("/api/provider-directory/sources").json()["sources"]
    assert {s["source_id"]: s["status"] for s in sources} == {
        "DATA_GO_KR_15155661": "INGEST_BLOCKED",
        "DATA_GO_KR_15091502": "INGEST_ALLOWED",
        "DATA_GO_KR_15090110": "INGEST_ALLOWED",
        "DATA_GO_KR_15080745": "INGEST_ALLOWED",
    }
    blocked = client.post("/api/provider-directory/ingest", json={
        "source_id": "DATA_GO_KR_15155661", "rows": [{"name": "x"}]})
    assert blocked.status_code == 422
    ok = client.post("/api/provider-directory/ingest", json={
        "source_id": "DATA_GO_KR_15091502", "rows": [{
            "name": "실존 조직", "phone": "010", "address": "개인정보 원본 주소",
            "public_address": "공개 디렉터리 주소", "service_hint": "주거 생활지원",
        }]})
    assert ok.status_code == 201 and ok.json()["dropped_pii_fields"] == 2
    entry = client.get("/api/provider-directory/entries").json()["entries"][0]
    assert entry["public_address"] == "공개 디렉터리 주소"
    assert entry["service_hint"] == "주거 생활지원"
    provider_id = DEMO["providers"][0]["id"]
    linked = client.post(
        f"/api/provider-directory/entries/{entry['entry_id']}/link",
        json={"provider_id": provider_id},
    )
    assert linked.status_code == 200
    badges = client.get(f"/api/providers/{provider_id}/badges").json()
    assert badges["badges"]["existence"] == "REAL_DIRECTORY"
    assert badges["directory_entry"]["public_address"] == "공개 디렉터리 주소"
    region = DEMO["default_region_id"]
    bad = client.get(f"/api/regions/{region}/reserve-comparison",
                     params={"budget_won": 1000000, "reserve_pct": 7})
    assert bad.status_code == 422
    assert client.get("/api/providers/nope/badges").status_code == 404
