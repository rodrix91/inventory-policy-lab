# 0008: Bootstrap of forecast residuals and a safety stock per period

- Status: accepted (alpha)
- Date: 2026-10-15
- Deciders: Rodrigo Pantoja Navajas

## Context

ADR 0007 left two documented weaknesses:

1. **The bootstrap resamples demand, not forecast error.** ADR 0004 draws periods of demand with replacement and subtracts the forecast over the interval. That ignores the order of the periods, so a trend or a season reads as noise. On the 48-month synthetic series (36 training, 12 test months), the trending item T has a naive forecast at the end of training that is above most of its rising history; the bootstrap quantile falls below the forecast over the interval and the safety stock is floored at zero. Under (R, S) with dynamic levels and R = 1, T reaches 78.4% fill rate out of sample with 12 stockout periods, and the three items together 89.3%, against 100% for the normal formula.
2. **The safety stock is static while the levels move.** With dynamic levels the forecast already follows the season, but the normal safety stock still uses the standard deviation of demand, which contains that seasonal swing, so it counts it twice. ADR 0007 rejected a sigma per season (too few errors per season in 36 months) and `--sigma rmse` (6 holdout errors are too few for a 95% quantile).

What should be protected is the error of the forecast over the protection interval, not the variability of demand around its mean (Silver, Pyke & Thomas, 2017). Computing the safety stock from the measured lead-time forecast errors, without assuming a distribution, is studied by Trapero, Cardós & Kourentzes (2019), who also note that overlapping lead-time errors are autocorrelated even when demand is not.

## Decision

- **`--bootstrap-source residuals`** (`Config.bootstrap_source = "residuals"`; the default stays `"demand"`). For each SKU, with `P = L + R` rounded half up:
  - At every origin `t` from 2 to `n - P` of the history the SKU is fitted on, the picked method is refitted on periods `0 .. t - 1` only and forecasts the total demand of periods `t .. t + P - 1` (a level method: `P` times its one-step forecast; damped Holt or Holt-Winters: the sum of its forecasts 1 to `P` steps ahead, with parameters re-picked by the same grid search). The error is the actual total minus that forecast. Origins where a model cannot be fitted yet (Holt-Winters before two full seasons) are skipped.
  - Each of N draws (default 2000, seeded per SKU as in ADR 0004) takes a lead time from the observed ones (or the default), turns `L + R` into whole periods and draws one error of that length. The safety stock is the service-level quantile (nearest rank) of the draws, floored at zero; the level keeps its form `D x (L + R) + SS`.
  - The origins start at 2, the minimum the backtest needs, rather than at the holdout: every usable origin adds an error, which is the whole point after ADR 0007 showed that 6 holdout errors are too few.
  - With too little history for any error of a length that can be drawn, the SKU falls back to the demand bootstrap, with a note; the result is then exactly the demand bootstrap's.
- **`--period-safety-stock`** (`Config.period_safety_stock`), only with `--dynamic-levels` and the residual bootstrap. The errors are taken relative to their forecast (error / forecast, origins with a forecast of zero skipped), and each period gets `SS(t) = max(q, 0) x D(t) x (L + R)`, where `q` is the bootstrap quantile of the relative errors and `D(t)` the mean forecast of the periods the level protects (ADR 0007). The level is `S(t) = D(t) x (L + R) + SS(t)`: a peak month gets more safety stock than a trough, and the seasonal swing is neither ignored nor counted twice. It applies only when a damped Holt or Holt-Winters model is picked; with a level forecast every `D(t)` is the same, so the SKU keeps one absolute safety stock and the report notes it.
- **Where it applies.** The residual source changes the bootstrap only: the main policy with `--safety-stock bootstrap`, and the bootstrap replay of `--test-periods`. The normal formula is unchanged, so the normal column of every earlier table stays the same. Asking for residuals when no bootstrap is computed, or for a safety stock per period without dynamic levels and residuals, is a usage error, not an option silently ignored.
- **No leak.** In the out-of-sample replay `_analyze_sku` receives the training periods only, so every error is computed from training data. `tests/test_residuals.py` replaces the 12 test months with zeros and asserts that safety stocks, levels, per-period safety stocks and training replays do not change, and a unit test asserts that no forecaster ever sees the periods it is scored on.
- **Unchanged by default.** Without the new options the Markdown and JSON reports are byte for byte those of 0.4.0 (checked on seven option sets). With them, the JSON settings gain `bootstrap_source` and `period_safety_stock`; with a safety stock per period the JSON policy gains `safety_stocks` and `next_safety_stocks` and the out-of-sample replay `test_safety_stocks`; the Markdown safety-stock column shows the range of the next season; and the out-of-sample table names the method `bootstrap (forecast residuals)`.

## Results

All numbers are out of sample (the 12 test periods only), from real runs, and pinned in `tests/test_residuals.py`. Cells are fill rate / stockout periods / average stock on hand summed over the SKUs. "Normal" and "bootstrap demand" are the 0.4.0 methods.

### 48-month synthetic series (36 train, 12 test)

| Policy | Normal | Bootstrap demand (0.4.0) | Bootstrap residuals | Residuals, SS per period |
|---|---|---|---|---|
| (s, Q) static, `--trend-seasonal` | 99.6% / 1 / 289.0 | 97.6% / 4 / 196.4 | 98.4% / 3 / 185.5 | n/a (static) |
| (s, Q) dynamic | 100.0% / 0 / 269.9 | 98.8% / 2 / 174.8 | 99.8% / 1 / 163.4 | 99.8% / 1 / 159.0 |
| (R, S) dynamic, R = 1 | 100.0% / 0 / 105.5 | 89.3% / 22 / 41.0 | 95.4% / 18 / 13.1 | 96.3% / 16 / 14.6 |
| (R, S) dynamic, R = 3 | 99.9% / 1 / 439.3 | 90.4% / 10 / 247.0 | 97.2% / 7 / 316.9 | 97.3% / 6 / 315.9 |

Per item under (R, S) dynamic, R = 1 (safety stock; fill rate; stockout periods):

| Item (training pick) | Bootstrap demand | Bootstrap residuals | Residuals, SS per period |
|---|---|---|---|
| T, trend (naive) | 0.0; 78.4%; 12 | 22.0; 93.3%; 6 | 22.0; 93.3%; 6 (level forecast: one SS) |
| TS, trend x season (Holt-Winters multiplicative) | 17.1; 91.7%; 10 | 24.2; 96.3%; 6 | 28.2, from 19.4 to 35.5 over the test year; 98.8%; 4 |
| S, season (Holt-Winters additive) | 44.0; 100.0%; 0 | 6.6; 97.0%; 6 | 8.6, from 4.7 to 10.4; 97.2%; 6 |

On this series the residual bootstrap does what it was meant to do: the trending item now gets a safety stock (22 units, from 33 errors), and the bootstrap's out-of-sample fill rate rises in every policy, by 6.1 points for (R, S) R = 1 and 6.8 points for R = 3, and with less stock in every policy except (R, S) R = 3 (247.0 to 316.9). The safety stock per period adds a little more (96.3% with 16 stockout periods for (R, S) R = 1), almost all of it on TS, whose error grows with its level. It does not close the gap with the normal formula, which reaches 100% under (R, S) R = 1 with 105.5 units: the seasonal items have only 11 errors each (Holt-Winters can be refitted only from month 24), so their 95% quantile is the largest of 11 errors, and S, which the demand bootstrap over-protected at 100%, drops to 97.0%.

### Synthetic example (24 months, `--test-periods 12`)

| Policy | Normal | Bootstrap demand (0.4.0) | Bootstrap residuals | Residuals, SS per period |
|---|---|---|---|---|
| (s, Q) static | 94.4% / 11 / 885.2 | 94.6% / 12 / 712.4 | 92.2% / 15 / 975.8 | n/a (static) |
| (s, Q) dynamic | 94.4% / 11 / 885.2 | 94.6% / 12 / 712.4 | 92.2% / 15 / 975.8 | 92.2% / 15 / 975.8 |
| (R, S) dynamic, R = 1 | 90.9% / 20 / 598.6 | 90.7% / 17 / 427.9 | 88.5% / 23 / 690.9 | 88.5% / 23 / 690.9 |
| (R, S) dynamic, R = 3 | 93.4% / 11 / 1,306.6 | 94.2% / 11 / 1,032.1 | 92.9% / 15 / 1,612.7 | 92.9% / 15 / 1,612.7 |

**Here the residual bootstrap is worse**: lower fill rate, more stockout periods and more stock in every policy. With 12 training months each SKU has only 6 to 9 errors, from forecasts fitted on as few as 2 periods; the erratic SKU-005 gets a much larger safety stock (378 against 68.5 units), the lumpy SKU-007 a quantile below zero (safety stock 0, 50.4% fill rate), and the seasonal SKU-003 falls from 94.4% to 69.8%. The trending SKU-004 is the one that improves (67.7% to 82.0%), as on the 48-month series. With no seasonal model in 12 months, the safety stock per period never applies and changes nothing.

## Alternatives considered

| Alternative | Benefit | Cost / why not now |
|---|---|---|
| Sum of `P` resampled one-step residuals | Many more errors (every one-step error) | Ignores that errors of a forecast held for `P` periods are correlated; for a naive forecast of a trend the `P`-step error grows faster than `P` one-step errors |
| Origins only in the holdout | Same errors as the forecast pick | 6 holdout errors are too few for a 95% quantile (ADR 0007, `--sigma rmse`) |
| Normal formula with the RMSE of the `P`-step errors | No random numbers | Brings back the normal assumption that ADR 0004 dropped |
| Safety stock per period also for level forecasts | Works for every SKU | Relative errors of forecasts fitted on 2 to 12 periods are unstable; on the 24-month example they multiplied the bootstrap's average stock by about 2.7 to 3.4 (measured while designing, not adopted) |
| Kernel or GARCH quantiles of the errors (Trapero et al., 2019) | Smoother quantiles, volatility that changes over time | More parameters than 11 to 33 errors can support |
| Residual bootstrap by default | One option less | Worse on the 24-month example; it needs history to pay off |

## Consequences

- The residual bootstrap needs history: it pays off when the method can be refitted at many origins, and does worse than the demand bootstrap with about a year of data. The report lists how many errors each SKU used.
- Damped Holt and Holt-Winters are refitted at every origin (the grid search each time), so a residual run with `--trend-seasonal` is slower than a demand bootstrap.
- The normal formula still uses the demand sigma, so with dynamic levels it still counts the season twice; it remains the best performer on the 48-month series and is left as it is.
- One split in time and synthetic data: the results show the mechanism, not evidence about real data.
