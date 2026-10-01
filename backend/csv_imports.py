"""Strict, privacy-aware parsing and validation for operational CSV imports."""

from __future__ import annotations

import csv
import hashlib
import io
import json
from datetime import date, datetime
from typing import Any

from backend.demand import redact_pii
from backend.timeutils import korea_today

IMPORT_HEADERS = {
    "demand_observations": (
        "village_code",
        "date",
        "service_type",
        "source_type",
        "note",
    ),
    "provider_availability": (
        "provider_id",
        "date",
        "start_time",
        "end_time",
        "service_type",
    ),
    "existing_service_history": (
        "village_code",
        "service_type",
        "program_name",
        "monthly_rounds",
        "as_of_date",
    ),
}
MAX_CSV_BYTES = 5 * 1024 * 1024
MAX_CSV_ROWS = 5000

_SOURCE_TYPES = {
    "phone": "phone",
    "전화": "phone",
    "village_meeting": "village_meeting",
    "마을회의": "village_meeting",
    "proxy": "proxy",
    "이장/대리조사": "proxy",
    "이장·대리조사": "proxy",
    "field": "field",
    "현장": "field",
    "현장조사": "field",
}


class CSVImportFormatError(ValueError):
    """The file cannot be interpreted as one of the supported CSV contracts."""


def parse_csv(payload: bytes, import_type: str) -> tuple[str, list[dict[str, Any]]]:
    if import_type not in IMPORT_HEADERS:
        raise CSVImportFormatError("지원하지 않는 CSV 가져오기 유형입니다.")
    if not payload:
        raise CSVImportFormatError("CSV 파일이 비어 있습니다.")
    if len(payload) > MAX_CSV_BYTES:
        raise CSVImportFormatError("CSV 파일은 5MB 이하만 가져올 수 있습니다.")

    decoded: str | None = None
    for encoding in ("utf-8-sig", "cp949"):
        try:
            decoded = payload.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if decoded is None:
        raise CSVImportFormatError("UTF-8 또는 CP949 인코딩 CSV만 지원합니다.")

    try:
        reader = csv.DictReader(io.StringIO(decoded, newline=""), strict=True)
        original_headers = reader.fieldnames
        if not original_headers:
            raise CSVImportFormatError("CSV 첫 줄에서 열 이름을 찾을 수 없습니다.")
        if any(not isinstance(header, str) or not header.strip() for header in original_headers):
            raise CSVImportFormatError("CSV 열 이름이 비어 있거나 올바르지 않습니다.")
        headers = [header.strip().lstrip("\ufeff") for header in original_headers]
        if len(headers) != len(set(headers)):
            raise CSVImportFormatError("CSV 열 이름이 중복되었습니다.")
        expected = IMPORT_HEADERS[import_type]
        missing = [header for header in expected if header not in headers]
        unexpected = [header for header in headers if header not in expected]
        if missing or unexpected:
            details = []
            if missing:
                details.append("필수 열 누락: " + ", ".join(missing))
            if unexpected:
                details.append("지원하지 않는 열: " + ", ".join(unexpected))
            raise CSVImportFormatError(" / ".join(details))
        reader.fieldnames = headers
        rows: list[dict[str, Any]] = []
        for row_number, row in enumerate(reader, start=2):
            if len(rows) >= MAX_CSV_ROWS:
                raise CSVImportFormatError("한 번에 5,000행까지만 가져올 수 있습니다.")
            extra = row.pop(None, None)
            short_row = any(row.get(header) is None for header in expected)
            rows.append(
                {
                    "row_number": row_number,
                    "values": {header: (row.get(header) or "").strip() for header in expected},
                    "column_count_mismatch": short_row or bool(extra),
                }
            )
    except csv.Error as exc:
        raise CSVImportFormatError(f"CSV 문법 오류: {exc}") from None
    if not rows:
        raise CSVImportFormatError("가져올 데이터 행이 없습니다.")
    return hashlib.sha256(payload).hexdigest(), rows


def prepare_import_rows(
    import_type: str,
    parsed_rows: list[dict[str, Any]],
    *,
    area_by_code: dict[str, dict[str, Any]],
    provider_services: dict[str, set[str]],
    service_policy: dict[str, str],
) -> list[dict[str, Any]]:
    """Return sanitized row records with explicit import/review/failure states."""
    prepared: list[dict[str, Any]] = []
    seen: set[str] = set()
    today = korea_today()
    for parsed in parsed_rows:
        row_number = int(parsed["row_number"])
        source = dict(parsed["values"])
        issues: list[str] = []
        redacted = False
        record: dict[str, Any]
        if import_type == "demand_observations":
            safe_note, redacted = redact_pii(source["note"])
            source_type = _SOURCE_TYPES.get(source["source_type"].casefold())
            record = {
                "village_code": source["village_code"],
                "date": source["date"],
                "service_type": source["service_type"],
                "source_type": source_type or source["source_type"],
                "note": safe_note,
            }
        elif import_type == "provider_availability":
            safe_provider_id, provider_id_redacted = redact_pii(source["provider_id"])
            redacted = provider_id_redacted
            record = {**source, "provider_id": safe_provider_id}
            if provider_id_redacted:
                issues.append("PII_IN_PROVIDER_ID")
        else:
            safe_program_name, name_redacted = redact_pii(source["program_name"])
            redacted = name_redacted
            record = {**source, "program_name": safe_program_name}
            if name_redacted:
                issues.append("PII_REDACTED_REVIEW")

        if import_type == "demand_observations":
            field_limits = {
                "village_code": 10,
                "date": 10,
                "service_type": 80,
                "source_type": 40,
                "note": 3000,
            }
        elif import_type == "provider_availability":
            field_limits = {
                "provider_id": 120,
                "date": 10,
                "start_time": 5,
                "end_time": 5,
                "service_type": 80,
            }
        else:
            field_limits = {
                "village_code": 10,
                "service_type": 80,
                "program_name": 120,
                "monthly_rounds": 3,
                "as_of_date": 10,
            }
        for field, maximum in field_limits.items():
            if len(source[field]) > maximum:
                issues.append("FIELD_TOO_LONG")
                record[field] = record.get(field, source[field])[:maximum]

        if bool(parsed["column_count_mismatch"]):
            issues.append("COLUMN_COUNT_MISMATCH")
        if not any(source.values()):
            issues.append("EMPTY_ROW")

        date_field = "as_of_date" if import_type == "existing_service_history" else "date"
        date_value: date | None = None
        try:
            date_value = date.fromisoformat(source[date_field])
            if date_value.isoformat() != source[date_field]:
                raise ValueError
        except ValueError:
            issues.append("INVALID_DATE_FORMAT")

        service_type = source["service_type"]
        policy_status = service_policy.get(service_type)
        if policy_status is None:
            issues.append("UNKNOWN_SERVICE_CODE")
        elif policy_status != "ALLOWED":
            issues.append("SERVICE_NOT_ALLOWED")

        if import_type == "demand_observations":
            village_code = source["village_code"]
            if len(village_code) != 10 or not village_code.isascii() or not village_code.isdigit():
                issues.append("INVALID_LEGAL_CODE_FORMAT")
            elif village_code not in area_by_code:
                issues.append("LEGAL_CODE_OUTSIDE_ENABLED_PILOTS")
            if source_type is None:
                issues.append("UNKNOWN_SOURCE_TYPE")
            if date_value is not None and date_value > today:
                issues.append("FUTURE_OBSERVATION_DATE")
            if redacted:
                issues.append("PII_REDACTED_REVIEW")
            if not safe_note:
                issues.append("NOTE_REQUIRED")
        elif import_type == "provider_availability":
            provider_id = source["provider_id"]
            services = provider_services.get(provider_id)
            if services is None:
                issues.append("UNKNOWN_PROVIDER_ID")
            elif policy_status == "ALLOWED" and service_type not in services:
                issues.append("PROVIDER_SERVICE_UNSUPPORTED")
            if date_value is not None and date_value < today:
                issues.append("PAST_AVAILABILITY_DATE")
            for field in ("start_time", "end_time"):
                try:
                    if datetime.strptime(source[field], "%H:%M").strftime("%H:%M") != source[field]:
                        raise ValueError
                except ValueError:
                    issues.append(f"INVALID_{field.upper()}")
            if not any(issue.startswith("INVALID_") for issue in issues):
                if source["start_time"] >= source["end_time"]:
                    issues.append("TIME_RANGE_MUST_BE_POSITIVE")
        else:
            village_code = source["village_code"]
            if len(village_code) != 10 or not village_code.isascii() or not village_code.isdigit():
                issues.append("INVALID_LEGAL_CODE_FORMAT")
            elif village_code not in area_by_code:
                issues.append("LEGAL_CODE_OUTSIDE_ENABLED_PILOTS")
            if not source["program_name"]:
                issues.append("PROGRAM_NAME_REQUIRED")
            if not source["monthly_rounds"].isascii() or not source["monthly_rounds"].isdigit():
                issues.append("INVALID_MONTHLY_ROUNDS")
            elif int(source["monthly_rounds"]) > 31:
                issues.append("MONTHLY_ROUNDS_OUT_OF_RANGE")
            if date_value is not None and date_value > today:
                issues.append("FUTURE_SERVICE_HISTORY_DATE")
            if date_value is not None and (today - date_value).days > 180:
                issues.append("STALE_EXISTING_SERVICE_SNAPSHOT")
            if redacted:
                issues.append("PII_REDACTED_REVIEW")

        signature = json.dumps(record, ensure_ascii=False, sort_keys=True)
        if signature in seen:
            issues.append("DUPLICATE_ROW_IN_FILE")
        seen.add(signature)

        reviewable_issues = {"PII_REDACTED_REVIEW", "NOTE_REQUIRED"}
        if import_type == "existing_service_history":
            reviewable_issues.add("STALE_EXISTING_SERVICE_SNAPSHOT")
        hard_failures = [issue for issue in issues if issue not in reviewable_issues]
        if hard_failures:
            status = "FAILED"
        elif issues:
            status = "NEEDS_REVIEW"
        else:
            status = "IMPORTED"
        prepared.append(
            {
                "row_number": row_number,
                "status": status,
                "record": record,
                "issues": issues,
                "redacted": redacted,
            }
        )
    return prepared
