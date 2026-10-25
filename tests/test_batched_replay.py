"""Large (s, Q) demand must not require one Python loop per lot."""

from __future__ import annotations

import math
from pathlib import Path

import pytest
from conftest import run_module, write_csv

from inventory_policy_lab import DataError, simulate
from inventory_policy_lab.simulate import _Ledger, _review_sq


def test_large_number_of_lots_replenishes_in_one_batch() -> None:
    # Initial stock = 7; demand = 2,000,000. Exactly 1,000,000 lots of 2
    # raise the position from -1,999,993 to 7 (> reorder threshold 5).
    replay = simulate([2_000_000, 0], reorder_point=5, order_quantity=2, lead_time=0)
    assert replay.orders_placed == 1_000_000
    assert replay.stockout_periods == 1
    assert replay.served_from_stock == 7
    assert replay.max_backorder == 1_999_993
    assert replay.total_demand == 2_000_000
    assert replay.average_on_hand == pytest.approx(3.5)
    assert replay.lead_time_periods == 0


def test_batching_preserves_warmup_and_delayed_arrivals() -> None:
    # The million orders in the warm-up are not charged to the scored period,
    # and reach the stock only after the configured lead time.
    replay = simulate(
        [2_000_000, 0, 3],
        reorder_point=5,
        order_quantity=2,
        lead_time=1,
        warmup=1,
    )
    assert replay.orders_placed == 1
    assert replay.periods == 2
    assert replay.total_demand == 3
    assert replay.served_from_stock == 3
    assert replay.max_backorder == 1_999_993
    assert replay.stockout_periods == 0


def test_batching_boundary_and_ordinary_order_counts_are_unchanged() -> None:
    for count in (0, 1, 17, 256, 257, 300):
        # s = 5, Q = 2, starting stock = 7. An exact count of 2-unit lots
        # is required to replace an even-sized demand.
        replay = simulate([2 * count, 0], reorder_point=5, order_quantity=2, lead_time=0)
        assert replay.orders_placed == count
        assert replay.stockout_periods == (1 if count > 3 else 0)


def test_dynamic_order_sizes_and_fractional_small_lots_remain_compatible() -> None:
    replay = simulate(
        [1.5, 3.5, 0, 0],
        reorder_point=[0.5, 0.5, 0.5, 0.5],
        order_quantity=[0.5, 2.0, 0.25, 0.25],
        lead_time=0,
        warmup=2,
    )
    assert replay.orders_placed == 0
    assert replay.periods == 2
    assert math.isfinite(replay.average_on_hand)


def test_rejects_sub_ulp_lot_sizes_instead_of_hanging() -> None:
    with pytest.raises(DataError, match="cannot advance the inventory position"):
        simulate([1e30], reorder_point=0, order_quantity=1, lead_time=0)


def test_rejects_order_counts_beyond_reliable_float_integer_precision() -> None:
    with pytest.raises(DataError, match="too many lots"):
        simulate([1e20], reorder_point=1e20, order_quantity=1, lead_time=0)


def test_cli_returns_data_error_without_overwriting_old_output(tmp_path: Path) -> None:
    csv = tmp_path / "very-high-demand.csv"
    rows = ["sku,period,quantity,unit_cost"]
    rows.extend(f"S1,{period},1e130,1" for period in range(1, 9))
    write_csv(csv, "\n".join(rows) + "\n")
    output = tmp_path / "existing-report.json"
    output.write_text('{"preserve": true}\n', encoding="utf-8")
    process = run_module(
        str(csv),
        "--ordering-cost",
        "1e180",
        "--holding-rate",
        "1e160",
        "--holdout",
        "2",
        "--format",
        "json",
        "-o",
        str(output),
    )
    assert process.returncode == 4
    assert ("too many lots" in process.stderr or "cannot advance" in process.stderr)
    assert "Traceback" not in process.stderr
    assert output.read_text(encoding="utf-8") == '{"preserve": true}\n'


def test_batch_corrects_a_rounded_down_lot_estimate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exercise the defensive extra-lot correction without costly loops."""
    monkeypatch.setitem(_review_sq.__globals__, "_BATCH_AFTER", 0)
    monkeypatch.setattr(math, "floor", lambda _: -1)
    ledger = _Ledger(net=0.0, warmup=0, arrivals={})
    _review_sq(ledger, 0, level=0, quantity=1, lead=0)
    assert ledger.orders == 1
    assert ledger.arrivals == {1: 1.0}


def test_batch_rejects_a_badly_underestimated_ratio(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(_review_sq.__globals__, "_BATCH_AFTER", 0)
    monkeypatch.setattr(math, "floor", lambda _: 0)
    ledger = _Ledger(net=-100.0, warmup=0, arrivals={})
    with pytest.raises(DataError, match="cannot advance the inventory position"):
        _review_sq(ledger, 0, level=0, quantity=1, lead=0)
    assert ledger.orders == 0


def test_batch_corrects_a_rounded_up_lot_estimate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(_review_sq.__globals__, "_BATCH_AFTER", 0)
    monkeypatch.setattr(math, "floor", lambda _: 1)
    ledger = _Ledger(net=0.0, warmup=0, arrivals={})
    _review_sq(ledger, 0, level=0, quantity=1, lead=0)
    assert ledger.orders == 1
    assert ledger.arrivals == {1: 1.0}


def test_batch_detects_nonfinite_aggregate_arrival(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(_review_sq.__globals__, "_BATCH_AFTER", 0)
    # Emulate an extreme rounding estimate to exercise the numerical guard
    # without constructing an array or iterating through astronomical lots.
    monkeypatch.setattr(math, "floor", lambda _: 10**307)
    ledger = _Ledger(net=0.0, warmup=0, arrivals={})
    with pytest.raises(DataError, match="arrival exceeds numeric range"):
        _review_sq(ledger, 0, level=0, quantity=1e10, lead=0)
    assert ledger.orders == 0
