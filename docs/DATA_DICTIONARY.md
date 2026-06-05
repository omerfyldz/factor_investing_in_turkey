# Data Dictionary

## Completed Baseline Inputs

| File | Purpose |
| --- | --- |
| `data/raw/yahoo_daily_prices.csv` | Frozen daily equity and index OHLCV data used by the completed baseline. |
| `data/raw/yahoo_fundamentals_long.csv` | Frozen public financial-statement observations used for ROE and P/E. |
| `data/raw/yahoo_info_snapshot.csv` | Public metadata snapshot. |
| `data/raw/universe.csv` | Ticker, source symbol, and stock/index role. |

## Experimental Official-BIST Inputs

These files support the optional official-BIST appendix. They are not required to reproduce the completed baseline.

Official source endpoints:

- Public equity bulletins: `https://www.borsaistanbul.com/data/thb/YYYY/MM/thbYYYYMMDD1.zip`
- Public index closes: `https://borsaistanbul.com/graphic.php?veriTuru=endeks-graphic&indexCode=XU100`
- DataStore monthly ratio metadata: `https://datastore.borsaistanbul.com/api/product-type/100465/products?page=1&page-size=100`

| File | Purpose |
| --- | --- |
| `data_bist/raw/bist_public_daily_prices.csv` | Official BIST public bulletin equity prices plus public index closes. |
| `data_bist/raw/bist_index_daily.csv` | Frozen public BIST index closes. |
| `data_bist/raw/universe.csv` | All common-stock `.E` rows found in the frozen bulletins plus index roles. |
| `data_bist/raw/bist_bulletin_download_log.csv` | Per-date bulletin download audit. |
| `data_bist/raw/bist_price_quality_report.csv` | Frozen BIST price row and ticker counts. |
| `data_bist/raw/bist_datastore_monthly_ratio_manifest.csv` | DataStore metadata manifest for monthly valuation-ratio products. |
| `data_bist/raw/bist_monthly_ratios.csv` | Missing experimental ROE/P/E input. It would be generated only if DataStore ratio files became available. |

## Baseline Price Columns

| Column | Meaning |
| --- | --- |
| `date` | Trading date. |
| `ticker` | Internal ticker code. |
| `open`, `high`, `low`, `close` | Daily prices. |
| `volume` | Daily traded volume. |

## Experimental BIST Monthly Ratio Columns

`src/build_bist_datastore_ratios.py` generates:

| Column | Meaning |
| --- | --- |
| `date` | Month-end ratio date. |
| `ticker` | BIST ticker code. |
| `roe` | Last-four-quarter net profit divided by equity. |
| `pe` | Positive BIST F/K field. |
| `market_value_thousand_tl` | Market value in thousand TL. |
| `net_profit_ttm_thousand_tl` | Net profit over the last four quarters. |
| `equity_thousand_tl` | Equity. |
| `dividend_yield_pct` | Dividend yield. |
| `pbv` | Price-to-book ratio. |
| `source_file` | DataStore source file. |

## Processed Panels

| File | Purpose |
| --- | --- |
| `data/processed/monthly_close.csv` | Month-end prices. |
| `data/processed/monthly_returns.csv` | Monthly returns. |
| `data/processed/roe_panel.csv` | ROE cross-sections. |
| `data/processed/pe_panel.csv` | P/E cross-sections. |
| `data/processed/factor_raw_long.csv` | Raw factor observations. |
| `data/processed/factor_zscores_long.csv` | Winsorized standardized factors and composites. |
| `data/processed/xu100_monthly_ma_deviations.csv` | BIST100 moving-average deviation regressors. |

## Look-Ahead Rule

Factor values observed at month `t` are paired with returns and trades at month `t+1`. The completed baseline applies this rule. The experimental official-BIST ratio builder would preserve the same rule if DataStore ratio files became available.
