import dataclasses

import pytest

from backend.empirical_priors import (
    DEFINITIONS,
    JANGGOK_LAUNDRY_CASE,
    KREI_SOURCE,
    KREI_TABLE_4_8,
    LAUNDRY_CASES,
    empirical_prior_snapshot,
    prior_for_service,
    prior_payload,
)
from backend.provenance import EvidenceLevel, calibration_status_v4
from backend.source_registry import SOURCES, DataSource, source_map

# Independent transcription of <표 4-8> (need, usage, unmet) checked against the PDF.
EXPECTED = {
    "이동 및 외출 지원": (13.2, 16.5, 83.5),
    "반찬 지원, 장보기": (16.5, 14.0, 86.0),
    "청소, 세탁": (19.0, 16.4, 83.6),
    "목욕 지원": (17.8, 26.7, 73.3),
    "이미용": (21.0, 20.1, 79.9),
    "쓰레기/폐기물 처리": (22.3, 12.8, 87.2),
    "공동급식": (18.8, 19.6, 80.4),
    "평생교육": (28.4, 21.1, 78.9),
    "문화·여가": (35.2, 29.7, 70.3),
    "도서 대여": (27.5, 16.3, 83.7),
    "건강교실": (41.1, 29.8, 70.2),
    "상하수도": (28.0, 4.9, 95.1),
    "간단 집수리": (31.8, 5.6, 94.4),
    "전기 수리": (33.1, 5.8, 94.2),
    "안전손잡이": (25.6, 7.4, 92.6),
    "도배": (31.2, 6.6, 93.4),
}


def test_all_sixteen_krei_rows_match_report_values():
    assert len(KREI_TABLE_4_8) == 16
    for prefix, values in EXPECTED.items():
        matches = [row for row in KREI_TABLE_4_8 if prefix in row.service_label]
        assert len(matches) == 1, prefix
        row = matches[0]
        assert (row.need_rate, row.usage_rate, row.unmet_rate) == values


def test_need_and_usage_are_distinct_quantities():
    for row in KREI_TABLE_4_8:
        assert row.need_rate != row.usage_rate
        assert 0 < row.need_rate < 100


def test_usage_plus_unmet_is_one_hundred_percent_of_needers():
    for row in KREI_TABLE_4_8:
        assert row.usage_rate + row.unmet_rate == pytest.approx(100.0, abs=0.11)


def test_demo_service_mapping_is_explicit_and_unique():
    assert prior_for_service("laundry").service_label == "청소, 세탁"
    assert prior_for_service("daily_necessities").service_label == "반찬 지원, 장보기"
    assert prior_for_service("home_repair").service_label.startswith("간단 집수리")
    assert prior_for_service("medical_service") is None
    mapped = [row.service_type for row in KREI_TABLE_4_8 if row.service_type]
    assert len(mapped) == len(set(mapped))


def test_source_values_are_immutable():
    row = prior_for_service("laundry")
    with pytest.raises(dataclasses.FrozenInstanceError):
        row.need_rate = 50.0  # type: ignore[misc]


def test_definitions_preserve_krei_wording():
    assert "‘전혀 필요 없음’과 ‘필요 없음’" in DEFINITIONS["need_rate"]
    assert "필요로 하는 사람 중" in DEFINITIONS["usage_rate"]
    assert "필요자 중" in DEFINITIONS["unmet_rate"]


def test_prior_payload_carries_required_metadata_and_warning():
    payload = prior_payload(prior_for_service("laundry"))
    for key in (
        "source_title", "publisher", "report_id", "published_date", "table_id",
        "service_label", "definition", "need_rate", "usage_rate", "unmet_rate",
        "population_scope", "source_scope", "provenance",
    ):
        assert payload[key] not in (None, ""), key
    assert payload["confidence_class"] == "EMPIRICAL_EXTERNAL"
    assert payload["provenance"] == "EXTERNAL_EMPIRICAL_PRIOR"
    assert "실제 수요" in payload["interpretation_warning"]
    assert KREI_SOURCE["sample_size"] == "NOT_STATED_IN_SOURCE"


def test_local_calibration_never_overwrites_external_raw_value():
    before = empirical_prior_snapshot()["snapshot_hash"]
    status = calibration_status_v4(has_external_prior=True, local_status_v3="CALIBRATED")
    assert status == "LOCAL_CALIBRATED"
    assert prior_for_service("laundry").need_rate == 19.0
    assert empirical_prior_snapshot()["snapshot_hash"] == before


def test_external_prior_alone_never_reaches_local_calibration():
    status = calibration_status_v4(has_external_prior=True, local_status_v3="UNCALIBRATED")
    assert status == "EXTERNAL_EMPIRICAL"
    assert calibration_status_v4(
        has_external_prior=False, local_status_v3="UNCALIBRATED"
    ) == "SYNTHETIC_ONLY"
    assert EvidenceLevel.EXTERNAL_EMPIRICAL_PRIOR < EvidenceLevel.LOCAL_CALIBRATED


def test_operational_validation_requires_local_calibration_first():
    assert calibration_status_v4(
        has_external_prior=True, local_status_v3="LIMITED_SAMPLE", operational_validation=True
    ) == "LOCAL_LIMITED"


def test_laundry_cases_are_case_references_not_defaults():
    assert len(LAUNDRY_CASES) == 6
    for case in (*LAUNDRY_CASES, JANGGOK_LAUNDRY_CASE):
        assert case.usage == "CASE_REFERENCE"
    sapyeong = next(case for case in LAUNDRY_CASES if case.name == "사평 빨래방")
    assert sapyeong.vehicle_count == 3
    assert "150" in sapyeong.daily_capacity


def test_snapshot_hash_is_deterministic():
    assert empirical_prior_snapshot() == empirical_prior_snapshot()


def test_unclear_license_blocks_ingestion():
    ok = source_map()["KREI_R2025_23"]
    assert ok.ingest_status == "INGEST_ALLOWED"
    unclear = DataSource(**{**dataclasses.asdict(ok), "license_status": "UNCLEAR"})
    assert unclear.ingest_status == "INGEST_BLOCKED"


def test_cross_domain_sources_declare_forbidden_uses():
    by_id = source_map()
    assert by_id["DATA_GO_KR_15120958"].role == "EXTERNAL_OPERATIONAL_REFERENCE"
    assert any("농촌 수요" in item for item in by_id["DATA_GO_KR_15120958"].must_not)
    assert by_id["KOSIS_117_DT_117078"].role == "EXTERNAL_CONTEXT"
    assert any("KREI" in item for item in by_id["KOSIS_117_DT_117078"].must_not)
    assert all(source.checked_at for source in SOURCES)


def test_provider_directories_are_discovery_only_not_operational_supply():
    by_id = source_map()
    cooperatives = by_id["DATA_GO_KR_15155661"]
    self_support = by_id["DATA_GO_KR_15091502"]
    for source in (cooperatives, self_support):
        assert source.reality == "REAL"
        assert any("수용량" in item for item in source.limitations)
        assert any("실제 공급자" in item for item in source.must_not)
        assert any("수집·표시하지 않음" in item for item in source.limitations)
    assert cooperatives.license_status == "UNCLEAR"
    assert cooperatives.ingest_status == "INGEST_BLOCKED"
    assert self_support.license_status == "OPEN_NO_RESTRICTION"
    assert self_support.source_url.endswith("15091502/fileData.do")
