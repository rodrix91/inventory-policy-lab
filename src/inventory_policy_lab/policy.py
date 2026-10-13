"""Safety stock, reorder point and economic order quantity."""

from __future__ import annotations

import math
import random
from collections.abc import Sequence
from dataclasses import dataclass
from statistics import NormalDist


@dataclass(frozen=True)
class Policy:
    """An (s, Q) policy for one SKU, in units and periods (``R = 0``: continuous review)."""

    service_level: float  # target cycle service level (probability of no stockout per cycle)
    z: float
    demand_per_period: float
    sigma_demand: float
    lead_time: float
    sigma_lead_time: float
    review_period: float
    safety_stock: float
    reorder_point: float
    eoq: float | None
    safety_stock_method: str = "normal"  # "normal" (formula) or "bootstrap" (empirical)


def safety_stock(
    service_level: float,
    demand_per_period: float,
    sigma_demand: float,
    lead_time: float,
    sigma_lead_time: float = 0.0,
    review_period: float = 0.0,
) -> tuple[float, float]:
    """Return ``(z, safety stock)`` for a target cycle service level.

    ``SS = z * sqrt((L + R) * sigma_D**2 + D**2 * sigma_L**2)`` with
    ``z = NormalDist().inv_cdf(service_level)``: the protection interval is the
    lead time ``L`` plus the review period ``R`` (``R = 0`` is continuous
    review). Assumes independent, normally distributed demand per period and
    lead time (Silver, Pyke & Thomas, 2017).
    """
    z = NormalDist().inv_cdf(service_level)
    protection = lead_time + review_period
    variance = protection * sigma_demand**2 + demand_per_period**2 * sigma_lead_time**2
    return z, z * math.sqrt(variance)


def bootstrap_safety_stock(
    demand: Sequence[float],
    service_level: float,
    demand_per_period: float,
    lead_time: float,
    review_period: float = 0.0,
    lead_times: Sequence[float] = (),
    samples: int = 2000,
    rng: random.Random | None = None,
) -> tuple[float, float]:
    """Return ``(quantile, safety stock)`` from a bootstrap of protection-interval demand.

    Each of ``samples`` draws builds one protection interval: its length is a
    lead time drawn from ``lead_times`` (or ``lead_time`` when none were
    observed) plus ``review_period``, rounded to whole periods (half up), and its
    demand is the sum of that many periods drawn with replacement from
    ``demand``. The ``service_level`` quantile of those sums (nearest rank) is
    the stock that covered the interval in that share of draws, so no normal
    distribution is assumed; lumpy and intermittent histories keep their shape.

    Safety stock is that quantile minus the expected interval demand
    ``D * (L + R)``, floored at zero: the reorder point is never set below the
    forecast over the interval. Pass a seeded ``rng`` for reproducible results.
    """
    if samples < 1:
        raise ValueError("samples must be at least 1")
    if not demand:
        raise ValueError("demand history is empty")
    rng = rng or random.Random(0)
    sums: list[float] = []
    for _ in range(samples):
        lead = rng.choice(lead_times) if lead_times else lead_time
        periods = int(lead + review_period + 0.5)
        sums.append(math.fsum(rng.choices(demand, k=periods)) if periods else 0.0)
    sums.sort()
    rank = max(math.ceil(service_level * samples), 1)
    quantile = sums[rank - 1]
    expected = demand_per_period * (lead_time + review_period)
    return quantile, max(quantile - expected, 0.0)


def eoq(annual_demand: float, ordering_cost: float, holding_cost: float) -> float | None:
    """Economic order quantity ``sqrt(2 * D * S / H)``; ``None`` when it is undefined.

    ``D`` is units per year, ``S`` the cost per order and ``H`` the cost of
    holding one unit for a year. Undefined when ``D`` or ``H`` is not positive.
    """
    if annual_demand <= 0 or holding_cost <= 0:
        return None
    return math.sqrt(2 * annual_demand * ordering_cost / holding_cost)


def build_policy(
    service_level: float,
    demand_per_period: float,
    sigma_demand: float,
    lead_time: float,
    sigma_lead_time: float = 0.0,
    eoq_units: float | None = None,
    review_period: float = 0.0,
    bootstrap_units: float | None = None,
) -> Policy:
    """Combine safety stock and reorder point ``s = D * (L + R) + SS`` into a :class:`Policy`.

    With ``bootstrap_units`` (from :func:`bootstrap_safety_stock`) that value is
    the safety stock and the policy is marked ``"bootstrap"``; ``z`` is still the
    normal quantile of the service level, reported for comparison.
    """
    z, ss = safety_stock(
        service_level, demand_per_period, sigma_demand, lead_time, sigma_lead_time, review_period
    )
    method = "normal"
    if bootstrap_units is not None:
        ss, method = bootstrap_units, "bootstrap"
    return Policy(
        service_level=service_level,
        z=z,
        demand_per_period=demand_per_period,
        sigma_demand=sigma_demand,
        lead_time=lead_time,
        sigma_lead_time=sigma_lead_time,
        review_period=review_period,
        safety_stock=ss,
        reorder_point=demand_per_period * (lead_time + review_period) + ss,
        eoq=eoq_units,
        safety_stock_method=method,
    )
