"""Safety stock, reorder point or order-up-to level, and economic order quantity."""

from __future__ import annotations

import math
import random
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from statistics import NormalDist

POLICY_KINDS = ("sQ", "RS", "RsS")
BOOTSTRAP_SOURCES = ("demand", "residuals")


def _valid_finite_number(value: float) -> bool:
    """Reject booleans and malformed Python inputs before numeric operations."""
    if isinstance(value, bool):
        return False
    try:
        return math.isfinite(value)
    except (TypeError, ValueError, OverflowError):
        return False


def _valid_nonnegative_number(value: float) -> bool:
    """Require an actual finite quantity, not a bool or malformed API input."""
    if isinstance(value, bool):
        return False
    try:
        return math.isfinite(value) and value >= 0
    except (TypeError, ValueError, OverflowError):
        return False


# Forecast of the total demand of the next ``periods`` periods from ``history``;
# ``None`` when the method cannot forecast from that history (the origin is skipped).
IntervalForecaster = Callable[[Sequence[float], int], float | None]


@dataclass(frozen=True)
class Policy:
    """An (s, Q), (R, S) or (R, s, S) policy for one SKU, in units and periods.

    ``reorder_point`` is the level the inventory position is compared with:
    the reorder point ``s`` of an (s, Q) policy (``R = 0``: continuous review),
    the order-up-to level ``S`` of an (R, S) policy, which has the same
    formula ``D * (L + R) + SS`` (ADR 0007), or the reorder level ``s`` of an
    (R, s, S) policy, again ``D * (L + R) + SS``, whose ``S`` is ``s + Q`` with
    the order quantity of the SKU (ADR 0013).
    """

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
    kind: str = "sQ"  # "sQ" (reorder point, fixed quantity), "RS" or "RsS" (periodic review)

    @property
    def order_up_to(self) -> float | None:
        """The order-up-to level ``S`` of an (R, S) policy; ``None`` for (s, Q) and for
        (R, s, S), whose ``S = s + Q`` depends on the order quantity."""
        return self.reorder_point if self.kind == "RS" else None


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
    lead time (Silver, Pyke & Thomas, 2017). Like the CLI configuration,
    the standalone API requires a service level in [0.5, 1), and finite,
    non-negative demand, variability and protection-period inputs.
    """
    # Direct Python callers may pass booleans or malformed values even though
    # the CLI already validates this setting.
    try:
        valid_level = not isinstance(service_level, bool) and 0.5 <= service_level < 1
    except (TypeError, ValueError, OverflowError):
        valid_level = False
    if not valid_level:
        raise ValueError(f"service_level must be at least 0.5 and below 1, got {service_level}")
    for name, value in (
        ("demand_per_period", demand_per_period),
        ("sigma_demand", sigma_demand),
        ("lead_time", lead_time),
        ("sigma_lead_time", sigma_lead_time),
        ("review_period", review_period),
    ):
        if not _valid_nonnegative_number(value):
            raise ValueError(f"{name} must be finite and non-negative, got {value}")
    z = NormalDist().inv_cdf(service_level)
    # A 50% service level requires no extra stock. Avoid 0 * infinity
    # becoming NaN when finite inputs have an unrepresentable intermediate.
    if z == 0:
        return z, 0.0
    protection = lead_time + review_period
    # Evaluate the square root as a Euclidean norm: squaring a large finite
    # demand/sigma can overflow even when the resulting stock is representable.
    deviation = math.hypot(
        math.sqrt(protection) * sigma_demand,
        demand_per_period * sigma_lead_time,
    )
    return z, z * deviation


def _check_bootstrap_service_level(service_level: float) -> None:
    """Reject invalid nearest-rank quantiles before drawing random samples."""
    try:
        valid = not isinstance(service_level, bool) and 0 < service_level <= 1
    except (TypeError, ValueError, OverflowError):
        valid = False
    if not valid:
        raise ValueError(f"bootstrap service_level must be in (0, 1], got {service_level}")


def _check_bootstrap_intervals(
    lead_time: float, review_period: float, lead_times: Sequence[float]
) -> None:
    """Validate every possible bootstrap duration before random sampling."""
    for name, value in (("lead_time", lead_time), ("review_period", review_period)):
        if not _valid_nonnegative_number(value):
            raise ValueError(f"{name} must be finite and non-negative, got {value}")
    for position, lead in enumerate(lead_times):
        if not _valid_nonnegative_number(lead):
            raise ValueError(f"lead_times[{position}] must be finite and non-negative, got {lead}")


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
    A bootstrap nearest-rank quantile requires ``0 < service_level <= 1``;
    invalid levels, lead/review times, individual lead-time observations,
    demand observations or forecast demand (negative, non-finite, boolean or
    nonnumeric), and non-integer sample counts raise ``ValueError`` before
    any random draw, including for zero-length intervals.
    """
    if isinstance(samples, bool) or not isinstance(samples, int) or samples < 1:
        raise ValueError("samples must be at least 1 (a positive integer)")
    _check_bootstrap_service_level(service_level)
    _check_bootstrap_intervals(lead_time, review_period, lead_times)
    if not demand:
        raise ValueError("demand history is empty")
    for index, quantity in enumerate(demand):
        if not _valid_nonnegative_number(quantity):
            raise ValueError(f"demand[{index}] must be finite and non-negative, got {quantity}")
    if not _valid_nonnegative_number(demand_per_period):
        raise ValueError(
            f"demand_per_period must be finite and non-negative, got {demand_per_period}"
        )
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


def protection_periods(lead_time: float, review_period: float) -> int:
    """The protection interval ``L + R`` in whole periods, rounded half up (may be 0)."""
    return int(lead_time + review_period + 0.5)


def interval_forecast_errors(
    series: Sequence[float],
    forecaster: IntervalForecaster,
    periods: int,
    start: int,
    relative: bool = False,
) -> tuple[float, ...]:
    """Rolling-origin errors of the forecast of the next ``periods`` periods.

    For every origin ``t`` from ``start`` to ``len(series) - periods``, the
    forecaster sees ``series[:t]`` only and forecasts the total demand of
    periods ``t`` to ``t + periods - 1``; the error is the actual total minus
    that forecast (positive: demand above the forecast). With ``relative`` the
    error is divided by the forecast, and origins with a forecast of zero or
    less are skipped. Origins where the forecaster returns ``None`` are skipped.
    ``periods = 0`` gives no errors: there is no interval to protect.
    """
    if start < 1:
        raise ValueError(f"start must be at least 1, got {start}")
    errors: list[float] = []
    if periods < 1:
        return ()
    for t in range(start, len(series) - periods + 1):
        forecast = forecaster(series[:t], periods)
        if forecast is None or (relative and forecast <= 0):
            continue
        error = math.fsum(series[t : t + periods]) - forecast
        errors.append(error / forecast if relative else error)
    return tuple(errors)


def residual_bootstrap_quantile(
    errors: Mapping[int, Sequence[float]],
    service_level: float,
    lead_time: float,
    review_period: float = 0.0,
    lead_times: Sequence[float] = (),
    samples: int = 2000,
    rng: random.Random | None = None,
) -> float:
    """The ``service_level`` quantile of bootstrapped protection-interval forecast errors.

    ``errors[P]`` holds the errors of the forecast of ``P`` whole periods (from
    :func:`interval_forecast_errors`). Each of ``samples`` draws takes a lead
    time from ``lead_times`` (or ``lead_time``), turns ``L + R`` into whole
    periods ``P`` (half up) and draws one error from ``errors[P]``; ``P = 0``
    draws 0. The quantile (nearest rank) is the safety stock that covered the
    forecast error in that share of draws, before any floor (ADR 0008).
    Raises ``ValueError`` when an interval length that can be drawn has no errors,
    when any reachable residual is NaN or infinite, when the quantile level is
    outside ``(0, 1]``, or when a lead/review time is negative or non-finite.
    All reachable residuals and possible ``lead_times`` are checked before
    drawing a random sample; residuals for unreachable intervals are ignored.
    """
    if isinstance(samples, bool) or not isinstance(samples, int) or samples < 1:
        raise ValueError("samples must be at least 1 (a positive integer)")
    _check_bootstrap_service_level(service_level)
    _check_bootstrap_intervals(lead_time, review_period, lead_times)
    candidates = tuple(lead_times) if lead_times else (lead_time,)
    for lead in candidates:
        periods = protection_periods(lead, review_period)
        if periods and not errors.get(periods):
            raise ValueError(f"no forecast errors over {periods} period(s)")
    # Preserve the pre-existing missing-interval error priority before checking
    # individual residuals; a faulty sample must never advance the caller's RNG.
    for lead in candidates:
        periods = protection_periods(lead, review_period)
        if periods:
            for index, residual in enumerate(errors[periods]):
                if not _valid_finite_number(residual):
                    raise ValueError(f"errors[{periods}][{index}] must be finite, got {residual}")
    rng = rng or random.Random(0)
    draws: list[float] = []
    for _ in range(samples):
        lead = rng.choice(lead_times) if lead_times else lead_time
        periods = protection_periods(lead, review_period)
        draws.append(rng.choice(errors[periods]) if periods else 0.0)
    draws.sort()
    return draws[max(math.ceil(service_level * samples), 1) - 1]


def eoq(annual_demand: float, ordering_cost: float, holding_cost: float) -> float | None:
    """Economic order quantity ``sqrt(2 * D * S / H)``; ``None`` when it is undefined.

    ``D`` is units per year, ``S`` the cost per order and ``H`` the cost of
    holding one unit for a year. Undefined when ``D`` or ``H`` is not positive.
    If intermediate multiplication overflows or underflows, compute the same
    finite quantity in log space without changing ordinary-sized results.
    Reject invalid standalone inputs instead of silently returning NaN or
    using a negative cost to obtain a misleading quantity. Zero demand or
    holding cost still returns None; zero ordering cost still returns zero.
    """
    for name, value in (
        ("annual demand", annual_demand),
        ("ordering cost", ordering_cost),
        ("holding cost", holding_cost),
    ):
        if not _valid_nonnegative_number(value):
            raise ValueError(f"{name} must be finite and non-negative, got {value}")
    if annual_demand <= 0 or holding_cost <= 0:
        return None
    radicand = 2 * annual_demand * ordering_cost / holding_cost
    if 0 < radicand < math.inf:
        return math.sqrt(radicand)
    if ordering_cost <= 0:
        return math.sqrt(radicand)
    # Valid inputs can overflow while multiplying D and S (or underflow
    # before division by H), even though their final EOQ is representable.
    # Keep the ordinary arithmetic path unchanged; use log space only when
    # that intermediate result is zero or non-finite.
    log_quantity = 0.5 * (
        math.log(2) + math.log(annual_demand) + math.log(ordering_cost) - math.log(holding_cost)
    )
    try:
        return math.exp(log_quantity)
    except OverflowError:
        # Preserve the old infinite result when even the final EOQ cannot fit.
        return math.inf


def build_policy(
    service_level: float,
    demand_per_period: float,
    sigma_demand: float,
    lead_time: float,
    sigma_lead_time: float = 0.0,
    eoq_units: float | None = None,
    review_period: float = 0.0,
    bootstrap_units: float | None = None,
    kind: str = "sQ",
) -> Policy:
    """Combine safety stock and the level ``D * (L + R) + SS`` into a :class:`Policy`.

    The level is the reorder point ``s`` with ``kind="sQ"``, the order-up-to
    level ``S`` with ``kind="RS"``, and the reorder level ``s`` with
    ``kind="RsS"`` (its ``S`` is ``s + Q``). With ``bootstrap_units`` (from
    :func:`bootstrap_safety_stock`) that value is the safety stock and the
    policy is marked ``"bootstrap"``; ``z`` is still the normal quantile of the
    service level, reported for comparison.
    """
    if kind not in POLICY_KINDS:
        raise ValueError(f"kind must be 'sQ', 'RS' or 'RsS', got {kind!r}")
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
        kind=kind,
    )


def dynamic_levels(
    forecasts: Sequence[float],
    periods: int,
    lead_time: float,
    review_period: float,
    safety_stock: float | Sequence[float],
) -> tuple[float, ...]:
    """Levels that follow the forecast: one per period, ``D(t) * (L + R) + SS``.

    ``forecasts[i]`` is the demand forecast of period ``i``. The level used at
    the end of period ``t`` protects the next ``L + R`` periods, so ``D(t)`` is
    the mean forecast of periods ``t + 1`` to ``t + P`` with ``P = L + R``
    rounded half up (at least 1). ``forecasts`` must cover ``periods + P``
    periods. With a constant forecast ``D`` every level is the static
    ``D * (L + R) + SS`` of :func:`build_policy` (ADR 0007).

    ``safety_stock`` is one number for every period, or one per period (from
    :func:`period_safety_stocks`, ADR 0008).
    """
    stocks = _per_period(safety_stock, periods)
    return tuple(
        demand * (lead_time + review_period) + stock
        for demand, stock in zip(
            interval_demands(forecasts, periods, lead_time, review_period), stocks, strict=True
        )
    )


def _per_period(value: float | Sequence[float], periods: int) -> tuple[float, ...]:
    if isinstance(value, int | float):
        return (float(value),) * periods
    if len(value) != periods:
        raise ValueError(f"safety_stock needs one value per period: {len(value)} for {periods}")
    return tuple(float(v) for v in value)


def interval_demands(
    forecasts: Sequence[float], periods: int, lead_time: float, review_period: float
) -> tuple[float, ...]:
    """``D(t)`` of :func:`dynamic_levels`: the mean forecast of the ``P`` periods after ``t``."""
    steps = max(protection_periods(lead_time, review_period), 1)
    if len(forecasts) < periods + steps:
        raise ValueError(
            f"forecasts must cover {periods} periods plus {steps} ahead, got {len(forecasts)}"
        )
    return tuple(math.fsum(forecasts[t + 1 : t + 1 + steps]) / steps for t in range(periods))


def period_safety_stocks(
    forecasts: Sequence[float],
    periods: int,
    lead_time: float,
    review_period: float,
    relative_error: float,
) -> tuple[float, ...]:
    """One safety stock per period, proportional to the forecast it protects.

    ``SS(t) = max(q, 0) * D(t) * (L + R)``, where ``q`` is a quantile of the
    relative forecast errors over the protection interval (error / forecast,
    from :func:`interval_forecast_errors` with ``relative=True``) and ``D(t)``
    is the mean forecast of the periods after ``t``, as in :func:`dynamic_levels`.
    A peak month gets more safety stock than a trough, and the seasonal swing
    itself, which the levels already follow, is not counted again (ADR 0008).
    """
    ratio = max(relative_error, 0.0)
    protection = lead_time + review_period
    return tuple(
        ratio * demand * protection
        for demand in interval_demands(forecasts, periods, lead_time, review_period)
    )
