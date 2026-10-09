"""Safety stock, reorder point and economic order quantity."""

from __future__ import annotations

import math
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
) -> Policy:
    """Combine safety stock and reorder point ``s = D * (L + R) + SS`` into a :class:`Policy`."""
    z, ss = safety_stock(
        service_level, demand_per_period, sigma_demand, lead_time, sigma_lead_time, review_period
    )
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
    )
