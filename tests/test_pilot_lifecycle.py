from __future__ import annotations

import csv
import io
import json
import os
import sqlite3
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import database, pilot_lifecycle
from backend.main import app
from backend.timeutils import korea_today

client = TestClient(app)


def _csv(headers: list[str], rows: list[list[str]]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(headers)
    writer.writerows(rows)
    return output.getvalue().encode("utf-8")


def _import(context_id: str, template: str, headers: list[str], rows: list[list[str]]) -> dict:
    preview = client.post(
        f"/api/pilot-imports/{template}/preview?context_id={context_id}",
        content=_csv(headers, rows),
        headers={"Content-Type": "text/csv"},
    )
    assert preview.status_code == 201, preview.text
    batch = preview.json()
    assert batch["rows_error"] == 0, batch["rows"]
    confirmed = client.post(
        f"/api/pilot-imports/{batch['batch_id']}/confirm", json={"confirm": True}
    )
    assert confirmed.status_code == 200, confirmed.text
    return confirmed.json()


def test_pilot_promotion_rolls_back_confirmation_when_mapping_is_invalid(tmp_path, monkeypatch):
    monkeypatch.setenv("VILLAGECOVERAGE_APP_DB", str(tmp_path / "pilot-rollback.sqlite"))
    context = client.post(
        "/api/pilot-contexts",
        json={"context_name": "rollback", "region_code": "홍성군", "data_mode": "PILOT"},
    )
    assert context.status_code == 201, context.text
    context_id = context.json()["context_id"]
    headers = [
        "provider_org_id",
        "service_description",
        "service_type",
        "mapping_status",
        "regulation_level",
        "source_type",
    ]
    preview = client.post(
        f"/api/pilot-imports/provider_services/preview?context_id={context_id}",
        content=_csv(
            headers,
            [
                [
                    "no-org",
                    "세탁 지원",
                    "laundry",
                    "MAPPING_SUGGESTED",
                    "UNREGULATED",
                    "PROVIDER_SELF_REPORTED",
                ],
                [
                    "missing-org",
                    "세탁 지원",
                    "laundry",
                    "MAPPING_SUGGESTED",
                    "UNREGULATED",
                    "PROVIDER_SELF_REPORTED",
                ],
            ],
        ),
        headers={"Content-Type": "text/csv"},
    )
    assert preview.status_code == 201, preview.text
    batch_id = preview.json()["batch_id"]
    confirmation = client.post(f"/api/pilot-imports/{batch_id}/confirm", json={"confirm": True})
    assert confirmation.status_code == 422
    assert confirmation.json()["detail"]["code"] == "PROVIDER_MAPPING_INVALID"

    connection = database.connect(tmp_path / "pilot-rollback.sqlite")
    try:
        assert (
            connection.execute(
                "SELECT status FROM pilot_import_batches WHERE batch_id=?", (batch_id,)
            ).fetchone()[0]
            == "PREVIEWED"
        )
        assert connection.execute("SELECT COUNT(*) FROM pilot_import_records").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM pilot_promoted_records").fetchone()[0] == 0
    finally:
        connection.close()


def test_malformed_capacity_date_service_and_area_rows_never_promote(tmp_path, monkeypatch):
    monkeypatch.setenv("VILLAGECOVERAGE_APP_DB", str(tmp_path / "pilot-malformed.sqlite"))
    created = client.post(
        "/api/pilot-contexts",
        json={"context_name": "malformed fixture", "region_code": "홍성군", "data_mode": "PILOT"},
    )
    assert created.status_code == 201
    context_id = created.json()["context_id"]
    cases = [
        (
            "provider_capacity",
            [
                "provider_org_id",
                "service_type",
                "period_start",
                "period_end",
                "capacity_count",
                "capacity_unit",
                "source_type",
            ],
            [
                [
                    "org-1",
                    "laundry",
                    "2026-10-01",
                    "2026-10-31",
                    "-2",
                    "회",
                    "PROVIDER_SELF_REPORTED",
                ]
            ],
            "NEGATIVE_VALUE",
        ),
        (
            "provider_availability",
            [
                "provider_org_id",
                "service_type",
                "available_date",
                "available",
                "start_time",
                "end_time",
                "source_type",
            ],
            [
                [
                    "org-1",
                    "laundry",
                    "not-a-date",
                    "true",
                    "09:00",
                    "12:00",
                    "PROVIDER_SELF_REPORTED",
                ]
            ],
            "INVALID_DATE_OR_AREA_CODE",
        ),
        (
            "provider_prices",
            [
                "provider_org_id",
                "service_type",
                "effective_date",
                "price_won",
                "price_basis",
                "source_type",
            ],
            [["org-1", "laundry", "2026-10-01", "0", "방문 1회", "PROVIDER_SELF_REPORTED"]],
            "ZERO_PRICE_NOT_ALLOWED",
        ),
        (
            "provider_prices",
            [
                "provider_org_id",
                "service_type",
                "effective_date",
                "price_won",
                "price_basis",
                "source_type",
            ],
            [
                [
                    "org-1",
                    "unknown-service",
                    "2026-10-01",
                    "25000",
                    "방문 1회",
                    "PROVIDER_SELF_REPORTED",
                ]
            ],
            "UNKNOWN_SERVICE_TYPE",
        ),
        (
            "demand_observations",
            [
                "region_code",
                "area_code",
                "observed_date",
                "service_type",
                "observed_count",
                "observation_kind",
                "note",
                "source_type",
            ],
            [
                [
                    "홍성군",
                    "not-a-code",
                    "2026-10-01",
                    "laundry",
                    "1",
                    "call",
                    "safe",
                    "LOCAL_AUTHORITY_INPUT",
                ]
            ],
            "INVALID_DATE_OR_AREA_CODE",
        ),
    ]
    for template, headers, rows, expected_issue in cases:
        preview = client.post(
            f"/api/pilot-imports/{template}/preview?context_id={context_id}",
            content=_csv(headers, rows),
            headers={"Content-Type": "text/csv"},
        )
        assert preview.status_code == 201, preview.text
        body = preview.json()
        assert body["rows_error"] == 1
        assert expected_issue in {issue["code"] for issue in body["rows"][0]["issues"]}
        confirmed = client.post(
            f"/api/pilot-imports/{body['batch_id']}/confirm", json={"confirm": True}
        )
        assert confirmed.status_code == 200, confirmed.text
        assert confirmed.json()["rows_imported"] == 0

    connection = database.connect(tmp_path / "pilot-malformed.sqlite")
    try:
        assert connection.execute("SELECT COUNT(*) FROM pilot_promoted_records").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM pilot_execution_logs").fetchone()[0] == 0
    finally:
        connection.close()


def test_pilot_mode_excludes_simulated_demand_instead_of_falling_back(tmp_path, monkeypatch):
    monkeypatch.setenv("VILLAGECOVERAGE_APP_DB", str(tmp_path / "pilot-isolation.sqlite"))
    created = client.post(
        "/api/pilot-contexts",
        json={"context_name": "actual pilot input", "region_code": "홍성군", "data_mode": "PILOT"},
    )
    assert created.status_code == 201
    context_id = created.json()["context_id"]
    today = korea_today()
    area_code = "4480031021"
    _import(
        context_id,
        "region_areas",
        [
            "area_code",
            "area_name",
            "latitude",
            "longitude",
            "population_total",
            "population_65_plus",
            "households_total",
            "source_date",
            "source_type",
        ],
        [
            [
                area_code,
                "Pilot area",
                "36.5",
                "126.6",
                "100",
                "40",
                "50",
                today.isoformat(),
                "LOCAL_AUTHORITY_INPUT",
            ]
        ],
    )
    _import(
        context_id,
        "demand_observations",
        [
            "region_code",
            "area_code",
            "observed_date",
            "service_type",
            "observed_count",
            "observation_kind",
            "note",
            "source_type",
        ],
        [
            [
                "홍성군",
                area_code,
                (today - timedelta(days=offset)).isoformat(),
                "home_repair",
                "2",
                "simulated",
                "synthetic demand must stay out",
                "SIMULATED",
            ]
            for offset in range(5)
        ],
    )
    result = client.post(
        f"/api/pilot-contexts/{context_id}/plans",
        json={"scenario": "balanced", "budget_won": 1_000_000},
    )
    assert result.status_code == 409, result.text
    assert result.json()["detail"]["code"] == "DATA_INSUFFICIENT"


def test_pilot_context_links_feedback_by_area_without_copying_private_text(tmp_path, monkeypatch):
    monkeypatch.setenv("VILLAGECOVERAGE_APP_DB", str(tmp_path / "pilot-feedback.sqlite"))
    context_response = client.post(
        "/api/pilot-contexts",
        json={
            "context_name": "synthetic feedback rehearsal",
            "region_code": "홍성군",
            "data_mode": "SYNTHETIC_REHEARSAL",
        },
    )
    assert context_response.status_code == 201, context_response.text
    context_id = context_response.json()["context_id"]
    area_code = "4480034021"
    _import(
        context_id,
        "region_areas",
        [
            "area_code", "area_name", "latitude", "longitude", "population_total",
            "population_65_plus", "households_total", "source_date", "source_type",
        ],
        [[area_code, "Synthetic village", "36.5", "126.6", "100", "40", "50",
          korea_today().isoformat(), "SIMULATED"]],
    )

    survey = client.post(
        f"/api/villages/{area_code}/surveys",
        json={
            "survey_type": "phone",
            "survey_date": korea_today().isoformat(),
            "service_type": "laundry",
            "frequency_per_month": 1,
            "free_text_note": "synthetic official survey fixture",
        },
    )
    assert survey.status_code == 201, survey.text
    feedback = client.post(
        "/api/feedback",
        json={
            "area_id": area_code,
            "service_type": "laundry",
            "feedback_type": "SERVICE_REQUEST",
            "description": "synthetic resident description must stay private",
            "contact": "010-1234-5678",
            "claim": {"claimed_frequency_per_month": 12},
        },
    )
    assert feedback.status_code == 201, feedback.text
    feedback_id = feedback.json()["feedback_id"]
    assert feedback.json()["conflict_ids"]

    linked = client.post(f"/api/pilot-contexts/{context_id}/feedback/{feedback_id}")
    assert linked.status_code == 201, linked.text
    assert linked.json()["unresolved_conflict_count"] == 1
    assert linked.json()["source_type"] == "RESIDENT_FEEDBACK"
    repeated = client.post(f"/api/pilot-contexts/{context_id}/feedback/{feedback_id}")
    assert repeated.status_code == 201, repeated.text

    detail = client.get(f"/api/pilot-contexts/{context_id}")
    assert detail.status_code == 200, detail.text
    assert len(detail.json()["resident_feedback"]) == 1
    summary = detail.json()["resident_feedback"][0]
    assert summary["feedback_id"] == feedback_id
    assert summary["area_code"] == area_code
    assert summary["unresolved_conflict_count"] == 1
    assert "description" not in summary
    assert "contact" not in summary
    assert "010-1234-5678" not in detail.text
    assert "synthetic resident description must stay private" not in detail.text

    unmatched = client.post(
        f"/api/pilot-contexts/{context_id}/feedback/fb-not-a-real-id"
    )
    assert unmatched.status_code == 404


def test_same_pilot_context_reaches_optimizer_approval_execution_and_actuals(tmp_path, monkeypatch):
    monkeypatch.setenv("VILLAGECOVERAGE_APP_DB", str(tmp_path / "pilot-loop.sqlite"))
    context_response = client.post(
        "/api/pilot-contexts",
        json={
            "context_name": "synthetic rehearsal test",
            "region_code": "홍성군",
            "data_mode": "SYNTHETIC_REHEARSAL",
        },
    )
    assert context_response.status_code == 201, context_response.text
    context_id = context_response.json()["context_id"]
    today = korea_today()
    area_codes = [str(4480034021 + index) for index in range(16)]

    _import(
        context_id,
        "region_areas",
        [
            "area_code",
            "area_name",
            "latitude",
            "longitude",
            "population_total",
            "population_65_plus",
            "households_total",
            "source_date",
            "source_type",
        ],
        [
            [
                code,
                f"Synthetic QA 마을 {index + 1}",
                f"{36.51 + index / 1000:.3f}",
                f"{126.61 + index / 1000:.3f}",
                "420",
                "160",
                "210",
                today.isoformat(),
                "PUBLIC_DATA",
            ]
            for index, code in enumerate(area_codes)
        ],
    )
    _import(
        context_id,
        "demand_observations",
        [
            "region_code",
            "area_code",
            "observed_date",
            "service_type",
            "observed_count",
            "observation_kind",
            "note",
            "source_type",
        ],
        [
            [
                "홍성군",
                code,
                (today - timedelta(days=offset)).isoformat(),
                "home_repair",
                "2",
                "synthetic observation",
                "synthetic rehearsal row",
                "SIMULATED",
            ]
            for code in area_codes
            for offset in range(5)
        ],
    )
    _import(
        context_id,
        "surveys",
        [
            "region_code", "area_code", "survey_date", "service_type", "survey_count",
            "eligible_population", "source_type", "note",
        ],
        [
            ["홍성군", area_codes[0], today.isoformat(), "home_repair", "1", "10",
             "SIMULATED", "synthetic survey fixture"],
            ["홍성군", area_codes[1], (today - timedelta(days=365)).isoformat(),
             "home_repair", "1", "10", "SIMULATED", "stale survey fixture"],
        ],
    )
    canonical_survey = client.post(
        f"/api/villages/{area_codes[0]}/surveys",
        json={
            "survey_type": "phone",
            "survey_date": today.isoformat(),
            "service_type": "home_repair",
            "frequency_per_month": 1,
            "free_text_note": "synthetic feedback conflict fixture",
        },
    )
    assert canonical_survey.status_code == 201, canonical_survey.text
    feedback = client.post(
        "/api/feedback",
        json={
            "area_id": area_codes[0],
            "service_type": "home_repair",
            "feedback_type": "SERVICE_REQUEST",
            "description": "synthetic rehearsal feedback",
            "claim": {"claimed_frequency_per_month": 12},
        },
    )
    assert feedback.status_code == 201, feedback.text
    assert feedback.json()["conflict_ids"]
    feedback_link = client.post(
        f"/api/pilot-contexts/{context_id}/feedback/{feedback.json()['feedback_id']}"
    )
    assert feedback_link.status_code == 201, feedback_link.text
    assert feedback_link.json()["unresolved_conflict_count"] == 1
    directory_ingest = client.post(
        "/api/provider-directory/ingest",
        json={
            "source_id": "DATA_GO_KR_15091502",
            "rows": [
                {
                    "name": "(주)홍성주거복지센터",
                    "source_record_id": "DATA_GO_KR_15091502:row-000933",
                    "organization_type": "지역",
                    "region_id": "pilot:홍성군",
                    "region_label": "충청남도 홍성군",
                    "region_code": "홍성군",
                    "service_hint": "집수리",
                    "public_service_description": "집수리",
                    "reference_date": "2025-12-31",
                    "public_contact_available": False,
                }
            ],
        },
    )
    assert directory_ingest.status_code == 201, directory_ingest.text
    assert directory_ingest.json()["inserted"] == 1
    org_headers = [
        "provider_org_id",
        "official_name",
        "organization_type",
        "region_code",
        "public_business_address",
        "public_contact_available",
        "source_id",
        "source_record_id",
        "source_snapshot",
        "provenance",
        "source_type",
    ]
    _import(
        context_id,
        "provider_organizations",
        org_headers,
        [
            [
                "org-1",
                "(주)홍성주거복지센터",
                "지역",
                "홍성군",
                "",
                "false",
                "DATA_GO_KR_15091502",
                "DATA_GO_KR_15091502:row-000933",
                "2025-12-31",
                "REAL_DIRECTORY",
                "OFFICIAL_DIRECTORY",
            ],
            [
                "org-2",
                "Synthetic provider B",
                "협동조합",
                "홍성군",
                "",
                "false",
                "SYNTHETIC_FIXTURE",
                "org-row-2",
                today.isoformat(),
                "SIMULATED",
                "SIMULATED",
            ],
        ],
    )
    service_headers = [
        "provider_org_id",
        "service_description",
        "service_type",
        "mapping_status",
        "regulation_level",
        "source_type",
    ]
    _import(
        context_id,
        "provider_services",
        service_headers,
        [
            [org, "간단 집수리", "home_repair", "MAPPING_SUGGESTED", "UNREGULATED", "SIMULATED"]
            for org in ("org-1", "org-2")
        ],
    )
    for org in ("org-1", "org-2"):
        mapped = client.post(
            f"/api/pilot-contexts/{context_id}/provider-service-mappings",
            json={
                "provider_org_id": org,
                "service_type": "home_repair",
                "decision": "VERIFIED_MAPPING",
                "reviewer_role": "REVIEWER",
                "note": "synthetic rehearsal mapping",
            },
        )
        assert mapped.status_code == 201, mapped.text

    availability_headers = [
        "provider_org_id",
        "service_type",
        "available_date",
        "available",
        "start_time",
        "end_time",
        "source_type",
    ]
    availability_rows = [
        [
            org,
            "home_repair",
            (today + timedelta(days=offset)).isoformat(),
            "true",
            "09:00",
            "17:00",
            "SIMULATED",
        ]
        for org in ("org-1", "org-2")
        for offset in range(1, 29)
    ]
    _import(context_id, "provider_availability", availability_headers, availability_rows)
    _import(
        context_id,
        "provider_capacity",
        [
            "provider_org_id",
            "service_type",
            "period_start",
            "period_end",
            "capacity_count",
            "capacity_unit",
            "source_type",
        ],
        [
            [
                org,
                "home_repair",
                today.isoformat(),
                (today + timedelta(days=35)).isoformat(),
                "80",
                "회",
                "SIMULATED",
            ]
            for org in ("org-1", "org-2")
        ],
    )
    def add_assumption(key, value):
        assumption = client.post(
            f"/api/pilot-contexts/{context_id}/assumptions",
            json={
                "assumption_key": key,
                "value": value,
                "reason": "deterministic synthetic rehearsal assumption",
                "provenance": "SIMULATED",
            },
        )
        assert assumption.status_code == 201, assumption.text

    add_assumption(
        "provider_base_locations", {"org-1": area_codes[0], "org-2": area_codes[0]}
    )
    add_assumption("service_duration_minutes", {"home_repair": 45})
    missing_price = client.post(
        f"/api/pilot-contexts/{context_id}/plans",
        json={"scenario": "balanced", "budget_won": 5_000_000},
    )
    assert missing_price.status_code == 409
    assert missing_price.json()["detail"]["code"] == "COST_UNKNOWN"

    _import(
        context_id,
        "provider_prices",
        [
            "provider_org_id", "service_type", "effective_date", "price_won",
            "price_basis", "source_type",
        ],
        [
            [org, "home_repair", today.isoformat(), "25000", "방문 1회", "SIMULATED"]
            for org in ("org-1", "org-2")
        ],
    )
    partial_route = [{
        "origin_id": area_codes[0], "destination_id": area_codes[1],
        "distance_m": 1010, "duration_s": 301,
    }]
    add_assumption("route_matrix", partial_route)
    with monkeypatch.context() as route_failure:
        route_failure.setattr(pilot_lifecycle, "get_cached", lambda *_args: None)
        unavailable_route = client.post(
            f"/api/pilot-contexts/{context_id}/plans",
            json={"scenario": "balanced", "budget_won": 5_000_000},
        )
    assert unavailable_route.status_code == 409
    assert unavailable_route.json()["detail"]["code"] == "ROUTE_MATRIX_UNAVAILABLE"

    complete_routes = [
        {
            "origin_id": origin,
            "destination_id": destination,
            "distance_m": 1000 + origin_index * 10 + destination_index,
            "duration_s": 300 + origin_index + destination_index,
        }
        for origin_index, origin in enumerate(area_codes)
        for destination_index, destination in enumerate(area_codes)
        if origin != destination
    ]
    add_assumption("route_matrix", complete_routes)

    plans = []
    for scenario in ("efficiency", "balanced", "underserved_first", "minimum_coverage"):
        created = client.post(
            f"/api/pilot-contexts/{context_id}/plans",
            json={"scenario": scenario, "budget_won": 5_000_000},
        )
        assert created.status_code == 201, created.text
        body = created.json()
        plans.append(body)
        assert body["pilot_context_id"] == context_id
        assert body["data_mode"] == "SYNTHETIC_REHEARSAL"
        assert body["plan"]["optimizer_version"] == "V5.1_BASELINE_DECOMPOSED"
        assert body["plan"]["planned_coverage"]["area_count"] == 16
        assert body["plan"]["total_cost_won"] > 0
        assert all(
            sources["home_repair"] == "PROVIDER_PRICE_IMPORT"
            for sources in body["plan"]["provider_cost_sources"].values()
        )
        assert body["data_snapshot"]["pilot_context_id"] == context_id
        assert body["data_snapshot"]["import_batch_ids"]
        assert {
            "warning": "STALE_SURVEYS_EXCLUDED", "count": 1,
        } in body["plan"]["evidence_warnings"]
        assert (
            body["data_snapshot"]["active_scenario_assumptions"]["service_duration_minutes"][
                "provenance"
            ]
            == "SIMULATED"
        )
        assert "SYNTHETIC FIELD-PILOT REHEARSAL" in body["provenance"]

    parent = plans[0]
    decline = client.post(
        f"/api/pilot-imports/provider_participation/preview?context_id={context_id}",
        content=_csv(
            [
                "provider_org_id",
                "plan_id",
                "service_type",
                "participation_status",
                "recorded_at",
                "source_type",
            ],
            [[
                "org-1", parent["plan_id"], "home_repair", "DECLINED", today.isoformat(),
                "SIMULATED",
            ]],
        ),
        headers={"Content-Type": "text/csv"},
    )
    assert decline.status_code == 201, decline.text
    decline_batch = client.post(
        f"/api/pilot-imports/{decline.json()['batch_id']}/confirm", json={"confirm": True}
    )
    assert decline_batch.status_code == 200, decline_batch.text
    replanned = client.post(
        f"/api/pilot-contexts/plans/{parent['plan_id']}/replan",
        json={"change_reason": "provider decline"},
    )
    assert replanned.status_code == 201, replanned.text
    version_two = replanned.json()
    assert version_two["pilot_context_id"] == context_id
    assert version_two["parent_plan_id"] == parent["plan_id"]
    assert version_two["plan_version"] == parent["plan_version"] + 1
    assert all(
        "org-1" not in str(item.get("provider_id")) for item in version_two["plan"]["rounds"]
    )

    submitted = client.post(
        f"/api/pilot-contexts/plans/{version_two['plan_id']}/approval",
        json={"action": "submit", "role": "PLANNER"},
    )
    assert submitted.status_code == 200, submitted.text
    changes = client.post(
        f"/api/pilot-contexts/plans/{version_two['plan_id']}/approval",
        json={
            "action": "request_changes",
            "role": "REVIEWER",
            "comment": "확정 가격의 기준일을 다시 확인해 주세요.",
        },
    )
    assert changes.status_code == 200, changes.text
    version_three = client.post(
        f"/api/pilot-contexts/plans/{version_two['plan_id']}/replan",
        json={"change_reason": "요청된 자료 기준일 반영"},
    )
    assert version_three.status_code == 201, version_three.text
    approved_plan = version_three.json()
    assert approved_plan["plan_version"] == version_two["plan_version"] + 1
    assert all(
        "org-1" not in str(item.get("provider_id")) for item in approved_plan["plan"]["rounds"]
    )
    assert (
        client.post(
            f"/api/pilot-contexts/plans/{approved_plan['plan_id']}/approval",
            json={"action": "submit", "role": "PLANNER"},
        ).status_code
        == 200
    )
    approval = client.post(
        f"/api/pilot-contexts/plans/{approved_plan['plan_id']}/approval",
        json={"action": "approve", "role": "REVIEWER"},
    )
    assert approval.status_code == 200, approval.text
    assert approval.json()["approval_status"] == "APPROVED"

    rounds = approved_plan["plan"]["rounds"]
    assert rounds, "the deterministic rehearsal should produce at least one planned round"
    round_item = rounds[0]
    execution = client.post(
        f"/api/pilot-imports/service_execution_logs/preview?context_id={context_id}",
        content=_csv(
            [
                "plan_id",
                "plan_version",
                "round_id",
                "provider_org_id",
                "region_code",
                "area_code",
                "service_type",
                "scheduled_date",
                "actual_date",
                "execution_status",
                "rounds",
                "actual_duration_minutes",
                "actual_cost_won",
                "completion_percent",
                "cancel_reason",
                "source_type",
            ],
            [
                [
                    approved_plan["plan_id"],
                    str(approved_plan["plan_version"]),
                    round_item["round_id"],
                    round_item["provider_org_id"],
                    "홍성군",
                    round_item["area_code"],
                    round_item["service_type"],
                    round_item["scheduled_date"],
                    round_item["scheduled_date"],
                    "COMPLETED",
                    "1",
                    "45",
                    "25000",
                    "100",
                    "",
                    "SERVICE_EXECUTION_LOG",
                ]
            ],
        ),
        headers={"Content-Type": "text/csv"},
    )
    assert execution.status_code == 201, execution.text
    execution_batch_id = execution.json()["batch_id"]
    execution_confirm = client.post(
        f"/api/pilot-imports/{execution_batch_id}/confirm", json={"confirm": True}
    )
    assert execution_confirm.status_code == 200, execution_confirm.text
    metrics = client.get(f"/api/pilot-contexts/plans/{approved_plan['plan_id']}/actuals")
    assert metrics.status_code == 200, metrics.text
    assert metrics.json()["execution_log_count"] == 1
    assert metrics.json()["actual_served_areas"] == 1
    assert metrics.json()["actual_cost_won"] == 25_000
    assert metrics.json()["cost_variance_won"] == "UNKNOWN"
    assert metrics.json()["planned_duration_minutes"] >= 45

    repeated = client.post(
        f"/api/pilot-imports/{execution_batch_id}/confirm", json={"confirm": True}
    )
    assert repeated.status_code == 200
    assert repeated.json()["promotion"]["idempotent"] is True
    after_repeat = client.get(
        f"/api/pilot-contexts/plans/{approved_plan['plan_id']}/actuals"
    )
    assert after_repeat.status_code == 200
    assert after_repeat.json()["execution_log_count"] == 1
    connection = database.connect(tmp_path / "pilot-loop.sqlite")
    try:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM pilot_execution_logs WHERE plan_id=?",
                (approved_plan["plan_id"],),
            ).fetchone()[0]
            == 1
        )
        original_json = connection.execute(
            "SELECT data_snapshot_json FROM pilot_plans WHERE plan_id=?",
            (approved_plan["plan_id"],),
        ).fetchone()[0]
        with pytest.raises(sqlite3.IntegrityError, match="PILOT_APPROVED_PLAN_IMMUTABLE"):
            connection.execute(
                "UPDATE pilot_plans SET plan_json=plan_json WHERE plan_id=?",
                (approved_plan["plan_id"],),
            )
        connection.rollback()
        assert json.loads(original_json)["pilot_context_id"] == context_id
    finally:
        connection.close()

    context_detail = client.get(f"/api/pilot-contexts/{context_id}").json()
    refreshed_plan = client.get(f"/api/pilot-contexts/plans/{approved_plan['plan_id']}").json()
    readiness = client.get(
        f"/api/pilot-setup/readiness?service_type=home_repair&context_id={context_id}"
    ).json()
    assert readiness["calibration"]["status"] != "LOCAL_VALIDATED_OPERATIONAL"
    connection = database.connect(tmp_path / "pilot-loop.sqlite")
    try:
        promoted_counts = {
            str(row["template_type"]): int(row["count"])
            for row in connection.execute(
                """SELECT template_type,COUNT(*) AS count FROM pilot_promoted_records
                   WHERE context_id=? GROUP BY template_type""",
                (context_id,),
            )
        }
        audit_events = [
            str(row["event_type"])
            for row in connection.execute(
                "SELECT event_type FROM audit_events WHERE subject_id IN (?,?,?)",
                (parent["plan_id"], version_two["plan_id"], approved_plan["plan_id"]),
            )
        ]
    finally:
        connection.close()
    rehearsal = {
        "label": "SYNTHETIC FIELD-PILOT REHEARSAL; NOT FIELD RESULTS",
        "pilot_context_id": context_id,
        "data_mode": "SYNTHETIC_REHEARSAL",
        "import_batches": context_detail["import_batch_ids"],
        "promoted_records": promoted_counts,
        "planning_run": {
            "context_id": context_id,
            "plan_ids": [item["plan_id"] for item in plans],
            "optimizer": "V5.1_BASELINE_DECOMPOSED",
            "same_context_for_all_scenarios": all(
                item["pilot_context_id"] == context_id for item in plans
            ),
        },
        "scenario_metrics": [
            {
                "scenario": item["scenario_key"],
                "plan_id": item["plan_id"],
                "planned_coverage": item["plan"]["planned_coverage"],
                "solver_status": item["plan"].get("solver_status"),
                "planned_round_count": len(item["plan"].get("rounds", [])),
                "planned_cost_won": item["plan"].get("total_cost_won")
                or item["plan"].get("budget_spent_won"),
            }
            for item in plans
        ],
        "replan": {
            "declined_provider_org_id": "org-1",
            "parent_plan_id": parent["plan_id"],
            "plan_id": version_two["plan_id"],
            "plan_version": version_two["plan_version"],
            "selected_provider_ids": sorted(
                {str(item["provider_id"]) for item in version_two["plan"]["rounds"]}
            ),
        },
        "approval": {
            "plan_id": approved_plan["plan_id"],
            "plan_version": approved_plan["plan_version"],
            "status": approval.json()["approval_status"],
            "changes_requested_on_parent": changes.json()["approval_status"],
            "audit_events": audit_events,
        },
        "execution": {
            "batch_id": execution_batch_id,
            "plan_id": approved_plan["plan_id"],
            "plan_version": approved_plan["plan_version"],
            "linked_round_id": round_item["round_id"],
            "status": "COMPLETED",
            "idempotent_reimport": repeated.json()["promotion"]["idempotent"],
        },
        "post_metrics": metrics.json(),
        "calibration_status": readiness["calibration"]["status"],
        "provenance": refreshed_plan["data_snapshot"]["provenance_records"],
        "resident_feedback": refreshed_plan["data_snapshot"]["resident_feedback"],
        "errors": [
            {
                "case": "missing_price",
                "code": missing_price.json()["detail"]["code"],
                "expected_fail_closed": True,
            },
            {
                "case": "route_unavailable",
                "code": unavailable_route.json()["detail"]["code"],
                "expected_fail_closed": True,
            },
            {
                "case": "stale_survey",
                "code": "STALE_SURVEYS_EXCLUDED",
                "expected_fail_closed": True,
            },
        ],
        "invariant_status": {
            "confirmed_data_promoted": bool(promoted_counts),
            "same_context_end_to_end": refreshed_plan["pilot_context_id"] == context_id,
            "all_scenarios_same_context": all(
                item["pilot_context_id"] == context_id for item in plans
            ),
            "optimizer_baseline_decomposed": refreshed_plan["plan"]["optimizer_version"]
            == "V5.1_BASELINE_DECOMPOSED",
            "provider_decline_replanned": all(
                "org-1" not in str(item.get("provider_id"))
                for item in version_two["plan"]["rounds"]
            ),
            "approved_plan_immutable": approval.json()["approval_status"] == "APPROVED",
            "execution_linked": metrics.json()["execution_log_count"] == 1,
            "resident_feedback_linked_with_conflict": (
                len(refreshed_plan["data_snapshot"]["resident_feedback"]) == 1
                and refreshed_plan["data_snapshot"]["resident_feedback"][0][
                    "unresolved_conflict_count"
                ] == 1
            ),
            "missing_price_fails_closed": missing_price.json()["detail"]["code"]
            == "COST_UNKNOWN",
            "missing_route_fails_closed": unavailable_route.json()["detail"]["code"]
            == "ROUTE_MATRIX_UNAVAILABLE",
            "stale_survey_excluded": {
                "warning": "STALE_SURVEYS_EXCLUDED", "count": 1,
            } in plans[0]["plan"]["evidence_warnings"],
            "synthetic_data_labeled": "SYNTHETIC FIELD-PILOT REHEARSAL"
            in refreshed_plan["provenance"],
            "synthetic_logs_do_not_promote_operational_calibration": (
                readiness["calibration"]["status"] != "LOCAL_VALIDATED_OPERATIONAL"
            ),
        },
    }
    assert all(rehearsal["invariant_status"].values())
    if os.environ.get("WRITE_PILOT_REHEARSAL_ARTIFACT") == "1":
        artifact_path = (
            Path(__file__).resolve().parents[1]
            / "artifacts"
            / "pilot_rehearsal_v5_2_completion.json"
        )
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text(
            json.dumps(rehearsal, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )


def test_real_directory_identity_accepts_local_provider_operations_in_pilot_mode(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("VILLAGECOVERAGE_APP_DB", str(tmp_path / "pilot-local-operations.sqlite"))
    created = client.post(
        "/api/pilot-contexts",
        json={"context_name": "local operations contract test", "region_code": "홍성군"},
    )
    assert created.status_code == 201, created.text
    context_id = created.json()["context_id"]
    today = korea_today()
    area_code = "4480034021"
    _import(
        context_id,
        "region_areas",
        [
            "area_code", "area_name", "latitude", "longitude", "population_total",
            "population_65_plus", "households_total", "source_date", "source_type",
        ],
        [[area_code, "Functional test area", "36.5", "126.6", "100", "40", "50",
          today.isoformat(), "PUBLIC_DATA"]],
    )
    _import(
        context_id,
        "demand_observations",
        [
            "region_code", "area_code", "observed_date", "service_type", "observed_count",
            "observation_kind", "note", "source_type",
        ],
        [["홍성군", area_code, (today - timedelta(days=day)).isoformat(), "home_repair",
          "1", "authority log", "non-identifying functional fixture", "LOCAL_AUTHORITY_INPUT"]
         for day in range(10)],
    )
    directory = client.post(
        "/api/provider-directory/ingest",
        json={
            "source_id": "DATA_GO_KR_15091502",
            "rows": [{
                "name": "(주)홍성주거복지센터",
                "source_record_id": "DATA_GO_KR_15091502:row-000933",
                "organization_type": "지역",
                "region_id": "pilot:홍성군",
                "region_label": "충청남도 홍성군",
                "region_code": "홍성군",
                "service_hint": "집수리",
                "public_service_description": "집수리",
                "reference_date": "2025-12-31",
                "public_contact_available": False,
            }],
        },
    )
    assert directory.status_code == 201, directory.text
    _import(
        context_id,
        "provider_organizations",
        [
            "provider_org_id", "official_name", "organization_type", "region_code",
            "public_business_address", "public_contact_available", "source_id",
            "source_record_id", "source_snapshot", "provenance", "source_type",
        ],
        [["org-real", "(주)홍성주거복지센터", "지역", "홍성군", "", "false",
          "DATA_GO_KR_15091502", "DATA_GO_KR_15091502:row-000933", "2025-12-31",
          "REAL_DIRECTORY", "OFFICIAL_DIRECTORY"]],
    )
    _import(
        context_id,
        "provider_services",
        [
            "provider_org_id", "service_description", "service_type", "mapping_status",
            "regulation_level", "source_type",
        ],
        [["org-real", "집수리", "home_repair", "MAPPING_SUGGESTED", "UNREGULATED",
          "PROVIDER_SELF_REPORTED"]],
    )
    mapping = client.post(
        f"/api/pilot-contexts/{context_id}/provider-service-mappings",
        json={
            "provider_org_id": "org-real", "service_type": "home_repair",
            "decision": "VERIFIED_MAPPING", "reviewer_role": "REVIEWER",
        },
    )
    assert mapping.status_code == 201, mapping.text
    availability_headers = [
        "provider_org_id", "service_type", "available_date", "available", "start_time",
        "end_time", "source_type",
    ]
    availability_rows = [
        ["org-real", "home_repair", (today + timedelta(days=day)).isoformat(), "true",
         "09:00", "15:00", "LOCAL_AUTHORITY_INPUT"]
        for day in range(1, 29)
    ]
    availability_batch = _import(
        context_id, "provider_availability", availability_headers, availability_rows
    )
    repeated_availability = client.post(
        f"/api/pilot-imports/provider_availability/preview?context_id={context_id}",
        content=_csv(availability_headers, availability_rows),
        headers={"Content-Type": "text/csv"},
    )
    assert repeated_availability.status_code == 201, repeated_availability.text
    assert repeated_availability.json()["batch_id"] == availability_batch["batch_id"]
    assert repeated_availability.json()["already_exists"] is True
    confirmed_again = client.post(
        f"/api/pilot-imports/{availability_batch['batch_id']}/confirm",
        json={"confirm": True},
    )
    assert confirmed_again.status_code == 200, confirmed_again.text
    assert confirmed_again.json()["already_confirmed"] is True
    availability_connection = database.connect(
        tmp_path / "pilot-local-operations.sqlite"
    )
    try:
        assert availability_connection.execute(
            """SELECT COUNT(*) FROM pilot_promoted_records
               WHERE context_id=? AND template_type='provider_availability'""",
            (context_id,),
        ).fetchone()[0] == 28
    finally:
        availability_connection.close()
    _import(
        context_id,
        "provider_capacity",
        [
            "provider_org_id", "service_type", "period_start", "period_end", "capacity_count",
            "capacity_unit", "source_type",
        ],
        [["org-real", "home_repair", today.isoformat(),
          (today + timedelta(days=35)).isoformat(), "20", "회", "LOCAL_AUTHORITY_INPUT"]],
    )
    _import(
        context_id,
        "provider_prices",
        [
            "provider_org_id", "service_type", "effective_date", "price_won", "price_basis",
            "source_type",
        ],
        [["org-real", "home_repair", today.isoformat(), "30000", "방문 1회",
          "PROVIDER_SELF_REPORTED"]],
    )
    for key, value in (
        ("provider_base_locations", {"org-real": area_code}),
        ("route_matrix", [{"origin_id": area_code, "destination_id": area_code,
                           "distance_m": 0, "duration_s": 0}]),
        ("service_duration_minutes", {"home_repair": 60}),
    ):
        assumption = client.post(
            f"/api/pilot-contexts/{context_id}/assumptions",
            json={
                "assumption_key": key,
                "value": value,
                "reason": "functional integration fixture",
            },
        )
        assert assumption.status_code == 201, assumption.text

    setup = client.get(f"/api/pilot-setup/readiness?context_id={context_id}")
    assert setup.status_code == 200, setup.text
    readiness_dimensions = {item["id"]: item for item in setup.json()["dimensions"]}
    assert readiness_dimensions["PROVIDER_DIRECTORY"]["status"] == "READY"
    assert readiness_dimensions["PROVIDER_OPERATIONS"]["status"] == "READY"
    assert readiness_dimensions["PRICING"]["status"] == "READY"
    assert readiness_dimensions["ROUTES"]["status"] == "READY"
    assert readiness_dimensions["EXECUTION_LOGS"]["status"] == "NOT_REQUIRED_YET"

    planned = client.post(
        f"/api/pilot-contexts/{context_id}/plans",
        json={"scenario": "balanced", "budget_won": 1_000_000},
    )
    assert planned.status_code == 201, planned.text
    body = planned.json()
    provider_input = body["plan"]["provider_inputs"][0]
    assert body["data_mode"] == "PILOT"
    assert provider_input["provenance"] == "REAL_DIRECTORY"
    assert provider_input["availability_source"] == "CONFIRMED_PILOT_IMPORT"
    assert provider_input["price_sources"]["home_repair"] == "PROVIDER_PRICE_IMPORT"
    assert body["plan"]["rounds"]
    provider_inputs = body["plan"]["provider_inputs"]
    assert [item["provider_org_id"] for item in provider_inputs] == ["org-real"]
    assert sum(item["provenance"] == "DEMO" for item in provider_inputs) == 0
    assert not any(
        item["source_type"] == "DEMO"
        for item in body["data_snapshot"]["provenance_records"]
    )
    availability_records = [
        item
        for item in body["data_snapshot"]["provenance_records"]
        if item["template_type"] == "provider_availability"
    ]
    assert availability_records
    assert all(item["source_type"] == "LOCAL_AUTHORITY_INPUT" for item in availability_records)
    snapshot = body["data_snapshot"]
    assert snapshot["optimizer_version"] == body["plan"]["optimizer_version"]
    assert snapshot["route_matrix_fingerprint"]
    assert snapshot["region_snapshot_id"] and snapshot["demand_snapshot_id"]
    assert snapshot["provider_snapshot_id"]
    assert availability_batch["batch_id"] in snapshot["import_batch_ids"]
    assert any(
        item["template_type"] == "provider_organizations"
        and item["source_id"] == "DATA_GO_KR_15091502"
        for item in snapshot["provenance_records"]
    )
    assert any(
        item["template_type"] == "provider_prices"
        and item["source_type"] == "PROVIDER_SELF_REPORTED"
        for item in snapshot["provenance_records"]
    )

    submitted = client.post(
        f"/api/pilot-contexts/plans/{body['plan_id']}/approval",
        json={"action": "submit", "role": "PLANNER"},
    )
    assert submitted.status_code == 200, submitted.text
    approved = client.post(
        f"/api/pilot-contexts/plans/{body['plan_id']}/approval",
        json={"action": "approve", "role": "REVIEWER"},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["approval_status"] == "APPROVED"
    original_plan = client.get(f"/api/pilot-contexts/plans/{body['plan_id']}").json()
    original_plan_json = json.dumps(original_plan["plan"], sort_keys=True)
    original_snapshot = json.dumps(original_plan["data_snapshot"], sort_keys=True)

    new_batch = _import(
        context_id,
        "demand_observations",
        [
            "region_code", "area_code", "observed_date", "service_type",
            "observed_count", "observation_kind", "note", "source_type",
        ],
        [[
            "홍성군", area_code, today.isoformat(), "home_repair", "2",
            "post-approval observation", "new confirmed local input", "LOCAL_AUTHORITY_INPUT",
        ]],
    )
    unchanged = client.get(f"/api/pilot-contexts/plans/{body['plan_id']}").json()
    assert unchanged["approval_status"] == "APPROVED"
    assert json.dumps(unchanged["plan"], sort_keys=True) == original_plan_json
    assert json.dumps(unchanged["data_snapshot"], sort_keys=True) == original_snapshot

    without_reason = client.post(
        f"/api/pilot-contexts/plans/{body['plan_id']}/replan",
        json={"change_reason": ""},
    )
    assert without_reason.status_code == 409
    assert without_reason.json()["detail"]["code"] == "CHANGE_REASON_REQUIRED"
    next_version = client.post(
        f"/api/pilot-contexts/plans/{body['plan_id']}/replan",
        json={"change_reason": f"새 import batch {new_batch['batch_id']} 반영"},
    )
    assert next_version.status_code == 201, next_version.text
    child = next_version.json()
    assert child["parent_plan_id"] == body["plan_id"]
    assert child["plan_version"] == original_plan["plan_version"] + 1
    assert child["approval_status"] == "DRAFT"
    assert child["data_snapshot"]["pilot_context_snapshot_id"] != original_plan[
        "data_snapshot"
    ]["pilot_context_snapshot_id"]
    assert new_batch["batch_id"] in child["data_snapshot"]["import_batch_ids"]
    unchanged_after_replan = client.get(f"/api/pilot-contexts/plans/{body['plan_id']}").json()
    assert unchanged_after_replan["approval_status"] == "APPROVED"
    assert json.dumps(unchanged_after_replan["plan"], sort_keys=True) == original_plan_json
