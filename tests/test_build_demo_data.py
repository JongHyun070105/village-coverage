from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import build_demo_data

ROOT = Path(__file__).resolve().parents[1]
ALLOWED_FACILITY_FIELDS = {
    "facility_type",
    "operating_status",
    "latitude",
    "longitude",
    "built_date",
    "floor_area_sqm",
    "source_reference_date",
    "source_dataset_id",
}


def test_licensed_buyeo_facilities_are_exactly_joined_and_minimized() -> None:
    areas = [
        {"legal_code": "4476025021", "county": "부여군", "town": "부여읍"},
        {"legal_code": "4476025022", "county": "부여군", "town": "부여읍"},
    ]
    rows = [
        {
            "시설명": "비공개 시설 이름",
            "시설유형": "경로당",
            "소재지도로명주소": "충청남도 부여군 부여읍 가상로 1",
            "소재지지번주소": "충청남도 부여군 부여읍 가상리 1",
            "위도": "36.281",
            "경도": "126.913",
            "영업상태명": "영업",
            "전화번호": "041-000-0000",
            "건립일자": "2001-01-01",
            "건물면적": "64.5",
            "관리기관명": "부여군",
            "데이터기준일자": "2026-08-26",
        },
        {
            "시설유형": "마을회관",
            "소재지도로명주소": "충청남도 부여군 부여읍 다른로 2",
            "소재지지번주소": "충청남도 부여군 부여읍 다른리 2",
            "위도": "36.282",
            "경도": "126.914",
            "영업상태명": "영업",
            "건립일자": "",
            "건물면적": "",
            "데이터기준일자": "2026-08-26",
        },
        {
            "시설유형": "경로당",
            "소재지지번주소": "충청남도 아산시 음봉면 가상리",
            "위도": "36.9",
            "경도": "127.0",
            "데이터기준일자": "2026-08-26",
        },
    ]
    minimized = build_demo_data.minimize_buyeo_facilities(
        rows,
        areas,
        lambda lat, _lng: ("4476025021" if lat == 36.281 else "4476025022", ""),
    )

    assert set(minimized) == {"4476025021", "4476025022"}
    assert len(minimized["4476025021"]) == len(minimized["4476025022"]) == 1
    facility = minimized["4476025021"][0]
    assert set(facility) == ALLOWED_FACILITY_FIELDS
    assert facility["source_dataset_id"] == build_demo_data.BUYEO_FACILITY_SOURCE_ID
    serialized = json.dumps(minimized, ensure_ascii=False)
    assert "비공개 시설 이름" not in serialized
    assert "041-000-0000" not in serialized
    assert "가상로" not in serialized
    assert "관리기관명" not in serialized


def test_licensed_buyeo_ingestion_fails_closed_when_terms_are_not_unrestricted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def fake_request(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            return 200, "text/html", build_demo_data.BUYEO_FACILITY_PUBLIC_PK.encode(), None
        provider = "충청남도 부여군".encode()
        return 200, "text/html", provider + " 이용허락범위 확인 필요".encode(), None

    monkeypatch.setattr(build_demo_data, "_request", fake_request)

    with pytest.raises(RuntimeError, match="reuse terms"):
        build_demo_data.fetch_licensed_buyeo_facilities()

    assert calls == 2


def test_checked_in_buyeo_facility_rows_match_explicit_source_terms() -> None:
    demo = json.loads((ROOT / "data" / "demo.json").read_text(encoding="utf-8"))
    source = demo["source_data"]
    buyeo = [
        area
        for area in demo["areas"]
        if area.get("county") == "부여군" and area.get("town") == "부여읍"
    ]
    facilities = [facility for area in buyeo for facility in area.get("facilities", [])]

    assert source["licensed_facility_detail_reuse_terms"] == "이용허락범위 제한 없음"
    assert source["licensed_facility_detail_rows"] == len(facilities) == 51
    assert (
        source["licensed_facility_detail_areas"]
        == len([area for area in buyeo if area.get("facilities")])
        == 22
    )
    assert len(buyeo) == 22
    assert all(set(facility) == ALLOWED_FACILITY_FIELDS for facility in facilities)
    assert all(
        facility["source_dataset_id"] == build_demo_data.BUYEO_FACILITY_SOURCE_ID
        for facility in facilities
    )
    assert all(
        not area.get("facilities")
        for area in demo["areas"]
        if area.get("county") != "부여군" or area.get("town") != "부여읍"
    )
