# Inventory Policy Lab: engineering decisions

This is the navigation page for the project's accepted **architecture decision records (ADRs)**. The ADRs document the reasoning behind each method, the tradeoffs that were considered, and why the defaults or opt-in settings were chosen.

Start with the [main README](../README.md) for command examples and the project limitations, or the [worked example](../examples/worked_example.csv) for a small reproducible input.

## From data to a decision

```text
Monthly demand history (CSV)
  -> validation and per-SKU aggregation
  -> ABC-XYZ and demand-pattern classification
  -> training-only forecast backtesting and method selection
  -> safety stock, reorder points and order quantities
  -> historical and optional out-of-sample policy replay
  -> optional order/holding/stockout cost comparison
  -> Markdown or JSON report
```

These stages are described in the source-level [architecture ADR](decisions/0001-architecture.md). The flow is descriptive, not a guarantee that a proposed stock policy performs well on real customer demand.

## Decision records by topic

### Foundations and forecasting

| ADR | Decision | Why it matters |
|---|---|---|
| [0001](decisions/0001-architecture.md) | Project architecture | Auditable standard-library modules and one-way data flow |
| [0002](decisions/0002-forecast-selection.md) | Forecast selection | Holdout MASE and method candidates by demand pattern |
| [0003](decisions/0003-policy-and-replay.md) | Policy and replay | How stock levels are derived and simulated |
| [0004](decisions/0004-bootstrap-safety-stock.md) | Bootstrap safety stock | Optional non-normal variability estimates |
| [0005](decisions/0005-out-of-sample-replay.md) | Time-based out-of-sample replay | Avoiding evaluation on the same periods used for fitting |
| [0006](decisions/0006-trend-and-seasonal-forecasts.md) | Trend and seasonality | Optional forecasting candidates for changing demand |

### Inventory policies and uncertainty

| ADR | Decision | Why it matters |
|---|---|---|
| [0007](decisions/0007-periodic-review-and-dynamic-levels.md) | Periodic review and dynamic levels | Alternatives to static reorder levels |
| [0008](decisions/0008-residual-bootstrap-and-period-safety-stock.md) | Residual bootstrap | Time-specific uncertainty and safety stock |
| [0009](decisions/0009-rolling-origin-replay.md) | Rolling-origin replay | Sequential historical evaluation |
| [0010](decisions/0010-fit-cache-and-prefix-grid.md) | Fit caching and prefix grid | Reusing calculated fits efficiently |
| [0011](decisions/0011-refit-every-k-periods.md) | Refit cadence | Updating policy inputs at intervals |
| [0013](decisions/0013-periodic-review-rss-policy.md) | Periodic-review (R, s, S) | An additional replenishment policy family |

### Cost and service tradeoffs

| ADR | Decision | Why it matters |
|---|---|---|
| [0012](decisions/0012-cost-of-the-out-of-sample-replay.md) | Replay cost | Comparing policies on an economic basis |
| [0014](decisions/0014-cost-rates-per-sku.md) | Per-SKU cost rates | Allowing different inventory cost structures |
| [0015](decisions/0015-cost-optimised-levels.md) | Cost-optimised levels | Searching stock parameters using training-derived scenarios |
| [0016](decisions/0016-fill-rate-floor-for-the-cost-search.md) | Fill-rate floor | Adding an explicit service constraint |
| [0017](decisions/0017-refit-demand-paths.md) | Forecast-refit demand paths | Accounting for forecast-model uncertainty |

The ADR numbers preserve the order in which design decisions were adopted. Topic grouping on this page does not alter that history.

## Reproduce a baseline analysis

From a clean project checkout using Python 3.11 or newer:

```bash
python -m inventory_policy_lab examples/demand_synthetic.csv
```

The dataset is **synthetic**, not evidence of real-world supply-chain performance. See the [CLI and methodology in the README](../README.md) before changing policy settings or interpreting the output as a purchase recommendation.

For changes to code or methodology, run:

```bash
python -m pytest
```

GitHub Actions additionally checks static typing, formatting, multi-platform behavior and packaged artifacts. See [CI](../.github/workflows/ci.yml) and the [contribution guide](../CONTRIBUTING.md).

## How to use these records

For an analyst reviewing a result, begin with ADRs 0002, 0003 and 0005 to understand forecast choice, stock logic and whether evaluation uses unseen periods. For a buyer comparing service level and total cost, read ADRs 0012 and 0015 through 0017. For a contributor extending the code, read ADR 0001 and the specific ADR for the feature being changed.

**Scope:** The project is marked alpha. Backtests and simulations are not substitutes for checking actual supplier constraints, data representativeness, business assumptions and human review. For vulnerabilities, follow the [security policy](../SECURITY.md) rather than publishing sensitive details.
