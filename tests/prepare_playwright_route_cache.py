"""Copy only the local route cache into an isolated Playwright database."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "village_coverage.sqlite"


def main() -> None:
    destination_path = Path(os.environ["VILLAGE_COVERAGE_DB"])
    if destination_path.resolve() == SOURCE.resolve():
        raise SystemExit("Playwright route database must be isolated from the source cache")
    if not SOURCE.is_file():
        raise SystemExit("Local route cache is required for legacy pilot E2E tests")

    source_uri = f"file:{quote(str(SOURCE))}?mode=ro"
    with sqlite3.connect(source_uri, uri=True) as source:
        tables = {
            row[0]
            for row in source.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        if tables != {"travel_matrix"}:
            raise SystemExit("Playwright source cache must contain only travel_matrix")
        columns = {
            row[1] for row in source.execute('PRAGMA table_info("travel_matrix")')
        }
        required = {
            "cache_key",
            "origin_id",
            "destination_id",
            "origin_x",
            "origin_y",
            "destination_x",
            "destination_y",
            "routing_version",
            "priority",
            "distance_m",
            "duration_s",
            "fetched_at",
        }
        if columns != required:
            raise SystemExit("Playwright source cache has an unexpected schema")
        route_count = source.execute("SELECT COUNT(*) FROM travel_matrix").fetchone()[0]
        route_versions = {
            row[0] for row in source.execute("SELECT DISTINCT routing_version FROM travel_matrix")
        }
        has_demo_routes = any("public-demo" in version.casefold() for version in route_versions)
        if not route_count or has_demo_routes:
            raise SystemExit("Playwright source must contain non-empty non-demo route data")

        destination_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(destination_path) as destination:
            source.backup(destination)
            copied_count = destination.execute("SELECT COUNT(*) FROM travel_matrix").fetchone()[0]
        if copied_count != route_count:
            raise SystemExit("Playwright route cache copy is incomplete")

    print(f"Playwright route cache isolated: {copied_count} rows")


if __name__ == "__main__":
    main()
