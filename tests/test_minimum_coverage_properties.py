from hypothesis import given, settings
from hypothesis import strategies as st

from backend.minimum_coverage import binary_search_minimum_budget


@settings(max_examples=80, deadline=None)
@given(
    threshold=st.integers(min_value=0, max_value=900_000),
    tolerance=st.integers(min_value=1, max_value=50_000),
    max_probes=st.integers(min_value=1, max_value=24),
)
def test_binary_search_never_claims_a_minimum_below_a_monotone_threshold(
    threshold: int, tolerance: int, max_probes: int
) -> None:
    def probe(budget: int) -> dict:
        return {
            "minimum_coverage_met": budget >= threshold,
            "solver_status": "OPTIMAL",
            "optimality_proven": True,
        }

    result = binary_search_minimum_budget(
        probe,
        lower_won=0,
        upper_won=1_000_000,
        tolerance_won=tolerance,
        max_probes=max_probes,
    )

    assert result["upper_bound_won"] >= threshold
    if result["status"] == "FOUND_WITHIN_TOLERANCE":
        assert result["minimum_budget_won"] >= threshold
        assert result["minimum_budget_won"] - threshold <= tolerance
        assert result["search_limit_reached"] is False
    else:
        assert result["status"] == "UPPER_BOUND_ONLY"
        assert result["minimum_budget_won"] is None


def test_search_limit_does_not_turn_a_wide_interval_into_a_proven_minimum() -> None:
    result = binary_search_minimum_budget(
        lambda budget: {
            "minimum_coverage_met": budget >= 333_333,
            "solver_status": "OPTIMAL",
            "optimality_proven": True,
        },
        lower_won=0,
        upper_won=1_000_000,
        tolerance_won=1,
        max_probes=1,
    )

    assert result["status"] == "UPPER_BOUND_ONLY"
    assert result["minimum_budget_won"] is None
    assert result["search_limit_reached"] is True
