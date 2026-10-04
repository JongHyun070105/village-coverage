from scripts.run_replan_benchmark_v5 import (
    _assignment_change_metrics,
    _expected_route_unavailable_block,
)


def test_assignment_change_metrics_are_zero_for_an_unchanged_plan():
    plan = {("provider-a", "area-a", "2026-10-06")}

    assert _assignment_change_metrics(plan, plan) == (0, 0.0)


def test_assignment_change_metrics_count_added_and_removed_assignments():
    previous = {
        ("provider-a", "area-a", "2026-10-06"),
        ("provider-b", "area-b", "2026-10-07"),
    }
    current = {
        ("provider-a", "area-a", "2026-10-06"),
        ("provider-c", "area-c", "2026-10-08"),
    }

    assert _assignment_change_metrics(previous, current) == (2, 1.0)


def test_assignment_change_rate_stays_defined_for_an_empty_baseline():
    assert _assignment_change_metrics(set(), {("provider-a", "area-a", "2026-10-06")}) == (
        1,
        1.0,
    )


def test_expected_route_unavailable_is_a_fail_closed_blocker_not_a_valid_plan():
    missing_route = "provider road route missing for depot-00 and area-000"

    assert _expected_route_unavailable_block(
        "ROUTE_UNAVAILABLE",
        "NOT_VERIFIABLE",
        "NOT_VERIFIABLE",
        missing_route,
        missing_route,
    )


def test_unexpected_replan_failure_is_not_reclassified_as_expected_route_block():
    assert not _expected_route_unavailable_block(
        "BUDGET_MINUS_TEN_PERCENT",
        "NOT_VERIFIABLE",
        "NOT_VERIFIABLE",
        "provider road route missing for depot-00 and area-000",
        "provider road route missing for depot-00 and area-000",
    )
