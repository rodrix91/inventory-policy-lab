"""Out-of-sample replay: the split, the absence of leakage, and numbers checked by hand."""

from __future__ import annotations

import json

import pytest
from conftest import EXAMPLES

from inventory_policy_lab import (
    Config,
    ConfigError,
    HistoryError,
    SkuHistory,
    analyze,
    analyze_file,
    out_of_sample_replay,
    parse_rows,
    render_json,
    render_markdown,
    train_history,
)
from inventory_policy_lab.reader import DemandData


def data_from(table: dict[str, list[float]]) -> DemandData:
    """Integer periods 1..n per SKU, ending together at the file's last period."""
    last = max(len(demand) for demand in table.values())
    rows = [["sku", "period", "quantity"]]
    for sku, demand in table.items():
        start = last - len(demand) + 1
        rows += [[sku, str(start + i), str(q)] for i, q in enumerate(demand)]
    return parse_rows(rows)


def test_constant_training_then_a_spike_by_hand() -> None:
    """Train on 4 periods of 10, test on 10 then 30 (holdout 2, L = 1, R = 1, cover 1).

    Fit: constant history, so every method forecasts 10 with zero error and naive
    wins the tie; sigma is 0, so the normal safety stock is 0, and every bootstrap
    interval sums to 2 x 10 = 20, so its safety stock is 0 too. Both policies are
    s = 10 x (1 + 1) = 20 and Q = 10.

    Replay, starting with s + Q = 30 on hand (an order at the end of t arrives at t + 2):
    t0: 30 - 10 = 20, position 20 <= 20: order (due t2).
    t1: 20 - 10 = 10, position 20: order (due t3).
    t2: +10 - 10 = 10, order (due t4).  t3: +10 - 10 = 10, order (due t5).
    In-sample (t0..t3): demand 40, all served, average on hand (20 + 10 + 10 + 10) / 4.
    t4: +10 - 10 = 10, position 20: order (due t6).
    t5: +10 = 20, serves 20 of 30 (stockout), net -10, position 0: three orders.
    Out-of-sample (t4, t5): demand 40, served 30, average on hand (10 + 0) / 2, backorder 10.
    """
    data = data_from({"a": [10, 10, 10, 10, 10, 30]})
    report = out_of_sample_replay(data, Config(holdout=2, test_periods=2))
    assert report.train_calendar == ("1", "2", "3", "4")
    assert report.test_calendar == ("5", "6")
    assert report.skipped == ()
    (sku,) = report.skus
    assert (sku.train_periods, sku.test_periods, sku.forecast_method, sku.forecast) == (
        4,
        2,
        "naive",
        10,
    )
    assert [r.method for r in sku.replays] == ["normal", "bootstrap"]
    for replay in sku.replays:
        assert (replay.safety_stock, replay.reorder_point, replay.order_quantity) == (0, 20, 10)
        inside, outside = replay.in_sample, replay.out_of_sample
        assert (inside.periods, inside.total_demand, inside.fill_rate) == (4, 40, 1)
        assert inside.average_on_hand == pytest.approx(12.5)
        assert (outside.periods, outside.total_demand, outside.served_from_stock) == (2, 40, 30)
        assert outside.fill_rate == pytest.approx(0.75)
        assert outside.stockout_periods == 1
        assert outside.average_on_hand == pytest.approx(5)
        assert outside.max_backorder == 10
        assert outside.orders_placed == 4
    totals = report.totals("normal", "out_of_sample")
    assert (totals.total_demand, totals.served_from_stock, totals.stockout_periods) == (40, 30, 1)
    assert totals.fill_rate == pytest.approx(0.75)
    assert totals.average_on_hand == pytest.approx(5)


def test_test_periods_do_not_leak_into_the_fit() -> None:
    lumpy = [0.0, 0, 40, 0, 0, 0, 90, 0, 0, 55, 0, 0]
    smooth = [10.0, 12, 9, 11, 10, 13, 9, 10, 12, 11, 10, 12]
    config = Config(holdout=4, test_periods=4)
    base = out_of_sample_replay(data_from({"a": smooth, "b": lumpy}), config)
    changed = out_of_sample_replay(
        data_from({"a": smooth[:8] + [99, 0, 99, 0], "b": lumpy[:8] + [500, 0, 0, 500]}), config
    )
    for before, after in zip(base.skus, changed.skus, strict=True):
        assert (before.abc, before.category, before.forecast) == (
            after.abc,
            after.category,
            after.forecast,
        )
        for old, new in zip(before.replays, after.replays, strict=True):
            assert (old.safety_stock, old.reorder_point, old.order_quantity) == (
                new.safety_stock,
                new.reorder_point,
                new.order_quantity,
            )
            assert old.in_sample == new.in_sample
            assert old.out_of_sample != new.out_of_sample


def test_train_history_drops_later_lead_times_and_late_skus() -> None:
    rows = [["sku", "period", "quantity", "lead_time"]]
    rows += [["a", str(i), "10", {1: "2", 6: "4"}.get(i, "")] for i in range(1, 9)]
    rows += [["late", "7", "3", "1"], ["late", "8", "5", ""]]
    a, late = parse_rows(rows).skus
    train_calendar = ("1", "2", "3", "4", "5", "6")
    assert train_history(late, train_calendar) is None
    train = train_history(a, ("1", "2", "3", "4"))
    assert train is not None
    assert train.demand == (10, 10, 10, 10) and train.periods == ("1", "2", "3", "4")
    assert (train.lead_times, train.lead_time_periods) == ((2.0,), ("1",))
    undated = SkuHistory("x", ("1", "2", "3"), (1.0, 2.0, 3.0), None, (3.0,), 1)
    kept = train_history(undated, ("1", "2"))
    assert kept is not None
    assert (kept.demand, kept.lead_times, kept.filled_periods) == ((1.0, 2.0), (3.0,), 0)


def test_late_and_short_skus_in_the_replay() -> None:
    smooth = [10.0, 12, 9, 11, 10, 13, 9, 10, 12, 11]
    data = data_from({"a": smooth, "short": [4.0, 6, 5, 7, 6], "late": [3.0, 4]})
    report = out_of_sample_replay(data, Config(holdout=2, test_periods=3))
    assert report.skipped == ("late",)
    short = next(s for s in report.skus if s.sku == "short")
    assert short.train_periods == 2
    assert any("no backtest" in note for note in short.notes)
    assert all(note.count("no backtest") <= 1 for note in short.notes)
    assert len(set(short.notes)) == len(short.notes)  # notes of both fits, not repeated


def test_training_window_must_fit_the_holdout() -> None:
    data = data_from({"a": [10.0] * 10})
    with pytest.raises(HistoryError, match="leave 2 for training") as excinfo:
        analyze(data, Config(holdout=6, test_periods=8))
    assert excinfo.value.exit_code == 5
    with pytest.raises(HistoryError, match="leave 0 for training"):
        analyze(data, Config(holdout=2, test_periods=12))
    with pytest.raises(ConfigError, match="test periods cannot be negative"):
        analyze(data, Config(test_periods=-1))


def test_off_by_default() -> None:
    report = analyze(data_from({"a": [10.0] * 10}), Config(holdout=2))
    assert report.out_of_sample is None
    assert "out_of_sample" not in report.to_dict()
    assert report.to_dict()["settings"]["test_periods"] == 0
    assert "Out-of-sample" not in render_markdown(report)


def test_synthetic_example_in_and_out_of_sample() -> None:
    report = analyze_file(EXAMPLES / "demand_synthetic.csv", Config(test_periods=12))
    oos = report.out_of_sample
    assert oos is not None
    # The numbers quoted in the README's "Out-of-sample replay" section and ADR 0005.
    assert (oos.train_calendar[-1], oos.test_calendar[0], oos.skipped) == (
        "2024-12",
        "2025-01",
        ("SKU-011",),
    )
    summary = {
        (method, sample): oos.totals(method, sample)
        for method in ("normal", "bootstrap")
        for sample in ("in_sample", "out_of_sample")
    }
    assert {
        key: (round(t.fill_rate or 0, 3), t.stockout_periods, round(t.average_on_hand, 1))
        for key, t in summary.items()
    } == {
        ("normal", "in_sample"): (0.988, 4, 1042.4),
        ("normal", "out_of_sample"): (0.944, 11, 885.2),
        ("bootstrap", "in_sample"): (0.999, 1, 864.4),
        ("bootstrap", "out_of_sample"): (0.946, 12, 712.4),
    }
    by_sku = {s.sku: s for s in oos.skus}
    rates = {
        sku: tuple(
            round(by_sku[sku].replay(m).out_of_sample.fill_rate or 0, 3)
            for m in ("normal", "bootstrap")
        )
        for sku in ("SKU-003", "SKU-004", "SKU-008")
    }
    assert rates == {
        "SKU-003": (0.829, 0.944),
        "SKU-004": (0.797, 0.677),
        "SKU-008": (0.859, 1.0),
    }
    assert (by_sku["SKU-003"].category, by_sku["SKU-004"].category) == ("smooth", "smooth")


def test_rendered_out_of_sample_section() -> None:
    report = analyze_file(EXAMPLES / "demand_synthetic.csv", Config(test_periods=12))
    text = render_markdown(report)
    assert "## Out-of-sample replay (train 2024-01 to 2024-12, test 2025-01 to 2025-12)" in text
    assert "| normal | 98.8% | 94.4% | 4 | 11 | 1,042.4 | 885.2 |" in text
    assert "| bootstrap | 99.9% | 94.6% | 1 | 12 | 864.4 | 712.4 |" in text
    assert "no history before 2025-01): SKU-011." in text
    data = json.loads(render_json(report))
    oos = data["out_of_sample"]
    assert data["settings"]["test_periods"] == 12
    assert oos["train"] == {"periods": 12, "first_period": "2024-01", "last_period": "2024-12"}
    assert oos["test"]["periods"] == 12 and oos["skipped_skus"] == ["SKU-011"]
    assert oos["summary"]["bootstrap"]["out_of_sample"]["stockout_periods"] == 12
    first = oos["skus"][0]
    assert set(first["policies"]) == {"normal", "bootstrap"}
    assert set(first["policies"]["normal"]["out_of_sample"]) >= {"fill_rate", "average_on_hand"}

    small = analyze(data_from({"a": [10, 10, 10, 10, 10, 30]}), Config(holdout=2, test_periods=2))
    assert "no history before" not in render_markdown(small)
