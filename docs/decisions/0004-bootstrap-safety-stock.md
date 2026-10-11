# 0004: Bootstrap safety stock as an option, not the default

- Status: accepted (alpha)
- Date: 2026-10-11
- Deciders: Rodrigo Pantoja Navajas

## Context

The 0.1.0 replay showed where the normal safety-stock formula fails: the lumpy SKU-012 of the synthetic example reached a 72.5% fill rate and the intermittent SKU-010 76.9%, at a 95% cycle-service target. Their demand is mostly zero with occasional large orders, nothing like a normal distribution. The opposite also happens: the erratic SKU-005 has a standard deviation inflated by a few large months, so the formula holds 555.7 units on average to reach a fill rate it would also reach with much less.

## Decision

- Add `--safety-stock bootstrap`. For each SKU, draw N protection intervals (default 2000): the interval length is a lead time drawn from the SKU's observed lead times (or the default) plus the review period, rounded half up to whole periods; its demand is the sum of that many periods drawn with replacement from the SKU's history. The safety stock is the service-level quantile (nearest rank) of those sums minus `D (L + R)`, floored at zero, so the reorder point keeps the same form `s = D (L + R) + SS`.
- Seed one `random.Random` per SKU with `"<seed>:<sku>"`. Reports are reproducible, and adding or removing other SKUs does not change a SKU's result.
- Keep the normal formula as the default. It is the textbook method readers expect, it needs no random numbers, and the bootstrap's advantage on the example is measured in-sample.

## Results on the synthetic example (2000 draws, seed 0)

SKU-012: 72.5% to 100% fill rate. SKU-006: 95.9% to 100%. SKU-005: 100% in both, average on hand 555.7 to 314.5. SKU-010: 76.9% to 78.4%. All SKUs: 99.4% to 99.8% fill rate, total average on hand 1,257.5 to 1,065.4. These figures are pinned by `tests/test_analysis.py`.

## Alternatives considered

- **Compound-Poisson or gamma demand.** Closer to the theory of intermittent demand, but each needs a fitted distribution and its own failure modes; the bootstrap uses the data as it is and needs no fit.
- **Moving-block bootstrap.** Keeps autocorrelation, but with 24 periods of history the blocks would be few and the result unstable. Independent draws are the simpler first step.
- **Bootstrap by default.** Rejected until an out-of-sample comparison (fit on the first part of the history, replay on the rest) shows it holds outside the data it was drawn from.

## Consequences

- The in-sample replay flatters the bootstrap, because it resamples the history it is replayed on. The README says so next to the comparison.
- Demand sizes larger than any in the history cannot be drawn; trend and seasonality are ignored, as in the normal formula.
- `Policy.z` is still reported with the bootstrap, as the normal quantile of the service level, for comparison.
