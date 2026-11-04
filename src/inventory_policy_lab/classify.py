"""ABC, XYZ and demand-pattern (Syntetos-Boylan) classification."""

from __future__ import annotations

import math
import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

# Syntetos, Boylan & Croston (2005) cut-off values.
ADI_CUTOFF = 1.32
CV2_CUTOFF = 0.49


def _valid_nonnegative_number(value: float) -> bool:
    """A finite, non-negative numeric input, excluding bool and malformed objects."""
    if isinstance(value, bool):
        return False
    try:
        return math.isfinite(value) and value >= 0
    except (TypeError, ValueError, OverflowError):
        return False


def abc_classes(values: Mapping[str, float], a: float = 0.80, b: float = 0.95) -> dict[str, str]:
    """Pareto ABC classes from a value per item (annual consumption value).

    Items are sorted by value, largest first (ties by name). An item is ``A``
    while the cumulative share of the items *before* it is below ``a``, ``B``
    while it is below ``b``, and ``C`` after that. Testing the share before
    the item means the largest item is always ``A``, even when it alone is
    more than ``a`` of the total. When the total is zero, every item is ``C``.
    Scale large finite item values if their sum would overflow, so ABC shares
    stay meaningful rather than making every SKU an A-class item. Both class
    cutoffs and item values are validated here, even when this public function
    is called without the higher-level Config validation.
    """
    if not (_valid_nonnegative_number(a) and _valid_nonnegative_number(b) and 0 < a < b <= 1):
        raise ValueError("ABC thresholds must satisfy 0 < a < b <= 1")
    if any(not _valid_nonnegative_number(value) for value in values.values()):
        raise ValueError("ABC item values must be finite and non-negative")
    total = sum(values.values())
    if not math.isfinite(total):
        # Every item is finite but their sum can overflow to infinity.
        # Scale before summing so cumulative ABC shares still reflect the
        # relative values rather than silently making every item class A.
        maximum = max(values.values())
        scaled = {name: value / maximum for name, value in values.items()}
        total = math.fsum(scaled.values())
        ordered = sorted(scaled.items(), key=lambda item: (-item[1], item[0]))
    else:
        ordered = sorted(values.items(), key=lambda item: (-item[1], item[0]))
    if total <= 0:
        return dict.fromkeys(values, "C")
    classes: dict[str, str] = {}
    cumulative = 0.0
    for name, value in ordered:
        share_before = cumulative / total
        classes[name] = "A" if share_before < a else "B" if share_before < b else "C"
        cumulative += value
    return classes


def coefficient_of_variation(demand: Sequence[float]) -> float | None:
    """Population standard deviation / mean for valid non-negative demand.

    Return ``None`` for an empty or all-zero history. Reject invalid values
    here too: the public helper can be called without ``demand_profile()``.
    """
    if not demand:
        return None
    for index, value in enumerate(demand):
        if not _valid_nonnegative_number(value):
            raise ValueError(f"demand[{index}] must be finite and non-negative")
    # CV is scale-invariant for non-negative demand. Normalize *before*
    # computing both moments, not only when fmean() overflows: subnormal
    # positive values can also make fmean() round to zero or pstdev()
    # underflow to zero, incorrectly reporting no demand or no variation.
    # The largest observation becomes exactly 1.0, while all values remain
    # in [0, 1]; this also avoids overflow for very large finite histories.
    maximum = max(demand)
    if maximum == 0:
        return None
    normalized = [value / maximum for value in demand]
    return statistics.pstdev(normalized) / statistics.fmean(normalized)


def xyz_class(cv: float | None, x: float = 0.5, y: float = 1.0) -> str:
    """Classify non-negative finite CV using finite, strictly increasing cutoffs.

    ``None`` (no demand) remains class ``Z``. The standalone library API
    validates settings as rigorously as the higher-level configuration does.
    """
    if not (_valid_nonnegative_number(x) and _valid_nonnegative_number(y) and 0 < x < y):
        raise ValueError("XYZ thresholds must satisfy finite 0 < x < y")
    if cv is None:
        return "Z"
    if not _valid_nonnegative_number(cv):
        raise ValueError("XYZ coefficient of variation must be finite and non-negative")
    return "X" if cv <= x else "Y" if cv <= y else "Z"


@dataclass(frozen=True)
class DemandProfile:
    """Syntetos-Boylan demand pattern of one series."""

    adi: float | None  # average inter-demand interval, in periods
    cv2: float | None  # squared CV of the non-zero demand sizes
    nonzero_periods: int
    category: str  # smooth, erratic, intermittent, lumpy, or no demand


def demand_profile(
    demand: Sequence[float], adi_cutoff: float = ADI_CUTOFF, cv2_cutoff: float = CV2_CUTOFF
) -> DemandProfile:
    """Classify a series as smooth, erratic, intermittent or lumpy.

    ``ADI`` is the number of periods divided by the number of periods with
    demand; ``CV2`` is the squared population coefficient of variation of the
    non-zero demand sizes. A series without demand is ``no demand``.
    Reject impossible observations and cutoffs in the public API instead of
    silently treating negative quantities as zero-demand periods.
    """
    if not (
        _valid_nonnegative_number(adi_cutoff)
        and adi_cutoff > 0
        and _valid_nonnegative_number(cv2_cutoff)
    ):
        raise ValueError("demand profile cutoffs must have finite ADI > 0 and CV2 >= 0")
    for index, quantity in enumerate(demand):
        if not _valid_nonnegative_number(quantity):
            raise ValueError(f"demand[{index}] must be finite and non-negative")
    sizes = [q for q in demand if q > 0]
    if not sizes:
        return DemandProfile(adi=None, cv2=None, nonzero_periods=0, category="no demand")
    adi = len(demand) / len(sizes)
    cv = coefficient_of_variation(sizes) or 0.0
    cv2 = cv**2
    if adi < adi_cutoff:
        category = "smooth" if cv2 < cv2_cutoff else "erratic"
    else:
        category = "intermittent" if cv2 < cv2_cutoff else "lumpy"
    return DemandProfile(adi=adi, cv2=cv2, nonzero_periods=len(sizes), category=category)
