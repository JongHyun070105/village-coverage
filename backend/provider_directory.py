"""License-first provider directory: real existence is separate from simulated operations.

A directory entry only says an organization appears in a public registry. Availability,
capacity and price are never taken from a directory and stay SIMULATED until a provider
reports them.
"""

from __future__ import annotations

import json
import sqlite3
import unicodedata
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from backend import errors
from backend.demand import redact_pii
from backend.errors import AppError
from backend.provider_source_registry import ProviderSourceRegistry
from backend.source_registry import source_map

SOURCE_STATUSES = (
    "DISCOVERED",
    "LICENSE_VERIFIED",
    "INGEST_ALLOWED",
    "INGEST_BLOCKED",
    "INGESTED",
    "SCHEMA_DRIFT",
    "ERROR",
)
ALLOWED_FIELDS = ("name", "service_hint", "region_id", "reference_date", "public_address")
PII_FIELDS = (
    "phone",
    "tel",
    "representative",
    "ceo",
    "manager_name",
    "address",
    "email",
    "contact",
    "대표자",
    "전화번호",
    "주소",
    "연락처",
)
CANDIDATE_MARKER = "공급 후보"
BADGE_NOTE = "디렉터리 등재는 실존 확인일 뿐 운영 여부·가용성·수용량·가격이 아닙니다."
REGISTRY = ProviderSourceRegistry()


class ProviderOrganization(BaseModel):
    """Only public directory facts; missing operating facts stay explicit."""

    model_config = ConfigDict(extra="forbid")

    provider_org_id: str = Field(min_length=1, max_length=120)
    official_name: str = Field(min_length=1, max_length=120)
    source_id: str = Field(min_length=1, max_length=80)
    source_record_id: str = Field(min_length=1, max_length=120)
    organization_type: str = Field(default="UNKNOWN", max_length=80)
    region_label: str = Field(default="", max_length=120)
    region_code: str | None = Field(default=None, max_length=20)
    address: str | None = Field(default=None, max_length=240)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    public_service_description: str | None = Field(default=None, max_length=500)
    public_contact_available: bool = False
    active_status_if_available: str | None = Field(default=None, max_length=80)
    source_snapshot: str
    provenance: Literal["REAL_DIRECTORY", "SELF_REPORTED", "LOCAL_AUTHORITY_VERIFIED"] = (
        "REAL_DIRECTORY"
    )
    availability_status: Literal["UNKNOWN", "SIMULATED"] = "UNKNOWN"
    capacity_status: Literal["UNKNOWN", "SIMULATED"] = "UNKNOWN"
    service_duration_status: Literal["UNKNOWN", "SIMULATED"] = "UNKNOWN"
    price_status: Literal["UNKNOWN", "SIMULATED"] = "UNKNOWN"
    participation_status: Literal["UNKNOWN", "SIMULATED"] = "UNKNOWN"


def normalized_key(value: str | None) -> str:
    normalized = unicodedata.normalize("NFKC", value or "").casefold()
    return "".join(char for char in normalized if char.isalnum())


def service_mapping_candidate(description: str | None) -> dict[str, str | None]:
    """Suggest a supported service; regulated or excluded work stays unmapped."""
    text = unicodedata.normalize("NFKC", description or "").casefold()
    if not text.strip():
        return {"service_type": None, "status": "UNMAPPED", "regulation_level": "EXCLUDED"}
    excluded = ("의료", "진료", "간호", "법률", "변호", "가스공사", "전기공사")
    licensed = ("전기", "가스", "전문건설", "배관", "면허", "자격")
    if any(term in text for term in excluded):
        return {"service_type": None, "status": "UNMAPPED", "regulation_level": "EXCLUDED"}
    if any(term in text for term in licensed):
        return {
            "service_type": None,
            "status": "UNMAPPED",
            "regulation_level": "LICENSE_REQUIRED",
        }
    if any(term in text for term in ("세탁", "빨래", "laundry")):
        service = "laundry"
    elif any(term in text for term in ("장보기", "반찬", "생필품", "생활용품")):
        service = "daily_necessities"
    elif any(term in text for term in ("간단 집수리", "주거환경개선", "주택개선")):
        service = "home_repair"
    else:
        return {"service_type": None, "status": "UNMAPPED", "regulation_level": "EXCLUDED"}
    return {
        "service_type": service,
        "status": "MAPPING_SUGGESTED",
        "regulation_level": "LIMITED" if service == "home_repair" else "UNREGULATED",
    }


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
        {
            **source_lifecycle(source.source_id),
            "name_ko": source.name_ko,
            "license_status": source.license_status,
        }
        for source in source_map().values()
        if source.role == "PUBLIC_DATA" and CANDIDATE_MARKER in source.name_ko
    ]


def registry_source_report(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    sources = REGISTRY.list(connection)
    for source in sources:
        source["status"] = source["ingestion_status"]
        source["schema_drift_detected"] = source["ingestion_status"] == "SCHEMA_DRIFT"
    return sources


def _entry_id(
    source_id: str, name: str, region_id: str, *, snapshot_id: str = "", source_record_id: str = ""
) -> str:
    digest = sha256(
        f"{source_id}|{region_id}|{name}|{snapshot_id}|{source_record_id}".encode()
    ).hexdigest()[:16]
    return f"dir-{digest}"


def _record_mapping(connection: sqlite3.Connection, entry_id: str, description: str) -> str:
    candidate = service_mapping_candidate(description)
    if not description.strip():
        return "UNMAPPED"
    mapping_key = f"{entry_id}|{candidate['service_type']}"
    mapping_id = f"map-{sha256(mapping_key.encode()).hexdigest()[:20]}"
    connection.execute(
        """INSERT OR IGNORE INTO provider_service_mapping_reviews(
             mapping_id, entry_id, source_description, suggested_service_type, status,
             regulation_level, provenance, created_at
           ) VALUES (?, ?, ?, ?, ?, ?, 'REAL_DIRECTORY', ?)""",
        (
            mapping_id,
            entry_id,
            description[:500],
            candidate["service_type"],
            candidate["status"],
            candidate["regulation_level"],
            datetime.now(UTC).isoformat(timespec="seconds"),
        ),
    )
    return str(candidate["status"])


def _record_duplicate_candidates(connection: sqlite3.Connection) -> int:
    rows = connection.execute(
        """SELECT entry_id, normalized_name, public_address FROM provider_directory_entries
           WHERE normalized_name IS NOT NULL AND normalized_name != '' ORDER BY entry_id"""
    ).fetchall()
    found = 0
    for index, left in enumerate(rows):
        left_name = str(left["normalized_name"])
        left_address = normalized_key(str(left["public_address"] or ""))
        for right in rows[index + 1 :]:
            right_name = str(right["normalized_name"])
            right_address = normalized_key(str(right["public_address"] or ""))
            same_name = left_name == right_name
            same_address = bool(left_address and left_address == right_address)
            if not same_name and not (same_address and left_name[:4] == right_name[:4]):
                continue
            signals = []
            if same_name:
                signals.append("NORMALIZED_NAME_MATCH")
            if same_address:
                signals.append("ADDRESS_MATCH")
            pair = sorted((str(left["entry_id"]), str(right["entry_id"])))
            candidate_id = "dup-" + sha256("|".join(pair).encode()).hexdigest()[:20]
            cursor = connection.execute(
                """INSERT OR IGNORE INTO provider_duplicate_candidates(
                     candidate_id, entry_id_a, entry_id_b, match_signals_json, created_at
                   ) VALUES (?, ?, ?, ?, ?)""",
                (
                    candidate_id,
                    pair[0],
                    pair[1],
                    json.dumps(signals),
                    datetime.now(UTC).isoformat(timespec="seconds"),
                ),
            )
            found += int(cursor.rowcount > 0)
    return found


def ingest_directory_snapshot(
    connection: sqlite3.Connection,
    source_id: str,
    *,
    raw_file: bytes,
    source_snapshot_date: str,
    downloaded_at: str,
    schema_fields: list[str],
    expected_schema_fields: list[str],
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Store an immutable, PII-minimized snapshot, then project its organizations.

    The input `rows` must already be mapped to the documented safe field names. Raw
    row payloads are never persisted. A schema mismatch records an explicit state
    and leaves any earlier snapshot untouched.
    """
    source = REGISTRY.get(connection, source_id)
    if source is None or not bool(source["reuse_allowed"]):
        raise AppError(
            errors.VALIDATION_ERROR,
            "재사용 허가가 확인되지 않은 출처는 수집할 수 없습니다.",
            status_code=422,
            details={"source_id": source_id, "status": "INGEST_BLOCKED"},
        )
    raw_hash = sha256(raw_file).hexdigest()
    sorted_fields = sorted(schema_fields)
    schema_hash = sha256(json.dumps(sorted_fields, ensure_ascii=False).encode()).hexdigest()
    if sorted_fields != sorted(expected_schema_fields):
        REGISTRY.mark_result(
            connection,
            source_id,
            status="SCHEMA_DRIFT",
            content_hash=raw_hash,
            error="SCHEMA_DRIFT_DETECTED: source columns differ from reviewed contract",
            downloaded_at=downloaded_at,
        )
        connection.commit()
        return {
            "source_id": source_id,
            "status": "SCHEMA_DRIFT",
            "error_code": "SCHEMA_DRIFT_DETECTED",
            "raw_file_hash": raw_hash,
            "existing_snapshot": (
                dict(row)
                if (
                    row := connection.execute(
                        """SELECT snapshot_id, source_snapshot_date, raw_file_hash
                   FROM provider_directory_snapshots WHERE source_id=?
                   ORDER BY created_at DESC LIMIT 1""",
                        (source_id,),
                    ).fetchone()
                )
                else None
            ),
            "ingested": 0,
        }

    snapshot_id = f"{source_id}:{raw_hash[:16]}"
    existing = connection.execute(
        """SELECT snapshot_id FROM provider_directory_snapshots
           WHERE source_id=? AND raw_file_hash=?""",
        (source_id, raw_hash),
    ).fetchone()
    if existing:
        return {
            "source_id": source_id,
            "snapshot_id": str(existing["snapshot_id"]),
            "raw_file_hash": raw_hash,
            "ingested": 0,
            "skipped": len(rows),
            "idempotent": True,
            "status": "INGESTED",
        }

    normalized_rows: list[dict[str, Any]] = []
    redacted_fields = 0
    for index, row in enumerate(rows, start=1):
        name = str(row.get("name") or "").strip()[:120]
        if not name:
            continue
        address, address_redacted = redact_pii(str(row.get("public_address") or ""))
        description, description_redacted = redact_pii(
            str(row.get("public_service_description") or row.get("service_hint") or "")
        )
        redacted_fields += int(address_redacted) + int(description_redacted)
        region_label = str(row.get("region_label") or "")[:120]
        source_record_id = str(row.get("source_record_id") or f"row-{index:06d}")[:120]
        safe_row = ProviderOrganization(
            provider_org_id=_entry_id(
                source_id,
                name,
                region_label,
                snapshot_id=snapshot_id,
                source_record_id=source_record_id,
            ),
            official_name=name,
            source_id=source_id,
            source_record_id=source_record_id,
            organization_type=str(row.get("organization_type") or "UNKNOWN")[:80],
            region_label=region_label,
            region_code=str(row.get("region_code") or "")[:20] or None,
            address=address[:240] or None,
            latitude=row.get("latitude"),
            longitude=row.get("longitude"),
            public_service_description=description[:500] or None,
            public_contact_available=bool(row.get("public_contact_available", False)),
            active_status_if_available=(
                str(row.get("active_status_if_available") or "")[:80] or None
            ),
            source_snapshot=snapshot_id,
        ).model_dump()
        normalized_rows.append(safe_row)

    snapshot_payload = {
        "source_id": source_id,
        "snapshot_id": snapshot_id,
        "source_snapshot_date": source_snapshot_date,
        "downloaded_at": downloaded_at,
        "schema_version": str(source["schema_version"]),
        "schema_fields": sorted_fields,
        "raw_file_hash": raw_hash,
        "organizations": normalized_rows,
    }
    connection.execute(
        """INSERT INTO provider_directory_snapshots(
             snapshot_id, source_id, raw_file_hash, source_snapshot_date, downloaded_at,
             schema_version, schema_hash, row_count, normalized_snapshot_json, created_at
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            snapshot_id,
            source_id,
            raw_hash,
            source_snapshot_date,
            downloaded_at,
            str(source["schema_version"]),
            schema_hash,
            len(normalized_rows),
            json.dumps(snapshot_payload, ensure_ascii=False, sort_keys=True),
            datetime.now(UTC).isoformat(timespec="seconds"),
        ),
    )
    inserted = 0
    skipped = 0
    for row in normalized_rows:
        name = row["official_name"]
        region_label = row["region_label"]
        entry_id = str(row["provider_org_id"])
        norm_name = normalized_key(name)
        description = row["public_service_description"] or ""
        cursor = connection.execute(
            """INSERT OR IGNORE INTO provider_directory_entries(
                 entry_id, source_id, name, service_hint, region_id, existence_provenance,
                 reference_date, created_at, public_address, source_record_id,
                 region_label, region_code, normalized_name, organization_type,
                 public_service_description,
                 public_contact_available, active_status_if_available, snapshot_id
               ) VALUES (?, ?, ?, ?, '', 'REAL_DIRECTORY', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                entry_id,
                source_id,
                name,
                description[:80] or None,
                source_snapshot_date,
                downloaded_at,
                row["address"],
                row["source_record_id"],
                region_label,
                row["region_code"],
                norm_name,
                row["organization_type"],
                description or None,
                int(row["public_contact_available"]),
                row["active_status_if_available"],
                snapshot_id,
            ),
        )
        if cursor.rowcount:
            inserted += 1
            _record_mapping(connection, entry_id, description)
        else:
            skipped += 1

    duplicate_candidates = _record_duplicate_candidates(connection)
    REGISTRY.mark_result(
        connection,
        source_id,
        status="INGESTED",
        content_hash=raw_hash,
        error=None,
        successful_at=datetime.now(UTC).isoformat(timespec="seconds"),
        downloaded_at=downloaded_at,
    )
    connection.commit()
    mapping_counts = {
        str(row["status"]): int(row["count"])
        for row in connection.execute(
            """SELECT status, COUNT(*) AS count FROM provider_service_mapping_reviews m
               JOIN provider_directory_entries e ON e.entry_id=m.entry_id
               WHERE e.snapshot_id=? GROUP BY status""",
            (snapshot_id,),
        ).fetchall()
    }
    return {
        "source_id": source_id,
        "snapshot_id": snapshot_id,
        "raw_file_hash": raw_hash,
        "source_snapshot_date": source_snapshot_date,
        "downloaded_at": downloaded_at,
        "row_count": len(normalized_rows),
        "ingested": inserted,
        "skipped": skipped,
        "redacted_fields": redacted_fields,
        "duplicate_candidates": duplicate_candidates,
        "mapping_status_counts": mapping_counts,
        "idempotent": False,
        "status": "INGESTED",
        "operational_status": "UNKNOWN",
        "note": BADGE_NOTE,
    }


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
        source_record_id = str(row.get("source_record_id") or "").strip()[:120] or None
        region_label = str(row.get("region_label") or "")[:120]
        region_code = str(row.get("region_code") or "")[:20] or None
        organization_type = str(row.get("organization_type") or "UNKNOWN")[:80]
        public_address, _ = redact_pii(str(row.get("public_address") or ""))
        description, _ = redact_pii(
            str(row.get("public_service_description") or row.get("service_hint") or "")
        )
        cursor = connection.execute(
            """INSERT OR IGNORE INTO provider_directory_entries(
                 entry_id, source_id, name, service_hint, region_id, existence_provenance,
                 reference_date, created_at, public_address, source_record_id,
                 region_label, region_code, normalized_name, organization_type,
                 public_service_description, public_contact_available, active_status_if_available)
               VALUES (?, ?, ?, ?, ?, 'REAL_DIRECTORY', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                _entry_id(source_id, name, region_id, source_record_id=source_record_id or ""),
                source_id,
                name[:120],
                description[:80] or None,
                region_id,
                (str(row["reference_date"]) if row.get("reference_date") else None),
                now,
                public_address[:240] or None,
                source_record_id,
                region_label,
                region_code,
                normalized_key(name),
                organization_type,
                description[:500] or None,
                int(bool(row.get("public_contact_available", False))),
                (str(row.get("active_status_if_available") or "")[:80] or None),
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


def linked_entry(connection: sqlite3.Connection, provider_id: str) -> dict[str, Any] | None:
    row = connection.execute(
        """SELECT entry_id, source_id, name, service_hint, region_id,
                  reference_date, public_address
           FROM provider_directory_entries
           WHERE linked_provider_id=? AND existence_provenance='REAL_DIRECTORY'
           ORDER BY entry_id LIMIT 1""",
        (provider_id,),
    ).fetchone()
    return dict(row) if row else None


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
    connection: sqlite3.Connection,
    region_id: str | None = None,
    *,
    source_id: str | None = None,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    query = (
        "SELECT entry_id, source_id, source_record_id, name, organization_type, service_hint, "
        "public_service_description, region_id, region_label, region_code, normalized_name, "
        "existence_provenance, reference_date, public_address, public_contact_available, "
        "active_status_if_available, snapshot_id, linked_provider_id, "
        "(SELECT m.status FROM provider_service_mapping_reviews m "
        "WHERE m.entry_id=provider_directory_entries.entry_id "
        "ORDER BY m.created_at DESC LIMIT 1) AS mapping_status, "
        "(SELECT m.suggested_service_type FROM provider_service_mapping_reviews m "
        "WHERE m.entry_id=provider_directory_entries.entry_id "
        "ORDER BY m.created_at DESC LIMIT 1) AS suggested_service_type "
        "FROM provider_directory_entries"
    )
    clauses: list[str] = []
    params: list[Any] = []
    if region_id:
        clauses.append("region_id=?")
        params.append(region_id)
    if source_id:
        clauses.append("source_id=?")
        params.append(source_id)
    if search:
        clauses.append("(name LIKE ? OR public_service_description LIKE ? OR region_label LIKE ?)")
        term = f"%{search.strip()[:100]}%"
        params.extend((term, term, term))
    clauses.append(
        "(snapshot_id IS NULL OR snapshot_id=(SELECT s.snapshot_id "
        "FROM provider_directory_snapshots s WHERE s.source_id="
        "provider_directory_entries.source_id ORDER BY s.created_at DESC LIMIT 1))"
    )
    query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY name, entry_id LIMIT ? OFFSET ?"
    params.extend((max(1, min(limit, 200)), max(0, offset)))
    return [dict(row) for row in connection.execute(query, tuple(params))]
