"""Read a long-format CSV of demand history into one series per SKU.

Expected columns (header names are case-insensitive and trimmed):

- ``sku``: item identifier.
- ``period`` (or ``date``): ``YYYY-MM`` months, ``YYYY-MM-DD`` dates, or integers.
  Every row must use the same kind.
- ``quantity`` (or ``qty`` / ``demand``): demand in the period, a number >= 0.
- ``unit_cost`` (optional): cost of one unit; the most recent non-empty value per
  SKU is used.
- ``lead_time`` (optional): an observed replenishment lead time in periods. All
  non-empty values of a SKU are treated as lead-time observations, each dated
  by the period of its row (the out-of-sample replay trains on the earlier ones).
- ``order_cost`` and ``stockout_cost`` (optional, read only with
  ``cost_columns=True``, the ``--cost-columns`` option): the cost per order
  placed and per unit short of the SKU, to price the out-of-sample replay
  (ADR 0014); the most recent non-empty value per SKU is used, like ``unit_cost``.
  Without the option these columns are ignored like any other extra column.

Several rows for the same SKU and period are summed (transaction lines). Each
SKU's series starts at its first period in the file and runs to the last period
of the file; periods in between without a row are demand zero. For months and
integers the calendar is complete (a month nobody sold in is still a period);
for dates the calendar is the set of dates that appear in the file, because the
frequency cannot be known.
"""

from __future__ import annotations

import csv
import math
import os
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .errors import DataError, InputFileError

COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "sku": ("sku",),
    "period": ("period", "date"),
    "quantity": ("quantity", "qty", "demand"),
    "unit_cost": ("unit_cost",),
    "lead_time": ("lead_time",),
}
REQUIRED = ("sku", "period", "quantity")
COST_COLUMNS = ("order_cost", "stockout_cost")  # read only with cost_columns (ADR 0014)

_MONTH = re.compile(r"^(\d{4})-(\d{2})$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_INT = re.compile(r"^-?\d+$")


@dataclass(frozen=True)
class SkuHistory:
    """The demand series of one SKU, aligned to the file's calendar."""

    sku: str
    periods: tuple[str, ...]
    demand: tuple[float, ...]
    unit_cost: float | None
    lead_times: tuple[float, ...]
    filled_periods: int  # periods with no row, counted as demand zero
    lead_time_periods: tuple[str, ...] = ()  # period of the row of each lead time
    order_cost: float | None = None  # order_cost column, with cost_columns (ADR 0014)
    stockout_cost: float | None = None  # stockout_cost column, with cost_columns (ADR 0014)


@dataclass(frozen=True)
class DemandData:
    """Everything read from one file."""

    source: str
    rows: int
    period_kind: str  # "month", "date" or "integer"
    calendar: tuple[str, ...]
    has_unit_cost: bool
    has_lead_time: bool
    skus: tuple[SkuHistory, ...]
    has_order_cost: bool = False  # read with cost_columns and the column is present
    has_stockout_cost: bool = False


def _period_kind(value: str) -> str:
    match = _MONTH.match(value)
    if match and 1 <= int(match.group(2)) <= 12:
        return "month"
    if _DATE.match(value):
        try:
            date.fromisoformat(value)
        except ValueError:
            return "invalid"
        return "date"
    if _INT.match(value):
        return "integer"
    return "invalid"


def _month_index(value: str) -> int:
    year, month = value.split("-")
    return int(year) * 12 + int(month) - 1


def _month_label(index: int) -> str:
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


def _calendar(kind: str, values: Iterable[str]) -> tuple[str, ...]:
    distinct = set(values)
    if kind == "month":
        indexes = [_month_index(v) for v in distinct]
        return tuple(_month_label(i) for i in range(min(indexes), max(indexes) + 1))
    if kind == "integer":
        numbers = [int(v) for v in distinct]
        return tuple(str(i) for i in range(min(numbers), max(numbers) + 1))
    return tuple(sorted(distinct))


def _number(text: str, column: str, line: int) -> float:
    try:
        value = float(text)
    except ValueError:
        raise DataError(f"line {line}: {column} {text!r} is not a number") from None
    if not math.isfinite(value):
        raise DataError(f"line {line}: {column} {text!r} is not a finite number")
    return value


def _resolve_columns(header: list[str], cost_columns: bool = False) -> dict[str, int]:
    normalized = [name.strip().lower() for name in header]
    found: dict[str, int] = {}
    aliases_of = dict(COLUMN_ALIASES)
    if cost_columns:
        aliases_of.update((name, (name,)) for name in COST_COLUMNS)
    for field, aliases in aliases_of.items():
        for alias in aliases:
            if alias in normalized:
                found[field] = normalized.index(alias)
                break
    missing = [field for field in REQUIRED if field not in found]
    if missing:
        expected = "; ".join("/".join(COLUMN_ALIASES[field]) for field in missing)
        raise DataError(
            f"missing required column(s): {expected} (header: {', '.join(header) or 'empty'})"
        )
    return found


def read_demand(path: str | os.PathLike[str], cost_columns: bool = False) -> DemandData:
    """Read ``path`` and return its demand history, one :class:`SkuHistory` per SKU.

    With ``cost_columns`` the optional ``order_cost`` and ``stockout_cost``
    columns are read too (ADR 0014).
    """
    file = Path(path)
    try:
        with file.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.reader(handle))
    except FileNotFoundError:
        raise InputFileError(f"file not found: {file}") from None
    except IsADirectoryError:
        raise InputFileError(f"not a file: {file}") from None
    except UnicodeDecodeError as exc:
        raise InputFileError(
            f"{file} is not valid UTF-8 (byte {exc.start}); re-save it as UTF-8"
        ) from None
    return parse_rows(rows, source=str(file), cost_columns=cost_columns)


def parse_rows(
    rows: list[list[str]], source: str = "<rows>", cost_columns: bool = False
) -> DemandData:
    """Parse already-split CSV rows (header first). Used by :func:`read_demand`."""
    if not rows:
        raise DataError(f"{source} is empty")
    columns = _resolve_columns(rows[0], cost_columns)
    width = max(columns.values()) + 1

    totals: dict[str, dict[str, float]] = {}
    costs: dict[str, float] = {}
    lead_times: dict[str, list[float]] = {}
    lead_time_periods: dict[str, list[str]] = {}
    sku_costs: dict[str, dict[str, float]] = {name: {} for name in COST_COLUMNS}
    kinds: set[str] = set()
    data_rows = 0

    for line, row in enumerate(rows[1:], start=2):
        if not any(cell.strip() for cell in row):
            continue
        if len(row) < width:
            raise DataError(f"line {line}: expected at least {width} fields, found {len(row)}")
        data_rows += 1
        sku = row[columns["sku"]].strip()
        period = row[columns["period"]].strip()
        quantity_text = row[columns["quantity"]].strip()
        if not sku:
            raise DataError(f"line {line}: empty sku")
        kind = _period_kind(period)
        if kind == "invalid":
            raise DataError(
                f"line {line}: period {period!r} is not YYYY-MM, YYYY-MM-DD or an integer"
            )
        kinds.add(kind)
        if len(kinds) > 1:
            raise DataError(
                f"line {line}: period {period!r} mixes period formats "
                f"({' and '.join(sorted(kinds))}); use one format for the whole file"
            )
        if not quantity_text:
            raise DataError(f"line {line}: empty quantity for sku {sku!r}")
        quantity = _number(quantity_text, "quantity", line)
        if quantity < 0:
            raise DataError(
                f"line {line}: negative quantity {quantity_text} for sku {sku!r}; "
                "net returns out of the demand history before the analysis"
            )
        per_period = totals.setdefault(sku, {})
        per_period[period] = per_period.get(period, 0.0) + quantity

        if "unit_cost" in columns:
            cost_text = row[columns["unit_cost"]].strip()
            if cost_text:
                cost = _number(cost_text, "unit_cost", line)
                if cost < 0:
                    raise DataError(f"line {line}: negative unit_cost {cost_text}")
                costs[sku] = cost  # the most recent row wins
        if "lead_time" in columns:
            lead_text = row[columns["lead_time"]].strip()
            if lead_text:
                lead = _number(lead_text, "lead_time", line)
                if lead < 0:
                    raise DataError(f"line {line}: negative lead_time {lead_text}")
                lead_times.setdefault(sku, []).append(lead)
                lead_time_periods.setdefault(sku, []).append(period)
        for name in COST_COLUMNS:
            if name in columns:
                text = row[columns[name]].strip()
                if text:
                    value = _number(text, name, line)
                    if value < 0:
                        raise DataError(f"line {line}: negative {name} {text}")
                    sku_costs[name][sku] = value  # the most recent row wins

    if not totals:
        raise DataError(f"{source} has a header but no data rows")

    kind = kinds.pop()
    all_periods = [p for per_period in totals.values() for p in per_period]
    calendar = _calendar(kind, all_periods)
    position = {period: index for index, period in enumerate(calendar)}

    histories = []
    for sku in sorted(totals):
        per_period = totals[sku]
        start = min(position[p] for p in per_period)
        periods = calendar[start:]
        demand = tuple(per_period.get(p, 0.0) for p in periods)
        histories.append(
            SkuHistory(
                sku=sku,
                periods=periods,
                demand=demand,
                unit_cost=costs.get(sku),
                lead_times=tuple(lead_times.get(sku, ())),
                filled_periods=len(periods) - len(per_period),
                lead_time_periods=tuple(lead_time_periods.get(sku, ())),
                order_cost=sku_costs["order_cost"].get(sku),
                stockout_cost=sku_costs["stockout_cost"].get(sku),
            )
        )
    return DemandData(
        source=source,
        rows=data_rows,
        period_kind=kind,
        calendar=calendar,
        has_unit_cost="unit_cost" in columns,
        has_lead_time="lead_time" in columns,
        skus=tuple(histories),
        has_order_cost="order_cost" in columns,
        has_stockout_cost="stockout_cost" in columns,
    )
