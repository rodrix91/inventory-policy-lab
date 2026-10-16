# 0014: Cost rates per SKU

- Status: accepted (alpha)
- Date: 2026-10-16
- Deciders: Rodrigo Pantoja Navajas

## Context

ADR 0012 prices the out-of-sample replay with three rates shared by every SKU and every unit. That is enough to rank policies on the same items, but it is not how carrying cost works: holding a unit costs a share of what the unit is worth (capital, storage, shrinkage), so a unit worth 310 costs about 365 times more to hold than one worth 0.85. The 24-month example spans exactly those unit costs, and with one holding rate of 1 per unit and month its cheap items look as expensive to stock as its dear ones. Order and stockout costs also differ by item (supplier, margin), and the input already carries one per-SKU attribute, `unit_cost`, in a way that extends cleanly.

## Decision

- **Holding as a yearly rate of the unit cost**: `--holding-cost-rate RATE` (`Config.holding_cost_rate`, at least 0). A unit on hand at the end of a period costs `RATE x unit_cost / periods_per_year`, so `0.25` with monthly data and a unit worth 48 is 1 per unit and month, the shared rate of ADR 0012. The rate is **yearly** because that is how carrying cost is quoted (Silver, Pyke & Thomas 2017) and how the EOQ input `--holding-rate` is already defined; `--periods-per-year` (12 by default, 52 for weeks) turns it into a per-period cost. It needs a `unit_cost` column (data error, exit 4, otherwise) and excludes `--holding-cost` (usage error, exit 2): one holding cost per run.
- **A new option, not `--holding-rate`.** `--holding-rate` already feeds the EOQ, which changes the order quantity. Reusing it to price the replay as well would change 0.8.0 reports that combine EOQ with cost rates, and would tie the two settings together, which ADR 0012 keeps apart on purpose (a cost table never moves the policy next to it). The two can be given the same value when the user wants the EOQ and the cost to agree.
- **Order and stockout costs from optional columns**: with `--cost-columns` (`Config.cost_columns`), the reader also takes `order_cost` and `stockout_cost` columns, each the most recent non-empty value of the SKU, exactly like `unit_cost`; negative or non-numeric values are data errors. A SKU without a value uses `--order-cost` / `--stockout-cost` (or 0). The columns are read only with the option, so a file that happens to have columns with those names gives the 0.8.0 report without it. At least one of the two columns must be present when the option is given.
- **Either of the two turns the costs on**, like any rate of ADR 0012, and needs `--test-periods`.
- **What changes in the report, only with them.** Markdown: the rates sentence names where each rate comes from, and a table of each SKU's rates (per order, per unit held a period, per unit short) opens the cost section; the totals and per-SKU tables are unchanged in shape. JSON: `holding_cost_rate` and `cost_columns` in the settings when used; `out_of_sample.costs.rates` gives `holding: null` and `holding_rate_of_unit_cost` with the rate, `cost_columns: true` with the columns; each SKU in `out_of_sample.costs.skus` gets its `rates`. API: `Config.sku_cost_rates(history)`, `Config.per_sku_costs`, `OutOfSampleReport.sku_rates`, `rates_of(sku)`, `SkuHistory.order_cost` / `stockout_cost`, `DemandData.has_order_cost` / `has_stockout_cost`, and `read_demand(path, cost_columns=True)` / `parse_rows(rows, cost_columns=True)`. Without the new options, the Markdown and JSON reports are byte for byte those of 0.8.0 (checked on 104 outputs: 17 option sets, including every cost option of 0.8.0, x 3 datasets x 2 formats).
- **The unit cost is the file's**, the most recent value of the SKU, which may come from a test row. That is the same value the ABC classes use, and the rates only price the replay (they are inputs, not demand), so this is not a leak of test demand.

## Consequences

- On the 24-month example, pricing holding at 25% a year of each unit cost instead of 1 per unit and month cuts the holding cost by about three quarters (most of the example's units are worth less than 48, the unit for which both rates agree) and moves the ranking: (R, s, S) with a monthly review becomes the cheapest of the five policies in all four columns (README, "Policies compared by cost").
- The shared rates of ADR 0012 remain the default, and per-SKU rates are opt-in; a stockout cost as a share of margin would need a price column, which the input does not have.
- The rates still only score the replay. Choosing `s` and `Q` for cost is ADR 0015.
