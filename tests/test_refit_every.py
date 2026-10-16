"""Rolling origin refitted every K test periods (ADR 0011): by hand, no leak, limits, results."""

from __future__ import annotations

import json
from dataclasses import replace
from functools import cache
from typing import Any

import pytest
from conftest import EXAMPLES
from test_rolling import HAND, HAND_CONFIG
from test_smoothing import integer, monthly, trend_seasonal_series

from inventory_policy_lab import (
    Config,
    ConfigError,
    OutOfSampleReport,
    analyze,
    analyze_file,
    render_json,
    render_markdown,
)
from inventory_policy_lab import analysis as analysis_module
from inventory_policy_lab.cli import main
from inventory_policy_lab.reader import SkuHistory

SYNTHETIC = EXAMPLES / "demand_synthetic.csv"


def test_refit_every_two_periods_by_hand(monkeypatch: pytest.MonkeyPatch) -> None:
    """The case of ``test_rolling_origin_by_hand`` (train 10 10 10 10, test 20 30 30), K = 2.

    Origin 4 (sees 10 10 10 10) decides test periods 4 and 5: s = 10, Q = 10, SS 0.
    Origin 6 (sees ... 20 30) decides period 6: s = 43.7618, Q = 30 (worked there).
    Test: t4: 10 due + 10 on hand = 20, serve 20 -> 0, order 10 + 10. t5: 20, serve
    30 -> -10 (out); s is still 10, so 3 x 10. t6: 30 - 10 = 20, serve 30 -> -10 (out).
    Served 60 of 80: 75% and 2 stockout periods, the fixed origin's result: the
    refit that would have raised s at the end of period 5 (origin 5) is skipped.
    """
    real = analysis_module._analyze_sku
    seen: list[tuple[int, int]] = []

    def recording(history: SkuHistory, config: Config, *args: Any, **kwargs: Any) -> Any:
        if "horizon" in kwargs and config.safety_stock_method == "normal":
            seen.append((len(history.demand), kwargs["horizon"]))
        return real(history, config, *args, **kwargs)

    monkeypatch.setattr(analysis_module, "_analyze_sku", recording)
    oos = analyze(integer(HAND), replace(HAND_CONFIG, refit_every=2)).out_of_sample
    assert oos is not None and oos.refit_every == 2
    # The fixed fit (horizon 3), then the origins at 4 (2 periods) and 6 (1 period).
    assert seen == [(4, 3), (4, 2), (6, 1)]
    normal = oos.skus[0].rolling_replay("normal")
    assert normal.forecast_methods == ("naive",) * 3
    assert normal.levels == pytest.approx((10, 10, 43.7618), abs=1e-4)
    assert normal.order_quantities == (10, 10, 30)
    result = normal.out_of_sample
    assert (result.fill_rate, result.stockout_periods) == (0.75, 2)


def test_refits_never_see_the_periods_they_decide(monkeypatch: pytest.MonkeyPatch) -> None:
    # Test periods 4 to 6; K = 2. The sentinel in period 5 is decided by origin 4,
    # which must not see it; origin 6 may.
    real = analysis_module._analyze_sku
    seen: list[int] = []

    def recording(history: SkuHistory, config: Config, *args: Any, **kwargs: Any) -> Any:
        if kwargs.get("horizon") == 2:
            assert 999 not in history.demand
            seen.append(len(history.demand))
        return real(history, config, *args, **kwargs)

    monkeypatch.setattr(analysis_module, "_analyze_sku", recording)
    data = integer({"A": [10.0, 10.0, 10.0, 10.0, 20.0, 999.0, 30.0]})
    analyze(data, replace(HAND_CONFIG, refit_every=2))
    assert seen == [4, 4]  # normal and bootstrap


@cache
def _series(cut: int | None, every: int) -> OutOfSampleReport:
    """48-month series, (R, S) dynamic R = 1, residual bootstrap, per-period SS."""
    series = trend_seasonal_series()
    if cut is not None:
        series = {sku: values[:cut] + [0.0] * (48 - cut) for sku, values in series.items()}
    config = Config(
        test_periods=12,
        trend_seasonal=True,
        policy="RS",
        dynamic_levels=True,
        bootstrap_source="residuals",
        period_safety_stock=True,
        rolling_origin=True,
        refit_every=every,
    )
    oos = analyze(monthly(series), config).out_of_sample
    assert oos is not None
    return oos


def test_no_leak_from_later_periods() -> None:
    # K = 3: origins 36, 39, 42, 45. Zeroing periods 40 to 47 cannot move what
    # origins 36 and 39 decided (test periods 0 to 5); the origin at 42 does see it.
    base, other = _series(None, 3), _series(40, 3)
    moved = False
    for a, b in zip(base.skus, other.skus, strict=True):
        for qa, qb in zip(a.rolling, b.rolling, strict=True):
            assert qa.forecast_methods[:6] == qb.forecast_methods[:6]
            assert qa.levels[:6] == qb.levels[:6]
            assert qa.safety_stocks[:6] == qb.safety_stocks[:6]
            moved = moved or qa.levels[6:] != qb.levels[6:]
    assert moved


def test_dynamic_decisions_are_the_refits_forecasts_ahead() -> None:
    # Between refits the levels keep following the forecast of the last refit:
    # the block of origin 36 is the fixed origin's first 3 test levels.
    every3, every1 = _series(None, 3), _series(None, 1)
    for s3, s1 in zip(every3.skus, every1.skus, strict=True):
        for r3, r1, fixed in zip(s3.rolling, s1.rolling, s3.replays, strict=True):
            assert r3.levels[:3] == fixed.test_levels[:3]
            assert r3.levels[::3] == r1.levels[::3]  # same refits at 36, 39, 42, 45
            for start in range(0, 12, 3):
                assert len(set(r3.forecast_methods[start : start + 3])) == 1


def test_static_decisions_are_held_between_refits() -> None:
    config = Config(
        test_periods=12,
        trend_seasonal=True,
        bootstrap_source="residuals",
        rolling_origin=True,
        refit_every=5,
    )
    oos = analyze_file(SYNTHETIC, config).out_of_sample
    assert oos is not None
    for s in oos.skus:
        for r in s.rolling:
            for block in (slice(0, 5), slice(5, 10), slice(10, 12)):
                assert len(set(r.levels[block])) == 1
                assert len(set(r.order_quantities[block])) == 1
                assert len(set(r.safety_stocks[block])) == 1
                assert len(set(r.forecast_methods[block])) == 1


@pytest.mark.parametrize(
    "settings",
    [
        {},
        {"policy": "RS", "dynamic_levels": True},
        {"policy": "RS", "dynamic_levels": True, "period_safety_stock": True},
        {"dynamic_levels": True, "review_period": 2},
    ],
)
def test_a_refit_period_of_the_whole_test_is_the_fixed_origin(settings: dict[str, Any]) -> None:
    for every in (12, 20):
        config = Config(
            test_periods=12,
            trend_seasonal=True,
            bootstrap_source="residuals",
            rolling_origin=True,
            refit_every=every,
            **settings,
        )
        oos = analyze_file(SYNTHETIC, config).out_of_sample
        assert oos is not None
        for s in oos.skus:
            for fixed, rolling in zip(s.replays, s.rolling, strict=True):
                assert rolling.out_of_sample == fixed.out_of_sample


def test_every_one_is_the_rolling_origin_byte_for_byte(
    capsys: pytest.CaptureFixture[str],
) -> None:
    args = [str(SYNTHETIC), "--test-periods", "12", "--trend-seasonal", "--rolling-origin"]
    for fmt in ("markdown", "json"):
        assert main([*args, "--format", fmt]) == 0
        default = capsys.readouterr().out
        assert main([*args, "--format", fmt, "--refit-every", "1"]) == 0
        assert capsys.readouterr().out == default
    assert '"refit_every"' not in default


def test_options_and_reports(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(ConfigError, match="at least 1 period, got 0"):
        Config(test_periods=3, rolling_origin=True, refit_every=0).validate()
    with pytest.raises(ConfigError, match="applies to the rolling-origin replay"):
        Config(test_periods=3, refit_every=3).validate()
    assert main([str(SYNTHETIC), "--test-periods", "12", "--refit-every", "3"]) == 2
    assert "--rolling-origin" in capsys.readouterr().err

    report = analyze(integer(HAND), replace(HAND_CONFIG, refit_every=2))
    text = render_markdown(report)
    assert "At the start of the first test period and then every 2 test periods" in text
    assert "Each refit decides its own period and the next 1" in text
    assert "| normal | 75.0% / 75.0% | 2 / 2 | 0.0 / 0.0 |" in text
    data = json.loads(render_json(report))
    assert (data["settings"]["rolling_origin"], data["settings"]["refit_every"]) == (True, 2)
    policy = data["out_of_sample"]["rolling_origin"]["skus"][0]["policies"]["normal"]
    assert policy["reorder_points"] == [10.0, 10.0, 43.7618]


# --- results quoted in the README and ADR 0011 ---------------------------------------


def _rolling(oos: OutOfSampleReport) -> tuple[tuple[float, int, float], ...]:
    """(fill rate, stockout periods, avg on hand summed) of normal, then bootstrap."""
    return tuple(
        (round(t.fill_rate or 0, 3), t.stockout_periods, round(t.average_on_hand, 1))
        for t in (oos.rolling_totals("normal"), oos.rolling_totals("bootstrap"))
    )


def _table(data: Any) -> dict[str, dict[int, tuple[tuple[float, int, float], ...]]]:
    out: dict[str, dict[int, tuple[tuple[float, int, float], ...]]] = {}
    for name, extra in (("sQ", {}), ("RS", {"policy": "RS", "dynamic_levels": True})):
        out[name] = {}
        for every in (1, 3, 6, 12):
            config = Config(
                test_periods=12,
                trend_seasonal=True,
                bootstrap_source="residuals",
                rolling_origin=True,
                refit_every=every,
                **extra,  # type: ignore[arg-type]
            )
            oos = analyze(data, config).out_of_sample
            assert oos is not None
            out[name][every] = _rolling(oos)
    return out


def test_48_month_series_results_quoted_in_the_readme() -> None:
    assert _table(monthly(trend_seasonal_series())) == {
        "sQ": {
            1: ((1.0, 0, 321.6), (0.996, 1, 220.9)),
            3: ((0.996, 1, 306.1), (0.987, 2, 195.4)),
            6: ((0.996, 1, 302.3), (0.987, 2, 188.3)),
            12: ((0.996, 1, 289.0), (0.984, 3, 185.5)),
        },
        "RS": {
            1: ((1.0, 0, 149.3), (0.994, 4, 36.4)),
            3: ((1.0, 0, 139.9), (0.988, 7, 29.2)),
            6: ((1.0, 0, 126.5), (0.978, 13, 22.5)),
            12: ((1.0, 0, 105.5), (0.954, 18, 13.1)),
        },
    }


def test_synthetic_example_results_quoted_in_the_readme() -> None:
    assert _table(analyze_file(SYNTHETIC).data) == {
        "sQ": {
            1: ((0.998, 4, 932.4), (0.985, 9, 913.7)),
            3: ((0.977, 6, 930.7), (0.957, 10, 1026.2)),
            6: ((0.97, 8, 941.6), (0.946, 12, 1004.9)),
            12: ((0.944, 11, 885.2), (0.922, 15, 975.8)),
        },
        "RS": {
            1: ((0.973, 10, 627.5), (0.96, 14, 678.2)),
            3: ((0.956, 12, 626.1), (0.937, 16, 708.1)),
            6: ((0.939, 18, 617.8), (0.913, 22, 702.1)),
            12: ((0.909, 20, 598.6), (0.885, 23, 690.9)),
        },
    }
