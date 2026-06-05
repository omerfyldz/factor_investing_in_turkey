"""Run the project on the separate BIST-source data folder."""

from __future__ import annotations

import os
from pathlib import Path


os.environ.setdefault(
    "PROJECT_DATA_SOURCE_LABEL",
    "BIST public prices/indexes + BIST DataStore monthly ratios",
)
os.environ.setdefault("PROJECT_RAW_DIR", "data_bist/raw")
os.environ.setdefault("PROJECT_PROCESSED_DIR", "data_bist/processed")
os.environ.setdefault("PROJECT_RESULTS_DIR", "results_bist")
os.environ.setdefault("PROJECT_FIGURES_DIR", "figures_bist")
os.environ.setdefault("PROJECT_PRESENTATION_DIR", "presentation_bist")
os.environ.setdefault("PROJECT_PRICE_FILE", "bist_public_daily_prices.csv")
os.environ.setdefault("PROJECT_FUNDAMENTALS_FILE", "bist_monthly_ratios.csv")
os.environ.setdefault("PROJECT_RATIO_FILE", "bist_monthly_ratios.csv")

if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    ratio_path = root / os.environ["PROJECT_RAW_DIR"] / os.environ["PROJECT_RATIO_FILE"]
    if not ratio_path.exists():
        raise SystemExit(
            f"Missing {ratio_path.relative_to(root)}. "
            "Place BIST DataStore degoran_M_YYYYMM.zip/ORANYYYYMM.xls files under "
            "data_bist/raw/datastore_basic_ratios and run src/build_bist_datastore_ratios.py first."
        )
    from run_project import main  # noqa: E402

    try:
        main()
    except FileNotFoundError as exc:
        raise SystemExit(str(exc)) from None
