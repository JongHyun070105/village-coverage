from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "overrides",
    [
        {},
        {"VILLAGE_COVERAGE_TEST_MODE": "true"},
        {"VILLAGECOVERAGE_E2E_TEST_AUTH": "1"},
    ],
)
def test_playwright_test_auth_requires_both_explicit_test_flags(overrides):
    environment = os.environ.copy()
    environment.pop("VILLAGE_COVERAGE_TEST_MODE", None)
    environment.pop("VILLAGECOVERAGE_E2E_TEST_AUTH", None)
    environment.update(overrides)

    result = subprocess.run(
        [sys.executable, "-c", "import backend.e2e_test_app"],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "requires explicit test mode and synthetic test auth" in result.stderr
