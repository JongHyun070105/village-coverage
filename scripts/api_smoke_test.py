#!/usr/bin/env python3
"""Live, secret-safe checks for VillageCoverage's configured data providers."""

from __future__ import annotations

import csv
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
REPORT_PATH = ROOT / "artifacts" / "api_smoke_report.json"
USER_AGENT = "VillageCoverage-pre-rnd/0.1"
DATA_GO_ROOT = "https://www.data.go.kr"
LEGAL_CODE_URL = "https://apis.data.go.kr/1741000/StanReginCd/getStanReginCdList"
FACILITY_URL = "https://api.data.go.kr/openapi/tn_pubr_public_vill_hall_sen_cent_api"
KAKAO_GEOCODE_URL = "https://dapi.kakao.com/v2/local/search/address.json"
KAKAO_DIRECTIONS_URL = "https://apis-navi.kakaomobility.com/v1/directions"
KAKAO_MAP_SDK_URL = "https://dapi.kakao.com/v2/maps/sdk.js"
POPULATION_DATASET_ID = "15099158"
SINGLE_HOUSEHOLD_DATASET_ID = "15099160"


def _load_config(name: str) -> str:
    """Read one setting without ever logging its value."""
    value = os.environ.get(name)
    if value:
        return value

    env_file = ROOT / ".env"
    if not env_file.exists():
        return ""
    for line in env_file.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        if key.strip() == name:
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            return value
    return ""


def _request(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    data: bytes | None = None,
    method: str | None = None,
    timeout: int = 30,
) -> tuple[int | None, str, bytes, str | None]:
    request_headers = {"User-Agent": USER_AGENT, **(headers or {})}
    request = urllib.request.Request(url, data=data, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            content_type = response.headers.get("Content-Type", "").split(";", 1)[0]
            return response.status, content_type, response.read(), None
    except urllib.error.HTTPError as exc:
        content_type = exc.headers.get("Content-Type", "").split(";", 1)[0]
        try:
            body = exc.read()
        except Exception:
            body = b""
        return exc.code, content_type, body, None
    except Exception as exc:  # Never surface exception text: URLs/headers may be sensitive.
        return None, "", b"", type(exc).__name__


def _query_url(base: str, params: dict[str, Any]) -> str:
    return f"{base}?{urllib.parse.urlencode(params)}"


def _json_payload(body: bytes) -> dict[str, Any] | None:
    try:
        value = json.loads(body)
        return value if isinstance(value, dict) else None
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


def _walk(value: Any):
    if isinstance(value, dict):
        yield value
        for nested in value.values():
            yield from _walk(nested)
    elif isinstance(value, list):
        yield value
        for nested in value:
            yield from _walk(nested)


def _find_record(value: Any, identifying_fields: set[str]) -> dict[str, Any] | None:
    for nested in _walk(value):
        if isinstance(nested, dict) and identifying_fields.intersection(nested):
            if all(not isinstance(item, (dict, list)) for item in nested.values()):
                return nested
    return None


def _find_value(value: Any, field_name: str) -> Any:
    normalized = field_name.lower()
    for nested in _walk(value):
        if isinstance(nested, dict):
            for key, item in nested.items():
                if key.lower() == normalized:
                    return item
    return None


def _find_list(value: Any, identifying_fields: set[str]) -> list[dict[str, Any]]:
    for nested in _walk(value):
        if (
            isinstance(nested, list)
            and nested
            and isinstance(nested[0], dict)
            and identifying_fields.intersection(nested[0])
        ):
            return nested
    record = _find_record(value, identifying_fields)
    return [record] if record else []


def _entry(
    *,
    source: str,
    status: str,
    endpoint_name: str,
    http_status: int | None = None,
    response_format: str | None = None,
    sample_column_names: list[str] | None = None,
    record_count_if_known: int | None = None,
    latest_reference_date: str | None = None,
    latency_ms: int | None = None,
    notes: str = "",
) -> dict[str, Any]:
    return {
        "source": source,
        "status": status,
        "endpoint_name": endpoint_name,
        "http_status": http_status,
        "response_format": response_format,
        "sample_column_names": sample_column_names or [],
        "record_count_if_known": record_count_if_known,
        "latest_reference_date": latest_reference_date,
        "latency_ms": latency_ms,
        "notes": notes,
    }


def _safe_error_note(http_status: int | None, exception_name: str | None) -> str:
    if exception_name:
        return (
            f"Request failed safely ({exception_name}); "
            "secret values and response bodies were suppressed."
        )
    if http_status is not None:
        return f"Provider returned HTTP {http_status}; response body was suppressed."
    return "Provider request failed; response body was suppressed."


def check_legal_dong_code(service_key: str) -> dict[str, Any]:
    endpoint_name = "StanReginCd.getStanReginCdList"
    if not service_key:
        return _entry(
            source="data.go.kr 15077871",
            status="FAIL",
            endpoint_name=endpoint_name,
            notes="DATA_GO_KR_SERVICE_KEY is missing.",
        )

    started = time.perf_counter()
    params = {
        "ServiceKey": service_key,
        "pageNo": "1",
        "numOfRows": "10",
        "type": "json",
    }
    http_status, content_type, body, error = _request(_query_url(LEGAL_CODE_URL, params))
    elapsed = round((time.perf_counter() - started) * 1000)
    payload = _json_payload(body)
    if http_status != 200 or payload is None:
        return _entry(
            source="data.go.kr 15077871",
            status="FAIL",
            endpoint_name=endpoint_name,
            http_status=http_status,
            response_format=content_type or None,
            latency_ms=elapsed,
            notes=_safe_error_note(http_status, error),
        )

    record = _find_record(payload, {"region_cd", "locatadd_nm", "sido_cd"})
    code = str(_find_value(payload, "resultCode") or "")
    total_count = _find_value(payload, "totalCount")
    valid = code == "INFO-0" and record is not None
    return _entry(
        source="data.go.kr 15077871",
        status="PASS" if valid else "FAIL",
        endpoint_name=endpoint_name,
        http_status=http_status,
        response_format="JSON" if payload is not None else content_type or None,
        sample_column_names=sorted(record.keys()) if record else [],
        record_count_if_known=int(total_count) if str(total_count).isdigit() else None,
        latency_ms=elapsed,
        notes="Observed INFO-0 legal-dong response."
        if valid
        else "The live legal-dong response did not contain a successful result and sample row.",
    )


def check_facilities(service_key: str) -> dict[str, Any]:
    endpoint_name = "tn_pubr_public_vill_hall_sen_cent_api"
    if not service_key:
        return _entry(
            source="data.go.kr 15114136",
            status="FAIL",
            endpoint_name=endpoint_name,
            notes="DATA_GO_KR_SERVICE_KEY is missing.",
        )

    started = time.perf_counter()
    page = 1
    total_count: int | None = None
    record_count = 0
    latest_date: str | None = None
    sample_columns: list[str] = []
    first_http_status: int | None = None
    provider_code = ""
    error: str | None = None
    while True:
        params = {
            "ServiceKey": service_key,
            "pageNo": str(page),
            "numOfRows": "1000",
            "type": "json",
        }
        http_status, content_type, body, error = _request(_query_url(FACILITY_URL, params))
        if first_http_status is None:
            first_http_status = http_status
        payload = _json_payload(body)
        if http_status != 200 or payload is None:
            elapsed = round((time.perf_counter() - started) * 1000)
            return _entry(
                source="data.go.kr 15114136",
                status="FAIL",
                endpoint_name=endpoint_name,
                http_status=first_http_status if first_http_status is not None else http_status,
                response_format=content_type or None,
                sample_column_names=sample_columns,
                record_count_if_known=total_count,
                latest_reference_date=latest_date,
                latency_ms=elapsed,
                notes=_safe_error_note(http_status, error),
            )

        header = payload.get("header", {})
        body_data = payload.get("body", {})
        provider_code = str(header.get("resultCode", "")) if isinstance(header, dict) else ""
        if provider_code != "00" or not isinstance(body_data, dict):
            elapsed = round((time.perf_counter() - started) * 1000)
            return _entry(
                source="data.go.kr 15114136",
                status="FAIL",
                endpoint_name=endpoint_name,
                http_status=first_http_status,
                response_format="JSON",
                sample_column_names=sample_columns,
                record_count_if_known=total_count,
                latest_reference_date=latest_date,
                latency_ms=elapsed,
                notes=(
                    f"Provider returned result code {provider_code or 'unknown'}; "
                    "response details were suppressed."
                ),
            )

        total_count = (
            int(body_data["totalCount"])
            if str(body_data.get("totalCount", "")).isdigit()
            else total_count
        )
        raw_items = (
            body_data.get("items", {}).get("item", [])
            if isinstance(body_data.get("items"), dict)
            else []
        )
        if isinstance(raw_items, dict):
            raw_items = [raw_items]
        if not isinstance(raw_items, list):
            raw_items = []
        if raw_items and not sample_columns:
            sample_columns = sorted(str(key) for key in raw_items[0].keys())
        for item in raw_items:
            if isinstance(item, dict):
                record_count += 1
                item_date = str(item.get("crtrYmd", ""))
                if re.fullmatch(r"\d{4}-\d{2}-\d{2}", item_date) and (
                    latest_date is None or item_date > latest_date
                ):
                    latest_date = item_date

        if total_count is None or record_count >= total_count or not raw_items:
            break
        page += 1
        time.sleep(0.12)

    elapsed = round((time.perf_counter() - started) * 1000)
    complete = (
        provider_code == "00"
        and total_count is not None
        and record_count == total_count
        and bool(sample_columns)
    )
    return _entry(
        source="data.go.kr 15114136",
        status="PASS" if complete else "FAIL",
        endpoint_name=endpoint_name,
        http_status=first_http_status,
        response_format="JSON",
        sample_column_names=sample_columns,
        record_count_if_known=record_count if complete else total_count,
        latest_reference_date=latest_date,
        latency_ms=elapsed,
        notes=(
            f"Fetched all {record_count:,} records across {page:,} pages; provider result code 00."
            if complete
            else "The complete facility result set was not observed."
        ),
    )


def _decode_csv(body: bytes) -> tuple[str, str]:
    try:
        return body.decode("utf-8-sig"), "CSV/UTF-8"
    except UnicodeDecodeError:
        return body.decode("cp949"), "CSV/CP949"


def check_file_dataset(dataset_id: str, label: str) -> dict[str, Any]:
    endpoint_name = f"fileData.csv:{dataset_id}"
    started = time.perf_counter()
    page_url = f"{DATA_GO_ROOT}/data/{dataset_id}/fileData.do"
    page_status, page_type, page_body, error = _request(page_url)
    if page_status != 200:
        return _entry(
            source=f"data.go.kr {dataset_id}",
            status="FAIL",
            endpoint_name=endpoint_name,
            http_status=page_status,
            response_format=page_type or None,
            latency_ms=round((time.perf_counter() - started) * 1000),
            notes=_safe_error_note(page_status, error),
        )

    page_text = page_body.decode("utf-8", errors="replace")
    match = re.search(r"atchFileId=(FILE_[A-Za-z0-9]+)&fileDetailSn=(\d+)", page_text)
    if not match:
        return _entry(
            source=f"data.go.kr {dataset_id}",
            status="FAIL",
            endpoint_name=endpoint_name,
            http_status=page_status,
            response_format=page_type or None,
            latency_ms=round((time.perf_counter() - started) * 1000),
            notes="The official dataset page did not expose a downloadable CSV attachment.",
        )

    params = {
        "atchFileId": match.group(1),
        "fileDetailSn": match.group(2),
        "insertDataPrcus": "N",
    }
    download_url = _query_url(f"{DATA_GO_ROOT}/cmm/cmm/fileDownload.do", params)
    http_status, content_type, body, error = _request(download_url, timeout=60)
    if http_status != 200 or not body:
        return _entry(
            source=f"data.go.kr {dataset_id}",
            status="FAIL",
            endpoint_name=endpoint_name,
            http_status=http_status,
            response_format=content_type or None,
            latency_ms=round((time.perf_counter() - started) * 1000),
            notes=_safe_error_note(http_status, error),
        )

    try:
        text, response_format = _decode_csv(body)
        reader = csv.reader(io.StringIO(text))
        header = next(reader, [])
        record_count = sum(1 for row in reader if row)
    except Exception as exc:
        return _entry(
            source=f"data.go.kr {dataset_id}",
            status="FAIL",
            endpoint_name=endpoint_name,
            http_status=http_status,
            response_format=content_type or None,
            latency_ms=round((time.perf_counter() - started) * 1000),
            notes=f"Downloaded file could not be parsed safely ({type(exc).__name__}).",
        )

    date_match = re.search(r"_(20\d{6})(?:\D|$)", page_text)
    latest_date = date_match.group(1) if date_match else None
    province_column = header.index("시도명") if "시도명" in header else None
    province_count: int | None = None
    if province_column is not None:
        try:
            rows = csv.reader(io.StringIO(text))
            next(rows, None)
            province_count = len(
                {
                    row[province_column].strip()
                    for row in rows
                    if len(row) > province_column and row[province_column].strip()
                }
            )
        except Exception:
            province_count = None

    coverage_note = (
        f"Observed {province_count} distinct province values." if province_count is not None else ""
    )
    if dataset_id == POPULATION_DATASET_ID and province_count == 1:
        coverage_note = (
            "Live catalog CSV currently contains only Chungcheongnam-do; "
            "this is a source-coverage limitation."
        )
    notes = (
        f"Fetched and parsed {record_count:,} rows and {len(header):,} columns. {coverage_note}"
    ).strip()
    valid = bool(header) and record_count > 0 and latest_date is not None
    return _entry(
        source=f"data.go.kr {dataset_id}",
        status="PASS" if valid else "FAIL",
        endpoint_name=endpoint_name,
        http_status=http_status,
        response_format=response_format,
        sample_column_names=header[:16],
        record_count_if_known=record_count,
        latest_reference_date=latest_date,
        latency_ms=round((time.perf_counter() - started) * 1000),
        notes=notes,
    )


def check_kakao_geocoding(rest_key: str) -> dict[str, Any]:
    endpoint_name = "/v2/local/search/address.json"
    if not rest_key:
        return _entry(
            source="Kakao Local API",
            status="FAIL",
            endpoint_name=endpoint_name,
            notes="KAKAO_REST_API_KEY is missing.",
        )
    started = time.perf_counter()
    url = _query_url(KAKAO_GEOCODE_URL, {"query": "서울특별시 중구 세종대로 110"})
    http_status, content_type, body, error = _request(
        url, headers={"Authorization": f"KakaoAK {rest_key}"}
    )
    elapsed = round((time.perf_counter() - started) * 1000)
    payload = _json_payload(body)
    documents = payload.get("documents", []) if payload else []
    valid = http_status == 200 and isinstance(documents, list) and bool(documents)
    return _entry(
        source="Kakao Local API",
        status="PASS" if valid else "FAIL",
        endpoint_name=endpoint_name,
        http_status=http_status,
        response_format="JSON" if payload else content_type or None,
        sample_column_names=sorted(documents[0].keys()) if valid else [],
        record_count_if_known=len(documents) if isinstance(documents, list) else None,
        latency_ms=elapsed,
        notes="Address lookup returned at least one result."
        if valid
        else _safe_error_note(http_status, error),
    )


def check_kakao_mobility(rest_key: str) -> dict[str, Any]:
    endpoint_name = "GET /v1/directions"
    if not rest_key:
        return _entry(
            source="Kakao Mobility",
            status="FAIL",
            endpoint_name=endpoint_name,
            notes="KAKAO_REST_API_KEY is missing.",
        )
    started = time.perf_counter()
    url = _query_url(
        KAKAO_DIRECTIONS_URL,
        {
            "origin": "126.9780,37.5665",
            "destination": "126.9720,37.5547",
            "priority": "TIME",
            "summary": "true",
        },
    )
    http_status, content_type, body, error = _request(
        url,
        headers={"Authorization": f"KakaoAK {rest_key}", "Content-Type": "application/json"},
    )
    elapsed = round((time.perf_counter() - started) * 1000)
    payload = _json_payload(body)
    routes = payload.get("routes", []) if payload else []
    summary = routes[0].get("summary", {}) if routes and isinstance(routes[0], dict) else {}
    valid = http_status == 200 and bool(summary.get("distance")) and bool(summary.get("duration"))
    return _entry(
        source="Kakao Mobility Directions API",
        status="PASS" if valid else "FAIL",
        endpoint_name=endpoint_name,
        http_status=http_status,
        response_format="JSON" if payload else content_type or None,
        sample_column_names=sorted(summary.keys()) if valid else [],
        record_count_if_known=1 if valid else 0,
        latency_ms=elapsed,
        notes="A road route returned distance and duration."
        if valid
        else _safe_error_note(http_status, error),
    )


def check_kakao_maps_js(js_key: str) -> dict[str, Any]:
    endpoint_name = "/v2/maps/sdk.js"
    if not js_key:
        return _entry(
            source="Kakao Maps JavaScript SDK",
            status="FAIL",
            endpoint_name=endpoint_name,
            notes="NEXT_PUBLIC_KAKAO_MAP_JS_KEY is missing.",
        )
    started = time.perf_counter()
    url = _query_url(KAKAO_MAP_SDK_URL, {"appkey": js_key, "autoload": "false"})
    http_status, content_type, body, error = _request(url)
    elapsed = round((time.perf_counter() - started) * 1000)
    valid = http_status == 200 and bool(body) and "javascript" in content_type.lower()
    return _entry(
        source="Kakao Maps JavaScript SDK",
        status="PASS" if valid else "FAIL",
        endpoint_name=endpoint_name,
        http_status=http_status,
        response_format="JavaScript" if valid else content_type or None,
        latency_ms=elapsed,
        notes="SDK script endpoint returned JavaScript."
        if valid
        else _safe_error_note(http_status, error),
    )


def check_gemini(api_key: str, model: str) -> dict[str, Any]:
    endpoint_name = "models.generateContent (structured output)"
    if not api_key or not model:
        missing = "GEMINI_API_KEY" if not api_key else "GEMINI_MODEL"
        return _entry(
            source="Google Gemini API",
            status="FAIL",
            endpoint_name=endpoint_name,
            notes=f"{missing} is missing.",
        )

    started = time.perf_counter()
    try:
        from google import genai

        from backend.demand import StructuredDemand

        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=model,
            contents="겨울철 세탁 서비스를 월 2회 제공해 주세요.",
            config={
                "response_mime_type": "application/json",
                "response_json_schema": StructuredDemand.model_json_schema(),
                "temperature": 0,
                "max_output_tokens": 768,
            },
        )
        parsed = StructuredDemand.model_validate_json(response.text or "")
        valid = isinstance(parsed.requests, list)
        error_name = None
    except Exception as exc:
        valid = False
        error_name = type(exc).__name__

    elapsed = round((time.perf_counter() - started) * 1000)
    return _entry(
        source="Google Gemini API",
        status="PASS" if valid else "FAIL",
        endpoint_name=endpoint_name,
        http_status=200 if valid else None,
        response_format="JSON (Pydantic JSON Schema)" if valid else None,
        sample_column_names=[
            "requests",
            "confidence",
            "needs_followup_survey",
        ]
        if valid
        else [],
        record_count_if_known=1 if valid else 0,
        latency_ms=elapsed,
        notes="Structured output validated against the application Pydantic model."
        if valid
        else _safe_error_note(None, error_name),
    )


def main() -> int:
    started = datetime.now(timezone.utc).isoformat()
    data_key = _load_config("DATA_GO_KR_SERVICE_KEY")
    kakao_key = _load_config("KAKAO_REST_API_KEY")
    kakao_js_key = _load_config("NEXT_PUBLIC_KAKAO_MAP_JS_KEY")
    gemini_key = _load_config("GEMINI_API_KEY")
    gemini_model = _load_config("GEMINI_MODEL")

    checks = [
        check_legal_dong_code(data_key),
        check_facilities(data_key),
        check_file_dataset(POPULATION_DATASET_ID, "population"),
        check_file_dataset(SINGLE_HOUSEHOLD_DATASET_ID, "single-household"),
        check_kakao_geocoding(kakao_key),
        check_kakao_mobility(kakao_key),
        check_kakao_maps_js(kakao_js_key),
        check_gemini(gemini_key, gemini_model),
    ]

    report = {
        "generated_at": started,
        "all_passed": all(item["status"] == "PASS" for item in checks),
        "checks": checks,
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    for item in checks:
        print(f"[{item['status']}] {item['endpoint_name']}")
    print(f"Report: {REPORT_PATH.relative_to(ROOT)}")
    return 0 if report["all_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
