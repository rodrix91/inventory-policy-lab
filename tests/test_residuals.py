"""Residual bootstrap and safety stock per period (ADR 0008): by hand, no leak, wiring, results."""

from __future__ import annotations

import json
import random
from collections.abc import Sequence
from typing import Any

import pytest
from conftest import EXAMPLES
from test_smoothing import integer, monthly, trend_seasonal_series

from inventory_policy_lab import (
    Config,
    ConfigError,
    analyze,
    analyze_file,
    dynamic_levels,
    interval_demands,
    interval_forecast_errors,
    naive,
    period_safety_stocks,
    protection_periods,
    render_json,
    render_markdown,
    residual_bootstrap_quantile,
)
from inventory_policy_lab.analysis import _residual_safety_stock

WORKED = EXAMPLES / "worked_example.csv"
SYNTHETIC = EXAMPLES / "demand_synthetic.csv"
RESIDUALS = {"bootstrap_source": "residuals"}


def naive_interval(history: Sequence[float], periods: int) -> float | None:
    return periods * naive(history)


# --- the errors and the quantile, by hand --------------------------------------------


def test_interval_forecast_errors_by_hand() -> None:
    # Naive over P = 2 periods, origins 2 and 3:
    # t = 2: sees 10 12 -> forecast 2 x 12 = 24, actual 14 + 16 = 30, error 6 (relative 0.25)
    # t = 3: sees 10 12 14 -> forecast 28, actual 16 + 18 = 34, error 6 (relative 6 / 28)
    series = [10, 12, 14, 16, 18]
    assert interval_forecast_errors(series, naive_interval, 2, 2) == (6, 6)
    assert interval_forecast_errors(series, naive_interval, 2, 2, relative=True) == pytest.approx(
        (0.25, 6 / 28)
    )
    # Origin 1 adds t = 1: forecast 20, actual 12 + 14 = 26, error 6.
    assert interval_forecast_errors(series, naive_interval, 2, 1) == (6, 6, 6)
    assert interval_forecast_errors(series, naive_interval, 0, 2) == ()
    assert interval_forecast_errors(series, naive_interval, 5, 2) == ()  # no origin fits
    with pytest.raises(ValueError, match="start must be at least 1"):
        interval_forecast_errors(series, naive_interval, 2, 0)


def test_errors_skip_origins_without_a_forecast() -> None:
    # A forecaster that cannot forecast from 2 periods, and one forecasting zero:
    # the first origin is skipped; a zero forecast is kept as an absolute error only.
    def picky(history: Sequence[float], periods: int) -> float | None:
        return None if len(history) < 3 else 0.0

    assert interval_forecast_errors([1, 2, 3, 4, 5], picky, 1, 2) == (4, 5)
    assert interval_forecast_errors([1, 2, 3, 4, 5], picky, 1, 2, relative=True) == ()


def test_errors_never_see_the_periods_they_score() -> None:
    seen: list[int] = []

    def recording(history: Sequence[float], periods: int) -> float | None:
        seen.append(len(history))
        assert 99 not in history  # the scored periods are not in the history passed in
        return 0.0

    series = [1.0, 2.0, 3.0, 99.0, 99.0]
    assert interval_forecast_errors(series, recording, 2, 2) == (102, 198)
    assert seen == [2, 3]


def test_residual_bootstrap_quantile_by_hand() -> None:
    # L = 1, R = 1: every draw is one of the four errors over 2 periods. The 99%
    # nearest-rank quantile of 2000 draws is the largest error; the 60% quantile is
    # the third value (about 50% of draws are -3 or 1, 75% at most 5).
    errors = {2: (-3.0, 1.0, 5.0, 9.0)}
    assert residual_bootstrap_quantile(errors, 0.99, 1, 1) == 9
    assert residual_bootstrap_quantile(errors, 0.6, 1, 1, rng=random.Random(1)) == 5
    # Lead times 1 and 2 with R = 1: intervals of 2 or 3 periods, half the draws each.
    mixed = {2: (0.0,), 3: (10.0,)}
    assert residual_bootstrap_quantile(mixed, 0.9, 1, 1, lead_times=(1, 2)) == 10
    assert residual_bootstrap_quantile(mixed, 0.3, 1, 1, lead_times=(1, 2)) == 0
    # L + R = 0.4 rounds to 0 periods: nothing to protect, the quantile is 0.
    assert residual_bootstrap_quantile({}, 0.95, 0.4, 0) == 0
    with pytest.raises(ValueError, match="no forecast errors over 3 period"):
        residual_bootstrap_quantile(mixed | {3: ()}, 0.95, 1, 1, lead_times=(1, 2))
    with pytest.raises(ValueError, match="no forecast errors over 2 period"):
        residual_bootstrap_quantile({}, 0.95, 1, 1)
    with pytest.raises(ValueError, match="samples must be at least 1"):
        residual_bootstrap_quantile(errors, 0.95, 1, 1, samples=0)


def test_protection_periods() -> None:
    assert [protection_periods(*lr) for lr in ((1, 1), (1.5, 1), (0.4, 0), (2.4, 1))] == [
        2,
        3,
        0,
        3,
    ]


def test_period_safety_stocks_by_hand() -> None:
    # L = 1, R = 1, P = 2: D(t) = mean(F(t+1), F(t+2)) = 25, 35, 45.
    # SS(t) = 0.1 x D(t) x 2 = 5, 7, 9; S(t) = D(t) x 2 + SS(t) = 55, 77, 99.
    forecasts = [10, 20, 30, 40, 50]
    assert interval_demands(forecasts, 3, 1, 1) == pytest.approx((25, 35, 45))
    stocks = period_safety_stocks(forecasts, 3, 1, 1, 0.1)
    assert stocks == pytest.approx((5, 7, 9))
    assert dynamic_levels(forecasts, 3, 1, 1, stocks) == pytest.approx((55, 77, 99))
    # A negative quantile is floored: no safety stock, levels at the forecast.
    assert period_safety_stocks(forecasts, 3, 1, 1, -0.2) == (0, 0, 0)
    with pytest.raises(ValueError, match="one value per period: 2 for 3"):
        dynamic_levels(forecasts, 3, 1, 1, (1.0, 2.0))


# --- the analysis, by hand -----------------------------------------------------------


def test_worked_example_residual_bootstrap_by_hand() -> None:
    """Holdout 2, service 95%, R = 1.

    W-1: moving average (window 3), observed lead time 2, so P = 3; origins 2 to 5:
      t = 2: sees 10 12 -> 3 x 11 = 33, actual 8 + 10 + 14 = 32, error -1
      t = 3: sees 10 12 8 -> 30, actual 10 + 14 + 6 = 30, error 0
      t = 4: sees 12 8 10 -> 30, actual 14 + 6 + 10 = 30, error 0
      t = 5: sees 8 10 14 -> 32, actual 6 + 10 + 14 = 30, error -2
      95% quantile 0: SS = 0 and S = s = 10 x 3 = 30.
    W-2: SBA, default lead time 1, so P = 2; origins 2 to 6 (Croston size 6, interval 3
    from t = 3, SBA 0.95 x 6 / 3 = 1.9 per period):
      t = 2: sees 0 0 -> 0, actual 6 + 0 = 6, error 6
      t = 3: sees 0 0 6 -> 3.8, actual 0 + 0, error -3.8;  t = 4: same, error -3.8
      t = 5: 3.8, actual 0 + 9, error 5.2;                t = 6: same, error 5.2
      95% quantile 6: SS = 6, s = 1.930645 x 2 + 6 = 9.86129.
    """
    report = analyze_file(WORKED, Config(holdout=2, safety_stock_method="bootstrap", **RESIDUALS))  # type: ignore[arg-type]
    w1, w2 = report.skus
    assert w1.policy.safety_stock == 0
    assert w1.policy.reorder_point == pytest.approx(30)
    assert "residual bootstrap: rolling-origin forecast errors (4 over 3 period(s))" in w1.notes
    assert not any("floored" in note for note in w1.notes)  # the quantile is 0, not below
    assert w2.policy.safety_stock == pytest.approx(6)
    assert w2.policy.reorder_point == pytest.approx(0.95 * 6.3 / 3.1 * 2 + 6)
    assert "residual bootstrap: rolling-origin forecast errors (5 over 2 period(s))" in w2.notes
    assert w1.policy.safety_stock_method == "bootstrap"
    text = render_markdown(report)
    assert "safety stock: bootstrap of rolling-origin forecast errors over the protection" in text
    assert "per period" not in text.split("## ABC-XYZ")[0]


def test_falling_demand_floors_the_safety_stock() -> None:
    # Every level forecast of a falling series is above what follows: all errors < 0.
    data = integer({"D": [20, 18, 16, 14, 12, 10, 8, 6]})
    config = Config(holdout=2, safety_stock_method="bootstrap", **RESIDUALS)  # type: ignore[arg-type]
    d = analyze(data, config).skus[0]
    assert d.policy.safety_stock == 0
    assert "residual quantile below zero: safety stock floored at 0" in d.notes


def test_too_short_for_residuals_falls_back_to_the_demand_bootstrap() -> None:
    # W-2 with a default lead time of 6: P = 7, 8 periods leave no origin from 2.
    settings = {"holdout": 2, "safety_stock_method": "bootstrap", "lead_time": 6}
    demand = analyze_file(WORKED, Config(**settings)).skus[1]  # type: ignore[arg-type]
    residual = analyze_file(WORKED, Config(**settings, **RESIDUALS)).skus[1]  # type: ignore[arg-type]
    assert residual.policy.safety_stock == demand.policy.safety_stock
    assert (
        "too little history for forecast errors over the protection interval: "
        "bootstrap of demand used"
    ) in residual.notes


def test_relative_errors_fall_back_without_a_positive_forecast() -> None:
    def zero(history: Sequence[float], periods: int) -> float | None:
        return 0.0

    config = Config(**RESIDUALS)  # type: ignore[arg-type]
    result = _residual_safety_stock(
        [3, 0, 4, 0, 5, 0], zero, 0.0, 1, (), 0.95, config, random.Random(0), per_period=True
    )
    assert result is not None
    assert result.relative is None
    assert result.safety_stock == 5  # largest two-period total, all forecasts zero
    assert "no positive forecast at any origin: one safety stock for every period" in result.notes


def test_per_period_safety_stock_follows_the_seasonal_forecast() -> None:
    config = Config(
        trend_seasonal=True,
        dynamic_levels=True,
        policy="RS",
        safety_stock_method="bootstrap",
        period_safety_stock=True,
        **RESIDUALS,  # type: ignore[arg-type]
    )
    report = analyze(monthly(trend_seasonal_series()), config)
    s = next(r for r in report.skus if r.sku == "S")
    assert s.method == "hw_additive"
    assert (len(s.safety_stocks), len(s.next_safety_stocks)) == (48, 12)
    assert s.safety_stocks[-1] == pytest.approx(s.policy.safety_stock)
    assert s.levels[-1] == pytest.approx(s.policy.reorder_point)
    # Proportional to the forecast: the peak month holds more than the trough.
    assert max(s.next_safety_stocks) > 1.5 * min(s.next_safety_stocks) > 0
    assert any("relative forecast errors" in note for note in s.notes)
    # W-1 of the worked example picks a level forecast: one safety stock, with a note.
    worked = Config(
        holdout=2,
        trend_seasonal=True,
        dynamic_levels=True,
        safety_stock_method="bootstrap",
        period_safety_stock=True,
        **RESIDUALS,  # type: ignore[arg-type]
    )
    w1 = analyze_file(WORKED, worked).skus[0]
    assert w1.method == "moving_average"
    assert (w1.safety_stocks, w1.next_safety_stocks) == ((), ())
    assert "level forecast picked: one safety stock for every period" in w1.notes
    assert w1.levels == pytest.approx((w1.policy.reorder_point,) * 8)


def test_default_bootstrap_is_unchanged() -> None:
    plain = analyze_file(SYNTHETIC, Config(safety_stock_method="bootstrap"))
    explicit = analyze_file(
        SYNTHETIC, Config(safety_stock_method="bootstrap", bootstrap_source="demand")
    )
    assert plain == explicit
    assert render_json(plain) == render_json(explicit)


@pytest.mark.parametrize(
    ("settings", "message"),
    [
        ({"bootstrap_source": "errors"}, "bootstrap source must be 'demand' or 'residuals'"),
        ({"bootstrap_source": "residuals"}, "only applies to a bootstrap safety stock"),
        (
            {"period_safety_stock": True, "safety_stock_method": "bootstrap"},
            "needs dynamic levels and the residual bootstrap",
        ),
        (
            {
                "period_safety_stock": True,
                "safety_stock_method": "bootstrap",
                "bootstrap_source": "residuals",
            },
            "needs dynamic levels and the residual bootstrap",
        ),
    ],
)
def test_config_errors(settings: dict[str, object], message: str) -> None:
    with pytest.raises(ConfigError, match=message):
        Config(**settings).validate()  # type: ignore[arg-type]
    Config(test_periods=12, **RESIDUALS).validate()  # type: ignore[arg-type]


# --- no leak from the test periods ---------------------------------------------------


def test_no_leak_from_the_test_periods_into_the_residual_bootstrap() -> None:
    series = trend_seasonal_series()
    changed = {sku: values[:36] + [0.0] * 12 for sku, values in series.items()}
    config = Config(
        test_periods=12,
        trend_seasonal=True,
        policy="RS",
        dynamic_levels=True,
        period_safety_stock=True,
        **RESIDUALS,  # type: ignore[arg-type]
    )
    base = analyze(monthly(series), config).out_of_sample
    other = analyze(monthly(changed), config).out_of_sample
    assert base is not None and other is not None
    for a, b in zip(base.skus, other.skus, strict=True):
        assert a.notes == b.notes
        for ra, rb in zip(a.replays, b.replays, strict=True):
            assert (ra.safety_stock, ra.reorder_point) == (rb.safety_stock, rb.reorder_point)
            assert ra.test_levels == rb.test_levels
            assert ra.test_safety_stocks == rb.test_safety_stocks
            assert ra.in_sample == rb.in_sample
    s = next(x for x in base.skus if x.sku == "S").replay("bootstrap")
    assert len(s.test_safety_stocks) == 12 and s.safety_stock > 0


# --- rendering and command line ------------------------------------------------------


def test_markdown_and_json_with_residuals() -> None:
    config = Config(
        test_periods=12,
        trend_seasonal=True,
        dynamic_levels=True,
        safety_stock_method="bootstrap",
        period_safety_stock=True,
        **RESIDUALS,  # type: ignore[arg-type]
    )
    report = analyze(monthly(trend_seasonal_series()), config)
    text = render_markdown(report)
    assert "safety stock: bootstrap of rolling-origin forecast errors" in text
    assert "; one safety stock per period, proportional to the forecast" in text
    assert "| bootstrap (forecast residuals) |" in text
    assert "A safety stock per period is shown the same way" in text
    s = next(r for r in report.skus if r.sku == "S")
    low, high = min(s.next_safety_stocks), max(s.next_safety_stocks)
    assert f"| {s.policy.safety_stock:,.1f} ({low:,.1f} to {high:,.1f}) |" in text
    data = json.loads(render_json(report))
    assert data["settings"]["bootstrap_source"] == "residuals"
    assert data["settings"]["period_safety_stock"] is True
    policy = next(x for x in data["skus"] if x["sku"] == "S")["policy"]
    assert (len(policy["safety_stocks"]), len(policy["next_safety_stocks"])) == (48, 12)
    replays = next(x for x in data["out_of_sample"]["skus"] if x["sku"] == "S")["policies"]
    assert len(replays["bootstrap"]["test_safety_stocks"]) == 12
    assert "test_safety_stocks" not in replays["normal"]
    # T picks naive on the 36 training months: one safety stock, no list.
    trend = next(x for x in data["out_of_sample"]["skus"] if x["sku"] == "T")
    assert trend["forecast_method"] == "naive"
    assert "test_safety_stocks" not in trend["policies"]["bootstrap"]


def test_residuals_only_in_the_out_of_sample_bootstrap() -> None:
    report = analyze_file(SYNTHETIC, Config(test_periods=12, **RESIDUALS))  # type: ignore[arg-type]
    text = render_markdown(report)
    assert "safety-stock sigma: standard deviation of demand" in text  # main policy: normal
    assert "| bootstrap (forecast residuals) |" in text
    assert "one safety stock per period" not in text
    data = json.loads(render_json(report))
    assert data["settings"]["period_safety_stock"] is False


def test_default_json_has_no_new_keys() -> None:
    data = json.loads(render_json(analyze_file(SYNTHETIC, Config(test_periods=12))))
    assert "bootstrap_source" not in data["settings"]
    assert "period_safety_stock" not in data["settings"]
    assert "| bootstrap |" in render_markdown(analyze_file(SYNTHETIC, Config(test_periods=12)))


def test_cli_options(capsys: pytest.CaptureFixture[str]) -> None:
    from inventory_policy_lab.cli import main

    args = [str(SYNTHETIC), "--test-periods", "12", "--bootstrap-source", "residuals"]
    assert main([*args, "--format", "json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["settings"]["bootstrap_source"] == "residuals"
    dynamic = ["--trend-seasonal", "--dynamic-levels", "--period-safety-stock"]
    assert main([*args, *dynamic, "--format", "json"]) == 0
    assert json.loads(capsys.readouterr().out)["settings"]["period_safety_stock"] is True
    assert main([str(SYNTHETIC), "--bootstrap-source", "residuals"]) == 2
    assert "only applies to a bootstrap safety stock" in capsys.readouterr().err
    assert main([*args, "--period-safety-stock"]) == 2
    assert "needs dynamic levels" in capsys.readouterr().err


# --- results quoted in the README and ADR 0008 ---------------------------------------

SOURCES: dict[str, dict[str, Any]] = {
    "demand": {},
    "residuals": RESIDUALS,
    "residuals, per period": {**RESIDUALS, "period_safety_stock": True},
}
POLICIES: dict[str, dict[str, Any]] = {
    "sQ static": {"trend_seasonal": True},
    "sQ dynamic": {"trend_seasonal": True, "dynamic_levels": True},
    "RS dynamic": {"trend_seasonal": True, "policy": "RS", "dynamic_levels": True},
    "RS dynamic, R=3": {
        "trend_seasonal": True,
        "policy": "RS",
        "dynamic_levels": True,
        "review_period": 3,
    },
}


def _results(series: bool) -> dict[str, dict[str, tuple[float, int, float]]]:
    """Out-of-sample totals: (fill rate, stockout periods, avg on hand summed)."""
    out: dict[str, dict[str, tuple[float, int, float]]] = {}
    for name, policy in POLICIES.items():
        row: dict[str, tuple[float, int, float]] = {}
        for source, extra in SOURCES.items():
            if extra.get("period_safety_stock") and not policy.get("dynamic_levels"):
                continue
            config = Config(test_periods=12, **policy, **extra)
            report = (
                analyze(monthly(trend_seasonal_series()), config)
                if series
                else analyze_file(SYNTHETIC, config)
            )
            oos = report.out_of_sample
            assert oos is not None
            methods = ("normal", "bootstrap") if source == "demand" else ("bootstrap",)
            for method in methods:
                t = oos.totals(method, "out_of_sample")
                key = "normal" if method == "normal" else f"bootstrap {source}"
                fill = round(t.fill_rate or 0, 3)
                row[key] = (fill, t.stockout_periods, round(t.average_on_hand, 1))
        out[name] = row
    return out


def test_48_month_series_results_quoted_in_the_readme() -> None:
    assert _results(series=True) == {
        "sQ static": {
            "normal": (0.996, 1, 289.0),
            "bootstrap demand": (0.976, 4, 196.4),
            "bootstrap residuals": (0.984, 3, 185.5),
        },
        "sQ dynamic": {
            "normal": (1.0, 0, 269.9),
            "bootstrap demand": (0.988, 2, 174.8),
            "bootstrap residuals": (0.998, 1, 163.4),
            "bootstrap residuals, per period": (0.998, 1, 159.0),
        },
        "RS dynamic": {
            "normal": (1.0, 0, 105.5),
            "bootstrap demand": (0.893, 22, 41.0),
            "bootstrap residuals": (0.954, 18, 13.1),
            "bootstrap residuals, per period": (0.963, 16, 14.6),
        },
        "RS dynamic, R=3": {
            "normal": (0.999, 1, 439.3),
            "bootstrap demand": (0.904, 10, 247.0),
            "bootstrap residuals": (0.972, 7, 316.9),
            "bootstrap residuals, per period": (0.973, 6, 315.9),
        },
    }


def test_48_month_series_trend_item_quoted_in_the_readme() -> None:
    """The trending item T under (R, S) dynamic, R = 1: the weakness of ADR 0007."""
    quoted = {}
    for source, extra in SOURCES.items():
        config = Config(test_periods=12, **POLICIES["RS dynamic"], **extra)
        oos = analyze(monthly(trend_seasonal_series()), config).out_of_sample
        assert oos is not None
        replay = next(s for s in oos.skus if s.sku == "T").replay("bootstrap")
        sim = replay.out_of_sample
        quoted[source] = (
            round(replay.safety_stock, 1),
            round(sim.fill_rate or 0, 3),
            sim.stockout_periods,
            round(sim.average_on_hand, 1),
        )
    assert quoted == {
        "demand": (0.0, 0.784, 12, 0.0),
        "residuals": (22.0, 0.933, 6, 4.1),
        "residuals, per period": (22.0, 0.933, 6, 4.1),
    }


def test_synthetic_example_results_quoted_in_the_readme() -> None:
    assert _results(series=False) == {
        "sQ static": {
            "normal": (0.944, 11, 885.2),
            "bootstrap demand": (0.946, 12, 712.4),
            "bootstrap residuals": (0.922, 15, 975.8),
        },
        "sQ dynamic": {
            "normal": (0.944, 11, 885.2),
            "bootstrap demand": (0.946, 12, 712.4),
            "bootstrap residuals": (0.922, 15, 975.8),
            "bootstrap residuals, per period": (0.922, 15, 975.8),
        },
        "RS dynamic": {
            "normal": (0.909, 20, 598.6),
            "bootstrap demand": (0.907, 17, 427.9),
            "bootstrap residuals": (0.885, 23, 690.9),
            "bootstrap residuals, per period": (0.885, 23, 690.9),
        },
        "RS dynamic, R=3": {
            "normal": (0.934, 11, 1306.6),
            "bootstrap demand": (0.942, 11, 1032.1),
            "bootstrap residuals": (0.929, 15, 1612.7),
            "bootstrap residuals, per period": (0.929, 15, 1612.7),
        },
    }
