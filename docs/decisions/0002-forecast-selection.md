# 0002: Forecast selection by holdout MASE, with candidates by demand pattern

- Status: accepted (alpha)
- Date: 2026-10-09
- Deciders: Rodrigo Pantoja Navajas

## Context

The policy depends on a forecast of demand per period. A default method (say, a 3-period moving average for everything) is common practice and often wrong. The method should be chosen per SKU on evidence, with a measure that works on series with zero-demand periods, and only among methods that make sense for the SKU's demand pattern.

## Decision

- Backtest every candidate on the last `holdout` periods with a rolling origin (each holdout period forecast from the periods before it, one step ahead).
- Score with MASE (Hyndman & Koehler, 2006): holdout MAE divided by the in-sample MAE of the one-step naive forecast on the training periods. Report MAE, RMSE and bias too. Do not use MAPE: it divides by actual demand, which is zero in many periods.
- Pick the lowest MASE; ties go to the earlier method (naive, moving average, SES, Croston, SBA). When MASE is undefined (constant training data), pick by MAE and say so in the notes.
- Candidates by Syntetos-Boylan pattern: smooth and erratic SKUs use naive, moving average and SES; intermittent and lumpy SKUs use SES, Croston and SBA.

## Why naive and moving average are excluded on intermittent and lumpy SKUs

After a run of zero-demand periods, naive and short moving averages forecast exactly zero. On a holdout that happens to be mostly zeros, that forecast scores a very low error (in the first version of this tool, an intermittent and a lumpy SKU of the synthetic dataset picked naive with MASE 0.00 and 0.07 and a forecast of 0). A zero forecast means a reorder point equal to the safety stock and no expected demand in the order quantity: it is accurate on the error measure and wrong for stock. Teunter & Duncan (2009) show that per-period error measures are not appropriate for intermittent demand and that a method that always forecasts zero is hard to beat on them. Croston-type methods estimate a demand *rate*, which is what the policy needs.

## Alternatives considered

| Alternative | Benefit | Cost / why not now |
|---|---|---|
| Fixed method per pattern (SES for smooth, SBA for intermittent) | Simple, matches the categorization literature | Ignores the data; no evidence shown to the user |
| Select by inventory outcome (replay each method's policy) | Measures what matters for stock | More computation and a circular in-sample choice; candidate for a later version |
| Optimize smoothing constants per SKU | Better fit | Overfits short series; fixed, documented constants are easier to audit |

## Consequences

- The choice is visible: the report shows MASE for every candidate and the bias of the pick.
- On intermittent SKUs the pick among SES, Croston and SBA is still made with a per-period measure, which is a known weakness (README, Limitations). The replay is the check on it.
