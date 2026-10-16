# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [Semantic Versioning](https://semver.org/) (pre-1.0: minor versions may change behavior).

## [Unreleased]

### Added

- Fill-rate floor for the cost search, opt-in with `--optimize-fill-floor F` (`Config.optimize_fill_floor`, `0 < F <= 1`, needs `--optimize-cost`): only pairs whose expected fill rate on the training demand paths is at least `F` can be picked (refinement included), and a SKU where no pair meets it keeps the heuristic pair. Markdown adds the floor and an expected-fill column; JSON adds `optimize_fill_floor`, `optimized.fill_floor`, `summary.fell_back` and per SKU `expected_fill_rate`, `heuristic_expected_fill_rate`, `feasible`, `fell_back`. API: `expected_outcomes`, `search_levels(..., fill_floor=)`, new `CostSearch` fields. Without it the reports are byte for byte those of 0.9.0 (122 outputs compared) (ADR 0016).
- Result (100 paths, README rates): the floor hardly binds, since the training paths already expect 95% to 100% fill; at 0.99 the out-of-sample fill rate of the optimised policy moves from 88.4% to 90.0% (48-month (s, Q)) and from 90.6% to 91.4% (24-month (s, Q)) at a higher test cost on the 24-month example (20,985 against 18,016), and (R, s, S) does not improve.

## [0.9.0] - 2026-10-16

### Added

- Cost rates per SKU for the out-of-sample replay (ADR 0014). `--holding-cost-rate RATE` (`Config.holding_cost_rate`) prices holding as a yearly fraction of each SKU's `unit_cost`, so a unit held one period costs `RATE x unit_cost / --periods-per-year` (needs a `unit_cost` column; excludes `--holding-cost`; separate from the EOQ `--holding-rate`). `--cost-columns` (`Config.cost_columns`) reads optional `order_cost` and `stockout_cost` columns, the most recent non-empty value per SKU, which replace `--order-cost` / `--stockout-cost` for that SKU. Markdown adds each SKU's rates to the cost section; JSON adds the settings, `holding_rate_of_unit_cost` / `cost_columns` to `out_of_sample.costs.rates` and `rates` to each SKU. API: `Config.sku_cost_rates`, `Config.per_sku_costs`, `OutOfSampleReport.sku_rates`, `OutOfSampleReport.rates_of`, `SkuHistory.order_cost` / `stockout_cost`, `DemandData.has_order_cost` / `has_stockout_cost`, `read_demand(..., cost_columns=True)`, `parse_rows(..., cost_columns=True)`. Without the new options the Markdown and JSON reports are byte for byte those of 0.8.0 (104 outputs compared).
- Result on the 24-month example (`--test-periods 12 --trend-seasonal --dynamic-levels --bootstrap-source residuals --rolling-origin`, 50 per order, 10 per unit short): with holding at 25% a year of unit cost instead of 1 per unit and month, holding falls by about three quarters and (R, s, S) with a monthly review becomes the cheapest policy in all four columns (6,941 normal fixed, 5,903 residual bootstrap rolling); README "Holding priced per SKU".
- Cost-optimised levels, opt-in with `--optimize-cost` (`Config.optimize_cost`; needs cost rates, `--test-periods` and `--policy sQ` or `RsS`) and `--optimize-samples N` (default 100, at least 10): for each SKU the safety stock and the order quantity (so `s` and `S = s + Q`) are searched on a bounded grid (heuristic, -1 to 3 sigma, minus 10% to 100% of the forecast over `L + R`; quantity heuristic or 0.5 to 12 periods of mean training demand; then quarter-sigma refinement) for the lowest expected cost of the test window, estimated on demand paths built from training only (training forecast plus resampled one-step training errors) and replayed from the state the normal policy reaches at the end of training. The pick is then replayed on the real test (fixed origin). Markdown: "Cost-optimised levels" section; JSON: settings and `out_of_sample.optimized`; API: `OptimizedReplay`, `SkuOutOfSample.optimized`, `OutOfSampleReport.optimized_cost`, `optimized_sku_cost`, `optimized_totals`, module `inventory_policy_lab.optimize`. Test demand never reaches the search (tested). Without the option the reports are byte for byte those of 0.8.0 (ADR 0015).
- Result (`--test-periods 12 --trend-seasonal`, 50 / 1 / 10, fixed origin, README "Levels optimised for cost"): the search cuts the expected cost on training paths by 33% to 41% but beats both heuristics out of sample only for (s, Q) on the 24-month example (18,016 against 21,371 normal and 19,212 bootstrap); it is worse on 48-month (s, Q) and 24-month (R, s, S), with fill rates of 86% to 95%. (R, S) R = 1 at service level 0.98 is the cheapest on the 48-month series (4,474, 98.5% fill rate). Search time about 0.5 s per SKU at 100 paths.

## [0.8.0] - 2026-10-15

### Added

- Cost of the out-of-sample replay, opt-in with `--order-cost`, `--holding-cost` and `--stockout-cost` (`Config.order_cost`, `holding_cost`, `stockout_cost`; need `--test-periods`): every replay of the test periods (normal and bootstrap, fixed and rolling origin) is priced at C per order placed, C per unit on hand at the end of a period, and C per unit of demand not served from stock in its period (backordered); a rate left out counts as 0. The Markdown report adds a "Cost of the test periods" section with totals per method and origin (orders, unit-periods held, units short, ordering, holding, stockout, total) and the same per SKU; JSON adds the rates to the settings and `out_of_sample.costs`. The rates do not change the policy (the EOQ inputs stay separate). Without them the Markdown and JSON reports are byte for byte those of 0.7.0 (ADR 0012).
- API: `CostRates`, `CostBreakdown`, `replay_cost`, `total_cost`, `Config.cost_rates`, `OutOfSampleReport.costs`, `OutOfSampleReport.cost`, `OutOfSampleReport.sku_cost`.
- Periodic-review (R, s, S) policy, opt-in with `--policy RsS` (`Config.policy = "RsS"`, a whole `--review-period` of at least 1): every R periods the position is reviewed and, only when it is at or below `s = D x (L + R) + SS` (the same level and safety stock as the other policies), an order brings it up to `S = s + Q`. Works with static and dynamic levels, normal and bootstrap safety stock (demand or residuals), the fixed and rolling origins and `--refit-every` (refits decide `s` and `Q`). Markdown: `Reorder level (s)`, `Order qty (Q = S - s)`, `Review (R)`; JSON: `kind: "RsS"`, `reorder_point`, `order_quantity`, `order_up_to`. API: `simulate_rss`; `replay_policy` and `build_policy` accept the kind. Reports of (s, Q) and (R, S) are unchanged (ADR 0013).
- Results with the example rates 50 per order, 1 per unit-month held and 10 per unit short (out of sample, `--trend-seasonal --dynamic-levels --bootstrap-source residuals --rolling-origin`, README "Policies compared by cost"): on the 48-month series (R, S) with a monthly review is cheapest in every column (3,066 normal fixed, 2,482 residual bootstrap rolling) and (R, s, S) R = 1 costs 5,801 and 4,404, because ordering up to `s + Q` holds about one lot more; on the 24-month example, where the frozen forecasts leave (R, S) at 90.9% fill rate, (R, s, S) R = 1 reaches 99.3% and is cheapest with a fixed origin (15,576 against 17,313), while with a rolling origin (R, S) wins at 10 per unit short (13,405 against 15,818) and (R, s, S) above about 24. A three-month review is never cheapest at these rates.

## [0.7.0] - 2026-10-15

### Changed

- Faster damped Holt and Holt-Winters fits, with identical results: `fit_holt_damped` and `fit_holt_winters` keep recent fits in a bounded cache keyed on the exact history, and on a miss score each parameter set once over the whole history, which gives the best fit of every prefix at the cost of one grid search (the backtest, the residual errors and the rolling origins fit those prefixes again and again). On the 48-month series, `--test-periods 12 --trend-seasonal --bootstrap-source residuals --rolling-origin` goes from 10.1 s to 0.22 s, and the fixed origin from 1.0 s to 0.15 s. Markdown and JSON reports are byte for byte those of 0.6.0, checked against the plain grid search kept in the tests (ADR 0010).

### Added

- `--refit-every K` (`Config.refit_every`, default 1; needs `--rolling-origin`): the rolling origin refits only at the start of every K-th test period, and each refit decides its own period and the next K - 1 (same safety stock and order quantity; with dynamic levels, its forecasts 1 to K steps ahead). K = 1 gives the 0.6.0 reports byte for byte; K at least the test window reproduces the fixed origin; no refit sees a period it decides (tested). JSON: `refit_every` in the settings when it is not 1; API: `OutOfSampleReport.refit_every` (ADR 0011).
- Results with `--test-periods 12 --trend-seasonal --bootstrap-source residuals`, K = 1, 3, 6, 12: the fill rate never rises with K. On the 48-month series, (R, S) R = 1 with the normal formula serves 100% at every K with stock from 149.3 (monthly) to 105.5 (yearly); with the residual bootstrap it goes from 99.4% to 95.4%. On the 24-month example, (s, Q) normal with a quarterly refit (K = 3) keeps 97.7% of fill rate against 99.8% monthly and 94.4% fixed, with the same stock as monthly. Each run takes 0.13 to 0.33 s.
- API: `fit_cache_info()`, `clear_fit_cache()`, `FitCacheInfo`.

## [0.6.0] - 2026-10-15

### Added

- Rolling-origin out-of-sample replay, opt-in with `--rolling-origin` (`Config.rolling_origin`, needs `--test-periods`): at the start of every test period each SKU is refitted, with the same steps as on train, on the periods before it only (training plus the test periods already observed), and its safety stock, level and order quantity decide the end of that period. It is reported next to the fixed-origin replay of ADR 0005, which is unchanged; both enter the test from the same stock and share the first decision. No leak, tested two ways: no out-of-sample fit ever receives the period it decides, and zeroing later test periods leaves the earlier decisions unchanged (ADR 0009).
- `simulate` accepts one order quantity per period. API: `RollingReplay`, `SkuOutOfSample.rolling`, `SkuOutOfSample.rolling_replay`, `OutOfSampleReport.rolling_origin`, `OutOfSampleReport.rolling_totals`.
- Markdown: a "Rolling origin" table (fixed / rolling) and the forecasts picked at the origins per SKU. JSON, only with the option: `rolling_origin` in the settings and in `out_of_sample` (summary and, per SKU and method, `forecast_methods`, `safety_stocks`, `reorder_points` or `order_up_to_levels`, `order_quantities`, `out_of_sample`). Without it the Markdown and JSON reports are unchanged, byte for byte.
- Results (out of sample, `--trend-seasonal --bootstrap-source residuals`): on the 24-month example the rolling origin raises the fill rate of (s, Q) from 94.4% to 99.8% (normal, 5% more stock) and from 92.2% to 98.5% (residual bootstrap, 6% less stock), and of (R, S) dynamic R = 1 from 90.9% to 97.3% and from 88.5% to 96.0%. On the 48-month series it mostly buys stock: the normal (R, S) stays at 100% with 42% more stock, and the residual bootstrap under (R, S) goes from 95.4% to 99.4% with stock from 13.1 to 36.4 units.

## [0.5.0] - 2026-10-15

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

[Unreleased]: https://github.com/rodrix91/inventory-policy-lab/compare/v0.9.0...HEAD
[0.9.0]: https://github.com/rodrix91/inventory-policy-lab/compare/v0.8.0...v0.9.0
[0.8.0]: https://github.com/rodrix91/inventory-policy-lab/compare/v0.7.0...v0.8.0
[0.7.0]: https://github.com/rodrix91/inventory-policy-lab/compare/v0.6.0...v0.7.0
[0.6.0]: https://github.com/rodrix91/inventory-policy-lab/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/rodrix91/inventory-policy-lab/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/rodrix91/inventory-policy-lab/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/rodrix91/inventory-policy-lab/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/rodrix91/inventory-policy-lab/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/rodrix91/inventory-policy-lab/releases/tag/v0.1.0
