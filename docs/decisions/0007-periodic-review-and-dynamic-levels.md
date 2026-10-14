# 0007: Periodic review (R, S) and levels that follow the forecast

- Status: accepted (alpha)
- Date: 2026-10-14
- Deciders: Rodrigo Pantoja Navajas

## Context

Every policy so far is an (s, Q) policy with one reorder point for the whole history (ADR 0003). ADR 0006 added damped Holt and Holt-Winters, but a static policy can only use a seasonal forecast to move that one level. On the 48-month synthetic series of ADR 0006 (36 training and 12 test months), Holt-Winters raised the out-of-sample fill rate of the normal policy from 97.5% to 99.6%, but with 52% more average stock (189.8 to 289.0 units, summed over the three items): covering the peak months means carrying the peak level through the troughs. ADR 0006 listed "a reorder point per period" as the natural next step.

Many companies also do not watch stock continuously: they review it on a fixed calendar (every week, every month) and order enough to bring it back up to a target. That is the periodic-review, order-up-to (R, S) policy, and it is the policy into which a period-by-period level fits most naturally.

## Decision

- **(R, S) policy**, opt-in with `--policy RS` (`Config.policy = "RS"`; the default stays `"sQ"`). The inventory position is reviewed at the end of every `R`-th period (`--review-period R`, a whole number of at least 1 with this policy) and an order of `S - position` is placed when the position is below `S`. The order arrives at the start of period `t + L + 1`, as in the (s, Q) replay, so it covers the `L + R` periods until the order of the next review arrives.
- **S has the reorder-point formula**: `S = D x (L + R) + SS`, with the same safety stock (normal formula or bootstrap) over the same protection interval `L + R` (Silver, Pyke & Thomas, 2017). Nothing new is estimated; only the ordering rule changes. The order quantity (EOQ or cover) is not used by the (R, S) replay, and the JSON reports it as null.
- **Dynamic levels**, opt-in with `--dynamic-levels` (`Config.dynamic_levels`), for both policies. The level used at the end of period `t` is `D(t) x (L + R) + SS`, where `D(t)` is the mean forecast of periods `t + 1` to `t + P` and `P = L + R` rounded half up (at least 1). Using the mean times `L + R`, rather than a sum over whole periods, makes a constant forecast give exactly the static level. The safety stock stays the static one. The option needs `--trend-seasonal`: with only level forecasts it could not change anything, so it is a usage error rather than an option silently ignored. When a level method wins anyway the SKU gets a note and its levels equal the static level.
- **Where the per-period forecasts come from** (`SmoothingFit.calendar_forecasts`):
  - Periods after the fitted history get the real multi-step forecast of the fit: `h` steps ahead for the `h`-th period. In the out-of-sample replay the fit is the one on the training periods, so the test levels are the forecasts 1 to N steps after the end of training and the test demand cannot reach them. `tests/test_periodic.py` checks this by replacing the test periods with zeros and asserting that the levels, safety stocks and training replays stay the same.
  - Periods inside the fitted history (the in-sample replay) get the forecast of the next period in the same season position, 1 to `m` steps ahead: the seasonal profile at the final level and trend. This mirrors the static in-sample replay, which applies the level computed at the end of the history to all of it. For damped Holt (no season) every earlier period gets the one-step forecast.
- **Starting stock**: the (R, S) replay starts with the first level on hand and nothing on order; the (s, Q) replay starts with `s + Q` as before (with dynamic levels, the first `s`).
- **Unchanged by default**: without the new options the Markdown report is identical and the JSON only gains two settings keys, `policy` and `dynamic_levels`. With `--policy RS` the policy table shows `Order-up-to (S)` and `Review (R)` instead of `Reorder point (s)` and `Order qty (Q)`; with dynamic levels the level cell also shows the lowest and highest level of the next season, and the JSON lists every level (`levels`, `next_levels`, and `test_levels` in the out-of-sample replay).

## Results

All numbers are out of sample (test periods only), from real runs, and pinned in `tests/test_periodic.py`. Normal and bootstrap are the safety-stock methods; the sigma is the default (standard deviation of demand) unless stated. Average stock is summed over the SKUs.

### 48-month synthetic series with known trend and seasonality (36 train, 12 test)

| Policy | Fill rate, normal / bootstrap | Stockout periods, normal / bootstrap | Avg on hand, normal / bootstrap |
|---|---|---|---|
| (s, Q), level forecasts only (0.2.0) | 97.5% / 96.6% | 3 / 5 | 189.8 / 172.4 |
| (s, Q) static, `--trend-seasonal` (0.3.0) | 99.6% / 97.6% | 1 / 4 | 289.0 / 196.4 |
| (s, Q) dynamic | 100.0% / 98.8% | 0 / 2 | 269.9 / 174.8 |
| (R, S) static, R = 1 | 97.4% / 85.5% | 4 / 19 | 140.0 / 79.4 |
| (R, S) dynamic, R = 1 | 100.0% / 89.3% | 0 / 22 | 105.5 / 41.0 |
| (R, S) static, R = 3 | 99.6% / 92.4% | 2 / 7 | 589.1 / 389.3 |
| (R, S) dynamic, R = 3 | 99.9% / 90.4% | 1 / 10 | 439.3 / 247.0 |
| (R, S) dynamic, R = 1, `--sigma rmse` | 89.2% / 89.3% | 21 / 22 | 14.3 / 41.0 |

With the normal safety stock, (R, S) with dynamic levels reaches 100% fill rate with no stockout period and 105.5 units of average stock: 63% less than the static (s, Q) with Holt-Winters (289.0) and 44% less than the 0.2.0 policy (189.8). Two effects add up, and the table separates them:

- **Dynamic levels** cut stock and raise service for a given policy: (R, S) R = 1 goes from 97.4% to 100% with 25% less stock (140.0 to 105.5); R = 3 from 99.6% to 99.9% with 25% less (589.1 to 439.3); (s, Q) from 99.6% to 100% with 7% less (289.0 to 269.9). Per item, with (R, S) R = 1 and the normal method, the seasonal S holds 60.0 units at 100% and the trend-seasonal TS 20.6 units at 100%.
- **The policy type** changes the cycle stock. An (s, Q) policy holds on average about `Q / 2` above its reorder point; (R, S) with R = 1 orders back every period's demand and holds no such cycle stock. With R = 3, S covers `L + 3` periods, so stock is much higher.

**The bootstrap does not work well with (R, S) here.** On the trending item T the forecast is naive (damped Holt loses its training holdout, ADR 0006), the bootstrap quantile of a rising history falls below the naive forecast over the interval, and the safety stock is floored at zero: 78.4% fill rate with 12 stockout periods. The cycle stock of (s, Q) hid that shortfall; (R, S) exposes it. Likewise `--sigma rmse`, the consistent pairing in theory (the levels already carry the season, so only the forecast error should be protected), gives 89.2%: a 6-period holdout RMSE is too small a sample to set a 95% safety stock.

### Synthetic example (24 months, `--test-periods 12`)

| Policy | Fill rate, normal / bootstrap | Stockout periods, normal / bootstrap | Avg on hand, normal / bootstrap |
|---|---|---|---|
| (s, Q) static (with or without `--trend-seasonal`) | 94.4% / 94.6% | 11 / 12 | 885.2 / 712.4 |
| (R, S) static or dynamic, R = 1 | 90.9% / 90.7% | 20 / 17 | 598.6 / 427.9 |
| (R, S) static or dynamic, R = 3 | 93.4% / 94.2% | 11 / 11 | 1,306.6 / 1,032.1 |

Here dynamic levels change nothing: with 12 training months no SKU gets a seasonal model (ADR 0006), so every level is static. (R, S) with R = 1 holds 32% less stock than (s, Q) but loses 3.5 points of fill rate and has 9 more stockout periods; R = 3 almost matches (s, Q) service with about 48% more stock.

## Alternatives considered

| Alternative | Benefit | Cost / why not now |
|---|---|---|
| (R, s, S) or (s, S) policies | Fewer, larger orders; the textbook optimum for many cost structures | Needs order and holding costs to set two levels; more parameters to explain and test |
| Safety stock that varies by period too (sigma per season, or quantiles of forecast errors) | Protects peaks and troughs in proportion to their own uncertainty | Needs many more errors per season than a 36-month history gives |
| Rolling refit through the test window | Closer to how a planner works | Changes the meaning of the out-of-sample replay of ADR 0005; separate decision |
| Dynamic levels on by default with `--trend-seasonal` | One option less | Would change the 0.3.0 reports without asking |
| Sum of the forecasts over whole periods instead of mean x (L + R) | Slightly simpler | A constant forecast would not give the static level when `L` is fractional |

## Limitations

- The safety stock is static. With the default sigma (demand standard deviation) it still includes the seasonal swing that the levels now follow, so it double counts; the RMSE alternative is too noisy on short holdouts. A better per-period error estimate is future work.
- In-sample, the levels are the seasonal profile at the final level, not what a planner would have used at the time; the in-sample replay stays a consistency check, as before.
- One split in time and three synthetic items: the 48-month result is an indication of the mechanism, not evidence about real data.
- The review calendar starts at each SKU's first period; reviews are not aligned across SKUs.
