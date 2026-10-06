"""Staged, auditable pilot CSV intake contracts and validation."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import re
import sqlite3
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any
from uuid import uuid4

from backend.demand import redact_pii

SOURCE_TYPES = frozenset(
    {
        "PUBLIC_DATA",
        "OFFICIAL_DIRECTORY",
        "LOCAL_AUTHORITY_INPUT",
        "SURVEY_INPUT",
        "PROVIDER_SELF_REPORTED",
        "SERVICE_EXECUTION_LOG",
        "RESIDENT_FEEDBACK",
        "SIMULATED",
    }
)
SERVICE_TYPES = frozenset({"laundry", "daily_necessities", "home_repair"})
MAX_PILOT_CSV_BYTES = 10 * 1024 * 1024
MAX_PILOT_CSV_ROWS = 10_000
MAX_FIELD_LENGTH = 10_000
STALE_SURVEY_DAYS = 180


@dataclass(frozen=True, slots=True)
class FieldRule:
    kind: str
    required: bool
    example: str
    description: str
    pii_risk: str = "낮음"
    provenance: str = "행 단위 source_type을 따릅니다."


def _f(
    kind: str,
    example: str,
    description: str,
    *,
    required: bool = True,
    pii_risk: str = "낮음",
    provenance: str = "행 단위 source_type을 따릅니다.",
) -> FieldRule:
    return FieldRule(kind, required, example, description, pii_risk, provenance)


PILOT_TEMPLATES: dict[str, dict[str, FieldRule]] = {
    "region_areas": {
        "area_code": _f("area_code", "4480031021", "10자리 법정동 코드"),
        "area_name": _f("string", "장곡면 오서리", "마을 또는 서비스 권역 이름"),
        "latitude": _f("decimal", "36.5123", "대표 좌표 위도"),
        "longitude": _f("decimal", "126.6123", "대표 좌표 경도"),
        "population_total": _f("integer", "420", "기준 인구"),
        "population_65_plus": _f("integer", "160", "65세 이상 인구"),
        "households_total": _f("integer", "210", "기준 가구 수"),
        "source_date": _f("date", "2026-09-30", "자료 기준일"),
        "source_type": _f("source_type", "PUBLIC_DATA", "자료의 근거 유형"),
    },
    "demand_observations": {
        "region_code": _f("string", "홍성군", "지자체 또는 pilot 권역 식별자"),
        "area_code": _f("area_code", "4480031021", "10자리 법정동 코드"),
        "observed_date": _f("date", "2026-09-30", "관측일"),
        "service_type": _f("service_type", "laundry", "서비스 코드"),
        "observed_count": _f(
            "integer", "4", "관측한 요청 또는 필요 건수; 행 수와 수요를 혼동하지 않도록 정의 필요"
        ),
        "observation_kind": _f("string", "전화 조사", "관측 방식 또는 사건 유형"),
        "note": _f(
            "string",
            "세탁 지원 요청 4건",
            "최소한의 비식별 근거 메모",
            pii_risk="높음; 전화번호·이름·주소·민감정보 입력 금지",
        ),
        "source_type": _f("source_type", "SURVEY_INPUT", "자료의 근거 유형"),
    },
    "surveys": {
        "region_code": _f("string", "홍성군", "지자체 또는 pilot 권역 식별자"),
        "area_code": _f("area_code", "4480031021", "10자리 법정동 코드"),
        "survey_date": _f("date", "2026-09-30", "조사일"),
        "service_type": _f("service_type", "laundry", "서비스 코드"),
        "survey_count": _f("integer", "12", "유효 응답 수; 개인 수요로 자동 환산하지 않음"),
        "eligible_population": _f("integer", "30", "조사 대상 모집단 수"),
        "source_type": _f("source_type", "SURVEY_INPUT", "자료의 근거 유형"),
        "note": _f(
            "string",
            "마을회관 대면 조사",
            "조사 방법 메모",
            required=False,
            pii_risk="높음; 개인 식별 정보 입력 금지",
        ),
    },
    "provider_organizations": {
        "provider_org_id": _f("string", "SE-00042", "업무상 내부 식별자"),
        "official_name": _f(
            "string", "홍성돌봄협동조합", "공식 조직명; 대표자 이름은 입력하지 않음"
        ),
        "organization_type": _f("string", "사회적기업", "공식 directory의 조직 유형"),
        "region_code": _f("string", "홍성군", "등록 주소 기준 지자체 코드 또는 명칭"),
        "public_business_address": _f(
            "string",
            "충남 홍성군 ...",
            "공개된 사업장 주소만 입력",
            required=False,
            pii_risk="중간; 개인 주거 주소 금지",
        ),
        "public_contact_available": _f(
            "boolean", "true", "공식 공개 연락처가 존재하는지 여부만 기록; 연락처 값은 넣지 않음"
        ),
        "source_id": _f("string", "DATA_GO_KR_15090110", "공식 source registry 식별자"),
        "source_record_id": _f(
            "string", "row-000042", "원본에서 해당 조직을 찾는 공개 레코드 식별자"
        ),
        "source_snapshot": _f("date", "2025-06-30", "디렉터리 기준일"),
        "provenance": _f("provenance", "REAL_DIRECTORY", "조직 존재 근거; 운영 검증 상태가 아님"),
        "source_type": _f("source_type", "OFFICIAL_DIRECTORY", "자료의 근거 유형"),
    },
    "provider_services": {
        "provider_org_id": _f("string", "SE-00042", "provider_organizations의 내부 식별자"),
        "service_description": _f(
            "string", "주거환경개선", "원문 서비스 설명", pii_risk="중간; 개인정보 포함 여부 확인"
        ),
        "service_type": _f(
            "service_type",
            "home_repair",
            "VillageCoverage 후보 서비스 코드; 불명확하면 빈 값",
            required=False,
        ),
        "mapping_status": _f(
            "mapping_status",
            "MAPPING_SUGGESTED",
            "UNMAPPED/MAPPING_SUGGESTED/VERIFIED_MAPPING/REJECTED_MAPPING",
        ),
        "regulation_level": _f(
            "regulation_level", "LIMITED", "UNREGULATED/LIMITED/LICENSE_REQUIRED/EXCLUDED"
        ),
        "source_type": _f("source_type", "PROVIDER_SELF_REPORTED", "자료의 근거 유형"),
    },
    "provider_availability": {
        "provider_org_id": _f("string", "SE-00042", "provider_organizations의 내부 식별자"),
        "service_type": _f("service_type", "laundry", "서비스 코드"),
        "available_date": _f("date", "2026-10-15", "가용 여부 기준일"),
        "available": _f("boolean", "true", "공급자가 보고한 해당 일자 가용 여부"),
        "start_time": _f("time", "09:00", "시작 시간", required=False),
        "end_time": _f("time", "12:00", "종료 시간", required=False),
        "source_type": _f("source_type", "PROVIDER_SELF_REPORTED", "자료의 근거 유형"),
    },
    "provider_capacity": {
        "provider_org_id": _f("string", "SE-00042", "provider_organizations의 내부 식별자"),
        "service_type": _f("service_type", "laundry", "서비스 코드"),
        "period_start": _f("date", "2026-10-01", "수용량 기간 시작일"),
        "period_end": _f("date", "2026-10-31", "수용량 기간 종료일"),
        "capacity_count": _f("integer", "20", "해당 기간 내 보고 수용량; 0도 유효한 사실"),
        "capacity_unit": _f("string", "회", "수용량 단위"),
        "source_type": _f("source_type", "PROVIDER_SELF_REPORTED", "자료의 근거 유형"),
    },
    "provider_prices": {
        "provider_org_id": _f("string", "SE-00042", "provider_organizations의 내부 식별자"),
        "service_type": _f("service_type", "laundry", "서비스 코드"),
        "effective_date": _f("date", "2026-10-01", "가격 기준일"),
        "price_won": _f(
            "integer", "25000", "원화 단가; 미확인 시 비워 경고로 남김", required=False
        ),
        "price_basis": _f("string", "방문 1회", "단가 산정 기준", required=False),
        "source_type": _f("source_type", "PROVIDER_SELF_REPORTED", "자료의 근거 유형"),
    },
    "service_execution_logs": {
        "plan_id": _f("string", "plan-2026-10-01", "실행 대상 계획 식별자"),
        "plan_version": _f("integer", "2", "실행 대상 계획 버전", required=False),
        "round_id": _f("string", "round-001", "계획 회차 식별자", required=False),
        "provider_org_id": _f("string", "SE-00042", "실행 공급자 식별자"),
        "region_code": _f("string", "홍성군", "지자체 또는 pilot 권역"),
        "area_code": _f("area_code", "4480031021", "10자리 법정동 코드"),
        "service_type": _f("service_type", "laundry", "서비스 코드"),
        "scheduled_date": _f("date", "2026-10-15", "계획된 수행일"),
        "actual_date": _f("date", "2026-10-15", "실제 수행일; 미수행이면 빈 값", required=False),
        "executed_date": _f("date", "2026-10-15", "실제 수행일; 미수행이면 빈 값", required=False),
        "execution_status": _f(
            "execution_status",
            "COMPLETED",
            "COMPLETED/PARTIALLY_COMPLETED/CANCELLED/NO_SHOW/PROVIDER_CANCELLED/RESCHEDULED",
        ),
        "rounds": _f("integer", "1", "실제 수행 회차"),
        "actual_duration_minutes": _f("integer", "55", "실제 수행 시간(분)", required=False),
        "actual_cost_won": _f("integer", "28000", "실제 비용(원)", required=False),
        "completion_percent": _f("integer", "100", "완료율(0~100)", required=False),
        "cancel_reason": _f(
            "string",
            "공급자 일정 변경",
            "취소·미수행 사유; 연락처·상세 주소 입력 금지",
            required=False,
            pii_risk="높음; 개인 식별 정보 입력 금지",
        ),
        "source_type": _f("source_type", "SERVICE_EXECUTION_LOG", "자료의 근거 유형"),
    },
    "provider_participation": {
        "provider_org_id": _f("string", "SE-00042", "provider_organizations의 내부 식별자"),
        "plan_id": _f("string", "plan-2026-10-01", "참여 의사를 확인한 계획"),
        "service_type": _f("service_type", "laundry", "서비스 코드"),
        "participation_status": _f(
            "participation_status", "DECLINED", "INVITED/OPTED_IN/DECLINED/UNAVAILABLE"
        ),
        "recorded_at": _f("date", "2026-10-02", "참여 확인일"),
        "source_type": _f("source_type", "PROVIDER_SELF_REPORTED", "자료의 근거 유형"),
    },
}


def template_manifest() -> dict[str, Any]:
    return {
        template_type: {
            "filename": f"{template_type}.csv",
            "fields": {
                name: {
                    "type": rule.kind,
                    "required": rule.required,
                    "example": rule.example,
                    "description": rule.description,
                    "pii_risk": rule.pii_risk,
                    "provenance_interpretation": rule.provenance,
                }
                for name, rule in fields.items()
            },
        }
        for template_type, fields in PILOT_TEMPLATES.items()
    }


def _parse_csv(payload: bytes, template_type: str) -> list[dict[str, Any]]:
    if template_type not in PILOT_TEMPLATES:
        raise ValueError("지원하지 않는 파일럿 CSV 양식입니다.")
    if not payload or len(payload) > MAX_PILOT_CSV_BYTES:
        raise ValueError("CSV 파일은 비어 있지 않고 10MB 이하여야 합니다.")
    decoded = None
    for encoding in ("utf-8-sig", "cp949"):
        try:
            decoded = payload.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if decoded is None:
        raise ValueError("UTF-8 또는 CP949 인코딩 CSV만 지원합니다.")
    try:
        reader = csv.reader(io.StringIO(decoded, newline=""), strict=True)
        headers = next(reader, None)
        allowed_headers = set(PILOT_TEMPLATES[template_type])
        required_headers = [
            name for name, rule in PILOT_TEMPLATES[template_type].items() if rule.required
        ]
        if not headers or any(not item.strip() for item in headers):
            raise ValueError("CSV 첫 행에 비어 있지 않은 열 이름이 필요합니다.")
        headers = [item.strip().lstrip("\ufeff") for item in headers]
        if len(headers) != len(set(headers)):
            raise ValueError("CSV 열 이름이 중복되었습니다.")
        missing = [name for name in required_headers if name not in headers]
        extra = [name for name in headers if name not in allowed_headers]
        if missing or extra:
            raise ValueError(
                "열 구성이 양식과 다릅니다. "
                + (f"누락: {', '.join(missing)}. " if missing else "")
                + (f"지원하지 않는 열: {', '.join(extra)}." if extra else "")
            )
        result = []
        for row_number, values in enumerate(reader, start=2):
            if row_number - 1 > MAX_PILOT_CSV_ROWS:
                raise ValueError("한 번에 10,000행까지만 처리할 수 있습니다.")
            data = {
                header: values[index].strip() if index < len(values) else ""
                for index, header in enumerate(headers)
            }
            if len(values) > len(headers):
                data["extra_columns"] = json.dumps(values[len(headers) :], ensure_ascii=False)
            result.append(
                {
                    "row_number": row_number,
                    "values": data,
                    "column_count_mismatch": len(values) != len(headers),
                }
            )
    except csv.Error as exc:
        raise ValueError("CSV 문법 오류로 파일을 읽을 수 없습니다.") from exc
    if not result:
        raise ValueError("가져올 행이 없습니다.")
    return result


def _known_area_codes(connection: sqlite3.Connection, context_id: str | None = None) -> set[str]:
    if context_id:
        codes: set[str] = set()
        for row in connection.execute(
            """SELECT payload_json FROM pilot_promoted_records
               WHERE context_id=? AND template_type='region_areas'""",
            (context_id,),
        ):
            try:
                record = json.loads(row[0])
                codes.add(str(record.get("area_code", "")))
            except (TypeError, json.JSONDecodeError):
                continue
        return codes
    codes = {
        str(row[0]) for row in connection.execute("SELECT legal_code FROM village_service_areas")
    }
    for row in connection.execute(
        """SELECT normalized_json FROM pilot_import_records
           WHERE template_type='region_areas'"""
    ):
        try:
            record = json.loads(row[0])
            codes.add(str(record.get("area_code", "")))
        except (TypeError, json.JSONDecodeError):
            continue
    return codes


def _validate_rows(
    connection: sqlite3.Connection,
    template_type: str,
    parsed_rows: list[dict[str, Any]],
    context_id: str | None = None,
) -> list[dict[str, Any]]:
    schema = PILOT_TEMPLATES[template_type]
    known_codes = _known_area_codes(connection, context_id)
    seen: set[str] = set()
    prepared: list[dict[str, Any]] = []
    today = date.today()
    for parsed in parsed_rows:
        record = dict(parsed["values"])
        issues: list[dict[str, str]] = []

        def issue(
            code: str,
            severity: str,
            detail: str,
            row_issues: list[dict[str, str]] = issues,
        ) -> None:
            row_issues.append({"code": code, "severity": severity, "detail": detail})

        if parsed["column_count_mismatch"]:
            issue("COLUMN_COUNT_MISMATCH", "ERROR", "열 개수가 양식의 헤더와 다릅니다.")
        for name, rule in schema.items():
            value = str(record.get(name, "")).strip()
            if not value:
                if rule.required:
                    issue("REQUIRED_FIELD", "ERROR", f"{name} 값이 필요합니다.")
                elif template_type == "provider_prices" and name == "price_won":
                    issue(
                        "PRICE_MISSING",
                        "WARNING",
                        "공급 가격이 비어 있어 비용 계산에는 사용할 수 없습니다.",
                    )
                continue
            if len(value) > MAX_FIELD_LENGTH:
                issue("FIELD_TOO_LONG", "ERROR", f"{name} 값이 허용 길이를 넘습니다.")
                record[name] = value[:MAX_FIELD_LENGTH]
                value = record[name]
            if name in {"note", "public_business_address", "service_description", "cancel_reason"}:
                safe, was_redacted = redact_pii(value)
                record[name] = safe
                if was_redacted:
                    issue(
                        "PII_REDACTED",
                        "WARNING",
                        f"{name}에서 연락처 또는 개인 식별 패턴을 가렸습니다.",
                    )
            if rule.kind == "source_type" and value not in SOURCE_TYPES:
                issue("UNKNOWN_SOURCE_TYPE", "ERROR", "허용된 자료 출처 코드가 아닙니다.")
            elif rule.kind == "service_type" and value not in SERVICE_TYPES:
                issue(
                    "UNKNOWN_SERVICE_TYPE",
                    "ERROR",
                    "지원되는 서비스 코드가 아닙니다. 해당 행은 가져오지 않습니다.",
                )
            elif rule.kind in {"date", "area_code"}:
                try:
                    if rule.kind == "date":
                        parsed_date = date.fromisoformat(value)
                        if parsed_date.isoformat() != value:
                            raise ValueError
                        if name == "survey_date" and (today - parsed_date).days > STALE_SURVEY_DAYS:
                            issue(
                                "OBSERVATION_STALE",
                                "WARNING",
                                "조사 기준일이 180일보다 오래되었습니다.",
                            )
                    elif not re.fullmatch(r"\d{10}", value):
                        raise ValueError
                    elif value not in known_codes and template_type != "region_areas":
                        issue(
                            "UNKNOWN_REGION_CODE",
                            "ERROR",
                            "먼저 해당 법정동을 region_areas 양식으로 등록해야 합니다.",
                        )
                except ValueError:
                    issue("INVALID_DATE_OR_AREA_CODE", "ERROR", f"{name} 형식이 올바르지 않습니다.")
            elif rule.kind in {"integer", "decimal"}:
                try:
                    numeric = float(value) if rule.kind == "decimal" else int(value)
                    if isinstance(numeric, float) and not math.isfinite(numeric):
                        issue("INVALID_NUMBER", "ERROR", f"{name}은 유한한 숫자여야 합니다.")
                    elif numeric < 0 and name not in {"latitude", "longitude"}:
                        issue("NEGATIVE_VALUE", "ERROR", f"{name}은 음수일 수 없습니다.")
                    elif (
                        template_type == "provider_prices" and name == "price_won" and numeric == 0
                    ):
                        issue(
                            "ZERO_PRICE_NOT_ALLOWED",
                            "ERROR",
                            "확인되지 않은 가격을 0원으로 기록할 수 없습니다.",
                        )
                    elif rule.kind == "decimal" and name == "latitude" and not -90 <= numeric <= 90:
                        issue("COORDINATE_OUT_OF_RANGE", "ERROR", "위도 범위는 -90에서 90입니다.")
                    elif (
                        rule.kind == "decimal"
                        and name == "longitude"
                        and not -180 <= numeric <= 180
                    ):
                        issue("COORDINATE_OUT_OF_RANGE", "ERROR", "경도 범위는 -180에서 180입니다.")
                except ValueError:
                    issue(
                        "INVALID_NUMBER", "ERROR", f"{name}은 유효한 {rule.kind} 값이어야 합니다."
                    )
            elif rule.kind == "boolean" and value.casefold() not in {
                "true",
                "false",
                "1",
                "0",
                "yes",
                "no",
            }:
                issue("INVALID_BOOLEAN", "ERROR", f"{name}은 true 또는 false여야 합니다.")
            elif rule.kind == "time" and not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
                issue("INVALID_TIME", "ERROR", f"{name}은 HH:MM 형식이어야 합니다.")
            elif rule.kind == "provenance" and value not in {
                "REAL_DIRECTORY",
                "SELF_REPORTED",
                "LOCAL_AUTHORITY_VERIFIED",
                "SIMULATED",
                "UNKNOWN",
            }:
                issue("UNKNOWN_PROVENANCE", "ERROR", "허용된 provenance 코드가 아닙니다.")
        if template_type == "provider_services":
            if record.get("mapping_status") not in {
                "UNMAPPED",
                "MAPPING_SUGGESTED",
                "VERIFIED_MAPPING",
                "REJECTED_MAPPING",
            }:
                issue(
                    "INVALID_MAPPING_STATUS", "ERROR", "서비스 매핑 상태 코드가 올바르지 않습니다."
                )
            if record.get("regulation_level") not in {
                "UNREGULATED",
                "LIMITED",
                "LICENSE_REQUIRED",
                "EXCLUDED",
            }:
                issue("INVALID_REGULATION_LEVEL", "ERROR", "규제 수준 코드가 올바르지 않습니다.")
            if record.get("mapping_status") in {"VERIFIED_MAPPING", "REJECTED_MAPPING"}:
                issue(
                    "MAPPING_REQUIRES_REVIEW",
                    "ERROR",
                    "CSV import로 서비스 mapping을 확정하거나 거부할 수 없습니다. "
                    "담당자 검토 API를 사용해야 합니다.",
                )
        if template_type == "provider_organizations":
            provenance = record.get("provenance")
            row_source = record.get("source_type")
            compatible = {
                "REAL_DIRECTORY": {"OFFICIAL_DIRECTORY", "PUBLIC_DATA"},
                "SELF_REPORTED": {"PROVIDER_SELF_REPORTED"},
                "LOCAL_AUTHORITY_VERIFIED": {"LOCAL_AUTHORITY_INPUT"},
                "SIMULATED": {"SIMULATED"},
                "UNKNOWN": SOURCE_TYPES,
            }
            if provenance not in compatible or row_source not in compatible[provenance]:
                issue(
                    "PROVENANCE_SOURCE_MISMATCH",
                    "ERROR",
                    "organization provenance와 source_type이 서로 맞지 않습니다.",
                )
        if template_type == "service_execution_logs" and record.get("execution_status") not in {
            "COMPLETED",
            "PARTIALLY_COMPLETED",
            "CANCELLED",
            "NO_SHOW",
            "PROVIDER_CANCELLED",
            "RESCHEDULED",
        }:
            issue("INVALID_EXECUTION_STATUS", "ERROR", "수행 결과 상태 코드가 올바르지 않습니다.")
        if template_type == "service_execution_logs":
            try:
                if (
                    record.get("completion_percent")
                    and not 0 <= int(record["completion_percent"]) <= 100
                ):
                    issue(
                        "INVALID_COMPLETION_PERCENT", "ERROR", "완료율은 0에서 100 사이여야 합니다."
                    )
            except ValueError:
                issue("INVALID_COMPLETION_PERCENT", "ERROR", "완료율은 정수여야 합니다.")
        if template_type == "provider_availability":
            start, end = record.get("start_time", ""), record.get("end_time", "")
            if start and end and start >= end:
                issue("INVALID_TIME_RANGE", "ERROR", "종료 시간은 시작 시간보다 늦어야 합니다.")
        if template_type == "provider_capacity" and record.get("period_start", "") > record.get(
            "period_end", ""
        ):
            issue("INVALID_PERIOD", "ERROR", "수용량 기간의 종료일은 시작일보다 빠를 수 없습니다.")
        if template_type == "provider_participation" and record.get("participation_status") not in {
            "INVITED",
            "OPTED_IN",
            "DECLINED",
            "UNAVAILABLE",
        }:
            issue("INVALID_PARTICIPATION_STATUS", "ERROR", "참여 상태 코드가 올바르지 않습니다.")
        signature = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        fingerprint = hashlib.sha256(f"{template_type}\0{signature}".encode()).hexdigest()
        if fingerprint in seen:
            issue("DUPLICATE_ROW_IN_FILE", "WARNING", "파일 안에 같은 내용의 행이 반복됩니다.")
        seen.add(fingerprint)
        severity = (
            "ERROR"
            if any(item["severity"] == "ERROR" for item in issues)
            else "WARNING"
            if issues
            else "VALID"
        )
        prepared.append(
            {
                "row_number": int(parsed["row_number"]),
                "row_fingerprint": fingerprint,
                "status": severity,
                "record": record,
                "issues": issues,
            }
        )
    return prepared


def _batch_dict(connection: sqlite3.Connection, batch_id: str) -> dict[str, Any] | None:
    row = connection.execute(
        "SELECT * FROM pilot_import_batches WHERE batch_id=?", (batch_id,)
    ).fetchone()
    if row is None:
        return None
    result = dict(row)
    result["rows"] = []
    for item in connection.execute(
        "SELECT * FROM pilot_import_rows WHERE batch_id=? ORDER BY row_number", (batch_id,)
    ):
        record = dict(item)
        record["normalized_record"] = json.loads(record.pop("normalized_json"))
        record["issues"] = json.loads(record.pop("issues_json"))
        result["rows"].append(record)
    return result


def create_preview(
    connection: sqlite3.Connection,
    *,
    template_type: str,
    file_name: str,
    payload: bytes,
    source_type: str,
    snapshot_id: str | None = None,
    context_id: str | None = None,
) -> tuple[dict[str, Any], bool]:
    if source_type not in SOURCE_TYPES:
        raise ValueError("허용된 source_type이 아닙니다.")
    if (
        context_id
        and connection.execute(
            "SELECT 1 FROM pilot_contexts WHERE context_id=?", (context_id,)
        ).fetchone()
        is None
    ):
        raise ValueError("파일럿 데이터셋을 찾을 수 없습니다.")
    digest = hashlib.sha256(payload).hexdigest()
    previous = connection.execute(
        "SELECT batch_id FROM pilot_import_batches WHERE template_type=? AND content_sha256=?",
        (template_type, digest),
    ).fetchone()
    if previous:
        batch = _batch_dict(connection, str(previous[0]))
        assert batch is not None
        if context_id:
            connection.execute(
                "INSERT OR IGNORE INTO pilot_context_batches(context_id,batch_id,linked_at) "
                "VALUES (?,?,?)",
                (context_id, str(previous[0]), datetime.now(UTC).isoformat(timespec="seconds")),
            )
        return batch, True
    parsed = _parse_csv(payload, template_type)
    prepared = _validate_rows(connection, template_type, parsed, context_id)
    safe_name = re.sub(r"[^\w.() -]", "_", file_name.rsplit("/", 1)[-1])[:255] or "upload.csv"
    now = datetime.now(UTC).isoformat(timespec="seconds")
    batch_id = str(uuid4())
    counts = {
        status.lower(): sum(row["status"] == status for row in prepared)
        for status in ("VALID", "WARNING", "ERROR")
    }
    row_source_types = {
        str(row["record"].get("source_type"))
        for row in prepared
        if row["record"].get("source_type") in SOURCE_TYPES
    }
    batch_source_type = next(iter(row_source_types)) if len(row_source_types) == 1 else "MIXED"
    connection.execute(
        """INSERT INTO pilot_import_batches(
             batch_id,file_name,content_sha256,template_type,uploaded_at,validated_at,
             rows_total,rows_valid,rows_warning,rows_error,status,source_type,snapshot_id
           ) VALUES (?,?,?,?,?,?,?,?,?,?,'PREVIEWED',?,?)""",
        (
            batch_id,
            safe_name,
            digest,
            template_type,
            now,
            now,
            len(prepared),
            counts["valid"],
            counts["warning"],
            counts["error"],
            batch_source_type,
            snapshot_id,
        ),
    )
    for item in prepared:
        connection.execute(
            """INSERT INTO pilot_import_rows(
                 row_id,batch_id,template_type,row_number,row_fingerprint,status,
                 normalized_json,issues_json
               ) VALUES (?,?,?,?,?,?,?,?)""",
            (
                str(uuid4()),
                batch_id,
                template_type,
                item["row_number"],
                item["row_fingerprint"],
                item["status"],
                json.dumps(item["record"], ensure_ascii=False, sort_keys=True),
                json.dumps(item["issues"], ensure_ascii=False),
            ),
        )
    if context_id:
        connection.execute(
            "INSERT INTO pilot_context_batches(context_id,batch_id,linked_at) VALUES (?,?,?)",
            (context_id, batch_id, now),
        )
    return _batch_dict(connection, batch_id) or {}, False


def confirm_preview(
    connection: sqlite3.Connection, batch_id: str
) -> tuple[dict[str, Any] | None, bool]:
    batch = _batch_dict(connection, batch_id)
    if batch is None:
        return None, False
    if batch["status"] != "PREVIEWED":
        return batch, True
    imported_count = 0
    for row in batch["rows"]:
        if row["status"] == "ERROR":
            continue
        normalized = row["normalized_record"]
        source = str(normalized.get("source_type") or batch["source_type"])
        record_id = str(uuid4())
        connection.execute(
            """INSERT OR IGNORE INTO pilot_import_records(
                 record_id,template_type,row_fingerprint,source_type,provenance,
                 normalized_json,imported_at,batch_id,row_number
               ) VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                record_id,
                batch["template_type"],
                row["row_fingerprint"],
                source,
                source,
                json.dumps(normalized, ensure_ascii=False, sort_keys=True),
                datetime.now(UTC).isoformat(timespec="seconds"),
                batch_id,
                row["row_number"],
            ),
        )
        saved = connection.execute(
            """SELECT record_id FROM pilot_import_records
               WHERE template_type=? AND row_fingerprint=?""",
            (batch["template_type"], row["row_fingerprint"]),
        ).fetchone()
        if saved:
            connection.execute(
                "UPDATE pilot_import_rows SET imported_record_id=? WHERE row_id=?",
                (saved[0], row["row_id"]),
            )
            imported_count += int(saved[0] == record_id)
    final_status = "IMPORTED_WITH_ERRORS" if batch["rows_error"] else "IMPORTED"
    connection.execute(
        """UPDATE pilot_import_batches SET status=?,confirmed_at=?,rows_imported=?
           WHERE batch_id=?""",
        (final_status, datetime.now(UTC).isoformat(timespec="seconds"), imported_count, batch_id),
    )
    return _batch_dict(connection, batch_id), False
