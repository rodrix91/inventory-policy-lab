# 0012: Cost of the out-of-sample replay

- Status: accepted (alpha)
- Date: 2026-10-15
- Deciders: Rodrigo Pantoja Navajas

## Context

Every comparison so far (normal against bootstrap safety stock, fixed against rolling origin, (s, Q) against (R, S), the refit cadences of ADR 0011) is reported as three numbers: fill rate, stockout periods and average stock. They often move in opposite directions (the rolling origin of ADR 0009 keeps 100% fill rate on the 48-month series with 42% more stock), and the reader has to weigh them by eye. An operation weighs them with money: what an order costs, what holding a unit for a period costs, and what a unit short costs. The replay already counts all three quantities; it only lacked the prices.

## Decision

- **Three rates, the same for every SKU**, all optional and at least 0: `--order-cost` per order placed (`Config.order_cost`), `--holding-cost` per unit on hand at the end of a period, per period (`Config.holding_cost`), and `--stockout-cost` per unit short (`Config.stockout_cost`). Giving any of them turns the others into 0. They need `--test-periods` (usage error otherwise): the cost scores the out-of-sample replay, where it can rank policies honestly; pricing the in-sample replay would rank the method that saw the data best.
- **What each part counts**, from the replay of ADR 0003/0005 over the test periods only:
  - ordering: orders placed at the end of a test period (an (s, Q) period that orders `Q` twice counts two);
  - holding: the stock on hand at the end of each test period, summed (`average on hand x periods`, the same stock the report already shows);
  - stockout: the units of test demand not served from stock in their own period.
- **Stockout per unit short, not per backorder-period.** The replay backorders what it cannot serve and fills it first from the next arrivals. Two shortage costs fit that model: a cost per unit short (Silver, Pyke & Thomas 2017, the `B2` cost) or a cost per unit and period on backorder (`B3`). We use the first because it is the quantity the fill rate measures (`units short = demand x (1 - fill rate)`), so the cost and the service column of the same table agree, and because in this replay a backorder is cleared by the next arrival, so its duration is mostly the lead time rather than a decision of the policy. A per-period backorder cost can be added later from the same ledger if a user needs it.
- **The cost does not change the policy.** Safety stocks, levels and order quantities are fitted as before; the rates only score what each replay did. The EOQ inputs `--ordering-cost` and `--holding-rate` (yearly, as a fraction of unit cost) remain a separate setting that does change `Q`. Keeping them apart means a cost table never moves the fill-rate columns next to it, and the same policies can be priced with several rate sets.
- **Reporting, only with a rate.** Markdown: a "Cost of the test periods" section after the out-of-sample (and rolling-origin) tables, with the rates, one total row per safety-stock method and origin (orders, unit-periods held, units short, ordering, holding, stockout, total), and one row per SKU, method and origin. JSON: the three rates in the settings and `out_of_sample.costs` with `rates`, `summary` and `skus` (per method and origin `fixed` / `rolling`). API: `CostRates`, `CostBreakdown`, `replay_cost`, `total_cost`, `Config.cost_rates`, `OutOfSampleReport.costs`, `OutOfSampleReport.cost(method, origin)` and `sku_cost(sku, method, origin)`. Without a rate the Markdown and JSON reports are byte for byte those of 0.7.0 (checked on 76 outputs: 13 option sets x 3 datasets x 2 formats).
- **Tests by hand**: one replay priced period by period (with and without warm-up), and the hand case of ADR 0009 priced for both origins (fixed 8 orders and 20 units short: 120; rolling 6 orders and 10 short: 70 at 5 / 1 / 4).

## Consequences

- Policies can be ranked by one number per rate set, and the ranking can be checked against the fill rate and stock it comes from.
- The result depends on the rates, which are inputs, not facts: the README states the rates it uses and why, and a different ratio of stockout to holding cost can reverse a ranking.
- Rates are uniform across SKUs. Per-SKU prices (holding as a share of `unit_cost`, stockout cost by margin) would be more realistic; they are left for later, since uniform rates are enough to compare policies on the same items.
