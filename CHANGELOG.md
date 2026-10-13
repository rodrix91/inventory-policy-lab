# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [Semantic Versioning](https://semver.org/) (pre-1.0: minor versions may change behavior).

## [Unreleased]

### Added

- Bootstrap safety stock (`--safety-stock bootstrap`, `--bootstrap-samples`, `--seed`; `bootstrap_safety_stock` in the API): the service-level quantile of protection-interval demand resampled from each SKU's own history, with lead times drawn from the observed ones, instead of the normal formula. Seeded per SKU, so reports are reproducible. On the synthetic example the lumpy SKU-012 goes from 72.5% to 100% replayed fill rate and total average stock falls from 1,257.5 to 1,065.4 units (in-sample; see ADR 0004).
- `safety_stock_method` in the JSON policy of each SKU and `safety_stock_method`, `bootstrap_samples` and `seed` in the JSON settings.

## [0.1.0] - 2026-10-09

First public version (alpha).

### Added

- Reader for long-format demand CSVs (`sku`, `period`/`date`, `quantity`, optional `unit_cost` and `lead_time`): `YYYY-MM`, `YYYY-MM-DD` or integer periods, duplicate rows summed, gaps after an item's first period filled with zero demand, clear errors for missing columns, invalid numbers, negative values and mixed period formats.
- ABC classification by annual consumption value (or annual units without unit costs) and XYZ classification by coefficient of variation, both with configurable thresholds, and the ABC-XYZ matrix.
- Demand-pattern classification after Syntetos, Boylan & Croston (2005): ADI and CV² with the 1.32 / 0.49 cut-offs (smooth, erratic, intermittent, lumpy).
- Forecasting methods: naive, moving average, simple exponential smoothing, Croston and the Syntetos-Boylan approximation (SBA). A rolling one-step holdout backtest reports MAE, RMSE, bias and MASE (Hyndman & Koehler, 2006), and the method with the lowest MASE is picked per SKU. Intermittent and lumpy SKUs are scored with SES, Croston and SBA only (ADR 0002).
- Policy per SKU: safety stock and reorder point for a target cycle service level with `statistics.NormalDist`, demand and lead-time variability, and a review period added to the protection interval; per-class service levels; EOQ when an ordering cost and a holding rate are given.
- Replay of the demand history under the resulting (s, Q) policy with backorders: fill rate, stockout periods, average stock on hand, orders placed and the largest backorder (ADR 0003).
- `inventory-policy-lab` command (also `python -m inventory_policy_lab`) with Markdown and JSON output, `--output`, documented exit codes (2 usage, 3 input file, 4 invalid data, 5 history too short), and a Python API (`analyze_file`, `analyze`, `read_demand`, the methods and formulas).
- Synthetic, seeded example dataset (`examples/demand_synthetic.csv`, `scripts/generate_example.py`), a hand-checked worked example (`examples/worked_example.csv`, verified in `tests/test_worked_example.py`) and an ABC Pareto chart drawn as SVG with the standard library (`docs/abc-pareto.svg`).
- README samples generated from real runs and checked by the test suite; CI on Python 3.11, 3.12 and 3.13 with tests, 100% line and branch coverage, Ruff and strict mypy; a release workflow that builds and tests the sdist and wheel.

[Unreleased]: https://github.com/rodrix91/inventory-policy-lab/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/rodrix91/inventory-policy-lab/releases/tag/v0.1.0
