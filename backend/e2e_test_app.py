"""Local Playwright app with an explicitly synthetic, server-trusted staff identity.

This entry point is only for isolated browser tests. Production and normal local
servers must continue to use ``backend.main:app`` and its real auth boundary.
"""

from __future__ import annotations

import os


def _synthetic_playwright_staff_roles() -> frozenset[str]:
    """Inject a fake server-side identity only into the disposable test app."""
    return frozenset({"PLANNER", "REVIEWER"})


def _build_app():
    if (
        os.environ.get("VILLAGE_COVERAGE_TEST_MODE") != "true"
        or os.environ.get("VILLAGECOVERAGE_E2E_TEST_AUTH") != "1"
    ):
        raise RuntimeError(
            "The Playwright test app requires explicit test mode and synthetic test auth."
        )

    from backend.authz import authenticated_staff_roles
    from backend.main import _operator_staff_roles, app

    app.dependency_overrides[authenticated_staff_roles] = _synthetic_playwright_staff_roles
    app.dependency_overrides[_operator_staff_roles] = _synthetic_playwright_staff_roles
    return app


app = _build_app()
