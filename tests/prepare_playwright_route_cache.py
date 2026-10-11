"""Create a temporary, explicitly synthetic route cache for standard Playwright tests."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))


def main() -> None:
    from route_fixtures import seed_test_route_cache

    if os.environ.get("VILLAGE_COVERAGE_TEST_ROUTE_FIXTURE", "").casefold() != "true":
        raise SystemExit("Set VILLAGE_COVERAGE_TEST_ROUTE_FIXTURE=true for Playwright test data")
    destination_path = Path(os.environ["VILLAGE_COVERAGE_DB"])
    demo = json.loads((ROOT / "data" / "demo.json").read_text(encoding="utf-8"))
    result = seed_test_route_cache(destination_path, demo["areas"])
    print(
        "Playwright route fixture created: "
        f"source={result['source']} version={result['routing_version']} "
        f"areas={result['area_count']} routes={result['route_count']} "
        f"sha256={result['fingerprint_sha256']}"
    )


if __name__ == "__main__":
    main()
