# 0003: Periodic review in the reorder point, and a replay to verify the policy

- Status: accepted (alpha)
- Date: 2026-10-09
- Deciders: Rodrigo Pantoja Navajas

## Context

The textbook continuous-review reorder point is `s = D L + z sqrt(L sigma_D² + D² sigma_L²)`. Demand history comes in periods (months, weeks), and the inventory can only be checked once per period of data. The first version of the replay applied that formula to the synthetic dataset and reviewed once per period: five of the six smooth items ended below a 95% cycle-service target, with fill rates from 61% to 94.5%, and one of them had 21 stockout periods out of 24.

The cause is undershoot: the inventory position is only seen at the end of each period, so it can fall well below `s` before an order is placed, and the order then has to cover one more period than the formula assumes.

## Decision

- Add the review period `R` to the protection interval: `SS = z sqrt((L + R) sigma_D² + D² sigma_L²)` and `s = D (L + R) + SS`, as for periodic-review systems in Silver, Pyke & Thomas (2017). `R = 1` (one period of data) by default; `--review-period 0` restores the continuous-review formula.
- Replay every SKU's history under its (s, Q) policy with backorders: arrivals at the start of the period, demand served from stock, review at the end, orders of `Q` while the inventory position is at or below `s` (so several at once if needed), arriving at the start of period `t + L + 1`. Report the fill rate, stockout periods, average on hand, orders placed and the largest backorder.

With `R = 1` all six smooth items reach fill rates of 98% to 100% in the replay.

## Alternatives considered

| Alternative | Benefit | Cost / why not now |
|---|---|---|
| Keep the continuous formula, report the replay only | Textbook-identical numbers | Systematically under-protects on period data; available with `--review-period 0` |
| (R, S) order-up-to policy | Natural for periodic review | Different policy family; the (s, Q) form keeps EOQ meaningful. Candidate for later |
| Lost sales instead of backorders | Closer to retail | The formulas assume backorders; mixing both would confuse the check |
| Out-of-sample replay (policy computed on a training window) | Honest estimate of future service | Needs longer histories than most teaching datasets; candidate for later |

## Consequences

- The replay is in-sample and uses one policy computed from the end of the history. It verifies that the policy is consistent with the data, not that it will achieve the same service in the future (README, Limitations).
- Where the normal approximation fails (lumpy items), the replay shows a fill rate below target instead of hiding it.
