from __future__ import annotations

import pytest

from backend.routing import optimize_multi_stop_route


def roads_for_two_stops() -> dict[tuple[str, str], tuple[int, int]]:
    return {
        ("base", "base"): (0, 0),
        ("a", "a"): (0, 0),
        ("b", "b"): (0, 0),
        ("base", "a"): (1000, 120),
        ("a", "base"): (1000, 120),
        ("base", "b"): (1000, 120),
        ("b", "base"): (1000, 120),
        ("a", "b"): (500, 60),
        ("b", "a"): (500, 60),
    }


def test_multi_stop_route_uses_directed_road_matrix_and_time_windows() -> None:
    result = optimize_multi_stop_route(
        "base",
        [
            {"area_id": "a", "name": "가마을", "duration_minutes": 60},
            {"area_id": "b", "name": "나마을", "duration_minutes": 60},
        ],
        roads_for_two_stops(),
        available_from="09:00",
        available_until="13:00",
        max_daily_hours=4,
    )

    assert result is not None
    assert [stop["area_id"] for stop in result["stops"]] in (["a", "b"], ["b", "a"])
    assert result["distance_m"] == 2500
    assert result["duration_s"] == 300
    assert result["duration_s"] < 2 * 240
    assert result["stops"][0]["service_start_time"] >= "09:00"
    assert result["stops"][-1]["service_end_time"] <= "13:00"
    assert result["stops"][0]["travel_after_s"] > 0
    assert result["stops"][-1]["travel_after_s"] > 0


def test_multi_stop_route_fails_closed_when_a_directed_road_leg_is_missing() -> None:
    roads = roads_for_two_stops()
    del roads[("a", "b")]
    with pytest.raises(ValueError, match="provider road route missing"):
        optimize_multi_stop_route(
            "base",
            [
                {"area_id": "a", "duration_minutes": 60},
                {"area_id": "b", "duration_minutes": 60},
            ],
            roads,
            available_from="09:00",
            available_until="13:00",
            max_daily_hours=4,
        )


def test_multi_stop_route_returns_no_route_when_service_time_window_does_not_fit() -> None:
    result = optimize_multi_stop_route(
        "base",
        [
            {"area_id": "a", "duration_minutes": 60},
            {"area_id": "b", "duration_minutes": 60},
        ],
        roads_for_two_stops(),
        available_from="09:00",
        available_until="10:30",
        max_daily_hours=2,
    )
    assert result is None
