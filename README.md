# BIST Factor Investing Project

This repository contains a reproducible EC581 factor-investing project on Turkish equities. The completed analysis studies Han, Zhou, and Zhu's trend-factor idea and adapts it to BIST stocks using four factors: ROE, P/E, 12-month momentum, and a BIST100-based trend signal.

The submission-ready project is the frozen baseline under `data/`, `results/`, `figures/`, and `presentation/`. A separate official-BIST/DataStore exploration is kept as an experimental appendix only; it is not required to reproduce the submitted findings.

## Submission-Ready Run

The final reproducible run uses:

- Frozen adjusted daily price data in `data/raw/yahoo_daily_prices.csv`.
- Frozen public financial-statement data in `data/raw/yahoo_fundamentals_long.csv`.
- BIST100 (`XU100`) as the benchmark and trend-regression index.
- Turkish stock columns only for factor portfolios and Backtrader trading.
- Month-end signals, cross-sectional winsorization, z-scores, and next-month return alignment.

The main script is:

```powershell
py src\run_project.py
```

It reads frozen CSV files and regenerates:

- `data/processed/`
- `results/`
- `figures/`
- `presentation/bist_factor_project_presentation.pdf`

## Reproduce

From a fresh Python environment:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install --upgrade pip
py -m pip install -r requirements.txt
py src\run_project.py
```

No data download is required for the completed baseline. The instructor can run the code from the frozen CSV files and reproduce the saved outputs.

## Key Results

The completed baseline selected `composite_all4`, the equal-weight combination of ROE, P/E, momentum, and trend.

| Result | Value |
| --- | ---: |
| Base vectorized top-10 Sharpe | `1.28` |
| Best vectorized trial | `equal_all_top15_no_regime` |
| Best vectorized Sharpe | `1.47` |
| Backtrader base final value | `3,078,262 TL` |
| Backtrader base simple return | `207.83%` |
| Backtrader base max drawdown | `23.84%` |
| Regime plus stop/take-profit final value | `1,921,929 TL` |
| Monte Carlo p-value | `0.9045` |

The results are economically interesting, but the Monte Carlo p-value means we should not claim statistically strong stock-selection skill. The final investment judgment is cautious.

## What We Tried

The project tested:

- Equal-weight, price/trend, trend-heavy, and quality/value factor composites.
- Top-5, top-10, and top-15 selection thresholds.
- BIST100 regime filtering.
- Stop-loss and take-profit rules.
- Walk-forward parameter selection.
- Bootstrap and random-portfolio Monte Carlo robustness checks.

The regime filter and stop/take-profit variant reduced drawdown but did not improve final wealth. Price/trend-only variants did not dominate the full four-factor composite.

## Experimental Official-BIST Appendix

The `data_bist/` and `src/*bist*.py` files document an experimental attempt to move from the Yahoo-based baseline to official Borsa Istanbul inputs. This work is not part of the final submitted result because the required BIST DataStore monthly valuation-ratio files could not be downloaded during the project window.

What was completed experimentally:

- Official BIST public bulletin prices were frozen locally.
- Public BIST index closes were frozen locally.
- A parser was written for BIST DataStore monthly ratio files.
- The runner was changed so it does not silently mix BIST prices with Yahoo fundamentals.

What remains missing for a true official-BIST rerun:

- `data_bist/raw/bist_monthly_ratios.csv`, built from BIST DataStore monthly ratio files such as `degoran_M_YYYYMM.zip`.
- Ideally, official adjusted BIST prices to avoid dividend/split distortions in momentum and trend signals.

The earlier hybrid test using BIST prices plus Yahoo fundamentals is preserved only as a rejected local experiment under `archive/legacy_bist_price_yahoo_fundamentals/`.

## Documentation

- [Project report](docs/PROJECT_REPORT.md)
- [Reproducibility guide](docs/REPRODUCIBILITY.md)
- [Data dictionary](docs/DATA_DICTIONARY.md)
- [Submission checklist](docs/SUBMISSION_CHECKLIST.md)
- [GitHub readiness note](docs/GITHUB_READINESS.md)
- [Frozen-input hash manifest](docs/repository_manifest.csv)

## Main Limitations

- Public fundamental history is incomplete for some Turkish stocks.
- The baseline universe may contain survivorship bias.
- Exact public financial-statement release dates are proxied with fixed lags.
- Transaction costs are set to zero because the assignment requires zero commission.
- The Monte Carlo test is a useful diagnostic, but it is not a full model of liquidity, sector exposure, turnover, or transaction costs.

## Final Submission Note

Before final submission, fill `project.group_participants` in `config/project_config.yaml`, rerun `py src\run_project.py`, and confirm that `results/project_audit_checklist.csv` contains only `OK` statuses.
