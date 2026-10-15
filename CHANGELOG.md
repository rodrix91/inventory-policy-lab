# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [Semantic Versioning](https://semver.org/) (pre-1.0: minor versions may change behavior).

## [Unreleased]

### Added

- Bootstrap of forecast residuals, opt-in with `--bootstrap-source residuals` (`Config.bootstrap_source`; the default stays `demand`): the bootstrap resamples the rolling-origin errors of the picked forecast over the protection interval `L + R` (each from a forecast refitted on the periods before its origin, from origin 2) instead of demand per period, so a trend or season the forecast follows is not counted as uncertainty. It applies to `--safety-stock bootstrap` and to the bootstrap replay of `--test-periods`, where only training periods are used (tested by replacing the test periods with zeros). Without enough history for any error the SKU falls back to the demand bootstrap, with a note; the report lists how many errors each SKU used (ADR 0008).
- Safety stock per period, opt-in with `--period-safety-stock` (`Config.period_safety_stock`, needs `--dynamic-levels` and the residual bootstrap): with a damped Holt or Holt-Winters forecast, each period gets `SS(t) = q x D(t) x (L + R)`, with `q` the bootstrap quantile of the relative forecast errors, so the levels follow the season without counting it twice. SKUs with a level forecast keep one safety stock, with a note.
- API: `interval_forecast_errors`, `residual_bootstrap_quantile`, `period_safety_stocks`, `interval_demands`, `protection_periods`; `dynamic_levels` accepts one safety stock per period; `SkuResult.safety_stocks`, `SkuResult.next_safety_stocks`, `PolicyReplay.test_safety_stocks`, `OutOfSampleReport.bootstrap_source`.
- JSON, only with the new options: `bootstrap_source` and `period_safety_stock` in the settings, `safety_stocks` and `next_safety_stocks` in the policy, `test_safety_stocks` out of sample. Without them the Markdown and JSON reports are unchanged, byte for byte.
- Results (out of sample, bootstrap): on the 48-month synthetic series, (R, S) with dynamic levels and R = 1 goes from 89.3% fill rate and 22 stockout periods (demand bootstrap) to 95.4% and 18 (residuals) and 96.3% and 16 (per period); the trending item from a safety stock of 0 and 78.4% to 22.0 units and 93.3%. The normal formula still does better there (100%). On the 24-month example with 12 training months the residual bootstrap is worse in every policy (for (s, Q), 94.6% to 92.2% with 37% more stock), so it stays opt-in.

## [0.4.0] - 2026-10-14

### Added

- Periodic-review, order-up-to policy, opt-in with `--policy RS` (`Config.policy`): the position is reviewed every `--review-period R` periods (a whole number of at least 1) and an order brings it back up to `S = D x (L + R) + SS`, the reorder-point formula with the same safety stock. Works with the normal and bootstrap safety stock and with the in-sample and out-of-sample replays. The Markdown policy table shows `Order-up-to (S)` and `Review (R)`; the JSON policy has `kind`, `order_up_to`, and null `reorder_point` and `order_quantity` (ADR 0007).
- Dynamic levels, opt-in with `--dynamic-levels` (`Config.dynamic_levels`, needs `--trend-seasonal`), for both policies: the level used at the end of period `t` is the mean forecast of the next `L + R` periods x (L + R) + SS, so a seasonal forecast moves s or S month by month instead of one level for the year. Out of sample the test levels are the training fit's forecasts 1 to N steps ahead, so the test periods cannot leak into them (tested). JSON: `levels`, `next_levels` and, out of sample, `test_levels`.
- API: `simulate_periodic`, `replay_policy`, `dynamic_levels`, `SmoothingFit.calendar_forecasts`, `Policy.kind`, `Policy.order_up_to`, `SkuResult.levels`, `SkuResult.next_levels`, `PolicyReplay.test_levels`, `OutOfSampleReport.policy`; `simulate` accepts one reorder point per period.
- JSON settings: `policy` and `dynamic_levels` (always present). Without the new options the Markdown report is unchanged.
- Results (out of sample, normal safety stock): on the 48-month synthetic series, (R, S) with dynamic levels reaches 100% fill rate with no stockout period and 105.5 units of average stock, against 99.6% and 289.0 for the static (s, Q) with Holt-Winters; dynamic levels alone cut (R, S) stock by about 25%. The bootstrap does worse with (R, S) (85.5% static, 89.3% dynamic). On the 24-month example the dynamic levels change nothing (no seasonal model with 12 training months), and (R, S) with R = 1 gives 90.9% fill rate with 32% less stock than (s, Q) at 94.4%.

## [0.3.0] - 2026-10-14

### Added

- Trend and seasonal forecasts, opt-in with `--trend-seasonal` (`Config.trend_seasonal`): damped Holt and additive and multiplicative Holt-Winters with a damped trend join the backtest of smooth and erratic SKUs, after the level methods, and are picked by the same lowest-MASE rule. Standard library only. Parameters come from a grid search on the squared one-step errors of the history each fit sees, so neither the holdout nor the `--test-periods` window can leak into them. A model is not a candidate without enough history (damped Holt: 4 periods before the first holdout origin; Holt-Winters: two full seasons; multiplicative: demand in every period). When one is picked, the policy uses its mean forecast over the protection interval `L + R`. API: `holt_damped`, `holt_winters`, `fit_holt_damped`, `fit_holt_winters`, `holt_damped_fit`, `holt_winters_fit`, `SmoothingFit`, `FitError` (ADR 0006).
- `--season-length M` (`Config.season_length`), the Holt-Winters season, by default `--periods-per-year` when it is a whole number; it is a usage error without `--trend-seasonal`.
- JSON: `trend_seasonal` and `season_length` in the settings (always present; `season_length` is null without the option), and `parameters` in a SKU's forecast when a smoothing model is picked. The Markdown report adds a settings line and backtest columns only with the option.
- Results: on the synthetic 24-month example with `--test-periods 12`, the out-of-sample results do not change (fill rate 94.4% normal, 94.6% bootstrap; SKU-003 82.9% / 94.4%, SKU-004 79.7% / 67.7%): 12 training months are too few for Holt-Winters, and damped Holt loses SKU-004's training holdout. On the full history damped Holt is picked for SKU-003 and SKU-009 (all-SKU replayed fill rate 99.4% to 99.5%). On a 48-month synthetic series with known trend and seasonality, the out-of-sample fill rate goes from 97.5% to 99.6% (normal) and from 96.6% to 97.6% (bootstrap), with 52% and 14% more average stock.
- Compatibility: without `--trend-seasonal` the candidates, picks and Markdown output are those of 0.2.0.

## [0.2.0] - 2026-10-14

### Added

- Bootstrap safety stock (`--safety-stock bootstrap`, `--bootstrap-samples`, `--seed`; `bootstrap_safety_stock` in the API): the service-level quantile of protection-interval demand resampled from each SKU's own history, with lead times drawn from the observed ones, instead of the normal formula. Seeded per SKU, so reports are reproducible. On the synthetic example the lumpy SKU-012 goes from 72.5% to 100% replayed fill rate and total average stock falls from 1,257.5 to 1,065.4 units (in-sample; see ADR 0004).
- `safety_stock_method` in the JSON policy of each SKU and `safety_stock_method`, `bootstrap_samples` and `seed` in the JSON settings.
- Out-of-sample replay (`--test-periods N`; `Config.test_periods`, `out_of_sample_replay`, `train_history`, `OutOfSampleReport` in the API): each SKU is fitted on all but the last N periods (ABC, pattern, forecast pick, sigma, lead times observed in training, bootstrap draws) and the normal and bootstrap policies are both replayed, scoring the training periods (in-sample) and the last N (out-of-sample) separately, in a new report section and an `out_of_sample` JSON key. On the synthetic example with 12 test periods, the fill rate falls from 98.8% to 94.4% (normal) and from 99.9% to 94.6% (bootstrap), so the bootstrap's in-sample lead almost disappears out of sample, while it still holds about 20% less stock (ADR 0005).
- `simulate(..., warmup=k)` replays the first k periods without scoring them; `SkuHistory.lead_time_periods` dates each observed lead time by its row. `test_periods` in the JSON settings.

### Changed

- Development: Ruff 0.17.0 (Dependabot PR #2, hashed lock regenerated).

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

[Unreleased]: https://github.com/rodrix91/inventory-policy-lab/compare/v0.4.0...HEAD
[0.4.0]: https://github.com/rodrix91/inventory-policy-lab/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/rodrix91/inventory-policy-lab/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/rodrix91/inventory-policy-lab/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/rodrix91/inventory-policy-lab/releases/tag/v0.1.0
