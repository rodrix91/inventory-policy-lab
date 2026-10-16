"""Demand paths that refit the forecast on bootstrapped histories (ADR 0017)."""

from __future__ import annotations

import json
import random
from collections.abc import Sequence
from dataclasses import replace

import pytest
from conftest import EXAMPLES, run_module
from test_smoothing import monthly, trend_seasonal_series

from inventory_policy_lab import (
    Config,
    ConfigError,
    CostRates,
    FitError,
    SmoothingFit,
    analyze,
    parse_rows,
    read_demand,
    render_json,
    render_markdown,
)
from inventory_policy_lab.analysis import _analyze_sku, _refit_forecasts
from inventory_policy_lab.optimize import block_bootstrap, block_length, bootstrap_histories
from inventory_policy_lab.render import _refit_text
from inventory_policy_lab.validation import _optimized_replay, train_history

SYNTHETIC = EXAMPLES / "demand_synthetic.csv"
SERIES = monthly(trend_seasonal_series())


def _priced(**settings: object) -> Config:
    base: dict[str, object] = {
        "test_periods": 12,
        "trend_seasonal": True,
        "order_cost": 50.0,
        "holding_cost": 1.0,
        "stockout_cost": 10.0,
        "optimize_cost": True,
        "optimize_samples": 20,
        "optimize_paths": "refit",
    }
    base.update(settings)
    return Config(**base)  # type: ignore[arg-type]


# --- the block bootstrap ------------------------------------------------------------


@pytest.mark.parametrize(("errors", "block"), [(0, 1), (1, 1), (7, 2), (8, 2), (27, 3), (34, 3)])
def test_block_length_is_the_rounded_cube_root(errors: int, block: int) -> None:
    assert block_length(errors) == block


def test_block_bootstrap_draws_consecutive_blocks() -> None:
    errors = [1.0, 2.0, 3.0, 4.0, 5.0]
    drawn = block_bootstrap(errors, 7, 2, random.Random(3))
    assert len(drawn) == 7
    # Every full block is two consecutive errors (the last block is cut to one).
    for i in range(0, 6, 2):
        assert drawn[i + 1] == drawn[i] + 1
    # A block longer than the errors is the whole sequence.
    assert block_bootstrap(errors, 5, 9, random.Random(1)) == tuple(errors)
    with pytest.raises(ValueError, match="at least one error"):
        block_bootstrap([], 3, 1, random.Random(1))


def test_bootstrap_histories_move_only_forecast_periods() -> None:
    """Periods 0 and 1 have no forecast and keep their value; the others become their
    forecast plus one of the errors 2, -1, 1 and -30 (floored at zero)."""
    series = [5.0, 6.0, 12.0, 9.0, 11.0, 0.0]
    one_step = [(2, 10.0), (3, 10.0), (4, 10.0), (5, 30.0)]
    histories = bootstrap_histories(series, one_step, 50, random.Random(7))
    assert len(histories) == 50
    errors = {2.0, -1.0, 1.0, -30.0}
    for history in histories:
        assert history[:2] == (5.0, 6.0)
        for t, forecast in one_step:
            assert history[t] == 0.0 or history[t] - forecast in errors
            assert history[t] >= 0.0
    assert len(set(histories)) > 1
    with pytest.raises(ValueError, match="at least two one-step forecasts"):
        bootstrap_histories(series, one_step[:1], 5, random.Random(1))


# --- refitting --------------------------------------------------------------------


def _mean(history: Sequence[float]) -> float:
    return sum(history) / len(history)


def _mean_interval(history: Sequence[float], periods: int) -> float | None:
    return periods * _mean(history) if len(history) >= 3 else None


def test_refit_of_a_level_method_is_flat() -> None:
    series = [10.0, 12.0, 8.0, 11.0, 9.0, 13.0]
    refits, failures = _refit_forecasts(
        series, _mean_interval, None, _mean, (10.0, 10.0, 10.0), 30, random.Random(2)
    )
    assert failures == 0 and len(refits) == 30
    assert all(len(r) == 3 and r[0] == r[1] == r[2] for r in refits)
    assert len({r[0] for r in refits}) > 1


def test_too_few_one_step_forecasts_refit_nothing() -> None:
    assert _refit_forecasts(
        [1.0, 2.0, 3.0, 4.0], _mean_interval, None, _mean, (1.0,), 10, random.Random(1)
    ) == ((), 0)


def test_failed_refits_keep_the_training_forecast() -> None:
    calls = {"n": 0}

    def flaky(history: Sequence[float]) -> SmoothingFit:
        calls["n"] += 1
        if calls["n"] % 2:
            raise FitError("no valid fit")
        return SmoothingFit("holt_damped", 0.5, 0.0, 1.0, None, _mean(history), 0.0, (), 0.0)

    series = [10.0, 12.0, 8.0, 11.0, 9.0, 13.0]
    refits, failures = _refit_forecasts(
        series, _mean_interval, flaky, None, (99.0, 99.0), 10, random.Random(5)
    )
    assert failures == 5
    assert sum(r == (99.0, 99.0) for r in refits) == 5
    assert all(r[0] == r[1] for r in refits)


# --- the report ---------------------------------------------------------------------


def test_every_sku_is_searched_on_refit_paths() -> None:
    for data, count in ((SERIES, 3), (read_demand(SYNTHETIC), 11)):
        for policy in ("sQ", "RsS"):
            oos = analyze(data, _priced(policy=policy)).out_of_sample
            assert oos is not None and oos.optimize_paths == "refit"
            assert len(oos.skus) == count
            for s in oos.skus:
                assert s.optimized is not None
                assert s.optimized.paths == "refit"
                assert s.optimized.search.samples == 20


def test_refit_paths_are_reproducible_and_differ_from_plain_paths() -> None:
    first = analyze(SERIES, _priced()).out_of_sample
    again = analyze(SERIES, _priced()).out_of_sample
    plain = analyze(SERIES, _priced(optimize_paths="forecast")).out_of_sample
    assert first is not None and again is not None and plain is not None
    assert [s.optimized for s in first.skus] == [s.optimized for s in again.skus]
    assert [s.optimized.search for s in first.skus if s.optimized] != [
        s.optimized.search for s in plain.skus if s.optimized
    ]
    for s in plain.skus:
        assert s.optimized is not None and s.optimized.paths == "forecast"


def test_the_training_fit_carries_one_refit_per_path() -> None:
    data = SERIES
    history = data.skus[2]
    train = train_history(history, data.calendar[:36])
    assert train is not None
    fitted = _analyze_sku(train, _priced(), "A", 1.0, horizon=12, optimize_inputs=True)
    assert fitted.method in ("holt_damped", "hw_additive", "hw_multiplicative")
    assert len(fitted.refit_forecasts) == 20
    assert all(len(f) == 12 for f in fitted.refit_forecasts)
    assert fitted.refit_forecasts != (fitted.next_forecasts,) * 20
    plain = _analyze_sku(
        train, _priced(optimize_paths="forecast"), "A", 1.0, horizon=12, optimize_inputs=True
    )
    assert plain.refit_forecasts == () and plain.refit_failures == 0
    assert plain.next_forecasts == fitted.next_forecasts
    assert plain.forecast_errors == fitted.forecast_errors


@pytest.mark.parametrize("factor", [0.0, 10.0])
def test_no_test_demand_reaches_the_refit_paths(factor: float) -> None:
    """The refits see the training periods only: changing the test year changes the
    score of the optimised policy, never the search."""
    config = _priced(policy="RsS")
    base = analyze(SERIES, config).out_of_sample
    rows = [["sku", "period", "quantity"]]
    for h in SERIES.skus:
        for i, (p, q) in enumerate(zip(h.periods, h.demand, strict=True)):
            rows.append([h.sku, p, str(q * factor if i >= 36 else q)])
    changed = analyze(parse_rows(rows), config).out_of_sample
    assert base is not None and changed is not None
    for a, b in zip(base.skus, changed.skus, strict=True):
        assert a.optimized is not None and b.optimized is not None
        assert a.optimized.search == b.optimized.search
        assert a.optimized.test_levels == b.optimized.test_levels
        assert a.optimized.out_of_sample != b.optimized.out_of_sample


def test_too_few_errors_keep_the_plain_paths() -> None:
    data = read_demand(SYNTHETIC)
    history = data.skus[0]
    train = train_history(history, data.calendar[:12])
    assert train is not None
    config = _priced()
    fitted = _analyze_sku(train, config, "A", 1.0, horizon=12, optimize_inputs=True)
    assert fitted.refit_forecasts
    found = _optimized_replay(history, train, fitted, config, CostRates(50, 1, 10))
    assert found.paths == "refit"
    sparse = replace(fitted, forecast_errors=(1.0,))
    found = _optimized_replay(history, train, sparse, config, CostRates(50, 1, 10))
    assert (found.paths, found.error_source, found.refit_failures) == (
        "forecast",
        "demand deviations",
        0,
    )


@pytest.mark.parametrize(
    ("settings", "message"),
    [
        ({"optimize_paths": "model"}, "optimize paths must be one of forecast, refit"),
        ({"optimize_cost": False}, "refit demand paths feed the cost search"),
    ],
)
def test_invalid_settings(settings: dict[str, object], message: str) -> None:
    with pytest.raises(ConfigError, match=message):
        _priced(**settings).validate()


def test_json_and_markdown() -> None:
    report = analyze(SERIES, _priced(policy="RsS"))
    data = json.loads(render_json(report))
    assert data["settings"]["optimize_paths"] == "refit"
    optimized = data["out_of_sample"]["optimized"]
    assert optimized["paths"] == {
        "kind": "refit",
        "refitted_skus": 3,
        "block_length": {"S": 2, "T": 3, "TS": 2},
    }
    assert {(s["paths"], s["refit_failures"]) for s in optimized["skus"]} == {("refit", 0)}
    text = render_markdown(report)
    assert "Refit paths: instead, each path rebuilds the training history" in text
    assert "(3 of 3 SKU(s) refitted)." in text
    off = analyze(SERIES, _priced(optimize_paths="forecast"))
    off_data = json.loads(render_json(off))
    assert "optimize_paths" not in off_data["settings"]
    assert "paths" not in off_data["out_of_sample"]["optimized"]
    assert "paths" not in off_data["out_of_sample"]["optimized"]["skus"][0]
    assert "Refit paths" not in render_markdown(off)


def test_refit_text_names_plain_paths_and_failed_refits() -> None:
    oos = analyze(SERIES, _priced()).out_of_sample
    assert oos is not None
    first, second, third = oos.skus
    assert first.optimized is not None and second.optimized is not None
    skus = (
        replace(first, optimized=replace(first.optimized, paths="forecast")),
        replace(second, optimized=replace(second.optimized, refit_failures=4)),
        third,
    )
    text = _refit_text(replace(oos, skus=skus))
    assert text.endswith(
        "(2 of 3 SKU(s) refitted; the others had fewer than two one-step errors and keep "
        "the plain paths; 4 refit(s) without a valid fit kept the training forecast)."
    )


def test_cli() -> None:
    common = ["--test-periods", "12", "--stockout-cost", "10", "--holding-cost", "1"]
    proc = run_module(
        str(SYNTHETIC),
        *common,
        "--optimize-cost",
        "--optimize-samples",
        "10",
        "--optimize-paths",
        "refit",
        "--format",
        "json",
    )
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["out_of_sample"]["optimized"]["paths"]["kind"] == "refit"
    alone = run_module(str(SYNTHETIC), *common, "--optimize-paths", "refit")
    assert alone.returncode == 2 and "need --optimize-cost" in alone.stderr
