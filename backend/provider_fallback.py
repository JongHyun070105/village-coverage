"""Fallback provider candidates and reserve-policy comparison. Candidates are never contracts.

A fallback must satisfy the same hard constraints as the primary: supported service,
availability window, travel limit, daily hours, monthly capacity and, for home repair, a
verified capability. Unknown stays unknown: an unverified provider is not a fallback.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from backend import home_repair, scheduling
from backend.settings import PlanningPolicy

TIERS = ("PRIMARY", "SECONDARY", "TERTIARY")
RESERVE_RATIOS_PCT = (0, 5, 10, 15)
RESERVE_OPTIONS = ("NO_RESERVE", "BUDGET_RESERVE", "PROVIDER_FALLBACK", "BOTH")
CANDIDATE_NOTICE = "후보일 뿐 자동 계약·배정이 아닙니다. 제공자 확인이 필요합니다."


def _month(date_text: str) -> str:
    return str(date_text)[:7]


def _topup(provider: dict[str, Any], policy: PlanningPolicy, service_cost: int) -> int:
    if service_cost <= 0:
        return 0
    minimum = max(
        int(provider.get("minimum_compensation_won", 0)),
        int(policy.minimum_provider_compensation_won),
    )
    return max(0, minimum - service_cost)


def _capability_ok(
    provider: dict[str, Any], service_type: str, capabilities: dict[str, dict[str, Any]] | None
) -> tuple[bool, str | None]:
    if service_type != "home_repair":
        return True, None
    capability = (capabilities or {}).get(str(provider["provider_id"]))
    if capability is None:
        return False, "CAPABILITY_UNVERIFIED"
    fit = home_repair.provider_profile_fit(capability)
    if not fit["eligible_job_ids"]:
        return False, "CAPABILITY_UNVERIFIED" if not fit["all_jobs_verified"] else "CAPABILITY_LOW"
    return True, None


def _usage(rounds: list[dict[str, Any]]) -> tuple[dict[tuple[str, str], int], set[tuple[str, str]]]:
    monthly: dict[tuple[str, str], int] = {}
    busy_days: set[tuple[str, str]] = set()
    for item in rounds:
        monthly[(item["provider_id"], _month(item["scheduled_date"]))] = (
            monthly.get((item["provider_id"], _month(item["scheduled_date"])), 0) + 1
        )
        busy_days.add((item["provider_id"], item["scheduled_date"]))
    return monthly, busy_days


def _round_fits_candidate(item: dict[str, Any], candidate: dict[str, Any]) -> bool:
    start = scheduling._minute(item["service_start_time"])
    end = scheduling._minute(item["service_end_time"])
    route = candidate["route"]
    departure = start - (route["outbound_s"] + 59) // 60
    arrival = end + (route["inbound_s"] + 59) // 60
    return (
        departure >= scheduling._minute(candidate["availability_start"])
        and arrival <= scheduling._minute(candidate["availability_end"])
    )


def fallback_candidates(
    areas: list[dict[str, Any]],
    providers: list[dict[str, Any]],
    routes: dict[tuple[str, str], tuple[int, int]],
    policy: PlanningPolicy,
    rounds: list[dict[str, Any]],
    *,
    capabilities: dict[str, dict[str, Any]] | None = None,
    depth: int = 2,
) -> dict[str, Any]:
    """Rank up to ``depth`` fallback providers for every planned round."""
    area_by_id = {str(area["id"]): area for area in areas}
    provider_by_id = {str(provider["provider_id"]): provider for provider in providers}
    monthly, busy_days = _usage(rounds)
    candidates_by_area: dict[str, list[dict[str, Any]]] = {}
    for area_id in sorted({str(item["area_id"]) for item in rounds}):
        candidates, _ = scheduling._make_candidates(
            [deepcopy(area_by_id[area_id])], providers, routes, policy,
            allow_route_fallback=True,
        )
        candidates_by_area[area_id] = candidates

    rows: list[dict[str, Any]] = []
    for item in sorted(
        rounds, key=lambda r: (r["scheduled_date"], r["provider_id"], r["area_id"])
    ):
        primary_id = str(item["provider_id"])
        rejected: dict[str, str] = {}
        viable: list[dict[str, Any]] = []
        for candidate in candidates_by_area[str(item["area_id"])]:
            provider_id = str(candidate["provider_id"])
            if provider_id == primary_id or candidate["scheduled_date"] != item["scheduled_date"]:
                continue
            if provider_id in rejected or any(v["provider_id"] == provider_id for v in viable):
                continue
            provider = provider_by_id[provider_id]
            ok, reason = _capability_ok(provider, str(item["service_type"]), capabilities)
            if not ok:
                rejected[provider_id] = str(reason)
                continue
            if (provider_id, item["scheduled_date"]) in busy_days:
                rejected[provider_id] = "PROVIDER_BUSY_THAT_DAY"
                continue
            used = monthly.get((provider_id, _month(item["scheduled_date"])), 0)
            if used + 1 > int(provider["max_monthly_rounds"]):
                rejected[provider_id] = "MONTHLY_CAPACITY_FULL"
                continue
            if not _round_fits_candidate(item, candidate):
                rejected[provider_id] = "TIME_WINDOW_MISMATCH"
                continue
            cost = (
                int(item["service_units"]) * scheduling.SERVICE_COST_WON[item["service_type"]]
                + int(candidate["route"]["cost_won"])
            )
            viable.append(
                {
                    "provider_id": provider_id,
                    "provider_name": candidate["provider_name"],
                    "estimated_total_cost_won": cost,
                    "extra_cost_vs_primary_won": cost - int(item["total_cost_won"]),
                    "travel_time_s": int(candidate["route"]["duration_s"]),
                }
            )
        viable.sort(
            key=lambda v: (v["estimated_total_cost_won"], v["travel_time_s"], v["provider_id"])
        )
        picked = [
            {**v, "tier": TIERS[index + 1], "requires_provider_confirmation": True,
             "auto_contract": False}
            for index, v in enumerate(viable[:depth])
        ]
        rows.append(
            {
                "area_id": item["area_id"],
                "service_type": item["service_type"],
                "scheduled_date": item["scheduled_date"],
                "primary_provider_id": primary_id,
                "primary_total_cost_won": int(item["total_cost_won"]),
                "fallbacks": picked,
                "has_fallback": bool(picked),
                "rejected_reasons": rejected,
            }
        )
    without = [row for row in rows if not row["has_fallback"]]
    return {
        "rounds": rows,
        "round_count": len(rows),
        "rounds_without_fallback": len(without),
        "fallback_coverage": (1 - len(without) / len(rows)) if rows else None,
        "status": "CANDIDATES_ONLY",
        "notice": CANDIDATE_NOTICE,
    }


def _zero_service(areas: list[dict[str, Any]], served: dict[str, int]) -> int:
    return sum(
        1 for area in areas
        if int(area.get("simulated_monthly_demand", 0)) > 0 and served.get(str(area["id"]), 0) <= 0
    )


def _served(rounds: list[dict[str, Any]]) -> dict[str, int]:
    served: dict[str, int] = {}
    for item in rounds:
        served[str(item["area_id"])] = served.get(str(item["area_id"]), 0) + int(
            item["service_units"]
        )
    return served


def _outcome(areas: list[dict[str, Any]], rounds: list[dict[str, Any]]) -> dict[str, int]:
    served = _served(rounds)
    return {
        "served_units": sum(served.values()),
        "zero_service_areas": _zero_service(areas, served),
    }


def recover_by_fallback(
    areas: list[dict[str, Any]],
    providers: list[dict[str, Any]],
    routes: dict[tuple[str, str], tuple[int, int]],
    policy: PlanningPolicy,
    rounds: list[dict[str, Any]],
    declined_provider_id: str,
    leftover_budget_won: int,
    *,
    capabilities: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Move a declining provider's rounds to ranked fallbacks while leftover budget allows."""
    provider_by_id = {str(p["provider_id"]): p for p in providers}
    surviving = [r for r in rounds if r["provider_id"] != declined_provider_id]
    lost = [r for r in rounds if r["provider_id"] == declined_provider_id]
    remaining_providers = [p for p in providers if p["provider_id"] != declined_provider_id]
    plan = fallback_candidates(
        areas, providers, routes, policy, rounds, capabilities=capabilities, depth=3,
    ) if remaining_providers else {"rounds": []}
    plan_rows = {
        (row["area_id"], row["scheduled_date"], row["primary_provider_id"]): row
        for row in plan["rounds"]
    }
    service_by_provider_month: dict[tuple[str, str], int] = {}
    for item in surviving:
        key = (item["provider_id"], _month(item["scheduled_date"]))
        service_by_provider_month[key] = service_by_provider_month.get(key, 0) + int(
            item["service_cost_won"]
        )
    monthly, busy_days = _usage(surviving)
    leftover = leftover_budget_won + sum(int(item["total_cost_won"]) for item in lost)
    spent_extra = 0
    moved: list[dict[str, Any]] = []
    for item in sorted(lost, key=lambda r: (r["scheduled_date"], r["area_id"])):
        row = plan_rows.get((item["area_id"], item["scheduled_date"], declined_provider_id))
        placed = False
        for option in (row["fallbacks"] if row else []):
            provider_id = option["provider_id"]
            provider = provider_by_id[provider_id]
            month = _month(item["scheduled_date"])
            if (provider_id, item["scheduled_date"]) in busy_days:
                continue
            if monthly.get((provider_id, month), 0) + 1 > int(provider["max_monthly_rounds"]):
                continue
            service_cost = int(item["service_units"]) * scheduling.SERVICE_COST_WON[
                item["service_type"]
            ]
            before = service_by_provider_month.get((provider_id, month), 0)
            topup_delta = _topup(provider, policy, before + service_cost) - _topup(
                provider, policy, before
            )
            cost = option["estimated_total_cost_won"] + topup_delta
            if spent_extra + cost > leftover:
                continue
            spent_extra += cost
            service_by_provider_month[(provider_id, month)] = before + service_cost
            monthly[(provider_id, month)] = monthly.get((provider_id, month), 0) + 1
            busy_days.add((provider_id, item["scheduled_date"]))
            moved.append({**item, "provider_id": provider_id,
                          "provider_name": option["provider_name"],
                          "total_cost_won": cost, "service_cost_won": service_cost})
            placed = True
            break
        if not placed:
            continue
    final = surviving + moved
    return {
        "rounds": final,
        "moved_round_count": len(moved),
        "lost_round_count": len(lost) - len(moved),
        "extra_spend_won": spent_extra,
        "outcome": _outcome(areas, final),
    }


def compare_reserve_policies(
    areas: list[dict[str, Any]],
    providers: list[dict[str, Any]],
    connection: Any,
    budget_won: int,
    *,
    reserve_pct: int,
    scenario: str = "balanced",
    policy: PlanningPolicy | None = None,
    capabilities: dict[str, dict[str, Any]] | None = None,
    max_solver_seconds: float = 20.0,
) -> dict[str, Any]:
    """Compare four reserve options by simulating each planned provider declining alone."""
    if reserve_pct not in RESERVE_RATIOS_PCT:
        raise ValueError(f"reserve_pct must be one of {RESERVE_RATIOS_PCT}")
    policy = policy or PlanningPolicy()
    routes = scheduling._route_rows(connection)
    reserve_budget = budget_won * (100 - reserve_pct) // 100

    def plan(budget: int, subset: list[dict[str, Any]]) -> dict[str, Any]:
        return scheduling.generate_provider_schedule(
            deepcopy(areas), deepcopy(subset), connection, budget, scenario, policy,
            allow_route_fallback=True, max_solver_seconds=max_solver_seconds,
        )

    full = plan(budget_won, providers)
    held = plan(reserve_budget, providers)
    planned_providers = sorted({r["provider_id"] for r in full["rounds"]})
    declines = []
    for declined in planned_providers:
        row: dict[str, Any] = {"declined_provider_id": declined, "options": {}}
        lost_units = sum(int(r["service_units"]) for r in full["rounds"]
                         if r["provider_id"] == declined)
        remaining = [p for p in providers if p["provider_id"] != declined]
        no_reserve_rounds = [r for r in full["rounds"] if r["provider_id"] != declined]
        row["options"]["NO_RESERVE"] = {
            **_outcome(areas, no_reserve_rounds), "mechanism": "NONE",
            "spend_won": sum(int(r["total_cost_won"]) for r in no_reserve_rounds),
        }
        replan_held = plan(budget_won, remaining) if remaining else {"rounds": []}
        row["options"]["BUDGET_RESERVE"] = {
            **_outcome(areas, replan_held["rounds"]), "mechanism": "REPLAN_WITH_RESERVE",
            "spend_won": sum(int(r["total_cost_won"]) for r in replan_held["rounds"]),
        }
        full_leftover = budget_won - int(full["budget_spent_won"])
        fb_full = recover_by_fallback(
            areas, providers, routes, policy, full["rounds"], declined, full_leftover,
            capabilities=capabilities,
        )
        row["options"]["PROVIDER_FALLBACK"] = {
            **fb_full["outcome"], "mechanism": "FALLBACK_CANDIDATES",
            "spend_won": sum(int(r["total_cost_won"]) for r in fb_full["rounds"]),
            "moved_rounds": fb_full["moved_round_count"],
        }
        held_leftover = budget_won - int(held["budget_spent_won"])
        fb_held = recover_by_fallback(
            areas, providers, routes, policy, held["rounds"], declined, held_leftover,
            capabilities=capabilities,
        )
        both = {**fb_held["outcome"], "mechanism": "FALLBACK_CANDIDATES",
                "spend_won": sum(int(r["total_cost_won"]) for r in fb_held["rounds"]),
                "moved_rounds": fb_held["moved_round_count"]}
        if fb_held["lost_round_count"] > 0 and remaining:
            replan_both = plan(budget_won, remaining)
            candidate_outcome = _outcome(areas, replan_both["rounds"])
            if (candidate_outcome["zero_service_areas"], -candidate_outcome["served_units"]) < (
                both["zero_service_areas"], -both["served_units"]
            ):
                both = {**candidate_outcome, "mechanism": "REPLAN_WITH_RESERVE",
                        "spend_won": sum(int(r["total_cost_won"]) for r in replan_both["rounds"]),
                        "moved_rounds": 0}
        row["options"]["BOTH"] = both
        row["lost_units_without_recovery"] = lost_units
        declines.append(row)

    def aggregate(option: str) -> dict[str, Any]:
        outcomes = [d["options"][option] for d in declines]
        base = full if option in ("NO_RESERVE", "PROVIDER_FALLBACK") else held
        within_budget = all(o["spend_won"] <= budget_won for o in outcomes)
        return {
            "option": option,
            "planned_budget_won": budget_won if base is full else reserve_budget,
            "no_decline": _outcome(areas, base["rounds"]),
            "worst_zero_service_after_decline": max(
                (o["zero_service_areas"] for o in outcomes), default=None),
            "worst_served_units_after_decline": min(
                (o["served_units"] for o in outcomes), default=None),
            "mechanisms": sorted({o["mechanism"] for o in outcomes}),
            "budget_never_exceeded": within_budget,
        }

    return {
        "scenario": scenario,
        "budget_won": budget_won,
        "reserve_pct": reserve_pct,
        "reserve_chosen_by": "PLANNER",
        "options": [aggregate(option) for option in RESERVE_OPTIONS],
        "declines": declines,
        "label": "SIMULATION",
        "notice": "공급자 불참 가정 시뮬레이션입니다. 예비 비율은 담당자가 선택합니다.",
    }
