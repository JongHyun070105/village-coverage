from scripts.run_replan_benchmark_v5 import _assignment_change_metrics


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
