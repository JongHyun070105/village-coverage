"""KOSIS OpenAPI client for 사회서비스수요·공급실태조사 context tables (V4 §12, §13).

Only tables confirmed in the live KOSIS catalog are listed. Values are
EXTERNAL_CONTEXT for broad social services and are never merged with the KREI
rural living-service prior.
"""

from __future__ import annotations

import json
import urllib.parse
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from backend.source_snapshots import SourceUnavailable, check_schema

KOSIS_BASE = "https://kosis.kr/openapi"
KOSIS_ORG_ID = "117"
KOSIS_SURVEY_NAME = "사회서비스수요·공급실태조사"
KOSIS_CATALOG_PATH = "G > G_14 > 117_A_003 (복지 > 사회서비스수요·공급실태조사 > 2013년이후)"
REQUIRED_DATA_FIELDS = ("ORG_ID", "TBL_ID", "PRD_DE", "C1", "C1_NM", "ITM_NM", "DT", "LST_CHN_DE")


@dataclass(frozen=True, slots=True)
class KosisTable:
    table_id: str
    table_name: str
    topic: str
    period_type: str  # KOSIS prdSe value


# Confirmed by statisticsList.do walk of 117_A_003 on 2026-10-03.
KOSIS_TABLES: tuple[KosisTable, ...] = (
    KosisTable("DT_117078_001", "최근 1년간 필요했던 사회서비스: 서비스 영역별", "need", "F"),
    KosisTable("DT_117078_003", "최근 1년간 이용 경험이 있는 사회서비스: 서비스 영역별",
               "usage", "F"),
    KosisTable("DT_117078_011", "사회서비스 필요 대비 이용률", "usage_among_need", "F"),
    KosisTable("DT_117078_005", "향후 1년 내에 이용 의향이 있는 사회서비스: 서비스 영역별",
               "intention", "F"),
    KosisTable("DT_117078_012", "서비스 영역별 양적 충분성", "sufficiency", "F"),
    KosisTable("DT_117078_04", "사회서비스 이용료 부담 주체에 대한 의견: 생애주기별",
               "fee_burden_opinion", "F"),
    KosisTable("DT_117078_01", "영역별 사회서비스 이용률", "usage_legacy", "F"),
    KosisTable("DT_117078_09", "지역 내 동일한서비스 제공 사업체 존재 여부 및 경쟁 사업체 수",
               "local_supplier_presence", "F"),
)

# Requested topics with no matching table in the live catalog (recorded, not guessed).
KOSIS_TOPICS_NOT_FOUND = (
    {"topic": "이용료 지불의사", "status": "NOT_FOUND_IN_CATALOG",
     "closest_table": "DT_117078_04 (이용료 부담 주체 의견; 지불의사와 다른 개념)"},
    {"topic": "희망 이용시간", "status": "NOT_FOUND_IN_CATALOG", "closest_table": None},
)


def normalize_kosis_key(raw: str) -> str:
    """Restore base64 '=' padding that is commonly lost when copying KOSIS keys."""
    key = raw.strip()
    if key and len(key) % 4:
        key += "=" * (-len(key) % 4)
    return key


Fetcher = Callable[[str], tuple[int, str]]


def _default_fetch(url: str) -> tuple[int, str]:
    import httpx

    response = httpx.get(url, timeout=30)
    return response.status_code, response.text


class KosisClient:
    def __init__(self, api_key: str, fetch: Fetcher | None = None):
        if not api_key:
            raise SourceUnavailable("KOSIS_KEY_MISSING", "KOSIS_API_KEY is not configured")
        self._key = normalize_kosis_key(api_key)
        self._fetch = fetch or _default_fetch

    def _call(self, path: str, params: dict[str, str]) -> Any:
        query = {"apiKey": self._key, "format": "json", "jsonVD": "Y", **params}
        url = f"{KOSIS_BASE}/{path}?" + urllib.parse.urlencode(query)
        try:
            status, text = self._fetch(url)
        except Exception as exc:  # network errors: never echo the URL (contains the key)
            raise SourceUnavailable("KOSIS_NETWORK_ERROR", type(exc).__name__) from None
        if status == 429:
            raise SourceUnavailable("KOSIS_RATE_LIMITED", "HTTP 429")
        if status >= 400:
            raise SourceUnavailable("KOSIS_HTTP_ERROR", f"HTTP {status}")
        try:
            data = json.loads(text)
        except ValueError:
            raise SourceUnavailable("KOSIS_INVALID_RESPONSE", "non-JSON body") from None
        if isinstance(data, dict) and "err" in data:
            code = str(data.get("err"))
            message = str(data.get("errMsg", ""))
            if code == "11":
                raise SourceUnavailable("KOSIS_AUTH_INVALID", "invalid key")
            if code == "30":
                raise SourceUnavailable("KOSIS_NO_DATA", "no data")
            if code == "20":
                raise SourceUnavailable("KOSIS_MISSING_PARAM", message[:60])
            if "초과" in message:
                raise SourceUnavailable("KOSIS_RATE_LIMITED", message[:60])
            raise SourceUnavailable(f"KOSIS_ERROR_{code}", message[:60])
        return data

    def table_comments(self, table: KosisTable) -> list[dict[str, Any]]:
        try:
            return self._call(
                "statisticsData.do",
                {"method": "getMeta", "type": "CMMT", "orgId": KOSIS_ORG_ID,
                 "tblId": table.table_id},
            )
        except SourceUnavailable:
            return []

    def table_data(self, table: KosisTable, latest_periods: int = 1) -> list[dict[str, Any]]:
        params = {
            "method": "getList", "orgId": KOSIS_ORG_ID, "tblId": table.table_id,
            "itmId": "ALL", "objL1": "ALL", "prdSe": table.period_type,
            "newEstPrdCnt": str(latest_periods),
        }
        try:
            rows = self._call("Param/statisticsParameterData.do", params)
        except SourceUnavailable as exc:
            if exc.code not in {"KOSIS_NO_DATA", "KOSIS_MISSING_PARAM"}:
                raise
            # Two-dimension tables need objL2 as well.
            rows = self._call("Param/statisticsParameterData.do", {**params, "objL2": "ALL"})
        if not isinstance(rows, list) or not rows:
            raise SourceUnavailable("KOSIS_NO_DATA", "empty list")
        check_schema(f"KOSIS:{table.table_id}", REQUIRED_DATA_FIELDS, rows[0].keys())
        return rows


def parse_table(table: KosisTable, rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Normalize one KOSIS table into a provenance-tagged snapshot entry."""
    dims = sorted({key[:-3] for row in rows for key in row if key.endswith("_NM")
                   and key.startswith("C") and key[1:-3].isdigit()})
    records = []
    for row in rows:
        raw = str(row.get("DT", "")).strip()
        try:
            value: float | None = float(raw)
        except ValueError:
            value = None  # '-' or blank stays missing; never zero-filled
        records.append({
            "period": row.get("PRD_DE"),
            "item": row.get("ITM_NM"),
            "unit": row.get("UNIT_NM"),
            "dimensions": {d: row.get(f"{d}_NM") for d in dims},
            "codes": {d: row.get(d) for d in dims},
            "value": value,
        })
    periods = sorted({str(row.get("PRD_DE")) for row in rows})
    return {
        "org_id": KOSIS_ORG_ID,
        "table_id": table.table_id,
        "table_name": table.table_name,
        "topic": table.topic,
        "period": periods[-1] if periods else None,
        "periods": periods,
        "unit": sorted({str(r.get("UNIT_NM")) for r in rows if r.get("UNIT_NM")}),
        "dimensions": [rows[0].get(f"{d}_OBJ_NM") or d for d in dims],
        "source": f"KOSIS {KOSIS_SURVEY_NAME} (보건복지부)",
        "last_updated": max((str(r.get("LST_CHN_DE") or "") for r in rows), default=None),
        "provenance": "EXTERNAL_CONTEXT",
        "scope_note": "전국 가구 대상 사회서비스 조사; 농촌 생활서비스와 동일 개념 아님",
        "record_count": len(records),
        "records": records,
    }
