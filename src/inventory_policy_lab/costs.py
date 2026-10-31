"""Cost of a replay: ordering, holding and stockout costs from the replayed periods.

A replay (:class:`~inventory_policy_lab.simulate.SimulationResult`) counts the
orders placed, the stock on hand at the end of each scored period and the
demand served from stock. With three cost rates those counts become money
(ADR 0012):

- **ordering**: ``order_cost`` per order placed in the scored periods;
- **holding**: ``holding_cost`` per unit on hand at the end of a scored period,
  so the stock of the whole replay costs ``holding_cost x average on hand x
  periods``;
- **stockout**: ``stockout_cost`` per unit of demand not served from stock in
  its own period (backordered and served later from the next arrivals, as the
  replay assumes). This is the "cost per unit short" of Silver, Pyke & Thomas
  (2017), the shortage cost that matches the fill rate the report scores.

The rates are the same for every SKU and do not change the policy: the order
quantity and the levels are fitted as before, and the cost only scores what
the replay did. The EOQ inputs (``--ordering-cost``, ``--holding-rate``) are a
separate setting that does change the order quantity.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass

from .simulate import SimulationResult


@dataclass(frozen=True)
class CostRates:
    """Cost per order, per unit and period held, and per unit short; all at least 0."""

    order: float = 0.0
    holding: float = 0.0
    stockout: float = 0.0

    def __post_init__(self) -> None:
        for name in ("order", "holding", "stockout"):
            value = getattr(self, name)
            # A bool is an int in Python, but True is not a meaningful
            # monetary rate. Catch bad direct API inputs instead of leaking
            # TypeError or OverflowError from math.isfinite/comparison.
            if isinstance(value, bool):
                valid = False
            else:
                try:
                    valid = math.isfinite(value) and value >= 0
                except (TypeError, ValueError, OverflowError):
                    valid = False
            if not valid:
                raise ValueError(f"{name} cost must be a finite number of at least 0, got {value!r}")


@dataclass(frozen=True)
class CostBreakdown:
    """What a replay (or a sum of replays) cost, with the quantities behind each part."""

    orders: int  # orders placed in the scored periods
    unit_periods: float  # sum over the scored periods of the end-of-period stock on hand
    units_short: float  # demand not served from stock in its own period
    ordering: float
    holding: float
    stockout: float

    @property
    def total(self) -> float:
        return self.ordering + self.holding + self.stockout


def replay_cost(result: SimulationResult, rates: CostRates) -> CostBreakdown:
    """The cost of one replay at ``rates`` (see the module docstring)."""
    unit_periods = result.average_on_hand * result.periods
    short = max(result.total_demand - result.served_from_stock, 0.0)
    return CostBreakdown(
        orders=result.orders_placed,
        unit_periods=unit_periods,
        units_short=short,
        ordering=rates.order * result.orders_placed,
        holding=rates.holding * unit_periods,
        stockout=rates.stockout * short,
    )


def total_cost(costs: Iterable[CostBreakdown]) -> CostBreakdown:
    """The sum of several breakdowns, part by part (for example over SKUs)."""
    items = list(costs)
    return CostBreakdown(
        orders=sum(c.orders for c in items),
        unit_periods=math.fsum(c.unit_periods for c in items),
        units_short=math.fsum(c.units_short for c in items),
        ordering=math.fsum(c.ordering for c in items),
        holding=math.fsum(c.holding for c in items),
        stockout=math.fsum(c.stockout for c in items),
    )
