"""관리홈닥터 월별지원현황 ingestion (data.go.kr 15120958) — V4 §14, §15.

This is operational data from public rental-housing complexes. It is used only
to study real monthly count variability and to validate forecasting methods.
It is never a rural demand prior.
"""

from __future__ import annotations

import json
import urllib.parse
from collections import defaultdict
from collections.abc import Callable
from typing import Any

from backend.source_snapshots import (
    SnapshotStore,
    SourceUnavailable,
    check_schema,
    ingest_with_fallback,
)

DATASET_ID = "15120958"
ODCLOUD_PATH = "/15120958/v1/uddi:14b48fcb-dbb0-42eb-bb90-bd63465ce8bc"
ODCLOUD_VERSION_LABEL = "주택관리공단(주)_임대주택 관리홈닥터 월별지원현황_20260630"
DOMAIN_LABEL = "EXTERNAL_OPERATIONAL_REFERENCE"
DOMAIN_LABEL_KO = "외부 운영자료 참고"
PRIMARY_PERIOD_START = (2021, 10)
OFFICIAL_LIMITATION = "데이터가 없는 일자도 포함되어 있어, 가급적이면 2021년 10월 부터 활용 권장"
CATEGORY_FIELDS = ("생활지원", "가사지원", "의료지원", "경제지원")
REQUIRED_FIELDS = (
    "년도", "월", "지사명", "단지명", "임대유형", "세대수", "대상세대(인원수)",
    "지원내용총건수", *CATEGORY_FIELDS,
)

Fetcher = Callable[[str], tuple[int, str]]


def ingest_snapshot(
    service_key: str,
    store: SnapshotStore,
    *,
    fetch: Fetcher | None = None,
    offline: bool = False,
) -> dict[str, Any]:
    """Fetch and cache the data.go.kr dataset with explicit fallback provenance."""

    def load() -> tuple[dict[str, Any], list[dict[str, Any]], int]:
        if offline:
            raise SourceUnavailable("OFFLINE_MODE", "live pull disabled")
        rows = fetch_all_rows(service_key, fetch=fetch)
        return {"dataset": DATASET_ID, "perPage": 5000, "serviceKey": service_key}, rows, len(rows)

    return ingest_with_fallback(f"DATA_GO_KR_{DATASET_ID}", load, store)


def _default_fetch(url: str) -> tuple[int, str]:
    import httpx

    response = httpx.get(url, timeout=60)
    return response.status_code, response.text


def fetch_all_rows(service_key: str, fetch: Fetcher | None = None,
                   per_page: int = 5000) -> list[dict[str, Any]]:
    if not service_key:
        raise SourceUnavailable("DATA_GO_KR_KEY_MISSING", "DATA_GO_KR_SERVICE_KEY not set")
    fetch = fetch or _default_fetch
    rows: list[dict[str, Any]] = []
    page = 1
    total = None
    while total is None or len(rows) < total:
        query = urllib.parse.urlencode(
            {"page": page, "perPage": per_page, "serviceKey": service_key, "returnType": "JSON"}
        )
        try:
            status, text = fetch(f"https://api.odcloud.kr/api{ODCLOUD_PATH}?{query}")
        except Exception as exc:
            raise SourceUnavailable("DATA_GO_KR_NETWORK_ERROR", type(exc).__name__) from None
        if status == 429:
            raise SourceUnavailable("DATA_GO_KR_RATE_LIMITED", "HTTP 429")
        if status in {401, 403}:
            raise SourceUnavailable("DATA_GO_KR_AUTH_INVALID", f"HTTP {status}")
        if status >= 400:
            raise SourceUnavailable("DATA_GO_KR_HTTP_ERROR", f"HTTP {status}")
        try:
            body = json.loads(text)
        except ValueError:
            raise SourceUnavailable("DATA_GO_KR_INVALID_RESPONSE", "non-JSON body") from None
        data = body.get("data") or []
        total = int(body.get("totalCount") or 0)
        if not data:
            break
        if page == 1:
            check_schema(f"DATA_GO_KR:{DATASET_ID}", REQUIRED_FIELDS, data[0].keys())
        rows.extend(data)
        page += 1
        if page > 100:  # hard stop: never loop forever on a misbehaving pager
            break
    if not rows:
        raise SourceUnavailable("DATA_GO_KR_NO_DATA", "empty response")
    return rows


def _int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Monthly national and per-branch series from 2021-10, with quality checks."""
    usable = []
    excluded_before_primary = 0
    invalid = 0
    for row in rows:
        year, month = _int(row.get("년도")), _int(row.get("월"))
        if year is None or month is None or not 1 <= month <= 12:
            invalid += 1
            continue
        if (year, month) < PRIMARY_PERIOD_START:
            excluded_before_primary += 1
            continue
        usable.append((f"{year:04d}-{month:02d}", row))

    national: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    branch: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    complexes: dict[str, int] = defaultdict(int)
    category_mismatch = 0
    zero_rows = 0
    for period, row in usable:
        total = _int(row.get("지원내용총건수")) or 0
        parts = [_int(row.get(field)) or 0 for field in CATEGORY_FIELDS]
        if sum(parts) != total:
            category_mismatch += 1
        if total == 0:
            zero_rows += 1
        bucket = national[period]
        bucket["total"] += total
        bucket["target_households"] += _int(row.get("대상세대(인원수)")) or 0
        for field, value in zip(CATEGORY_FIELDS, parts, strict=True):
            bucket[field] += value
        branch[str(row.get("지사명") or "미상")][period] += total
        complexes[period] += 1

    periods = sorted(national)
    missing_months = _missing_months(periods)
    return {
        "dataset_id": DATASET_ID,
        "version_label": ODCLOUD_VERSION_LABEL,
        "domain_label": DOMAIN_LABEL,
        "domain_label_ko": DOMAIN_LABEL_KO,
        "official_limitation": OFFICIAL_LIMITATION,
        "primary_period_start": "2021-10",
        "input_rows": len(rows),
        "usable_rows": len(usable),
        "excluded_before_primary_period": excluded_before_primary,
        "invalid_period_rows": invalid,
        "zero_total_rows": zero_rows,
        "category_total_mismatch_rows": category_mismatch,
        "periods": periods,
        "missing_months": missing_months,
        "national_monthly": [
            {"period": p, "complex_count": complexes[p], **dict(national[p])} for p in periods
        ],
        "branch_monthly": {
            name: [{"period": p, "total": series.get(p)} for p in periods]
            for name, series in sorted(branch.items())
        },
        "allowed_uses": [
            "월별 건수 변동성 분석",
            "시계열 예측 방법 검증 프레임워크",
            "서비스 유형 분포 참고",
            "운영 부하 분포 참고",
        ],
        "forbidden_uses": ["농촌 마을 수요 기준값", "마을 서비스 회차 환산"],
    }


def _missing_months(periods: list[str]) -> list[str]:
    if not periods:
        return []
    year, month = map(int, periods[0].split("-"))
    end = tuple(map(int, periods[-1].split("-")))
    present = set(periods)
    missing = []
    while (year, month) <= end:
        key = f"{year:04d}-{month:02d}"
        if key not in present:
            missing.append(key)
        month += 1
        if month > 12:
            year, month = year + 1, 1
    return missing
