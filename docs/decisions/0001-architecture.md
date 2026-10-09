# 0001: Architecture of inventory-policy-lab

- Status: accepted (alpha)
- Date: 2026-10-09
- Deciders: Rodrigo Pantoja Navajas

## Context

Operations students, lecturers and analysts need to go from a demand history to a defensible inventory policy and to see why each number is what it is. The tool should install anywhere Python 3.11+ exists, need nothing at runtime, and be small enough to read and audit in one sitting.

## Decision

- A standard-library-only package (`src/` layout) with single-purpose modules: `reader` → `analysis` (using `classify`, `forecast`, `policy`, `simulate`) → `render`, wired together by `cli`. Data flows one way: `reader` returns a plain `DemandData`, `analysis` returns a `Report`, renderers only format a `Report`.
- Every formula is a small pure function (`safety_stock`, `eoq`, `croston`, ...) that is public and tested on its own with numbers computed by hand.
- Normal quantiles come from `statistics.NormalDist`; means and deviations from `statistics`.
- Errors are exceptions carrying an exit code (2 usage, 3 input file, 4 data, 5 history); only `cli.main` prints them.
- Output is Markdown for people and JSON (every number, rounded to 4 decimals) for other programs.

## Alternatives considered

| Alternative | Benefit | Cost / why not now |
|---|---|---|
| pandas / statsmodels / scipy | Richer models (Holt-Winters, ARIMA), faster vector math | Heavy dependencies for a teaching and analysis tool; the formulas would be hidden behind library calls; harder to verify by hand |
| One script | Less structure | Harder to test each formula alone and to extend |
| Wide input (one column per period) | Matches some spreadsheets | Long format is what ERPs export and handles lead times and costs per row; wide files are easy to melt first |
| Guessing period frequency for dates | Fills gaps in daily or weekly data | Wrong guesses create fake zero-demand periods. Chosen: complete calendars only for months and integers |

## Consequences

- Positive: zero runtime dependencies, deterministic output, each number traceable to a function and a reference.
- Negative: no trend or seasonal models; files are read into memory.
- Revisit if trend/seasonal methods or distribution-free safety stock (bootstrap) are added.
