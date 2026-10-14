"""Replay a demand history under an (s, Q) or an (R, S) policy.

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

The level can be one number for the whole history or one number per period
(dynamic levels, ADR 0007): then the level compared at the end of period ``t``
is the ``t``-th one, and the run starts from the first.

:func:`simulate_periodic` replays a periodic-review, order-up-to (R, S)
policy with the same timing, except for step 3: the inventory position is
reviewed only at the end of every ``R``-th period (periods ``R - 1``,
``2R - 1``, ...), and then an order of ``S - position`` is placed when the
position is below ``S``. The run starts with ``S`` units on hand.
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


def _levels(level: float | Sequence[float], periods: int, name: str) -> tuple[float, list[float]]:
    """The starting level and one level per period, from one number or a sequence."""
    if isinstance(level, int | float):
        return float(level), [float(level)] * periods
    if len(level) != periods:
        raise ValueError(f"{name} needs one level per period: {len(level)} for {periods}")
    levels = [float(value) for value in level]
    return (levels[0] if levels else 0.0), levels


def _check_warmup(demand: Sequence[float], warmup: int) -> None:
    if not 0 <= warmup <= len(demand):
        raise ValueError("warmup must be between 0 and the number of periods")


@dataclass
class _Ledger:
    """Stock, orders on the way and the scores of one replay."""

    net: float
    warmup: int
    arrivals: dict[int, float]
    served_total: float = 0.0
    stockouts: int = 0
    on_hand_sum: float = 0.0
    orders: int = 0
    max_backorder: float = 0.0

    def serve(self, t: int, quantity: float) -> None:
        """Receive what is due in ``t``, serve its demand and score it after the warm-up."""
        self.net += self.arrivals.pop(t, 0.0)
        served = min(max(self.net, 0.0), quantity)
        self.net -= quantity
        if t >= self.warmup:
            self.served_total += served
            if served < quantity - _EPSILON:
                self.stockouts += 1
            self.on_hand_sum += max(self.net, 0.0)
            self.max_backorder = max(self.max_backorder, -self.net)

    def position(self) -> float:
        return self.net + sum(self.arrivals.values())

    def order(self, t: int, due: int, quantity: float) -> None:
        self.arrivals[due] = self.arrivals.get(due, 0.0) + quantity
        self.orders += int(t >= self.warmup)

    def result(self, demand: Sequence[float], lead: int) -> SimulationResult:
        periods = len(demand) - self.warmup
        total = float(sum(demand[self.warmup :]))
        return SimulationResult(
            periods=periods,
            total_demand=total,
            served_from_stock=self.served_total,
            fill_rate=self.served_total / total if total > 0 else None,
            stockout_periods=self.stockouts,
            average_on_hand=self.on_hand_sum / periods if periods else 0.0,
            orders_placed=self.orders,
            max_backorder=self.max_backorder,
            lead_time_periods=lead,
        )


def simulate(
    demand: Sequence[float],
    reorder_point: float | Sequence[float],
    order_quantity: float,
    lead_time: float,
    warmup: int = 0,
) -> SimulationResult:
    """Replay ``demand`` under the (s=``reorder_point``, Q=``order_quantity``) policy.

    ``reorder_point`` is one level, or one per period (the level checked at the
    end of that period). The first ``warmup`` periods are replayed without
    being scored.
    """
    if order_quantity <= 0:
        raise ValueError("order_quantity must be positive")
    _check_warmup(demand, warmup)
    start, levels = _levels(reorder_point, len(demand), "reorder_point")
    lead = int(lead_time + 0.5)
    ledger = _Ledger(net=start + order_quantity, warmup=warmup, arrivals={})
    for t, quantity in enumerate(demand):
        ledger.serve(t, quantity)
        position = ledger.position()
        while position <= levels[t] + _EPSILON:
            ledger.order(t, t + lead + 1, order_quantity)
            position += order_quantity
    return ledger.result(demand, lead)


def simulate_periodic(
    demand: Sequence[float],
    order_up_to: float | Sequence[float],
    review_period: int,
    lead_time: float,
    warmup: int = 0,
) -> SimulationResult:
    """Replay ``demand`` under the (R=``review_period``, S=``order_up_to``) policy.

    The position is reviewed at the end of periods ``R - 1``, ``2R - 1``, ...;
    when it is below ``S`` an order of ``S - position`` arrives at the start of
    period ``t + L + 1``. ``order_up_to`` is one level, or one per period (the
    level used at a review at the end of that period). The run starts with the
    first level on hand. The first ``warmup`` periods are not scored.
    """
    if isinstance(review_period, bool) or not isinstance(review_period, int):
        raise ValueError("review_period must be a whole number of periods")
    if review_period < 1:
        raise ValueError("review_period must be at least 1")
    _check_warmup(demand, warmup)
    start, levels = _levels(order_up_to, len(demand), "order_up_to")
    lead = int(lead_time + 0.5)
    ledger = _Ledger(net=start, warmup=warmup, arrivals={})
    for t, quantity in enumerate(demand):
        ledger.serve(t, quantity)
        if (t + 1) % review_period:
            continue
        shortfall = levels[t] - ledger.position()
        if shortfall > _EPSILON:
            ledger.order(t, t + lead + 1, shortfall)
    return ledger.result(demand, lead)
