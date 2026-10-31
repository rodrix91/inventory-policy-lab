# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [Semantic Versioning](https://semver.org/) (pre-1.0: minor versions may change behavior).

## [Unreleased]

- Reject booleans, non-integer sample counts and malformed direct Python inputs in both bootstrap safety-stock and residual quantile calculations. Validate service levels, lead/review durations, observed demand, forecasts and reachable residuals before drawing random numbers, raising actionable `ValueError` messages instead of accepting `True` as a number or leaking `TypeError`/`OverflowError`. Preserve existing valid seeded results, error precedence, CLI behavior and report formats; add input-by-input RNG-state regression tests.

- Reject booleans and malformed direct Python API inputs in normal `safety_stock()` and economic order quantity `eoq()` calculations, including nonnumeric values and integers too large for a finite float. Return the established actionable parameter-specific `ValueError` rather than treating `True` as a quantity or leaking `TypeError`/`OverflowError`. Preserve valid calculations, CLI validation and report schemas; add cross-field regression tests.

- Validate direct Python `CostRates` inputs before replay costing: reject booleans masquerading as monetary amounts, strings, `None`, complex values and excessively large integers with the established actionable `ValueError` message instead of accepting `True` or leaking `TypeError`/`OverflowError`. Preserve valid zero, integer and fractional rates, scored costs, CLI settings and report schemas; add cross-field regression tests.


- Reject JSON reports with duplicate object property names (including Unicode-escaped aliases), `NaN`/`Infinity` literals or numeric exponents overflowing to infinity in the reusable GitHub Action. Validate all nesting levels before exposing report outputs, with synthetic injection regressions and real CLI compatibility tests. Inventory calculations, Markdown reports and release versions are unchanged.

- Fail closed when generating release notes from a duplicated version heading, a missing or malformed release date, or an impossible calendar date. Require one unambiguous `## [VERSION] - YYYY-MM-DD` section before producing notes, with offline regression tests. Existing valid release histories and package versions remain unchanged.

- Escape terminal control characters, bidirectional formatting marks, Unicode line separators and hidden format characters in SKU identifiers when rendering Markdown inventory reports. Show stable `[U+XXXX]` labels instead of invisible or reordering text, while preserving original SKU values in machine-readable JSON and retaining existing CR/LF entity formatting. Add regression tests across tables and all affected codepoints.

- Validate `warmup` as an actual integer period count in public `simulate()`, `simulate_periodic()` and `simulate_rss()` replays. Reject booleans and fractional/non-integer counts before processing demand, rather than silently interpreting `True` as one excluded period or raising a slicing error after replay. Preserve valid zero/full-history warmups, negative/out-of-range integer errors and replay scoring; add 45 cross-policy regression cases.

- Reject boolean, string, `None` and other nonnumeric smoothing coefficients in standalone `ses()`, `croston()` and `sba()` calls before reading demand. Previously `True` silently acted as `alpha=1` and invalid `sba()` inputs could raise `TypeError` before Croston validated them. Preserve finite coefficients in `(0, 1]`, existing error messages for out-of-range numeric inputs, forecast results, CLI behavior and release version. Add regression coverage for all three public APIs.

- Guard custom `backtest()` model outputs that are boolean or not usable finite numeric forecasts, including strings, `None`, complex numbers, objects and oversized integers. Return the established indexed `ValueError` instead of interpreting `True` as demand or leaking a `TypeError`/`OverflowError`. Preserve valid forecasts, the existing negative/non-finite errors, CLI behavior, versions and output schemas; add direct API regression tests.

- Reject boolean and non-integer `holdout` values in the public `backtest()` API before processing demand or invoking a forecast method. Previously `True` was silently interpreted as one held-out period and non-integer values could cause unexpected arithmetic or slicing errors. Preserve existing nonpositive/infeasible integer errors, rolling forecast scores, version, and CLI behavior; add direct regression tests.

- Reject non-integer `window` values, including booleans, floats, strings and `None`, in the public `moving_average()` forecasting API before processing demand. Previously `True` silently meant one period and a float could reach slicing and raise `TypeError`. Preserve existing nonpositive integer errors, valid moving averages, report schemas and CLI behavior; add direct API regression tests.

- Reject NaN and infinite forecast errors in all reachable protection intervals of the public `residual_bootstrap_quantile()` API before random draws, with indexed error messages. Preserve missing-interval error precedence, valid signed finite residuals, seeded behavior and ignored intervals; add API regression tests across negative and positive intervals.

- Reject negative, NaN and infinite demand observations and expected demand in the public `bootstrap_safety_stock()` API before any random sampling, including zero-length protection intervals. Report the invalid observation index, preserve existing sample/service/lead-time error priority, valid zero-demand results and seeded reproducibility, and cover the standalone API with parametrized regressions.

- Reject `NaN` and infinite scalar or per-period `reorder_point`, `order_up_to` and `order_quantity` values in all three public inventory replay APIs (`simulate`, `simulate_periodic`, `simulate_rss`) before stock is mutated or scored. Report the original zero-based period for invalid dynamic values, preserve existing checks for nonpositive quantities and all finite policies, and add cross-policy scalar/dynamic regression tests.

- Reject negative and non-finite observations in direct `backtest()` input, including held-out actual demand, before invoking forecast methods. Also reject invalid custom method predictions (negative, NaN or infinite), reporting the original zero-based period; previously both could contaminate MAE, RMSE, MASE or the forecast table. Preserve valid zero and large finite values and add focused regressions.

- Reject empty, negative, NaN and infinite demand histories in the public `naive()` and `moving_average()` forecasting APIs, including invalid observations outside the moving-average window. Report the original zero-based position, preserve valid zero and large finite forecasts, and add focused regression coverage.

- Reject negative, NaN and infinite demand in the public `ses()` forecasting API, with the zero-based invalid observation index. Require at least one demand period instead of failing with an `IndexError`. Preserve valid zero/positive and very large finite demand forecasts; add 13 parameterized and behavioral regressions without changing package versions or releases.

- Validate finite, non-negative demand in the public `coefficient_of_variation()` helper (also when called independently of `demand_profile()`). Previously negative series could yield meaningless negative CV values and NaN/infinity could raise cryptic errors; report the zero-based invalid position consistently with other demand APIs. Empty or zero-only series have no defined CV (`None`). Preserve valid finite demand and include regression tests.

- Test the built wheel as an installed package on Linux, macOS and Windows in isolated virtual environments. Check the installed command, package metadata, PEP 561 `py.typed` marker and a real JSON policy report with the requested holdout, outside the source checkout and without `PYTHONPATH`. Preserve the release version and existing source-distribution checks.

- Reject negative, NaN and infinite demand passed directly to public `croston()` and `sba()` forecasting functions, with the invalid zero-based demand index in `ValueError`. Previously negative values could be skipped as zero periods and non-finite values could contaminate forecasts. Preserve valid zero and positive demand, and add 22 parametrized regression cases.

- Validate finite, non-negative demand observations and finite, meaningful ADI/CV² cutoffs in the public `demand_profile()` API. Previously negative or NaN observations could be silently treated as zero-demand periods, producing misleading smooth/intermittent classifications. Preserve valid classification behavior and add parameterized API regressions.

- Advertise Python 3.14 in package metadata following the successful Linux, Windows and macOS CI compatibility matrix; keep runtime requirements, package version, and released tags unchanged.

- Run the existing Linux, Windows and macOS test matrices under Python 3.14, preserving all earlier version checks and quality gates. Keep package metadata and releases unchanged until the exact-head PR CI succeeds.

- Match required and opt-in cost-column aliases using full Unicode `casefold` rather than simple lowercase, so a case-equivalent ERP label (for example `ſku`) is recognized and conflicting columns are rejected instead of silently ignored. Preserve optional cost-column opt-in rules and existing output files on invalid input; add API and CLI regression tests.

- Reject impossible monthly demand periods with year `0000` (including equivalent Unicode decimal-digit labels), consistently with existing strict validation of ISO calendar dates. Keep years `0001` through `9999` valid, preserve source-line diagnostics, and leave any previously generated report untouched on failure; add API and CLI regression tests.

- Report the actual physical CSV source line for invalid demand values or row widths after quoted multiline fields, including skipped Excel `sep=` preambles, CRLF/gzip exports, and embedded newlines in the header. Preserve the public `parse_rows` record-number behavior for pre-parsed lists, error exit codes, and previously written reports; add parser and real CLI regression tests.

- Include a runnable, synthetic semicolon-delimited Excel `sep=;` example at `examples/regional-excel.csv` (two SKUs, 12 months). Make the README quickstart point to this real file and add API/CLI regression tests so the documented example cannot silently disappear or become invalid.

- Recognize an optional Excel `sep=;` (or another supported single-character `sep=` declaration) on the first CSV line when it agrees with the explicit `--delimiter`. Exclude it from parsed data, preserve source line numbers and quoted headers, and reject contradictory/unsupported hints as data errors before replacing existing reports. Works identically with gzip and selected text encodings; add positive/negative regression cases.

- Add explicit `--delimiter` choices (`comma`, `semicolon`, `tab`, `pipe`) for regional ERP and spreadsheet demand exports. Preserve comma as the default, strict CSV row checks, encoding support, gzip parity, cost columns and analysis semantics. Extend the Python `read_demand` and `analyze_file` APIs, and cover valid sources, quoted fields, malformed rows, unsupported options, CLI, and existing-output safety with regression tests.

- Accept explicitly configured demand CSV text encodings via `--encoding CODEC` in the CLI, Python API, and reusable GitHub Action, including gzip streams. Default UTF-8 BOM behavior is unchanged. Unknown or binary codecs fail as usage error 2; undecodable content fails as input error 3 without replacing saved reports. Add cp1252 and UTF-16 parity and failure-path regressions.

- Read `.csv.gz` demand-history exports directly in the CLI, Python API, and reusable GitHub Action using standard-library gzip text streams (case-insensitive `.gz` suffix). Preserve existing strict CSV, UTF-8 BOM, model inputs, report schemas and file safety. Damaged or truncated gzip inputs return input exit `3` without overwriting existing reports; malformed but decodable CSV remains a data error (`4`). Add parity and error-regression tests.

- Strengthen the reusable GitHub Action's successful-report contract: reject freshly created but malformed JSON, empty/partial Markdown, missing dataset/SKU summaries, duplicate SKU entries and implausible fill rates before returning `succeeded=true` or exposing `report-path`. Preserve the standalone CLI's output, the prior freshness protections and existing files on failures; add synthetic and real end-to-end regression coverage.

- Normalize accepted Unicode decimal digits in monthly `YYYY-MM` periods to canonical ASCII month labels **before** summing demand, recording lead-time periods and building the calendar. Previously `_period_kind` accepted e.g. Arabic-Indic `٢٠٢٦-٠١` but the calendar emitted `2026-01`, silently hiding the observed demand behind a zero-filled month. Add regression tests for Arabic-Indic, Devanagari, Persian and ASCII months, equivalent-month aggregation, real missing months, UTF-8 file reading and a JSON CLI report. Existing integer and date period semantics remain unchanged.

- Reject ragged demand-export CSV records before model calculations: each non-blank row must match the full header width, including auxiliary or opt-in cost columns. Previously excess cells or omitted trailing ignored columns could be silently accepted, concealing faulty source exports. Preserve the existing actionable error for missing required fields, blank-record handling, explicitly empty cells and quoted commas/multiline values. Add parser, standalone CLI and GitHub Action regression checks, including preservation of existing reports on failure.

- Fail closed when the reusable GitHub Action's CLI reports success without creating a **fresh** report: compare the pre-existing output's file identity, size and nanosecond modification time with the post-run output so an old report cannot falsely produce `succeeded=true` or a usable `report-path`. Preserve existing files on failure and accept fresh atomic replacements and first-run outputs; add cross-platform runner regression tests without changing the standalone analysis CLI.

- Harden reusable GitHub Action boundary handling: reject CR/LF/NUL and other terminal controls in CSV paths, report paths and extra arguments before invoking the CLI or creating a report directory, while preserving tabs as normal argument separators. Choose a JSON job-summary Markdown fence longer than any backtick run in untrusted report text, avoiding premature code-block termination. Preserve ordinary inputs, raw JSON and standalone CLI behavior; add failure-path and regression tests.

- Validate every demand observation, including warm-up periods, before running public `(s,Q)`, `(R,S)` and `(R,s,S)` inventory replays. Reject negative, `NaN` and infinite demand with a zero-based period in `ValueError`, avoiding fictitious stock gains, invalid fill rates and non-finite metrics; preserve normal and zero-demand replays and existing option-validation precedence. Add cross-policy regression tests.

- Reject negative and non-finite `lead_time` values in all three standalone inventory replay APIs (`simulate`, `simulate_periodic`, `simulate_rss`) before placing inventory orders. Prevent backdated arrivals and confusing NaN/infinity integer conversions while preserving valid half-up rounding, warm-up behavior and existing error precedence. Add cross-policy regression tests.

- Reject negative and non-finite lead time, review period and observed lead-time values in both public bootstrap safety-stock and forecast-residual APIs before sampling. Report a clear `ValueError` identifying the invalid setting or `lead_times` position instead of silently using invalid intervals; preserve zero-duration results, seeded valid draws, and sample-count validation precedence. Add parameterized regressions and documentation.

- Apply CLI-consistent finite, non-negative demand, variability and duration validation and the `[0.5, 1)` normal cycle-service-level range to public `safety_stock()` / `build_policy()` calls. Reject unsafe negative or non-finite inputs before calculations; at exactly 50% service return a zero safety stock without creating `0 * infinity` from extreme finite protection intervals. Preserve valid replenishment-policy formulas and add parameterized public-API regressions.

- Validate nearest-rank bootstrap `service_level` in the standalone demand and forecast-residual APIs before drawing any samples. Reject zero, negative, above-one, NaN and infinite quantiles with `ValueError` instead of selecting an invalid quantile or raising `IndexError`. Preserve established valid `(0, 1]` quantiles (including 0.3, 0.4 and 1.0), sample-count error precedence, existing CLI policy and report outputs; add parameterized regressions.

- Validate finite and non-negative demand, ordering cost and holding cost in standalone public `eoq()` calls before any early return. Reject `NaN`, infinities and negative costs with `ValueError` to prevent silently invalid EOQ or misleading undefined results; preserve all valid zero-input semantics and numerical-overflow stability. Add parameterized input and boundary regressions.

- Validate public forecast-method parameters directly: reject zero and negative moving-average windows, which otherwise silently select full or incorrect history slices, and reject out-of-range/non-finite SES, Croston and SBA smoothing factors. Match existing `Config` checks, preserve all valid forecasts and report schemas, and add parameterized regression tests for numerical boundaries, no-demand series and API/CLI consistency.

- Validate the standalone `xyz_class()` API against invalid numerical segmentation settings and coefficients of variation, including NaN, infinity, negative CV, zero/reversed cutoffs, and missing-demand calls with invalid thresholds. Apply the same finite `0 < x < y` rule as `Config`, preserve the original X/Y/Z categories for legitimate values, and add parameterized regression coverage for public API callers.

- Harden the standalone `abc_classes()` API: reject negative annual consumption values even when their sum stays finite, and reject non-finite, reversed or out-of-range A/B cumulative-share thresholds before assigning priorities. Previously, negative items could silently distort ABC classes or turn a canceling total into all-C output; the CLI's existing configuration and CSV validation already guarded these cases. Preserve ordinary inputs, all-zero inventories, and overflow-safe finite totals. Add focused regression tests.

- Prevent coefficient-of-variation and Syntetos-Boylan demand-pattern calculations from overflowing on individually finite, large demand observations when the intermediate sum exceeds floating-point range. Normalize by the largest observation only when the original mean computation overflows, preserving ordinary-scale results and existing classifications. Add targeted API regression tests for smooth, intermittent, erratic and lumpy demand, and unchanged zero-demand behavior.

- Prevent effectively unbounded (s, Q) replay loops when very large demand requires many identical lots of a small EOQ. Preserve per-order arithmetic for normal workloads, then aggregate same-time lots in constant time while counting every order. Reject quantities too small to advance the floating-point position and counts beyond reliable numeric precision with controlled data errors (CLI exit 4), keeping existing report files untouched. Add API, warm-up, delayed-arrival, large-batch and CLI regressions (issue #72).

- Stabilize economic order quantity (EOQ) for extreme but finite ordering/holding costs and demand. The original arithmetic remains unchanged when its intermediate value is finite and nonzero; otherwise a log-space fallback recovers any representable positive order quantity, preventing false infinity or zero from intermediate overflow/underflow. Preserve legacy zero/undefined cost behavior, standard EOQ formulas, report schema and ordinary-sized results. Add direct API, pipeline and subprocess CLI regressions.

- Stabilize holdout forecast RMSE and normal safety-stock calculations: scale errors before squaring and use `math.hypot` for demand/lead-time deviations, preventing finite but very large values from turning into `Infinity` and tiny nonzero errors from underflowing to zero. Keep the same forecast selection, normal formulas, public API and JSON schema; add overflow, underflow, zero-error and ordinary-sized regression tests.

- Harden ABC inventory classification against numeric overflow: scale finite per-SKU values before cumulative-share calculations when their total exceeds float range, avoiding silent misclassification of every SKU as A. Reject an overflowing annualized consumption value with an actionable SKU-specific data error (CLI exit 4) before forecasting, preserving any existing output report. Add API and CLI regression tests for large finite values and unchanged normal behavior.

- Fix misleading cost selection on unsorted ERP exports: take each SKU's most recent **period** with a non-empty `unit_cost`, and (with `--cost-columns`) independently select latest-period `order_cost` and `stockout_cost`; use the last non-empty row to resolve ties in the same period. Previously the final CSV row won even if it belonged to an older period, potentially changing ABC, EOQ and replay costs. Support integer, month and date calendars, preserve default opt-in cost-column rules and existing report-on-error safeguards; add parser and CLI regressions.

- Reject duplicate `--class-service-levels` entries after normalizing ABC class names to uppercase. Previously `A=0.99,a=0.8` silently overwrote the intended 99% service target with 80%; now the CLI exits 2 without replacing any existing report. Add regressions for exact, case-insensitive and whitespace-normalized duplicates.

- Bound automatic month and integer calendar expansion to 100,000 periods, rejecting huge gaps with a controlled data error (exit 4) rather than allocating billions of zero-demand observations. Also reject integer period labels longer than 128 digits before numeric conversion. Add library and CLI regressions, including preservation of pre-existing output reports.

- Reject numeric overflow when summing individually finite transaction quantities for the same SKU and period. Avoid propagating `Infinity` into demand histories, forecasts or inventory recommendations; provide an actionable line/SKU/period error (exit 4) and preserve earlier output reports. Library and CLI regressions cover overflow and valid large observations for distinct periods/SKUs.

- Extend clean CSV input error handling to filesystem metadata checks (`exists`/`is_file`) that can fail on restricted or unreliable storage. These now return input exit code 3 without tracebacks or overwriting existing reports, with library and CLI regressions.

- Normalize zero-padded and signed-zero integer-period values before aggregating demand and observed lead times, fixing `KeyError` from accepted inputs such as `01`/`002`. Equivalent integer spellings now share a calendar bucket; month and date handling remain unchanged. Add parser and end-to-end CLI regressions (issue #64).

- Handle CSV input permission errors and other filesystem read failures as clear input errors (CLI exit 3) instead of uncaught tracebacks, while preserving existing report files. Library and CLI regressions cover permission denial, I/O failure and unchanged prior output.

- Reject malformed CSV quoting (unterminated quoted fields and text after closing quotes) before inventory analysis, with an actionable source line and data-error exit code 4. Correctly quoted commas and multiline fields remain supported. Added reader and CLI regressions verifying that existing report files survive invalid input.

- Fail closed on ambiguous ERP/CSV headers for consumed inventory fields: repeated headers (even with case/whitespace differences) and alternative aliases (`quantity`/`qty`/`demand`, `period`/`date`) are rejected with actionable field names and positions instead of silently choosing one and changing forecast inputs. This also covers optional costs and lead times, and opt-in per-SKU cost columns. Non-consumed extra columns remain compatible. Added library and CLI regressions, including preservation of an existing output report on error.

- Rejected non-finite (`NaN`, `Infinity`, `-Infinity`) inventory policy settings that could bypass numeric validation, including lead/review periods, annualization, order coverage, EOQ inputs and ABC-XYZ thresholds. The CLI now exits 2 with an explicit setting name rather than generating invalid estimates; existing report files stay untouched. Added API and CLI regression cases for invalid parameters and normal finite values.

- Hardened Markdown rendering of CSV-supplied SKU identifiers throughout policy, forecast, out-of-sample replay, per-SKU cost and notes sections. Text that looks like Markdown links, HTML or newlines is now displayed literally without corrupting tables or the GitHub Action summary; machine-readable JSON and inventory computations are unchanged. Added direct and CLI regression coverage.

- Prevented false-green reusable Action runs when `args` uses `--help`, `--version`, or abbreviated forms: these can exit successfully without analyzing a CSV, especially if a report already exists. The Action now rejects informational options and abbreviated `--format` / `--output` overrides before any report directories are created or subprocesses run. Added parametrized regressions and end-to-end Action CI checks; standalone CLI help/version remain available.

- The reusable GitHub Action now validates CSV input paths against the caller's `GITHUB_WORKSPACE` before creating report directories or launching the CLI. Absolute paths, workspace traversal, escaping symlinks, stdin and line-break paths fail closed with documented Action outputs; new unit and end-to-end CI checks preserve normal relative-path behavior.

- CI now verifies the installed package from the source distribution contains the PEP 561 `py.typed` marker.

- Source distributions now explicitly include `SECURITY.md` and `CITATION.cff`, and CI verifies both files are present in the built sdist.

- README now links the private vulnerability-reporting guidance in `SECURITY.md` from the development section.

- README now documents how to verify release SHA-256 checksums and GitHub provenance attestations, while noting that historical releases may predate those guarantees.

- Release builds now generate GitHub artifact provenance attestations for the wheel and source distribution, signed through GitHub OIDC/Sigstore and pinned to `actions/attest` v4.2.2 by commit SHA.

- GitHub Actions checkouts now disable persisted Git credentials because CI and release jobs do not push repository changes.

- Release artifacts now include a `SHA256SUMS` file so downloaded wheels and source distributions can be independently verified.

- CI jobs now have explicit conservative timeouts so a hung coverage run, platform test, or packaging step cannot occupy a runner indefinitely.

- The release job now has an explicit timeout so a stuck build, install, release test, or upload cannot occupy a runner indefinitely.

- Built distributions now expose direct links to issues, contributing guidance, documentation, and security alongside the existing homepage and changelog links.

### Changed

- The reusable GitHub Action now rejects explicit report paths that are absolute or resolve outside `GITHUB_WORKSPACE`, matching its documented relative-path contract and preventing accidental writes outside the caller workspace.
- Added a reusable composite GitHub Action that runs the existing CLI with safe argv handling, preserves atomic report writes, exposes `exit-code`/`succeeded`/`report-path`, and is tested end to end on both a real JSON report and a missing-input failure.
- GitHub Actions are pinned to the verified commit SHAs behind `actions/checkout@v7` and `actions/setup-python@v7`, with version comments retained for readable Dependabot updates.
- CI keeps 100% coverage, lint, formatting, mypy and generated-file checks on Python 3.12 while testing Python 3.11 and 3.13 separately without coverage instrumentation; superseded runs for the same PR or branch are cancelled.
- CI now runs the full test suite on Windows and macOS at Python 3.11 and 3.13, in addition to the Linux quality matrix, to exercise OS-sensitive path identity, links and atomic output behavior.

### Fixed

- Input directories are rejected consistently as `InputFileError` before opening them, including on Windows where opening a directory can raise `PermissionError` instead of `IsADirectoryError`.
- File sources embedded in reports use POSIX-style separators, so generated reports and README samples are byte-stable across Windows, macOS and Linux.
- Prevent `--output` from overwriting the input CSV through identical paths, relative aliases, symlinks or hard links; fail closed when file identity cannot be checked. Add regression tests.
- Write report files atomically through a temporary file and `os.replace`, so a failed write or final replacement preserves the previous complete report and cleans up temporary files. Regression tests cover replacement and `fsync` failures, including cleanup after the file handle closes.

## [0.10.0] - 2026-10-16

### Changed

- README "Levels optimised for cost": the table now shows the cost-optimised policy before (plain paths, as in 0.9.0) and after the options of this release (fill floor 0.95, refit paths, both) on the 48-month series and the 24-month example, pinned in `tests/test_optimize.py`, with the conclusion: refit paths make (R, s, S) the cheapest fixed-origin policy on the 48-month series (97.9% / 4,084), robustly across seeds and path counts, and help nothing on the 24-month example, where the heuristics stay cheaper.

### Added

- `OptimizedReplay` is exported from the package (`from inventory_policy_lab import OptimizedReplay`), like the other result types; it was only importable from `inventory_policy_lab.validation`.

- Fill-rate floor for the cost search, opt-in with `--optimize-fill-floor F` (`Config.optimize_fill_floor`, `0 < F <= 1`, needs `--optimize-cost`): only pairs whose expected fill rate on the training demand paths is at least `F` can be picked (refinement included), and a SKU where no pair meets it keeps the heuristic pair. Markdown adds the floor and an expected-fill column; JSON adds `optimize_fill_floor`, `optimized.fill_floor`, `summary.fell_back` and per SKU `expected_fill_rate`, `heuristic_expected_fill_rate`, `feasible`, `fell_back`. API: `expected_outcomes`, `search_levels(..., fill_floor=)`, new `CostSearch` fields. Without it the reports are byte for byte those of 0.9.0 (122 outputs compared) (ADR 0016).
- Result (100 paths, README rates): the floor hardly binds, since the training paths already expect 95% to 100% fill; at 0.99 the out-of-sample fill rate of the optimised policy moves from 88.4% to 90.0% (48-month (s, Q)) and from 90.6% to 91.4% (24-month (s, Q)) at a higher test cost on the 24-month example (20,985 against 18,016), and (R, s, S) does not improve.
- Demand paths that refit the forecast, opt-in with `--optimize-paths refit` (`Config.optimize_paths`, needs `--optimize-cost`): each path rebuilds the training history as its one-step forecasts plus a moving-block bootstrap of their errors (blocks of the rounded cube root of the error count), refits the picked forecast method on it, and adds a resampled one-step error to that refit's forecasts, so the search pays for the uncertainty of the model's level, trend and season. Too-short histories keep the plain paths; failed refits keep the training forecast (counted). Markdown adds one sentence; JSON adds `optimize_paths`, `optimized.paths` and per SKU `paths`, `refit_failures`. API: `Config.optimize_paths`, `OptimizedReplay.paths`, `refit_failures`, `OutOfSampleReport.optimize_paths`, `SkuResult.refit_forecasts`, `refit_failures`, `optimize.bootstrap_histories`, `block_bootstrap`, `block_length`. Test demand never reaches the refits (tested). Without it the reports are byte for byte those of 0.9.0 (ADR 0017).
- Result (100 paths, README rates): 48-month (R, s, S) R = 1 goes from 94.9% / 5,119 to 97.9% / 4,084, below both heuristics and (R, S) at 0.98, and holds with another seed and 200 paths; 48-month (s, Q) improves with seed 0 (96.4% / 5,371) but not robustly (6,901 and 7,162 with seed 1 and 200 paths); on the 24-month example (s, Q) gets worse (20,275 against 18,016) and (R, s, S) improves to 89.5% / 18,387 but stays well above the heuristics. Refit paths add about 1 s on the 48-month series (2.7 s against 1.7 s) and nothing measurable on the 24-month example.

## [0.9.0] - 2026-10-16

### Added

- Cost rates per SKU for the out-of-sample replay (ADR 0014). `--holding-cost-rate RATE` (`Config.holding_cost_rate`) prices holding as a yearly fraction of each SKU's `unit_cost`, so a unit held one period costs `RATE x unit_cost / --periods-per-year` (needs a `unit_cost` column; excludes `--holding-cost`; separate from the EOQ `--holding-rate`). `--cost-columns` (`Config.cost_columns`) reads optional `order_cost` and `stockout_cost` columns, the most recent non-empty value per SKU, which replace `--order-cost` / `--stockout-cost` for that SKU. Markdown adds each SKU's rates to the cost section; JSON adds the settings, `holding_rate_of_unit_cost` / `cost_columns` to `out_of_sample.costs.rates` and `rates` to each SKU. API: `Config.sku_cost_rates`, `Config.per_sku_costs`, `OutOfSampleReport.sku_rates`, `OutOfSampleReport.rates_of`, `SkuHistory.order_cost` / `stockout_cost`, `DemandData.has_order_cost` / `has_stockout_cost`, `read_demand(..., cost_columns=True)`, `parse_rows(..., cost_columns=True)`. Without the new options the Markdown and JSON reports are byte for byte those of 0.8.0 (104 outputs compared).
- Result on the 24-month example (`--test-periods 12 --trend-seasonal --dynamic-levels --bootstrap-source residuals --rolling-origin`, 50 per order, 10 per unit short): with holding at 25% a year of unit cost instead of 1 per unit and month, holding falls by about three quarters and (R, s, S) with a monthly review becomes the cheapest policy in all four columns (6,941 normal fixed, 5,903 residual bootstrap rolling); README "Holding priced per SKU".
- Cost-optimised levels, opt-in with `--optimize-cost` (`Config.optimize_cost`; needs cost rates, `--test-periods` and `--policy sQ` or `RsS`) and `--optimize-samples N` (default 100, at least 10): for each SKU the safety stock and the order quantity (so `s` and `S = s + Q`) are searched on a bounded grid (heuristic, -1 to 3 sigma, minus 10% to 100% of the forecast over `L + R`; quantity heuristic or 0.5 to 12 periods of mean training demand; then quarter-sigma refinement) for the lowest expected cost of the test window, estimated on demand paths built from training only (training forecast plus resampled one-step training errors) and replayed from the state the normal policy reaches at the end of training. The pick is then replayed on the real test (fixed origin). Markdown: "Cost-optimised levels" section; JSON: settings and `out_of_sample.optimized`; API: `OptimizedReplay`, `SkuOutOfSample.optimized`, `OutOfSampleReport.optimized_cost`, `optimized_sku_cost`, `optimized_totals`, module `inventory_policy_lab.optimize`. Test demand never reaches the search (tested). Without the option the reports are byte for byte those of 0.8.0 (ADR 0015).
- Result (`--test-periods 12 --trend-seasonal`, 50 / 1 / 10, fixed origin, README "Levels optimised for cost"): the search cuts the expected cost on training paths by 33% to 41% but beats both heuristics out of sample only for (s, Q) on the 24-month example (18,016 against 21,371 normal and 19,212 bootstrap); it is worse on 48-month (s, Q) and 24-month (R, s, S), with fill rates of 86% to 95%. (R, S) R = 1 at service level 0.98 is the cheapest on the 48-month series (4,474, 98.5% fill rate). Search time about 0.5 s per SKU at 100 paths.

## [0.8.0] - 2026-10-15

### Added

- Cost of the out-of-sample replay, opt-in with `--order-cost`, `--holding-cost` and `--stockout-cost` (`Config.order_cost`, `holding_cost`, `stockout_cost`; need `--test-periods`): every replay of the test periods (normal and bootstrap, fixed and rolling origin) is priced at C per order placed, C per unit on hand at the end of a period, and C per unit of demand not served from stock in its period (backordered); a rate left out counts as 0. The Markdown report adds a "Cost of the test periods" section with totals per method and origin (orders, unit-periods held, units short, ordering, holding, stockout, total) and the same per SKU; JSON adds the rates to the settings and `out_of_sample.costs`. The rates do not change the policy (the EOQ inputs stay separate). Without them the Markdown and JSON reports are byte for byte those of 0.7.0 (ADR 0012).
- API: `CostRates`, `CostBreakdown`, `replay_cost`, `total_cost`, `Config.cost_rates`, `OutOfSampleReport.costs`, `OutOfSampleReport.cost`, `OutOfSampleReport.sku_cost`.
- Periodic-review (R, s, S) policy, opt-in with `--policy RsS` (`Config.policy = "RsS"`, a whole `--review-period` of at least 1): every R periods the position is reviewed and, only when it is at or below `s = D x (L + R) + SS` (the same level and safety stock as the other policies), an order brings it up to `S = s + Q`. Works with static and dynamic levels, normal and bootstrap safety stock (demand or residuals), the fixed and rolling origins and `--refit-every` (refits decide `s` and `Q`). Markdown: `Reorder level (s)`, `Order qty (Q = S - s)`, `Review (R)`; JSON: `kind: "RsS"`, `reorder_point`, `order_quantity`, `order_up_to`. API: `simulate_rss`; `replay_policy` and `build_policy` accept the kind. Reports of (s, Q) and (R, S) are unchanged (ADR 0013).
- Results with the example rates 50 per order, 1 per unit-month held and 10 per unit short (out of sample, `--trend-seasonal --dynamic-levels --bootstrap-source residuals --rolling-origin`, README "Policies compared by cost"): on the 48-month series (R, S) with a monthly review is cheapest in every column (3,066 normal fixed, 2,482 residual bootstrap rolling) and (R, s, S) R = 1 costs 5,801 and 4,404, because ordering up to `s + Q` holds about one lot more; on the 24-month example, where the frozen forecasts leave (R, S) at 90.9% fill rate, (R, s, S) R = 1 reaches 99.3% and is cheapest with a fixed origin (15,576 against 17,313), while with a rolling origin (R, S) wins at 10 per unit short (13,405 against 15,818) and (R, s, S) above about 24. A three-month review is never cheapest at these rates.

## [0.7.0] - 2026-10-15

### Changed

- Faster damped Holt and Holt-Winters fits, with identical results: `fit_holt_damped` and `fit_holt_winters` keep recent fits in a bounded cache keyed on the exact history, and on a miss score each parameter set once over the whole history, which gives the best fit of every prefix at the cost of one grid search (the backtest, the residual errors and the rolling origins fit those prefixes again and again). On the 48-month series, `--test-periods 12 --trend-seasonal --bootstrap-source residuals --rolling-origin` goes from 10.1 s to 0.22 s, and the fixed origin from 1.0 s to 0.15 s. Markdown and JSON reports are byte for byte those of 0.6.0, checked against the plain grid search kept in the tests (ADR 0010).

### Added

- `--refit-every K` (`Config.refit_every`, default 1; needs `--rolling-origin`): the rolling origin refits only at the start of every K-th test period, and each refit decides its own period and the next K - 1 (same safety stock and order quantity; with dynamic levels, its forecasts 1 to K steps ahead). K = 1 gives the 0.6.0 reports byte for byte; K at least the test window reproduces the fixed origin; no refit sees a period it decides (tested). JSON: `refit_every` in the settings when it is not 1; API: `OutOfSampleReport.refit_every` (ADR 0011).
- Results with `--test-periods 12 --trend-seasonal --bootstrap-source residuals`, K = 1, 3, 6, 12: the fill rate never rises with K. On the 48-month series, (R, S) R = 1 with the normal formula serves 100% at every K with stock from 149.3 (monthly) to 105.5 (yearly); with the residual bootstrap it goes from 99.4% to 95.4%. On the 24-month example, (s, Q) normal with a quarterly refit (K = 3) keeps 97.7% of fill rate against 99.8% monthly and 94.4% fixed, with the same stock as monthly. Each run takes 0.13 to 0.33 s.
- API: `fit_cache_info()`, `clear_fit_cache()`, `FitCacheInfo`.

## [0.6.0] - 2026-10-15

### Added

- Rolling-origin out-of-sample replay, opt-in with `--rolling-origin` (`Config.rolling_origin`, needs `--test-periods`): at the start of every test period each SKU is refitted, with the same steps as on train, on the periods before it only (training plus the test periods already observed), and its safety stock, level and order quantity decide the end of that period. It is reported next to the fixed-origin replay of ADR 0005, which is unchanged; both enter the test from the same stock and share the first decision. No leak, tested two ways: no out-of-sample fit ever receives the period it decides, and zeroing later test periods leaves the earlier decisions unchanged (ADR 0009).
- `simulate` accepts one order quantity per period. API: `RollingReplay`, `SkuOutOfSample.rolling`, `SkuOutOfSample.rolling_replay`, `OutOfSampleReport.rolling_origin`, `OutOfSampleReport.rolling_totals`.
- Markdown: a "Rolling origin" table (fixed / rolling) and the forecasts picked at the origins per SKU. JSON, only with the option: `rolling_origin` in the settings and in `out_of_sample` (summary and, per SKU and method, `forecast_methods`, `safety_stocks`, `reorder_points` or `order_up_to_levels`, `order_quantities`, `out_of_sample`). Without it the Markdown and JSON reports are unchanged, byte for byte.
- Results (out of sample, `--trend-seasonal --bootstrap-source residuals`): on the 24-month example the rolling origin raises the fill rate of (s, Q) from 94.4% to 99.8% (normal, 5% more stock) and from 92.2% to 98.5% (residual bootstrap, 6% less stock), and of (R, S) dynamic R = 1 from 90.9% to 97.3% and from 88.5% to 96.0%. On the 48-month series it mostly buys stock: the normal (R, S) stays at 100% with 42% more stock, and the residual bootstrap under (R, S) goes from 95.4% to 99.4% with stock from 13.1 to 36.4 units.

## [0.5.0] - 2026-10-15

### Added

- Bootstrap of forecast residuals, opt-in with `--bootstrap-source residuals` (`Config.bootstrap_source`; the default stays `demand`): the bootstrap resamples the rolling-origin errors of the picked forecast over the protection interval `L + R` (each from a forecast refitted on the periods before its origin, from origin 2) instead of demand per period, so a trend or season the forecast follows is not counted as uncertainty. It applies to `--safety-stock bootstrap` and to the bootstrap replay of `--test-periods`, where only training periods are used (tested by replacing the test periods with zeros). Without enough history for any error the SKU falls back to the demand bootstrap, with a note; the report lists how many errors each SKU used (ADR 0008).
- Safety stock per period, opt-in with `--period-safety-stock` (`Config.period_safety_stock`, needs `--dynamic-levels` and the residual bootstrap): with a damped Holt or Holt-Winters forecast, each period gets `SS(t) = q x D(t) x (L + R)`, with `q` the bootstrap quantile of the relative forecast errors, so the levels follow the season without counting it twice. SKUs with a level forecast keep one safety stock, with a note.
- API: `interval_forecast_errors`, `residual_bootstrap_quantile`, `period_safety_stocks`, `interval_demands`, `protection_periods`; `dynamic_levels` accepts one safety stock per period; `SkuResult.safety_stocks`, `SkuResult.next_safety_stocks`, `PolicyReplay.test_safety_stocks`, `OutOfSampleReport.bootstrap_source`.
- JSON, only with the new options: `bootstrap_source` and `period_safety_stock` in the settings, `safety_stocks` and `next_safety_stocks` in the policy, `test_safety_stocks` out of sample. Without them the Markdown and JSON reports are unchanged, byte for byte.
- Results (out of sample, bootstrap): on the 48-month synthetic series, (R, S) with dynamic levels and R = 1 goes from 89.3% fill rate and 22 stockout periods (demand bootstrap) to 95.4% and 18 (residuals) and 96.3% and 16 (per period); the trending item from a safety stock of 0 and 78.4% to 22.0 units and 93.3%. The normal formula still does better there (100%). On the 24-month example with 12 training months the residual bootstrap is worse in every policy (for (s, Q), 94.6% to 92.2% with 37% more stock), so it stays opt-in.

## [0.4.0] - 2026-10-14

### Added

- Periodic-review, order-up-to policy, opt-in with `--policy RS` (`Config.policy`): the position is reviewed every `--review-period R` periods (a whole number of at least 1) and an order brings it back up to `S = D x (L + R) + SS`, the reorder-point formula with the same safety stock. Works with the normal and bootstrap safety stock and with the in-sample and out-of-sample replays. The Markdown policy table shows `Order-up-to (S)` and `Review (R)`; the JSON policy has `kind`, `order_up_to`, and null `reorder_point` and `order_quantity` (ADR 0007).
- Dynamic levels, opt-in with `--dynamic-levels` (`Config.dynamic_levels`, needs `--trend-seasonal`), for both policies: the level used at the end of period `t` is the mean forecast of the next `L + R` periods x (L + R) + SS, so a seasonal forecast moves s or S month by month instead of one level for the year. Out of sample the test levels are the training fit's forecasts 1 to N steps ahead, so the test periods cannot leak into them (tested). JSON: `levels`, `next_levels` and, out of sample, `test_levels`.
- API: `simulate_periodic`, `replay_policy`, `dynamic_levels`, `SmoothingFit.calendar_forecasts`, `Policy.kind`, `Policy.order_up_to`, `SkuResult.levels`, `SkuResult.next_levels`, `PolicyReplay.test_levels`, `OutOfSampleReport.policy`; `simulate` accepts one reorder point per period.
- JSON settings: `policy` and `dynamic_levels` (always present). Without the new options the Markdown report is unchanged.
- Results (out of sample, normal safety stock): on the 48-month synthetic series, (R, S) with dynamic levels reaches 100% fill rate with no stockout period and 105.5 units of average stock, against 99.6% and 289.0 for the static (s, Q) with Holt-Winters; dynamic levels alone cut (R, S) stock by about 25%. The bootstrap does worse with (R, S) (85.5% static, 89.3% dynamic). On the 24-month example the dynamic levels change nothing (no seasonal model with 12 training months), and (R, S) with R = 1 gives 90.9% fill rate with 32% less stock than (s, Q) at 94.4%.

## [0.3.0] - 2026-10-14

### Added

- Trend and seasonal forecasts, opt-in with `--trend-seasonal` (`Config.trend_seasonal`): damped Holt and additive and multiplicative Holt-Winters with a damped trend join the backtest of smooth and erratic SKUs, after the level methods, and are picked by the same lowest-MASE rule. Standard library only. Parameters come from a grid search on the squared one-step errors of the history each fit sees, so neither the holdout nor the `--test-periods` window can leak into them. A model is not a candidate without enough history (damped Holt: 4 periods before the first holdout origin; Holt-Winters: two full seasons; multiplicative: demand in every period). When one is picked, the policy uses its mean forecast over the protection interval `L + R`. API: `holt_damped`, `holt_winters`, `fit_holt_damped`, `fit_holt_winters`, `holt_damped_fit`, `holt_winters_fit`, `SmoothingFit`, `FitError` (ADR 0006).
- `--season-length M` (`Config.season_length`), the Holt-Winters season, by default `--periods-per-year` when it is a whole number; it is a usage error without `--trend-seasonal`.
- JSON: `trend_seasonal` and `season_length` in the settings (always present; `season_length` is null without the option), and `parameters` in a SKU's forecast when a smoothing model is picked. The Markdown report adds a settings line and backtest columns only with the option.
- Results: on the synthetic 24-month example with `--test-periods 12`, the out-of-sample results do not change (fill rate 94.4% normal, 94.6% bootstrap; SKU-003 82.9% / 94.4%, SKU-004 79.7% / 67.7%): 12 training months are too few for Holt-Winters, and damped Holt loses SKU-004's training holdout. On the full history damped Holt is picked for SKU-003 and SKU-009 (all-SKU replayed fill rate 99.4% to 99.5%). On a 48-month synthetic series with known trend and seasonality, the out-of-sample fill rate goes from 97.5% to 99.6% (normal) and from 96.6% to 97.6% (bootstrap), with 52% and 14% more average stock.
- Compatibility: without `--trend-seasonal` the candidates, picks and Markdown output are those of 0.2.0.

## [0.2.0] - 2026-10-14

### Added

- Bootstrap safety stock (`--safety-stock bootstrap`, `--bootstrap-samples`, `--seed`; `bootstrap_safety_stock` in the API): the service-level quantile of protection-interval demand resampled from each SKU's own history, with lead times drawn from the observed ones, instead of the normal formula. Seeded per SKU, so reports are reproducible. On the synthetic example the lumpy SKU-012 goes from 72.5% to 100% replayed fill rate and total average stock falls from 1,257.5 to 1,065.4 units (in-sample; see ADR 0004).
- `safety_stock_method` in the JSON policy of each SKU and `safety_stock_method`, `bootstrap_samples` and `seed` in the JSON settings.
- Out-of-sample replay (`--test-periods N`; `Config.test_periods`, `out_of_sample_replay`, `train_history`, `OutOfSampleReport` in the API): each SKU is fitted on all but the last N periods (ABC, pattern, forecast pick, sigma, lead times observed in training, bootstrap draws) and the normal and bootstrap policies are both replayed, scoring the training periods (in-sample) and the last N (out-of-sample) separately, in a new report section and an `out_of_sample` JSON key. On the synthetic example with 12 test periods, the fill rate falls from 98.8% to 94.4% (normal) and from 99.9% to 94.6% (bootstrap), so the bootstrap's in-sample lead almost disappears out of sample, while it still holds about 20% less stock (ADR 0005).
- `simulate(..., warmup=k)` replays the first k periods without scoring them; `SkuHistory.lead_time_periods` dates each observed lead time by its row. `test_periods` in the JSON settings.

### Changed

- Development: Ruff 0.17.0 (Dependabot PR #2, hashed lock regenerated).

## [0.1.0] - 2026-10-09

First public version (alpha).

### Added

- Reader for long-format demand CSVs (`sku`, `period`/`date`, `quantity`, optional `unit_cost` and `lead_time`): `YYYY-MM`, `YYYY-MM-DD` or integer periods, duplicate rows summed, gaps after an item's first period filled with zero demand, clear errors for missing columns, invalid numbers, negative values and mixed period formats.
- ABC classification by annual consumption value (or annual units without unit costs) and XYZ classification by coefficient of variation, both with configurable thresholds, and the ABC-XYZ matrix.
- Demand-pattern classification after Syntetos, Boylan & Croston (2005): ADI and CV² with the 1.32 / 0.49 cut-offs (smooth, erratic, intermittent, lumpy).
- Forecasting methods: naive, moving average, simple exponential smoothing, Croston and the Syntetos-Boylan approximation (SBA). A rolling one-step holdout backtest reports MAE, RMSE, bias and MASE (Hyndman & Koehler, 2006), and the method with the lowest MASE is picked per SKU. Intermittent and lumpy SKUs are scored with SES, Croston and SBA only (ADR 0002).
- Policy per SKU: safety stock and reorder point for a target cycle service level with `statistics.NormalDist`, demand and lead-time variability, and a review period added to the protection interval; per-class service levels; EOQ when an ordering cost and a holding rate are given.
- Replay of the demand history under the resulting (s, Q) policy with backorders: fill rate, stockout periods, average stock on hand, orders placed and the largest backorder (ADR 0003).
- `inventory-policy-lab` command (also `python -m inventory_policy_lab`) with Markdown and JSON output, `--output`, documented exit codes (2 usage, 3 input file, 4 invalid data, 5 history too short), and a Python API (`analyze_file`, `analyze`, `read_demand`, the methods and formulas).
- Synthetic, seeded example dataset (`examples/demand_synthetic.csv`, `scripts/generate_example.py`), a hand-checked worked example (`examples/worked_example.csv`, verified in `tests/test_worked_example.py`) and an ABC Pareto chart drawn as SVG with the standard library (`docs/abc-pareto.svg`).
- README samples generated from real runs and checked by the test suite; CI on Python 3.11, 3.12 and 3.13 with tests, 100% line and branch coverage, Ruff and strict mypy; a release workflow that builds and tests the sdist and wheel.

[Unreleased]: https://github.com/rodrix91/inventory-policy-lab/compare/v0.10.0...HEAD
[0.10.0]: https://github.com/rodrix91/inventory-policy-lab/compare/v0.9.0...v0.10.0
[0.9.0]: https://github.com/rodrix91/inventory-policy-lab/compare/v0.8.0...v0.9.0
[0.8.0]: https://github.com/rodrix91/inventory-policy-lab/compare/v0.7.0...v0.8.0
[0.7.0]: https://github.com/rodrix91/inventory-policy-lab/compare/v0.6.0...v0.7.0
[0.6.0]: https://github.com/rodrix91/inventory-policy-lab/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/rodrix91/inventory-policy-lab/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/rodrix91/inventory-policy-lab/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/rodrix91/inventory-policy-lab/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/rodrix91/inventory-policy-lab/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/rodrix91/inventory-policy-lab/releases/tag/v0.1.0
