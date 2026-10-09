"""The analysis pipeline: settings, fallbacks and the notes that explain them."""

from __future__ import annotations

from typing import Any

import pytest
from conftest import EXAMPLES

from inventory_policy_lab import (
    Config,
    ConfigError,
    DataError,
    HistoryError,
    analyze,
    analyze_file,
    parse_rows,
)
from inventory_policy_lab.reader import DemandData


def data_from(table: dict[str, list[float]], **extra: list[str]) -> DemandData:
    """Integer periods 1..n per SKU, plus optional extra columns (same value each row)."""
    header = ["sku", "period", "quantity", *extra]
    rows = [header]
    for sku, demand in table.items():
        for index, quantity in enumerate(demand, start=1):
            rows.append([sku, str(index), str(quantity), *(extra[c][0] for c in extra)])
    return parse_rows(rows)


SMOOTH = [10.0, 12, 9, 11, 10, 13, 9, 10, 12, 11]


@pytest.mark.parametrize(
    ("settings", "message"),
    [
        ({"service_level": 1.0}, "service_level must be at least 0.5 and below 1"),
        ({"service_level": 0.4}, "service_level must be at least 0.5"),
        ({"class_service_levels": {"D": 0.9}}, "apply to A, B and C, not 'D'"),
        ({"class_service_levels": {"A": 1.5}}, "service level of class A must be"),
        ({"holdout": 0}, "holdout must be at least 1"),
        ({"ma_window": 0}, "moving-average window must be at least 1"),
        ({"ses_alpha": 0}, "ses alpha must be in (0, 1]"),
        ({"croston_alpha": 1.5}, "croston alpha must be in (0, 1]"),
        ({"periods_per_year": 0}, "periods per year must be positive"),
        ({"abc_thresholds": (0.9, 0.8)}, "ABC thresholds must satisfy"),
        ({"xyz_thresholds": (0, 1)}, "XYZ thresholds must satisfy"),
        ({"abc_thresholds": (0.8, 1.2)}, "cannot exceed 1"),
        ({"lead_time": -1}, "lead time and its standard deviation cannot be negative"),
        ({"lead_time_std": -1}, "cannot be negative"),
        ({"review_period": -1}, "review period cannot be negative"),
        ({"ordering_cost": 10}, "EOQ needs both an ordering cost and a holding rate"),
        ({"holding_rate": 0.2}, "EOQ needs both"),
        ({"ordering_cost": -1, "holding_rate": 0.2}, "ordering cost cannot be negative"),
        ({"ordering_cost": 1, "holding_rate": 0}, "holding rate must be positive"),
        ({"order_cover": 0}, "order cover must be positive"),
        ({"sigma": "mad"}, "sigma must be 'demand' or 'rmse'"),
    ],
)
def test_invalid_settings(settings: dict[str, Any], message: str) -> None:
    with pytest.raises(ConfigError) as excinfo:
        Config(**settings).validate()
    assert message in str(excinfo.value)
    assert excinfo.value.exit_code == 2


def test_too_short_history_is_a_history_error() -> None:
    with pytest.raises(HistoryError, match="covers 5 period") as excinfo:
        analyze(data_from({"a": [1, 2, 3, 4, 5]}))
    assert excinfo.value.exit_code == 5


def test_unit_cost_must_be_given_for_every_sku() -> None:
    rows = [
        ["sku", "period", "quantity", "unit_cost"],
        *[["a", str(i), "1", "2"] for i in range(1, 9)],
        *[["b", str(i), "1", ""] for i in range(1, 9)],
    ]
    with pytest.raises(DataError, match="unit_cost is empty for every row of sku\\(s\\): b"):
        analyze(parse_rows(rows))


def test_eoq_needs_a_unit_cost_column() -> None:
    with pytest.raises(DataError, match="EOQ needs a unit_cost column"):
        analyze(data_from({"a": SMOOTH}), Config(ordering_cost=10, holding_rate=0.2))


def test_abc_by_quantity_without_unit_costs_and_cover_quantity() -> None:
    report = analyze(data_from({"a": SMOOTH, "b": [1.0] * 10}), Config(order_cover=2))
    assert report.abc_basis == "quantity"
    a = report.skus[0]
    assert a.annual_value == pytest.approx(sum(SMOOTH) / 10 * 12)
    assert a.order_quantity == pytest.approx(2 * a.forecast)
    assert a.order_quantity_source == "cover"
    assert report.to_dict()["abc_basis"] == "quantity"


def test_class_service_levels_override_the_default() -> None:
    config = Config(service_level=0.9, class_service_levels={"A": 0.99})
    report = analyze(data_from({"a": SMOOTH, "b": [0.1] * 10}), config)
    assert report.skus[0].abc == "A" and report.skus[0].policy.service_level == 0.99
    assert report.skus[1].abc == "C" and report.skus[1].policy.service_level == 0.9


def test_sigma_rmse_uses_the_backtest_error() -> None:
    report = analyze(data_from({"a": SMOOTH}), Config(sigma="rmse"))
    picked = {b.method: b for b in report.skus[0].backtests}[report.skus[0].method]
    assert report.skus[0].policy.sigma_demand == picked.rmse


def test_short_sku_skips_the_backtest() -> None:
    rows = [["sku", "period", "quantity"]]
    rows += [["old", str(i), str(q)] for i, q in enumerate(SMOOTH, start=1)]
    rows += [["new", "8", "4"], ["new", "9", "6"], ["new", "10", "8"]]
    report = analyze(parse_rows(rows), Config(sigma="rmse"))
    new = report.skus[0]
    assert new.sku == "new" and new.periods == 3
    assert new.backtests == ()
    assert new.method == "moving_average"
    assert new.forecast == 6
    assert any("no backtest, moving_average used" in n for n in new.notes)
    assert any("demand standard deviation used" in n for n in new.notes)


def test_short_intermittent_sku_uses_ses_and_one_period_sku_has_no_sigma() -> None:
    rows = [["sku", "period", "quantity"]]
    rows += [["old", str(i), str(q)] for i, q in enumerate(SMOOTH, start=1)]
    rows += [["late", "8", "0"], ["late", "9", "0"], ["late", "10", "5"], ["one", "10", "3"]]
    report = analyze(parse_rows(rows))
    late, _, one = report.skus
    assert late.profile.category == "intermittent"
    assert late.method == "ses"
    assert one.policy.sigma_demand == 0


def test_zero_forecast_falls_back_to_one_unit_and_constant_training_uses_mae() -> None:
    report = analyze(data_from({"a": [0.0] * 10}), Config())
    a = report.skus[0]
    assert a.profile.category == "no demand"
    assert a.forecast == 0
    assert a.order_quantity == 1 and a.order_quantity_source == "minimum"
    assert any("MASE undefined" in n for n in a.notes)
    assert any("order quantity set to 1 unit" in n for n in a.notes)
    assert report.overall_fill_rate() is None
    assert report.profile_counts()["no demand"] == 1


def test_observed_lead_time_variability() -> None:
    rows = [["sku", "period", "quantity", "lead_time"]]
    rows += [["a", str(i), str(q), "2" if i % 2 else "4"] for i, q in enumerate(SMOOTH, 1)]
    policy = analyze(parse_rows(rows)).skus[0].policy
    assert policy.lead_time == 3
    assert policy.sigma_lead_time == pytest.approx(1.0540926)  # sample sd of 2,4,2,4,...


def test_default_lead_time_settings_are_used_without_observations() -> None:
    policy = analyze(data_from({"a": SMOOTH}), Config(lead_time=3, lead_time_std=0.5)).skus[0]
    assert (policy.policy.lead_time, policy.policy.sigma_lead_time) == (3, 0.5)


def test_synthetic_example_runs_and_is_consistent() -> None:
    report = analyze_file(EXAMPLES / "demand_synthetic.csv")
    assert len(report.skus) == 12
    assert sum(sum(row.values()) for row in report.matrix().values()) == 12
    for result in report.skus:
        assert result.abc_xyz == result.abc + result.xyz
        assert result.policy.reorder_point >= result.policy.safety_stock >= 0
        if result.profile.category in ("intermittent", "lumpy"):
            assert {b.method for b in result.backtests} == {"ses", "croston", "sba"}
