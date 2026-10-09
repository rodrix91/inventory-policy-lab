"""Replay of the (s, Q) policy, checked period by period by hand."""

from __future__ import annotations

import pytest

from inventory_policy_lab import simulate


def test_replay_by_hand() -> None:
    # s = 4, Q = 10, L = 1: an order placed at the end of t arrives at the start of t + 2.
    # t0: 14 on hand, demand 5 -> 9.                 position 9 > 4
    # t1: demand 5 -> 4.                             position 4 <= 4: order 10 (due t3)
    # t2: serve 4 of 5 (stockout) -> net -1.         position 9 > 4
    # t3: +10 -> 9, demand 5 -> 4.                   position 4 <= 4: order 10 (due t5)
    # t4: serve 4 of 5 (stockout) -> net -1.
    result = simulate([5, 5, 5, 5, 5], reorder_point=4, order_quantity=10, lead_time=1)
    assert result.total_demand == 25
    assert result.served_from_stock == 23
    assert result.fill_rate == pytest.approx(0.92)
    assert result.stockout_periods == 2
    assert result.average_on_hand == pytest.approx((9 + 4 + 0 + 4 + 0) / 5)
    assert result.orders_placed == 2
    assert result.max_backorder == 1
    assert result.lead_time_periods == 1


def test_several_orders_when_position_falls_far_below_s() -> None:
    # start with s + Q = 7 on hand; demand 20 serves 7 and leaves net -13, so it takes
    # 10 orders of 2 to lift the position above s (-13 + 20 = 7 > 5); they arrive in t1
    result = simulate([20, 0], reorder_point=5, order_quantity=2, lead_time=0)
    assert result.orders_placed == 10
    assert result.stockout_periods == 1
    assert result.served_from_stock == 7
    assert result.max_backorder == 13


def test_lead_time_rounds_half_up_and_zero_demand_has_no_fill_rate() -> None:
    assert simulate([0, 0], 1, 1, lead_time=1.5).lead_time_periods == 2
    assert simulate([0, 0], 1, 1, lead_time=1.4).lead_time_periods == 1
    result = simulate([0, 0], 1, 1, lead_time=1)
    assert result.fill_rate is None
    assert result.orders_placed == 0
    assert simulate([], 1, 1, 1).average_on_hand == 0


def test_order_quantity_must_be_positive() -> None:
    with pytest.raises(ValueError, match="order_quantity must be positive"):
        simulate([1], 1, 0, 1)
