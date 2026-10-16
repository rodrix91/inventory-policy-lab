# 0013: Periodic-review (R, s, S) policy

- Status: accepted (alpha)
- Date: 2026-10-15
- Deciders: Rodrigo Pantoja Navajas

## Context

The tool had two policies: (s, Q), whose position is checked every period and which orders fixed lots of `Q`, and (R, S) (ADR 0007), which reviews every `R` periods and always orders back up to `S`. (R, S) places an order at every review where anything was sold, which is wasteful when an order has a fixed cost; (s, Q) only orders when needed but in fixed lots. The (R, s, S) policy combines both: review every `R` periods, and order up to `S` only when the position has fallen to `s` or below (Silver, Pyke & Thomas, 2017). With the cost evaluation of ADR 0012 the three can now be compared on one number.

## Decision

- **`--policy RsS`** (`Config.policy = "RsS"`, `Policy.kind = "RsS"`), with a whole `--review-period R` of at least 1, like (R, S).
- **Levels.** `s = D x (L + R) + SS`, the same formula and safety stock as the reorder point of (s, Q) and the `S` of (R, S), so all three protect the same interval with the same safety stock. `S = s + Q`, with the SKU's order quantity `Q` (EOQ or forecast x `--order-cover`, at least 1 unit). This is the simple heuristic of Silver, Pyke & Thomas for (s, S) systems (`S = s + Q`), not a joint cost optimisation of `s` and `S`: it keeps the safety stock comparable across policies and needs no new parameter. `Policy.order_up_to` stays `None` for (R, s, S), since `S` depends on `Q`, which the policy object does not hold; the reports show it.
- **Replay** (`simulate_rss`): same timing as (R, S): orders due arrive at the start of a period, demand is served or backordered, and the position is reviewed at the end of periods `R - 1, 2R - 1, ...`. At a review an order of `S - position` is placed only when the position is at or below `s`. The run starts with `s + Q` on hand, like (s, Q). With dynamic levels `s(t)` follows the forecast and `S(t) = s(t) + Q(t)`; in the rolling origin both `s` and `Q` are those of the refit that decides the period, as for (s, Q). Tested by hand (two replays worked period by period, one with a level and quantity per period), and against (R, S): with whole demands and levels, (R, s, S) with `Q = 1` is (R, S) with `S = s + 1`, checked on 200 random cases.
- **No leak**: the out-of-sample paths are the same as for the other policies (`_analyze_sku` on the history before each origin, `replay_policy` with warm-up); tested again for (R, s, S) by zeroing periods 40 to 47 of the 48-month series (decisions of the origins at 36 to 40 unchanged, later ones move), and `--refit-every 12` reproduces the fixed origin.
- **Reports.** Markdown: a policy line (`s`, `S = s + Q`, `R`) and the policy table columns `Reorder level (s)`, `Order qty (Q = S - s)`, `Review (R)`. JSON: `kind: "RsS"`, `reorder_point`, `order_quantity` and `order_up_to = s + Q` in the policy and in each out-of-sample replay; the rolling origin lists `reorder_points` and `order_quantities`. Reports of (s, Q) and (R, S) are unchanged byte for byte (76 outputs compared).

## Results

Out of sample, `--test-periods 12 --trend-seasonal --dynamic-levels --bootstrap-source residuals --rolling-origin` with `--order-cost 50 --holding-cost 1 --stockout-cost 10`, pinned in `tests/test_rss.py` (the README explains the rates). Cells: fill rate / total cost of the 12 test months, summed over the SKUs.

| Data | Policy | Normal, fixed | Normal, rolling | Bootstrap residuals, fixed | Bootstrap residuals, rolling |
|---|---|---|---|---|---|
| 48 months | (s, Q) | 100.0% / 5,139 | 100.0% / 5,112 | 99.8% / 3,951 | 99.9% / 3,869 |
| 48 months | (R, S), R = 1 | 100.0% / 3,066 | 100.0% / 3,592 | 95.4% / 3,732 | 99.4% / 2,482 |
| 48 months | (R, S), R = 3 | 99.9% / 5,924 | 100.0% / 6,859 | 97.2% / 5,499 | 99.4% / 5,520 |
| 48 months | (R, s, S), R = 1 | 100.0% / 5,801 | 100.0% / 5,905 | 99.9% / 4,540 | 100.0% / 4,404 |
| 48 months | (R, s, S), R = 3 | 100.0% / 9,836 | 100.0% / 10,764 | 100.0% / 8,262 | 100.0% / 9,159 |
| 24 months | (s, Q) | 94.4% / 21,371 | 99.8% / 17,735 | 92.2% / 23,849 | 98.5% / 19,178 |
| 24 months | (R, S), R = 1 | 90.9% / 17,313 | 97.3% / 13,405 | 88.5% / 19,956 | 96.0% / 14,813 |
| 24 months | (R, S), R = 3 | 93.4% / 21,594 | 97.0% / 19,353 | 92.9% / 25,599 | 96.9% / 23,004 |
| 24 months | (R, s, S), R = 1 | 99.3% / 15,576 | 100.0% / 15,818 | 97.9% / 17,490 | 99.5% / 16,632 |
| 24 months | (R, s, S), R = 3 | 97.9% / 25,065 | 99.3% / 24,634 | 96.7% / 29,523 | 98.4% / 29,018 |

Reading:

- **(R, s, S) is not cheaper by itself.** Ordering up to `s + Q` instead of `S = s` keeps about one lot more in stock. On the 48-month series, where (R, S) R = 1 already serves 100%, that extra stock costs about 3,100 in holding (4,351 against 1,266, normal, fixed) to save 7 of 36 orders (350): (R, S) R = 1 is cheapest in every column there at 10 per unit short (with the residual bootstrap and a fixed origin, its 95.4% fill rate makes (s, Q) cheaper above about 11).
- **It pays where service is short.** On the 24-month example the forecasts frozen at the end of a 12-month training window leave (R, S) at 90.9% (578 units short, normal, fixed); (R, s, S) R = 1 reaches 99.3% (43 short) and is the cheapest policy with a fixed origin. The break-even stockout cost between the two is about 6.8 per unit short (5.9 with the residual bootstrap). With a rolling origin (R, S) is short much less (173 units) and wins at 10, but (R, s, S) wins above about 24 per unit short (18 with the bootstrap).
- **R = 3 never wins at these rates**: it saves two thirds of the orders (about 1,200 on the 48-month series) but holds thousands of unit-months more to cover a longer interval. A higher order cost relative to holding would be needed to favour it.

## Consequences

- The three textbook policies are available under the same safety stock and the same out-of-sample machinery, and the cost table ranks them for a stated rate set.
- Part of what (R, s, S) wins on the 24-month example is simply more stock, which (R, S) with a higher service level might buy at a similar cost; that comparison is not made here. A cost-optimised `s` and `S` (for example Ehrhardt's power approximation, Management Science, 1979) is left for later.
