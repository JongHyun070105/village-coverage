#!/usr/bin/env python3
"""Fetch public sources and build privacy-minimized Chungnam pilot regions.

Raw provider rows are processed in memory and are never written to the repository.
Only public, area-level aggregates, facility counts, anchor coordinates, and the
explicitly unrestricted minimized Buyeo facility subset are saved.
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
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.data_ingestion import legal_code as _legal_code  # noqa: E402
from backend.regions import DEFAULT_REGION_ID  # noqa: E402
from backend.regions import region_id as _region_id  # noqa: E402
from backend.simulation import REFERENCE_SEED, simulated_operating_profile  # noqa: E402
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

REGION_NAME = "충청남도 검증 시범 지역"
REGION_PROVINCE = "충청남도"
PILOT_TOWNS = (("홍성군", "장곡면"), ("부여군", "부여읍"), ("아산시", "음봉면"))
POPULATION_DATASET_ID = "15099158"
HOUSEHOLD_DATASET_ID = "15099160"
FACILITY_DATASET_ID = "15114136"
BUYEO_FACILITY_PUBLIC_PK = "uddi:d4c76add-7771-4c45-a057-e30472b0dae3"
BUYEO_FACILITY_SOURCE_ID = f"{FACILITY_DATASET_ID}:{BUYEO_FACILITY_PUBLIC_PK}"
BUYEO_FACILITY_CATALOG_URL = "https://www.data.go.kr/data/15114136/standard.do?recommendDataYn=Y"
KAKAO_REGION_URL = "https://dapi.kakao.com/v2/local/geo/coord2regioncode.json"
KAKAO_ADDRESS_URL = "https://dapi.kakao.com/v2/local/search/address.json"
SEED = REFERENCE_SEED


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
    matches = list(re.finditer(r"atchFileId=(FILE_[A-Za-z0-9]+)&fileDetailSn=(\d+)", page_text))
    if len(matches) != 1:
        raise RuntimeError(f"expected exactly one linked CSV attachment, found {len(matches)}")
    match = matches[0]
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


def fetch_licensed_buyeo_facilities() -> tuple[list[dict[str, str]], list[str], str]:
    """Download Buyeo's provider file only after rechecking its reuse terms.

    The portal's parent standard dataset omits a dataset-wide license field, so
    this deliberately uses the Buyeo provider row and its detail modal. The
    terms must continue to say "이용허락범위 제한 없음" or ingestion stops.
    """
    page_status, _, page_body, error = _request(BUYEO_FACILITY_CATALOG_URL)
    if page_status != 200:
        raise RuntimeError(
            f"Buyeo facility catalog unavailable ({type(error).__name__ if error else page_status})"
        )
    detail_url = f"{DATA_GO_ROOT}/tcs/dss/selectDpkDetailInfo.do"
    detail_status, _, detail_body, error = _request(
        detail_url,
        headers={
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": BUYEO_FACILITY_CATALOG_URL,
        },
        data=urlencode({"publicDataDetailPk": BUYEO_FACILITY_PUBLIC_PK}).encode("utf-8"),
        method="POST",
    )
    if detail_status != 200:
        raise RuntimeError(
            f"Buyeo facility terms unavailable ({type(error).__name__ if error else detail_status})"
        )
    detail_text = detail_body.decode("utf-8", errors="replace")
    if "충청남도 부여군" not in detail_text:
        raise RuntimeError("Buyeo facility provider does not match the selected source")
    if "이용허락범위 제한 없음" not in detail_text:
        raise RuntimeError("Buyeo facility reuse terms are not explicitly unrestricted")
    file_match = re.search(
        rf"fn_fileDataDown\(\s*'{FACILITY_DATASET_ID}'\s*,\s*'{re.escape(BUYEO_FACILITY_PUBLIC_PK)}'"
        r"\s*,\s*'([^']+)'\s*,\s*'(\d+)'\s*,\s*'csv'\s*\)",
        detail_text,
    )
    if not file_match:
        raise RuntimeError("licensed Buyeo facility CSV attachment not found")
    download_url = _query_url(
        f"{DATA_GO_ROOT}/cmm/cmm/fileDownload.do",
        {
            "atchFileId": file_match.group(1),
            "fileDetailSn": file_match.group(2),
            "insertDataPrcus": "N",
        },
    )
    download_status, _, download_body, error = _request(download_url, timeout=60)
    if download_status != 200 or not download_body:
        detail = type(error).__name__ if error else download_status
        raise RuntimeError(f"licensed Buyeo facility CSV unavailable ({detail})")
    fields, rows = decode_csv(download_body)
    required = {
        "시설명",
        "시설유형",
        "소재지도로명주소",
        "소재지지번주소",
        "위도",
        "경도",
        "영업상태명",
        "전화번호",
        "건립일자",
        "건물면적",
        "관리기관명",
        "데이터기준일자",
    }
    if not required.issubset(fields):
        raise RuntimeError("licensed Buyeo facility CSV schema changed")
    dates = sorted({str(row.get("데이터기준일자", "")).strip() for row in rows} - {""})
    if not rows or not dates:
        raise RuntimeError("licensed Buyeo facility CSV has no dated rows")
    return rows, fields, dates[-1]


def minimize_buyeo_facilities(
    rows: list[dict[str, Any]],
    areas: list[dict[str, Any]],
    geocode: Any,
) -> dict[str, list[dict[str, Any]]]:
    """Join licensed Buyeo-eup rows by Kakao legal code and retain allowlisted fields."""
    valid_codes = {
        str(area["legal_code"])
        for area in areas
        if area.get("county") == "부여군" and area.get("town") == "부여읍"
    }
    if not valid_codes:
        raise RuntimeError("Buyeo-eup service areas missing from public snapshot")
    result: dict[str, list[dict[str, Any]]] = defaultdict(list)
    selected_rows = 0
    for row in rows:
        address = " ".join(
            str(row.get(field, "")) for field in ("소재지지번주소", "소재지도로명주소")
        )
        if "부여군" not in address or "부여읍" not in address:
            continue
        selected_rows += 1
        try:
            latitude = float(str(row.get("위도", "")).replace(",", "").strip())
            longitude = float(str(row.get("경도", "")).replace(",", "").strip())
        except (TypeError, ValueError):
            raise RuntimeError("Buyeo-eup facility row has invalid coordinates") from None
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            raise RuntimeError("Buyeo-eup facility row has out-of-range coordinates")
        legal_code, _ = geocode(latitude, longitude)
        if legal_code not in valid_codes:
            raise RuntimeError("Buyeo-eup facility row did not join an enabled legal area")
        facility_type = str(row.get("시설유형", "")).strip()
        reference_date = str(row.get("데이터기준일자", "")).strip()
        if not facility_type or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", reference_date):
            raise RuntimeError("Buyeo-eup facility row lacks type or reference date")
        raw_floor_area = str(row.get("건물면적", "")).replace(",", "").strip()
        try:
            floor_area = float(raw_floor_area) if raw_floor_area else None
        except ValueError:
            floor_area = None
        result[legal_code].append(
            {
                "facility_type": facility_type,
                "operating_status": str(row.get("영업상태명", "")).strip() or None,
                "latitude": latitude,
                "longitude": longitude,
                "built_date": str(row.get("건립일자", "")).strip() or None,
                "floor_area_sqm": floor_area,
                "source_reference_date": reference_date,
                "source_dataset_id": BUYEO_FACILITY_SOURCE_ID,
            }
        )
    if not selected_rows:
        raise RuntimeError("licensed Buyeo facility CSV contains no Buyeo-eup rows")
    if sum(map(len, result.values())) != selected_rows:
        raise RuntimeError("not all selected Buyeo-eup facility rows were joined")
    return dict(result)


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
    sensitive = {
        "flctNm",
        "telno",
        "lctnRoadNmAddr",
        "lctnLotnoAddr",
        "mngInstNm",
        "insttNm",
        "시설명",
        "소재지도로명주소",
        "소재지지번주소",
        "전화번호",
        "관리기관명",
    }
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
        "시설명": ("시설 이름.", None, "not persisted"),
        "소재지도로명주소": ("시설 도로명 주소.", None, "not persisted"),
        "소재지지번주소": ("시설 지번 주소.", None, "not persisted"),
        "전화번호": ("시설 연락 전화번호.", None, "not persisted"),
        "관리기관명": ("시설 관리기관명.", None, "not persisted"),
        "시설유형": ("시설의 공개 분류.", "facility_type", None),
        "위도": ("WGS84 위도.", "latitude", "exact legal-code coordinate join"),
        "경도": ("WGS84 경도.", "longitude", "exact legal-code coordinate join"),
        "영업상태명": ("시설 운영 상태.", "operating_status", None),
        "건립일자": ("시설 건립일.", "built_date", None),
        "건물면적": ("시설 건물 면적(㎡).", "floor_area_sqm", None),
        "데이터기준일자": ("원천 행의 기준일.", "source_reference_date", None),
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
        f"data.go.kr/{BUYEO_FACILITY_SOURCE_ID}": "충청남도 부여군 마을회관·경로당 CSV",
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
        (
            "행 단위 시설 속성은 명시적으로 재사용 제한이 없는 부여군 부여읍 파일만 "
            "저장합니다. 홍성·아산은 권역 집계와 앵커만 보존합니다."
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
        (
            "| `facilities` | 부여군 CSV | 유형·상태·좌표·건립일·면적·기준일; "
            "접촉 필드 제외 | 선택 지역 |"
        ),
        "| `simulated_monthly_demand`, `demand_*` | 공개 원본에 없음 | 시뮬레이션 | 예 |",
        "",
        (
            "인구와 1인가구는 정확한 10자리 법정동 코드로 연결했습니다. "
            "행정리 이름만으로 통계 인구를 임의 분할하거나 보간하지 않습니다."
        ),
        "",
        "## 원본 필드 전체 목록",
        "",
        "시설 집계와 대표 좌표는 전국 표준 API에서 보존합니다. 행 단위 속성은 부여군이",
        "공식 상세창에 표시한 `이용허락범위 제한 없음` 조건을 확인한 부여읍 CSV의",
        "최소 필드만 저장합니다. 홍성·아산은 집계 전용이며 시설명·주소·전화번호·",
        "관리기관 정보 및 원본 식별자는 모든 지역에서 저장하지 않습니다.",
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
        licensed_buyeo_rows, licensed_buyeo_fields, buyeo_facility_date = (
            fetch_licensed_buyeo_facilities()
        )
    except Exception as exc:
        print(f"Public data retrieval failed safely ({type(exc).__name__}).")
        return 1

    region_config = [
        {
            "region_id": _region_id(county, town),
            "province": REGION_PROVINCE,
            "county": county,
            "town": town,
            "name": f"{county} {town}",
        }
        for county, town in PILOT_TOWNS
    ]
    region_config_by_id = {item["region_id"]: item for item in region_config}
    pop_rows = [
        row
        for row in population_rows
        if row.get("시도명", "").strip() == REGION_PROVINCE
        and (row.get("시군구명", "").strip(), row.get("읍면동명", "").strip()) in PILOT_TOWNS
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
    region_area_counts = Counter(
        _region_id(str(row.get("시군구명", "")), str(row.get("읍면동명", "")))
        for row in pop_by_code.values()
    )
    if any(region_area_counts.get(item["region_id"], 0) < 10 for item in region_config):
        raise RuntimeError("each selected Chungnam town must contain at least ten legal-ri areas")
    missing_households = set(pop_by_code) - set(hh_by_code)
    if missing_households:
        raise RuntimeError("selected Chungnam regions do not have complete exact household joins")
    region_id_by_code = {
        code: _region_id(str(row.get("시군구명", "")), str(row.get("읍면동명", "")))
        for code, row in pop_by_code.items()
    }

    candidates: list[tuple[str, dict[str, Any]]] = []
    for item in all_facilities:
        address_compact = "".join(
            str(item.get(key, "")) for key in ("lctnLotnoAddr", "lctnRoadNmAddr")
        ).replace(" ", "")
        matching_region = next(
            (
                config["region_id"]
                for config in region_config
                if config["county"].replace(" ", "") in address_compact
                and config["town"].replace(" ", "") in address_compact
            ),
            None,
        )
        if matching_region:
            candidates.append((matching_region, item))
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
    for candidate_region_id, record in candidates:
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
            if region_id_by_code[candidate_code] == candidate_region_id
            and area_name
            and area_name.replace(" ", "") in address_text
        ]
        for candidate_code in address_hits:
            text_area_hits[candidate_code] += 1
        if len(address_hits) == 1:
            unambiguous_text_matches += 1
        elif len(address_hits) > 1:
            ambiguous_text_matches += 1
        else:
            no_text_matches += 1
        if code in pop_by_code and region_id_by_code[code] == candidate_region_id:
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
        simulated_inputs = simulated_operating_profile(
            {
                "id": code,
                "population_total": pop_total,
                "elderly_ratio_65": hhi,
                "single_households_total": singles_total,
            },
            REFERENCE_SEED,
        )
        # No anchor gets disclosed if public facilities have no usable coordinate.
        anchor = facilities[len(facilities) // 2] if facilities else None
        areas.append(
            {
                "id": code,
                "legal_code": code,
                "region_id": region_id_by_code[code],
                "name": (
                    f"{pop_row.get('읍면동명', '').strip()} {pop_row.get('리명', '').strip()}"
                ).strip(),
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
                **simulated_inputs,
                "data_provenance": "REAL PUBLIC DATA + SIMULATED FOR PRE-R&D",
            }
        )

    def throttled_reverse_geocode(lat: float, lng: float) -> tuple[str, str]:
        result = reverse_geocode(lat, lng, kakao_key)
        time.sleep(0.08)
        return result

    licensed_buyeo_by_code = minimize_buyeo_facilities(
        licensed_buyeo_rows, areas, throttled_reverse_geocode
    )
    for area in areas:
        area["facilities"] = licensed_buyeo_by_code.get(str(area["legal_code"]), [])

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
    area_by_region: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for area in areas:
        area_by_region[str(area["region_id"])].append(area)
    verified_regions = []
    for config in region_config:
        region_areas = area_by_region[config["region_id"]]
        region_codes = {str(area["legal_code"]) for area in region_areas}
        household_join_count = sum(code in hh_by_code for code in region_codes)
        facility_area_count = sum(bool(facilities_by_code.get(code)) for code in region_codes)
        anchor_count = sum(
            area["anchor_lat"] is not None and area["anchor_lng"] is not None
            for area in region_areas
        )
        full_join_rate = (
            sum(code in hh_by_code and bool(facilities_by_code.get(code)) for code in region_codes)
            / len(region_codes)
            if region_codes
            else 0
        )
        if household_join_count != len(region_codes) or full_join_rate < 1.0:
            raise RuntimeError("selected region failed exact public-source join coverage")
        verified_regions.append(
            {
                **config,
                "area_count": len(region_areas),
                "household_join_rate": round(household_join_count / len(region_codes), 4),
                "facility_area_count": facility_area_count,
                "coordinate_anchor_count": anchor_count,
                "facility_area_coverage": round(facility_area_count / len(region_codes), 4),
                "full_source_join_rate": round(full_join_rate, 4),
                "population_reference_date": str(population_date),
                "household_reference_date": str(household_date),
                "facility_latest_update_date": facility_date,
                "facility_detail_row_count": sum(
                    len(area.get("facilities", [])) for area in region_areas
                ),
                "facility_detail_area_count": sum(
                    bool(area.get("facilities")) for area in region_areas
                ),
                "provenance": "REAL PUBLIC DATA; EXACT LEGAL-CODE JOIN",
            }
        )
    facility_data = {
        "region": region_config_by_id[DEFAULT_REGION_ID]["name"],
        "default_region_id": DEFAULT_REGION_ID,
        "regions": verified_regions,
        "source_data": {
            "legal_code_endpoint": "StanReginCd.getStanReginCdList",
            "legal_code_records": legal_code_count,
            "population_dataset_id": POPULATION_DATASET_ID,
            "household_dataset_id": HOUSEHOLD_DATASET_ID,
            "facility_dataset_id": FACILITY_DATASET_ID,
            "licensed_facility_detail_source_id": BUYEO_FACILITY_SOURCE_ID,
            "licensed_facility_detail_catalog_url": BUYEO_FACILITY_CATALOG_URL,
            "licensed_facility_detail_reuse_terms": "이용허락범위 제한 없음",
            "licensed_facility_detail_reference_date": buyeo_facility_date,
            "licensed_facility_detail_rows": sum(map(len, licensed_buyeo_by_code.values())),
            "licensed_facility_detail_areas": len(licensed_buyeo_by_code),
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
        "regions": verified_regions,
        "sources": facility_data["source_data"],
        "metrics": {
            "population_rows_with_unique_legal_code": len(pop_codes) == len(population_rows),
            "household_rows_with_unique_legal_code": len(household_codes) == len(household_rows),
            "population_household_code_intersection": len(pop_codes & household_codes),
            "household_codes_without_population_row": len(household_codes - pop_codes),
            "pilot_population_area_count": len(pop_by_code),
            "verified_region_count": len(verified_regions),
            "regions_with_complete_source_join": sum(
                item["full_source_join_rate"] == 1.0 for item in verified_regions
            ),
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
            "licensed_facility_detail_rows": sum(map(len, licensed_buyeo_by_code.values())),
            "licensed_facility_detail_areas": len(licensed_buyeo_by_code),
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
            (
                "Three Chungnam towns are enabled only after exact population, household, "
                "Kakao facility-anchor joins."
            ),
            "Pilot joins use exact legal codes; population is not split by village-name ratios.",
            (
                "Only Buyeo-eup facility rows with explicitly unrestricted reuse terms "
                "persist type, status, coordinates, build date, area, and reference date."
            ),
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
    field_manifest += _public_field_manifest(
        f"data.go.kr/{BUYEO_FACILITY_SOURCE_ID}", licensed_buyeo_fields, licensed_buyeo_rows
    )
    schema = {
        "sources": [
            "data.go.kr/15077871",
            f"data.go.kr/{POPULATION_DATASET_ID}",
            f"data.go.kr/{HOUSEHOLD_DATASET_ID}",
            f"data.go.kr/{FACILITY_DATASET_ID}",
            f"data.go.kr/{BUYEO_FACILITY_SOURCE_ID}",
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
            f"data.go.kr/{BUYEO_FACILITY_SOURCE_ID}": {
                "provider": "충청남도 부여군",
                "endpoint": (
                    "CSV provider row accessed through the official detail modal at "
                    + BUYEO_FACILITY_CATALOG_URL
                ),
                "catalog_url": BUYEO_FACILITY_CATALOG_URL,
                "reference_date": buyeo_facility_date,
                "record_count": len(licensed_buyeo_rows),
                "persisted_record_count": sum(map(len, licensed_buyeo_by_code.values())),
                "reuse_terms": "이용허락범위 제한 없음",
                "persisted_fields": [
                    "시설유형",
                    "영업상태명",
                    "위도",
                    "경도",
                    "건립일자",
                    "건물면적",
                    "데이터기준일자",
                ],
                "omitted_fields": [
                    "시설명",
                    "소재지도로명주소",
                    "소재지지번주소",
                    "전화번호",
                    "관리기관명",
                ],
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
        f"Built {len(areas)} area aggregates across {len(verified_regions)} verified regions; "
        f"population+household join {quality['metrics']['pilot_household_join_rate']:.0%}; "
        f"facility area coverage {quality['metrics']['facility_area_coverage']:.0%}. "
        "Unminimized source rows were not saved."
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
