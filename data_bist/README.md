# Experimental Official-BIST Appendix

This folder contains an experimental official-BIST data pipeline. It is not part of the completed submission run because the required BIST DataStore monthly valuation-ratio files could not be downloaded during the project window.

## Frozen Price Data

`raw/bist_public_daily_prices.csv` contains:

- `1,216,158` rows.
- `727` common-stock tickers.
- `4` index tickers.
- Date range `2016-01-04` to `2026-05-26`.

Prices come from Borsa Istanbul public bulletin files. Index closes come from the public BIST index graphic endpoint.

Source endpoints:

- `https://www.borsaistanbul.com/data/thb/YYYY/MM/thbYYYYMMDD1.zip`
- `https://borsaistanbul.com/graphic.php?veriTuru=endeks-graphic&indexCode=XU100`
- `https://datastore.borsaistanbul.com/api/product-type/100465/products?page=1&page-size=100`

## Missing Input

The experimental four-factor rerun would require:

```text
raw/bist_monthly_ratios.csv
```

Build it by placing BIST DataStore monthly valuation-ratio files such as `degoran_M_YYYYMM.zip` under:

```text
raw/datastore_basic_ratios/
```

Then run:

```powershell
py src\build_bist_datastore_ratios.py
py src\run_project_bist.py
```

The runner stops if the BIST ratio CSV is missing. It never copies Yahoo fundamentals into this folder. This is intentional: the appendix should not produce a mixed-source result.

## Price Limitation

Public bulletin closes are official but unadjusted. For a future official-BIST study, replace them with adjusted BIST DataStore prices when available.
