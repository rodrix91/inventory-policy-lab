"""Replay a demand history under an (s, Q) policy.

The formulas in :mod:`inventory_policy_lab.policy` assume continuous review
and normal demand. Replaying the actual history shows what the policy would
have achieved on this data, period by period:

1. At the start of period ``t`` the orders due in ``t`` arrive.
2. Demand of ``t`` is served from the stock on hand; the rest is backordered
   (served later, first, from the next arrivals).
3. At the end of ``t``, while the inventory position (net stock plus orders on
   the way) is at or below ``s``, an order of ``Q`` is placed. It arrives at
   the start of period ``t + L + 1``, so it covers the demand of the ``L``
   periods after the order, which is what the reorder point protects.

The lead time is rounded to whole periods (half up). The run starts with
``s + Q`` units on hand and nothing on order.

With ``warmup = k`` the first ``k`` periods are replayed but not scored: the
metrics cover only the periods after them, which start from the stock, the
backorders and the orders on the way that the policy left at the end of the
warm-up. The out-of-sample replay uses it to score a policy on the test
periods only (ADR 0005).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

_EPSILON = 1e-9


@dataclass(frozen=True)
class SimulationResult:
    periods: int
    total_demand: float
    served_from_stock: float
    fill_rate: float | None  # served from stock / demand; None without demand
    stockout_periods: int  # periods whose demand was not fully served from stock
    average_on_hand: float  # mean end-of-period stock on hand
    orders_placed: int
    max_backorder: float
    lead_time_periods: int


def simulate(
    demand: Sequence[float],
    reorder_point: float,
    order_quantity: float,
    lead_time: float,
    warmup: int = 0,
) -> SimulationResult:
    """Replay ``demand`` under the (s=``reorder_point``, Q=``order_quantity``) policy.

    The first ``warmup`` periods are replayed without being scored.
    """
    if order_quantity <= 0:
        raise ValueError("order_quantity must be positive")
    if not 0 <= warmup <= len(demand):
        raise ValueError("warmup must be between 0 and the number of periods")
    lead = int(lead_time + 0.5)
    net = reorder_point + order_quantity
    arrivals: dict[int, float] = {}
    served_total = 0.0
    stockouts = 0
    on_hand_sum = 0.0
    orders = 0
    max_backorder = 0.0
    for t, quantity in enumerate(demand):
        scored = t >= warmup
        net += arrivals.pop(t, 0.0)
        served = min(max(net, 0.0), quantity)
        net -= quantity
        if scored:
            served_total += served
            if served < quantity - _EPSILON:
                stockouts += 1
            on_hand_sum += max(net, 0.0)
            max_backorder = max(max_backorder, -net)
        position = net + sum(arrivals.values())
        while position <= reorder_point + _EPSILON:
            due = t + lead + 1
            arrivals[due] = arrivals.get(due, 0.0) + order_quantity
            position += order_quantity
            orders += int(scored)
    periods = len(demand) - warmup
    total = float(sum(demand[warmup:]))
    return SimulationResult(
        periods=periods,
        total_demand=total,
        served_from_stock=served_total,
        fill_rate=served_total / total if total > 0 else None,
        stockout_periods=stockouts,
        average_on_hand=on_hand_sum / periods if periods else 0.0,
        orders_placed=orders,
        max_backorder=max_backorder,
        lead_time_periods=lead,
    )
