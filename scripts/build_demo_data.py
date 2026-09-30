#!/usr/bin/env python3
"""Fetch the current public sources and build a privacy-minimized Janggok demo.

Raw provider rows are processed in memory and are never written to the repository.
Only public, area-level aggregates, facility counts, and anchor coordinates are saved.
"""

from __future__ import annotations

import csv
import io
import json
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.data_ingestion import legal_code as _legal_code  # noqa: E402
from scripts.api_smoke_test import (  # noqa: E402
    DATA_GO_ROOT,
    FACILITY_URL,
    LEGAL_CODE_URL,
    _find_list,
    _find_record,
    _find_value,
    _json_payload,
    _load_config,
    _query_url,
    _request,
)

REGION_NAME = "홍성군 장곡면"
REGION_PROVINCE = "충청남도"
POPULATION_DATASET_ID = "15099158"
HOUSEHOLD_DATASET_ID = "15099160"
FACILITY_DATASET_ID = "15114136"
KAKAO_REGION_URL = "https://dapi.kakao.com/v2/local/geo/coord2regioncode.json"
KAKAO_ADDRESS_URL = "https://dapi.kakao.com/v2/local/search/address.json"
SEED = 2026


def decode_csv(body: bytes) -> tuple[list[str], list[dict[str, str]]]:
    try:
        text = body.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = body.decode("cp949")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ValueError("CSV header missing")
    return list(reader.fieldnames), [row for row in reader if row]


def download_dataset(dataset_id: str) -> tuple[list[str], list[dict[str, str]], int]:
    page_url = f"{DATA_GO_ROOT}/data/{dataset_id}/fileData.do"
    page_status, _, page_body, error = _request(page_url)
    if page_status != 200:
        raise RuntimeError(
            f"dataset page unavailable ({type(error).__name__ if error else page_status})"
        )
    page_text = page_body.decode("utf-8", errors="replace")
    match = re.search(r"atchFileId=(FILE_[A-Za-z0-9]+)&fileDetailSn=(\d+)", page_text)
    if not match:
        raise RuntimeError("dataset CSV attachment not found")
    url = _query_url(
        f"{DATA_GO_ROOT}/cmm/cmm/fileDownload.do",
        {"atchFileId": match.group(1), "fileDetailSn": match.group(2), "insertDataPrcus": "N"},
    )
    status, _, body, error = _request(url, timeout=60)
    if status != 200 or not body:
        raise RuntimeError(
            f"dataset download unavailable ({type(error).__name__ if error else status})"
        )
    fields, rows = decode_csv(body)
    date_match = re.search(r"_(20\d{6})(?:\D|$)", page_text)
    if not date_match:
        raise RuntimeError("dataset reference date not found on official page")
    return fields, rows, int(date_match.group(1))


def fetch_legal_code_sample(service_key: str) -> tuple[list[str], list[dict[str, Any]], int]:
    url = _query_url(
        LEGAL_CODE_URL,
        {"ServiceKey": service_key, "pageNo": 1, "numOfRows": 10, "type": "json"},
    )
    status, _, body, error = _request(url)
    payload = _json_payload(body)
    if status != 200 or not payload:
        raise RuntimeError(
            f"legal-code API unavailable ({type(error).__name__ if error else status})"
        )
    sample = _find_record(payload, {"region_cd", "locatadd_nm", "sido_cd"})
    rows = _find_list(payload, {"region_cd", "locatadd_nm", "sido_cd"})
    if not sample or not rows:
        raise RuntimeError("legal-code API response has no observed sample row")
    total = _find_value(payload, "totalCount")
    if not str(total).isdigit():
        raise RuntimeError("legal-code API totalCount missing")
    return list(sample), rows, int(total)


def fetch_facilities(service_key: str) -> tuple[list[dict[str, Any]], list[str], int, str | None]:
    records: list[dict[str, Any]] = []
    fields: list[str] = []
    page = 1
    total: int | None = None
    latest: str | None = None
    while total is None or len(records) < total:
        url = _query_url(
            FACILITY_URL,
            {"ServiceKey": service_key, "pageNo": page, "numOfRows": 1000, "type": "json"},
        )
        status, _, body, error = _request(url, timeout=60)
        try:
            payload = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError):
            payload = None
        if status != 200 or not isinstance(payload, dict):
            raise RuntimeError(
                f"facility API unavailable ({type(error).__name__ if error else status})"
            )
        header = payload.get("header", {})
        data = payload.get("body", {})
        if (
            not isinstance(header, dict)
            or str(header.get("resultCode")) != "00"
            or not isinstance(data, dict)
        ):
            raise RuntimeError("facility API did not return result code 00")
        try:
            total = int(data["totalCount"])
        except (KeyError, TypeError, ValueError):
            raise RuntimeError("facility API totalCount missing") from None
        items = data.get("items", {})
        batch = items.get("item", []) if isinstance(items, dict) else []
        if isinstance(batch, dict):
            batch = [batch]
        if not isinstance(batch, list):
            raise RuntimeError("facility API rows malformed")
        if batch:
            if not fields:
                fields = [str(name) for name in batch[0].keys()]
            records.extend(item for item in batch if isinstance(item, dict))
            for item in batch:
                date = str(item.get("crtrYmd", "")) if isinstance(item, dict) else ""
                if re.fullmatch(r"\d{4}-\d{2}-\d{2}", date) and (latest is None or date > latest):
                    latest = date
        if not batch or len(records) >= total:
            break
        page += 1
        time.sleep(0.12)
    if len(records) != total:
        raise RuntimeError(f"facility API returned {len(records)} of {total} rows")
    return records, fields, total, latest


def _number(value: Any) -> int:
    try:
        return int(float(str(value).replace(",", "").strip() or 0))
    except (TypeError, ValueError):
        return 0


def _age_fields(headers: list[str]) -> dict[tuple[int | None, str], str]:
    found: dict[tuple[int | None, str], str] = {}
    for column in headers:
        cleaned = column.replace(" ", "")
        match = re.fullmatch(r"(\d+)세(남자|여자)", cleaned)
        if match:
            found[(int(match.group(1)), match.group(2))] = column
            continue
        if cleaned in {"110세이상남자", "110세이상여자"}:
            sex = "남자" if cleaned.endswith("남자") else "여자"
            found[(None, sex)] = column
    for sex in ("남자", "여자"):
        missing = [age for age in range(110) if (age, sex) not in found]
        if missing or (None, sex) not in found:
            raise ValueError(f"observed CSV age columns incomplete for {sex}")
    return found


def _age_sum(row: dict[str, str], fields: dict[tuple[int | None, str], str], minimum: int) -> int:
    return sum(
        _number(row.get(column))
        for (age, _sex), column in fields.items()
        if age is None or age >= minimum
    )


def _request_json(url: str, key: str) -> dict[str, Any]:
    status, _, body, error = _request(url, headers={"Authorization": f"KakaoAK {key}"})
    if status != 200:
        raise RuntimeError(f"Kakao API unavailable ({type(error).__name__ if error else status})")
    try:
        payload = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise RuntimeError("Kakao API response was not JSON") from None
    if not isinstance(payload, dict):
        raise RuntimeError("Kakao API response shape invalid")
    return payload


def reverse_geocode(lat: float, lng: float, key: str) -> tuple[str, str]:
    payload = _request_json(_query_url(KAKAO_REGION_URL, {"x": lng, "y": lat}), key)
    documents = payload.get("documents", [])
    if not isinstance(documents, list):
        return "", ""
    for item in documents:
        if isinstance(item, dict) and item.get("region_type") == "B":
            return _legal_code(item.get("code")), str(item.get("address_name", ""))
    return "", ""


def geocode_address(address: str, key: str) -> tuple[float, float] | None:
    if not address:
        return None
    payload = _request_json(_query_url(KAKAO_ADDRESS_URL, {"query": address}), key)
    documents = payload.get("documents", [])
    if isinstance(documents, list) and documents and isinstance(documents[0], dict):
        try:
            return float(documents[0]["y"]), float(documents[0]["x"])
        except (KeyError, TypeError, ValueError):
            return None
    return None


def _public_field_manifest(
    source: str,
    fields: list[str],
    sample_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    sensitive = {"flctNm", "telno", "lctnRoadNmAddr", "lctnLotnoAddr", "mngInstNm", "insttNm"}
    descriptions = {
        "region_cd": ("10자리 법정동 지역코드.", "legal_code", "join key"),
        "sido_cd": ("시도 행정표준 코드.", None, None),
        "sgg_cd": ("시군구 행정표준 코드.", None, None),
        "umd_cd": ("읍면동 행정표준 코드.", None, None),
        "ri_cd": ("리 행정표준 코드.", None, None),
        "locatjumin_cd": ("주민등록 지역코드.", None, None),
        "locatjijuk_cd": ("지적 지역코드.", None, None),
        "locatadd_nm": ("지역 주소명.", "legal_name", None),
        "locat_order": ("지역 코드 서열.", None, None),
        "locat_rm": ("지역 코드 비고.", None, None),
        "locathigh_cd": ("상위 지역코드.", None, None),
        "locallow_nm": ("최하위 지역명.", "legal_name", None),
        "adpt_de": ("법정동 코드 생성일(YYYYMMDD).", None, None),
        "법정동코드": ("법정동 10자리 코드.", "legal_code", "join key"),
        "기준연월": ("통계 기준연월(YYYYMM).", "public_data_reference_date", None),
        "시도명": ("시도명.", "province", None),
        "시군구명": ("시군구명.", "county", None),
        "읍면동명": ("읍면동명.", "town", None),
        "리명": ("법정리명.", "village_name", None),
        "계": ("전체 인구 또는 1인세대 수.", "population_total or single_households_total", None),
        "남자": ("남성 인구 또는 남성 1인세대 수.", None, None),
        "여자": ("여성 인구 또는 여성 1인세대 수.", None, None),
        "flctNm": ("시설명.", None, "not persisted"),
        "flctTyp": ("시설 유형.", None, None),
        "lctnRoadNmAddr": ("도로명 주소.", None, "not persisted"),
        "lctnLotnoAddr": ("지번 주소.", None, "not persisted"),
        "lat": ("위도(WGS84 좌표).", "anchor_lat", "coordinate input"),
        "lot": ("경도(WGS84 좌표).", "anchor_lng", "coordinate input"),
        "busiCodNm": ("시설 운영 유형 코드명.", None, None),
        "telno": ("시설 연락 전화번호.", None, "not persisted"),
        "builYmd": ("시설 건축일.", None, None),
        "builArea": ("시설 건축 면적.", None, None),
        "mngInstNm": ("시설 관리기관명.", None, "not persisted"),
        "crtrYmd": ("원천 레코드 기준일.", None, None),
        "insttCode": ("제공기관 코드.", None, None),
        "insttNm": ("제공기관명.", None, "not persisted"),
    }
    for field in fields:
        values = [str(row.get(field, "")).strip() for row in sample_rows[:500]]
        nonempty = [value for value in values if value]
        meaning, internal_field, join_role = descriptions.get(
            field, ("원본 연령대별 남녀 인구 또는 1인세대 수.", None, None)
        )
        if field == "계" and source.endswith(POPULATION_DATASET_ID):
            meaning, internal_field = "총 주민등록 인구수.", "population_total"
        elif field == "계" and source.endswith(HOUSEHOLD_DATASET_ID):
            meaning, internal_field = "총 주민등록 1인세대 수.", "single_households_total"
        age_match = re.fullmatch(r"(?:(\d+)세|(110세이상)\s?)(남자|여자)", field)
        if age_match:
            age_label = "110세 이상" if age_match.group(2) else f"{age_match.group(1)}세"
            sex = "남성" if age_match.group(3) == "남자" else "여성"
            meaning = f"{age_label} {sex} 인구 또는 1인세대 수."
            internal_field = "age-specific source count"
        item: dict[str, Any] = {
            "source": source,
            "field": field,
            "meaning": meaning,
            "villagecoverage_field": internal_field,
            "join_role": join_role,
            "observed_nonempty_sample_rows": len(nonempty),
            "nullable_in_observed_sample": len(nonempty) < len(values),
            "example": None if field in sensitive else (nonempty[0] if nonempty else None),
        }
        result.append(item)
    return result


def write_data_dictionary(manifest: dict[str, Any]) -> None:
    titles = {
        "data.go.kr/15077871": "행정안전부 법정동 코드 OpenAPI",
        "data.go.kr/15099158": "행정안전부 주민등록 인구 CSV",
        "data.go.kr/15099160": "행정안전부 1인세대 CSV",
        "data.go.kr/15114136": "전국 마을회관·경로당 표준데이터 API",
    }
    lines = [
        "# 공개데이터 사전",
        "",
        (
            "아래 원본 필드는 현재 공식 API/CSV 응답에서 직접 읽었습니다. "
            "연령별 남녀 컬럼은 응답의 실제 컬럼명을 모두 열거합니다."
        ),
        (
            "Nullable 판정은 현재 응답 표본 기준입니다. 시설명·주소·전화번호·관리기관 "
            "예시는 개인정보와 접촉정보 노출 방지를 위해 저장하지 않았습니다."
        ),
        "",
        "## 핵심 내부 필드와 조인",
        "",
        "| 내부 필드 | 원본 필드 | 계산 또는 연결 방식 | Nullable |",
        "|---|---|---|---|",
        "| `legal_code` | 코드 API `region_cd`, 통계 `법정동코드` | 10자리 exact key | 아니오 |",
        "| `population_total` | 인구 `계` | 원본 총인구 | 아니오 |",
        "| 인구 `65_plus` / `75_plus` / `80_plus` | 원본 연령 컬럼 | 이상 남녀 합계 | 아니오 |",
        "| `single_households_total` | 1인세대 `계` | 원본 총 1인세대 | 아니오 |",
        "| 1인세대 `65_plus` / `75_plus` / `80_plus` | 원본 연령 컬럼 | 이상 남녀 합계 | 아니오 |",
        "| `anchor_lat` / `anchor_lng` | 시설 좌표와 Kakao 역지오코딩 | 대표 앵커 | 조건부 |",
        "| `facility_count` | 시설 API | exact legal-code에 매핑된 시설 레코드 수 | 아니오 |",
        "| `simulated_monthly_demand`, `demand_*` | 공개 원본에 없음 | 시뮬레이션 | 예 |",
        "",
        (
            "인구와 1인가구는 정확한 10자리 법정동 코드로 연결했습니다. "
            "행정리 이름만으로 통계 인구를 임의 분할하거나 보간하지 않습니다."
        ),
        "",
        "## 원본 필드 전체 목록",
        "",
    ]
    for source in manifest["sources"]:
        metadata = manifest.get("source_metadata", {}).get(source, {})
        lines.extend(
            [
                f"### {titles.get(source, source)} (`{source}`)",
                "",
                f"제공기관: {metadata.get('provider', '—')}",
                f"기준일/기준연월: {metadata.get('reference_date') or '—'}",
                f"관측 행 수: {metadata.get('record_count', '—')}",
                f"실제 호출/다운로드: `{metadata.get('endpoint', '—')}`",
                f"공식 안내: {metadata.get('catalog_url', '—')}",
                "",
                "| 원본 필드명 | 의미 | 내부 필드 | 조인 역할 | 실제 예시 | Nullable(표본) |",
                "|---|---|---|---|---|---|",
            ]
        )
        for item in manifest["columns"]:
            if item["source"] != source:
                continue
            example = item["example"] if item["example"] is not None else "—"
            internal = item["villagecoverage_field"] or "—"
            role = item["join_role"] or "—"
            nullable = "예" if item["nullable_in_observed_sample"] else "아니오"
            lines.append(
                "| "
                + " | ".join(
                    (
                        f"`{item['field']}`",
                        item["meaning"],
                        f"`{internal}`",
                        role,
                        f"`{example}`",
                        nullable,
                    )
                )
                + " |"
            )
        lines.append("")
    path = ROOT / "docs" / "DATA_DICTIONARY.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    data_key = _load_config("DATA_GO_KR_SERVICE_KEY")
    kakao_key = _load_config("KAKAO_REST_API_KEY")
    if not data_key or not kakao_key:
        print("Missing data.go.kr or Kakao settings; values were not inspected or printed.")
        return 2

    try:
        legal_code_fields, legal_code_rows, legal_code_count = fetch_legal_code_sample(data_key)
        population_fields, population_rows, population_date = download_dataset(
            POPULATION_DATASET_ID
        )
        household_fields, household_rows, household_date = download_dataset(HOUSEHOLD_DATASET_ID)
        all_facilities, facility_fields, facility_count, facility_date = fetch_facilities(data_key)
    except Exception as exc:
        print(f"Public data retrieval failed safely ({type(exc).__name__}).")
        return 1

    pop_rows = [
        row
        for row in population_rows
        if row.get("시도명", "").strip() == REGION_PROVINCE
        and row.get("시군구명", "").strip() == "홍성군"
        and row.get("읍면동명", "").strip() == "장곡면"
    ]
    hh_by_code = {_legal_code(row.get("법정동코드")): row for row in household_rows}
    pop_age = _age_fields(population_fields)
    hh_age = _age_fields(household_fields)
    pop_by_code: dict[str, dict[str, str]] = {}
    for row in pop_rows:
        code = _legal_code(row.get("법정동코드"))
        if not code or code in pop_by_code:
            raise RuntimeError("pilot population source has a missing or duplicate legal code")
        pop_by_code[code] = row
    if len(pop_by_code) < 10:
        raise RuntimeError("pilot region produced fewer than ten legal-ri areas")

    candidates = [
        item
        for item in all_facilities
        if "장곡면"
        in " ".join(str(item.get(key, "")) for key in ("lctnLotnoAddr", "lctnRoadNmAddr"))
    ]
    facilities_by_code: dict[str, list[dict[str, Any]]] = defaultdict(list)
    mapped = 0
    coordinate_count = 0
    reverse_failures = 0
    address_geocoded = 0
    text_area_hits: Counter[str] = Counter()
    unambiguous_text_matches = 0
    ambiguous_text_matches = 0
    no_text_matches = 0
    area_name_by_code = {
        code: str(row.get("리명", "")).strip() for code, row in pop_by_code.items()
    }
    for record in candidates:
        lat = lng = None
        try:
            raw_lat, raw_lng = (
                str(record.get("lat", "")).strip(),
                str(record.get("lot", "")).strip(),
            )
            if raw_lat and raw_lng:
                lat, lng = float(raw_lat), float(raw_lng)
                if not (-90 <= lat <= 90 and -180 <= lng <= 180):
                    lat = lng = None
        except ValueError:
            lat = lng = None
        if lat is None:
            address = str(record.get("lctnLotnoAddr") or record.get("lctnRoadNmAddr") or "")
            point = geocode_address(address, kakao_key)
            if point:
                lat, lng = point
                address_geocoded += 1
        if lat is None or lng is None:
            continue
        coordinate_count += 1
        try:
            code, _ = reverse_geocode(lat, lng, kakao_key)
        except Exception:
            code = ""
        if not code:
            reverse_failures += 1
            continue
        address_text = " ".join(
            str(record.get(key, "")) for key in ("lctnLotnoAddr", "lctnRoadNmAddr")
        ).replace(" ", "")
        address_hits = [
            candidate_code
            for candidate_code, area_name in area_name_by_code.items()
            if area_name and area_name.replace(" ", "") in address_text
        ]
        for candidate_code in address_hits:
            text_area_hits[candidate_code] += 1
        if len(address_hits) == 1:
            unambiguous_text_matches += 1
        elif len(address_hits) > 1:
            ambiguous_text_matches += 1
        else:
            no_text_matches += 1
        if code in pop_by_code:
            mapped += 1
            facilities_by_code[code].append({"lat": lat, "lng": lng})
        time.sleep(0.08)

    areas: list[dict[str, Any]] = []
    for code, pop_row in sorted(pop_by_code.items()):
        hh_row = hh_by_code.get(code)
        facilities = sorted(
            facilities_by_code.get(code, []), key=lambda row: (row["lat"], row["lng"])
        )
        pop_total = _number(pop_row.get("계"))
        elderly = {age: _age_sum(pop_row, pop_age, age) for age in (65, 75, 80)}
        singles_total = _number(hh_row.get("계")) if hh_row else 0
        singles_elderly = {
            age: _age_sum(hh_row, hh_age, age) if hh_row else 0 for age in (65, 75, 80)
        }
        hhi = elderly[65] / pop_total if pop_total else 0
        # Seeded simulated observations intentionally leave some areas low-data.
        stable = int(code[-3:])
        observation_count = [1, 2, 3, 4, 6, 8][(stable + SEED) % 6]
        demand_units = max(3, min(12, round(3 + hhi * 7 + (singles_total / max(pop_total, 1)) * 5)))
        demand_units += ((stable * 17 + SEED) % 5) - 2
        demand_units = max(2, demand_units)
        # No anchor gets disclosed if public facilities have no usable coordinate.
        anchor = facilities[len(facilities) // 2] if facilities else None
        areas.append(
            {
                "id": code,
                "legal_code": code,
                "name": f"장곡면 {pop_row.get('리명', '').strip()}".strip(),
                "province": pop_row.get("시도명", "").strip(),
                "county": pop_row.get("시군구명", "").strip(),
                "town": pop_row.get("읍면동명", "").strip(),
                "village_name": pop_row.get("리명", "").strip(),
                "population_total": pop_total,
                "population_65_plus": elderly[65],
                "population_75_plus": elderly[75],
                "population_80_plus": elderly[80],
                "elderly_ratio_65": round(elderly[65] / pop_total, 4) if pop_total else None,
                "elderly_ratio_75": round(elderly[75] / pop_total, 4) if pop_total else None,
                "elderly_ratio_80": round(elderly[80] / pop_total, 4) if pop_total else None,
                "single_households_total": singles_total,
                "single_households_65_plus": singles_elderly[65],
                "single_households_75_plus": singles_elderly[75],
                "single_households_80_plus": singles_elderly[80],
                "facility_count": len(facilities),
                "anchor_lat": round(anchor["lat"], 7) if anchor else None,
                "anchor_lng": round(anchor["lng"], 7) if anchor else None,
                "public_data_reference_date": str(population_date),
                "household_data_reference_date": str(household_date),
                "demand_observation_count": observation_count,
                "demand_data_count": observation_count,
                "demand_confidence": "조사 필요"
                if observation_count < 4
                else "주의"
                if observation_count < 7
                else "충분",
                "needs_survey": observation_count < 4,
                "simulated_monthly_demand": demand_units,
                "simulated_beneficiaries_per_service": 2 + ((stable + SEED) % 4),
                "service_type": "laundry"
                if stable % 3 == 0
                else "daily_necessities"
                if stable % 3 == 1
                else "home_repair",
                "data_provenance": "REAL PUBLIC DATA + SIMULATED FOR PRE-R&D",
            }
        )

    if not areas or any(area["anchor_lat"] is None for area in areas):
        raise RuntimeError("not every pilot service area has a coordinate anchor")

    pop_codes = {_legal_code(row.get("법정동코드")) for row in population_rows}
    household_codes = {_legal_code(row.get("법정동코드")) for row in household_rows}
    coords = {
        (round(row["lat"], 7), round(row["lng"], 7))
        for group in facilities_by_code.values()
        for row in group
    }
    area_covered = sum(bool(facilities_by_code.get(code)) for code in pop_by_code)
    text_matched_areas = set(text_area_hits)
    facility_data = {
        "region": REGION_NAME,
        "source_data": {
            "legal_code_endpoint": "StanReginCd.getStanReginCdList",
            "legal_code_records": legal_code_count,
            "population_dataset_id": POPULATION_DATASET_ID,
            "household_dataset_id": HOUSEHOLD_DATASET_ID,
            "facility_dataset_id": FACILITY_DATASET_ID,
            "population_reference_date": str(population_date),
            "household_reference_date": str(household_date),
            "facility_latest_update_date": facility_date,
            "population_rows": len(population_rows),
            "population_distinct_provinces": len({r.get("시도명", "") for r in population_rows}),
            "household_rows": len(household_rows),
            "household_distinct_provinces": len({r.get("시도명", "") for r in household_rows}),
            "facility_rows": facility_count,
        },
        "planning_defaults": {
            "seed": SEED,
            "currency": "KRW",
            "monthly_budget": 5_000_000,
            "minimum_services_per_area": 1,
            "simulation_notice": (
                "서비스 수요 및 공급자 운영조건은 Pre-R&D 검증을 위한 시뮬레이션 데이터입니다."
            ),
        },
        "providers": [
            {
                "id": f"sim-provider-{index}",
                "capacity_per_month": 60,
                "provenance": "SIMULATED FOR PRE-R&D",
            }
            for index in range(1, 4)
        ],
        "areas": areas,
    }
    _write(ROOT / "data" / "demo.json", facility_data)

    quality = {
        "region": REGION_NAME,
        "sources": facility_data["source_data"],
        "metrics": {
            "population_rows_with_unique_legal_code": len(pop_codes) == len(population_rows),
            "household_rows_with_unique_legal_code": len(household_codes) == len(household_rows),
            "population_household_code_intersection": len(pop_codes & household_codes),
            "household_codes_without_population_row": len(household_codes - pop_codes),
            "pilot_population_area_count": len(pop_by_code),
            "pilot_household_join_count": sum(code in hh_by_code for code in pop_by_code),
            "pilot_household_join_rate": round(
                sum(code in hh_by_code for code in pop_by_code) / len(pop_by_code), 4
            ),
            "facility_text_candidates": len(candidates),
            "facility_coordinate_count": coordinate_count,
            "facility_coordinate_coverage": round(coordinate_count / len(candidates), 4)
            if candidates
            else 0,
            "facility_reverse_geocode_exact_code_count": mapped,
            "facility_reverse_geocode_failures": reverse_failures,
            "facility_reverse_geocode_match_rate": round(mapped / coordinate_count, 4)
            if coordinate_count
            else 0,
            "facility_areas_covered": area_covered,
            "facility_area_coverage": round(area_covered / len(pop_by_code), 4),
            "facility_records_sharing_coordinates": coordinate_count - len(coords),
            "distinct_facility_coordinates": len(coords),
            "facility_addresses_with_one_text_area_match": unambiguous_text_matches,
            "facility_addresses_with_ambiguous_text_area_match": ambiguous_text_matches,
            "facility_addresses_without_text_area_match": no_text_matches,
            "areas_with_population_household_facility": sum(
                code in hh_by_code and bool(facilities_by_code.get(code)) for code in pop_by_code
            ),
            "full_source_join_rate": round(
                sum(
                    code in hh_by_code and bool(facilities_by_code.get(code))
                    for code in pop_by_code
                )
                / len(pop_by_code),
                4,
            ),
            "address_text_mapping_areas": len(text_matched_areas),
            "areas_missing_data": [area["name"] for area in areas if area["anchor_lat"] is None],
            "duplicate_population_legal_codes": len(population_rows) - len(pop_codes),
            "duplicate_household_legal_codes": len(household_rows) - len(household_codes),
        },
        "interpretation": [
            "Population catalog contains Chungcheongnam-do only, despite a national dataset title.",
            "Household source spans 16 provinces; unmatched codes are not imputed.",
            "Pilot joins use exact legal codes; population is not split by village-name ratios.",
            "Facility name, address, telephone, and manager fields were not persisted.",
            "Facilities may share a coordinate and remain separate coverage records.",
        ],
    }
    _write(ROOT / "artifacts" / "data_quality_report.json", quality)

    field_manifest = []
    field_manifest += _public_field_manifest(
        "data.go.kr/15077871", legal_code_fields, legal_code_rows
    )
    field_manifest += _public_field_manifest(
        f"data.go.kr/{POPULATION_DATASET_ID}", population_fields, population_rows
    )
    field_manifest += _public_field_manifest(
        f"data.go.kr/{HOUSEHOLD_DATASET_ID}", household_fields, household_rows
    )
    field_manifest += _public_field_manifest(
        f"data.go.kr/{FACILITY_DATASET_ID}", facility_fields, all_facilities
    )
    schema = {
        "sources": [
            "data.go.kr/15077871",
            f"data.go.kr/{POPULATION_DATASET_ID}",
            f"data.go.kr/{HOUSEHOLD_DATASET_ID}",
            f"data.go.kr/{FACILITY_DATASET_ID}",
        ],
        "columns": field_manifest,
        "source_metadata": {
            "data.go.kr/15077871": {
                "provider": "행정안전부",
                "endpoint": f"GET {LEGAL_CODE_URL}",
                "catalog_url": "https://www.data.go.kr/data/15077871/openapi.do",
                "reference_date": None,
                "record_count": legal_code_count,
            },
            f"data.go.kr/{POPULATION_DATASET_ID}": {
                "provider": "행정안전부",
                "endpoint": (
                    "CSV linked from "
                    + f"{DATA_GO_ROOT}/data/"
                    + POPULATION_DATASET_ID
                    + "/fileData.do"
                ),
                "catalog_url": f"https://www.data.go.kr/data/{POPULATION_DATASET_ID}/fileData.do",
                "reference_date": str(population_date),
                "record_count": len(population_rows),
            },
            f"data.go.kr/{HOUSEHOLD_DATASET_ID}": {
                "provider": "행정안전부",
                "endpoint": (
                    "CSV linked from "
                    + f"{DATA_GO_ROOT}/data/"
                    + HOUSEHOLD_DATASET_ID
                    + "/fileData.do"
                ),
                "catalog_url": f"https://www.data.go.kr/data/{HOUSEHOLD_DATASET_ID}/fileData.do",
                "reference_date": str(household_date),
                "record_count": len(household_rows),
            },
            f"data.go.kr/{FACILITY_DATASET_ID}": {
                "provider": "행정안전부",
                "endpoint": f"GET {FACILITY_URL}",
                "catalog_url": f"https://www.data.go.kr/data/{FACILITY_DATASET_ID}/standard.do",
                "reference_date": facility_date,
                "record_count": facility_count,
            },
        },
        "age_field_validation": {
            "population_age_field_count": len(pop_age),
            "household_age_field_count": len(hh_age),
            "population_required_age_ranges_available": True,
            "household_required_age_ranges_available": True,
        },
        "privacy": "Facility contact/name/address sample values are intentionally omitted.",
    }
    _write(ROOT / "artifacts" / "public_schema_manifest.json", schema)
    write_data_dictionary(schema)
    print(
        f"Built {len(areas)} area aggregates; population+household join "
        f"{quality['metrics']['pilot_household_join_rate']:.0%}; facility area coverage "
        f"{quality['metrics']['facility_area_coverage']:.0%}. Raw records were not saved."
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(
            f"Build failed safely ({type(exc).__name__}); "
            "provider responses and secrets were not printed."
        )
        raise SystemExit(1) from None
