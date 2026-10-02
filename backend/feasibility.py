"""Deterministic feasibility breakdown, solver safety model, and route failure explanations."""

from __future__ import annotations

from typing import Any

SOLVER_STATUS_MESSAGES: dict[str, str] = {
    "OPTIMAL": "최적성이 확인된 계획입니다.",
    "FEASIBLE": "실행 가능한 계획을 찾았지만 최적성은 확인되지 않았습니다.",
    "TIME_LIMIT": "제한시간 내 실행 가능한 계획을 찾았으며 더 나은 계획이 존재할 수 있습니다.",
    "INFEASIBLE": "현재 조건으로 실행 가능한 계획이 없습니다.",
    "UNKNOWN": "계획 수립 상태를 확인할 수 없습니다.",
    "MODEL_INVALID": "계획 모델 설정이 올바르지 않습니다.",
}

# The 8 canonical minimum service guarantee failure reason codes (§17)
FEASIBILITY_REASONS = (
    "MONEY_SHORTAGE",
    "PROVIDER_CAPACITY_SHORTAGE",
    "NO_COMPATIBLE_PROVIDER",
    "PROVIDER_DECLINED",
    "TIME_WINDOW_CONFLICT",
    "ROUTE_UNAVAILABLE",
    "SERVICE_NOT_SUPPORTED",
    "INSUFFICIENT_EVIDENCE",
)

# Route matrix failure codes (§13)
ROUTE_FAILURE_CODES = (
    "ROAD_EDGE_MISSING",
    "MULTI_STOP_ROUTE_INCOMPLETE",
    "HUB_FALLBACK_USED",
    "NO_ROAD_ROUTE",
    "ROUTE_UNAVAILABLE",
    "ROUTE_API_NOT_AVAILABLE",
)

LEGACY_REASON_MAP: dict[str, str] = {
    "BUDGET": "MONEY_SHORTAGE",
    "MONEY_SHORTAGE": "MONEY_SHORTAGE",
    "PROVIDER_CAPACITY": "PROVIDER_CAPACITY_SHORTAGE",
    "SHARED_PROVIDER_CAPACITY": "PROVIDER_CAPACITY_SHORTAGE",
    "PROVIDER_CAPACITY_OR_SERVICE_MIX": "PROVIDER_CAPACITY_SHORTAGE",
    "PROVIDER_CAPACITY_SHORTAGE": "PROVIDER_CAPACITY_SHORTAGE",
    "NO_SUPPORTED_PROVIDER": "NO_COMPATIBLE_PROVIDER",
    "NO_COMPATIBLE_PROVIDER": "NO_COMPATIBLE_PROVIDER",
    "PROVIDER_DECLINED": "PROVIDER_DECLINED",
    "REQUESTED_TIME_WINDOW": "TIME_WINDOW_CONFLICT",
    "EXCLUDED_DAY_CONFLICT": "TIME_WINDOW_CONFLICT",
    "PREFERRED_DAY_CONFLICT": "TIME_WINDOW_CONFLICT",
    "REQUESTED_DATE_WINDOW": "TIME_WINDOW_CONFLICT",
    "TIME_WINDOW": "TIME_WINDOW_CONFLICT",
    "MAX_DAILY_HOURS": "TIME_WINDOW_CONFLICT",
    "SHARED_PROVIDER_TIME": "TIME_WINDOW_CONFLICT",
    "TIME_WINDOW_CONFLICT": "TIME_WINDOW_CONFLICT",
    "MAX_TRAVEL_TIME": "ROUTE_UNAVAILABLE",
    "ROUTE_UNAVAILABLE": "ROUTE_UNAVAILABLE",
    "NO_ROAD_ROUTE": "ROUTE_UNAVAILABLE",
    "ROAD_EDGE_MISSING": "ROUTE_UNAVAILABLE",
    "MULTI_STOP_ROUTE_INCOMPLETE": "ROUTE_UNAVAILABLE",
    "ROUTE_API_NOT_AVAILABLE": "ROUTE_UNAVAILABLE",
    "SERVICE_NOT_ALLOWED": "SERVICE_NOT_SUPPORTED",
    "SERVICE_NOT_SUPPORTED": "SERVICE_NOT_SUPPORTED",
    "NEEDS_SURVEY": "INSUFFICIENT_EVIDENCE",
    "INSUFFICIENT_EVIDENCE": "INSUFFICIENT_EVIDENCE",
    "DEMAND_BELOW_MINIMUM": "DEMAND_BELOW_MINIMUM",
}

SERVICE_LABELS: dict[str, str] = {
    "laundry": "세탁",
    "daily_necessities": "생필품",
    "home_repair": "주거수리",
}


def canonicalize_feasibility_reason(reason: str | None) -> str:
    """Map internal or legacy reason codes to canonical §17 codes."""
    if not reason:
        return "SCENARIO_PRIORITY"
    return LEGACY_REASON_MAP.get(reason, reason)


def explain_area_feasibility(
    primary_code: str,
    service_type: str = "daily_necessities",
    secondary_codes: list[str] | None = None,
) -> dict[str, Any]:
    """Provide deterministic, rule-based area failure explanation without LLM generation."""
    canonical_primary = canonicalize_feasibility_reason(primary_code)
    secondary_canonical = [
        canonicalize_feasibility_reason(code)
        for code in (secondary_codes or [])
        if canonicalize_feasibility_reason(code) != canonical_primary
    ]
    # Unique preserve order
    seen: set[str] = set()
    filtered_secondaries = []
    for code in secondary_canonical:
        if code not in seen:
            seen.add(code)
            filtered_secondaries.append(code)

    service_name = SERVICE_LABELS.get(service_type, service_type)
    money_resolvable = canonical_primary == "MONEY_SHORTAGE"

    if canonical_primary == "MONEY_SHORTAGE":
        suggested_action = "추가 예산 확보 시 계획 충족 가능"
        reason_explanation = "예산 부족으로 인해 최소 서비스 횟수를 충족하지 못했습니다."
    elif canonical_primary == "PROVIDER_CAPACITY_SHORTAGE":
        suggested_action = f"추가 {service_name} 공급자 확보 또는 서비스 일정 조정"
        reason_explanation = (
            f"{service_name} 공급자의 가용 용량이 부족합니다 (예산 추가만으로 해결 불가)."
        )
    elif canonical_primary == "NO_COMPATIBLE_PROVIDER":
        suggested_action = f"{service_name} 서비스를 제공할 수 있는 신규 공급자 발굴"
        reason_explanation = (
            f"해당 권역에서 {service_name} 서비스를 제공할 수 있는 공급자가 없습니다."
        )
    elif canonical_primary == "PROVIDER_DECLINED":
        suggested_action = "공급자 참여 일정 재조율 또는 대체 공급자 배정"
        reason_explanation = "공급자가 해당 일정에 참여하지 않아 배정되지 못했습니다."
    elif canonical_primary == "TIME_WINDOW_CONFLICT":
        suggested_action = "희망 방문 시간대 완화 또는 요일 조정"
        reason_explanation = "희망 시간대 및 운영 시간 제약으로 일정을 확정하지 못했습니다."
    elif canonical_primary == "ROUTE_UNAVAILABLE":
        suggested_action = "도로 경로 데이터 확인 또는 인근 거점 재설정"
        reason_explanation = "도로 이동시간을 확인할 수 없어 해당 회차를 계획하지 못했습니다."
    elif canonical_primary == "SERVICE_NOT_SUPPORTED":
        suggested_action = "정책 허용 서비스 항목 검토 및 조정"
        reason_explanation = "현재 계획 정책에서 허용되지 않은 서비스 유형입니다."
    elif canonical_primary == "INSUFFICIENT_EVIDENCE":
        suggested_action = "현장 조사 또는 전화 확인을 통한 수요 검증"
        reason_explanation = "수요 근거 데이터가 부족하여 현장 조사가 필요합니다."
    elif canonical_primary == "DEMAND_BELOW_MINIMUM":
        suggested_action = "해당 권역의 수요 조사 재확인"
        reason_explanation = "권역의 월간 서비스 수요가 최소 보장 기준보다 적습니다."
    else:
        suggested_action = "정책 우선순위 및 자원 배분 검토"
        reason_explanation = "정책 우선순위 또는 복합 제약으로 인해 배정되지 못했습니다."

    return {
        "primary_reason": canonical_primary,
        "secondary_reasons": filtered_secondaries,
        "money_resolvable": money_resolvable,
        "suggested_action": suggested_action,
        "reason_explanation": reason_explanation,
    }


def map_solver_status(
    status_code: int,
    wall_time_seconds: float,
    max_time_seconds: float,
    cp_model_module: Any,
) -> tuple[str, bool, bool]:
    """Map OR-Tools CP-SAT status to explicit safety model (§12).

    Returns (solver_status, optimality_proven, time_limit_reached).
    Never converts FEASIBLE to OPTIMAL.
    """
    time_limit_margin = 0.05
    time_limit_reached = wall_time_seconds >= (max_time_seconds - time_limit_margin)

    if status_code == cp_model_module.OPTIMAL:
        return "OPTIMAL", True, False
    elif status_code == cp_model_module.FEASIBLE:
        if time_limit_reached:
            return "TIME_LIMIT", False, True
        return "FEASIBLE", False, False
    elif status_code == cp_model_module.INFEASIBLE:
        return "INFEASIBLE", False, False
    elif status_code == cp_model_module.MODEL_INVALID:
        return "MODEL_INVALID", False, False
    else:  # UNKNOWN or others
        if time_limit_reached:
            return "TIME_LIMIT", False, True
        return "UNKNOWN", False, False
