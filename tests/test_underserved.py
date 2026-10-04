from __future__ import annotations

import json
import sqlite3
from copy import deepcopy
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import database, scheduling, underserved
from backend.main import app
from backend.scheduling import generate_provider_schedule
from backend.travel import Route, connect, put_cached
from backend.underserved import (
    DEFAULT_UNDERSERVED_POLICY,
    UnderservedPolicy,
    compute_metric,
    month_label,
)

ROOT = Path(__file__).resolve().parents[1]
DEMO = json.loads((ROOT / "data" / "demo.json").read_text(encoding="utf-8"))
AS_OF = "2026-06"


@pytest.fixture(autouse=True)
def single_month_calendar(monkeypatch):
    monkeypatch.setattr(scheduling, "korea_today", lambda: date(2026, 6, 1))


def rows_served_until(months_ago: int | None, count: int = 12):
    base = underserved.month_index(AS_OF)
    out = []
    for ago in range(count - 1, -1, -1):
        served = months_ago is not None and ago >= months_ago
        out.append({"month": month_label(base - ago), "rounds_delivered": 2 if served else 0,
                    "provenance": "REAL_REPORTED"})
    return out


@pytest.mark.parametrize(
    ("months_ago", "expected"),
    [(0, "RECENTLY_SERVED"), (2, "RECENTLY_SERVED"), (3, "WAITING"), (5, "WAITING"),
     (6, "LONG_UNSERVED"), (11, "LONG_UNSERVED"), (None, "CHRONICALLY_UNSERVED")],
)
def test_status_boundaries_follow_policy(months_ago, expected) -> None:
    metric = compute_metric("a", "laundry", rows_served_until(months_ago), as_of_month=AS_OF)
    assert metric.status == expected
    assert metric.points == DEFAULT_UNDERSERVED_POLICY.status_points[expected]


def test_thresholds_are_configuration_not_code() -> None:
    strict = UnderservedPolicy(
        recently_served_max_months=0, waiting_max_months=1, long_unserved_max_months=2
    )
    strict.validate()
    metric = compute_metric("a", "laundry", rows_served_until(3), as_of_month=AS_OF, policy=strict)
    assert metric.status == "CHRONICALLY_UNSERVED"
    with pytest.raises(ValueError):
        UnderservedPolicy(waiting_max_months=1).validate()
    with pytest.raises(ValueError):
        UnderservedPolicy(status_points={"WAITING": 1}).validate()


def test_missing_history_is_unknown_not_zero_service() -> None:
    assert compute_metric("a", "laundry", [], as_of_month=AS_OF).status == "UNKNOWN"
    assert compute_metric("a", "laundry", rows_served_until(None)[:2], as_of_month=AS_OF
                          ).status == "UNKNOWN"
    stale = [
        {"month": f"2025-{m:02d}", "rounds_delivered": 0, "provenance": "REAL_REPORTED"}
        for m in range(8, 12)
    ]
    metric = compute_metric("a", "laundry", stale, as_of_month=AS_OF)
    assert metric.status == "UNKNOWN"
    assert metric.basis == "HISTORY_STALE"
    assert metric.points == 0


def test_history_table_enforces_provenance_and_month(tmp_path) -> None:
    connection = database.connect(tmp_path / "u.sqlite")
    database.seed_reference_data(connection, DEMO)
    area = DEMO["areas"][0]
    with pytest.raises(sqlite3.IntegrityError):
        underserved.upsert_history_month(
            connection, area_id=area["id"], service_type="laundry", month="2026-13",
            rounds_delivered=1, provenance="REAL_REPORTED")
    with pytest.raises(sqlite3.IntegrityError):
        underserved.upsert_history_month(
            connection, area_id=area["id"], service_type="laundry", month="2026-05",
            rounds_delivered=1, provenance="MADE_UP")
    connection.close()


def test_demo_seed_is_deterministic_simulated_and_never_overwrites_real(tmp_path) -> None:
    connection = database.connect(tmp_path / "u.sqlite")
    database.seed_reference_data(connection, DEMO)
    areas = DEMO["areas"][:12]
    first = underserved.seed_simulated_history(connection, areas, as_of_month=AS_OF)
    snapshot = connection.execute(
        "SELECT * FROM area_service_history ORDER BY area_id, service_type, month"
    ).fetchall()
    assert first > 0
    assert {row["provenance"] for row in snapshot} == {"SIMULATED"}
    underserved.seed_simulated_history(connection, areas, as_of_month=AS_OF)
    again = connection.execute(
        "SELECT * FROM area_service_history ORDER BY area_id, service_type, month"
    ).fetchall()
    assert [tuple(r) for r in snapshot] == [tuple(r) for r in again]
    target = areas[0]
    underserved.upsert_history_month(
        connection, area_id=target["id"], service_type=target["service_type"],
        month=AS_OF, rounds_delivered=7, provenance="REAL_REPORTED")
    connection.commit()
    underserved.seed_simulated_history(connection, areas, as_of_month=AS_OF)
    row = connection.execute(
        "SELECT rounds_delivered, provenance FROM area_service_history"
        " WHERE area_id=? AND service_type=? AND month=?",
        (target["id"], target["service_type"], AS_OF)).fetchone()
    assert (row["rounds_delivered"], row["provenance"]) == (7, "REAL_REPORTED")
    connection.close()


def two_area_fixture(tmp_path, *, near_points: int, far_points: int):
    connection = connect(tmp_path / "travel.sqlite")
    base = {"id": "base", "anchor_lat": 36.5, "anchor_lng": 126.6}
    areas = []
    for index, (area_id, distance, points) in enumerate(
        [("near", 3000, near_points), ("far", 9000, far_points)]
    ):
        destination = {"id": area_id, "anchor_lat": 36.51 + index * 0.01, "anchor_lng": 126.61}
        put_cached(connection, base, destination, Route("base", area_id, distance, 600))
        put_cached(connection, destination, base, Route(area_id, "base", distance, 600))
        areas.append({
            "id": area_id, "name": area_id, "service_type": "laundry",
            "simulated_monthly_demand": 3, "needs_survey": False, "population_total": 100,
            "elderly_ratio_65": 0.4, "single_households_65_plus": 12,
            "underserved_points": points,
        })
    provider = {
        "provider_id": "p1", "name": "p1", "base_area_id": "base",
        "supported_services": ["laundry"],
        "availability": [
            {"weekday": d, "start_time": "09:00", "end_time": "17:00"}
            for d in ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday",
                      "sunday")
        ],
        "max_monthly_rounds": 1, "service_capacity": 1, "max_daily_hours": 6,
        "max_travel_time_minutes": 90, "minimum_compensation_won": 0,
    }
    return areas, [provider], connection


def served(result) -> set[str]:
    return {item["area_id"] for item in result["rounds"]}


def test_underserved_first_overrides_cheaper_route_when_history_says_so(tmp_path) -> None:
    areas, providers, connection = two_area_fixture(tmp_path, near_points=0, far_points=5)
    try:
        efficiency = generate_provider_schedule(
            deepcopy(areas), providers, connection, 2_000_000, "efficiency")
        underserved_first = generate_provider_schedule(
            deepcopy(areas), providers, connection, 2_000_000, "underserved_first")
        balanced = generate_provider_schedule(
            deepcopy(areas), providers, connection, 2_000_000, "balanced")
        assert served(efficiency) == {"near"}
        assert served(underserved_first) == {"far"}
        assert served(balanced) == {"far"}
        assert underserved_first["underserved_outcome"]["underserved_points_covered"] == 5
        assert underserved_first["underserved_outcome"]["label"] == "SIMULATION"
    finally:
        connection.close()


def test_without_history_balanced_and_underserved_first_do_not_invent_priority(tmp_path) -> None:
    areas, providers, connection = two_area_fixture(tmp_path, near_points=0, far_points=0)
    try:
        legacy = [{k: v for k, v in a.items() if k != "underserved_points"} for a in areas]
        with_zero = generate_provider_schedule(
            deepcopy(areas), providers, connection, 2_000_000, "balanced")
        without_key = generate_provider_schedule(
            legacy, providers, connection, 2_000_000, "balanced")
        assert with_zero["rounds"] == without_key["rounds"]
        tie = generate_provider_schedule(
            deepcopy(areas), providers, connection, 2_000_000, "underserved_first")
        assert served(tie) == {"near"}
    finally:
        connection.close()


def test_underserved_plan_is_deterministic_and_respects_budget(tmp_path) -> None:
    areas, providers, connection = two_area_fixture(tmp_path, near_points=1, far_points=5)
    try:
        first = generate_provider_schedule(
            deepcopy(areas), providers, connection, 2_000_000, "underserved_first")
        second = generate_provider_schedule(
            deepcopy(areas), providers, connection, 2_000_000, "underserved_first")
        assert first["rounds"] == second["rounds"]
        assert first["underserved_outcome"] == second["underserved_outcome"]
        assert first["budget_spent_won"] <= 2_000_000
        broke = generate_provider_schedule(
            deepcopy(areas), providers, connection, 0, "underserved_first")
        assert broke["rounds"] == []
        assert broke["underserved_outcome"]["ZERO_SERVICE_AREA_COUNT"] == 2
    finally:
        connection.close()


def test_plan_outcome_counts_zero_service_and_reduced_exclusion() -> None:
    areas = [
        {"id": "a", "simulated_monthly_demand": 2, "underserved_status": "CHRONICALLY_UNSERVED",
         "underserved_points": 5},
        {"id": "b", "simulated_monthly_demand": 2, "underserved_status": "RECENTLY_SERVED",
         "underserved_points": 0},
        {"id": "c", "simulated_monthly_demand": 0, "underserved_status": "LONG_UNSERVED",
         "underserved_points": 3},
    ]
    baseline = underserved.plan_outcome(areas, {"b": 2})
    plan = underserved.plan_outcome(areas, {"a": 2})
    assert baseline["ZERO_SERVICE_AREA_COUNT"] == 1
    assert plan["ZERO_SERVICE_AREA_COUNT"] == 1
    assert underserved.reduced_exclusion_count(plan, baseline) == 1
    assert underserved.reduced_exclusion_count(baseline, plan) == 0


def test_api_status_seed_and_four_policy_comparison(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("VILLAGECOVERAGE_APP_DB", str(tmp_path / "underserved-api.sqlite"))
    client = TestClient(app)
    region = DEMO["areas"][0]["region_id"]
    policy = client.get("/api/underserved/policy").json()
    assert policy["status_points"]["UNKNOWN"] == 0
    before = client.get(f"/api/regions/{region}/underserved").json()
    assert before["status_counts"]["UNKNOWN"] == len(before["areas"])
    seeded = client.post(f"/api/regions/{region}/underserved/demo-seed").json()
    assert seeded["provenance"] == "SIMULATED"
    after = client.get(f"/api/regions/{region}/underserved").json()
    assert after["status_counts"]["UNKNOWN"] < len(after["areas"])
    comparison = client.get(f"/api/regions/{region}/underserved/comparison").json()
    assert comparison["label"] == "SIMULATION"
    policies = [row["policy"] for row in comparison["rows"]]
    assert policies == ["request_count_only", "efficiency", "balanced", "underserved_first",
                        "minimum_coverage"]
    for row in comparison["rows"]:
        assert "ZERO_SERVICE_AREA_COUNT" in row
        assert "REDUCED_EXCLUSION_COUNT" in row
    assert "저장" not in comparison["notice"]
    rows = {row["policy"]: row for row in comparison["rows"]}
    assert (
        rows["underserved_first"]["underserved_points_covered"]
        >= rows["efficiency"]["underserved_points_covered"]
    )


def test_underserved_scenario_schedule_is_accepted_by_api(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("VILLAGECOVERAGE_APP_DB", str(tmp_path / "underserved-plan.sqlite"))
    client = TestClient(app)
    response = client.post(
        "/api/schedules", json={"scenario": "underserved_first", "budget_won": 5_000_000}
    )
    assert response.status_code == 201, response.text
    assert response.json()["scenario_key"] == "underserved_first"
