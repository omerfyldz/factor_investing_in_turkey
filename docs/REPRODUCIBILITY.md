# Reproducibility Guide

## Completed Baseline

Use a fresh Python session:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install --upgrade pip
py -m pip install -r requirements.txt
py src\run_project.py
```

The command reads frozen inputs from `data/raw/` and rewrites:

- `data/processed/`
- `results/`
- `figures/`
- `presentation/bist_factor_project_presentation.pdf`

It must not require network access.

## Participant Names

Before final submission, edit:

```yaml
project:
  group_participants:
    - "Name Surname"
    - "Name Surname"
```

Then rerun:

```powershell
py src\run_project.py
```

Check `results/project_audit_checklist.csv`. Every row should be `OK`.

## Experimental Official-BIST Appendix

The official-BIST scripts are not required to reproduce the submitted findings. They are retained as an experimental appendix in case DataStore access becomes available later.

```powershell
py src\download_bist_data.py --start-date 2016-01-01 --workers 8
py src\build_bist_datastore_ratios.py
py src\run_project_bist.py
```

Before running the ratio builder, place BIST DataStore files such as `degoran_M_YYYYMM.zip` under:

```text
data_bist/raw/datastore_basic_ratios/
```

`src/run_project_bist.py` stops if `data_bist/raw/bist_monthly_ratios.csv` is absent. This prevents accidental mixing of official BIST prices with Yahoo fundamentals. Since the required DataStore files could not be downloaded, this path is documented but not used for the final results.

## Validation Checks

Run:

```powershell
py -m compileall src
py src\run_project.py
```

Then inspect:

- `results/project_audit_checklist.csv`
- `results/validation_report.txt`
- `results/strategy_development_narrative.txt`
- `results/monte_carlo_summary.csv`
- `presentation/bist_factor_project_presentation.pdf`

Refresh the frozen-input hash manifest after intentional input or source-code changes:

```powershell
py src\write_repository_manifest.py
```

## GitHub Notes

Raw CSV files are intentionally committed because the instructor requires identical reproducible findings from frozen data. Do not remove the CSV inputs from the repository.
