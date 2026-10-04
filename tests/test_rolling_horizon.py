from datetime import date

import pytest

from backend.rolling_horizon import (
    RollingHorizonConfig,
    advance_rolling_state,
    initial_rolling_state,
)


def test_rolling_state_carries_budget_capacity_service_and_history():
    state = initial_rolling_state(
        [
            {
                "id": "area-a",
                "simulated_monthly_demand": 3,
                "minimum_services_remaining": 2,
                "days_since_last_service": 40,
            }
        ],
        budget_won=50_000,
        minimum_services_per_area=1,
        as_of_date=date(2026, 10, 1),
    )

    next_state = advance_rolling_state(
        state,
        [
            {
                "area_id": "area-a",
                "provider_id": "provider-a",
                "scheduled_date": "2026-10-03",
                "service_units": 1,
                "service_cost_won": 8_000,
                "travel_cost_won": 1_000,
                "estimated_work_minutes": 60,
            }
        ],
        window_end=date(2026, 10, 7),
        provider_month_compensation_floor_won={("provider-a", "2026-10"): 10_000},
        minimum_obligation_reserve_won=8_000,
    )

    assert next_state.remaining_budget_won == 39_000
    assert next_state.remaining_area_demand["area-a"] == 2
    assert next_state.remaining_minimum_obligations["area-a"] == 1
    assert next_state.provider_month_rounds_committed == {"provider-a": {"2026-10": 1}}
    assert next_state.provider_month_hours_committed == {"provider-a": {"2026-10": 1.0}}
    assert next_state.provider_month_service_cost_committed == {
        "provider-a": {"2026-10": 8_000}
    }
    assert next_state.already_served_area_ids == ("area-a",)
    assert next_state.days_since_last_service["area-a"] == 4
    assert next_state.as_of_date == date(2026, 10, 7)


def test_rolling_state_reserves_monthly_compensation_once_across_commits():
    state = initial_rolling_state(
        [{"id": "area-a", "simulated_monthly_demand": 3}],
        budget_won=50_000,
        minimum_services_per_area=1,
        as_of_date=date(2026, 10, 1),
    )
    first = advance_rolling_state(
        state,
        [
            {
                "area_id": "area-a",
                "provider_id": "provider-a",
                "scheduled_date": "2026-10-02",
                "service_units": 1,
                "service_cost_won": 8_000,
                "travel_cost_won": 1_000,
            }
        ],
        window_end=date(2026, 10, 7),
        provider_month_compensation_floor_won={("provider-a", "2026-10"): 10_000},
    )
    second = advance_rolling_state(
        first,
        [
            {
                "area_id": "area-a",
                "provider_id": "provider-a",
                "scheduled_date": "2026-10-09",
                "service_units": 1,
                "service_cost_won": 8_000,
                "travel_cost_won": 1_000,
            }
        ],
        window_end=date(2026, 10, 14),
        provider_month_compensation_floor_won={("provider-a", "2026-10"): 10_000},
    )

    assert first.remaining_budget_won == 39_000
    assert second.remaining_budget_won == 32_000
    assert second.provider_month_service_cost_committed["provider-a"]["2026-10"] == 16_000


@pytest.mark.parametrize(
    "config",
    [
        RollingHorizonConfig(28, 7, 21),
        RollingHorizonConfig(21, 7, 14),
        RollingHorizonConfig(28, 14, 14),
    ],
)
def test_rolling_configuration_covers_commit_plus_lookahead(config):
    assert config.commit_window_days + config.lookahead_days == config.planning_window_days


def test_rolling_configuration_rejects_commit_window_without_lookahead():
    with pytest.raises(ValueError, match="equal"):
        RollingHorizonConfig(28, 7, 14)
