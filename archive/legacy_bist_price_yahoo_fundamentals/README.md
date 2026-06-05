# Legacy Hybrid BIST Experiment

This archive preserves an exploratory run that used:

- Official BIST public bulletin prices.
- Public BIST index closes.
- Copied frozen Yahoo fundamentals for ROE/P/E.

It was useful as a price-source sensitivity check, but it is not part of the final submitted strategy. The hybrid design was rejected because it mixed sources and used unadjusted public bulletin prices.

Saved exploratory metrics included:

- Base Backtrader final value: `2,812,164 TL`.
- Base Backtrader Sharpe analyzer: `0.536`.
- Regime plus stop/take-profit final value: `2,092,917 TL`.
- Regime plus stop/take-profit Sharpe analyzer: `0.762`.
- Monte Carlo p-value: `0.7595`.

Compact result files are tracked under `summary/`. The larger generated folders
remain local and are ignored to avoid duplicating non-final outputs in the
submission repository.

Do not present these numbers as final findings.
