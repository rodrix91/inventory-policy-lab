"""Damped Holt and Holt-Winters: numbers by hand, known patterns, and the analysis wiring."""

from __future__ import annotations

import json
import math
import random

import pytest
from conftest import EXAMPLES

from inventory_policy_lab import (
    Config,
    ConfigError,
    FitError,
    OutOfSampleReport,
    analyze,
    analyze_file,
    fit_holt_damped,
    fit_holt_winters,
    holt_damped,
    holt_damped_fit,
    holt_winters,
    holt_winters_fit,
    parse_rows,
    render_json,
    render_markdown,
    train_history,
)
from inventory_policy_lab.analysis import _analyze_sku
from inventory_policy_lab.reader import DemandData, read_demand
from inventory_policy_lab.smoothing import ALPHAS, BETAS, PHIS


def monthly(table: dict[str, list[float]], start_year: int = 2022) -> DemandData:
    rows = [["sku", "period", "quantity"]]
    for sku, demand in table.items():
        rows += [
            [sku, f"{start_year + i // 12}-{i % 12 + 1:02d}", str(q)] for i, q in enumerate(demand)
        ]
    return parse_rows(rows)


def integer(table: dict[str, list[float]]) -> DemandData:
    rows = [["sku", "period", "quantity"]]
    for sku, demand in table.items():
        rows += [[sku, str(i + 1), str(q)] for i, q in enumerate(demand)]
    return parse_rows(rows)


def trend_seasonal_series() -> dict[str, list[float]]:
    """48 synthetic months with a known shape (seeded noise), used in the README and ADR 0006.

    T: level 40 growing 2 per month; S: 100 with a +-40 yearly sine; TS: a level
    growing 1 per month times a +-35% yearly sine. Noise is normal, sd 4 to 6.
    """
    rng = random.Random(6)
    out: dict[str, list[float]] = {"T": [], "S": [], "TS": []}
    for t in range(48):
        season = math.sin(2 * math.pi * t / 12)
        out["T"].append(max(0, round(40 + 2.0 * t + rng.gauss(0, 4))))
        out["S"].append(max(0, round(100 + 40 * season + rng.gauss(0, 6))))
        out["TS"].append(max(0, round((60 + 1.0 * t) * (1 + 0.35 * season) + rng.gauss(0, 4))))
    return out


def test_damped_holt_by_hand() -> None:
    """y = 10 12 15 16, a = b = 0.5, phi = 0.8.

    Start: L = 12, B = 12 - 10 = 2.
    y = 15: forecast 12 + 0.8 x 2 = 13.6, error 1.4; L = 0.5 x 15 + 0.5 x 13.6 = 14.3;
            B = 0.5 x (14.3 - 12) + 0.5 x 0.8 x 2 = 1.95.
    y = 16: forecast 14.3 + 0.8 x 1.95 = 15.86, error 0.14; L = 0.5 x 16 + 0.5 x 15.86 = 15.93;
            B = 0.5 x (15.93 - 14.3) + 0.5 x 0.8 x 1.95 = 1.595.
    SSE = 1.4² + 0.14² = 1.9796. F(1) = 15.93 + 0.8 x 1.595 = 17.206;
    F(2) = 15.93 + (0.8 + 0.64) x 1.595 = 18.2268; mean of both 17.7164.
    """
    fit = holt_damped_fit([10, 12, 15, 16], alpha=0.5, beta=0.5, phi=0.8)
    assert (fit.model, fit.gamma, fit.seasonals) == ("holt_damped", None, ())
    assert fit.level == pytest.approx(15.93)
    assert fit.trend == pytest.approx(1.595)
    assert fit.sse == pytest.approx(1.9796)
    assert fit.forecast(1) == pytest.approx(17.206)
    assert fit.forecast(2) == pytest.approx(18.2268)
    assert fit.mean_forecast(2) == pytest.approx(17.7164)
    assert fit.mean_forecast(0) == pytest.approx(17.206)  # at least one period
    assert fit.parameters() == {"alpha": 0.5, "beta": 0.5, "phi": 0.8}


def test_additive_holt_winters_by_hand() -> None:
    """y = 10 20 14 24 16, m = 2, a = b = g = 0.5, phi = 0.9.

    Start: L = mean(10, 20) = 15, B = (mean(14, 24) - 15) / 2 = 2, S = (-5, 5).
    y = 14 (S -5): forecast 15 + 1.8 - 5 = 11.8, error 2.2;
        L = 0.5 x (14 + 5) + 0.5 x 16.8 = 17.9; S = 0.5 x (14 - 17.9) + 0.5 x -5 = -4.45;
        B = 0.5 x 2.9 + 0.5 x 0.9 x 2 = 2.35.
    y = 24 (S 5): forecast 17.9 + 2.115 + 5 = 25.015, error -1.015;
        L = 0.5 x 19 + 0.5 x 20.015 = 19.5075; S = 0.5 x 4.4925 + 2.5 = 4.74625;
        B = 0.5 x 1.6075 + 0.45 x 2.35 = 1.86125.
    y = 16 (S -4.45): forecast 19.5075 + 1.675125 - 4.45 = 16.732625, error -0.732625;
        L = 0.5 x 20.45 + 0.5 x 21.182625 = 20.8163125;
        S = 0.5 x (16 - 20.8163125) + 0.5 x -4.45 = -4.63315625;
        B = 0.5 x 1.3088125 + 0.45 x 1.86125 = 1.49196875.
    F(1) = 20.8163125 + 0.9 x 1.49196875 + 4.74625 = 26.905334375;
    F(2) = 20.8163125 + 1.71 x 1.49196875 - 4.63315625 = 18.7344228125.
    """
    fit = holt_winters_fit([10, 20, 14, 24, 16], 2, alpha=0.5, beta=0.5, gamma=0.5, phi=0.9)
    assert fit.model == "hw_additive"
    assert fit.level == pytest.approx(20.8163125)
    assert fit.trend == pytest.approx(1.49196875)
    assert fit.seasonals == pytest.approx((4.74625, -4.63315625))
    assert fit.sse == pytest.approx(2.2**2 + 1.015**2 + 0.732625**2)
    assert fit.forecast(1) == pytest.approx(26.905334375)
    assert fit.forecast(2) == pytest.approx(18.7344228125)
    # the season repeats: horizon 3 uses the factor of horizon 1 again
    assert fit.forecast(3) == pytest.approx(20.8163125 + 2.439 * 1.49196875 + 4.74625)
    assert fit.parameters() == {"alpha": 0.5, "beta": 0.5, "phi": 0.9, "gamma": 0.5}


def test_multiplicative_holt_winters_by_hand() -> None:
    """y = 10 20 12 24, m = 2, a = b = g = 0.5, phi = 0.9.

    Start: L = 15, B = (18 - 15) / 2 = 1.5, S = (10/15, 20/15).
    y = 12: forecast (15 + 1.35) x 2/3 = 10.9, error 1.1; L = 0.5 x 12 / (2/3) + 0.5 x 16.35
        = 17.175; S = 0.5 x 12 / 17.175 + 0.5 x 2/3; B = 0.5 x 2.175 + 0.45 x 1.5 = 1.7625.
    y = 24: forecast (17.175 + 1.58625) x 4/3 = 25.015, error -1.015;
        L = 0.5 x 24 / (4/3) + 0.5 x 18.76125 = 18.380625; S = 0.5 x 24 / 18.380625 + 0.5 x 4/3;
        B = 0.5 x 1.205625 + 0.45 x 1.7625 = 1.3959375.
    F(1) = (18.380625 + 0.9 x 1.3959375) x S(1).
    """
    fit = holt_winters_fit([10, 20, 12, 24], 2, 0.5, 0.5, 0.5, 0.9, "multiplicative")
    first = 0.5 * 12 / 17.175 + 0.5 * 2 / 3
    second = 0.5 * 24 / 18.380625 + 0.5 * 4 / 3
    assert fit.model == "hw_multiplicative"
    assert fit.level == pytest.approx(18.380625)
    assert fit.trend == pytest.approx(1.3959375)
    assert fit.seasonals == pytest.approx((first, second))
    assert fit.sse == pytest.approx(1.1**2 + 1.015**2)
    assert fit.forecast(1) == pytest.approx((18.380625 + 0.9 * 1.3959375) * first)
    assert fit.forecast(2) == pytest.approx((18.380625 + 1.71 * 1.3959375) * second)


def test_exact_seasonal_patterns_are_reproduced() -> None:
    pattern = [40.0, 60, 55, 45]  # mean 50, no trend
    additive = fit_holt_winters(pattern * 4, 4)
    # every one-step error is zero, so every grid point ties and the first one wins
    assert additive.sse == pytest.approx(0)
    assert (additive.alpha, additive.beta, additive.gamma, additive.phi) == (0.1, 0.05, 0.05, 0.8)
    assert [additive.forecast(h) for h in range(1, 9)] == pytest.approx(pattern * 2)
    factors = [100.0 * f for f in (0.8, 1.2, 1.1, 0.9)]
    multiplicative = fit_holt_winters(factors * 3, 4, "multiplicative")
    assert multiplicative.sse == pytest.approx(0)
    assert [multiplicative.forecast(h) for h in range(1, 5)] == pytest.approx(factors)
    assert holt_winters(pattern * 4, 4) == pytest.approx(40)


def test_damped_holt_follows_a_known_trend() -> None:
    line = [10.0 + 3 * t for t in range(12)]  # next value 46
    fit = fit_holt_damped(line)
    assert fit.alpha in ALPHAS and fit.beta in BETAS and fit.phi in PHIS
    assert fit.phi == max(PHIS)  # the least damping fits a straight line best
    assert 44 < fit.forecast(1) < 46  # damping keeps it just below the line
    assert holt_damped(line) == fit.forecast(1)
    assert fit_holt_damped([30.0, 20, 10, 0]).forecast(3) == 0  # floored at zero


def test_invalid_inputs_and_fits() -> None:
    with pytest.raises(ValueError, match="at least 2 periods"):
        holt_damped_fit([5], 0.5, 0.5, 0.9)
    with pytest.raises(ValueError, match="fitted on at least 4 periods"):
        fit_holt_damped([1, 2, 3])
    with pytest.raises(ValueError, match="horizon must be at least 1"):
        holt_damped_fit([1, 2], 0.5, 0.5, 0.9).forecast(0)
    with pytest.raises(ValueError, match="'additive' or 'multiplicative'"):
        holt_winters_fit([1, 2, 3, 4], 2, 0.5, 0.5, 0.5, 0.9, "both")
    with pytest.raises(ValueError, match="two full seasons"):
        holt_winters_fit([1, 2, 3], 2, 0.5, 0.5, 0.5, 0.9)
    with pytest.raises(ValueError, match="two full seasons"):
        holt_winters_fit([1, 2, 3, 4], 1, 0.5, 0.5, 0.5, 0.9)
    with pytest.raises(FitError, match="above zero"):
        holt_winters_fit([1, 0, 3, 4], 2, 0.5, 0.5, 0.5, 0.9, "multiplicative")
    with pytest.raises(FitError, match="above zero"):
        fit_holt_winters([1, 0, 3, 4], 2, "multiplicative")
    # a collapse from 1000 to 1 drives the multiplicative level below zero
    crash = [1000.0, 1000, 1, 1, 1, 1]
    with pytest.raises(FitError, match="level fell"):
        holt_winters_fit(crash, 2, 0.9, 0.05, 0.05, 0.98, "multiplicative")
    with pytest.raises(FitError, match="no parameter set"):
        fit_holt_winters(crash, 2, "multiplicative")
    assert fit_holt_winters(crash, 2).model == "hw_additive"  # additive always fits


def test_config_season_length_and_candidates() -> None:
    assert Config().effective_season_length == 12
    assert Config(periods_per_year=52).effective_season_length == 52
    assert Config(periods_per_year=12.5).effective_season_length is None
    assert Config(periods_per_year=1).effective_season_length is None
    on = Config(trend_seasonal=True, season_length=2)
    assert on.effective_season_length == 2
    assert Config().trend_seasonal_fitters("smooth", 40, True) == {}
    assert on.trend_seasonal_fitters("lumpy", 40, True) == {}
    assert on.trend_seasonal_fitters("smooth", 3, True) == {}
    assert list(on.trend_seasonal_fitters("erratic", 4, True)) == [
        "holt_damped",
        "hw_additive",
        "hw_multiplicative",
    ]
    assert list(on.trend_seasonal_fitters("smooth", 4, False)) == ["holt_damped", "hw_additive"]
    yearly = Config(trend_seasonal=True)
    assert list(yearly.trend_seasonal_fitters("smooth", 23, True)) == ["holt_damped"]
    assert len(yearly.trend_seasonal_fitters("smooth", 24, True)) == 3
    odd = Config(trend_seasonal=True, periods_per_year=12.5)
    assert list(odd.trend_seasonal_fitters("smooth", 100, True)) == ["holt_damped"]
    data = integer({"a": [10.0] * 10})
    with pytest.raises(ConfigError, match="only applies with trend_seasonal"):
        analyze(data, Config(holdout=2, season_length=4))
    with pytest.raises(ConfigError, match="at least 2, got 1"):
        analyze(data, Config(holdout=2, trend_seasonal=True, season_length=1))


def test_off_by_default_keeps_the_report() -> None:
    data = integer({"a": [10.0 + 3 * t for t in range(12)]})
    report = analyze(data, Config(holdout=3))
    (sku,) = report.skus
    assert [b.method for b in sku.backtests] == ["naive", "moving_average", "ses"]
    assert sku.forecast_parameters is None
    payload = report.to_dict()
    assert payload["settings"]["trend_seasonal"] is False
    assert payload["settings"]["season_length"] is None
    assert "parameters" not in payload["skus"][0]["forecast"]
    text = render_markdown(report)
    assert "holt_damped" not in text and "Trend and seasonal" not in text


def test_trend_is_picked_and_forecast_over_the_protection_interval() -> None:
    series = trend_seasonal_series()["T"][:24]
    report = analyze(integer({"T": series}), Config(holdout=6, trend_seasonal=True))
    (sku,) = report.skus
    assert [b.method for b in sku.backtests] == ["naive", "moving_average", "ses", "holt_damped"]
    assert sku.method == "holt_damped"
    fit = fit_holt_damped(series)
    # default lead time 1 + review period 1 = 2 periods: mean of F(1) and F(2)
    assert sku.forecast == pytest.approx((fit.forecast(1) + fit.forecast(2)) / 2)
    assert sku.policy.demand_per_period == sku.forecast
    assert sku.forecast_parameters == fit.parameters()
    payload = json.loads(render_json(report))
    assert payload["settings"]["trend_seasonal"] is True
    assert payload["settings"]["season_length"] == 12
    assert payload["skus"][0]["forecast"]["parameters"] == fit.parameters()
    text = render_markdown(report)
    assert "- Trend and seasonal candidates for smooth and erratic SKUs: damped Holt" in text
    assert "season length 12, from 24 periods" in text
    assert "| SKU | naive | moving_average | ses | croston | sba | holt_damped |" in text
    assert "SES, damped Holt and Holt-Winters when the history allows" in text
    odd = analyze(
        integer({"T": series}), Config(holdout=6, trend_seasonal=True, periods_per_year=12.5)
    )
    assert "no Holt-Winters (no season length)" in render_markdown(odd)


def test_failed_multiplicative_fit_is_left_out_with_a_note() -> None:
    data = integer({"a": [1000.0, 1000, 1, 1, 1, 1, 1, 1]})
    report = analyze(data, Config(holdout=2, trend_seasonal=True, season_length=2))
    (sku,) = report.skus
    methods = [b.method for b in sku.backtests]
    assert "hw_additive" in methods and "hw_multiplicative" not in methods
    assert "hw_multiplicative: no valid fit (level not positive), left out" in sku.notes


def test_trend_and_seasonal_series_out_of_sample() -> None:
    """The 48-month series: the README and ADR 0006 quote these numbers."""
    data = monthly(trend_seasonal_series())
    before = analyze(data, Config(test_periods=12)).out_of_sample
    after = analyze(data, Config(test_periods=12, trend_seasonal=True)).out_of_sample
    assert before is not None and after is not None

    def summary(oos: OutOfSampleReport) -> dict[str, tuple[float, int, float]]:
        return {
            method: (
                round(t.fill_rate or 0, 3),
                t.stockout_periods,
                round(t.average_on_hand, 1),
            )
            for method in ("normal", "bootstrap")
            for t in [oos.totals(method, "out_of_sample")]
        }

    assert summary(before) == {"normal": (0.975, 3, 189.8), "bootstrap": (0.966, 5, 172.4)}
    assert summary(after) == {"normal": (0.996, 1, 289.0), "bootstrap": (0.976, 4, 196.4)}
    assert {s.sku: s.forecast_method for s in before.skus} == {
        "T": "naive",
        "S": "naive",
        "TS": "naive",
    }
    assert {s.sku: s.forecast_method for s in after.skus} == {
        "T": "naive",  # damped Holt is a candidate but loses the training holdout
        "S": "hw_additive",
        "TS": "hw_multiplicative",
    }


def test_no_leak_from_the_test_periods_into_trend_and_seasonal_fits() -> None:
    series = trend_seasonal_series()
    changed = {sku: values[:36] + [0.0] * 12 for sku, values in series.items()}
    config = Config(test_periods=12, trend_seasonal=True)
    base = analyze(monthly(series), config).out_of_sample
    other = analyze(monthly(changed), config).out_of_sample
    assert base is not None and other is not None
    for a, b in zip(base.skus, other.skus, strict=True):
        assert (a.forecast_method, a.forecast) == (b.forecast_method, b.forecast)
        assert [r.reorder_point for r in a.replays] == [r.reorder_point for r in b.replays]


def test_synthetic_example_with_trend_and_seasonal_candidates() -> None:
    """The 24-month example: the README quotes these numbers next to the ADR 0005 ones."""
    before = analyze_file(EXAMPLES / "demand_synthetic.csv", Config(test_periods=12))
    after = analyze_file(
        EXAMPLES / "demand_synthetic.csv", Config(test_periods=12, trend_seasonal=True)
    )
    assert before.out_of_sample is not None and after.out_of_sample is not None
    # Out of sample nothing changes: with 12 training months no SKU has the 24
    # periods Holt-Winters needs, and damped Holt loses the training holdout.
    for old, new in zip(before.out_of_sample.skus, after.out_of_sample.skus, strict=True):
        assert (old.forecast_method, old.forecast) == (new.forecast_method, new.forecast)
        assert old.replays == new.replays
    oos = {s.sku: s for s in after.out_of_sample.skus}
    assert (oos["SKU-003"].forecast_method, oos["SKU-004"].forecast_method) == (
        "naive",
        "moving_average",
    )
    # On the full history damped Holt wins the holdout of SKU-003 and SKU-009.
    picks = {s.sku: s.method for s in after.skus}
    assert picks["SKU-003"] == "holt_damped" and picks["SKU-009"] == "holt_damped"
    assert picks["SKU-004"] == "naive"
    assert round(before.overall_fill_rate() or 0, 3) == 0.994
    assert round(after.overall_fill_rate() or 0, 3) == 0.995
    changed = [s.sku for s, o in zip(after.skus, before.skus, strict=True) if s.method != o.method]
    assert changed == ["SKU-003", "SKU-009"]


def test_synthetic_example_numbers_quoted_in_the_readme() -> None:
    config = Config(test_periods=12, trend_seasonal=True)
    report = analyze_file(EXAMPLES / "demand_synthetic.csv", config)
    assert report.out_of_sample is not None
    oos = {s.sku: s for s in report.out_of_sample.skus}
    quoted = {
        (sku, method): (
            round(r.in_sample.fill_rate or 0, 3),
            round(r.out_of_sample.fill_rate or 0, 3),
            r.in_sample.stockout_periods,
            r.out_of_sample.stockout_periods,
            round(r.in_sample.average_on_hand, 1),
            round(r.out_of_sample.average_on_hand, 1),
        )
        for sku in ("SKU-003", "SKU-004")
        for method in ("normal", "bootstrap")
        for r in [oos[sku].replay(method)]
    }
    assert quoted == {
        ("SKU-003", "normal"): (0.923, 0.829, 3, 4, 68.5, 51.0),
        ("SKU-003", "bootstrap"): (0.995, 0.944, 1, 3, 100.6, 79.2),
        ("SKU-004", "normal"): (1.0, 0.797, 0, 6, 60.7, 8.6),
        ("SKU-004", "bootstrap"): (1.0, 0.677, 0, 9, 46.8, 3.6),
    }
    # MASE of the training holdout of SKU-004 (2024-01 to 2024-12, holdout 6)
    data = read_demand(EXAMPLES / "demand_synthetic.csv")
    history = next(h for h in data.skus if h.sku == "SKU-004")
    train = train_history(history, data.calendar[:12])
    assert train is not None
    fitted = _analyze_sku(train, config, "A", 1.0)
    scores = {b.method: round(b.mase or 0, 2) for b in fitted.backtests}
    assert (scores["holt_damped"], scores["moving_average"], fitted.method) == (
        1.25,
        0.91,
        "moving_average",
    )
    # MASE on the full history and the in-sample effect on SKU-003
    full = {s.sku: s for s in report.skus}
    mase = {
        sku: {b.method: round(b.mase or 0, 2) for b in full[sku].backtests}
        for sku in ("SKU-003", "SKU-004", "SKU-009")
    }
    assert (mase["SKU-003"]["holt_damped"], mase["SKU-003"]["naive"]) == (0.90, 1.0)
    assert (mase["SKU-009"]["holt_damped"], mase["SKU-009"]["ses"]) == (1.18, 1.23)
    assert (mase["SKU-004"]["naive"], mase["SKU-004"]["holt_damped"]) == (1.67, 2.06)
    assert round(full["SKU-003"].simulation.fill_rate or 0, 3) == 0.988
    before = analyze_file(EXAMPLES / "demand_synthetic.csv", Config())
    assert round(
        next(s for s in before.skus if s.sku == "SKU-003").simulation.fill_rate or 0, 3
    ) == (0.98)
