# 0011: Rolling origin refitted every K test periods

- Status: accepted (alpha)
- Date: 2026-10-15
- Deciders: Rodrigo Pantoja Navajas

## Context

ADR 0009 refits every SKU at every test period and listed "refit every `k` periods" as an alternative for speed. ADR 0010 removed the speed argument (0.22 s instead of 10.1 s for the slowest run), but a second one remains: few operations recompute their inventory parameters every month. A quarterly or half-yearly review is common, and a replay that refits monthly overstates what such an operation would see. The two ends were already there (the fixed origin, refitted never, and the monthly rolling origin); the cadences in between were not.

## Decision

- **`--refit-every K`** (`Config.refit_every`, default 1, at least 1) applies to the rolling-origin replay only: `K` other than 1 without `--rolling-origin` is a usage error.
- **What a refit decides.** Refits run at the start of test periods `0, K, 2K, ...` (offsets inside the test window), each on the periods before it only, by the same `_analyze_sku` call as in ADR 0009, now asked for `K` periods ahead (fewer for the last block). That refit decides its own period and the next `K - 1`: the same safety stock, order quantity, class and forecast pick; with dynamic levels, the level of each period is the refit's mean forecast of the protection interval from that period, that is its forecasts 1 to `K` steps ahead, and with `--period-safety-stock` its safety stock per period likewise. This is how the fixed origin already uses the training fit over the whole test window, so the two ends match exactly: `K = 1` is the monthly rolling origin of 0.6.0 and `K` of at least the test window is the fixed origin (both tested, the second with four option sets and K = 12 and 20).
- **No leak.** A decision is never taken by a refit that saw its period: tested by hand (a sentinel in the second period of a two-period block is never seen by the refit that decides it) and by zeroing periods 40 to 47 of the 48-month series with `K = 3`, which leaves the decisions of the origins at 36 and 39 (test periods 0 to 5) unchanged while the origin at 42 moves.
- **Reporting.** With `K = 1` the Markdown and JSON reports are byte for byte those of 0.6.0 (tested through the command line). Otherwise the JSON settings gain `refit_every`, `OutOfSampleReport.refit_every` carries it, and the Markdown "Rolling origin" paragraph says how often the refit runs and that each refit decides `K` periods. The per-period lists (`forecast_methods`, `safety_stocks`, levels, `order_quantities`) keep one entry per test period, so a held decision appears `K` times.

## Results

Out of sample, `--test-periods 12 --trend-seasonal --bootstrap-source residuals --rolling-origin`, pinned in `tests/test_refit_every.py`. Cells: fill rate / stockout periods / average stock on hand summed over the SKUs, normal then residual bootstrap. Time: wall time of one command (best of 3, Python 3.12, with ADR 0010's cache).

| Data | Policy | K = 1 | K = 3 | K = 6 | K = 12 (= fixed) |
|---|---|---|---|---|---|
| 48 months | (s, Q) normal | 100.0% / 0 / 321.6 | 99.6% / 1 / 306.1 | 99.6% / 1 / 302.3 | 99.6% / 1 / 289.0 |
| 48 months | (s, Q) bootstrap residuals | 99.6% / 1 / 220.9 | 98.7% / 2 / 195.4 | 98.7% / 2 / 188.3 | 98.4% / 3 / 185.5 |
| 48 months | (s, Q) time | 0.23 s | 0.17 s | 0.16 s | 0.15 s |
| 48 months | (R, S) R = 1 normal | 100.0% / 0 / 149.3 | 100.0% / 0 / 139.9 | 100.0% / 0 / 126.5 | 100.0% / 0 / 105.5 |
| 48 months | (R, S) R = 1 bootstrap residuals | 99.4% / 4 / 36.4 | 98.8% / 7 / 29.2 | 97.8% / 13 / 22.5 | 95.4% / 18 / 13.1 |
| 48 months | (R, S) time | 0.22 s | 0.18 s | 0.16 s | 0.16 s |
| 24 months | (s, Q) normal | 99.8% / 4 / 932.4 | 97.7% / 6 / 930.7 | 97.0% / 8 / 941.6 | 94.4% / 11 / 885.2 |
| 24 months | (s, Q) bootstrap residuals | 98.5% / 9 / 913.7 | 95.7% / 10 / 1,026.2 | 94.6% / 12 / 1,004.9 | 92.2% / 15 / 975.8 |
| 24 months | (s, Q) time | 0.32 s | 0.18 s | 0.15 s | 0.13 s |
| 24 months | (R, S) R = 1 normal | 97.3% / 10 / 627.5 | 95.6% / 12 / 626.1 | 93.9% / 18 / 617.8 | 90.9% / 20 / 598.6 |
| 24 months | (R, S) R = 1 bootstrap residuals | 96.0% / 14 / 678.2 | 93.7% / 16 / 708.1 | 91.3% / 22 / 702.1 | 88.5% / 23 / 690.9 |
| 24 months | (R, S) time | 0.33 s | 0.18 s | 0.15 s | 0.13 s |

- The fill rate never rises with K and the stockout periods never fall, in any row.
- On the 48-month series, under (R, S) with the normal formula, every K serves 100% and stock falls by 29% from monthly to yearly: the monthly refit buys nothing measurable there. With the residual bootstrap a slower refit trades service for stock.
- On the 24-month example, (s, Q) normal with K = 3 keeps 3.3 of the 5.4 points of fill rate the monthly refit gains over the fixed origin, with the same stock. The residual bootstrap is not monotone in stock: K = 3 and 6 hold more stock than K = 1 and than the fixed origin, because a quantile refitted from a handful of errors is then kept for K periods.
- Run time differs by at most 0.2 s, so the choice of K is about the planning cadence being modelled, not speed. Three and seven SKUs over one test year are small samples.

## Alternatives considered

| Alternative | Benefit | Cost / why not |
|---|---|---|
| Hold the refit's period-0 level for the whole block, also with dynamic levels | Simpler | A dynamic policy would then stop following its own forecast between refits, and `K` = test window would not reproduce the fixed origin, which follows the training forecasts |
| Refit on a calendar (every quarter starting in January) instead of every K test periods | Matches a calendar review | Needs the calendar's frequency; offsets inside the test window are exact for any period type and give the fixed origin as the limit |
| Recompute the safety stock at every period and refit the forecast every K | Closer to some planning systems | Two cadences and a split of `_analyze_sku`; not asked for, and the safety stock and the forecast come from the same backtest here |

## Consequences

- One more option, which only changes reports when it is set to something other than 1.
- The fixed and the monthly rolling origin are now the two ends of one parameter, tested as such.
