from __future__ import annotations

import json
from pathlib import Path

from route_fixtures import seed_test_route_cache

from backend.travel import (
    TEST_FIXTURE_ROUTE_SOURCE,
    TEST_FIXTURE_ROUTING_VERSION,
    connect,
    get_cached,
)


def test_synthetic_route_fixture_is_deterministic_and_explicitly_labeled(
    tmp_path: Path, monkeypatch
) -> None:
    demo = json.loads(Path("data/demo.json").read_text(encoding="utf-8"))
    first_path = tmp_path / "route-fixture-a.sqlite"
    second_path = tmp_path / "route-fixture-b.sqlite"
    first = seed_test_route_cache(first_path, demo["areas"])
    second = seed_test_route_cache(second_path, demo["areas"])
    assert first == second
    assert first["source"] == TEST_FIXTURE_ROUTE_SOURCE
    assert first["routing_version"] == TEST_FIXTURE_ROUTING_VERSION
    assert first["area_count"] == len({area["id"] for area in demo["areas"]})
    assert first["route_count"] == first["area_count"] ** 2

    origin, destination = demo["areas"][:2]
    connection = connect(first_path)
    try:
        route = get_cached(connection, origin, destination)
        assert route is not None
        assert route.source == TEST_FIXTURE_ROUTE_SOURCE
    finally:
        connection.close()

    monkeypatch.setenv("VILLAGE_COVERAGE_TEST_ROUTE_FIXTURE", "false")
    connection = connect(first_path)
    try:
        assert get_cached(connection, origin, destination) is None
    finally:
        connection.close()
