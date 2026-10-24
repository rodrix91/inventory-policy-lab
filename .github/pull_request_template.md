## Summary

- What changed and why.

## Analytical impact

- [ ] No formula, forecasting method, policy rule, or reported metric changed.
- [ ] If analytical behavior changed, the method/reference and expected impact are documented.

## Checks

- [ ] `python -m pytest` passes.
- [ ] Coverage remains at 100% line and branch.
- [ ] `ruff check .` and `ruff format --check .` pass.
- [ ] `mypy` passes.
- [ ] Generated files and README samples are refreshed when affected.
- [ ] New formulas or methods include a hand-checked or otherwise independently justified test.

## Data and compatibility

- [ ] No secrets or confidential company data are included.
- [ ] Existing behavior remains unchanged unless the PR explicitly documents the intended change.

## Notes

Keep changes focused and reviewable. Preserve existing history and design decisions.
