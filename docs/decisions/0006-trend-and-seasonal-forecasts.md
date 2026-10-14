# 0006: Damped Holt and Holt-Winters as opt-in forecast candidates

- Status: accepted (alpha)
- Date: 2026-10-14
- Deciders: Rodrigo Pantoja Navajas

## Context

Every forecasting method of ADR 0002 is a level method: naive, moving average and SES for smooth and erratic items, SES, Croston and SBA for intermittent ones. The out-of-sample replay of ADR 0005 showed where that hurts. On the synthetic example with 12 test periods, most of the service lost out of sample came from the trending SKU-004 (79.7% fill rate with the normal formula, 67.7% with the bootstrap) and the seasonal SKU-003 (82.9% and 94.4%). A level forecast fitted on the first year cannot follow either pattern through the second.

## Decision

- Add three candidates, implemented in `smoothing.py` with the standard library only (the runtime has no dependencies and this does not change that):
  - `holt_damped`: Holt's linear trend with a damped trend (Gardner & McKenzie, 1985), started at `L = y(2)`, `B = y(2) - y(1)`.
  - `hw_additive` and `hw_multiplicative`: Holt-Winters (Winters, 1960) with the same damped trend, started with the classic heuristic on the first two seasons (level = mean of season 1, trend = difference of the two season means / m, seasonal = first season minus, or divided by, that level).
- They are **opt-in**: `--trend-seasonal` (`Config.trend_seasonal`). Without it the candidates, the report and the JSON are what they were in 0.2.0, apart from two new JSON settings keys (`trend_seasonal`, `season_length`).
- With the option they join the backtest of smooth and erratic SKUs, after naive, moving average and SES (so a tie keeps the old pick), and are chosen by the same rule: lowest MASE on the holdout. Intermittent and lumpy SKUs keep SES, Croston and SBA; a trend or a season is not identifiable from a few non-zero periods.
- **Parameters are fitted inside the data the model sees.** For each call, a grid search picks the alpha, beta, phi and (Holt-Winters) gamma that minimise the sum of squared one-step errors on that history: alpha 0.1 to 0.9 by 0.1, beta and gamma in {0.05, 0.1, 0.2, 0.3}, phi in {0.8, 0.9, 0.95, 0.98}. The backtest calls the method at each holdout origin with the periods before it, and the out-of-sample replay fits on the training periods only, so neither the holdout nor the test periods can leak into the parameters. `tests/test_smoothing.py` checks this by replacing the test periods with zeros and asserting that every fit, forecast and reorder point stays the same.
- **Not a candidate without enough history**, judged on the shortest fit of the backtest (the periods before the first holdout origin): damped Holt needs 4 periods (a start plus at least two one-step errors), Holt-Winters two full seasons (`2 x m`), and the multiplicative form demand above zero in every period. If no grid point keeps the multiplicative level positive, the candidate is left out and the SKU gets a note.
- **Season length**: `--season-length M`, by default `--periods-per-year` when it is a whole number (12 for months, 52 for weeks). With a fractional periods-per-year and no season length, only damped Holt is added. A season length without `--trend-seasonal` is a usage error, so it cannot be set and silently ignored.
- **Forecast for the policy.** A trend or seasonal forecast changes from period to period, but the (s, Q) policy is static. When one of these models is picked, `D` is the mean of its forecasts for the next `L + R` periods (rounded half up, at least one), which is the demand the reorder point protects. For the level methods that mean equals the one-step forecast, so they are unchanged. Forecasts are floored at zero.
- **Safety stock is unchanged.** The normal formula uses the demand standard deviation by default (which a trend or a season inflates) or the holdout RMSE of the picked method with `--sigma rmse`, which is the consistent pairing for these models; the bootstrap works on the history as before.

## Results

### Synthetic example (24 months), `--test-periods 12`

Out of sample **nothing changes**. With 12 training months and a holdout of 6, the shortest fit has 6 periods: no SKU reaches the 24 Holt-Winters needs, and damped Holt, which is a candidate, loses the training holdout of SKU-004 (MASE 1.25 against 0.91 for the moving average) because its 2024 demand is nearly flat from July to November. SKU-003 stays at 82.9% / 94.4% and SKU-004 at 79.7% / 67.7% (normal / bootstrap), and the totals stay at 94.4% / 94.6%. On the full 24 months (the main report), damped Holt wins the holdout of SKU-003 (MASE 0.90 against 1.00 for naive) and SKU-009 (1.18 against 1.23 for SES); the replayed fill rate of all SKUs goes from 99.4% to 99.5%, with 0.3 units more average stock in total. SKU-004 still picks naive (1.67 against 2.06 for damped Holt).

### A 48-month synthetic series with known trend and seasonality

`trend_seasonal_series()` in `tests/test_smoothing.py`, seeded: T (level 40 growing 2 per month), S (100 with a yearly +-40 sine), TS (a growing level times a +-35% yearly sine). With `test_periods=12` the training window has 36 months, so Holt-Winters is a candidate.

| Safety stock | Fill rate out, before / after | Stockout periods out, before / after | Avg on hand out (sum), before / after |
|---|---|---|---|
| normal | 97.5% / 99.6% | 3 / 1 | 189.8 / 289.0 |
| bootstrap | 96.6% / 97.6% | 5 / 4 | 172.4 / 196.4 |

S picks additive Holt-Winters, TS multiplicative; T keeps naive, because damped Holt loses its training holdout. Service improves, but most of the gain is bought with more stock (52% more with the normal formula): a static policy can only set one reorder point for the whole year, so a better seasonal forecast mostly raises the level it protects. The table and the picks are pinned in `tests/test_smoothing.py`, as are the example results above.

## Alternatives considered

| Alternative | Benefit | Cost / why not now |
|---|---|---|
| statsmodels `ExponentialSmoothing` (maximum likelihood) | Mature, optimised parameters, prediction intervals | Adds numpy, scipy, pandas and statsmodels to a standard-library runtime |
| Candidates on by default | Every user gets them | Changes the picks and the reports of 0.2.0 without asking; the evidence above is not strong enough to make it the default |
| Undamped Holt (phi = 1) | Follows a straight trend exactly | Extrapolating a trend over the lead time is the classic overshoot; damping is the more robust default |
| Nelder-Mead or another optimiser | Continuous parameters, lower in-sample error | More code to test; a coarse grid is transparent and, with MASE choosing between models, the grain of the grid matters less than the choice of model |
| Seasonal naive or classical decomposition | Simple | Not smoothed; Holt-Winters contains the seasonal idea with a trend |
| A reorder point per period (time-varying policy) | The natural partner of a seasonal forecast | A different policy model and replay; candidate for later |

## Limitations

- **History**: Holt-Winters needs two full seasons before the first holdout origin. With monthly data and the default holdout of 6 that is 30 months in the file, or 30 training months with `--test-periods`. Most short histories get damped Holt only.
- **Static policy**: the reorder point is fixed, so a seasonal forecast can only move one level. Covering the peaks costs stock in the troughs, as the 48-month results show.
- **Selection by MASE on a short holdout**: with 6 holdout periods a trend model can lose to a level one on noise, as on SKU-004. The replay, not the MASE, says whether the policy works.
- **Grid search on in-sample SSE**: coarse, and it can overfit a short history; no information criterion and no prediction intervals.
- **Heuristic start**: the first two seasons set the initial states, so an unusual first year shapes the seasonal factors until gamma smooths them out.
