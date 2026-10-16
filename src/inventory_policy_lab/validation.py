"""Out-of-sample replay: fit each policy on the earlier periods, score it on the rest.

The in-sample replay of :mod:`inventory_policy_lab.simulate` applies a policy
computed from the whole history to that same history, so it flatters every
method, and most of all the bootstrap, which resamples the periods it is then
replayed on. Here the calendar is split in time:

1. **Train**: every period except the last ``test_periods``. Classes (ABC on the
   training demand), the demand pattern, the forecast backtest and pick, the
   demand sigma, the observed lead times dated in training, and the bootstrap
   draws use these periods only.
2. **Test**: the last ``test_periods`` periods. The policy fitted on train, one
   with the normal formula and one with the bootstrap, is replayed over train
   and test, and only the test periods are scored, so the test starts from the
   stock and orders the policy left at the end of training (ADR 0005).

The training replay of the same policy is reported next to it as the in-sample
reference: the gap between the two is the optimism of the in-sample replay.

With ``Config.rolling_origin`` the test is also replayed with a **rolling
origin** (ADR 0009): at the start of every test period ``t`` each SKU is
refitted, exactly as on train, on periods ``0 .. t - 1`` only (the training
periods plus the test periods already observed), and the safety stock, the
level and the order quantity of that refit are the ones used at the end of
``t``. The training periods are replayed with the fixed policy, so both
replays enter the test from the same stock and orders, and the first test
period has the same decision in both.

With ``Config.refit_every`` ``K`` above 1 the refit runs only at the start of
test periods ``0, K, 2K, ...`` of the test window (ADR 0011). The refit at
``t`` sees periods ``0 .. t - 1`` and decides periods ``t .. t + K - 1``: the
same safety stock and order quantity, and with dynamic levels its forecasts
1 to ``K`` steps ahead, exactly as the fixed origin uses the training fit for
the whole test window. ``K = 1`` is the rolling origin above; a ``K`` of at
least the test window gives the fixed-origin replay.
"""

from __future__ import annotations

import math
import random
import statistics
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING

from .classify import abc_classes
from .costs import CostBreakdown, CostRates, replay_cost, total_cost
from .errors import HistoryError
from .optimize import CostSearch, demand_paths, quantity_grid, safety_grid, search_levels
from .policy import protection_periods
from .reader import DemandData, SkuHistory
from .simulate import SimulationResult

SAFETY_STOCK_METHODS = ("normal", "bootstrap")
ORIGINS = ("fixed", "rolling")  # the out-of-sample replays: fixed origin, rolling origin

if TYPE_CHECKING:  # pragma: no cover - imports for type hints only
    from .analysis import Config, SkuResult
    from .policy import Policy


@dataclass(frozen=True)
class PolicyReplay:
    """One safety-stock method fitted on train and replayed in and out of sample."""

    method: str  # "normal" or "bootstrap"
    safety_stock: float
    reorder_point: float  # s of (s, Q), or the order-up-to level S of (R, S)
    order_quantity: float
    in_sample: SimulationResult  # the train periods (policy fitted on them)
    out_of_sample: SimulationResult  # the test periods only
    test_levels: tuple[float, ...] = ()  # dynamic levels of the test periods; () when static
    test_safety_stocks: tuple[float, ...] = ()  # per-period safety stocks of the test periods


@dataclass(frozen=True)
class RollingReplay:
    """One safety-stock method refitted at every test period (rolling origin, ADR 0009).

    Every tuple has one entry per test period: what the refit on the periods
    before it decided for the end of that period.
    """

    method: str  # "normal" or "bootstrap"
    forecast_methods: tuple[str, ...]  # the forecast picked at each origin
    safety_stocks: tuple[float, ...]
    levels: tuple[float, ...]  # s of (s, Q), or the order-up-to level S of (R, S)
    order_quantities: tuple[float, ...]  # Q of (s, Q); refitted but unused by (R, S)
    out_of_sample: SimulationResult  # the test periods only


@dataclass(frozen=True)
class OptimizedReplay:
    """The cost-optimised safety stock and quantity of a SKU, replayed on the test (ADR 0015).

    The training periods keep the normal policy, so the test starts from the
    same stock as the normal fixed-origin replay.
    """

    search: CostSearch  # what the search on training paths picked, and its expected costs
    test_levels: tuple[float, ...]  # level of each test period: forecast part + picked SS
    order_quantity: float  # the picked Q (S = s + Q for (R, s, S))
    error_source: str  # "forecast errors" or "demand deviations" (too few errors)
    errors: int  # how many training values the demand paths resample
    out_of_sample: SimulationResult  # the test periods only


@dataclass(frozen=True)
class SkuOutOfSample:
    sku: str
    train_periods: int
    test_periods: int
    abc: str  # from the training demand
    category: str  # demand pattern of the training demand
    forecast_method: str
    forecast: float
    replays: tuple[PolicyReplay, ...]  # one per method, in SAFETY_STOCK_METHODS order
    notes: tuple[str, ...]
    rolling: tuple[RollingReplay, ...] = ()  # with Config.rolling_origin, same order
    optimized: OptimizedReplay | None = None  # with Config.optimize_cost (ADR 0015)

    def replay(self, method: str) -> PolicyReplay:
        return next(r for r in self.replays if r.method == method)

    def rolling_replay(self, method: str) -> RollingReplay:
        return next(r for r in self.rolling if r.method == method)


@dataclass(frozen=True)
class ReplayTotals:
    """A replay summed over SKUs: fill rate on all demand, stockouts and stock summed."""

    total_demand: float
    served_from_stock: float
    fill_rate: float | None
    stockout_periods: int
    average_on_hand: float  # sum of the SKUs' average stock on hand


@dataclass(frozen=True)
class OutOfSampleReport:
    test_periods: int
    train_calendar: tuple[str, ...]
    test_calendar: tuple[str, ...]
    skus: tuple[SkuOutOfSample, ...]
    skipped: tuple[str, ...]  # SKUs with no demand history in the train periods
    policy: str = "sQ"  # the policy kind replayed: "sQ", "RS" or "RsS"
    bootstrap_source: str = "demand"  # what the bootstrap replay resamples (ADR 0008)
    rolling_origin: bool = False  # SKUs also carry rolling-origin replays (ADR 0009)
    refit_every: int = 1  # the rolling origin refits every K test periods (ADR 0011)
    costs: CostRates | None = None  # cost rates that score the test periods (ADR 0012)
    # Each SKU's own rates when some rate depends on the SKU (ADR 0014); empty otherwise.
    sku_rates: Mapping[str, CostRates] = field(default_factory=dict)
    holding_cost_rate: float | None = None  # yearly holding rate of the unit cost (ADR 0014)
    cost_columns: bool = False  # order_cost and stockout_cost columns read (ADR 0014)
    optimize_cost: bool = False  # SKUs also carry cost-optimised replays (ADR 0015)
    optimize_samples: int = 0  # demand paths of the cost search
    optimize_fill_floor: float | None = None  # fill-rate floor of the search (ADR 0016)

    def rates_of(self, sku: str) -> CostRates:
        """The cost rates of ``sku``: its own (ADR 0014), else the shared ones.

        Raises ``ValueError`` when the report has no cost rates.
        """
        if self.costs is None:
            raise ValueError("this report has no cost rates (Config order, holding, stockout)")
        return self.sku_rates.get(sku, self.costs)

    def totals(self, method: str, sample: str) -> ReplayTotals:
        """Totals of ``method`` for ``sample`` ``"in_sample"`` or ``"out_of_sample"``."""
        return _sum([getattr(s.replay(method), sample) for s in self.skus])

    def rolling_totals(self, method: str) -> ReplayTotals:
        """Out-of-sample totals of ``method`` with a rolling origin."""
        return _sum([s.rolling_replay(method).out_of_sample for s in self.skus])

    def sku_cost(self, sku: SkuOutOfSample, method: str, origin: str = "fixed") -> CostBreakdown:
        """Cost of the test periods of ``sku`` under ``method``, origin ``"fixed"`` or
        ``"rolling"``. Raises ``ValueError`` when the report has no cost rates."""
        rates = self.rates_of(sku.sku)
        if origin not in ORIGINS:
            raise ValueError(f"origin must be 'fixed' or 'rolling', got {origin!r}")
        replay = sku.replay(method) if origin == "fixed" else sku.rolling_replay(method)
        return replay_cost(replay.out_of_sample, rates)

    def cost(self, method: str, origin: str = "fixed") -> CostBreakdown:
        """Cost of the test periods of ``method`` summed over the SKUs."""
        return total_cost(self.sku_cost(s, method, origin) for s in self.skus)

    def optimized_sku_cost(self, sku: SkuOutOfSample) -> CostBreakdown:
        """Cost of the test periods of ``sku`` with its cost-optimised policy (ADR 0015).

        Raises ``ValueError`` when the report has no cost search.
        """
        if sku.optimized is None:
            raise ValueError("this report has no cost search (Config.optimize_cost)")
        return replay_cost(sku.optimized.out_of_sample, self.rates_of(sku.sku))

    def optimized_cost(self) -> CostBreakdown:
        """Cost of the test periods with the cost-optimised policies, summed over the SKUs."""
        return total_cost(self.optimized_sku_cost(s) for s in self.skus)

    def optimized_totals(self) -> ReplayTotals:
        """Out-of-sample totals of the cost-optimised policies."""
        if not self.optimize_cost:
            raise ValueError("this report has no cost search (Config.optimize_cost)")
        return _sum([s.optimized.out_of_sample for s in self.skus if s.optimized is not None])


def _sum(results: list[SimulationResult]) -> ReplayTotals:
    demand = sum(r.total_demand for r in results)
    served = sum(r.served_from_stock for r in results)
    return ReplayTotals(
        total_demand=demand,
        served_from_stock=served,
        fill_rate=served / demand if demand > 0 else None,
        stockout_periods=sum(r.stockout_periods for r in results),
        average_on_hand=sum(r.average_on_hand for r in results),
    )


@dataclass(frozen=True)
class _Origin:
    """What every SKU's refit at one rolling origin sees: histories, values, classes."""

    histories: dict[str, SkuHistory]
    values: dict[str, float]
    classes: dict[str, str]


def _origin(data: DemandData, calendar: tuple[str, ...], config: Config) -> _Origin:
    """Histories cut to ``calendar`` and the ABC classes of their demand.

    SKUs with no period in ``calendar`` are left out, as on train.
    """
    histories: dict[str, SkuHistory] = {}
    for history in data.skus:
        cut = train_history(history, calendar)
        if cut is not None:
            histories[history.sku] = cut
    values = {
        sku: statistics.fmean(h.demand)
        * config.periods_per_year
        * (h.unit_cost if h.unit_cost is not None else 1.0)
        for sku, h in histories.items()
    }
    return _Origin(histories, values, abc_classes(values, *config.abc_thresholds))


def train_history(history: SkuHistory, train_calendar: tuple[str, ...]) -> SkuHistory | None:
    """The part of ``history`` inside ``train_calendar``; ``None`` if it starts later.

    Lead times are kept only when their row falls in the train periods. A
    history without dated lead times (built by hand, not by the reader) keeps
    all of them. ``filled_periods`` is not split and is reported as 0.
    """
    train = set(train_calendar)
    keep = sum(1 for period in history.periods if period in train)
    if keep == 0:
        return None
    lead_times = history.lead_times
    lead_time_periods = history.lead_time_periods
    if len(lead_time_periods) == len(lead_times):
        dated = [(t, p) for t, p in zip(lead_times, lead_time_periods, strict=True) if p in train]
        lead_times = tuple(t for t, _ in dated)
        lead_time_periods = tuple(p for _, p in dated)
    return replace(
        history,
        periods=history.periods[:keep],
        demand=history.demand[:keep],
        lead_times=lead_times,
        lead_time_periods=lead_time_periods,
        filled_periods=0,
    )


def out_of_sample_replay(data: DemandData, config: Config) -> OutOfSampleReport:
    """Fit on all but the last ``config.test_periods`` periods and score on them.

    Raises :class:`HistoryError` when the train periods are fewer than
    ``config.holdout + 2``, the minimum the forecast backtest needs.
    """
    from .analysis import _analyze_sku, replay_policy  # analysis imports this lazily too

    test_periods = config.test_periods
    train_length = len(data.calendar) - test_periods
    if train_length < config.holdout + 2:
        raise HistoryError(
            f"the file covers {len(data.calendar)} period(s); {test_periods} test period(s) "
            f"leave {max(train_length, 0)} for training, and a holdout of {config.holdout} "
            f"needs at least {config.holdout + 2}. Lower --test-periods or --holdout"
        )
    train_calendar = data.calendar[:train_length]
    test_calendar = data.calendar[train_length:]

    fit = _origin(data, train_calendar, config)
    trains, values, classes = fit.histories, fit.values, fit.classes
    skipped = [h.sku for h in data.skus if h.sku not in trains]
    # One refit every K test periods: the origin at calendar index t sees periods
    # 0 .. t - 1 and decides the periods t .. t + K - 1 (the rest of the test, at the end).
    origins = (
        [
            _origin(data, data.calendar[:t], config)
            for t in range(train_length, len(data.calendar), config.refit_every)
        ]
        if config.rolling_origin
        else []
    )

    by_sku = {h.sku: h for h in data.skus}
    results = []
    for history in data.skus:
        train = trains.get(history.sku)
        if train is None:
            continue
        replays = []
        rolling = []
        notes: list[str] = []
        fitted = None
        optimized = None
        for method in SAFETY_STOCK_METHODS:
            settings = replace(config, safety_stock_method=method)
            # Dynamic levels of the test periods come from the fit on train only:
            # the real forecasts 1 to N steps after the end of training.
            ahead = len(history.demand) - len(train.demand)
            search = config.optimize_cost and method == "normal"
            fitted = _analyze_sku(
                train,
                settings,
                classes[history.sku],
                values[history.sku],
                horizon=ahead,
                optimize_inputs=search,
            )
            notes += [note for note in fitted.notes if note not in notes]
            policy = fitted.policy
            levels = fitted.levels + fitted.next_levels
            test = replay_policy(
                history.demand,
                policy,
                fitted.order_quantity,
                levels,
                warmup=len(train.demand),
            )
            replays.append(
                PolicyReplay(
                    method=method,
                    safety_stock=policy.safety_stock,
                    reorder_point=policy.reorder_point,
                    order_quantity=fitted.order_quantity,
                    in_sample=fitted.simulation,
                    out_of_sample=test,
                    test_levels=fitted.next_levels,
                    test_safety_stocks=fitted.next_safety_stocks,
                )
            )
            if search:
                optimized = _optimized_replay(
                    history, train, fitted, config, config.sku_cost_rates(history)
                )
            if origins:
                train_levels = fitted.levels or (policy.reorder_point,) * len(train.demand)
                rolling.append(
                    _rolling_replay(
                        history.demand,
                        settings,
                        origins,
                        history.sku,
                        policy,
                        train_levels,
                        fitted.order_quantity,
                        test_periods,
                    )
                )
        assert fitted is not None  # SAFETY_STOCK_METHODS is not empty
        results.append(
            SkuOutOfSample(
                sku=history.sku,
                train_periods=len(train.demand),
                test_periods=test_periods,
                abc=fitted.abc,
                category=fitted.profile.category,
                forecast_method=fitted.method,
                forecast=fitted.forecast,
                replays=tuple(replays),
                notes=tuple(notes),
                rolling=tuple(rolling),
                optimized=optimized,
            )
        )
    return OutOfSampleReport(
        test_periods=test_periods,
        train_calendar=train_calendar,
        test_calendar=test_calendar,
        skus=tuple(results),
        skipped=tuple(skipped),
        policy=config.policy,
        bootstrap_source=config.bootstrap_source,
        rolling_origin=config.rolling_origin,
        refit_every=config.refit_every,
        costs=config.cost_rates,
        sku_rates=(
            {s.sku: config.sku_cost_rates(by_sku[s.sku]) for s in results}
            if config.per_sku_costs
            else {}
        ),
        holding_cost_rate=config.holding_cost_rate,
        cost_columns=config.cost_columns,
        optimize_cost=config.optimize_cost,
        optimize_samples=config.optimize_samples if config.optimize_cost else 0,
        optimize_fill_floor=config.optimize_fill_floor,
    )


def _optimized_replay(
    history: SkuHistory, train: SkuHistory, fitted: SkuResult, config: Config, rates: CostRates
) -> OptimizedReplay:
    """Search the safety stock and quantity of ``history`` for cost on ``train`` only.

    ``fitted`` is the normal policy fitted on ``train`` with the inputs of the
    search (the forecast of every test period and the one-step errors of the
    training periods). The demand paths and every grid bound come from
    ``train`` and ``fitted``; the test demand is used only by the final replay.
    """
    from .analysis import replay_policy

    policy = fitted.policy
    train_length = len(train.demand)
    test_length = len(history.demand) - train_length
    train_levels = fitted.levels or (policy.reorder_point,) * train_length
    test_levels = fitted.next_levels or (policy.reorder_point,) * test_length
    base = tuple(level - policy.safety_stock for level in test_levels)
    mean = statistics.fmean(train.demand)
    errors, source = fitted.forecast_errors, "forecast errors"
    if len(errors) < 2:
        errors = tuple(d - mean for d in train.demand)
        source = "demand deviations"
    protection = max(protection_periods(policy.lead_time, policy.review_period), 1)
    sigma = statistics.pstdev(errors) * math.sqrt(protection)
    rng = random.Random(f"{config.seed}:{history.sku}:optimize")
    paths = demand_paths(fitted.next_forecasts, errors, config.optimize_samples, rng)
    result = search_levels(
        train.demand,
        train_levels,
        fitted.order_quantity,
        policy.kind,
        int(policy.review_period) if policy.kind == "RsS" else 1,
        policy.lead_time,
        base,
        paths,
        rates,
        safety_grid(policy.safety_stock, sigma, policy.reorder_point - policy.safety_stock),
        quantity_grid(fitted.order_quantity, mean),
        refine_step=sigma / 4,
        fill_floor=config.optimize_fill_floor,
    )
    levels = tuple(b + result.safety_stock for b in base)
    replay = replay_policy(
        history.demand,
        policy,
        (fitted.order_quantity,) * train_length + (result.order_quantity,) * test_length,
        train_levels + levels,
        warmup=train_length,
    )
    return OptimizedReplay(
        search=result,
        test_levels=levels,
        order_quantity=result.order_quantity,
        error_source=source,
        errors=len(errors),
        out_of_sample=replay,
    )


def _rolling_replay(
    demand: tuple[float, ...],
    settings: Config,
    origins: list[_Origin],
    sku: str,
    train_policy: Policy,
    train_levels: tuple[float, ...],
    train_quantity: float,
    test_periods: int,
) -> RollingReplay:
    """Refit ``sku`` at every origin and replay the test with the refitted decisions.

    Each origin decides ``settings.refit_every`` test periods (fewer for the
    last one): the refit's level and safety stock of each of them (the same
    numbers with a static policy; with dynamic levels, its forecasts 1 to ``K``
    steps ahead) and its order quantity.

    The refit at an origin is the same :func:`_analyze_sku` call as on train,
    on the history before the origin only, so a test period can influence the
    decisions of the periods after it and never of itself or the ones before.
    The training periods keep ``train_levels`` and ``train_quantity``, so the
    test starts from the state the fixed replay reaches. The refits' notes are
    not repeated: the first origin is the training fit, whose notes are listed.
    """
    from .analysis import _analyze_sku, replay_policy

    methods: list[str] = []
    stocks: list[float] = []
    levels: list[float] = []
    quantities: list[float] = []
    for index, origin in enumerate(origins):
        start = index * settings.refit_every
        span = min(settings.refit_every, test_periods - start)
        fitted = _analyze_sku(
            origin.histories[sku],
            settings,
            origin.classes[sku],
            origin.values[sku],
            horizon=span,
        )
        # With dynamic levels, next_levels[j] is the level of the end of the j-th
        # period after the history the refit saw (j = 0: the origin's own period).
        for j in range(span):
            methods.append(fitted.method)
            levels.append(
                fitted.next_levels[j] if fitted.next_levels else fitted.policy.reorder_point
            )
            stocks.append(
                fitted.next_safety_stocks[j]
                if fitted.next_safety_stocks
                else fitted.policy.safety_stock
            )
            quantities.append(fitted.order_quantity)
    warmup = len(train_levels)
    result = replay_policy(
        demand,
        train_policy,
        (train_quantity,) * warmup + tuple(quantities),
        train_levels + tuple(levels),
        warmup=warmup,
    )
    return RollingReplay(
        method=settings.safety_stock_method,
        forecast_methods=tuple(methods),
        safety_stocks=tuple(stocks),
        levels=tuple(levels),
        order_quantities=tuple(quantities),
        out_of_sample=result,
    )
