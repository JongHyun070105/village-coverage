from __future__ import annotations

import csv
import io
import json
from datetime import date, timedelta

from fastapi.testclient import TestClient

from backend import database
from backend.main import app

client = TestClient(app)


def _csv(headers: list[str], rows: list[list[str]]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(headers)
    writer.writerows(rows)
    return output.getvalue().encode("utf-8")


def test_pilot_import_requires_preview_confirmation_and_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("VILLAGECOVERAGE_APP_DB", str(tmp_path / "pilot-import.sqlite"))
    template = client.get("/api/pilot-imports/templates")
    assert template.status_code == 200
    assert len(template.json()["templates"]) == 10

    area_headers = [
        "area_code",
        "area_name",
        "latitude",
        "longitude",
        "population_total",
        "population_65_plus",
        "households_total",
        "source_date",
        "source_type",
    ]
    area_file = _csv(
        area_headers,
        [
            [
                "4480031021",
                "오서리",
                "36.51",
                "126.61",
                "420",
                "160",
                "210",
                "2026-09-30",
                "PUBLIC_DATA",
            ]
        ],
    )
    area_preview = client.post(
        "/api/pilot-imports/region_areas/preview?file_name=areas.csv",
        content=area_file,
        headers={"Content-Type": "text/csv"},
    )
    assert area_preview.status_code == 201, area_preview.text
    area_batch = area_preview.json()
    assert area_batch["status"] == "PREVIEWED"
    assert (area_batch["rows_total"], area_batch["rows_valid"], area_batch["rows_error"]) == (
        1,
        1,
        0,
    )

    connection = database.connect(tmp_path / "pilot-import.sqlite")
    try:
        assert connection.execute("SELECT COUNT(*) FROM pilot_import_records").fetchone()[0] == 0
    finally:
        connection.close()

    confirmed_area = client.post(
        f"/api/pilot-imports/{area_batch['batch_id']}/confirm", json={"confirm": True}
    )
    assert confirmed_area.status_code == 200
    assert confirmed_area.json()["rows_imported"] == 1

    demand_headers = [
        "region_code",
        "area_code",
        "observed_date",
        "service_type",
        "observed_count",
        "observation_kind",
        "note",
        "source_type",
    ]
    demand_file = _csv(
        demand_headers,
        [
            [
                "홍성군",
                "4480031021",
                "2026-09-30",
                "laundry",
                "2",
                "전화",
                "010-1234-5678 요청",
                "SURVEY_INPUT",
            ],
            ["홍성군", "9999999999", "2026-09-30", "laundry", "1", "전화", "확인", "SURVEY_INPUT"],
            ["홍성군", "4480031021", "not-a-date", "laundry", "-1", "전화", "오류", "SURVEY_INPUT"],
        ],
    )
    preview = client.post(
        "/api/pilot-imports/demand_observations/preview?file_name=demand.csv",
        content=demand_file,
        headers={"Content-Type": "text/csv"},
    )
    assert preview.status_code == 201, preview.text
    batch = preview.json()
    assert (batch["rows_total"], batch["rows_warning"], batch["rows_error"]) == (3, 1, 2)
    preview_json = json.dumps(batch, ensure_ascii=False)
    assert "010-1234-5678" not in preview_json
    assert "PII_REDACTED" in preview_json

    connection = database.connect(tmp_path / "pilot-import.sqlite")
    try:
        assert (
            connection.execute(
                """SELECT COUNT(*) FROM pilot_import_records
                   WHERE template_type='demand_observations'"""
            ).fetchone()[0]
            == 0
        )
    finally:
        connection.close()

    failed = client.get(f"/api/pilot-imports/{batch['batch_id']}/failed.csv")
    assert failed.status_code == 200
    assert "UNKNOWN_REGION_CODE" in failed.text
    assert "not-a-date" in failed.text

    confirmed = client.post(
        f"/api/pilot-imports/{batch['batch_id']}/confirm", json={"confirm": True}
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["rows_imported"] == 1
    assert confirmed.json()["status"] == "IMPORTED_WITH_ERRORS"

    readiness = client.get("/api/pilot-setup/readiness?service_type=laundry&area_code=4480031021")
    assert readiness.status_code == 200
    assert readiness.json()["calibration"]["status"] == "LIMITED_SAMPLE"
    assert readiness.json()["calibration"]["promotion_policy"]["volume_alone_promotes"] is False
    assert readiness.json()["planning_gate"].startswith("LIMITED_PLANNING")

    repeated_preview = client.post(
        "/api/pilot-imports/demand_observations/preview?file_name=renamed.csv",
        content=demand_file,
        headers={"Content-Type": "text/csv"},
    )
    assert repeated_preview.status_code == 201
    assert repeated_preview.json()["batch_id"] == batch["batch_id"]
    assert repeated_preview.json()["already_exists"] is True
    repeated_confirm = client.post(
        f"/api/pilot-imports/{batch['batch_id']}/confirm", json={"confirm": True}
    )
    assert repeated_confirm.json()["rows_imported"] == 1
    assert repeated_confirm.json()["already_confirmed"] is True

    connection = database.connect(tmp_path / "pilot-import.sqlite")
    try:
        assert (
            connection.execute(
                """SELECT COUNT(*) FROM pilot_import_records
                   WHERE template_type='demand_observations'"""
            ).fetchone()[0]
            == 1
        )
        saved = connection.execute(
            """SELECT normalized_json FROM pilot_import_records
               WHERE template_type='demand_observations'"""
        ).fetchone()[0]
        assert "010-1234-5678" not in saved
    finally:
        connection.close()


def test_pilot_import_warns_for_missing_price_and_unknown_service(tmp_path, monkeypatch):
    monkeypatch.setenv("VILLAGECOVERAGE_APP_DB", str(tmp_path / "pilot-price.sqlite"))
    headers = [
        "provider_org_id",
        "service_type",
        "effective_date",
        "price_won",
        "price_basis",
        "source_type",
    ]
    response = client.post(
        "/api/pilot-imports/provider_prices/preview",
        content=_csv(
            headers, [["org-1", "unmapped-work", "2026-09-30", "", "", "PROVIDER_SELF_REPORTED"]]
        ),
        headers={"Content-Type": "text/csv"},
    )
    assert response.status_code == 201, response.text
    issues = response.json()["rows"][0]["issues"]
    assert {issue["code"] for issue in issues} == {"PRICE_MISSING", "UNKNOWN_SERVICE_TYPE"}
    assert response.json()["rows_error"] == 1


def test_pilot_import_accepts_ten_thousand_rows_without_dropping_them(tmp_path, monkeypatch):
    monkeypatch.setenv("VILLAGECOVERAGE_APP_DB", str(tmp_path / "pilot-10k.sqlite"))
    headers = [
        "area_code",
        "area_name",
        "latitude",
        "longitude",
        "population_total",
        "population_65_plus",
        "households_total",
        "source_date",
        "source_type",
    ]
    rows = [
        [
            str(1_000_000_000 + index),
            f"area-{index}",
            "36.5",
            "126.6",
            "100",
            "40",
            "50",
            "2026-09-30",
            "PUBLIC_DATA",
        ]
        for index in range(10_000)
    ]
    response = client.post(
        "/api/pilot-imports/region_areas/preview?file_name=ten-thousand.csv",
        content=_csv(headers, rows),
        headers={"Content-Type": "text/csv"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["rows_total"] == 10_000
    assert body["rows_valid"] == 10_000
    assert len(body["rows"]) == 10_000


def test_pilot_import_rejects_malformed_encoding_and_negative_price(tmp_path, monkeypatch):
    monkeypatch.setenv("VILLAGECOVERAGE_APP_DB", str(tmp_path / "pilot-invalid.sqlite"))
    bad_encoding = client.post(
        "/api/pilot-imports/region_areas/preview",
        content=b"\xff\xfe\x00",
        headers={"Content-Type": "text/csv"},
    )
    assert bad_encoding.status_code == 422

    headers = [
        "provider_org_id",
        "service_type",
        "effective_date",
        "price_won",
        "price_basis",
        "source_type",
    ]
    negative_price = client.post(
        "/api/pilot-imports/provider_prices/preview",
        content=_csv(
            headers, [["org-1", "laundry", "2026-09-30", "-1", "visit", "PROVIDER_SELF_REPORTED"]]
        ),
        headers={"Content-Type": "text/csv"},
    )
    assert negative_price.status_code == 201
    assert negative_price.json()["rows_error"] == 1
    assert negative_price.json()["rows"][0]["issues"][0]["code"] == "NEGATIVE_VALUE"


def test_calibration_promotes_only_after_coverage_sources_freshness_and_real_logs(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("VILLAGECOVERAGE_APP_DB", str(tmp_path / "calibration-gates.sqlite"))
    area_headers = [
        "area_code",
        "area_name",
        "latitude",
        "longitude",
        "population_total",
        "population_65_plus",
        "households_total",
        "source_date",
        "source_type",
    ]
    area = client.post(
        "/api/pilot-imports/region_areas/preview",
        content=_csv(
            area_headers,
            [
                [
                    "4480031021",
                    "오서리",
                    "36.51",
                    "126.61",
                    "420",
                    "160",
                    "210",
                    "2026-09-30",
                    "PUBLIC_DATA",
                ]
            ],
        ),
        headers={"Content-Type": "text/csv"},
    ).json()
    client.post(f"/api/pilot-imports/{area['batch_id']}/confirm", json={"confirm": True})

    today = date.today()
    observations = []
    surveys = []
    executions = []
    for index in range(30):
        demand_day = (today - timedelta(days=174 - index * 6)).isoformat()
        survey_day = (today - timedelta(days=175 - index * 6)).isoformat()
        observations.append(
            [
                "홍성군",
                "4480031021",
                demand_day,
                "laundry",
                "2",
                "현장",
                "수요 관측",
                "LOCAL_AUTHORITY_INPUT",
            ]
        )
        surveys.append(
            [
                "홍성군",
                "4480031021",
                survey_day,
                "laundry",
                "24",
                "30",
                "SURVEY_INPUT",
                "비식별 표본 조사",
            ]
        )
        executions.append(
            [
                "pilot-plan",
                "provider-x",
                "홍성군",
                "4480031021",
                "laundry",
                demand_day,
                demand_day,
                "COMPLETED",
                "1",
                "SERVICE_EXECUTION_LOG",
            ]
        )

    cases = [
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
            observations,
        ),
        (
            "surveys",
            [
                "region_code",
                "area_code",
                "survey_date",
                "service_type",
                "survey_count",
                "eligible_population",
                "source_type",
                "note",
            ],
            surveys,
        ),
        (
            "service_execution_logs",
            [
                "plan_id",
                "provider_org_id",
                "region_code",
                "area_code",
                "service_type",
                "scheduled_date",
                "executed_date",
                "execution_status",
                "rounds",
                "source_type",
            ],
            executions,
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
                    "provider-x",
                    "laundry",
                    today.isoformat(),
                    "true",
                    "09:00",
                    "12:00",
                    "PROVIDER_SELF_REPORTED",
                ]
            ],
        ),
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
                    "provider-x",
                    "laundry",
                    (today - timedelta(days=30)).isoformat(),
                    today.isoformat(),
                    "0",
                    "회",
                    "PROVIDER_SELF_REPORTED",
                ]
            ],
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
                    "provider-x",
                    "laundry",
                    today.isoformat(),
                    "25000",
                    "방문 1회",
                    "PROVIDER_SELF_REPORTED",
                ]
            ],
        ),
        (
            "provider_participation",
            [
                "provider_org_id",
                "plan_id",
                "service_type",
                "participation_status",
                "recorded_at",
                "source_type",
            ],
            [
                [
                    "provider-x",
                    "pilot-plan",
                    "laundry",
                    "OPTED_IN",
                    today.isoformat(),
                    "PROVIDER_SELF_REPORTED",
                ]
            ],
        ),
    ]
    batches = []
    for kind, headers, rows in cases:
        response = client.post(
            f"/api/pilot-imports/{kind}/preview",
            content=_csv(headers, rows),
            headers={"Content-Type": "text/csv"},
        )
        assert response.status_code == 201, response.text
        assert response.json()["rows_error"] == 0
        batches.append(response.json()["batch_id"])

    confirmed_demand = client.post(
        f"/api/pilot-imports/{batches[0]}/confirm", json={"confirm": True}
    )
    assert confirmed_demand.status_code == 200
    limited = client.get(
        "/api/pilot-setup/readiness?service_type=laundry&area_code=4480031021"
    ).json()["calibration"]
    assert limited["status"] == "LIMITED_SAMPLE"
    assert "source_diversity" in limited["missing_requirements"]

    confirmed_surveys = client.post(
        f"/api/pilot-imports/{batches[1]}/confirm", json={"confirm": True}
    )
    assert confirmed_surveys.status_code == 200
    calibrated = client.get(
        "/api/pilot-setup/readiness?service_type=laundry&area_code=4480031021"
    ).json()["calibration"]
    assert calibrated["status"] == "LOCAL_CALIBRATED"
    assert {
        "provider_availability",
        "provider_capacity",
        "actual_price",
        "participation_decision",
    }.issubset(calibrated["operational_missing_requirements"])

    for batch_id in batches[2:]:
        confirmed = client.post(f"/api/pilot-imports/{batch_id}/confirm", json={"confirm": True})
        assert confirmed.status_code == 200

    ready = client.get(
        "/api/pilot-setup/readiness?service_type=laundry&area_code=4480031021"
    ).json()["calibration"]
    assert ready["status"] == "LOCAL_VALIDATED_OPERATIONAL"
    assert ready["missing_requirements"] == []
    assert ready["operational_missing_requirements"] == []
