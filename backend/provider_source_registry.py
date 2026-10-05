"""Audited metadata for provider directories, separate from operating evidence."""

from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass
from typing import Any

from backend.source_registry import source_map


@dataclass(frozen=True, slots=True)
class ProviderSource:
    source_id: str
    source_name: str
    provider_authority: str
    source_url: str
    dataset_id: str
    license_type: str
    reuse_allowed: bool
    scope: str
    snapshot_date: str
    update_cycle: str
    schema_version: str


PROVIDER_SOURCES: tuple[ProviderSource, ...] = (
    ProviderSource(
        source_id="DATA_GO_KR_15091502",
        source_name="한국자활복지개발원 전국자활기업현황",
        provider_authority="한국자활복지개발원",
        source_url="https://www.data.go.kr/data/15091502/fileData.do",
        dataset_id="15091502",
        license_type="OPEN_NO_RESTRICTION",
        reuse_allowed=True,
        scope="전국",
        snapshot_date="2025-12-31",
        update_cycle="연간; 다음 등록 예정 2027-04-08",
        schema_version="self-support-v1",
    ),
    ProviderSource(
        source_id="DATA_GO_KR_15090110",
        source_name="고용노동부 사회적기업 목록",
        provider_authority="고용노동부",
        source_url="https://www.data.go.kr/data/15090110/fileData.do",
        dataset_id="15090110",
        license_type="OPEN_NO_RESTRICTION",
        reuse_allowed=True,
        scope="전국",
        snapshot_date="2025-06-30",
        update_cycle="수시 (자동 갱신 안내)",
        schema_version="social-enterprise-v1",
    ),
    ProviderSource(
        source_id="DATA_GO_KR_15080745",
        source_name="행정안전부 전국 마을기업 현황",
        provider_authority="행정안전부",
        source_url="https://www.data.go.kr/data/15080745/fileData.do",
        dataset_id="15080745",
        license_type="OPEN_NO_RESTRICTION",
        reuse_allowed=True,
        scope="전국",
        snapshot_date="2025-12-31",
        update_cycle="연간; 다음 등록 예정 2027-09-14",
        schema_version="village-enterprise-v1",
    ),
    ProviderSource(
        source_id="DATA_GO_KR_15155661",
        source_name="전국협동조합표준데이터",
        provider_authority="기획재정부 소관 / 지방자치단체 제공",
        source_url="https://www.data.go.kr/data/15155661/standard.do",
        dataset_id="15155661",
        license_type="UNCLEAR",
        reuse_allowed=False,
        scope="전국; 지자체 자료의 월별 병합으로 시차 가능",
        snapshot_date="2026-09-15 (포털 수정일)",
        update_cycle="월별 병합; 개별 지자체 제공 일정에 따름",
        schema_version="cooperative-standard-unverified",
    ),
)

INGESTION_STATES = frozenset(
    {
        "DISCOVERED",
        "LICENSE_VERIFIED",
        "INGEST_ALLOWED",
        "INGEST_BLOCKED",
        "INGESTED",
        "SCHEMA_DRIFT",
        "ERROR",
    }
)


class ProviderSourceRegistry:
    """Persist the reviewed source contract and mutable ingestion outcome."""

    def sync(self, connection: sqlite3.Connection) -> None:
        sources = source_map()
        for source in PROVIDER_SOURCES:
            legacy = sources.get(source.source_id)
            if legacy is None:
                raise ValueError(
                    f"Provider source lacks a base source-registry record: {source.source_id}"
                )
            initial_state = "INGEST_ALLOWED" if source.reuse_allowed else "INGEST_BLOCKED"
            connection.execute(
                """INSERT INTO provider_source_registry(
                     source_id, source_name, provider_authority, source_url, dataset_id,
                     license_type, reuse_allowed, scope, snapshot_date, update_cycle,
                     schema_version, ingestion_status, updated_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                     strftime('%Y-%m-%dT%H:%M:%SZ','now'))
                   ON CONFLICT(source_id) DO UPDATE SET
                     source_name=excluded.source_name,
                     provider_authority=excluded.provider_authority,
                     source_url=excluded.source_url,
                     dataset_id=excluded.dataset_id,
                     license_type=excluded.license_type,
                     reuse_allowed=excluded.reuse_allowed,
                     scope=excluded.scope,
                     snapshot_date=excluded.snapshot_date,
                     update_cycle=excluded.update_cycle,
                     schema_version=excluded.schema_version,
                     updated_at=excluded.updated_at""",
                (
                    source.source_id,
                    source.source_name,
                    source.provider_authority,
                    source.source_url,
                    source.dataset_id,
                    source.license_type,
                    int(source.reuse_allowed),
                    source.scope,
                    source.snapshot_date,
                    source.update_cycle,
                    source.schema_version,
                    initial_state,
                ),
            )

    def list(self, connection: sqlite3.Connection) -> list[dict[str, Any]]:
        self.sync(connection)
        return [
            dict(row)
            for row in connection.execute(
                "SELECT * FROM provider_source_registry ORDER BY source_id"
            ).fetchall()
        ]

    def get(self, connection: sqlite3.Connection, source_id: str) -> dict[str, Any] | None:
        self.sync(connection)
        row = connection.execute(
            "SELECT * FROM provider_source_registry WHERE source_id=?", (source_id,)
        ).fetchone()
        return dict(row) if row else None

    def mark_result(
        self,
        connection: sqlite3.Connection,
        source_id: str,
        *,
        status: str,
        content_hash: str | None = None,
        error: str | None = None,
        successful_at: str | None = None,
        downloaded_at: str | None = None,
    ) -> None:
        if status not in INGESTION_STATES:
            raise ValueError("Unknown provider source ingestion state")
        source = self.get(connection, source_id)
        if source is None:
            raise KeyError(source_id)
        if status in {"INGESTED", "SCHEMA_DRIFT", "ERROR"} and not source["reuse_allowed"]:
            raise ValueError("A source without verified reuse permission cannot be ingested")
        connection.execute(
            """UPDATE provider_source_registry SET ingestion_status=?, content_hash=?,
                 last_error=?, last_success=COALESCE(?, last_success),
                 downloaded_at=COALESCE(?, downloaded_at),
                 updated_at=strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE source_id=?""",
            (status, content_hash, error, successful_at, downloaded_at, source_id),
        )


def provider_source_definitions() -> list[dict[str, Any]]:
    return [asdict(source) for source in PROVIDER_SOURCES]
