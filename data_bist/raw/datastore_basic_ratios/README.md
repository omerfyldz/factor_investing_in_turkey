# BIST DataStore Monthly Basic Ratios

Place BIST DataStore monthly valuation-ratio files here.

Expected files:
- `degoran_M_YYYYMM.zip` downloaded from BIST DataStore monthly Basic Ratios / Degerleme Oranlari.
- Or extracted `ORANYYYYMM.xls` / CSV equivalents.

Then run:

```powershell
py src\build_bist_datastore_ratios.py
py src\run_project_bist.py
```

The builder writes `data_bist\raw\bist_monthly_ratios.csv`.
By default, ratio rows are filtered to tickers present in `data_bist/raw/bist_public_daily_prices.csv`.
A product manifest is written to `data_bist\raw\bist_datastore_monthly_ratio_manifest.csv` when DataStore metadata is reachable.

This directory is intentionally BIST-only. Do not put Yahoo Finance files here.