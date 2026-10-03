"""Interpretable time-series baselines and rolling-origin evaluation (V4 §21-§23, §65).

Every model receives only the history strictly before the forecast origin
(``series[:cutoff]``). Datasets are evaluated separately; results are never
pooled across synthetic, external-operational, and local data.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Callable, Sequence
from typing import Any

from backend.stats_dist import negbin_quantiles, poisson_quantiles

Prediction = tuple[float, float, float] | None  # (point, p10, p90)
LOOKBACK = 6
SEASON = 12
ALPHA = 0.3
INTERVAL = (0.1, 0.9)  # nominal 80% central interval

# Ordinal interpretability (5 = explainable in one sentence to a planner).
INTERPRETABILITY = {
    "NAIVE_LAST": 5,
    "SEASONAL_NAIVE": 5,
    "ROLLING_MEDIAN": 5,
    "POISSON_BASELINE": 4,
    "EXPONENTIAL_SMOOTHING": 4,
    "NEGATIVE_BINOMIAL": 3,
    "GAMMA_POISSON_BAYES": 3,
}
MODEL_DESCRIPTIONS_KO = {
    "NAIVE_LAST": "직전 달 값을 그대로 사용",
    "SEASONAL_NAIVE": "작년 같은 달 값을 사용",
    "ROLLING_MEDIAN": "최근 6개월 중앙값",
    "POISSON_BASELINE": "최근 6개월 평균의 포아송 범위",
    "EXPONENTIAL_SMOOTHING": "최근 값에 더 큰 가중치를 둔 평활 평균 (α=0.3)",
    "NEGATIVE_BINOMIAL": "과산포(분산>평균)일 때만 음이항 범위",
    "GAMMA_POISSON_BAYES": "초기 구간 평균을 약한 사전값으로 둔 감마-포아송 갱신",
}


def _empirical_interval(point: float, residuals: Sequence[float]) -> tuple[float, float]:
    if len(residuals) < 3:
        return max(0.0, point), point
    ordered = sorted(residuals)
    lo = ordered[max(0, math.floor(INTERVAL[0] * (len(ordered) - 1)))]
    hi = ordered[min(len(ordered) - 1, math.ceil(INTERVAL[1] * (len(ordered) - 1)))]
    return max(0.0, point + lo), max(0.0, point + hi)


def _one_step_residuals(history: Sequence[float], predictor: Callable[[Sequence[float]], float],
                        minimum: int) -> list[float]:
    return [history[t] - predictor(history[:t]) for t in range(minimum, len(history))]


def naive_last(history: Sequence[float]) -> Prediction:
    if len(history) < 2:
        return None
    point = float(history[-1])
    lo, hi = _empirical_interval(point, _one_step_residuals(history, lambda h: h[-1], 1))
    return point, lo, hi


def seasonal_naive(history: Sequence[float]) -> Prediction:
    if len(history) < SEASON + 1:
        return None
    point = float(history[-SEASON])
    residuals = _one_step_residuals(history, lambda h: h[-SEASON], SEASON)
    lo, hi = _empirical_interval(point, residuals)
    return point, lo, hi


def rolling_median(history: Sequence[float]) -> Prediction:
    if len(history) < LOOKBACK:
        return None

    def predictor(h: Sequence[float]) -> float:
        return float(statistics.median(h[-LOOKBACK:]))

    point = predictor(history)
    lo, hi = _empirical_interval(point, _one_step_residuals(history, predictor, LOOKBACK))
    return point, lo, hi


def _ses_level(h: Sequence[float]) -> float:
    level = float(h[0])
    for value in h[1:]:
        level = ALPHA * float(value) + (1 - ALPHA) * level
    return level


def exponential_smoothing(history: Sequence[float]) -> Prediction:
    if len(history) < LOOKBACK:
        return None
    point = _ses_level(history)
    lo, hi = _empirical_interval(point, _one_step_residuals(history, _ses_level, 2))
    return point, lo, hi


def poisson_baseline(history: Sequence[float]) -> Prediction:
    if len(history) < LOOKBACK:
        return None
    mean = statistics.fmean(history[-LOOKBACK:])
    lo, _, hi = poisson_quantiles(mean, (INTERVAL[0], 0.5, INTERVAL[1]))
    return mean, float(lo), float(hi)


def negative_binomial(history: Sequence[float]) -> Prediction:
    window = list(history[-SEASON:])
    if len(window) < LOOKBACK:
        return None
    mean = statistics.fmean(window)
    variance = statistics.variance(window)
    if mean <= 0 or variance <= mean:
        return None  # not overdispersed: NB is not applicable
    shape = mean * mean / (variance - mean)
    rate = shape / mean
    lo, _, hi = negbin_quantiles(shape, rate, (INTERVAL[0], 0.5, INTERVAL[1]))
    return mean, float(lo), float(hi)


def gamma_poisson_bayes(history: Sequence[float]) -> Prediction:
    if len(history) < LOOKBACK:
        return None
    # Weak prior: first LOOKBACK months' mean as one pseudo-month; update with recent window.
    prior_mean = statistics.fmean(history[:LOOKBACK])
    recent = list(history[-LOOKBACK:])
    shape = max(prior_mean, 0.5) * 1.0 + sum(recent)
    rate = 1.0 + len(recent)
    lo, _, hi = negbin_quantiles(shape, rate, (INTERVAL[0], 0.5, INTERVAL[1]))
    return shape / rate, float(lo), float(hi)


MODELS: dict[str, Callable[[Sequence[float]], Prediction]] = {
    "NAIVE_LAST": naive_last,
    "SEASONAL_NAIVE": seasonal_naive,
    "ROLLING_MEDIAN": rolling_median,
    "EXPONENTIAL_SMOOTHING": exponential_smoothing,
    "POISSON_BASELINE": poisson_baseline,
    "NEGATIVE_BINOMIAL": negative_binomial,
    "GAMMA_POISSON_BAYES": gamma_poisson_bayes,
}


def rolling_origin(series: Sequence[float], model: str, min_train: int = 12) -> list[dict]:
    fn = MODELS[model]
    cases = []
    for cutoff in range(min_train, len(series)):
        history = list(series[:cutoff])  # strictly before the origin: no leakage
        prediction = fn(history)
        cases.append({
            "cutoff": cutoff,
            "actual": float(series[cutoff]),
            "prediction": prediction,
            "scale_history": history,
        })
    return cases


def _mase_scale(history: Sequence[float]) -> float | None:
    diffs = [abs(b - a) for a, b in zip(history, history[1:], strict=False)]
    scale = statistics.fmean(diffs) if diffs else 0.0
    return scale if scale > 0 else None


def evaluate_series(series: Sequence[float], model: str, min_train: int = 12) -> dict[str, Any]:
    cases = rolling_origin(series, model, min_train)
    made = [c for c in cases if c["prediction"] is not None]
    scale = _mase_scale(series[:min_train])
    errors = [c["prediction"][0] - c["actual"] for c in made]
    abs_errors = [abs(e) for e in errors]
    actual_sum = sum(abs(c["actual"]) for c in made)
    covered = [c["prediction"][1] <= c["actual"] <= c["prediction"][2] for c in made]
    widths = [c["prediction"][2] - c["prediction"][1] for c in made]
    level = statistics.fmean(abs(c["actual"]) for c in made) if made else None
    return {
        "cases": len(cases),
        "predictions": len(made),
        "availability": round(len(made) / len(cases), 4) if cases else 0.0,
        "mae": round(statistics.fmean(abs_errors), 4) if made else None,
        "mase": round(statistics.fmean(abs_errors) / scale, 4) if made and scale else None,
        "wape": round(sum(abs_errors) / actual_sum, 4) if made and actual_sum > 0 else None,
        "bias": round(statistics.fmean(errors), 4) if made else None,
        "relative_bias": round(statistics.fmean(errors) / level, 4) if made and level else None,
        "coverage_80": round(sum(covered) / len(covered), 4) if made else None,
        "mean_interval_width": round(statistics.fmean(widths), 4) if made else None,
        "relative_interval_width": (round(statistics.fmean(widths) / level, 4)
                                    if made and level else None),
        "error_stability": round(statistics.pstdev(abs_errors) / scale, 4)
        if len(made) > 1 and scale else None,
    }


def _mean(values: list[float | None]) -> float | None:
    present = [v for v in values if v is not None]
    return round(statistics.fmean(present), 4) if present else None


def evaluate_dataset(series_by_id: dict[str, Sequence[float]], min_train: int = 12
                     ) -> dict[str, Any]:
    models: dict[str, Any] = {}
    for model in MODELS:
        per_series = {sid: evaluate_series(s, model, min_train) for sid, s in series_by_id.items()
                      if len(s) > min_train}
        keys = ("availability", "mae", "mase", "wape", "bias", "relative_bias", "coverage_80",
                "mean_interval_width", "relative_interval_width", "error_stability")
        models[model] = {
            "series_evaluated": len(per_series),
            **{key: _mean([m[key] for m in per_series.values()]) for key in keys},
            "interpretability": INTERPRETABILITY[model],
            "description_ko": MODEL_DESCRIPTIONS_KO[model],
        }
    return {"models": models, "selection": select_model(models)}


def select_model(models: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Multi-metric selection; never 'lowest MAE wins'.

    Eligibility: availability >= 0.8 and 80% interval coverage within [0.6, 0.95].
    Among eligible models: rank on MASE, |relative bias|, |coverage-0.8|, error
    stability; sum of ranks; ties go to the more interpretable model.
    """
    eligible = {
        name: m for name, m in models.items()
        if (m["availability"] or 0) >= 0.8 and m["coverage_80"] is not None
        and 0.6 <= m["coverage_80"] <= 0.95 and m["mase"] is not None
    }
    excluded = {
        name: ("LOW_AVAILABILITY" if (m["availability"] or 0) < 0.8 else "INTERVAL_MISCALIBRATED")
        for name, m in models.items() if name not in eligible
    }
    if not eligible:
        return {"selected": None, "reason": "NO_ELIGIBLE_MODEL", "excluded": excluded}
    criteria = {
        "accuracy_mase": lambda m: m["mase"],
        "bias": lambda m: abs(m["relative_bias"] or 0),
        "interval_calibration": lambda m: abs(m["coverage_80"] - 0.8),
        "stability": lambda m: m["error_stability"] if m["error_stability"] is not None else 1e9,
    }
    ranks: dict[str, dict[str, int]] = {name: {} for name in eligible}
    for criterion, key in criteria.items():
        ordered = sorted(eligible, key=lambda n, key=key: (key(eligible[n]), n))
        for position, name in enumerate(ordered, start=1):
            ranks[name][criterion] = position
    totals = {name: sum(r.values()) for name, r in ranks.items()}
    best = sorted(eligible, key=lambda n: (totals[n], -INTERPRETABILITY[n], n))
    return {
        "selected": best[0],
        "rank_totals": totals,
        "ranks": ranks,
        "order": best,
        "excluded": excluded,
        "policy": "가용성·구간보정 자격 후 정확도·편향·구간보정·안정성 순위합; 동률 시 해석가능성",
    }
