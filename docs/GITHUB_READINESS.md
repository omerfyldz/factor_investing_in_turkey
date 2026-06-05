# GitHub Readiness

Verified on `2026-06-05`.

## Completed

- Rebuilt the baseline end to end with `py src\run_project.py`.
- Confirmed selected strategy: `composite_all4`.
- Confirmed pinned dependencies in `requirements.txt`.
- Confirmed frozen raw CSV inputs remain in `data/raw/`.
- Confirmed saved Backtrader trades, positions, orders, returns, equity curves, metrics, figures, and PDF presentation.
- Confirmed the experimental official-BIST pipeline no longer copies Yahoo fundamentals.
- Archived the rejected hybrid BIST-price plus Yahoo-fundamentals experiment locally.
- Added SHA-256 hashes in `docs/repository_manifest.csv`.
- Added `.gitignore` and `.gitattributes`.

## Remaining Manual Input

Set participant names in:

```yaml
project:
  group_participants:
    - "Name Surname"
```

Then rerun:

```powershell
py src\run_project.py
```

Confirm `results/project_audit_checklist.csv` contains only `OK`.

## GitHub Size Check

The largest required project input is `data/raw/yahoo_daily_prices.csv` at approximately `44.65 MB`, below GitHub's `100 MB` per-file limit.

The GitHub package contains `110` tracked project files totaling approximately `108.79 MB`.

Course notebooks, lecture PDFs, the assignment PDF, the paper PDF, reference guides, and unrelated S&P example data were removed from tracking so the repository presents the project as independent work.

The experimental BIST raw files are kept locally and ignored for the GitHub submission package.

Bulky legacy generated outputs under `archive/legacy_bist_price_yahoo_fundamentals/` are ignored. The tracked archive README preserves the experiment summary without duplicating generated artifacts.

## Experimental BIST Appendix

The official-BIST work remains experimental because BIST DataStore monthly valuation-ratio files could not be downloaded. This does not block the completed baseline submission.
