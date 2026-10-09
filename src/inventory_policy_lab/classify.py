"""ABC, XYZ and demand-pattern (Syntetos-Boylan) classification."""

from __future__ import annotations

import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

# Syntetos, Boylan & Croston (2005) cut-off values.
ADI_CUTOFF = 1.32
CV2_CUTOFF = 0.49


def abc_classes(values: Mapping[str, float], a: float = 0.80, b: float = 0.95) -> dict[str, str]:
    """Pareto ABC classes from a value per item (annual consumption value).

    Items are sorted by value, largest first (ties by name). An item is ``A``
    while the cumulative share of the items *before* it is below ``a``, ``B``
    while it is below ``b``, and ``C`` after that. Testing the share before
    the item means the largest item is always ``A``, even when it alone is
    more than ``a`` of the total. When the total is zero, every item is ``C``.
    """
    total = sum(values.values())
    if total <= 0:
        return dict.fromkeys(values, "C")
    ordered = sorted(values.items(), key=lambda item: (-item[1], item[0]))
    classes: dict[str, str] = {}
    cumulative = 0.0
    for name, value in ordered:
        share_before = cumulative / total
        classes[name] = "A" if share_before < a else "B" if share_before < b else "C"
        cumulative += value
    return classes


def coefficient_of_variation(demand: Sequence[float]) -> float | None:
    """Population standard deviation over mean of per-period demand; ``None`` if the mean is 0."""
    mean = statistics.fmean(demand)
    if mean == 0:
        return None
    return statistics.pstdev(demand) / mean


def xyz_class(cv: float | None, x: float = 0.5, y: float = 1.0) -> str:
    """``X`` if CV <= x, ``Y`` if CV <= y, else ``Z`` (also when there is no demand)."""
    if cv is None:
        return "Z"
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
    """
    sizes = [q for q in demand if q > 0]
    if not sizes:
        return DemandProfile(adi=None, cv2=None, nonzero_periods=0, category="no demand")
    adi = len(demand) / len(sizes)
    cv2 = (statistics.pstdev(sizes) / statistics.fmean(sizes)) ** 2
    if adi < adi_cutoff:
        category = "smooth" if cv2 < cv2_cutoff else "erratic"
    else:
        category = "intermittent" if cv2 < cv2_cutoff else "lumpy"
    return DemandProfile(adi=adi, cv2=cv2, nonzero_periods=len(sizes), category=category)
