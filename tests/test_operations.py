"""Tests for Operations Mode attention layer and plan revision comparison (§25)."""

from __future__ import annotations

import json
from pathlib import Path

from starlette.testclient import TestClient

from backend import database
from backend.main import app
from backend.operations import build_operations_attention
from backend.plan_changes import build_plan_change_explanation
from backend.regions import DEFAULT_REGION_ID
from backend.timeutils import korea_today

client = TestClient(app)


def test_build_plan_change_explanation_includes_travel_and_uncovered_deltas() -> None:
    prev_rounds = [
        {
            "area_id": "area-1",
            "service_type": "laundry",
            "provider_id": "p1",
            "service_units": 2,
            "total_cost_won": 100_000,
            "travel_before_s": 1200,
            "travel_after_s": 1200,
        },
        {
            "area_id": "area-2",
            "service_type": "daily_necessities",
            "provider_id": "p2",
            "service_units": 1,
            "total_cost_won": 50_000,
            "travel_before_s": 600,
            "travel_after_s": 600,
        },
    ]
    next_rounds = [
        {
            "area_id": "area-1",
            "service_type": "laundry",
            "provider_id": "p1",
            "service_units": 2,
            "total_cost_won": 100_000,
            "travel_before_s": 1200,
            "travel_after_s": 1200,
        },
        # area-2 is removed/unmet in next rounds
    ]

    diff = build_plan_change_explanation(
        prev_rounds,
        next_rounds,
        reason="PROVIDER_FAILURE_OR_DECLINE",
    )

    assert diff["previous_total_cost_won"] == 150_000
    assert diff["current_total_cost_won"] == 100_000
    assert diff["total_cost_delta_won"] == -50_000

    assert diff["previous_travel_time_s"] == 3600
    assert diff["current_travel_time_s"] == 2400
    assert diff["travel_time_delta_s"] == -1200

    assert diff["previous_uncovered_count"] == 0
    assert diff["current_uncovered_count"] == 1
    assert diff["uncovered_delta"] == 1


def test_plan_change_uncovered_count_uses_the_complete_region_area_set() -> None:
    rounds = [
        {
            "area_id": "area-1",
            "service_type": "laundry",
            "provider_id": "p1",
            "service_units": 1,
            "total_cost_won": 100_000,
        }
    ]

    diff = build_plan_change_explanation(
        rounds,
        rounds,
        reason="PROVIDER_FAILURE_OR_DECLINE",
        area_ids=["area-1", "area-2", "area-3"],
    )

    assert diff["previous_uncovered_count"] == 2
    assert diff["current_uncovered_count"] == 2
    assert diff["uncovered_delta"] == 0


def test_operations_attention_endpoint_and_builder(tmp_path: Path, monkeypatch) -> None:
    db_file = tmp_path / "ops_test.sqlite"
    monkeypatch.setenv("VILLAGECOVERAGE_APP_DB", str(db_file))
    conn = database.connect(db_file)
    data = json.loads(database.ROOT.joinpath("data", "demo.json").read_text(encoding="utf-8"))
    try:
        database.seed_reference_data(conn, data)
        items = build_operations_attention(conn, DEFAULT_REGION_ID, None)
        assert isinstance(items, list)
    finally:
        conn.close()

    res = client.get("/api/operations/attention")
    assert res.status_code == 200
    body = res.json()
    assert "region_id" in body
    assert "total_attention_count" in body
    assert "attention_items" in body
    assert isinstance(body["attention_items"], list)


def test_operations_attention_surfaces_conflicts_declines_and_unmet_areas(
    tmp_path: Path,
) -> None:
    db_file = tmp_path / "ops_attention.sqlite"
    conn = database.connect(db_file)
    data = json.loads(database.ROOT.joinpath("data", "demo.json").read_text(encoding="utf-8"))
    region = next(item for item in data["regions"] if item["region_id"] == DEFAULT_REGION_ID)
    area = next(
        item
        for item in data["areas"]
        if item.get("region_id") == DEFAULT_REGION_ID
    )
    try:
        database.seed_reference_data(conn, data)
        database.seed_provider_data(conn, data)
        provider = database.list_providers(conn, DEFAULT_REGION_ID)[0]
        future_date = max(korea_today().isoformat(), "2030-01-01")

        conn.execute(
            """INSERT INTO demand_evidence_conflicts(
                   conflict_id, area_id, service_type, conflict_type,
                   evidence_survey_ids_json, values_json, status, provenance,
                   created_at, updated_at
               ) VALUES (?, ?, 'laundry', 'FREQUENCY_CONFLICT', '[]', '[]',
                         'REVIEW_REQUIRED', 'TEST FIXTURE', ?, ?)""",
            ("conflict-1", area["id"], future_date, future_date),
        )
        conn.execute(
            """INSERT INTO schedule_runs(
                   schedule_id, scenario_key, budget_won, summary_json,
                   provenance, created_at, region_id
               ) VALUES ('schedule-1', 'balanced', 0, '{}', 'TEST FIXTURE', ?, ?)""",
            (future_date, region["region_id"]),
        )
        conn.execute(
            """INSERT INTO service_rounds(
                   round_id, provider_id, area_id, service_type, round_date,
                   start_time, duration_minutes, estimated_compensation_won, provenance
               ) VALUES ('round-1', ?, ?, 'laundry', ?, '09:00', 60, 0, 'TEST FIXTURE')""",
            (provider["provider_id"], area["id"], future_date),
        )
        conn.execute(
            """INSERT INTO scheduled_rounds(
                   scheduled_round_id, schedule_id, service_round_id, provider_id,
                   area_id, service_type, scheduled_date, departure_time,
                   service_start_time, service_end_time, duration_minutes, service_units,
                   travel_before_s, travel_after_s, travel_distance_m, service_cost_won,
                   travel_cost_won, minimum_compensation_topup_won, total_cost_won,
                   provenance
               ) VALUES ('scheduled-1', 'schedule-1', 'round-1', ?, ?, 'laundry',
                         ?, '08:30', '09:00', '10:00', 60, 1, 0, 0, 0, 0, 0, 0, 0,
                         'TEST FIXTURE')""",
            (provider["provider_id"], area["id"], future_date),
        )
        conn.execute(
            """INSERT INTO provider_participations(
                   participation_id, provider_id, round_id, status, updated_at, provenance
               ) VALUES ('participation-1', ?, 'round-1', 'DECLINED', ?, 'TEST FIXTURE')""",
            (provider["provider_id"], future_date),
        )
        conn.commit()

        items = build_operations_attention(
            conn,
            DEFAULT_REGION_ID,
            {
                "minimum_coverage": {
                    "assignments": [
                        {
                            "area_id": area["id"],
                            "covered": True,
                            "minimum_frequency_met": False,
                            "primary_reason": "PROVIDER_CAPACITY_SHORTAGE",
                            "reason_explanation": "세탁 공급자의 가용 용량이 부족합니다.",
                            "suggested_action": "추가 세탁 공급자 확보",
                            "money_resolvable": False,
                        }
                    ]
                }
            },
        )
    finally:
        conn.close()

    categories = {item["category"] for item in items}
    assert categories == {"EVIDENCE_CONFLICT", "PROVIDER_DECLINE", "UNMET_COVERAGE"}
    conflict_item = next(item for item in items if item["category"] == "EVIDENCE_CONFLICT")
    assert area["name"] in conflict_item["title"]
    unmet_item = next(item for item in items if item["category"] == "UNMET_COVERAGE")
    assert area["name"] in unmet_item["title"]
    assert "세탁 공급자의 가용 용량이 부족합니다." in unmet_item["description"]
    assert "추가 세탁 공급자 확보" in unmet_item["description"]
    assert "예산 추가만으로 해결되지 않음" in unmet_item["description"]


def test_operations_attention_uses_proven_monthly_budget_gap(tmp_path: Path) -> None:
    db_file = tmp_path / "ops_budget_gap.sqlite"
    conn = database.connect(db_file)
    data = json.loads(database.ROOT.joinpath("data", "demo.json").read_text(encoding="utf-8"))
    area = next(item for item in data["areas"] if item.get("region_id") == DEFAULT_REGION_ID)
    try:
        database.seed_reference_data(conn, data)
        items = build_operations_attention(
            conn,
            DEFAULT_REGION_ID,
            {
                "minimum_coverage": {
                    "guarantee_feasible": True,
                    "budget_gap_won": 250_000,
                    "assignments": [
                        {
                            "area_id": area["id"],
                            "service_type": "laundry",
                            "covered": False,
                            "minimum_frequency_met": False,
                            "primary_reason": "SHARED_BUDGET_OR_CAPACITY",
                            "money_resolvable": False,
                        }
                    ],
                }
            },
        )
    finally:
        conn.close()

    unmet_item = next(item for item in items if item["category"] == "UNMET_COVERAGE")
    assert "250,000원" in unmet_item["description"]
    assert "예산 추가로 해결 가능" in unmet_item["description"]
    assert "추가 예산 250,000원 확보" in unmet_item["description"]
