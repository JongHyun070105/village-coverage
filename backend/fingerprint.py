"""Plan reproducibility fingerprint and provenance view (§21)."""

from __future__ import annotations

import hashlib
import json
from typing import Any

OPTIMIZER_VERSION = "v3-ortools-cpsat-deterministic"
ROUTE_CACHE_VERSION = "kakao-mobility-directed-20261002"
FORECAST_CALIBRATION_VERSION = "v3-hurdle-rolling-origin-v1"


def canonical_json_hash(payload: Any) -> str:
    """Generate a deterministic SHA-256 hash from canonical sorted JSON."""
    serialized = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def compute_plan_fingerprint(
    *,
    areas: list[dict[str, Any]],
    providers: list[dict[str, Any]],
    budget_won: int,
    policy_dict: dict[str, Any],
    route_matrix_fingerprint: str | None = None,
    optimizer_version: str = OPTIMIZER_VERSION,
    forecast_calibration_version: str = FORECAST_CALIBRATION_VERSION,
    evidence_snapshot_id: str | None = None,
) -> dict[str, Any]:
    """Compute deterministic SHA-256 fingerprint for a planning run.

    Guarantees:
      Same input snapshots + configuration -> same fingerprint.
      Any change in budget, policy, routes, or provider state -> distinct fingerprint.
    """
    # 1. Canonical representation of service areas & public data
    canonical_areas = sorted(
        [
            {
                "id": str(a.get("id")),
                "name": str(a.get("name")),
                "service_type": str(a.get("service_type")),
                "simulated_monthly_demand": int(a.get("simulated_monthly_demand", 0)),
                "needs_survey": bool(a.get("needs_survey", False)),
                "population_total": int(a.get("population_total", 0)),
                "elderly_ratio_65": float(a.get("elderly_ratio_65", 0.0)),
                "single_households_65_plus": int(a.get("single_households_65_plus", 0)),
            }
            for a in areas
        ],
        key=lambda item: item["id"],
    )

    # 2. Canonical representation of providers & availability
    canonical_providers = sorted(
        [
            {
                "provider_id": str(p.get("provider_id")),
                "base_area_id": str(p.get("base_area_id")),
                "supported_services": sorted(str(s) for s in p.get("supported_services", [])),
                "max_monthly_rounds": int(p.get("max_monthly_rounds", 0)),
                "service_capacity": int(p.get("service_capacity", 0)),
                "max_daily_hours": float(p.get("max_daily_hours", 0.0)),
                "max_travel_time_minutes": int(p.get("max_travel_time_minutes", 0)),
                "availability": sorted(
                    [
                        f"{slot.get('weekday')}:{slot.get('start_time')}-{slot.get('end_time')}"
                        for slot in p.get("availability", [])
                    ]
                ),
            }
            for p in providers
        ],
        key=lambda item: item["provider_id"],
    )

    canonical_payload = {
        "public_data_snapshot": canonical_areas,
        "evidence_snapshot_id": evidence_snapshot_id or "default-evidence-snapshot",
        "provider_profiles": canonical_providers,
        "budget_won": int(budget_won),
        "policy_config": policy_dict,
        "route_matrix_version": route_matrix_fingerprint or ROUTE_CACHE_VERSION,
        "optimizer_version": optimizer_version,
        "forecast_calibration_version": forecast_calibration_version,
    }

    fingerprint = canonical_json_hash(canonical_payload)

    # Human-readable provenance view (§21)
    provenance_view = {
        "fingerprint": fingerprint,
        "public_data": "2026-08 행정안전부 주민등록 인구 및 통계청 가구원 데이터",
        "demand_evidence": (
            f"수요 조사 및 보정 증빙 (스냅샷: {canonical_payload['evidence_snapshot_id']})"
        ),
        "provider_model": f"공급자 실현가능 프로필 (등록 공급자 {len(canonical_providers)}개소)",
        "road_routing": (
            f"Kakao Mobility 유향 도로 캐시 ({canonical_payload['route_matrix_version']})"
        ),
        "policy_model": (
            f"정책 가중치 설정 (어르신: {policy_dict.get('elderly_priority_weight', 500)}, "
            f"독거가구: {policy_dict.get('single_elderly_household_priority_weight', 500)}, "
            f"설문보호: {policy_dict.get('survey_required_protection_weight', 1000)})"
        ),
        "optimizer": f"Google OR-Tools CP-SAT ({optimizer_version})",
        "reproducible": True,
    }

    return {
        "fingerprint": fingerprint,
        "canonical_payload": canonical_payload,
        "provenance_view": provenance_view,
    }
