"""Keep backend tests independent from developer databases and provider credentials."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
_TEST_ROOT = Path(tempfile.mkdtemp(prefix="village-coverage-pytest-"))
_ROUTE_DB = _TEST_ROOT / "routes.sqlite"
_PUBLIC_DEMO_ROUTE_DB = _TEST_ROOT / "public-demo-routes.sqlite"

for _name in (
    "DATA_GO_KR_SERVICE_KEY",
    "GEMINI_API_KEY",
    "GEMINI_MODEL",
    "KAKAO_REST_API_KEY",
    "KOSIS_API_KEY",
    "NEXT_PUBLIC_KAKAO_MAP_JS_KEY",
    "VILLAGECOVERAGE_APP_DB",
    "VILLAGECOVERAGE_PUBLIC_DEMO_ROUTE_DB",
    "VILLAGE_COVERAGE_DB",
    "VILLAGE_COVERAGE_PUBLIC_DEMO",
    "VILLAGE_COVERAGE_TEST_ROUTE_FIXTURE",
):
    os.environ.pop(_name, None)

os.environ.update(
    {
        "VILLAGE_COVERAGE_DB": str(_ROUTE_DB),
        "VILLAGE_COVERAGE_PUBLIC_DEMO": "false",
        "VILLAGE_COVERAGE_TEST_ROUTE_FIXTURE": "true",
        "VILLAGE_COVERAGE_TEST_MODE": "true",
        "VILLAGECOVERAGE_PUBLIC_DEMO_ROUTE_DB": str(_PUBLIC_DEMO_ROUTE_DB),
        "DATA_GO_KR_SERVICE_KEY": "",
        "GEMINI_API_KEY": "",
        "GEMINI_MODEL": "",
        "KAKAO_REST_API_KEY": "",
        "KOSIS_API_KEY": "",
        "NEXT_PUBLIC_KAKAO_MAP_JS_KEY": "",
    }
)

def _seed_route_fixture() -> dict[str, object]:
    from route_fixtures import seed_test_route_cache

    demo_data = json.loads((ROOT / "data" / "demo.json").read_text(encoding="utf-8"))
    return seed_test_route_cache(_ROUTE_DB, demo_data["areas"])


ROUTE_FIXTURE_INFO = _seed_route_fixture()


@pytest.fixture(autouse=True)
def _isolate_application_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VILLAGECOVERAGE_APP_DB", str(tmp_path / "application.sqlite"))

