import json
import os

import pytest

from backend.home_doctor import (
    DOMAIN_LABEL,
    REQUIRED_FIELDS,
    fetch_all_rows,
    summarize,
)
from backend.kosis import KOSIS_TABLES, KosisClient, normalize_kosis_key, parse_table
from backend.source_snapshots import (
    SchemaDriftDetected,
    SnapshotStore,
    SourceUnavailable,
    check_schema,
    ingest_with_fallback,
    redact_params,
)

TABLE = next(t for t in KOSIS_TABLES if t.table_id == "DT_117078_011")
SECRET = "abcDEF123secretKOSISkeyValue0000000000000A"


def kosis_row(code: str, name: str, value: str) -> dict:
    return {
        "ORG_ID": "117", "TBL_ID": TABLE.table_id, "TBL_NM": TABLE.table_name,
        "PRD_DE": "2023", "PRD_SE": "2년", "C1": code, "C1_NM": name,
        "C1_OBJ_NM": "서비스영역별", "ITM_ID": "T001", "ITM_NM": "필요대비이용률",
        "UNIT_NM": None, "DT": value, "LST_CHN_DE": "2025-03-18",
    }


def fake_fetch(responses):
    calls = []

    def fetch(url):
        calls.append(url)
        return responses.pop(0)

    fetch.calls = calls
    return fetch


def test_kosis_key_padding_is_normalized_without_changing_valid_keys():
    assert normalize_kosis_key("abc") == "abc="
    assert normalize_kosis_key("abcd") == "abcd"
    assert normalize_kosis_key("  ab ") == "ab=="


def test_kosis_parser_keeps_dimensions_and_missing_values():
    rows = [kosis_row("A0201", "노인 돌봄 서비스", "32.5"), kosis_row("A0402", "정신건강", "-")]
    fetch = fake_fetch([(200, json.dumps(rows))])
    parsed = parse_table(TABLE, KosisClient(SECRET, fetch=fetch).table_data(TABLE))
    assert parsed["table_id"] == "DT_117078_011"
    assert parsed["org_id"] == "117"
    assert parsed["period"] == "2023"
    assert parsed["dimensions"] == ["서비스영역별"]
    assert parsed["last_updated"] == "2025-03-18"
    assert parsed["provenance"] == "EXTERNAL_CONTEXT"
    assert parsed["records"][0]["value"] == 32.5
    assert parsed["records"][1]["value"] is None  # never zero-filled


def test_kosis_missing_key_is_reported_not_fabricated():
    with pytest.raises(SourceUnavailable) as exc:
        KosisClient("")
    assert exc.value.code == "KOSIS_KEY_MISSING"


def test_kosis_rate_limit_and_auth_errors_do_not_leak_key():
    fetch = fake_fetch([(429, "")])
    with pytest.raises(SourceUnavailable) as exc:
        KosisClient(SECRET, fetch=fetch).table_data(TABLE)
    assert exc.value.code == "KOSIS_RATE_LIMITED"
    assert SECRET not in str(exc.value)
    fetch = fake_fetch([(200, json.dumps({"err": "11", "errMsg": "유효하지않은 인증KEY"}))])
    with pytest.raises(SourceUnavailable) as exc:
        KosisClient(SECRET, fetch=fetch).table_data(TABLE)
    assert exc.value.code == "KOSIS_AUTH_INVALID"


def test_kosis_two_dimension_tables_retry_with_second_level():
    rows = [kosis_row("A0201", "노인 돌봄 서비스", "32.5")]
    fetch = fake_fetch([
        (200, json.dumps({"err": "20", "errMsg": "필수요청변수값이 누락되었습니다. (objL)"})),
        (200, json.dumps(rows)),
    ])
    assert len(KosisClient(SECRET, fetch=fetch).table_data(TABLE)) == 1
    assert "objL2=ALL" in fetch.calls[1]


def test_kosis_schema_drift_is_detected_not_silently_parsed():
    row = kosis_row("A0201", "노인 돌봄 서비스", "32.5")
    del row["DT"]
    fetch = fake_fetch([(200, json.dumps([row]))])
    with pytest.raises(SchemaDriftDetected) as exc:
        KosisClient(SECRET, fetch=fetch).table_data(TABLE)
    assert "DT" in exc.value.missing


@pytest.mark.parametrize(
    ("response", "expected_code"),
    [
        ((503, "upstream unavailable"), "KOSIS_HTTP_ERROR"),
        ((200, "not-json"), "KOSIS_INVALID_RESPONSE"),
        ((200, "[]"), "KOSIS_NO_DATA"),
    ],
)
def test_kosis_failure_matrix_http_malformed_and_empty(response, expected_code):
    client = KosisClient(SECRET, fetch=fake_fetch([response]))
    with pytest.raises(SourceUnavailable) as exc:
        client.table_data(TABLE)
    assert exc.value.code == expected_code
    assert SECRET not in str(exc.value)


def test_kosis_failure_matrix_timeout_is_safe_and_redacted():
    def timeout(_url):
        raise TimeoutError("request exceeded timeout")

    with pytest.raises(SourceUnavailable) as exc:
        KosisClient(SECRET, fetch=timeout).table_data(TABLE)
    assert exc.value.code == "KOSIS_NETWORK_ERROR"
    assert "TimeoutError" in str(exc.value)
    assert SECRET not in str(exc.value)


def test_cache_fallback_returns_last_successful_snapshot(tmp_path):
    retrieved_at = "2025-12-31T12:30:00+00:00"
    store = SnapshotStore(tmp_path)
    ok = ingest_with_fallback(
        "KOSIS_X", lambda: ({"apiKey": SECRET, "tblId": "X"}, {"v": 1}, 1), store
    )
    assert ok["status"] == "LIVE"
    assert ok["snapshot"]["request_params"]["apiKey"] == "<redacted>"
    store.store(
        "STALE_X", request_params={}, payload={"v": 1}, record_count=1,
        retrieved_at=retrieved_at,
    )

    def down():
        raise SourceUnavailable("KOSIS_NETWORK_ERROR", "ConnectError")

    fallback = ingest_with_fallback("KOSIS_X", down, store)
    assert fallback["status"] == "CACHED_FALLBACK"
    assert fallback["snapshot"]["payload"] == {"v": 1}
    assert fallback["cache_note"].endswith("기준 캐시")
    stale = ingest_with_fallback(
        "STALE_X",
        lambda: (_ for _ in ()).throw(SourceUnavailable("HTTP_TIMEOUT", "timeout")),
        store,
    )
    assert stale["status"] == "CACHED_FALLBACK"
    assert stale["error_code"] == "HTTP_TIMEOUT"
    assert stale["snapshot"]["retrieved_at"] == retrieved_at
    assert "2025-12-31" in stale["cache_note"]
    for path in tmp_path.rglob("*.json"):
        assert SECRET not in path.read_text(encoding="utf-8")


def test_no_cache_and_failure_reports_unavailable(tmp_path):
    def down():
        raise SourceUnavailable("KOSIS_NETWORK_ERROR", "x")

    result = ingest_with_fallback("NEW", down, SnapshotStore(tmp_path))
    assert result["status"] == "UNAVAILABLE"
    assert result["snapshot"] is None


def test_snapshots_are_content_addressed_and_immutable(tmp_path):
    store = SnapshotStore(tmp_path)
    first = store.store("S", request_params={}, payload=[1, 2], record_count=2)
    second = store.store("S", request_params={}, payload=[1, 2], record_count=2,
                         retrieved_at="2030-01-01T00:00:00+00:00")
    assert first.snapshot_id == second.snapshot_id
    assert store.latest("S").retrieved_at == first.retrieved_at


def test_redaction_covers_common_key_names():
    assert redact_params({"serviceKey": "x", "ApiKey": "y", "page": 1}) == {
        "ApiKey": "<redacted>", "page": 1, "serviceKey": "<redacted>"}


def hd_row(year, month, total, parts=(1, 1, 1, 1), branch="서울지사"):
    return {
        "년도": year, "월": month, "지사명": branch, "단지명": "단지", "임대유형": "영구임대",
        "세대수": 100, "대상세대(인원수)": 5, "지원내용총건수": total,
        "생활지원": parts[0], "가사지원": parts[1], "의료지원": parts[2], "경제지원": parts[3],
    }


def test_home_doctor_monthly_parsing_and_primary_period_filter():
    rows = [hd_row(2021, 9, 4), hd_row(2021, 10, 4), hd_row(2021, 12, 4), hd_row(2022, 1, 4)]
    summary = summarize(rows)
    assert summary["excluded_before_primary_period"] == 1
    assert summary["periods"] == ["2021-10", "2021-12", "2022-01"]
    assert summary["missing_months"] == ["2021-11"]
    assert summary["national_monthly"][0]["total"] == 4


def test_home_doctor_zero_rows_and_category_totals():
    summary = summarize([hd_row(2022, 1, 0, (0, 0, 0, 0)), hd_row(2022, 1, 9, (1, 1, 1, 1))])
    assert summary["zero_total_rows"] == 1
    assert summary["category_total_mismatch_rows"] == 1
    month = summary["national_monthly"][0]
    assert month["생활지원"] == 1 and month["total"] == 9


def test_home_doctor_empty_input_and_domain_label():
    summary = summarize([])
    assert summary["periods"] == [] and summary["missing_months"] == []
    assert summary["domain_label"] == DOMAIN_LABEL == "EXTERNAL_OPERATIONAL_REFERENCE"
    assert "농촌 마을 수요 기준값" in summary["forbidden_uses"]


def test_home_doctor_schema_drift_and_missing_key():
    with pytest.raises(SourceUnavailable):
        fetch_all_rows("")
    bad = {k: 1 for k in REQUIRED_FIELDS if k != "의료지원"}
    fetch = fake_fetch([(200, json.dumps({"data": [bad], "totalCount": 1}))])
    with pytest.raises(SchemaDriftDetected):
        fetch_all_rows("key", fetch=fetch)


@pytest.mark.parametrize(
    ("response", "expected_code"),
    [
        ((503, "server error"), "DATA_GO_KR_HTTP_ERROR"),
        ((200, "bad json"), "DATA_GO_KR_INVALID_RESPONSE"),
        ((200, json.dumps({"data": [], "totalCount": 0})), "DATA_GO_KR_NO_DATA"),
    ],
)
def test_home_doctor_failure_matrix_http_malformed_and_empty(response, expected_code):
    with pytest.raises(SourceUnavailable) as exc:
        fetch_all_rows("not-a-real-key", fetch=fake_fetch([response]))
    assert exc.value.code == expected_code
    assert "not-a-real-key" not in str(exc.value)


def test_home_doctor_failure_matrix_timeout_is_safe():
    def timeout(_url):
        raise TimeoutError("request exceeded timeout")

    with pytest.raises(SourceUnavailable) as exc:
        fetch_all_rows("not-a-real-key", fetch=timeout)
    assert exc.value.code == "DATA_GO_KR_NETWORK_ERROR"
    assert "TimeoutError" in str(exc.value)
    assert "not-a-real-key" not in str(exc.value)


def test_check_schema_reports_unexpected_fields_without_failing():
    result = check_schema("S", ["a"], ["a", "b"])
    assert result == {"status": "SCHEMA_OK", "unexpected_fields": ["b"]}


@pytest.mark.skipif(os.environ.get("VC_LIVE_SMOKE") != "1", reason="live smoke is opt-in")
def test_live_kosis_and_home_doctor_smoke():
    from scripts.api_smoke_test import _load_config

    rows = KosisClient(_load_config("KOSIS_API_KEY")).table_data(TABLE)
    assert rows and rows[0]["TBL_ID"] == TABLE.table_id
    hd = fetch_all_rows(_load_config("DATA_GO_KR_SERVICE_KEY"), per_page=5000)
    assert len(hd) > 1000
