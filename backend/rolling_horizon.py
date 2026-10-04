"""Rolling-horizon configuration and explicit state carryover for provider schedules."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any


@dataclass(frozen=True)
class RollingHorizonConfig:
    planning_window_days: int = 28
    commit_window_days: int = 7
    lookahead_days: int = 21

    def __post_init__(self) -> None:
        if self.planning_window_days < 1:
            raise ValueError("planning_window_days must be positive")
        if self.commit_window_days < 1:
            raise ValueError("commit_window_days must be positive")
        if self.lookahead_days < 0:
            raise ValueError("lookahead_days cannot be negative")
        if self.commit_window_days + self.lookahead_days != self.planning_window_days:
            raise ValueError("commit_window_days + lookahead_days must equal planning_window_days")


@dataclass(frozen=True)
class RollingHorizonState:
    remaining_budget_won: int
    remaining_area_demand: dict[str, int]
    remaining_minimum_obligations: dict[str, int]
    provider_month_rounds_committed: dict[str, dict[str, int]]
    provider_month_hours_committed: dict[str, dict[str, float]]
    provider_month_service_cost_committed: dict[str, dict[str, int]]
    already_served_area_ids: tuple[str, ...]
    days_since_last_service: dict[str, int | None]
    minimum_obligation_reserve_won: int = 0
    as_of_date: date | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "remaining_budget_won": self.remaining_budget_won,
            "remaining_area_demand": dict(self.remaining_area_demand),
            "remaining_minimum_obligations": dict(self.remaining_minimum_obligations),
            "provider_month_rounds_committed": {
                key: dict(value) for key, value in self.provider_month_rounds_committed.items()
            },
            "provider_month_hours_committed": {
                key: dict(value) for key, value in self.provider_month_hours_committed.items()
            },
            "provider_month_service_cost_committed": {
                key: dict(value)
                for key, value in self.provider_month_service_cost_committed.items()
            },
            "already_served_area_ids": list(self.already_served_area_ids),
            "days_since_last_service": dict(self.days_since_last_service),
            "minimum_obligation_reserve_won": self.minimum_obligation_reserve_won,
            "as_of_date": self.as_of_date.isoformat() if self.as_of_date else None,
        }


def initial_rolling_state(
    areas: list[dict[str, Any]],
    budget_won: int,
    minimum_services_per_area: int,
    *,
    as_of_date: date | None = None,
) -> RollingHorizonState:
    return RollingHorizonState(
        remaining_budget_won=max(0, int(budget_won)),
        remaining_area_demand={
            str(area["id"]): max(0, int(area.get("simulated_monthly_demand", 0)))
            for area in areas
        },
        remaining_minimum_obligations={
            str(area["id"]): max(
                0,
                int(area.get("minimum_services_remaining", minimum_services_per_area)),
            )
            for area in areas
        },
        provider_month_rounds_committed={},
        provider_month_hours_committed={},
        provider_month_service_cost_committed={},
        already_served_area_ids=(),
        days_since_last_service={
            str(area["id"]): (
                max(0, int(area["days_since_last_service"]))
                if area.get("days_since_last_service") is not None
                else None
            )
            for area in areas
        },
        as_of_date=as_of_date,
    )


def advance_rolling_state(
    state: RollingHorizonState,
    committed_rounds: list[dict[str, Any]],
    *,
    window_end: date,
    provider_month_compensation_floor_won: dict[tuple[str, str], int] | None = None,
    minimum_obligation_reserve_won: int = 0,
) -> RollingHorizonState:
    """Carry budget, area obligations, provider use, service history and reserve forward."""
    area_demand = dict(state.remaining_area_demand)
    obligations = dict(state.remaining_minimum_obligations)
    provider_rounds = {
        provider_id: dict(months)
        for provider_id, months in state.provider_month_rounds_committed.items()
    }
    provider_hours = {
        provider_id: dict(months)
        for provider_id, months in state.provider_month_hours_committed.items()
    }
    provider_service_cost = {
        provider_id: dict(months)
        for provider_id, months in state.provider_month_service_cost_committed.items()
    }
    days_since = dict(state.days_since_last_service)
    served = set(state.already_served_area_ids)
    travel_spend = 0
    incremental_provider_pay = 0
    new_service_cost: dict[tuple[str, str], int] = {}
    rounds_by_area: dict[str, int] = {}
    units_by_area: dict[str, int] = {}
    latest_service: dict[str, date] = {}
    for round_item in committed_rounds:
        area_id = str(round_item["area_id"])
        provider_id = str(round_item["provider_id"])
        scheduled_date = date.fromisoformat(str(round_item["scheduled_date"]))
        month = scheduled_date.strftime("%Y-%m")
        provider_rounds.setdefault(provider_id, {})[month] = (
            provider_rounds.setdefault(provider_id, {}).get(month, 0) + 1
        )
        provider_hours.setdefault(provider_id, {})[month] = (
            provider_hours.setdefault(provider_id, {}).get(month, 0.0)
            + max(0, int(round_item.get("estimated_work_minutes", 0))) / 60.0
        )
        service_cost = max(0, int(round_item.get("service_cost_won", 0)))
        key = (provider_id, month)
        new_service_cost[key] = new_service_cost.get(key, 0) + service_cost
        rounds_by_area[area_id] = rounds_by_area.get(area_id, 0) + 1
        units_by_area[area_id] = units_by_area.get(area_id, 0) + max(
            0, int(round_item.get("service_units", 0))
        )
        latest_service[area_id] = max(latest_service.get(area_id, scheduled_date), scheduled_date)
        travel_spend += max(0, int(round_item.get("travel_cost_won", 0)))
        served.add(area_id)

    for (provider_id, month), service_cost in new_service_cost.items():
        prior_service_cost = provider_service_cost.setdefault(provider_id, {}).get(month, 0)
        floor = max(
            0,
            int((provider_month_compensation_floor_won or {}).get((provider_id, month), 0)),
        )
        prior_pay = max(prior_service_cost, floor) if prior_service_cost else 0
        new_pay = max(prior_service_cost + service_cost, floor)
        incremental_provider_pay += max(0, new_pay - prior_pay)
        provider_service_cost[provider_id][month] = prior_service_cost + service_cost

    for area_id, units in units_by_area.items():
        area_demand[area_id] = max(0, area_demand.get(area_id, 0) - units)
        obligations[area_id] = max(0, obligations.get(area_id, 0) - rounds_by_area[area_id])
    for area_id, current_days in days_since.items():
        if current_days is None:
            continue
        last_service = latest_service.get(area_id)
        days_since[area_id] = (
            max(0, (window_end - last_service).days)
            if last_service is not None
            else current_days + max(0, (window_end - state.as_of_date).days)
            if state.as_of_date is not None
            else current_days
        )

    spend = travel_spend + incremental_provider_pay
    remaining_budget = max(0, state.remaining_budget_won - spend)
    return RollingHorizonState(
        remaining_budget_won=remaining_budget,
        remaining_area_demand=area_demand,
        remaining_minimum_obligations=obligations,
        provider_month_rounds_committed=provider_rounds,
        provider_month_hours_committed=provider_hours,
        provider_month_service_cost_committed=provider_service_cost,
        already_served_area_ids=tuple(sorted(served)),
        days_since_last_service=days_since,
        minimum_obligation_reserve_won=min(
            remaining_budget, max(0, int(minimum_obligation_reserve_won))
        ),
        as_of_date=window_end,
    )
