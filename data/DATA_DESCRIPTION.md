# S&P 500 Factor-Investing Dataset — Data Description

**Course:** EC581 — Algorithmic Trading and Quantitative Strategies (Boğaziçi University)
**Purpose:** Raw historical data for a student **factor-investing** project.
**Data vendor:** [Tiingo](https://www.tiingo.com/) (End-of-Day prices + Fundamentals add-on).
**Built:** June 2026. **Price history:** ~20 years.

> This dataset deliberately ships **raw** data only. No ratios, factors, z-scores, or
> signals are pre-computed — *you* decide which variables to use and how to combine
> them. The one thing that **is** handled for you is **point-in-time correctness
> (no look-ahead bias)** — see the section of the same name below; please read it
> before joining fundamentals to prices.

---

## 1. Contents

All files are in `./data/` and are in **long format** (stacked by ticker).

| File | What it is | Grain (one row = ) |
|---|---|---|
| `sp500_constituents.csv` | Universe + GICS metadata | one company |
| `sp500_prices_long.csv` | Daily OHLCV, raw **and** split/dividend-adjusted | one (ticker, date) |
| `sp500_fundamentals_statements_long.csv` | **As-reported** financial-statement line items (all fields) | one (ticker, filing, field) |
| `sp500_fundamentals_daily_long.csv` | Daily point-in-time market metrics | one (ticker, date) |
| `fundamentals_field_definitions.csv` | Human-readable definition + units of every fundamentals field | one field code |

---

## 2. Universe

- **Source:** current S&P 500 membership from the community-maintained
  [`datasets/s-and-p-500-companies`](https://github.com/datasets/s-and-p-500-companies)
  list (sourced from Wikipedia), downloaded June 2026.
- **Count:** 503 listed securities (a few companies have two share classes,
  e.g. `GOOGL`/`GOOG`, `FOX`/`FOXA`, `NWS`/`NWSA`).
- `sp500_constituents.csv` columns: `Symbol, Security, GICS Sector,
  GICS Sub-Industry, Headquarters Location, Date added, CIK, Founded`.

> ⚠️ **Survivorship bias (important, and *not* the same as look-ahead bias).**
> This is the universe **as of June 2026**. Companies that were in the S&P 500
> in the past but have since been removed (bankruptcies, mergers, demotions) are
> **not** included. Any backtest run on this universe is therefore biased upward
> (it only contains today's "survivors"). This is an inherent limitation of using
> a *current* constituent list and you should acknowledge it in your report.
> (Eliminating it would require a point-in-time / historical index-membership
> dataset, which Tiingo's EOD product does not provide.)

---

## 3. File schemas

### 3.1 `sp500_prices_long.csv` — daily prices
Columns:

| Column | Meaning |
|---|---|
| `ticker` | S&P symbol (matches `sp500_constituents.Symbol`) |
| `date` | trading date (`YYYY-MM-DD`) |
| `open, high, low, close, volume` | **raw** (unadjusted) prices and share volume |
| `adjOpen, adjHigh, adjLow, adjClose, adjVolume` | prices/volume **adjusted for splits *and* dividends** |
| `divCash` | cash dividend paid (per share) with ex-date on that row |
| `splitFactor` | split factor on that row (e.g. `2.0` for a 2-for-1 split) |

- Use **`adjClose`** to compute total returns: `ret_t = adjClose_t / adjClose_{t-1} − 1`.
- Adjusted columns are **retro-adjusted**: a past `adjClose` already reflects all
  *subsequent* splits/dividends. This is standard and is the correct series for
  return calculations. (If you want to use a *price level* itself as a feature,
  be aware of this; for returns it is exactly what you want.)

### 3.2 `sp500_fundamentals_statements_long.csv` — financial statements (as-reported)
Columns:

| Column | Meaning |
|---|---|
| `ticker` | S&P symbol |
| `date_available` | **date the statement was released to the public** (≈ SEC filing date). **Use this as the as-of date.** |
| `fiscal_year` | fiscal year the figure refers to |
| `fiscal_quarter` | `1`–`4` = that fiscal quarter; **`0` = the annual (10-K) report** |
| `statement_type` | one of `incomeStatement`, `balanceSheet`, `cashFlow`, `overview` |
| `data_code` | the field code (e.g. `totalAssets`, `netinc`, `revenue`, `equity`, `roe`, `eps`) |
| `value` | the reported value (currency = USD; units per the definitions file) |

- **76 distinct `data_code`s** are present (the exact set per filing depends on the
  company — e.g. banks like `JPM` report a different balance-sheet structure than
  industrials). Look up every code in `fundamentals_field_definitions.csv`.
- `statement_type = overview` contains vendor-computed convenience figures
  (e.g. `roe`, `roa`, `peRatio`, `pbRatio`, `bookVal`, `grossMargin`,
  `piotroskiFScore`). They are included for completeness; if you prefer, ignore
  them and compute your own ratios from the raw income-statement / balance-sheet /
  cash-flow line items.
- Both quarterly (`fiscal_quarter` 1–4) and annual (`fiscal_quarter` 0) records are
  present; the annual row and the Q4 row often share the same `date_available`.

### 3.3 `sp500_fundamentals_daily_long.csv` — daily market metrics
Columns: `ticker, date, marketCap, enterpriseVal, peRatio, pbRatio, trailingPEG1Y`.

- These update **daily** with price and are **point-in-time** (the valuation
  ratios only change once the underlying statement is public — Tiingo does the
  lagging for you here).
- `marketCap` is the cleanest source for a **size** variable (it uses
  point-in-time shares outstanding × price).

### 3.4 `fundamentals_field_definitions.csv`
Columns: `dataCode, name, description, statementType, units`. The dictionary for
every fundamentals field (85 definitions, covering the 76 codes that appear in the
statements file plus the daily metrics).

---

## 4. Point-in-time correctness / **No look-ahead bias** (read this!)

A financial statement for, say, the quarter ending **March 30** is not known to the
market until it is **filed weeks later** (e.g. **May 1**). Joining that statement to
prices on the *period-end* date would let your model "see" earnings before they were
public — classic **look-ahead bias**.

This dataset is built to avoid that:

1. **Statements are "as-reported".** Tiingo dates each statement record by
   `date_available` = **the date it was released to the public** (≈ filing date),
   *not* the fiscal period end. We also use *as-reported* (rather than later
   *restated*) figures, so a value is what was actually known at the time — this
   avoids **restatement** look-ahead as well.
   *Verified example (3M / `MMM`, `totalAssets`):* fiscal-2005 Q1 → `date_available
   = 2005-05-06`; Q2 → `2005-08-03`; the annual report → `2006-02-21`. Filing dates
   land ~4–8 weeks after each period end, as they should.
2. **Daily fundamentals** (`marketCap`, `peRatio`, …) are already point-in-time.
3. **Prices** are point-in-time by nature.

### How to join fundamentals to prices correctly

Use a **backward as-of join** on the **availability date** — never on the fiscal
period end. Example (Python / pandas):

```python
import pandas as pd

px = pd.read_csv("data/sp500_prices_long.csv", parse_dates=["date"])

fun = pd.read_csv("data/sp500_fundamentals_statements_long.csv",
                  parse_dates=["date_available"])

# pick one field, e.g. net income, and pivot to one value per (ticker, filing)
ni = (fun[fun.data_code == "netinc"]
        .sort_values("date_available")
        .rename(columns={"value": "netinc", "date_available": "date"}))

# As-of merge PER TICKER: each trading day gets the LATEST fundamental that was
# already public on or before that day  ->  no look-ahead.
out = []
for tkr, g in px.sort_values("date").groupby("ticker"):
    f = ni[ni.ticker == tkr][["date", "netinc"]]
    if f.empty:
        continue
    out.append(pd.merge_asof(g, f, on="date", direction="backward"))
panel = pd.concat(out)
```

`pd.merge_asof(..., direction="backward")` guarantees that on any date you only
ever use fundamentals whose `date_available <= date`.

**Rules of thumb**
- Align on `date_available` (statements) / `date` (daily, prices). Do **not** use
  `fiscal_year`/`fiscal_quarter` as a calendar timestamp.
- If you build trailing-twelve-month (TTM) figures, sum the **last four quarterly
  records by `date_available`** (use `fiscal_quarter` 1–4, exclude the `0` annual to
  avoid double counting).

---

## 5. Known data quirks

- **Dual-class shares:** fundamentals are reported once per company, so the
  secondary class can have **empty** statements/daily data (e.g. `GOOG` is empty;
  use `GOOGL`). Prices exist for both classes.
- **Newer members / spin-offs** have shorter histories (e.g. `ALLE` from 2013,
  `AMCR` from 2019). This is correct, not missing data. `VLTO` (Veralto, 2023
  spin-off) has prices but **no fundamentals** in Tiingo yet.
- **Ticker normalization:** dotted symbols in the constituent list (`BRK.B`,
  `BF.B`) are queried from Tiingo as `BRK-B`, `BF-B`; the `ticker` column keeps the
  original S&P symbol (with the dot).
- **Currency:** USD. **Units:** per `fundamentals_field_definitions.csv` (`$`,
  `%`, share counts, or unitless ratios).
- Any tickers that failed to download are listed in `data/_failures.csv`
  (absent if there were none).

---

## 6. Reproducing / refreshing the data

```bash
# from the project folder
conda run -n boun-lectures pip install -r requirements.txt
conda run -n boun-lectures python fetch_sp500_factor_data.py            # full run
conda run -n boun-lectures python fetch_sp500_factor_data.py --max-tickers 3   # quick test
```

The script is **resumable**: completed tickers are tracked in `data/_status_*.txt`
and skipped on re-run. To rebuild from scratch, delete the `data/_status_*.txt`
files and the output CSVs. The Tiingo API key is read (never written) from
`D:\GITHUB\keys.env` via `python-dotenv` (`TIINGO_API_KEY`).

---

## 7. Dataset size

| File | Rows | Size (MB) |
|---|---:|---:|
| `sp500_constituents.csv` | 503 | 0.1 |
| `sp500_prices_long.csv` | 2,293,664 | 254.5 |
| `sp500_fundamentals_statements_long.csv` | 3,459,358 | 190.5 |
| `sp500_fundamentals_daily_long.csv` | 2,296,965 | 191.3 |
| `fundamentals_field_definitions.csv` | 85 | 0.0 |

- **Prices:** 503 tickers, 2006-06-05 → 2026-06-02.
- **Statements:** 499 tickers, 76 distinct field codes, availability 2005-04-29 → 2026-06-02.
- **Daily metrics:** 499 tickers, 2006-06-05 → 2026-06-02.
- **Failures:** none.

> Prices cover all **503** securities. Fundamentals cover **499**; the exact 4
> without fundamentals are `FOX`, `GOOG`, `NWS` (dual-class *secondary* tickers —
> their financials are filed under the primary class `FOXA` / `GOOGL` / `NWSA`)
> and `VLTO` (Veralto, a late-2023 spin-off not yet covered by Tiingo's
> fundamentals). All four still have complete daily price histories.
>
> Row counts were verified against the fetch log: on-disk rows equal the rows
> pulled from the API exactly, for every ticker — **no truncation**.
>
> The two large files (`prices`, `statements`) are ~250 MB / ~190 MB. On a
> memory-constrained machine, read selectively, e.g.
> `pd.read_csv(..., usecols=[...])`, filter by `ticker`, or read in `chunksize=`
> batches rather than loading everything at once.
