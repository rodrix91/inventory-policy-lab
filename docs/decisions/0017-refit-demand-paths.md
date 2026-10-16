# 0017: Demand paths that refit the forecast

- Status: accepted (alpha), opt-in
- Date: 2026-10-16
- Deciders: Rodrigo Pantoja Navajas

## Context

ADR 0015 scores each candidate on demand paths made of the training forecast plus a resampled one-step error. Those paths trust the fitted model: the forecast of the test year is the same on every path, so the search never pays for a wrong level, trend or season. ADR 0015 named this as the reason the search overfits (fill rates of 86% to 95% out of sample) and ADR 0016 showed that a fill-rate floor on such paths cannot fix it. The paths themselves need to carry the uncertainty of the model.

## Decision

- **Opt-in**: `--optimize-paths refit` (`Config.optimize_paths = "refit"`, default `"forecast"`, the paths of ADR 0015), only with `--optimize-cost` (exit 2 otherwise). With the default, the reports with and without `--optimize-cost` are byte for byte those of 0.9.0 (122 outputs compared).
- **Bootstrapped training histories (fixed-design residual bootstrap).** On the training periods only, the picked forecast method gives the one-step rolling-origin forecast `f_t` of every period it can forecast (the same forecasts whose errors `e_t = y_t - f_t` ADR 0015 resamples; for a smoothing model these come from the fit cache). Each history keeps the periods without a forecast and replaces each other period by `max(f_t + e*_t, 0)`, where `e*` is a moving-block bootstrap of the errors in their time order, blocks of `round(n^(1/3))` errors (at least 1; `n` = number of errors), each starting at a random position, the last one cut. Blocks keep short runs of errors together, so autocorrelated misses (a season the model gets wrong two months in a row) survive the resampling.
- **Refit and path.** The method picked on the real training history is refitted on each bootstrapped history: a damped Holt or Holt-Winters model runs its own parameter search; a level method (moving average, SES, Croston, SBA, naive) is applied to it. The refit's forecasts of the test periods, plus one resampled one-step error per period (floored at zero), make one path; there is one bootstrapped history and one refit per path (`--optimize-samples`). Model selection is not repeated per history (a limit: it would multiply the cost by the number of candidates). A refit with no valid fit (for example multiplicative Holt-Winters on a history with a zero) keeps the training forecast and is counted.
- **Fallback.** With fewer than two one-step forecasts (too short a history) nothing can be resampled: the SKU keeps the plain paths with demand deviations, as in ADR 0015, and the report says how many SKUs were refitted.
- **Seeds.** The histories use their own generator (`seed:sku:optimize:refit`), the path errors the generator of ADR 0015; the other replays' draws do not move.
- **Reporting, only with the option.** Markdown: one sentence after the description of the search (how the paths are built, SKUs refitted, failed refits). JSON: `optimize_paths` in the settings, `out_of_sample.optimized.paths` (`kind`, `refitted_skus`, `block_length` per refitted SKU), and per SKU `paths` and `refit_failures`. API: `Config.optimize_paths`, `OptimizedReplay.paths` and `refit_failures`, `OutOfSampleReport.optimize_paths`, `SkuResult.refit_forecasts` and `refit_failures`; in `inventory_policy_lab.optimize`: `bootstrap_histories`, `block_bootstrap`, `block_length`, `PATH_KINDS`.
- **No leak, tested**: the histories are built from the training periods only. Setting every test period of the 48-month series to zero, or to ten times its demand, leaves every SKU's search and test levels identical while the optimised replay's score changes.
- **Time** (best of two wall-clock runs, one process each, this machine, 100 paths): 48-month series 1.7 s with plain paths and 2.7 s with refit paths (two of three SKUs refit a Holt-Winters model, 200 refits, all fit-cache misses because every bootstrapped history is a new key; the one-step forecasts of the training prefixes are cache hits); 24-month example 5.8 s and 5.8 s (its 12 training months only allow level methods, which refit in microseconds). Without the cost search both files take 0.12 to 0.16 s.

## Consequences

- On the README runs (`--test-periods 12 --trend-seasonal`, 50 per order, 1 per unit-month, 10 per unit short, 100 paths, seed 0), fill rate / test cost of the cost-optimised policy, plain paths against refit paths:
  - 48-month (R, s, S) R = 1: 94.9% / 5,119 against 97.9% / 4,084, below the normal (6,133) and bootstrap (4,945) heuristics and below (R, S) at 0.98 (4,474). It holds with seed 1 (97.3% / 4,325) and 200 paths (98.1% / 4,014).
  - 48-month (s, Q): 88.4% / 7,766 against 96.4% / 5,371, but that is not robust: seed 1 gives 91.0% / 6,901 and 200 paths 90.1% / 7,162, so (s, Q) stays above the bootstrap heuristic (5,125) in two of three runs.
  - 24-month (s, Q): 90.6% / 18,016 against 89.0% / 20,275 (seed 1: 20,792; 200 paths: 20,703); worse.
  - 24-month (R, s, S): 86.0% / 19,102 against 89.5% / 18,387 (seed 1: 19,099; 200 paths: 19,283); better fill, still far above the heuristics (15,576 normal, 14,157 bootstrap).
- So refitting helps where there is a model to be uncertain about (36 training months with Holt-Winters), and does nothing useful where 12 training months only allow a level method: there the bootstrapped histories barely move the level forecast, and the problem is the frozen forecast itself, which no search on training data can see. With a 0.95 fill floor (ADR 0016) the 48-month results do not change and the 24-month ones cost more (21,827 and 19,179).
- The option stays a diagnostic. A path generator that also re-selects the model, or a search at every rolling origin, are the next candidates.
