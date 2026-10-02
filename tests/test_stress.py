"""Fast CI smoke test for scenario stress testing and invariants (§11, §33)."""

from __future__ import annotations

from scripts.run_stress_tests import REFERENCE_SEED, run_single_stress_test


def test_quick_synthetic_stress_scenario_invariants(tmp_path) -> None:
    """Run a fast small scenario (16 areas, 3 providers, variant A) with tight time limit."""
    record = run_single_stress_test(
        num_areas=16,
        num_providers=3,
        variant="A",
        seed=REFERENCE_SEED,
        temp_dir=tmp_path,
        max_solver_seconds=1.5,
    )
    assert record["status"] == "PASS", f"Stress invariants violated: {record['violations']}"
    assert record["invariants_passed"] is True
    assert record["budget_spent_won"] <= record["budget_won"]
    assert record["covered_areas"] > 0
    assert record["solver_status"] in {"OPTIMAL", "FEASIBLE", "TIME_LIMIT"}
