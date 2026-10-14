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
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from .classify import abc_classes
from .errors import HistoryError
from .reader import DemandData, SkuHistory
from .simulate import SimulationResult

SAFETY_STOCK_METHODS = ("normal", "bootstrap")

if TYPE_CHECKING:  # pragma: no cover - imports for type hints only
    from .analysis import Config


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

    def replay(self, method: str) -> PolicyReplay:
        return next(r for r in self.replays if r.method == method)


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
    policy: str = "sQ"  # the policy kind replayed: "sQ" or "RS"

    def totals(self, method: str, sample: str) -> ReplayTotals:
        """Totals of ``method`` for ``sample`` ``"in_sample"`` or ``"out_of_sample"``."""
        results = [getattr(s.replay(method), sample) for s in self.skus]
        demand = sum(r.total_demand for r in results)
        served = sum(r.served_from_stock for r in results)
        return ReplayTotals(
            total_demand=demand,
            served_from_stock=served,
            fill_rate=served / demand if demand > 0 else None,
            stockout_periods=sum(r.stockout_periods for r in results),
            average_on_hand=sum(r.average_on_hand for r in results),
        )


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

    trains: dict[str, SkuHistory] = {}
    skipped: list[str] = []
    for history in data.skus:
        train = train_history(history, train_calendar)
        if train is None:
            skipped.append(history.sku)
        else:
            trains[history.sku] = train
    values = {
        sku: statistics.fmean(h.demand)
        * config.periods_per_year
        * (h.unit_cost if h.unit_cost is not None else 1.0)
        for sku, h in trains.items()
    }
    classes = abc_classes(values, *config.abc_thresholds)

    results = []
    for history in data.skus:
        train = trains.get(history.sku)
        if train is None:
            continue
        replays = []
        notes: list[str] = []
        fitted = None
        for method in SAFETY_STOCK_METHODS:
            settings = replace(config, safety_stock_method=method)
            # Dynamic levels of the test periods come from the fit on train only:
            # the real forecasts 1 to N steps after the end of training.
            ahead = len(history.demand) - len(train.demand)
            fitted = _analyze_sku(
                train, settings, classes[history.sku], values[history.sku], horizon=ahead
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
            )
        )
    return OutOfSampleReport(
        test_periods=test_periods,
        train_calendar=train_calendar,
        test_calendar=test_calendar,
        skus=tuple(results),
        skipped=tuple(skipped),
        policy=config.policy,
    )
