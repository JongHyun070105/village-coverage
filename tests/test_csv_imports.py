from datetime import date

import pytest

from backend.csv_imports import CSVImportFormatError, parse_csv, prepare_import_rows


def test_csv_parser_accepts_cp949_and_reports_canonical_row_numbers() -> None:
    payload = (
        "village_code,date,service_type,source_type,note\n"
        "1111111111,2026-10-01,laundry,phone,전화 조사\n"
    ).encode("cp949")
    digest, rows = parse_csv(payload, "demand_observations")

    assert len(digest) == 64
    assert rows[0]["row_number"] == 2
    assert rows[0]["values"]["note"] == "전화 조사"


@pytest.mark.parametrize(
    "payload",
    [
        b"village_code,date,service_type,note\n1111111111,2026-10-01,laundry,hello\n",
        b'village_code,date,service_type,source_type,note\n1111111111,2026-10-01,laundry,phone,"unclosed\n',
        b"village_code,village_code,date,service_type,source_type,note\n",
    ],
)
def test_csv_parser_rejects_missing_duplicate_or_malformed_columns(payload: bytes) -> None:
    with pytest.raises(CSVImportFormatError):
        parse_csv(payload, "demand_observations")


def test_csv_validation_distinguishes_invalid_codes_and_review_rows() -> None:
    today = date.today().isoformat()
    _, rows = parse_csv(
        (
            "village_code,date,service_type,source_type,note\n"
            f"1111111111,{today},laundry,phone,call\n"
            f"9999999999,{today},laundry,phone,call\n"
            f"1111111111,{today},laundry,phone,\n"
            f"1111111111,{today},medical,phone,call\n"
        ).encode(),
        "demand_observations",
    )
    result = prepare_import_rows(
        "demand_observations",
        rows,
        area_by_code={"1111111111": {"id": "area"}},
        provider_services={},
        service_policy={"laundry": "ALLOWED"},
    )

    assert [item["status"] for item in result] == [
        "IMPORTED",
        "FAILED",
        "NEEDS_REVIEW",
        "FAILED",
    ]
    assert "LEGAL_CODE_OUTSIDE_ENABLED_PILOTS" in result[1]["issues"]
    assert "NOTE_REQUIRED" in result[2]["issues"]
    assert "UNKNOWN_SERVICE_CODE" in result[3]["issues"]


def test_csv_validation_rejects_regulated_and_excluded_service_codes() -> None:
    today = date.today().isoformat()
    _, rows = parse_csv(
        (
            "village_code,date,service_type,source_type,note\n"
            f"1111111111,{today},medical_service,phone,의료 요청\n"
            f"1111111111,{today},mobility_support,phone,이동 요청\n"
        ).encode(),
        "demand_observations",
    )
    result = prepare_import_rows(
        "demand_observations",
        rows,
        area_by_code={"1111111111": {"id": "area"}},
        provider_services={},
        service_policy={"medical_service": "REGULATED", "mobility_support": "EXCLUDED"},
    )

    assert [row["status"] for row in result] == ["FAILED", "FAILED"]
    assert all("SERVICE_NOT_ALLOWED" in row["issues"] for row in result)


def test_csv_validation_bounds_notes_and_redacts_invalid_provider_identifiers() -> None:
    today = date.today().isoformat()
    note = "x" * 3001
    _, demand_rows = parse_csv(
        (
            "village_code,date,service_type,source_type,note\n"
            f"1111111111,{today},laundry,phone,{note}\n"
        ).encode(),
        "demand_observations",
    )
    demand_result = prepare_import_rows(
        "demand_observations",
        demand_rows,
        area_by_code={"1111111111": {"id": "area"}},
        provider_services={},
        service_policy={"laundry": "ALLOWED"},
    )[0]
    assert demand_result["status"] == "FAILED"
    assert "FIELD_TOO_LONG" in demand_result["issues"]
    assert len(demand_result["record"]["note"]) == 3000

    _, availability_rows = parse_csv(
        (
            "provider_id,date,start_time,end_time,service_type\n"
            f"010-1111-2222,{today},09:00,17:00,laundry\n"
        ).encode(),
        "provider_availability",
    )
    availability_result = prepare_import_rows(
        "provider_availability",
        availability_rows,
        area_by_code={},
        provider_services={},
        service_policy={"laundry": "ALLOWED"},
    )[0]
    assert availability_result["status"] == "FAILED"
    assert "010-1111-2222" not in availability_result["record"]["provider_id"]
    assert "PII_IN_PROVIDER_ID" in availability_result["issues"]
