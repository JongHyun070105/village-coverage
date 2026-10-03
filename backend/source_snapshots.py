"""Raw-snapshot cache for external API ingestion (V4 §66, §67, §96, §97).

Each successful pull is stored as an immutable JSON snapshot with its request
parameters (credentials removed), retrieval time, record count, content hash,
and observed schema. When a live pull fails, callers fall back to the latest
successful snapshot and surface its date; nothing is fabricated. A schema that
differs from the expected contract is never silently accepted.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CACHE_DIR = ROOT / "data" / "cache" / "source_snapshots"
SECRET_PARAM_NAMES = frozenset({"apikey", "servicekey", "api_key", "service_key", "key"})


class SchemaDriftDetected(RuntimeError):
    """Observed fields no longer satisfy the expected source contract."""

    def __init__(self, source_id: str, missing: list[str], unexpected: list[str]):
        self.source_id = source_id
        self.missing = missing
        self.unexpected = unexpected
        super().__init__(f"SCHEMA_DRIFT_DETECTED for {source_id}: missing={missing}")


class SourceUnavailable(RuntimeError):
    """A live source failed before returning usable data; the code is safe to log."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(f"{code}: {message}")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def redact_params(params: dict[str, Any]) -> dict[str, Any]:
    return {
        key: ("<redacted>" if key.lower() in SECRET_PARAM_NAMES else value)
        for key, value in sorted(params.items())
    }


def content_hash(records: Any) -> str:
    encoded = json.dumps(records, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def check_schema(
    source_id: str, required: Iterable[str], observed: Iterable[str]
) -> dict[str, Any]:
    required_set, observed_set = set(required), set(observed)
    missing = sorted(required_set - observed_set)
    unexpected = sorted(observed_set - required_set)
    if missing:
        raise SchemaDriftDetected(source_id, missing, unexpected)
    return {"status": "SCHEMA_OK", "unexpected_fields": unexpected}


@dataclass(frozen=True)
class Snapshot:
    source_id: str
    snapshot_id: str
    retrieved_at: str
    request_params: dict[str, Any]
    record_count: int
    source_hash: str
    schema_status: str
    payload: Any

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "snapshot_id": self.snapshot_id,
            "retrieved_at": self.retrieved_at,
            "request_params": self.request_params,
            "record_count": self.record_count,
            "source_hash": self.source_hash,
            "schema_status": self.schema_status,
            "payload": self.payload,
        }


class SnapshotStore:
    def __init__(self, cache_dir: Path | str = DEFAULT_CACHE_DIR):
        self.cache_dir = Path(cache_dir)

    def _dir(self, source_id: str) -> Path:
        safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in source_id)
        return self.cache_dir / safe

    def store(
        self,
        source_id: str,
        *,
        request_params: dict[str, Any],
        payload: Any,
        record_count: int,
        schema_status: str = "SCHEMA_OK",
        retrieved_at: str | None = None,
    ) -> Snapshot:
        retrieved = retrieved_at or utc_now()
        digest = content_hash(payload)
        snapshot = Snapshot(
            source_id=source_id,
            snapshot_id=f"{source_id}:{digest[:16]}",
            retrieved_at=retrieved,
            request_params=redact_params(request_params),
            record_count=record_count,
            source_hash=digest,
            schema_status=schema_status,
            payload=payload,
        )
        directory = self._dir(source_id)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{digest[:16]}.json"
        if not path.exists():  # immutable: identical content keeps the first record
            path.write_text(
                json.dumps(snapshot.as_dict(), ensure_ascii=False, indent=1), encoding="utf-8"
            )
        (directory / "LATEST").write_text(path.name, encoding="utf-8")
        return snapshot

    def latest(self, source_id: str) -> Snapshot | None:
        directory = self._dir(source_id)
        pointer = directory / "LATEST"
        if not pointer.exists():
            return None
        path = directory / pointer.read_text(encoding="utf-8").strip()
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return Snapshot(**data)


def ingest_with_fallback(
    source_id: str,
    fetch: Callable[[], tuple[dict[str, Any], Any, int]],
    store: SnapshotStore,
) -> dict[str, Any]:
    """Run a live pull; on failure, return the latest successful snapshot, labelled."""
    try:
        params, payload, count = fetch()
    except SchemaDriftDetected as exc:
        cached = store.latest(source_id)
        return {
            "status": "SCHEMA_DRIFT_DETECTED",
            "error_code": "SCHEMA_DRIFT_DETECTED",
            "missing_fields": exc.missing,
            "snapshot": cached.as_dict() if cached else None,
            "cache_note": _cache_note(cached),
        }
    except SourceUnavailable as exc:
        cached = store.latest(source_id)
        return {
            "status": "CACHED_FALLBACK" if cached else "UNAVAILABLE",
            "error_code": exc.code,
            "snapshot": cached.as_dict() if cached else None,
            "cache_note": _cache_note(cached),
        }
    snapshot = store.store(source_id, request_params=params, payload=payload, record_count=count)
    return {"status": "LIVE", "error_code": None, "snapshot": snapshot.as_dict(),
            "cache_note": None}


def _cache_note(snapshot: Snapshot | None) -> str | None:
    if snapshot is None:
        return None
    day = snapshot.retrieved_at[:10]
    return f"{day} 기준 캐시"
