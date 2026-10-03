"""Minimum coverage V2: money-only vs schedule-feasible minimum cost (V4 §25-§27).

* THEORETICAL_MINIMUM_COST (money only): the decomposed planner's aggregate
  relaxation under the *same* cost model but without the calendar (dates,
  time windows, daily hours). It is a lower bound on the schedule-feasible cost.
* The V3 monthly aggregate estimate (``optimization.minimum_guarantee_budget``)
  uses a central-hub travel model and is reported separately; it is *not* a
  bound on the schedule model and the two must not be subtracted.
* SCHEDULE_FEASIBLE_MINIMUM_COST: the 28-day provider/date/route model
  minimizing cost subject to every area meeting the minimum
  (``scheduling.generate_provider_schedule(_required_budget_only=True)``), or a
  monotone binary search over budgets with the full planner as oracle.

When a gap is caused by providers, routes, time windows, service support or
missing evidence, more money alone will not close it; that is reported
explicitly instead of a budget figure.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from typing import Any

# Canonical feasibility reasons -> V4 non-monetary failure codes.
NON_MONETARY_REASON_MAP: dict[str, str] = {
    "NO_COMPATIBLE_PROVIDER": "NO_PROVIDER",
    "PROVIDER_DECLINED": "NO_PROVIDER",
    "PROVIDER_CAPACITY_SHORTAGE": "NO_CAPACITY",
    "ROUTE_UNAVAILABLE": "NO_ROUTE",
    "TIME_WINDOW_CONFLICT": "TIME_WINDOW",
    "SERVICE_NOT_SUPPORTED": "SERVICE_NOT_SUPPORTED",
    "INSUFFICIENT_EVIDENCE": "DATA_INSUFFICIENT",
    "DEMAND_BELOW_MINIMUM": "DATA_INSUFFICIENT",
}
NON_MONETARY_LABELS_KO: dict[str, str] = {
    "NO_PROVIDER": "가능한 공급자 없음",
    "NO_CAPACITY": "공급자 용량 부족",
    "NO_ROUTE": "도로 경로 없음",
    "TIME_WINDOW": "시간대 제약",
    "SERVICE_NOT_SUPPORTED": "지원하지 않는 서비스",
    "DATA_INSUFFICIENT": "수요 근거 부족",
}
REQUIRED_BUDGET_FAILURE_TO_CODE = {
    "PROVIDER_CAPACITY_OR_TIME": "NO_CAPACITY",
    "DEMAND_BELOW_MINIMUM": "DATA_INSUFFICIENT",
}


def classify_area_gaps(plan: dict[str, Any]) -> list[dict[str, Any]]:
    """Split each unmet area into money-resolvable vs non-monetary causes."""
    rows = []
    for area_id, explanation in (plan.get("feasibility_breakdown") or {}).items():
        reasons = [explanation.get("primary_reason"), *explanation.get("secondary_reasons", [])]
        codes = sorted(
            {NON_MONETARY_REASON_MAP[r] for r in reasons if r in NON_MONETARY_REASON_MAP}
        )
        rows.append({
            "area_id": area_id,
            "primary_reason": explanation.get("primary_reason"),
            "non_monetary_codes": codes,
            "money_resolvable": bool(explanation.get("money_resolvable")) and not codes,
            "suggested_action": explanation.get("suggested_action"),
        })
    return sorted(rows, key=lambda row: row["area_id"])


def minimum_coverage_comparison(
    *,
    plan: dict[str, Any],
    budget_won: int,
    legacy_estimate_won: int | None,
    legacy_status: str,
) -> dict[str, Any]:
    gaps = classify_area_gaps(plan)
    theoretical_minimum_won = plan.get("money_only_minimum_won")
    schedule_won = plan.get("required_budget_won")
    schedule_status = plan.get("required_budget_status") or "NOT_CALCULATED"
    schedule_reason = plan.get("required_budget_reason")
    non_monetary: dict[str, int | None] = dict(
        Counter(code for row in gaps for code in row["non_monetary_codes"])
    )
    if schedule_status == "INFEASIBLE" and schedule_reason in REQUIRED_BUDGET_FAILURE_TO_CODE:
        # Region-level blocker from the schedule model: no per-area count available.
        non_monetary.setdefault(REQUIRED_BUDGET_FAILURE_TO_CODE[schedule_reason], None)
    # A proven schedule-feasible minimum means more money *does* close the gap, even
    # if capacity/route constraints bind at the current budget. Only a proven
    # infeasibility makes money alone insufficient; otherwise it is unknown.
    if schedule_status == "CALCULATED":
        money_alone_insufficient: bool | None = False
    elif schedule_status == "INFEASIBLE":
        money_alone_insufficient = True
    else:
        money_alone_insufficient = None
    difference = (
        schedule_won - theoretical_minimum_won
        if schedule_won is not None and theoretical_minimum_won is not None
        else None
    )
    return {
        "theoretical_minimum_cost": {
            "value_won": theoretical_minimum_won,
            "status": "CALCULATED" if theoretical_minimum_won is not None else "NOT_PROVEN",
            "model": "AGGREGATE_RELAXATION_SAME_COST_MODEL_NO_CALENDAR",
            "label": "이론적 최소비용 (같은 비용모델, 일정·시간 제약 미반영)",
        },
        "legacy_monthly_estimate": {
            "value_won": legacy_estimate_won,
            "status": legacy_status,
            "model": "V3_MONTHLY_AGGREGATE_CENTRAL_HUB_TRAVEL",
            "label": "V3 월간 집계 추정 (중앙거점 이동모델; 위 두 값과 직접 비교 불가)",
        },
        "schedule_feasible_minimum_cost": {
            "value_won": schedule_won,
            "status": schedule_status,
            "reason": schedule_reason,
            "model": plan.get("required_budget_model")
            or "FOUR_WEEK_PROVIDER_DATE_ROUTE_MODEL",
            "route_strategy": plan.get("route_strategy"),
            "label": "실행 가능한 일정 기준 최소비용",
        },
        "difference_won": difference,
        "budget_won": budget_won,
        "additional_budget_needed_won": (
            max(0, schedule_won - budget_won) if schedule_won is not None else None
        ),
        "money_alone_insufficient": money_alone_insufficient,
        "money_alone_message": (
            "예산 증액만으로는 해결되지 않습니다."
            if money_alone_insufficient
            else "예산 증액으로 최소보장이 가능합니다 (일정 기준 최소비용 확인)."
            if money_alone_insufficient is False
            else "예산 증액만으로 해결되는지 확인되지 않았습니다."
        ),
        "non_monetary_scope": (
            "BINDING_AT_CURRENT_BUDGET" if money_alone_insufficient is False
            else "BLOCKING" if money_alone_insufficient else "UNVERIFIED"
        ),
        "non_monetary_failures": [
            {"code": code, "label": NON_MONETARY_LABELS_KO[code], "area_count": count}
            for code, count in sorted(non_monetary.items())
        ],
        "area_gaps": gaps,
        "status_note": (
            "최소비용 값은 최적성이 증명된 경우에만 표시합니다; 미증명 시 값은 비워 둡니다."
        ),
    }


def binary_search_minimum_budget(
    probe: Callable[[int], dict[str, Any]],
    *,
    lower_won: int,
    upper_won: int,
    tolerance_won: int = 10_000,
    max_probes: int = 18,
) -> dict[str, Any]:
    """Smallest budget whose plan meets the minimum, assuming feasibility is monotone in budget.

    A probe that fails *with* a proven-optimal solve is conclusive (budget too
    low). A probe that fails without proof is inconclusive: the search then only
    returns an upper bound, never a claimed minimum.
    """
    probes: list[dict[str, Any]] = []
    top = probe(upper_won)
    probes.append(_probe_row(upper_won, top))
    if not top.get("minimum_coverage_met"):
        return {
            "status": "NOT_MET_AT_UPPER_BOUND",
            "money_alone_insufficient": True,
            "minimum_budget_won": None,
            "upper_bound_won": None,
            "probes": probes,
        }
    low, high = lower_won, upper_won
    inconclusive = False
    while high - low > tolerance_won and len(probes) < max_probes:
        middle = (low + high) // 2
        result = probe(middle)
        probes.append(_probe_row(middle, result))
        if result.get("minimum_coverage_met"):
            high = middle
        elif _shortfall_proven(result):
            low = middle
        else:
            inconclusive = True
            low = middle  # keep searching, but the final value is only an upper bound
    exhausted_above_tolerance = high - low > tolerance_won
    proven_minimum = not inconclusive and not exhausted_above_tolerance
    return {
        "status": "FOUND_WITHIN_TOLERANCE" if proven_minimum else "UPPER_BOUND_ONLY",
        "money_alone_insufficient": False,
        "minimum_budget_won": high if proven_minimum else None,
        "upper_bound_won": high,
        "tolerance_won": tolerance_won,
        "search_limit_reached": exhausted_above_tolerance,
        "inconclusive_probe_seen": inconclusive,
        "probes": probes,
    }


def _shortfall_proven(result: dict[str, Any]) -> bool:
    """A failed probe is conclusive if the solve, or its proven relaxation, rules it out."""
    if result.get("optimality_proven"):
        return True
    decomposition = result.get("decomposition") or {}
    aggregate = decomposition.get("stage_a_components") or {}
    required = result.get("minimum_frequency_met_areas", 0) + result.get(
        "unmet_minimum_frequency_areas", 0
    )
    return (
        decomposition.get("stage_a_status") == "OPTIMAL"
        and aggregate.get("met_count") is not None
        and required > 0
        and aggregate["met_count"] < required
    )


def _probe_row(budget: int, result: dict[str, Any]) -> dict[str, Any]:
    return {
        "budget_won": budget,
        "minimum_coverage_met": bool(result.get("minimum_coverage_met")),
        "solver_status": result.get("solver_status"),
        "optimality_proven": bool(result.get("optimality_proven")),
        "shortfall_proven": (
            None if result.get("minimum_coverage_met") else _shortfall_proven(result)
        ),
    }
