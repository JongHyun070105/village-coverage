"""Deterministic test-only route cache data with explicit synthetic provenance."""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any

from backend.travel import (
    TEST_FIXTURE_ROUTE_SOURCE,
    TEST_FIXTURE_ROUTING_VERSION,
    cache_key,
    connect,
)

TEST_FIXTURE_TIMESTAMP = "2000-01-01T00:00:00+00:00"


def seed_test_route_cache(
    destination: Path | str, areas: list[dict[str, Any]]
) -> dict[str, Any]:
    """Create a new isolated SQLite file and seed deterministic synthetic route edges."""
    destination_path = Path(destination).expanduser().resolve()
    temp_root = Path(tempfile.gettempdir()).resolve()
    if destination_path == temp_root or temp_root not in destination_path.parents:
        raise ValueError("test route fixtures must be written below the system temporary directory")

    unique_areas: dict[str, dict[str, Any]] = {}
    for area in areas:
        area_id = str(area["id"])
        current = unique_areas.get(area_id)
        if current is not None and (
            float(current["anchor_lng"]) != float(area["anchor_lng"])
            or float(current["anchor_lat"]) != float(area["anchor_lat"])
        ):
            raise ValueError(f"conflicting coordinates for test area {area_id}")
        unique_areas[area_id] = area
    ordered_areas = [unique_areas[area_id] for area_id in sorted(unique_areas)]
    if not ordered_areas:
        raise ValueError("test route fixture requires at least one area")

    destination_path.parent.mkdir(parents=True, exist_ok=True)
    with destination_path.open("xb"):
        pass

    connection = connect(destination_path)
    try:
        rows = []
        for origin_index, origin in enumerate(ordered_areas):
            for destination_index, target in enumerate(ordered_areas):
                if origin_index == destination_index:
                    distance_m = duration_s = 0
                else:
                    material = f"{origin['id']}\0{target['id']}".encode("utf-8")
                    deterministic_value = int.from_bytes(
                        hashlib.sha256(material).digest()[:4], "big"
                    )
                    distance_m = 1_000 + deterministic_value % 9_000
                    duration_s = max(60, round(distance_m / 8.33))
                rows.append(
                    (
                        cache_key(origin, target),
                        str(origin["id"]),
                        str(target["id"]),
                        float(origin["anchor_lng"]),
                        float(origin["anchor_lat"]),
                        float(target["anchor_lng"]),
                        float(target["anchor_lat"]),
                        TEST_FIXTURE_ROUTING_VERSION,
                        "TIME",
                        distance_m,
                        duration_s,
                        TEST_FIXTURE_TIMESTAMP,
                    )
                )
        connection.executemany(
            """INSERT INTO travel_matrix (
                cache_key, origin_id, destination_id, origin_x, origin_y,
                destination_x, destination_y, routing_version, priority,
                distance_m, duration_s, fetched_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            rows,
        )
        connection.commit()
        fingerprint_material = json.dumps(rows, separators=(",", ":"), ensure_ascii=False)
        return {
            "source": TEST_FIXTURE_ROUTE_SOURCE,
            "routing_version": TEST_FIXTURE_ROUTING_VERSION,
            "area_count": len(ordered_areas),
            "route_count": len(rows),
            "fingerprint_sha256": hashlib.sha256(fingerprint_material.encode("utf-8")).hexdigest(),
        }
    finally:
        connection.close()
