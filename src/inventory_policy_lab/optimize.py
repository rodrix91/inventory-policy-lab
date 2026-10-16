"""Cost-optimised levels: search the safety stock and the order quantity (ADR 0015).

The policies of :mod:`inventory_policy_lab.policy` set the level from a service
target and the order quantity from EOQ or a cover rule; the cost rates of ADR
0012 only score what they did. Here the two numbers an (s, Q) or (R, s, S)
policy is made of are chosen for cost instead, on the training window only:

- **What is searched.** The level of every test period keeps the forecast part
  of the heuristic level (``D x (L + R)``, static or following the forecast
  period by period) and replaces its safety stock with a searched one, so
  ``s = D x (L + R) + SS``; the order quantity ``Q`` is searched too, and
  (R, s, S) orders up to ``S = s + Q``. Searching ``SS`` and ``Q`` is searching
  ``s`` and ``S``.
- **The objective** is the mean cost of the test window over demand paths built
  from training data only: each path gives every test period the training
  forecast of that period plus a one-step forecast error of the training
  periods drawn at random (floored at zero demand). Every path starts from the
  stock and orders the heuristic policy left at the end of training, the state
  the real test also starts from, and every candidate is scored on the same
  paths (common random numbers), so differences between candidates are not noise
  between draws.
- **The grid** is bounded and documented: ``SS`` is the heuristic one,
  ``z x sigma`` for ``z`` in :data:`SAFETY_Z` (``sigma``: the standard deviation of
  the one-step errors times the square root of ``L + R``), or minus a share
  (:data:`FORECAST_SHARES`) of the forecast over ``L + R``, down to a level of
  zero; ``Q`` is the heuristic one or :data:`COVER_PERIODS` periods of mean
  training demand. Every pair is scored, then the best ``SS`` is refined in
  quarter-sigma steps (:data:`REFINE_STEPS`) at the best ``Q``. The heuristic
  pair comes first and wins ties, so the search only moves away from it for a
  strictly lower expected cost.
- **An optional fill-rate floor** (ADR 0016): with ``fill_floor``, a pair is
  accepted only when its expected fill rate on the same paths (units served
  from stock over units demanded, summed over the paths) is at least the floor;
  the cheapest accepted pair wins, and when no pair qualifies the heuristic
  pair is kept.
"""

from __future__ import annotations

import math
import random
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from functools import partial

from .costs import CostRates
from .simulate import _Ledger, _review_period, _review_rss, _review_sq

OPTIMIZABLE = ("sQ", "RsS")  # (R, S) has no quantity to search: its S is the level
SAFETY_Z = tuple(-1.0 + 0.5 * i for i in range(9))  # -1.0 to 3.0 sigma
# Below the forecast over the protection interval: a share of it taken off the level.
# An (s, Q) level counts the review period in L + R, one period more than the replay's
# risk interval, so its cheapest level can sit far below the heuristic one.
FORECAST_SHARES = tuple(0.1 * i for i in range(1, 11))  # 0.1 to 1.0
COVER_PERIODS = (0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 6.0, 8.0, 10.0, 12.0)
REFINE_STEPS = (-4, -3, -2, -1, 1, 2, 3, 4)  # quarter-sigma steps around the best safety stock
DEFAULT_SAMPLES = 100


@dataclass(frozen=True)
class CostSearch:
    """The pair picked by :func:`search_levels` and the expected costs behind it."""

    safety_stock: float
    order_quantity: float
    expected_cost: float  # mean cost of the test window per path, at the pick
    heuristic_safety_stock: float
    heuristic_order_quantity: float
    heuristic_cost: float  # the same for the heuristic pair
    candidates: int  # pairs scored
    samples: int  # demand paths
    # With a fill-rate floor (ADR 0016) only; None and 0 without one:
    fill_floor: float | None = None  # least expected fill rate a pair needs
    expected_fill: float | None = None  # expected fill rate on the paths, at the pick
    heuristic_fill: float | None = None  # the same for the heuristic pair
    feasible: int = 0  # pairs scored whose expected fill rate meets the floor
    fell_back: bool = False  # no pair met the floor: the heuristic pair is kept


def _with_first(first: float, others: Sequence[float]) -> tuple[float, ...]:
    values = [first]
    for value in others:
        if all(abs(value - seen) > 1e-9 for seen in values):
            values.append(value)
    return tuple(values)


def safety_grid(heuristic: float, sigma: float, interval_demand: float) -> tuple[float, ...]:
    """The heuristic safety stock, then ``z x sigma`` for ``z`` in :data:`SAFETY_Z`, then
    minus each of :data:`FORECAST_SHARES` of ``interval_demand`` (the forecast over
    the protection interval), down to a level of zero."""
    values = [z * sigma for z in SAFETY_Z]
    values += [-share * interval_demand for share in FORECAST_SHARES if interval_demand > 0]
    return _with_first(heuristic, values)


def quantity_grid(heuristic: float, mean_demand: float) -> tuple[float, ...]:
    """The heuristic quantity, then :data:`COVER_PERIODS` periods of ``mean_demand``.

    Without demand only the heuristic quantity is left (a quantity must be positive).
    """
    covers = [c * mean_demand for c in COVER_PERIODS] if mean_demand > 0 else []
    return _with_first(heuristic, covers)


def demand_paths(
    forecasts: Sequence[float], errors: Sequence[float], samples: int, rng: random.Random
) -> tuple[tuple[float, ...], ...]:
    """``samples`` paths: each period's forecast plus an error drawn from ``errors``, at least 0."""
    if not errors:
        raise ValueError("demand paths need at least one error to resample")
    return tuple(tuple(max(f + rng.choice(errors), 0.0) for f in forecasts) for _ in range(samples))


_Step = Callable[[_Ledger, int, float, float], None]


def _step(kind: str, review: int, lead: int) -> _Step:
    """The end-of-period decision of ``kind``, as the simulator takes it."""

    def sq(ledger: _Ledger, t: int, level: float, quantity: float) -> None:
        _review_sq(ledger, t, level, quantity, lead)

    def rss(ledger: _Ledger, t: int, level: float, quantity: float) -> None:
        _review_rss(ledger, t, level, quantity, review, lead)

    return sq if kind == "sQ" else rss


def expected_outcomes(
    train_demand: Sequence[float],
    train_levels: Sequence[float],
    train_quantity: float,
    kind: str,
    review_period: int,
    lead_time: float,
    base_levels: Sequence[float],
    paths: Sequence[Sequence[float]],
    rates: CostRates,
    candidates: Sequence[tuple[float, float]],
) -> list[tuple[float, float]]:
    """Mean cost of the test window per path, and expected fill rate, of each
    ``(safety stock, quantity)``.

    The fill rate is the units served from stock over the units demanded, both
    summed over every path (1.0 when the paths have no demand).

    The training periods are replayed once with ``train_levels`` and
    ``train_quantity`` (the run starts with the first level plus that quantity
    on hand, as :func:`~inventory_policy_lab.simulate.simulate` does); each path
    then continues from that state with levels ``base_levels[h] + safety stock``
    and the candidate's quantity, and only the path's periods are priced. The
    result equals pricing ``simulate`` / ``simulate_rss`` over the training
    demand followed by the path, with the training periods as warm-up.
    """
    if kind not in OPTIMIZABLE:
        raise ValueError(f"cost search applies to 'sQ' and 'RsS', not {kind!r}")
    if not train_demand or len(train_levels) != len(train_demand):
        raise ValueError("cost search needs training periods with one level each")
    if not paths or any(len(path) != len(base_levels) for path in paths):
        raise ValueError("every demand path needs one value per test level")
    review = _review_period(review_period)
    lead = int(lead_time + 0.5)
    step = _step(kind, review, lead)
    warmup = len(train_demand)
    start = _Ledger(net=train_levels[0] + train_quantity, warmup=warmup, arrivals={})
    for t, quantity in enumerate(train_demand):
        start.serve(t, quantity)
        step(start, t, train_levels[t], train_quantity)
    totals = [math.fsum(path) for path in paths]
    demanded = math.fsum(totals)
    results = []
    for safety, quantity in candidates:
        if quantity <= 0:
            raise ValueError("order quantity must be positive")
        levels = [base + safety for base in base_levels]
        cost = 0.0
        served: list[float] = []
        for path, total in zip(paths, totals, strict=True):
            ledger = _Ledger(net=start.net, warmup=warmup, arrivals=dict(start.arrivals))
            for h, demand in enumerate(path):
                ledger.serve(warmup + h, demand)
                step(ledger, warmup + h, levels[h], quantity)
            short = max(total - ledger.served_total, 0.0)
            served.append(total - short)
            cost += (
                rates.order * ledger.orders
                + rates.holding * ledger.on_hand_sum
                + rates.stockout * short
            )
        fill = math.fsum(served) / demanded if demanded > 0 else 1.0
        results.append((cost / len(paths), fill))
    return results


def expected_costs(
    train_demand: Sequence[float],
    train_levels: Sequence[float],
    train_quantity: float,
    kind: str,
    review_period: int,
    lead_time: float,
    base_levels: Sequence[float],
    paths: Sequence[Sequence[float]],
    rates: CostRates,
    candidates: Sequence[tuple[float, float]],
) -> list[float]:
    """Mean cost of the test window per path for each ``(safety stock, quantity)``.

    The cost part of :func:`expected_outcomes`, with the same arguments.
    """
    outcomes = expected_outcomes(
        train_demand,
        train_levels,
        train_quantity,
        kind,
        review_period,
        lead_time,
        base_levels,
        paths,
        rates,
        candidates,
    )
    return [cost for cost, _ in outcomes]


def search_levels(
    train_demand: Sequence[float],
    train_levels: Sequence[float],
    train_quantity: float,
    kind: str,
    review_period: int,
    lead_time: float,
    base_levels: Sequence[float],
    paths: Sequence[Sequence[float]],
    rates: CostRates,
    safety_values: Sequence[float],
    quantity_values: Sequence[float],
    refine_step: float = 0.0,
    fill_floor: float | None = None,
) -> CostSearch:
    """The ``(safety stock, quantity)`` with the lowest expected cost.

    First every pair of the two grids, whose first values are the heuristic
    ones; then, with a positive ``refine_step``, the best safety stock plus each
    of :data:`REFINE_STEPS` times ``refine_step`` at the best quantity. Pairs are
    scored in that order (grid: safety stock, then quantity) and a pair replaces
    the best only with a strictly lower cost, so the heuristic pair wins ties.

    With ``fill_floor`` (ADR 0016) only pairs whose expected fill rate is at
    least the floor can be picked, the refinement included; when no grid pair
    meets it, the heuristic pair is kept without refining (``fell_back``).
    """
    if not safety_values or not quantity_values:
        raise ValueError("the grids need at least one value each")
    replay = partial(
        expected_outcomes,
        train_demand,
        train_levels,
        train_quantity,
        kind,
        review_period,
        lead_time,
        base_levels,
        paths,
        rates,
    )
    candidates = [(s, q) for s in safety_values for q in quantity_values]
    outcomes = replay(candidates)

    def allowed(index: int) -> bool:
        return fill_floor is None or outcomes[index][1] >= fill_floor

    accepted = [index for index in range(len(candidates)) if allowed(index)]
    fell_back = not accepted
    best = accepted[0] if accepted else 0
    for index in accepted:
        if outcomes[index][0] < outcomes[best][0]:
            best = index
    if refine_step > 0 and not fell_back:
        safety, quantity = candidates[best]
        local = [(safety + k * refine_step, quantity) for k in REFINE_STEPS]
        candidates += local
        outcomes += replay(local)
        for index in range(len(candidates) - len(local), len(candidates)):
            if allowed(index):
                accepted.append(index)
                if outcomes[index][0] < outcomes[best][0]:
                    best = index
    return CostSearch(
        safety_stock=candidates[best][0],
        order_quantity=candidates[best][1],
        expected_cost=outcomes[best][0],
        heuristic_safety_stock=safety_values[0],
        heuristic_order_quantity=quantity_values[0],
        heuristic_cost=outcomes[0][0],
        candidates=len(candidates),
        samples=len(paths),
        fill_floor=fill_floor,
        expected_fill=None if fill_floor is None else outcomes[best][1],
        heuristic_fill=None if fill_floor is None else outcomes[0][1],
        feasible=len(accepted) if fill_floor is not None else 0,
        fell_back=fell_back,
    )
