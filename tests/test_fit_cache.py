"""The fit cache and the one-pass prefix grid give exactly what a plain grid search gives.

The reference below is the grid search of 0.6.0, kept here verbatim: every
parameter set fitted on the history with :func:`holt_damped_fit` or
:func:`holt_winters_fit`, lowest SSE first on ties. The fits are compared by
``repr`` (every field, bit for bit), and whole Markdown and JSON reports are
compared byte for byte with the reference swapped in (ADR 0010).
"""

from __future__ import annotations

import random
from collections.abc import Iterator, Sequence
from dataclasses import replace
from itertools import product
from typing import Any

import pytest
from conftest import EXAMPLES
from test_smoothing import monthly, trend_seasonal_series

from inventory_policy_lab import (
    Config,
    FitError,
    SmoothingFit,
    analyze,
    clear_fit_cache,
    fit_cache_info,
    fit_holt_damped,
    fit_holt_winters,
    holt_damped_fit,
    holt_winters_fit,
    read_demand,
    render_json,
    render_markdown,
)
from inventory_policy_lab import analysis as analysis_module
from inventory_policy_lab import smoothing as smoothing_module
from inventory_policy_lab.smoothing import ALPHAS, BETAS, GAMMAS, PHIS, _history_key


def reference_holt_damped(history: Sequence[float]) -> SmoothingFit:
    if len(history) < 4:
        raise ValueError("damped Holt is fitted on at least 4 periods")
    best: SmoothingFit | None = None
    for alpha, beta, phi in product(ALPHAS, BETAS, PHIS):
        fit = holt_damped_fit(history, alpha, beta, phi)
        if best is None or fit.sse < best.sse:
            best = fit
    assert best is not None
    return best


def reference_holt_winters(
    history: Sequence[float], season_length: int, seasonal: str = "additive"
) -> SmoothingFit:
    if seasonal == "multiplicative" and min(history, default=0) <= 0:
        raise FitError("multiplicative Holt-Winters needs demand above zero in every period")
    best: SmoothingFit | None = None
    for alpha, beta, gamma, phi in product(ALPHAS, BETAS, GAMMAS, PHIS):
        try:
            fit = holt_winters_fit(history, season_length, alpha, beta, gamma, phi, seasonal)
        except FitError:
            continue
        if best is None or fit.sse < best.sse:
            best = fit
    if best is None:
        raise FitError("no parameter set gives a positive multiplicative level")
    return best


@pytest.fixture(autouse=True)
def empty_cache() -> Iterator[None]:
    clear_fit_cache()
    yield
    clear_fit_cache()


def _outcome(fit: Any, *args: Any) -> str:
    try:
        return repr(fit(*args))
    except FitError as error:
        return f"FitError: {error}"


def _series() -> dict[str, list[float]]:
    rng = random.Random(10)
    out = {name: values for name, values in trend_seasonal_series().items()}
    out["noise"] = [max(1.0, round(rng.gauss(50, 20), 1)) for _ in range(30)]
    out["crash"] = [1000.0, 1000, 1, 1, 1, 1, 2, 1]  # multiplicative: no fit from 6 periods
    return out


@pytest.mark.parametrize("order", ["longest first", "shortest first"])
def test_every_prefix_matches_a_plain_grid(order: str) -> None:
    for name, values in _series().items():
        m = 2 if name == "crash" else 12
        lengths = list(range(4, len(values) + 1))
        if order == "longest first":
            lengths.reverse()
        for k in lengths:
            prefix = values[:k]
            assert repr(fit_holt_damped(prefix)) == repr(reference_holt_damped(prefix))
            if k < 2 * m:
                continue
            for seasonal in ("additive", "multiplicative"):
                got = _outcome(fit_holt_winters, prefix, m, seasonal)
                assert got == _outcome(reference_holt_winters, prefix, m, seasonal), (name, k)
    info = fit_cache_info()
    if order == "longest first":  # one grid pass per history and model, then hits only
        assert info.misses == len(_series()) * 3 and info.hits > 0
    else:  # every call brings a period no pass has seen
        assert info.hits == 0


def test_crash_series_prefixes_valid_then_not() -> None:
    crash = _series()["crash"]
    # The long history first: its pass also stores the shorter prefixes.
    with pytest.raises(FitError, match="no parameter set"):
        fit_holt_winters(crash[:6], 2, "multiplicative")
    assert fit_holt_winters(crash[:4], 2, "multiplicative").model == "hw_multiplicative"
    with pytest.raises(FitError, match="no parameter set"):  # now from the cache
        fit_holt_winters(crash[:6], 2, "multiplicative")
    assert fit_cache_info().hits == 2


def test_cache_counts_evicts_and_clears(monkeypatch: pytest.MonkeyPatch) -> None:
    values = [float(v) for v in trend_seasonal_series()["T"][:10]]
    fit_holt_damped(values)  # one miss, stores the prefixes of 4 to 10 periods
    assert fit_cache_info() == smoothing_module.FitCacheInfo(0, 1, 7, 4096)
    fit_holt_damped(values[:5])
    assert (fit_cache_info().hits, fit_cache_info().misses) == (1, 1)
    monkeypatch.setattr(smoothing_module._CACHE, "max_size", 3)
    fit_holt_damped(values[:5] + [0.0])  # a new history: the store drops to 3 entries
    assert fit_cache_info().size == 3
    assert fit_holt_damped(values[:5]) == reference_holt_damped(values[:5])
    clear_fit_cache()
    assert fit_cache_info() == smoothing_module.FitCacheInfo(0, 0, 0, 3)


def test_keys_tell_apart_equal_values_of_another_type_or_sign() -> None:
    assert _history_key((10, 12)) != _history_key((10.0, 12.0))
    assert _history_key((0.0, 1.0)) != _history_key((-0.0, 1.0))
    assert _history_key([1.5, 2.0]) == _history_key((1.5, 2.0))
    ints, floats = [10, 12, 15, 16, 18], [10.0, 12.0, 15.0, 16.0, 18.0]
    assert repr(fit_holt_damped(ints)) == repr(reference_holt_damped(ints))
    assert repr(fit_holt_damped(floats)) == repr(reference_holt_damped(floats))


def test_argument_errors_are_unchanged() -> None:
    with pytest.raises(ValueError, match="'additive' or 'multiplicative'"):
        fit_holt_winters([1.0, 2, 3, 4], 2, "both")
    with pytest.raises(ValueError, match="two full seasons"):
        fit_holt_winters([1.0, 2, 3], 2)
    with pytest.raises(ValueError, match="two full seasons"):
        fit_holt_winters([1.0, 2, 3, 4], 1)
    with pytest.raises(FitError, match="above zero"):
        fit_holt_winters([1.0, 0, 3, 4], 2, "multiplicative")
    assert fit_cache_info().misses == 0  # rejected before the cache


ROLLING = {"test_periods": 12, "rolling_origin": True, "trend_seasonal": True}
OPTION_SETS: dict[str, dict[str, Any]] = {
    "trend_seasonal": {"trend_seasonal": True},
    "rolling": ROLLING,
    "rolling_residuals": {**ROLLING, "bootstrap_source": "residuals"},
    "rolling_rs_per_period": {
        **ROLLING,
        "bootstrap_source": "residuals",
        "policy": "RS",
        "dynamic_levels": True,
        "period_safety_stock": True,
    },
    "rolling_rs3_rmse": {
        **ROLLING,
        "policy": "RS",
        "review_period": 3,
        "dynamic_levels": True,
        "sigma": "rmse",
    },
    "bootstrap_residuals": {
        "trend_seasonal": True,
        "safety_stock_method": "bootstrap",
        "bootstrap_source": "residuals",
        "dynamic_levels": True,
        "period_safety_stock": True,
    },
}


def _both_formats(data: Any, config: Config) -> tuple[str, str]:
    report = analyze(data, config)
    return render_markdown(report), render_json(report)


@pytest.mark.parametrize("name", sorted(OPTION_SETS))
def test_reports_are_byte_identical_to_a_plain_grid(
    name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every report section, Markdown and JSON, with and without the cache.

    The 48-month series uses 4 test periods here to keep the plain grid fast;
    the README checks the 12-period runs separately.
    """
    datasets = {
        "synthetic": (read_demand(EXAMPLES / "demand_synthetic.csv"), 12),
        "series": (monthly(trend_seasonal_series()), 4),
    }
    for data, test_periods in datasets.values():
        settings = dict(OPTION_SETS[name])
        if "test_periods" in settings:
            settings["test_periods"] = test_periods
        config = Config(**settings)
        cached = _both_formats(data, config)
        cached_again = _both_formats(data, config)  # served from a warm cache
        with monkeypatch.context() as patch:
            patch.setattr(analysis_module, "fit_holt_damped", reference_holt_damped)
            patch.setattr(analysis_module, "fit_holt_winters", reference_holt_winters)
            plain = _both_formats(data, replace(config))
        assert cached == plain
        assert cached_again == plain
