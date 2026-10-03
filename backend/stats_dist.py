"""Small, dependency-free distribution helpers for interpretable demand ranges.

Only closed-form conjugate models are used (Beta-Binomial, Gamma-Poisson), so
every range can be explained as "prior pseudo-observations + local counts".
"""

from __future__ import annotations

import math


def _betacf(a: float, b: float, x: float) -> float:
    """Continued fraction for the regularized incomplete beta (modified Lentz)."""
    tiny = 1e-300
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    d = 1.0 / (d if abs(d) > tiny else tiny)
    h = d
    for m in range(1, 300):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > tiny else tiny)
        c = 1.0 + aa / c
        c = c if abs(c) > tiny else tiny
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > tiny else tiny)
        c = 1.0 + aa / c
        c = c if abs(c) > tiny else tiny
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 1e-12:
            break
    return h


def beta_cdf(x: float, a: float, b: float) -> float:
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    log_front = (
        math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
        + a * math.log(x) + b * math.log1p(-x)
    )
    front = math.exp(log_front)
    if x < (a + 1) / (a + b + 2):
        return front * _betacf(a, b, x) / a
    return 1.0 - front * _betacf(b, a, 1.0 - x) / b


def beta_quantile(q: float, a: float, b: float) -> float:
    lo, hi = 0.0, 1.0
    for _ in range(80):
        mid = (lo + hi) / 2
        if beta_cdf(mid, a, b) < q:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def negbin_quantiles(shape: float, rate: float, qs: tuple[float, ...]) -> tuple[int, ...]:
    """Quantiles of the Gamma(shape, rate)-Poisson posterior predictive (one month)."""
    p = rate / (rate + 1.0)  # success probability in the NB(shape, p) parameterization
    results: list[int] = []
    cumulative = 0.0
    k = 0
    log_pmf = shape * math.log(p)  # k = 0
    targets = sorted(qs)
    index = 0
    while index < len(targets) and k < 100_000:
        cumulative += math.exp(log_pmf)
        while index < len(targets) and cumulative >= targets[index] - 1e-12:
            results.append(k)
            index += 1
        log_pmf += math.log((k + shape) / (k + 1)) + math.log1p(-p)
        k += 1
    order = {q: value for q, value in zip(targets, results, strict=False)}
    return tuple(order[q] for q in qs)


def poisson_quantiles(mean: float, qs: tuple[float, ...]) -> tuple[int, ...]:
    if mean <= 0:
        return tuple(0 for _ in qs)
    results = {}
    cumulative, k, log_pmf = 0.0, 0, -mean
    targets = sorted(qs)
    index = 0
    while index < len(targets) and k < 100_000:
        cumulative += math.exp(log_pmf)
        while index < len(targets) and cumulative >= targets[index] - 1e-12:
            results[targets[index]] = k
            index += 1
        k += 1
        log_pmf += math.log(mean) - math.log(k)
    return tuple(results[q] for q in qs)
