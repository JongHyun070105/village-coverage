from scripts.run_policy_sensitivity import (
    CURRENT_DEFAULTS,
    DIMENSIONS,
    SENSITIVITY_CENTER,
    policy_grid,
)


def test_policy_grid_preserves_ui_default_and_tests_symmetric_center_perturbations() -> None:
    rows = policy_grid()
    by_name = {name: weights for name, *weights in rows}

    assert len(rows) == 22
    assert by_name["baseline_default"] == list(CURRENT_DEFAULTS)
    assert by_name["sensitivity_center"] == list(SENSITIVITY_CENTER)
    assert all(0 <= value <= 1000 for _name, *weights in rows for value in weights)

    for dimension_index, dimension in enumerate(DIMENSIONS):
        for percent in (-20, -10, -5, 5, 10, 20):
            name = f"center_{dimension}_{percent:+d}pct"
            expected = list(SENSITIVITY_CENTER)
            expected[dimension_index] = round(expected[dimension_index] * (100 + percent) / 100)
            assert by_name[name] == expected
