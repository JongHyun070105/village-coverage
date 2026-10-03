"""Public finance model V2 (V4 §11, §92).

Gross plan cost is split into cost categories; revenues are separated by
funding source. Unconfirmed support amounts are UNKNOWN, never zero: if any
offsetting amount is unknown, the net public funding need is reported as an
upper bound ("at most"), not as a point value.
"""

from __future__ import annotations

from typing import Any

from backend.service_modes import COST_CATEGORY_LABELS_KO, FUNDING_SOURCE_LABELS_KO

UNKNOWN = "UNKNOWN"
REVENUE_SOURCES = ("USER_FEE", "COOPERATIVE_REVENUE", "DONATION", "SOCIAL_CONTRIBUTION", "OTHER")
PUBLIC_SOURCES = ("CENTRAL_GOV_SUBSIDY", "PUBLIC_PROGRAM")


def plan_cost_breakdown(plan_summary: dict[str, Any]) -> dict[str, int | None]:
    """Map schedule cost fields onto V4 cost categories (unmodelled items stay None)."""
    return {
        "SERVICE_EXECUTION_COST": _int(plan_summary.get("service_cost_won")),
        "TRAVEL_DISTANCE_COST": _int(plan_summary.get("travel_cost_won")),
        "STAFF_COST": _int(plan_summary.get("minimum_compensation_topup_won")),
        "TRAVEL_TIME_COST": None,  # folded into travel_cost_won by the planner
        "VEHICLE_COST": None,
        "MATERIAL_COST": None,
        "FIXED_INFRASTRUCTURE_COST": None,
        "FACILITY_OPERATING_COST": None,
        "MAINTENANCE_COST": None,
    }


def _int(value: Any) -> int | None:
    return None if value is None else int(value)


def public_finance_view(
    *,
    gross_cost_won: int,
    served_units: int,
    user_fee_per_unit_won: int | str = UNKNOWN,
    fee_exempt_share: float | str = UNKNOWN,
    funding: dict[str, int | str] | None = None,
    cost_breakdown: dict[str, int | None] | None = None,
) -> dict[str, Any]:
    """Scenario finance; every input may be UNKNOWN and is shown as such."""
    funding = dict(funding or {})
    unknown_inputs: list[str] = []

    if user_fee_per_unit_won == UNKNOWN or fee_exempt_share == UNKNOWN:
        user_fee_revenue: int | str = UNKNOWN
        unknown_inputs.append("USER_FEE")
    else:
        share = float(fee_exempt_share)
        if not 0 <= share <= 1:
            raise ValueError("fee_exempt_share must be between 0 and 1")
        paying_units = round(served_units * (1 - share))
        user_fee_revenue = paying_units * int(user_fee_per_unit_won)

    public_support = 0
    other_revenue = 0
    sources = []
    for source in (*PUBLIC_SOURCES, *REVENUE_SOURCES[1:]):
        value = funding.get(source, UNKNOWN)
        sources.append({"source": source, "label": FUNDING_SOURCE_LABELS_KO[source],
                        "amount_won": value})
        if value == UNKNOWN:
            unknown_inputs.append(source)
            continue
        if int(value) < 0:
            raise ValueError("funding amounts must be nonnegative")
        if source in PUBLIC_SOURCES:
            public_support += int(value)
        else:
            other_revenue += int(value)
    sources.insert(0, {"source": "USER_FEE", "label": FUNDING_SOURCE_LABELS_KO["USER_FEE"],
                       "amount_won": user_fee_revenue})

    known_offsets = public_support + other_revenue + (
        user_fee_revenue if isinstance(user_fee_revenue, int) else 0
    )
    net = max(0, gross_cost_won - known_offsets)
    exact = not unknown_inputs
    local_dependency = (round(net / gross_cost_won, 3) if gross_cost_won and exact else None)
    breakdown = cost_breakdown or {}
    return {
        "gross_cost_won": gross_cost_won,
        "cost_breakdown": [
            {"category": key, "label": COST_CATEGORY_LABELS_KO[key],
             "amount_won": value if value is not None else UNKNOWN}
            for key, value in breakdown.items()
        ],
        "user_fee_revenue_won": user_fee_revenue,
        "existing_public_support_won": public_support if not set(PUBLIC_SOURCES) & set(
            unknown_inputs) else UNKNOWN,
        "other_revenue_won": other_revenue if not set(REVENUE_SOURCES[1:]) & set(
            unknown_inputs) else UNKNOWN,
        "net_public_funding_need_won": net if exact else None,
        "net_public_funding_need_upper_bound_won": net,
        "net_public_funding_status": "EXACT" if exact else "UPPER_BOUND_UNKNOWN_OFFSETS",
        "unknown_inputs": sorted(set(unknown_inputs)),
        "funding_sources": sources,
        "sustainability": {
            "local_budget_dependency_ratio": local_dependency,
            "user_fee_share": (round(user_fee_revenue / gross_cost_won, 3)
                               if isinstance(user_fee_revenue, int) and gross_cost_won else None),
            "note": "시나리오 계산이며 실제 사업 재무전망이 아닙니다.",
        },
        "provenance": "SCENARIO INPUT + OPTIMIZATION RESULT",
    }
