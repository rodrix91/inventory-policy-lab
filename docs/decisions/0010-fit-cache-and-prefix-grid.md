# 0010: Fit cache and one-pass prefix grid for damped Holt and Holt-Winters

- Status: accepted (alpha)
- Date: 2026-10-15
- Deciders: Rodrigo Pantoja Navajas

## Context

ADR 0009 recorded the cost of the rolling origin: on the 48-month series with `--trend-seasonal` and the residual bootstrap a run took about 10 seconds against about 1 for the fixed origin, and the test suite about a minute. A cProfile of `--test-periods 12 --trend-seasonal --bootstrap-source residuals --rolling-origin --policy RS --dynamic-levels` on that series (0.6.0) showed where it went: 23.5 of 25.2 profiled seconds inside `fit_holt_winters`, with 2,165 grid searches and 905,490 calls of `holt_winters_fit`, plus 921 damped Holt grid searches. Almost all of them were repeats. A grid fit depends only on the history it is given, and the same prefixes of a series are fitted again and again:

- the backtest of one origin fits the prefixes ending 6 to 1 periods before it, and the next origin fits five of them again;
- the residual errors of ADR 0008 fit every prefix from period 2 (24 for Holt-Winters) at every origin;
- the normal and the bootstrap replay refit the same SKU on the same history.

The 2,165 Holt-Winters grid searches covered 732 different histories, and those histories are the prefixes of a handful of series.

## Decision

- **A bounded cache of grid fits.** `fit_holt_damped` and `fit_holt_winters` look the history up in a least-recently-used store of 4,096 entries (`FIT_CACHE_SIZE`) before running the grid. The key is the model, the season length and kind, and the exact history: the set of value types and the `repr` of every value, so `10` and `10.0`, or `0.0` and `-0.0`, are different keys even though they compare equal. A history with no valid multiplicative fit is stored as its `FitError` message and raises the same error again. The stored `SmoothingFit` is frozen, so sharing it is safe; the store is guarded by a lock. Argument errors (too short, unknown kind, a zero in a multiplicative history) are raised before the cache, as before. `fit_cache_info()` and `clear_fit_cache()` are public for long-running processes.
- **One pass over every prefix.** On a miss the grid scores each of its 144 (damped Holt) or 576 (Holt-Winters) parameter sets once over the whole history and records the SSE after every step. The start of both models depends only on the first two periods or the first two seasons, so it is the same for every prefix, and the SSE after step `k` is exactly the SSE a fit on the first `k` periods computes: same operations, same order. Each prefix not stored yet takes the first parameter set of strictly lowest SSE (the plain grid's tie rule) and gets its fit from `holt_damped_fit` or `holt_winters_fit` with those parameters; all of them are stored. A multiplicative parameter set whose level stops being positive at a step is invalid for the prefixes that include that step and valid for the shorter ones, as in the plain grid. So the first fit of a series costs about one grid search and leaves its shorter prefixes ready for the backtest and the residual errors.
- **Results unchanged, bit for bit.** Nothing outside the two fit functions changed. `tests/test_fit_cache.py` keeps the 0.6.0 grid search verbatim as a reference and checks that every prefix of five series (trend, season, trend and season, noise, and a multiplicative collapse) gets the same `repr` of the fit, or the same error, from the cache in both call orders; and that the Markdown and JSON reports of six option sets on the 24-month example and on the 48-month series are byte for byte the same with the reference swapped in, cold and warm. Before merging, 76 Markdown and JSON reports (13 option sets on the 48-month series, the 24-month example and the worked example) were compared byte for byte against 0.6.0: all identical.

## Results

Wall time of one command (best of two runs, Python 3.12, including the interpreter start), `--test-periods 12 --trend-seasonal --bootstrap-source residuals`:

| Run | 0.6.0 | With the cache |
|---|---|---|
| 48-month series, (s, Q), fixed origin | 1.01 s | 0.15 s |
| 48-month series, (s, Q), `--rolling-origin` | 10.11 s | 0.22 s |
| 48-month series, (R, S) dynamic R = 1, `--rolling-origin` | 10.14 s | 0.22 s |
| 24-month example, (s, Q), fixed origin | 0.17 s | 0.11 s |
| 24-month example, (s, Q), `--rolling-origin` | 1.03 s | 0.32 s |
| 24-month example, (R, S) dynamic R = 1, `--rolling-origin` | 1.02 s | 0.32 s |

Profiled (cProfile) on the (R, S) rolling run of the 48-month series, the 2,165 Holt-Winters and 921 damped Holt fit requests are the same, but they now run 6 Holt-Winters and 3 damped Holt passes (one per SKU and model: the in-sample fit on all 48 months stores every shorter prefix, so every later request is a hit) and 150 plus 135 single fits for the picked parameters, instead of 905,490 and 130,032 single fits: 0.58 profiled seconds instead of 25.2. The 212 tests of 0.6.0 run in 4.2 seconds instead of 63; the new reference tests run the plain grid on purpose and add about 28.

## Alternatives considered

| Alternative | Benefit | Cost / why not |
|---|---|---|
| Cache only (no prefix pass) | Simpler | Every new history still costs one grid search per prefix the first time; the residual errors at the first origin alone need about 13 Holt-Winters grids per SKU and kind |
| Cache scoped to one `analyze` call | No state between calls | Needs the cache threaded through `Config`, the backtest and the forecasters; the bounded global store gives the same results and the same speed |
| Key on the float values (tuple equality) | Faster key | `0.0 == -0.0` and `10 == 10.0` would share an entry, and the returned fit could differ in the sign of a zero or an `int` field |
| Vectorised grid (NumPy) | Faster still | Runtime stays standard-library only (ADR 0001) |
| Carry the fit state forward from the previous origin's prefix | Faster on very long series | The best parameter set changes between prefixes, so the state of one set cannot be reused for another; the one-pass grid already gives every prefix at the cost of one fit |

## Consequences

- The rolling origin is now about as cheap as the fixed origin; ADR 0009's "about 10 seconds" no longer holds (0.2 s on that run).
- The process keeps up to 4,096 fits (a few megabytes at most); `clear_fit_cache()` frees them.
- The reference tests are the guard for any later change of the recursions: a change in `holt_damped_fit` or `holt_winters_fit` must be mirrored in the one-pass grid, or those tests fail.
