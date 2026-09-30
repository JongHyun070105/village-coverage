"""Local SQLite cache and provider integration for road travel metrics."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.api_smoke_test import _load_config

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = Path(_load_config("VILLAGE_COVERAGE_DB") or ROOT / "data" / "village_coverage.sqlite")
DESTINATIONS_URL = "https://apis-navi.kakaomobility.com/v1/destinations/directions"
DIRECTIONS_URL = "https://apis-navi.kakaomobility.com/v1/directions"
ROUTING_VERSION = "kakao-mobility-destinations-v1"
PRIORITY = "TIME"


@dataclass(frozen=True)
class Route:
    origin_id: str
    destination_id: str
    distance_m: int
    duration_s: int
    source: str = "Kakao Mobility road route"


def connect(path: Path | str = DB_PATH) -> sqlite3.Connection:
    db_path = Path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute(
        """CREATE TABLE IF NOT EXISTS travel_matrix (
            cache_key TEXT PRIMARY KEY,
            origin_id TEXT NOT NULL,
            destination_id TEXT NOT NULL,
            origin_x REAL NOT NULL,
            origin_y REAL NOT NULL,
            destination_x REAL NOT NULL,
            destination_y REAL NOT NULL,
            routing_version TEXT NOT NULL,
            priority TEXT NOT NULL,
            distance_m INTEGER NOT NULL CHECK(distance_m >= 0),
            duration_s INTEGER NOT NULL CHECK(duration_s >= 0),
            fetched_at TEXT NOT NULL
        )"""
    )
    connection.commit()
    return connection


def cache_key(origin: dict[str, Any], destination: dict[str, Any], priority: str = PRIORITY) -> str:
    material = {
        "origin_id": origin["id"],
        "origin_x": round(float(origin["anchor_lng"]), 7),
        "origin_y": round(float(origin["anchor_lat"]), 7),
        "destination_id": destination["id"],
        "destination_x": round(float(destination["anchor_lng"]), 7),
        "destination_y": round(float(destination["anchor_lat"]), 7),
        "routing_version": ROUTING_VERSION,
        "priority": priority,
    }
    return hashlib.sha256(json.dumps(material, sort_keys=True).encode()).hexdigest()


def get_cached(
    connection: sqlite3.Connection, origin: dict[str, Any], destination: dict[str, Any]
) -> Route | None:
    row = connection.execute(
        "SELECT distance_m, duration_s FROM travel_matrix WHERE cache_key = ?",
        (cache_key(origin, destination),),
    ).fetchone()
    if row is None:
        return None
    return Route(origin["id"], destination["id"], int(row[0]), int(row[1]))


def put_cached(
    connection: sqlite3.Connection,
    origin: dict[str, Any],
    destination: dict[str, Any],
    route: Route,
) -> None:
    connection.execute(
        """INSERT INTO travel_matrix (
            cache_key, origin_id, destination_id, origin_x, origin_y,
            destination_x, destination_y, routing_version, priority,
            distance_m, duration_s, fetched_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(cache_key) DO UPDATE SET
            distance_m = excluded.distance_m,
            duration_s = excluded.duration_s,
            fetched_at = excluded.fetched_at""",
        (
            cache_key(origin, destination),
            origin["id"],
            destination["id"],
            float(origin["anchor_lng"]),
            float(origin["anchor_lat"]),
            float(destination["anchor_lng"]),
            float(destination["anchor_lat"]),
            ROUTING_VERSION,
            PRIORITY,
            route.distance_m,
            route.duration_s,
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    connection.commit()


def _http_json(
    url: str, *, headers: dict[str, str], body: bytes | None = None, timeout: int = 20
) -> tuple[int | None, dict[str, Any] | None]:
    request = urllib.request.Request(
        url, data=body, headers=headers, method="POST" if body is not None else "GET"
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read())
            return response.status, payload if isinstance(payload, dict) else None
    except urllib.error.HTTPError as error:
        return error.code, None
    except Exception:
        return None, None


def fetch_group(
    origin: dict[str, Any], destinations: list[dict[str, Any]], api_key: str
) -> dict[str, Route]:
    if not destinations:
        return {}
    request_body = {
        "origin": {"x": str(origin["anchor_lng"]), "y": str(origin["anchor_lat"])},
        "destinations": [
            {"key": item["id"], "x": str(item["anchor_lng"]), "y": str(item["anchor_lat"])}
            for item in destinations
        ],
        "radius": 10000,
        "priority": PRIORITY,
    }
    headers = {
        "Authorization": f"KakaoAK {api_key}",
        "Content-Type": "application/json",
        "User-Agent": "VillageCoverage-pre-rnd/0.1",
    }
    status: int | None = None
    payload: dict[str, Any] | None = None
    for attempt in range(2):
        status, payload = _http_json(
            DESTINATIONS_URL, headers=headers, body=json.dumps(request_body).encode()
        )
        if status == 200 and payload:
            break
        if attempt == 0:
            time.sleep(0.35)
    if status != 200 or not payload:
        return {}
    results: dict[str, Route] = {}
    for item in payload.get("routes", []):
        if not isinstance(item, dict) or item.get("result_code") != 0:
            continue
        summary = item.get("summary")
        destination_id = str(item.get("key", ""))
        if not isinstance(summary, dict):
            continue
        try:
            distance, duration = int(summary["distance"]), int(summary["duration"])
        except (KeyError, TypeError, ValueError):
            continue
        if distance < 0 or duration < 0:
            continue
        results[destination_id] = Route(origin["id"], destination_id, distance, duration)
    return results


def fetch_single(origin: dict[str, Any], destination: dict[str, Any], api_key: str) -> Route | None:
    params = {
        "origin": f"{origin['anchor_lng']},{origin['anchor_lat']}",
        "destination": f"{destination['anchor_lng']},{destination['anchor_lat']}",
        "priority": PRIORITY,
        "summary": "true",
    }
    url = f"{DIRECTIONS_URL}?{urllib.parse.urlencode(params)}"
    headers = {
        "Authorization": f"KakaoAK {api_key}",
        "Content-Type": "application/json",
        "User-Agent": "VillageCoverage-pre-rnd/0.1",
    }
    for attempt in range(2):
        status, payload = _http_json(url, headers=headers)
        routes = payload.get("routes", []) if payload else []
        route = routes[0] if routes and isinstance(routes[0], dict) else {}
        summary = route.get("summary", {}) if isinstance(route, dict) else {}
        try:
            distance = int(summary["distance"])
            duration = int(summary["duration"])
            if status == 200 and route.get("result_code") == 0 and distance >= 0 and duration >= 0:
                return Route(origin["id"], destination["id"], distance, duration)
        except (KeyError, TypeError, ValueError):
            pass
        if attempt == 0:
            time.sleep(0.35)
    return None


def calculate_or_cached(
    connection: sqlite3.Connection,
    origin: dict[str, Any],
    destination: dict[str, Any],
    api_key: str,
) -> Route | None:
    cached = get_cached(connection, origin, destination)
    if cached:
        return cached
    fresh = fetch_group(origin, [destination], api_key).get(destination["id"])
    if fresh is None:
        fresh = fetch_single(origin, destination, api_key)
    if fresh is not None:
        put_cached(connection, origin, destination, fresh)
        return fresh
    # Failure fallback is deliberately exact-key only; no straight-line substitution.
    return get_cached(connection, origin, destination)


def matrix_summary(connection: sqlite3.Connection) -> dict[str, Any]:
    row = connection.execute(
        "SELECT COUNT(*), MAX(fetched_at), COUNT(DISTINCT origin_id) FROM travel_matrix"
    ).fetchone()
    return {"route_count": int(row[0]), "latest_fetch": row[1], "origin_count": int(row[2])}
