# 0016: Fill-rate floor for the cost search

- Status: accepted (alpha), opt-in
- Date: 2026-10-16
- Deciders: Rodrigo Pantoja Navajas

## Context

The cost search of ADR 0015 picks the safety stock and order quantity with the lowest expected cost on demand paths built from training data. On the README runs it promised cuts of 33% to 41% and then let the out-of-sample fill rate fall to 86% to 95%. A buyer who must keep a service commitment needs a way to say "cheapest, but not below this fill rate", and the obvious place to say it is the search itself.

## Decision

- **Opt-in**: `--optimize-fill-floor F` (`Config.optimize_fill_floor`), `0 < F <= 1`, only with `--optimize-cost` (exit 2 otherwise). Without it nothing changes: the reports with and without `--optimize-cost` are byte for byte those of 0.9.0 (122 Markdown and JSON outputs compared, including three `--optimize-cost` runs per file).
- **Expected fill rate on the same paths.** Each candidate pair is replayed on the same demand paths as its cost (common random numbers, ADR 0015); its expected fill rate is the units served from stock over the units demanded, both summed over all paths (1.0 if the paths have no demand). Summing before dividing weights each path by its demand, as the report's own fill rate does, and avoids undefined ratios on paths without demand. `expected_outcomes` returns `(cost, fill rate)` per pair; `expected_costs` keeps its signature and returns the cost part.
- **Accepted pairs.** Only pairs with expected fill rate `>= F` can be picked; among them the cheapest wins, with the existing order and tie rule (grid order, a strictly lower cost replaces the best). The quarter-sigma refinement moves around the best accepted pair and its pairs must meet the floor too.
- **Fallback to the heuristic.** When no grid pair meets the floor, the heuristic pair is kept (no refinement) and the SKU is marked `fell_back`. The heuristic pair is not exempt from the floor when other pairs meet it: the floor is a constraint on the pick, and the heuristic is only the default when the constraint cannot be met.
- **Reporting, only with the option.** Markdown: one sentence after the description of the search (the floor and how many SKUs fell back) and a column "Expected fill rate on training paths, normal / optimised" (marked "none met the floor" on fallback). JSON: `optimize_fill_floor` in the settings, `out_of_sample.optimized.fill_floor`, `summary.fell_back`, and per SKU `expected_fill_rate`, `heuristic_expected_fill_rate`, `feasible` (accepted pairs) and `fell_back`. API: `CostSearch.fill_floor`, `expected_fill`, `heuristic_fill`, `feasible`, `fell_back`; `OutOfSampleReport.optimize_fill_floor`; `search_levels(..., fill_floor=)`.
- **No leak**: the floor is evaluated on the training paths only; setting the test periods of the 48-month series to zero leaves every search identical (tested).

## Consequences

- On the README runs (`--test-periods 12 --trend-seasonal`, 50 per order, 1 per unit-month, 10 per unit short, 100 paths) the floor hardly binds, because the training paths already expect fill rates of 95% to 100% for most picks. Out-of-sample fill rate and test cost of the cost-optimised policy, without floor / 0.95 / 0.99:
  - 48-month (s, Q): 88.4% / 7,766, 88.4% / 7,766, 90.0% / 7,616.
  - 48-month (R, s, S): 94.9% / 5,119 in all three.
  - 24-month (s, Q): 90.6% / 18,016, 90.7% / 18,750, 91.4% / 20,985 (3 of 11 SKUs fell back at 0.99).
  - 24-month (R, s, S): 86.0% / 19,102, 86.1% / 19,859, 85.6% / 20,560 (1 fell back at 0.99).
- So a floor on the training model does not deliver the service it asks for out of sample: the gap is between the model's paths and the test, not inside the search. The floor is still the right constraint to have once the paths are more honest; ADR 0017 makes them carry the model's own uncertainty.
- The search time grows by the fill bookkeeping only (one sum per path).
