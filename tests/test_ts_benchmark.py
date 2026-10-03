import pytest

from backend.ts_benchmark import (
    MODELS,
    evaluate_dataset,
    evaluate_series,
    negative_binomial,
    rolling_origin,
    select_model,
)
from scripts.run_forecast_backtest import synthetic_series

SERIES = [3, 4, 2, 5, 6, 4, 3, 5, 4, 6, 7, 5, 4, 3, 5, 6, 4, 5, 6, 7]


@pytest.mark.parametrize("model", list(MODELS))
def test_no_future_data_leaks_into_any_model(model):
    cutoff = 14
    baseline = {c["cutoff"]: c["prediction"] for c in rolling_origin(SERIES, model)}
    poisoned = SERIES[:cutoff] + [999] * (len(SERIES) - cutoff)
    changed = {c["cutoff"]: c["prediction"] for c in rolling_origin(poisoned, model)}
    for origin in range(12, cutoff + 1):
        assert baseline[origin] == changed[origin], (model, origin)


def test_negative_binomial_only_applies_when_overdispersed():
    assert negative_binomial([5] * 12) is None
    assert negative_binomial([1, 9, 2, 12, 0, 8, 3, 15, 1, 7, 2, 11]) is not None


def test_metrics_are_reported_and_availability_counts_gaps():
    result = evaluate_series(SERIES, "SEASONAL_NAIVE")
    assert result["availability"] < 1.0
    assert result["mae"] is not None and result["coverage_80"] is not None
    assert evaluate_series(SERIES, "NAIVE_LAST")["availability"] == 1.0


def test_selection_is_multi_metric_and_excludes_miscalibrated_intervals():
    models = {
        "LOW_MAE_BAD_INTERVAL": {"availability": 1.0, "mase": 0.1, "relative_bias": 0.0,
                                 "coverage_80": 0.2, "error_stability": 0.1},
        "BALANCED": {"availability": 1.0, "mase": 0.9, "relative_bias": 0.01,
                     "coverage_80": 0.79, "error_stability": 0.3},
    }
    from backend import ts_benchmark

    ts_benchmark.INTERPRETABILITY.setdefault("LOW_MAE_BAD_INTERVAL", 1)
    ts_benchmark.INTERPRETABILITY.setdefault("BALANCED", 1)
    selection = select_model(models)
    assert selection["selected"] == "BALANCED"
    assert selection["excluded"]["LOW_MAE_BAD_INTERVAL"] == "INTERVAL_MISCALIBRATED"


def test_synthetic_dataset_is_seeded_and_deterministic():
    assert synthetic_series() == synthetic_series()
    report = evaluate_dataset(dict(list(synthetic_series().items())[:4]))
    assert set(report["models"]) == set(MODELS)
    assert report["selection"]["policy"]
