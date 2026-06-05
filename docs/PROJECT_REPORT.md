# Project Report

## Objective

Implement a Turkey/BIST factor-investing strategy aligned with the project PDF and instructor requirements. The strategy combines ROE, P/E, 12-month momentum, and a BIST100-based trend factor. Backtests use Backtrader with `1,000,000 TL` initial capital, `100,000 TL` fixed cash sizing per trade, zero commission, and market orders.

## Paper Adaptation

Han, Zhou, and Zhu combine moving-average information across horizons to forecast returns. This project adapts that idea to Turkey:

1. Compute moving-average deviations for BIST100 (`XU100`).
2. Regress next-month BIST100 returns on those deviations.
3. Drop non-significant variables at the configured significance level.
4. Apply the retained coefficients to Turkish stocks.
5. Combine trend with ROE, P/E, and momentum.

The completed baseline retained `mad_1000` with coefficient `0.023998` and p-value `0.000757`.

## Completed Baseline Data

The completed baseline is frozen under `data/raw/`:

- `yahoo_daily_prices.csv`: `463,502` daily Turkish equity and index price rows across `77` tickers from `2000-01-04` to `2026-05-26`.
- `yahoo_fundamentals_long.csv`: `75,320` public financial-statement observations across `73` tickers.
- `universe.csv`: stock and index roles.

The baseline uses the configured Turkish equity universe. Index columns such as `XU100`, `XU030`, `XBANK`, and `XUSIN` are excluded from stock portfolios.

## Signal Process

1. Resample prices to month end.
2. Calculate momentum as `P_t / P_{t-12} - 1`.
3. Calculate ROE from net income and equity.
4. Calculate positive P/E from price and EPS.
5. Fit the BIST100 trend regression and apply retained coefficients to stocks.
6. Winsorize cross-sections and compute z-scores.
7. Use month `t` signals only for month `t+1` returns and subsequent Backtrader orders.

## Required Analyses

The repository saves:

- Portfolio-sort FMPs: top quintile minus bottom quintile.
- Cross-sectional-regression FMPs.
- Raw IC and rank IC.
- Common-start-date comparisons.
- Selected-date FMP weights.
- Backtrader trades, orders, positions, returns, equity curves, and metrics.
- Improvement tests, bootstrap output, Monte Carlo output, and walk-forward validation.

## Results

| Test | Result |
| --- | ---: |
| Base vectorized top-10 Sharpe | `1.28` |
| Best vectorized trial | `equal_all_top15_no_regime` |
| Best vectorized Sharpe | `1.47` |
| Backtrader base final value | `3,078,262 TL` |
| Backtrader base simple return | `207.83%` |
| Backtrader base Sharpe analyzer | `0.30` |
| Backtrader base max drawdown | `23.84%` |
| Regime plus stop/take-profit final value | `1,921,929 TL` |
| Regime plus stop/take-profit Sharpe analyzer | `0.37` |
| Regime plus stop/take-profit max drawdown | `18.03%` |
| Monte Carlo p-value | `0.9045` |

## What We Tried

The project tested:

- Equal-weight ROE, P/E, momentum, and trend.
- Momentum/trend-only, trend-heavy, and quality/value composites.
- Top-5, top-10, and top-15 selection thresholds.
- A BIST100 regime filter.
- Stop-loss and take-profit rules.
- Walk-forward parameter selection.
- Bootstrap and random-portfolio Monte Carlo diagnostics.

## What Did Not Work

- The BIST100 regime filter reduced average vectorized Sharpe from `1.09` without the filter to `0.77` with the filter.
- Stop-loss and take-profit rules reduced Backtrader final wealth. They lowered drawdown but did not improve the main return objective.
- Price/trend-only variants did not dominate the four-factor composite.
- Monte Carlo random portfolios frequently matched or exceeded the base strategy Sharpe, producing p-value `0.9045`.

## Interpretation

The backtest is economically interesting but does not prove durable stock-selection skill. The Monte Carlo test is deliberately conservative and imperfect: it preserves the monthly position count but does not fully model liquidity, sector exposure, turnover, holding persistence, or transaction costs. Even with that caveat, `0.9045` is too high to claim statistical strength.

The honest conclusion is cautious. The strategy is suitable for further research, not real-money deployment in its current form.

## Experimental Official-BIST Appendix

The official-BIST pipeline is retained as an experimental appendix, not as a submitted result:

- Public bulletin prices and public index closes are frozen under `data_bist/raw/`.
- The price freeze contains `1,216,158` rows, `727` stock tickers, and `4` index tickers from `2016-01-04` to `2026-05-26`.
- A parser was prepared for BIST DataStore monthly valuation-ratio files such as `degoran_M_YYYYMM.zip`.

A true official-BIST four-factor rerun was not completed because the required DataStore monthly ratio ZIP files could not be downloaded during the project window. The earlier hybrid experiment is preserved under `archive/legacy_bist_price_yahoo_fundamentals/` and must not be presented as final because it mixed BIST prices with Yahoo fundamentals.

## Future Directions

- Obtain BIST DataStore monthly valuation-ratio files and adjusted closing prices if access becomes available.
- Use historical index constituents or another point-in-time universe to reduce survivorship bias.
- Add realistic slippage, spread, liquidity, and turnover analysis as a separate research layer while retaining the zero-commission assignment run.
- Strengthen robustness tests with sector-neutral, liquidity-matched, and block-bootstrap null models.
