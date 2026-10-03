"""Payload builders for the 근거·출처 center and per-village V4 demand evidence."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from backend.demand_model_v4 import DEFAULT_CONFIG, estimate_area_service_demand
from backend.empirical_priors import (
    DEFINITIONS,
    JANGGOK_LAUNDRY_CASE,
    KREI_SOURCE,
    LAUNDRY_CASES,
    NOT_INTENDED_USES,
    SERVICE_DESIGN_REFERENCE_MODELS,
    V4_DEMO_SERVICES,
    prior_for_service,
    prior_payload,
)
from backend.provenance import CALIBRATION_STATUS_KO, VALUE_LABELS_KO
from backend.source_registry import SOURCES, source_payload

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"


def _artifact(name: str) -> dict[str, Any] | None:
    try:
        return json.loads((ARTIFACTS / name).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _snapshot_status() -> dict[str, dict[str, Any]]:
    kosis = _artifact("kosis_snapshot.json") or {}
    home = _artifact("home_doctor_snapshot.json") or {}
    kosis_tables = kosis.get("tables") or []
    return {
        "KOSIS_117_DT_117078": {
            "snapshot_status": (
                "LIVE_VERIFIED" if kosis.get("live_verified") else
                "CACHED" if any(t.get("data") for t in kosis_tables) else "UNAVAILABLE"
            ),
            "snapshot_generated_at": kosis.get("generated_at"),
            "cache_note": next((t.get("cache_note") for t in kosis_tables if t.get("cache_note")),
                               None),
            "table_count": sum(1 for t in kosis_tables if t.get("data")),
        },
        "DATA_GO_KR_15120958": {
            "snapshot_status": (
                "LIVE_VERIFIED" if home.get("live_verified") else
                "CACHED" if home.get("summary") else "UNAVAILABLE"
            ),
            "snapshot_generated_at": home.get("generated_at"),
            "cache_note": home.get("cache_note"),
            "record_count": home.get("raw_record_count"),
        },
        "KREI_R2025_23": {
            "snapshot_status": "ENCODED_FROM_REPORT",
            "snapshot_hash": (_artifact("empirical_prior_snapshot.json") or {}).get(
                "snapshot_hash"),
        },
    }


def sources_payload() -> dict[str, Any]:
    status = _snapshot_status()
    return {
        "sources": [
            {**source_payload(source), **status.get(source.source_id, {})} for source in SOURCES
        ],
        "value_labels": VALUE_LABELS_KO,
        "calibration_status_labels": CALIBRATION_STATUS_KO,
    }


def priors_payload() -> dict[str, Any]:
    return {
        "source": KREI_SOURCE,
        "definitions": DEFINITIONS,
        "not_intended_uses": list(NOT_INTENDED_USES),
        "demo_services": [prior_payload(prior_for_service(s)) for s in V4_DEMO_SERVICES],
        "laundry_cases": [_case(case) for case in (*LAUNDRY_CASES, JANGGOK_LAUNDRY_CASE)],
        "service_design_reference_models": list(SERVICE_DESIGN_REFERENCE_MODELS),
    }


def _case(case: Any) -> dict[str, Any]:
    from dataclasses import asdict

    payload = asdict(case)
    payload["funding_sources"] = list(case.funding_sources)
    return payload


def kosis_payload() -> dict[str, Any]:
    snapshot = _artifact("kosis_snapshot.json")
    if snapshot is None:
        return {"status": "UNAVAILABLE", "tables": []}
    return snapshot


def home_doctor_payload() -> dict[str, Any]:
    snapshot = _artifact("home_doctor_snapshot.json")
    if snapshot is None:
        return {"status": "UNAVAILABLE", "summary": None}
    summary = dict(snapshot.get("summary") or {})
    summary.pop("branch_monthly", None)  # keep the API payload compact
    return {**{k: v for k, v in snapshot.items() if k != "summary"}, "summary": summary}


def village_demand_v4(
    *,
    area: dict[str, Any],
    surveys: list[dict[str, Any]],
    evidence_review: dict[str, Any],
    calibration_by_service: dict[str, str],
    as_of: date,
) -> list[dict[str, Any]]:
    unresolved_conflicts = sum(
        1 for c in evidence_review.get("conflicts", [])
        if c.get("status") == "REVIEW_REQUIRED" or c.get("resolution_method") == "FURTHER_SURVEY"
    )
    unresolved_duplicates = sum(
        1 for c in evidence_review.get("duplicate_candidates", [])
        if c.get("status") == "POSSIBLE_DUPLICATE"
    )
    results = []
    for service_type in V4_DEMO_SERVICES:
        observations = [
            {
                "occurred_on": s["survey_date"],
                "frequency_per_month": s.get("frequency_per_month"),
                "source_type": s.get("survey_type"),
                "created_at": s.get("created_at"),
            }
            for s in surveys if s.get("service_type") == service_type
        ]
        synthetic = (
            float(area["simulated_monthly_demand"])
            if area.get("service_type") == service_type and area.get("simulated_monthly_demand")
            else None
        )
        results.append(
            estimate_area_service_demand(
                area=area,
                service_type=service_type,
                observations=observations,
                as_of=as_of,
                synthetic_prior_monthly=synthetic,
                unresolved_conflicts=unresolved_conflicts,
                unresolved_duplicates=unresolved_duplicates,
                local_calibration_status_v3=calibration_by_service.get(service_type,
                                                                       "UNCALIBRATED"),
                config=DEFAULT_CONFIG,
            )
        )
    return results
