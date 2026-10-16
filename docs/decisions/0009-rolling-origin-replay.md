# 0009: Rolling-origin out-of-sample replay

- Status: accepted (alpha)
- Date: 2026-10-15
- Deciders: Rodrigo Pantoja Navajas

## Context

The out-of-sample replay of ADR 0005 fits every policy once, at the end of the training window, and keeps it for the whole test window. ADR 0005 listed this as a limitation ("the out-of-sample result is pessimistic for an operation that recomputes its policy every period") and named the rolling origin as the candidate for later. ADRs 0006 to 0008 made the frozen policy weigh more: a trending item gets a forecast that is a year old by the end of the test, and the residual bootstrap of ADR 0008 gets no new errors from the test periods it has already seen.

Evaluating a forecast from a rolling origin, refitting at each origin on the data available then, is the standard out-of-sample design for time series (Tashman, 2000; Hyndman & Athanasopoulos, 2021, section 5.10). Here the same idea is applied to the whole policy, not only to the forecast.

## Decision

- **`--rolling-origin`** (`Config.rolling_origin`, off by default) adds a second replay of the test window; it needs `--test-periods` (a usage error otherwise). The fixed-origin replay of ADR 0005 is still computed and reported, so the two are compared side by side in one run.
- **What is refitted.** At the start of every test period `t` (calendar index), every SKU is refitted exactly as on train, by the same `_analyze_sku` call, on periods `0 .. t - 1` only: the training periods plus the test periods already observed. That covers the ABC class (from the demand of all SKUs with history before `t`), the demand pattern, the forecast backtest and pick, the sigma, the lead times whose row is dated before `t`, the bootstrap draws (demand or residuals), the safety stock (per period with `--period-safety-stock`), the level and the order quantity. The level and quantity of that refit are the ones used at the end of period `t`; with dynamic levels it is the refit's level for period `t` (the mean forecast of `t + 1 .. t + P`).
- **Timing and state.** The training periods are replayed with the fixed policy, so both replays enter the test with the same stock, backorders and open orders, and the first test period has the same decision in both (tested). `simulate` accepts one order quantity per period for this; with one quantity it is unchanged.
- **No leak.** Each refit sees a history cut to the periods before its origin. Two tests check it: one replaces a test period with a sentinel and asserts that no out-of-sample fit ever receives it, and the origins see 4, 5 and 6 periods in turn; the other sets periods 40 to 47 of the 48-month series to zero and asserts that the forecast picks, levels, safety stocks and quantities of origins 36 to 40 do not change, while later origins do.
- **Reporting.** The Markdown out-of-sample section gains a "Rolling origin" table (fill rate, stockout periods and average stock, fixed / rolling, per safety-stock method) and a per-SKU table with the forecasts picked at the origins. The JSON settings gain `rolling_origin: true` and `out_of_sample` gains `rolling_origin` with a summary and, per SKU and method, `forecast_methods`, `safety_stocks`, `reorder_points` or `order_up_to_levels`, `order_quantities` (for (s, Q)) and `out_of_sample`. The refits' notes are not repeated per origin.
- **Unchanged by default.** Without the option the Markdown and JSON reports are byte for byte those of 0.5.0 (checked on ten option sets).

## Results

Out of sample, the 12 test periods only, from real runs pinned in `tests/test_rolling.py`. Cells are fill rate / stockout periods / average stock on hand summed over the SKUs, fixed origin then rolling origin. All runs use `--trend-seasonal --bootstrap-source residuals`; the normal column does not depend on the bootstrap source.

### 48-month synthetic series (36 train, 12 test)

| Policy | Normal, fixed | Normal, rolling | Bootstrap residuals, fixed | Bootstrap residuals, rolling |
|---|---|---|---|---|
| (s, Q) static | 99.6% / 1 / 289.0 | 100.0% / 0 / 321.6 | 98.4% / 3 / 185.5 | 99.6% / 1 / 220.9 |
| (R, S) dynamic, R = 1 | 100.0% / 0 / 105.5 | 100.0% / 0 / 149.3 | 95.4% / 18 / 13.1 | 99.4% / 4 / 36.4 |

### Synthetic example (24 months, `--test-periods 12`)

| Policy | Normal, fixed | Normal, rolling | Bootstrap residuals, fixed | Bootstrap residuals, rolling |
|---|---|---|---|---|
| (s, Q) static | 94.4% / 11 / 885.2 | 99.8% / 4 / 932.4 | 92.2% / 15 / 975.8 | 98.5% / 9 / 913.7 |
| (R, S) dynamic, R = 1 | 90.9% / 20 / 598.6 | 97.3% / 10 / 627.5 | 88.5% / 23 / 690.9 | 96.0% / 14 / 678.2 |

The rolling origin raises the out-of-sample fill rate and cuts stockout periods in every cell. The price differs:

- **On the 24-month example it is close to a free gain.** The normal formula gains 5.4 and 6.4 points of fill rate with about 5% more stock; the residual bootstrap gains 6.3 and 7.5 points with 6% and 2% less stock, because each refit adds errors to the 6 to 9 it had at the end of training. The gain comes from the trending SKU-004 (normal (s, Q): 79.7% to 99.4%) and the seasonal SKU-003 (82.9% to 99.8%), whose forecasts the fixed policy froze for a year. The lumpy SKU-007 (50.4% with the residual bootstrap) and the intermittent SKU-006 (82.9%) do not improve: refitting does not fix a quantile taken from a handful of errors.
- **On the 48-month series it mostly buys stock.** Where the fixed origin already reached 100% (normal, (R, S) R = 1), the rolling origin keeps 100% with 42% more average stock (105.5 to 149.3): the demand sigma is recomputed on a longer trending history and grows (the trending item T's safety stock goes from 50.8 to 63.1 units over the test year). Under (s, Q) the normal formula gains 0.4 points for 11% more stock. The residual bootstrap gains most under (R, S) R = 1 (95.4% with 18 stockout periods to 99.4% with 4, T from 93.3% to 100%), but its stock almost triples from a very low base (13.1 to 36.4 units).

So the rolling origin is a fairer estimate of a policy that is recomputed every period, not a better policy: what it reports is closer to what an operation that refits monthly would see, and on this data that is better service, sometimes for more stock.

## Alternatives considered

| Alternative | Benefit | Cost / why not now |
|---|---|---|
| Replace the fixed origin when the option is on | One replay, shorter report | Loses the comparison, which is the point of the option |
| Refit at the end of period `t` (seeing period `t`) | Uses one more period per decision | The decision at the end of `t` is then made with `t`'s demand, which is realistic, but the first test decision would differ from the fixed policy and the two replays would not share a starting point; the start-of-period refit is the stricter, simpler rule |
| Refit every `k` periods | `k` times faster | One more option; a monthly refit is what the example data implies |
| Keep the ABC class of the training window | Fewer moving parts | The class sets the service level with `--class-service-levels`; a class frozen at the end of training is part of what the option is meant to unfreeze |
| Group residual errors by seasonal position, or start Holt-Winters origins earlier, to get more errors | More errors for the seasonal items | Not clean yet: with Holt-Winters refitted from month 24, 36 training months leave about one error per seasonal position, and earlier origins need a Holt-Winters fit on less than two seasons. Left for a later ADR |

## Consequences

- One full refit per test period and SKU: with `--trend-seasonal` and the residual bootstrap, the 48-month series takes about 10 seconds against about 1 for the fixed origin. The test suite grows accordingly.
- The training replay and the fixed-origin results are untouched, so every table of ADRs 0005 to 0008 still holds.
- Still one test window and synthetic data: the results show the mechanism, not evidence about real data.

## References

- Tashman, L. J. (2000). Out-of-sample tests of forecasting accuracy: an analysis and review. *International Journal of Forecasting*, 16(4), 437-450.
- Hyndman, R. J., & Athanasopoulos, G. (2021). *Forecasting: Principles and Practice* (3rd ed.), section 5.10, time series cross-validation. OTexts.
