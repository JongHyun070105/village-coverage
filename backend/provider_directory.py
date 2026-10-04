"""License-first provider directory: real existence is separate from simulated operations.

A directory entry only says an organization appears in a public registry. Availability,
capacity and price are never taken from a directory and stay SIMULATED until a provider
reports them.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any

from backend import errors
from backend.errors import AppError
from backend.source_registry import source_map

SOURCE_STATUSES = ("DISCOVERED", "LICENSE_VERIFIED", "INGEST_ALLOWED", "INGEST_BLOCKED")
ALLOWED_FIELDS = ("name", "service_hint", "region_id", "reference_date")
PII_FIELDS = (
    "phone", "tel", "representative", "ceo", "manager_name", "address", "email", "contact",
    "대표자", "전화번호", "주소", "연락처",
)
CANDIDATE_MARKER = "공급 후보"
BADGE_NOTE = "디렉터리 등재는 실존 확인일 뿐 운영 여부·가용성·수용량·가격이 아닙니다."


def source_lifecycle(source_id: str) -> dict[str, Any]:
    source = source_map().get(source_id)
    if source is None:
        return {
            "source_id": source_id,
            "status": "DISCOVERED",
            "reason": "미등록 출처입니다. 이용허락 확인 전에는 수집하지 않습니다.",
        }
    if source.license_status == "UNCLEAR" or not source.reuse_allowed:
        return {
            "source_id": source_id,
            "status": "INGEST_BLOCKED",
            "reason": "이용허락이 불분명하거나 재사용이 허용되지 않아 수집을 차단합니다.",
        }
    if CANDIDATE_MARKER in source.name_ko:
        return {
            "source_id": source_id,
            "status": "INGEST_ALLOWED",
            "reason": "이용허락 확인됨. 존재 여부 후보로만 수집하며 개인정보 필드는 버립니다.",
        }
    return {
        "source_id": source_id,
        "status": "LICENSE_VERIFIED",
        "reason": "이용허락은 확인됐으나 공급 후보 출처가 아니므로 디렉터리로 수집하지 않습니다.",
    }


def directory_source_report() -> list[dict[str, Any]]:
    return [
        {**source_lifecycle(source.source_id), "name_ko": source.name_ko,
         "license_status": source.license_status}
        for source in source_map().values()
        if source.role == "PUBLIC_DATA" and CANDIDATE_MARKER in source.name_ko
    ]


def _entry_id(source_id: str, name: str, region_id: str) -> str:
    digest = sha256(f"{source_id}|{region_id}|{name}".encode()).hexdigest()[:16]
    return f"dir-{digest}"


def ingest_rows(
    connection: sqlite3.Connection, source_id: str, rows: list[dict[str, Any]]
) -> dict[str, Any]:
    lifecycle = source_lifecycle(source_id)
    if lifecycle["status"] != "INGEST_ALLOWED":
        raise AppError(
            errors.VALIDATION_ERROR,
            "이용허락이 확인되지 않은 출처는 수집할 수 없습니다.",
            status_code=422,
            details={"source_id": source_id, "status": lifecycle["status"]},
        )
    now = datetime.now(UTC).isoformat()
    inserted = 0
    skipped = 0
    dropped_pii_fields = 0
    for row in rows:
        dropped_pii_fields += sum(1 for key in row if key in PII_FIELDS)
        name = str(row.get("name") or "").strip()
        if not name:
            skipped += 1
            continue
        region_id = str(row.get("region_id") or "")
        cursor = connection.execute(
            """INSERT OR IGNORE INTO provider_directory_entries(
                 entry_id, source_id, name, service_hint, region_id, existence_provenance,
                 reference_date, created_at)
               VALUES (?, ?, ?, ?, ?, 'REAL_DIRECTORY', ?, ?)""",
            (
                _entry_id(source_id, name, region_id), source_id, name[:120],
                (str(row["service_hint"])[:80] if row.get("service_hint") else None),
                region_id,
                (str(row["reference_date"]) if row.get("reference_date") else None),
                now,
            ),
        )
        if cursor.rowcount:
            inserted += 1
        else:
            skipped += 1
    connection.commit()
    return {
        "source_id": source_id,
        "inserted": inserted,
        "skipped": skipped,
        "dropped_pii_fields": dropped_pii_fields,
        "provenance": "REAL_DIRECTORY",
        "note": BADGE_NOTE,
    }


def link_entry(connection: sqlite3.Connection, entry_id: str, provider_id: str) -> bool:
    cursor = connection.execute(
        "UPDATE provider_directory_entries SET linked_provider_id=? WHERE entry_id=?",
        (provider_id, entry_id),
    )
    connection.commit()
    return cursor.rowcount > 0


def provider_badges(connection: sqlite3.Connection, provider_id: str) -> dict[str, str]:
    linked = connection.execute(
        "SELECT 1 FROM provider_directory_entries WHERE linked_provider_id=? "
        "AND existence_provenance='REAL_DIRECTORY'",
        (provider_id,),
    ).fetchone()
    return {
        "existence": "REAL_DIRECTORY" if linked else "SIMULATED",
        "availability": "SIMULATED",
        "capacity": "SIMULATED",
        "price": "SIMULATED",
    }


def list_entries(
    connection: sqlite3.Connection, region_id: str | None = None
) -> list[dict[str, Any]]:
    query = (
        "SELECT entry_id, source_id, name, service_hint, region_id, existence_provenance, "
        "reference_date, linked_provider_id FROM provider_directory_entries"
    )
    params: tuple[str, ...] = ()
    if region_id:
        query += " WHERE region_id=?"
        params = (region_id,)
    return [dict(row) for row in connection.execute(query + " ORDER BY entry_id", params)]
