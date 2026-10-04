"""Cost model V3: itemised plan cost and funding gap where UNKNOWN never becomes 0."""

from __future__ import annotations

import math
from typing import Any

from backend.optimization import TRAVEL_LABOR_WON_PER_HOUR, TRAVEL_RATE_WON_PER_KM

MODEL_VERSION = "COST_MODEL_V3"
UNKNOWN = "UNKNOWN"

COMPONENT_LABELS_KO = {
    "TRAVEL_DISTANCE": "이동거리 비용",
    "TRAVEL_TIME": "이동시간 비용",
    "SETUP": "준비·설치 비용",
    "SERVICE": "서비스 수행비",
    "MATERIAL": "재료비",
    "VEHICLE": "차량비",
    "FIXED_PARTICIPATION": "고정 참여비",
    "MINIMUM_COMPENSATION_TOPUP": "최소 보상 보전액",
}
COMPONENTS = tuple(COMPONENT_LABELS_KO)
ASSUMPTION_KEYS = {
    "SETUP": "setup_per_round_won",
    "MATERIAL": "material_per_unit_won",
    "VEHICLE": "vehicle_per_round_won",
    "FIXED_PARTICIPATION": "fixed_participation_per_provider_month_won",
}


def _nonnegative(assumptions: dict[str, Any], key: str) -> int | None:
    value = assumptions.get(key)
    if value is None or value == UNKNOWN:
        return None
    if isinstance(value, bool) or int(value) != value or int(value) < 0:
        raise ValueError(f"{key} must be a nonnegative integer or UNKNOWN")
    return int(value)


def round_cost_components(
    plan_round: dict[str, Any], assumptions: dict[str, Any]
) -> dict[str, Any]:
    before = int(plan_round.get("travel_before_s", 0))
    after = int(plan_round.get("travel_after_s", 0))
    distance_m = int(plan_round.get("travel_distance_m", 0))
    time_cost = (
        math.ceil(before / 3600 * TRAVEL_LABOR_WON_PER_HOUR)
        + math.ceil(after / 3600 * TRAVEL_LABOR_WON_PER_HOUR)
    )
    distance_cost = math.ceil(distance_m / 1000 * TRAVEL_RATE_WON_PER_KM)
    travel_total = int(plan_round["travel_cost_won"])
    setup = _nonnegative(assumptions, ASSUMPTION_KEYS["SETUP"])
    material = _nonnegative(assumptions, ASSUMPTION_KEYS["MATERIAL"])
    vehicle = _nonnegative(assumptions, ASSUMPTION_KEYS["VEHICLE"])
    units = int(plan_round["service_units"])
    return {
        "provider_id": plan_round["provider_id"],
        "area_id": plan_round["area_id"],
        "scheduled_date": plan_round.get("scheduled_date"),
        "components": {
            "TRAVEL_DISTANCE": distance_cost,
            "TRAVEL_TIME": time_cost,
            "SETUP": setup,
            "SERVICE": int(plan_round["service_cost_won"]),
            "MATERIAL": None if material is None else material * units,
            "VEHICLE": vehicle,
        },
        "travel_reconciliation_residual_won": travel_total - distance_cost - time_cost,
    }


def plan_cost_model(
    rounds: list[dict[str, Any]],
    assumptions: dict[str, Any] | None = None,
    *,
    minimum_compensation_topup_won: int | None = None,
) -> dict[str, Any]:
    """Itemise a plan; a component with no input is UNKNOWN and excluded from the known floor."""
    assumptions = dict(assumptions or {})
    items = [round_cost_components(row, assumptions) for row in rounds]
    topup = (
        sum(int(row.get("minimum_compensation_topup_won", 0)) for row in rounds)
        if minimum_compensation_topup_won is None
        else int(minimum_compensation_topup_won)
    )
    fixed_unit = _nonnegative(assumptions, ASSUMPTION_KEYS["FIXED_PARTICIPATION"])
    provider_months = {
        (row["provider_id"], str(row.get("scheduled_date") or "")[:7]) for row in rounds
    }
    totals: dict[str, int | None] = {}
    for component in COMPONENTS:
        if component == "FIXED_PARTICIPATION":
            totals[component] = None if fixed_unit is None else fixed_unit * len(provider_months)
        elif component == "MINIMUM_COMPENSATION_TOPUP":
            totals[component] = topup
        elif component in ASSUMPTION_KEYS:
            provided = _nonnegative(assumptions, ASSUMPTION_KEYS[component])
            totals[component] = (
                None if provided is None
                else sum(item["components"][component] for item in items)
            )
        else:
            totals[component] = sum(item["components"][component] for item in items)
    known_floor = sum(value for value in totals.values() if value is not None)
    unknown = sorted(key for key, value in totals.items() if value is None)
    return {
        "model_version": MODEL_VERSION,
        "components": [
            {
                "component": key,
                "label": COMPONENT_LABELS_KO[key],
                "amount_won": UNKNOWN if totals[key] is None else totals[key],
                "provenance": (
                    "UNKNOWN: NO PLANNER INPUT" if totals[key] is None
                    else "PLANNER INPUT" if key in ASSUMPTION_KEYS
                    else "OPTIMIZER COST MODEL"
                ),
            }
            for key in COMPONENTS
        ],
        "known_cost_floor_won": known_floor,
        "unknown_components": unknown,
        "cost_status": "EXACT" if not unknown else "AT_LEAST_KNOWN_FLOOR",
        "total_cost_won": known_floor if not unknown else None,
        "travel_reconciliation_residual_won": sum(
            item["travel_reconciliation_residual_won"] for item in items
        ),
        "provider_months_with_service": len(provider_months),
        "rounds": items,
        "label": "MODEL ESTIMATE",
    }


def funding_gap(
    cost_model: dict[str, Any],
    *,
    budget_won: int,
    other_funding: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Gap = cost - funding. Unknown costs unbound the gap above, unknown funding below."""
    if budget_won < 0:
        raise ValueError("budget_won must be nonnegative")
    known_funding = int(budget_won)
    unknown_funding: list[str] = []
    for source, value in sorted((other_funding or {}).items()):
        if value is None or value == UNKNOWN:
            unknown_funding.append(source)
            continue
        if int(value) < 0:
            raise ValueError("funding amounts must be nonnegative")
        known_funding += int(value)
    floor = int(cost_model["known_cost_floor_won"])
    costs_exact = not cost_model["unknown_components"]
    funding_exact = not unknown_funding
    shortfall_at_known = max(0, floor - known_funding)
    point = shortfall_at_known if costs_exact and funding_exact else None
    if costs_exact and funding_exact:
        status = "EXACT"
    elif costs_exact:
        status = "UPPER_BOUND_UNKNOWN_FUNDING"
    elif funding_exact:
        status = "LOWER_BOUND_UNKNOWN_COSTS"
    else:
        status = "UNKNOWN_BOTH_SIDES"
    return {
        "known_cost_floor_won": floor,
        "known_funding_won": known_funding,
        "gap_won": point,
        "gap_at_least_won": shortfall_at_known if funding_exact and not costs_exact else None,
        "gap_at_most_won": shortfall_at_known if costs_exact and not funding_exact else None,
        "status": status,
        "unknown_cost_components": cost_model["unknown_components"],
        "unknown_funding_sources": unknown_funding,
        "note": "알 수 없는 항목은 0원으로 처리하지 않고 범위로만 표시합니다.",
        "label": "MODEL ESTIMATE",
    }
