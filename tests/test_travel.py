from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest

from backend import travel
from backend.travel import Route, calculate_or_cached, connect, get_cached, put_cached


def make_area(area_id: str, longitude: float) -> dict[str, str | float]:
    return {"id": area_id, "anchor_lng": longitude, "anchor_lat": 36.5}


def test_cache_key_includes_routing_option_and_version(monkeypatch) -> None:
    origin = make_area("origin", 126.6)
    destination = make_area("destination", 126.7)
    base = travel.cache_key(origin, destination)

    assert travel.cache_key(origin, destination, "DISTANCE") != base
    monkeypatch.setattr(travel, "ROUTING_VERSION", "kakao-mobility-v2")
    assert travel.cache_key(origin, destination) != base


def test_single_route_retries_with_cached_matrix_priority(monkeypatch) -> None:
    origin = make_area("origin", 126.6)
    destination = make_area("destination", 126.7)
    requests: list[tuple[str, dict[str, str]]] = []

    def fake_http_json(url: str, *, headers: dict[str, str], **kwargs):
        requests.append((url, headers))
        if len(requests) == 1:
            return 503, None
        return 200, {"routes": [{"result_code": 0, "summary": {"distance": 1200, "duration": 90}}]}

    monkeypatch.setattr(travel, "_http_json", fake_http_json)
    monkeypatch.setattr(travel.time, "sleep", lambda _: None)

    route = travel.fetch_single(origin, destination, "unit-test-key")

    assert route == Route("origin", "destination", 1200, 90)
    assert len(requests) == 2
    assert parse_qs(urlparse(requests[0][0]).query)["priority"] == [travel.PRIORITY]


@pytest.mark.parametrize(
    "route_summary",
    [
        {"result_code": 1, "summary": {"distance": 1200, "duration": 90}},
        {"result_code": 0, "summary": {"distance": -1, "duration": 90}},
    ],
)
def test_single_route_rejects_failed_or_negative_route_summaries(
    monkeypatch, route_summary
) -> None:
    origin = make_area("origin", 126.6)
    destination = make_area("destination", 126.7)
    monkeypatch.setattr(travel.time, "sleep", lambda _: None)
    monkeypatch.setattr(
        travel,
        "_http_json",
        lambda *_args, **_kwargs: (
            200,
            {"routes": [route_summary]},
        ),
    )

    assert travel.fetch_single(origin, destination, "unit-test-key") is None


def test_route_cache_is_exact_and_survives_network_failure(tmp_path, monkeypatch) -> None:
    origin = make_area("origin", 126.6)
    destination = make_area("destination", 126.7)
    connection = connect(tmp_path / "routes.sqlite")
    cached = Route("origin", "destination", 1200, 90)
    put_cached(connection, origin, destination, cached)

    def no_network(*_args, **_kwargs):
        raise AssertionError("cached route should be used without a provider request")

    monkeypatch.setattr(travel, "fetch_group", no_network)
    monkeypatch.setattr(travel, "fetch_single", no_network)
    assert calculate_or_cached(connection, origin, destination, "unit-test-key") == cached

    moved_destination = make_area("destination", 126.71)
    assert get_cached(connection, origin, moved_destination) is None
    connection.close()
