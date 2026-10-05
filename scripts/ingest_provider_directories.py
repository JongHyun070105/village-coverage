"""Fetch reviewed official provider files and persist PII-minimized snapshots.

Only the two public files with a verified direct download are enabled here.
The social-enterprise catalogue remains license-allowed but is not scraped: its
official listing page did not provide a directly verifiable bulk file in this
audit. The cooperative catalogue stays blocked by the source registry.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import posixpath
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend import database  # noqa: E402
from backend.provider_directory import ingest_directory_snapshot  # noqa: E402
from backend.provider_source_registry import (  # noqa: E402
    PROVIDER_SOURCES,
    ProviderSourceRegistry,
)

DATA_DIR = ROOT / "data" / "provider_snapshots"
ARTIFACT_DIR = ROOT / "artifacts"
USER_AGENT = "VillageCoverage/5.2 provider source audit"

SELF_SUPPORT_URL = (
    "https://www.data.go.kr/cmm/cmm/fileDownload.do?"
    "atchFileId=FILE_000000003607526&fileDetailSn=1&insertDataPrcus=N"
)
VILLAGE_ENTERPRISE_URL = (
    "https://www.mois.go.kr/cmm/fms/FileDown.do?atchFileId=FILE_00146938_7EjMH8&fileSn=0"
)

SELF_SUPPORT_SCHEMA = [
    "순번",
    "시도",
    "시군구",
    "자활기업",
    "자활기업구분",
    "대표자명",
    "업종",
    "사업자구분",
    "주소",
]
VILLAGE_ENTERPRISE_SCHEMA = [
    "연번",
    "시도",
    "시군구",
    "소재지",
    "마을기업명",
    "유형",
    "주 업종",
    "주 생산품 또는 서비스명",
    "사업내용",
    "사업자등록번호 (-포함 작성)",
]

SOURCE_AUDIT = {
    "checked_at": "2026-10-06",
    "sources": [
        {
            "source_id": "DATA_GO_KR_15091502",
            "source_name": "한국자활복지개발원 전국자활기업현황",
            "provider_authority": "한국자활복지개발원",
            "source_url": "https://www.data.go.kr/data/15091502/fileData.do",
            "dataset_id": "15091502",
            "license_type": "OPEN_NO_RESTRICTION",
            "reuse_allowed": True,
            "scope": "전국",
            "snapshot_date": "2025-12-31",
            "catalog_row_count": 977,
            "update_cycle": "연간; 다음 등록 예정 2027-04-08",
            "ingestion_status": "INGESTED",
            "fields_excluded": ["대표자명"],
            "schema_version": "self-support-v1",
        },
        {
            "source_id": "DATA_GO_KR_15090110",
            "source_name": "고용노동부 사회적기업 목록",
            "provider_authority": "고용노동부",
            "source_url": "https://www.data.go.kr/data/15090110/fileData.do",
            "dataset_id": "15090110",
            "license_type": "OPEN_NO_RESTRICTION",
            "reuse_allowed": True,
            "scope": "전국",
            "snapshot_date": "2025-06-30",
            "catalog_row_count": 3534,
            "update_cycle": "수시 (포털 자동 갱신 안내)",
            "ingestion_status": "INGEST_ALLOWED",
            "ingestion_note": (
                "공식 포털은 SEIS의 목록 화면을 연결하지만, 확인한 화면 응답에서 "
                "검증 가능한 원본 파일 링크를 찾지 못해 수집하지 않음"
            ),
            "schema_version": "social-enterprise-v1",
        },
        {
            "source_id": "DATA_GO_KR_15080745",
            "source_name": "행정안전부 전국 마을기업 현황",
            "provider_authority": "행정안전부",
            "source_url": "https://www.data.go.kr/data/15080745/fileData.do",
            "dataset_id": "15080745",
            "license_type": "OPEN_NO_RESTRICTION",
            "reuse_allowed": True,
            "scope": "전국",
            "snapshot_date": "2025-12-31",
            "catalog_row_count": 1726,
            "update_cycle": "연간; 다음 등록 예정 2027-09-14",
            "ingestion_status": "INGESTED",
            "fields_excluded": ["사업자등록번호"],
            "schema_version": "village-enterprise-v1",
        },
        {
            "source_id": "DATA_GO_KR_15155661",
            "source_name": "전국협동조합표준데이터",
            "provider_authority": "기획재정부 소관 / 지방자치단체 제공",
            "source_url": "https://www.data.go.kr/data/15155661/standard.do",
            "dataset_id": "15155661",
            "license_type": "UNCLEAR",
            "reuse_allowed": False,
            "scope": "전국; 지자체 자료의 월별 병합으로 시차 가능",
            "snapshot_date": "2026-09-15 (포털 수정일)",
            "update_cycle": "월별 병합; 지자체별 제공 일정",
            "ingestion_status": "INGEST_BLOCKED",
            "ingestion_note": "공식 표준데이터 페이지에서 재사용 허가 문구를 확인하지 못함",
            "schema_version": "cooperative-standard-unverified",
        },
    ],
}


def _download(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=45) as response:
        payload = response.read()
        if response.status != 200 or not payload:
            raise RuntimeError("Official provider file download returned no usable bytes")
    return payload


def _decode_csv(payload: bytes) -> tuple[list[str], list[dict[str, str]]]:
    decoded = None
    for encoding in ("utf-8-sig", "cp949", "euc-kr"):
        try:
            decoded = payload.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if decoded is None:
        raise ValueError("Official CSV is not UTF-8 or CP949")
    reader = csv.DictReader(io.StringIO(decoded, newline=""))
    headers = [_clean_header(value or "") for value in (reader.fieldnames or [])]
    if not headers or len(headers) != len(set(headers)):
        raise ValueError("Official CSV header is empty or contains duplicates")
    records = []
    for row in reader:
        records.append(
            {_clean_header(key or ""): (value or "").strip() for key, value in row.items()}
        )
    return headers, records


def _clean_header(value: str) -> str:
    return " ".join(value.replace("\ufeff", "").split())


def _column_number(reference: str) -> int:
    letters = re.match(r"[A-Z]+", reference.upper())
    if letters is None:
        raise ValueError("Invalid worksheet cell reference")
    number = 0
    for letter in letters.group(0):
        number = number * 26 + ord(letter) - ord("A") + 1
    return number - 1


def _xlsx_rows(payload: bytes) -> tuple[list[str], list[dict[str, str]]]:
    namespace = {
        "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
        "rel": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
        "pkg": "http://schemas.openxmlformats.org/package/2006/relationships",
    }
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        shared: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            shared_root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            shared = [
                "".join(part.text or "" for part in item.findall(".//main:t", namespace))
                for item in shared_root.findall("main:si", namespace)
            ]
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        targets = {
            item.attrib["Id"]: item.attrib["Target"]
            for item in relationships.findall("pkg:Relationship", namespace)
        }
        sheet = workbook.find("main:sheets/main:sheet", namespace)
        if sheet is None:
            raise ValueError("Official workbook has no worksheet")
        target = targets[sheet.attrib[f"{{{namespace['rel']}}}id"]]
        sheet_path = (
            target.lstrip("/")
            if target.startswith("/")
            else posixpath.normpath(posixpath.join("xl", target))
        )
        worksheet = ET.fromstring(archive.read(sheet_path))
        rows = worksheet.findall(".//main:sheetData/main:row", namespace)

        def read_cell(cell: ET.Element) -> str:
            kind = cell.attrib.get("t")
            if kind == "inlineStr":
                return "".join(text.text or "" for text in cell.findall(".//main:t", namespace))
            value = cell.find("main:v", namespace)
            if value is None:
                return ""
            if kind == "s":
                return shared[int(value.text or "0")]
            return value.text or ""

        decoded_rows: list[tuple[int, list[str]]] = []
        for index, row in enumerate(rows):
            values: list[str] = []
            for cell in row.findall("main:c", namespace):
                col = _column_number(cell.attrib.get("r", "A1"))
                while len(values) <= col:
                    values.append("")
                values[col] = read_cell(cell)
            decoded_rows.append((index + 1, values))

        header_index = next(
            (
                index
                for index, values in decoded_rows[:15]
                if {"시도", "시군구", "마을기업명", "소재지"}.issubset(
                    {_clean_header(value) for value in values if value}
                )
            ),
            None,
        )
        if header_index is None:
            raise ValueError("Official workbook column header was not found")
        raw_headers = decoded_rows[header_index - 1][1]
        headers = [_clean_header(value) for value in raw_headers]
        if not headers or len(headers) != len(set(value for value in headers if value)):
            raise ValueError("Official workbook header is empty or contains duplicates")
        records: list[dict[str, str]] = []
        for row_number, values in decoded_rows[header_index:]:
            record = {
                headers[column]: (values[column] if column < len(values) else "").strip()
                for column in range(len(headers))
                if headers[column]
            }
            if any(value.strip() for value in record.values()):
                record["__row_number"] = str(row_number)
                records.append(record)
        return headers, records


def _normalize_self_support(records: list[dict[str, str]]) -> list[dict[str, object]]:
    normalized = []
    for index, row in enumerate(records, start=2):
        name = row.get("자활기업", "").strip()
        if not name:
            continue
        normalized.append(
            {
                "name": name,
                "source_record_id": f"DATA_GO_KR_15091502:row-{index:06d}",
                "organization_type": row.get("자활기업구분", "").strip() or "자활기업",
                "region_label": " ".join(
                    part
                    for part in (row.get("시도", "").strip(), row.get("시군구", "").strip())
                    if part
                ),
                "public_address": row.get("주소", "").strip(),
                "public_service_description": row.get("업종", "").strip(),
                "public_contact_available": False,
            }
        )
    return normalized


def _normalize_village_enterprises(
    records: list[dict[str, str]],
) -> list[dict[str, object]]:
    normalized = []
    for fallback_index, row in enumerate(records, start=1):
        name = row.get("마을기업명", "").strip()
        if not name:
            continue
        row_number = row.get("__row_number", str(fallback_index))
        descriptions = [
            row.get("주 업종", "").strip(),
            row.get("주 생산품 또는 서비스명", "").strip(),
        ]
        normalized.append(
            {
                "name": name,
                "source_record_id": f"DATA_GO_KR_15080745:row-{int(row_number):06d}",
                "organization_type": row.get("유형", "").strip() or "마을기업",
                "region_label": " ".join(
                    part
                    for part in (row.get("시도", "").strip(), row.get("시군구", "").strip())
                    if part
                ),
                "public_address": row.get("소재지", "").strip(),
                "public_service_description": " / ".join(part for part in descriptions if part),
                "public_contact_available": False,
            }
        )
    return normalized


def source_audit_report() -> dict[str, object]:
    return {**SOURCE_AUDIT, "audit_status": "OFFICIAL_CATALOG_CHECKED"}


def ingest_official_snapshots(*, db_path: Path) -> dict[str, object]:
    now = datetime.now(UTC).isoformat(timespec="seconds")
    download_specs = (
        (
            "DATA_GO_KR_15091502",
            SELF_SUPPORT_URL,
            _decode_csv,
            SELF_SUPPORT_SCHEMA,
            _normalize_self_support,
        ),
        (
            "DATA_GO_KR_15080745",
            VILLAGE_ENTERPRISE_URL,
            _xlsx_rows,
            VILLAGE_ENTERPRISE_SCHEMA,
            _normalize_village_enterprises,
        ),
    )
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    connection = database.connect(db_path)
    try:
        demo = json.loads((ROOT / "data" / "demo.json").read_text(encoding="utf-8"))
        database.seed_reference_data(connection, demo)
        registry = ProviderSourceRegistry()
        registry.sync(connection)
        results: list[dict[str, object]] = []
        for source_id, url, parser, expected_fields, normalizer in download_specs:
            source = next(item for item in PROVIDER_SOURCES if item.source_id == source_id)
            try:
                raw = _download(url)
                schema_fields, raw_rows = parser(raw)
                normalized = normalizer(raw_rows)
                result = ingest_directory_snapshot(
                    connection,
                    source_id,
                    raw_file=raw,
                    source_snapshot_date=source.snapshot_date,
                    downloaded_at=now,
                    schema_fields=schema_fields,
                    expected_schema_fields=expected_fields,
                    rows=normalized,
                )
                result["download_url"] = url
                if result.get("status") == "INGESTED":
                    result["normalized_snapshot_path"] = (
                        f"data/provider_snapshots/{source_id.lower()}_{source.snapshot_date}_"
                        f"{result['raw_file_hash'][:16]}.json"
                    )
                    snapshot = connection.execute(
                        """SELECT normalized_snapshot_json FROM provider_directory_snapshots
                           WHERE snapshot_id=?""",
                        (result.get("snapshot_id"),),
                    ).fetchone()
                    if snapshot:
                        destination = ROOT / str(result["normalized_snapshot_path"])
                        if not destination.exists():
                            destination.write_text(snapshot[0] + "\n", encoding="utf-8")
                result["source_rows"] = len(raw_rows)
                source_meta = next(
                    item for item in SOURCE_AUDIT["sources"] if item["source_id"] == source_id
                )
                catalog_count = int(source_meta["catalog_row_count"])
                file_count = len(normalized)
                result["catalog_row_count"] = catalog_count
                result["source_count_matches_catalog"] = catalog_count == file_count
                result["data_quality_warnings"] = (
                    []
                    if catalog_count == file_count
                    else [
                        {
                            "code": "PORTAL_METADATA_ROW_COUNT_MISMATCH",
                            "catalog_rows": catalog_count,
                            "file_rows": file_count,
                            "action": "검토 전까지 원본 행을 유지하고 차이를 확인합니다.",
                        }
                    ]
                )
                result["schema_fields"] = schema_fields
                results.append(result)
            except Exception as exc:
                registry.mark_result(
                    connection,
                    source_id,
                    status="ERROR",
                    error=f"PROVIDER_INGEST_ERROR:{type(exc).__name__}",
                    downloaded_at=now,
                )
                connection.commit()
                results.append(
                    {
                        "source_id": source_id,
                        "status": "ERROR",
                        "error_code": type(exc).__name__,
                        "source_snapshot_date": source.snapshot_date,
                        "download_url": url,
                        "ingested": 0,
                    }
                )
        connection.commit()
        current_results = {str(item["source_id"]): item for item in results}
        report = {
            "generated_at": now,
            "provider_sources": results,
            "not_ingested": [
                {
                    "source_id": source["source_id"],
                    "status": current_results.get(source["source_id"], {}).get(
                        "status", source["ingestion_status"]
                    ),
                    "reason": source.get(
                        "ingestion_note",
                        current_results.get(source["source_id"], {}).get("error_code", ""),
                    ),
                }
                for source in SOURCE_AUDIT["sources"]
                if current_results.get(source["source_id"], {}).get(
                    "status", source["ingestion_status"]
                )
                != "INGESTED"
            ],
            "data_classification": {
                "organization_existence": "REAL_DIRECTORY",
                "availability": "UNKNOWN",
                "capacity": "UNKNOWN",
                "price": "UNKNOWN",
                "participation": "UNKNOWN",
            },
            "raw_files_retained": False,
        }
        (ARTIFACT_DIR / "provider_source_audit.json").write_text(
            json.dumps(source_audit_report(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        (ARTIFACT_DIR / "provider_ingestion_summary.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return report
    finally:
        connection.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db",
        type=Path,
        default=database.database_path(),
        help="Target app database. The default is the configured local application database.",
    )
    args = parser.parse_args()
    report = ingest_official_snapshots(db_path=args.db)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
