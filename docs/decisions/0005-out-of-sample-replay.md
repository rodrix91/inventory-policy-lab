# 0005: Out-of-sample replay with a split in time

- Status: accepted (alpha)
- Date: 2026-10-14
- Deciders: Rodrigo Pantoja Navajas

## Context

The replay of ADR 0003 applies the policy computed from the whole history to that same history. It checks that the policy is consistent with the data, but it is optimistic: the forecast, the sigma and the bootstrap draws have all seen the periods they are scored on. ADR 0004 kept the normal formula as the default until an out-of-sample comparison showed whether the bootstrap's in-sample advantage holds outside the data it resamples.

## Decision

- Add `--test-periods N` (`Config.test_periods`, 0 = off, the default). The file's calendar is split in time: the first `T - N` periods train, the last `N` test. No shuffling and no cross-validation folds, because demand is a time series and the question is how a policy set today does on the periods that follow.
- Everything a policy depends on is fitted on the training periods only: ABC (on training demand), the demand pattern, the forecast backtest and pick (the `--holdout` backtest runs inside the training window), the demand sigma or RMSE, the observed lead times whose row falls in training, and the bootstrap draws. The unit cost is the SKU's most recent one, as in the main report; it only affects ABC by value and EOQ, not the service results.
- Both safety-stock methods are always fitted and replayed, whatever `--safety-stock` says, so the comparison is side by side.
- The fitted (s, Q) policy is replayed over the whole history with `simulate(..., warmup=T - N)`: the training periods are replayed but not scored, and the test periods start from the stock, backorders and open orders the policy left at the end of training. Restarting the test with `s + Q` on hand would hand every policy a full shelf on day one and inflate its first-cycle service.
- The report shows, per method, the in-sample result (the same policy scored on its training periods) next to the out-of-sample one. The gap is the optimism of the in-sample replay.
- A SKU with no history in the training periods (introduced during the test) is listed as skipped. A SKU with fewer than `holdout + 2` training periods is kept and fitted with the short-history fallback of the main analysis, with its note. The training window itself must hold at least `holdout + 2` periods, otherwise the run stops with a history error (exit 5).
- The output of the main report does not change when the option is off: the Markdown section and the JSON key `out_of_sample` only appear with `--test-periods`.

## Results on the synthetic example (`--test-periods 12`: train 2024-01 to 2024-12, test 2025-01 to 2025-12)

| Safety stock | Fill rate, in-sample (train) | Fill rate, out-of-sample (test) | Stockout periods, in / out | Avg on hand (sum), in / out |
|---|---|---|---|---|
| normal | 98.8% | 94.4% | 4 / 11 | 1,042.4 / 885.2 |
| bootstrap | 99.9% | 94.6% | 1 / 12 | 864.4 / 712.4 |

Out of sample, both methods lose 4 to 5 points of fill rate and the bootstrap's in-sample lead almost disappears: 94.6% against 94.4%, with one stockout period more, though with about 20% less average stock. The losses are concentrated in two items whose pattern a level forecast cannot follow: the trending SKU-004 (79.7% normal, 67.7% bootstrap) and the seasonal SKU-003 (82.9% normal, 94.4% bootstrap). The intermittent SKU-008 improves with the bootstrap (85.9% to 100%). SKU-011 starts in 2025-03 and is skipped. These figures are pinned by `tests/test_validation.py`.

## Alternatives considered

| Alternative | Benefit | Cost / why not now |
|---|---|---|
| Rolling origin (refit every period) | Uses the data more fully; closer to how a policy is recomputed in practice | One fit per period and SKU; harder to read in a report. Candidate for later |
| Fraction (`--train-fraction 0.5`) instead of a period count | Scales with history length | A count is what a planner thinks in ("the last year") and maps directly to the calendar |
| Restart the test with `s + Q` on hand | Simpler; test independent of training replay | Flatters the first cycle of every policy; the warm-up keeps the state honest |
| Reuse `--holdout` for the split | One option fewer | `--holdout` is the forecast backtest inside the fit; mixing both would let the test leak into the forecast pick |

## Limitations

- One split, one test window. With 24 periods, 12 test periods hold at most a few replenishment cycles per SKU, and intermittent SKUs only a handful of demands; the results are an indication, not a statistically tight estimate.
- The comparison only shows that neither method is protected against trend and seasonality, because neither models them. It does not say which method is better in general.
- The policy is fixed through the test window, so the out-of-sample result is pessimistic for an operation that recomputes its policy every period.
- Default lead times (`--lead-time`) are used for SKUs with no lead time observed in training, as in the main report.
