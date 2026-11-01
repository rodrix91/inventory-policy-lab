"""Direct policy construction must reject invalid optional EOQ and bootstrap amounts."""

from __future__ import annotations

import math
from typing import Any

import pytest

from inventory_policy_lab import build_policy


def policy(**kwargs: Any) -> object:
    return build_policy(
        service_level=0.95,
        demand_per_period=10.0,
        sigma_demand=2.0,
        lead_time=2.0,
        review_period=1.0,
        **kwargs,
    )


INVALID_QUANTITIES: tuple[Any, ...] = (
    -1,
    -0.01,
    math.nan,
    math.inf,
    -math.inf,
    True,
    False,
    "4",
    [],
    {},
    1 + 2j,
    object(),
    10**400,
)


@pytest.mark.parametrize("name", ["eoq_units", "bootstrap_units"])
@pytest.mark.parametrize("invalid", INVALID_QUANTITIES)
def test_invalid_optional_quantities_fail_with_clear_error(name: str, invalid: Any) -> None:
    with pytest.raises(ValueError, match=rf"{name} must be finite and non-negative"):
        policy(**{name: invalid})


def test_valid_optional_quantities_preserve_policy_values_and_methods() -> None:
    plain = build_policy(0.95, 10.0, 2.0, lead_time=2.0, review_period=1.0)
    assert plain.eoq is None
    assert plain.safety_stock_method == "normal"

    regular = build_policy(0.95, 10.0, 2.0, lead_time=2.0, review_period=1.0, eoq_units=50.0)
    assert regular.eoq == 50.0
    assert regular.safety_stock == plain.safety_stock
    assert regular.reorder_point == plain.reorder_point

    zero = build_policy(
        0.95,
        10.0,
        2.0,
        lead_time=2.0,
        review_period=1.0,
        eoq_units=0.0,
        bootstrap_units=0.0,
    )
    assert zero.eoq == 0.0
    assert zero.safety_stock_method == "bootstrap"
    assert zero.safety_stock == 0.0
    assert zero.reorder_point == 30.0

    bootstrap = build_policy(
        0.95,
        10.0,
        2.0,
        lead_time=2.0,
        review_period=1.0,
        eoq_units=25.0,
        bootstrap_units=4.5,
    )
    assert bootstrap.eoq == 25.0
    assert bootstrap.safety_stock_method == "bootstrap"
    assert bootstrap.safety_stock == 4.5
    assert bootstrap.reorder_point == 34.5


def test_invalid_kind_keeps_prior_validation_priority() -> None:
    with pytest.raises(ValueError, match="kind must be"):
        policy(kind="unsupported", eoq_units=-1, bootstrap_units=-1)
