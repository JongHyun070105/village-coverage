"""Compare delivery modes for the same laundry demand (V4 §87-§93).

Delivery mode is a policy choice: this module reports cost, distance, staff
time, and resident access for each mode side by side and never ranks one as
"best". Road legs come from the cached Kakao matrix; facility existence comes
from public village-hall/senior-center data; every operating parameter is a
visible SIMULATION assumption (KREI case values are references, not defaults).
"""

from __future__ import annotations

import itertools
import math
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any

from backend.optimization import TRAVEL_LABOR_WON_PER_HOUR, TRAVEL_RATE_WON_PER_KM
from backend.service_modes import SERVICE_MODE_LABELS_KO

RoadLookup = Callable[[str, str], tuple[int, int] | None]  # -> (distance_m, duration_s)


@dataclass(frozen=True)
class ModeAssumptions:
    """Planner-visible scenario inputs (SIMULATION; not observed operating data)."""

    staff_won_per_hour: int = TRAVEL_LABOR_WON_PER_HOUR
    vehicle_won_per_km: int = TRAVEL_RATE_WON_PER_KM
    home_visit_minutes_per_unit: int = 45
    pickup_runs_per_month: int = 8  # weekly pickup + weekly return delivery
    pickup_stop_minutes: int = 15
    central_processing_won_per_unit: int = 8_000
    mobile_visits_per_area_per_month: int = 2
    mobile_minutes_per_unit: int = 60
    mobile_vehicle_won_per_day: int = 150_000
    hub_operating_won_per_month: int = 300_000
    hub_staff_hours_per_month: int = 40
    hub_access_threshold_minutes: int = 15
    workday_minutes: int = 8 * 60
    existing_public_asset: bool = True
    provenance: str = "SIMULATION_ASSUMPTION"

    def payload(self) -> dict[str, Any]:
        return asdict(self)


DEFAULT_ASSUMPTIONS = ModeAssumptions()


def _tour(base: str, stops: list[str], road: RoadLookup) -> tuple[list[str], int, int] | None:
    """Deterministic nearest-neighbour tour + 2-opt over directed road legs."""
    if not stops:
        return [], 0, 0

    def leg(a: str, b: str) -> tuple[int, int] | None:
        return road(a, b)

    remaining = sorted(stops)
    order: list[str] = []
    current = base
    while remaining:
        options = [(leg(current, s), s) for s in remaining]
        options = [(value, s) for value, s in options if value is not None]
        if not options:
            return None
        (_, nxt) = min(options, key=lambda item: (item[0][1], item[1]))
        order.append(nxt)
        remaining.remove(nxt)
        current = nxt

    def total(sequence: list[str]) -> tuple[int, int] | None:
        path = [base, *sequence, base]
        dist = dur = 0
        for a, b in zip(path, path[1:], strict=False):
            value = leg(a, b)
            if value is None:
                return None
            dist += value[0]
            dur += value[1]
        return dist, dur

    best = total(order)
    if best is None:
        return None
    improved = True
    while improved:
        improved = False
        for i, j in itertools.combinations(range(len(order)), 2):
            candidate = order[:i] + order[i:j + 1][::-1] + order[j + 1:]
            value = total(candidate)
            if value is not None and value[1] < best[1]:
                order, best, improved = candidate, value, True
    return order, best[0], best[1]


def select_hubs(
    areas: list[dict[str, Any]], road: RoadLookup, *, max_hubs: int = 2,
    threshold_minutes: int = 15,
) -> list[dict[str, Any]]:
    """Exhaustive p-median over areas with a public village hall/senior center.

    Criteria: demand-weighted resident travel minutes (primary), population
    within the access threshold, then area id for determinism. Only existing
    public facilities are candidates; no new construction is assumed.
    """
    candidates = sorted(str(a["id"]) for a in areas if int(a.get("facility_count") or 0) > 0)
    results = []
    for k in range(1, max_hubs + 1):
        best = None
        for hubs in itertools.combinations(candidates, k):
            weighted = 0.0
            within = 0
            unreachable = 0
            for area in areas:
                area_id = str(area["id"])
                times = [0 if area_id == hub else (road(area_id, hub) or (None, None))[1]
                         for hub in hubs]
                times = [t for t in times if t is not None]
                if not times:
                    unreachable += 1
                    continue
                minutes = min(times) / 60
                weighted += minutes * int(area.get("simulated_monthly_demand") or 0)
                if minutes <= threshold_minutes:
                    within += int(area.get("population_total") or 0)
            key = (unreachable, round(weighted, 3), -within, hubs)
            if best is None or key < best[0]:
                best = (key, hubs, weighted, within, unreachable)
        if best is not None:
            _, hubs, weighted, within, unreachable = best
            results.append({
                "hub_count": k,
                "hub_area_ids": list(hubs),
                "demand_weighted_travel_minutes": round(weighted, 1),
                "population_within_threshold": within,
                "unreachable_areas": unreachable,
                "facility_existence": "REAL PUBLIC DATA (마을회관·경로당 표준데이터)",
                "facility_availability": "SIMULATED (운영 가능 여부 미확인)",
            })
    return results


def compare_service_modes(
    *,
    areas: list[dict[str, Any]],
    base_area_id: str,
    road: RoadLookup,
    assumptions: ModeAssumptions | None = None,
    hub_count: int = 1,
) -> dict[str, Any]:
    demand = {str(a["id"]): int(a.get("simulated_monthly_demand") or 0) for a in areas}
    units = sum(demand.values())
    demand_areas = sorted(a for a, d in demand.items() if d > 0)
    a = assumptions or DEFAULT_ASSUMPTIONS
    staff = a.staff_won_per_hour / 60  # won per minute
    km = a.vehicle_won_per_km / 1000  # won per metre
    modes: dict[str, dict[str, Any]] = {}

    # HOME_VISIT: one round trip per unit to the area anchor.
    dist = dur = 0
    unreachable = []
    for area_id in demand_areas:
        out, back = road(base_area_id, area_id), road(area_id, base_area_id)
        if out is None or back is None:
            unreachable.append(area_id)
            continue
        dist += (out[0] + back[0]) * demand[area_id]
        dur += (out[1] + back[1]) * demand[area_id]
    service_min = units * a.home_visit_minutes_per_unit
    modes["HOME_VISIT"] = _mode_result(
        "HOME_VISIT", distance_m=dist, travel_s=dur, service_minutes=service_min,
        costs={"TRAVEL_DISTANCE_COST": dist * km, "TRAVEL_TIME_COST": dur / 60 * staff,
               "STAFF_COST": service_min * staff},
        resident_access_minutes=0.0, served_units=units, unreachable=unreachable,
        care_linkage_possible=True, workday=a.workday_minutes,
        note="주민 이동 없음; 방문 회차가 많아 이동거리가 가장 크게 늘 수 있음",
    )

    # VILLAGE_PICKUP: weekly multi-stop pickup/delivery runs + central processing.
    tour = _tour(base_area_id, demand_areas, road)
    if tour is None:
        modes["VILLAGE_PICKUP"] = _unavailable("VILLAGE_PICKUP", "NO_ROUTE")
    else:
        _, tdist, tdur = tour
        stops = len(demand_areas) * a.pickup_stop_minutes
        run_dist, run_s = tdist * a.pickup_runs_per_month, tdur * a.pickup_runs_per_month
        stop_min = stops * a.pickup_runs_per_month
        modes["VILLAGE_PICKUP"] = _mode_result(
            "VILLAGE_PICKUP", distance_m=run_dist, travel_s=run_s, service_minutes=stop_min,
            costs={"TRAVEL_DISTANCE_COST": run_dist * km, "TRAVEL_TIME_COST": run_s / 60 * staff,
                   "STAFF_COST": stop_min * staff,
                   "SERVICE_EXECUTION_COST": units * a.central_processing_won_per_unit},
            resident_access_minutes=None, served_units=units, unreachable=[],
            care_linkage_possible=True, workday=a.workday_minutes,
            note="마을회관 수거·배달; 주민은 회관까지 이동 필요(가구 수거 시 돌봄 연계 가능)",
        )

    # MOBILE_SERVICE: vehicle tours visiting each demand area a few times a month.
    if tour is None:
        modes["MOBILE_SERVICE"] = _unavailable("MOBILE_SERVICE", "NO_ROUTE")
    else:
        _, tdist, tdur = tour
        runs = a.mobile_visits_per_area_per_month
        on_site = units * a.mobile_minutes_per_unit
        days = math.ceil((tdur / 60 * runs + on_site) / a.workday_minutes) if units else 0
        modes["MOBILE_SERVICE"] = _mode_result(
            "MOBILE_SERVICE", distance_m=tdist * runs, travel_s=tdur * runs,
            service_minutes=on_site,
            costs={"TRAVEL_DISTANCE_COST": tdist * runs * km,
                   "TRAVEL_TIME_COST": tdur * runs / 60 * staff,
                   "STAFF_COST": on_site * staff,
                   "VEHICLE_COST": days * a.mobile_vehicle_won_per_day},
            resident_access_minutes=None, served_units=units, unreachable=[],
            care_linkage_possible=False, workday=a.workday_minutes,
            note="차량 현장 처리; 방문일에 맞춰 주민이 차량 위치로 이동",
        )

    # VILLAGE_HUB: residents travel to selected existing public facilities.
    hubs = select_hubs(areas, road, max_hubs=hub_count,
                       threshold_minutes=a.hub_access_threshold_minutes)
    chosen = next((h for h in hubs if h["hub_count"] == hub_count), None)
    if chosen is None:
        modes["VILLAGE_HUB"] = _unavailable("VILLAGE_HUB", "NO_PUBLIC_FACILITY_CANDIDATE")
    else:
        staff_min = a.hub_staff_hours_per_month * 60 * hub_count
        infrastructure = 0 if a.existing_public_asset else None
        weighted_minutes = chosen["demand_weighted_travel_minutes"]
        modes["VILLAGE_HUB"] = _mode_result(
            "VILLAGE_HUB", distance_m=0, travel_s=0, service_minutes=staff_min,
            costs={"FACILITY_OPERATING_COST": a.hub_operating_won_per_month * hub_count,
                   "STAFF_COST": staff_min * staff,
                   "SERVICE_EXECUTION_COST": units * a.central_processing_won_per_unit,
                   "FIXED_INFRASTRUCTURE_COST": infrastructure},
            resident_access_minutes=round(weighted_minutes / units, 1) if units else 0.0,
            served_units=units, unreachable=[], care_linkage_possible=False,
            workday=a.workday_minutes,
            note="기존 공공시설 활용 가정; 주민 이동시간은 도로 기준 편도(왕복 아님)",
            extra={"hub": chosen},
        )

    return {
        "service_type": "laundry",
        "demand_units_per_month": units,
        "demand_provenance": "SIMULATION (same demand for every mode)",
        "base_area_id": base_area_id,
        "assumptions": a.payload(),
        "modes": modes,
        "hub_candidates": hubs,
        "policy_note": (
            "서비스 방식은 정책 선택입니다. 비용·접근성 차이를 비교할 뿐 우열을 판정하지 않습니다."
        ),
        "reference_cases_note": (
            "KREI 세탁 사례(<표 4-9>)는 CASE_REFERENCE로만 제공되며 "
            "위 가정값에 사용하지 않았습니다."
        ),
    }


def _mode_result(
    mode: str, *, distance_m: int, travel_s: int, service_minutes: float,
    costs: dict[str, float | None], resident_access_minutes: float | None, served_units: int,
    unreachable: list[str], care_linkage_possible: bool, workday: int, note: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    known = {k: round(v) for k, v in costs.items() if v is not None}
    unknown = sorted(k for k, v in costs.items() if v is None)
    staff_minutes = travel_s / 60 + service_minutes
    return {
        "mode": mode,
        "label": SERVICE_MODE_LABELS_KO[mode],
        "status": "AVAILABLE",
        "monthly_cost_breakdown_won": known,
        "unknown_cost_items": unknown,
        "monthly_cost_won": sum(known.values()) if not unknown else None,
        "monthly_cost_known_part_won": sum(known.values()),
        "vehicle_distance_km": round(distance_m / 1000, 1),
        "staff_hours": round(staff_minutes / 60, 1),
        "workdays_needed": math.ceil(staff_minutes / workday) if staff_minutes else 0,
        "served_units": served_units,
        "cost_per_unit_won": (round(sum(known.values()) / served_units)
                              if served_units and not unknown else None),
        "resident_travel_minutes_per_unit": resident_access_minutes,
        "resident_travel_note": (
            "주민 이동 없음" if resident_access_minutes == 0 else
            "주민이 회관/차량 위치까지 이동 (마을 내부 이동은 측정 불가)"
            if resident_access_minutes is None else "도로 기준 거점까지 편도"
        ),
        "unreachable_area_ids": unreachable,
        "care_linkage_possible": care_linkage_possible,
        "note": note,
        "provenance": "MODEL ESTIMATE (Kakao road legs + SIMULATION assumptions)",
        **(extra or {}),
    }


def _unavailable(mode: str, reason: str) -> dict[str, Any]:
    return {"mode": mode, "label": SERVICE_MODE_LABELS_KO[mode], "status": "UNAVAILABLE",
            "reason": reason, "monthly_cost_won": None}
