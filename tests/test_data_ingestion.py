from __future__ import annotations

from backend.data_ingestion import legal_code
from scripts.build_demo_data import _age_fields, _age_sum, _public_field_manifest, decode_csv


def test_decodes_observed_cp949_csv() -> None:
    header = "법정동코드,기준연월,계".encode("cp949")
    row = "4480034021,20260831,230".encode("cp949")
    fields, rows = decode_csv(header + b"\n" + row + b"\n")
    assert fields == ["법정동코드", "기준연월", "계"]
    assert rows[0]["법정동코드"] == "4480034021"


def test_age_columns_are_read_from_full_observed_schema() -> None:
    headers = [f"{age}세{sex}" for sex in ("남자", "여자") for age in range(110)]
    headers += ["110세이상 남자", "110세이상 여자"]
    fields = _age_fields(headers)
    row = {column: "1" for column in headers}
    assert len(fields) == 222
    assert _age_sum(row, fields, 65) == 92
    assert _age_sum(row, fields, 75) == 72
    assert _age_sum(row, fields, 80) == 62


def test_age_schema_fails_closed_when_required_range_is_absent() -> None:
    try:
        _age_fields(["0세남자", "110세이상 남자"])
    except ValueError as error:
        assert "age columns incomplete" in str(error)
    else:
        raise AssertionError("partial age schema should not be accepted")


def test_legal_code_is_canonicalized_without_name_guessing() -> None:
    assert legal_code("4480034021") == "4480034021"
    assert legal_code("4480034021.0") == "4480034021"
    assert legal_code(100001) == "0000100001"
    assert legal_code("") == ""


def test_manifest_describes_110_plus_and_omits_facility_contact_examples() -> None:
    manifest = _public_field_manifest(
        "data.go.kr/15114136",
        ["110세이상 남자", "flctNm", "telno", "lctnRoadNmAddr"],
        [
            {
                "110세이상 남자": "7",
                "flctNm": "시설 식별값",
                "telno": "[전화번호 비공개]",
                "lctnRoadNmAddr": "도로 주소",
            }
        ],
    )
    assert manifest[0]["meaning"] == "110세 이상 남성 인구 또는 1인세대 수."
    assert all(item["example"] is None for item in manifest[1:])
