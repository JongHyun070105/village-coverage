"""Pull KREI/KOSIS/HomeDoctor evidence and write secret-free snapshot artifacts.

Usage: uv run python scripts/run_empirical_ingestion.py [--offline]

Live pulls use KOSIS_API_KEY and DATA_GO_KR_SERVICE_KEY server-side. Raw
responses go to the gitignored cache (data/cache/source_snapshots); artifacts
hold only aggregated, provenance-tagged summaries. Failures fall back to the
last successful snapshot and are reported, never fabricated.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.empirical_priors import empirical_prior_snapshot  # noqa: E402
from backend.home_doctor import fetch_all_rows, summarize  # noqa: E402
from backend.kosis import (  # noqa: E402
    KOSIS_CATALOG_PATH,
    KOSIS_TABLES,
    KOSIS_TOPICS_NOT_FOUND,
    KosisClient,
    parse_table,
)
from backend.source_snapshots import (  # noqa: E402
    SnapshotStore,
    SourceUnavailable,
    ingest_with_fallback,
    utc_now,
)
from scripts.api_smoke_test import _load_config  # noqa: E402

ARTIFACTS = ROOT / "artifacts"


def _write(name: str, payload: dict) -> None:
    path = ARTIFACTS / name
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {path.relative_to(ROOT)}")


def kosis_snapshot(store: SnapshotStore, offline: bool) -> dict:
    key = _load_config("KOSIS_API_KEY")
    print("KOSIS_API_KEY", "PRESENT" if key else "MISSING")
    tables = []
    for table in KOSIS_TABLES:
        def fetch(table=table):
            if offline:
                raise SourceUnavailable("OFFLINE_MODE", "live pull disabled")
            client = KosisClient(key)
            rows = client.table_data(table)
            parsed = parse_table(table, rows)
            comments = [c.get("CMMT_DC") for c in client.table_comments(table)
                        if c.get("CMMT_NM") == "통계표"]
            parsed["definition"] = comments[0] if comments else None
            params = {"orgId": "117", "tblId": table.table_id, "prdSe": table.period_type,
                      "newEstPrdCnt": 1, "apiKey": key}
            return params, parsed, parsed["record_count"]

        result = ingest_with_fallback(f"KOSIS_{table.table_id}", fetch, store)
        snap = result["snapshot"]
        tables.append({
            "table_id": table.table_id,
            "status": result["status"],
            "error_code": result["error_code"],
            "cache_note": result["cache_note"],
            "retrieved_at": snap["retrieved_at"] if snap else None,
            "source_hash": snap["source_hash"] if snap else None,
            "data": snap["payload"] if snap else None,
        })
        print(table.table_id, result["status"], result["error_code"] or "")
    return {
        "source_id": "KOSIS_117_DT_117078",
        "generated_at": utc_now(),
        "catalog_path": KOSIS_CATALOG_PATH,
        "provenance": "EXTERNAL_CONTEXT",
        "scope_rule": (
            "KOSIS 사회서비스(전국 가구) 맥락 근거; KREI 농촌 생활서비스 기준값과 혼합 금지"
        ),
        "live_verified": any(t["status"] == "LIVE" for t in tables),
        "tables": tables,
        "topics_not_found": list(KOSIS_TOPICS_NOT_FOUND),
    }


def home_doctor_snapshot(store: SnapshotStore, offline: bool) -> dict:
    key = _load_config("DATA_GO_KR_SERVICE_KEY")
    print("DATA_GO_KR_SERVICE_KEY", "PRESENT" if key else "MISSING")

    def fetch():
        if offline:
            raise SourceUnavailable("OFFLINE_MODE", "live pull disabled")
        rows = fetch_all_rows(key)
        return {"dataset": "15120958", "perPage": 5000, "serviceKey": key}, rows, len(rows)

    result = ingest_with_fallback("DATA_GO_KR_15120958", fetch, store)
    snap = result["snapshot"]
    summary = summarize(snap["payload"]) if snap else None
    print("HomeDoctor", result["status"], result["error_code"] or "")
    return {
        "source_id": "DATA_GO_KR_15120958",
        "generated_at": utc_now(),
        "status": result["status"],
        "error_code": result["error_code"],
        "cache_note": result["cache_note"],
        "live_verified": result["status"] == "LIVE",
        "retrieved_at": snap["retrieved_at"] if snap else None,
        "raw_record_count": snap["record_count"] if snap else 0,
        "raw_source_hash": snap["source_hash"] if snap else None,
        "summary": summary,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    store = SnapshotStore()
    _write("empirical_prior_snapshot.json", empirical_prior_snapshot())
    _write("kosis_snapshot.json", kosis_snapshot(store, args.offline))
    _write("home_doctor_snapshot.json", home_doctor_snapshot(store, args.offline))


if __name__ == "__main__":
    main()
