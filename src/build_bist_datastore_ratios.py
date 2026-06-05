"""Build stock-level ROE and P/E inputs from BIST DataStore monthly ratios.

Expected manual inputs:
    data_bist/raw/datastore_basic_ratios/degoran_M_YYYYMM.zip
or extracted files such as:
    data_bist/raw/datastore_basic_ratios/ORANYYYYMM.xls

The output is a frozen CSV consumed by src/run_project_bist.py:
    data_bist/raw/bist_monthly_ratios.csv
"""

from __future__ import annotations

import argparse
import io
import json
import re
import urllib.request
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import yaml


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "project_config.yaml"
RAW_DIR = ROOT / "data_bist" / "raw"
DEFAULT_INPUT_DIR = RAW_DIR / "datastore_basic_ratios"
DEFAULT_OUTPUT = RAW_DIR / "bist_monthly_ratios.csv"
DEFAULT_MANIFEST = RAW_DIR / "bist_datastore_monthly_ratio_manifest.csv"
PRODUCT_TYPE_ID = 100465
PRICE_FILE = RAW_DIR / "bist_public_daily_prices.csv"
INDEX_TICKERS = {"XU100", "XU030", "XBANK", "XUSIN"}


RATIO_COLUMNS = [
    "raw_code",
    "name",
    "market_value_thousand_tl",
    "net_profit_ttm_thousand_tl",
    "net_cash_dividend_thousand_tl",
    "equity_thousand_tl",
    "pe",
    "dividend_yield_pct",
    "pbv",
]


def load_config() -> dict:
    with CONFIG_PATH.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def load_ratio_filter_tickers(config: dict, use_config_universe: bool) -> set[str]:
    if use_config_universe or not PRICE_FILE.exists():
        return {str(ticker).upper() for ticker in config["stock_tickers"]}

    prices = pd.read_csv(PRICE_FILE, usecols=["ticker"])
    tickers = {
        str(ticker).upper()
        for ticker in prices["ticker"].dropna().unique()
        if str(ticker).upper() not in INDEX_TICKERS
    }
    return tickers or {str(ticker).upper() for ticker in config["stock_tickers"]}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Convert BIST DataStore monthly ratio files to a project CSV.")
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--manifest-only", action="store_true", help="Only refresh the DataStore product manifest.")
    parser.add_argument("--skip-manifest", action="store_true", help="Do not call the DataStore metadata API.")
    parser.add_argument(
        "--filter-config-universe",
        action="store_true",
        help="Filter ratios to config/project_config.yaml stock_tickers instead of the frozen BIST price universe.",
    )
    return parser.parse_args()


def http_json(url: str, timeout: int = 30) -> object:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_monthly_ratio_manifest() -> pd.DataFrame:
    rows: list[dict] = []
    page = 1
    while True:
        url = (
            f"https://datastore.borsaistanbul.com/api/product-type/{PRODUCT_TYPE_ID}/products"
            f"?page={page}&page-size=100"
        )
        payload = http_json(url)
        if not payload:
            break
        if not isinstance(payload, list):
            raise ValueError(f"Unexpected DataStore manifest response on page {page}: {type(payload)!r}")
        for item in payload:
            entity = item.get("dataDefnEntity") or {}
            rows.append(
                {
                    "product_id": item.get("id"),
                    "file_name": item.get("fileName"),
                    "product_date": item.get("date"),
                    "create_date": item.get("createDate"),
                    "file_size": item.get("fileSize"),
                    "price": item.get("price"),
                    "in_library": item.get("inLibrary"),
                    "description": entity.get("description"),
                    "keywords": entity.get("keywords"),
                }
            )
        page += 1
    return pd.DataFrame(rows)


def write_input_readme(input_dir: Path, manifest_path: Path, output_path: Path) -> None:
    input_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        "# BIST DataStore Monthly Basic Ratios",
        "",
        "Place BIST DataStore monthly valuation-ratio files here.",
        "",
        "Expected files:",
        "- `degoran_M_YYYYMM.zip` downloaded from BIST DataStore monthly Basic Ratios / Degerleme Oranlari.",
        "- Or extracted `ORANYYYYMM.xls` / CSV equivalents.",
        "",
        "Then run:",
        "",
        "```powershell",
        "py src\\build_bist_datastore_ratios.py",
        "py src\\run_project_bist.py",
        "```",
        "",
        f"The builder writes `{output_path.relative_to(ROOT)}`.",
        "By default, ratio rows are filtered to tickers present in `data_bist/raw/bist_public_daily_prices.csv`.",
        f"A product manifest is written to `{manifest_path.relative_to(ROOT)}` when DataStore metadata is reachable.",
        "",
        "This directory is intentionally BIST-only. Do not put Yahoo Finance files here.",
    ]
    (input_dir / "README.md").write_text("\n".join(lines), encoding="utf-8")


def parse_period_from_name(name: str) -> pd.Timestamp | None:
    match = re.search(r"(20\d{2})(0[1-9]|1[0-2])", name)
    if not match:
        return None
    year, month = match.groups()
    return pd.Timestamp(int(year), int(month), 1) + pd.offsets.MonthEnd(0)


def normalize_code(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    code = str(value).strip().upper()
    code = re.sub(r"\.E$", "", code)
    code = re.sub(r"[^A-Z0-9]", "", code)
    return code


def parse_number(value: object) -> float:
    if value is None or pd.isna(value):
        return np.nan
    if isinstance(value, (int, float, np.integer, np.floating)):
        return float(value)

    text = str(value).strip()
    if text in {"", "-", "--", "N/A", "NA", "NULL"}:
        return np.nan

    negative = text.startswith("(") and text.endswith(")")
    text = text.strip("()")
    text = re.sub(r"[^0-9,.\-]", "", text)
    if not text or text in {"-", ".", ","}:
        return np.nan

    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        text = text.replace(",", ".")

    try:
        number = float(text)
    except ValueError:
        return np.nan
    return -number if negative else number


def read_excel_or_delimited(member_name: str, payload: bytes) -> pd.DataFrame:
    suffix = Path(member_name).suffix.lower()
    if suffix in {".xls", ".xlsx"}:
        try:
            engine = "xlrd" if suffix == ".xls" else "openpyxl"
            return pd.read_excel(io.BytesIO(payload), header=None, dtype=str, engine=engine)
        except Exception:
            pass

    best = pd.DataFrame()
    for encoding in ["utf-8-sig", "cp1254", "latin1"]:
        for sep in [";", ",", "\t"]:
            try:
                candidate = pd.read_csv(
                    io.BytesIO(payload),
                    sep=sep,
                    header=None,
                    dtype=str,
                    encoding=encoding,
                    engine="python",
                )
            except Exception:
                continue
            if candidate.shape[1] > best.shape[1]:
                best = candidate
            if candidate.shape[1] >= len(RATIO_COLUMNS):
                return candidate
    return best


def normalize_ratio_frame(
    df: pd.DataFrame,
    period: pd.Timestamp,
    source_file: str,
    stock_tickers: set[str],
) -> pd.DataFrame:
    if df.empty or df.shape[1] < len(RATIO_COLUMNS):
        return pd.DataFrame()

    out = df.iloc[:, : len(RATIO_COLUMNS)].copy()
    out.columns = RATIO_COLUMNS
    out["ticker"] = out["raw_code"].map(normalize_code)
    out = out[out["ticker"].isin(stock_tickers)].copy()
    if out.empty:
        return pd.DataFrame()

    numeric_cols = RATIO_COLUMNS[2:]
    for col in numeric_cols:
        out[col] = out[col].map(parse_number)

    out["date"] = period
    out["roe"] = out["net_profit_ttm_thousand_tl"] / out["equity_thousand_tl"]
    out.loc[out["equity_thousand_tl"] == 0, "roe"] = np.nan
    out.loc[out["pe"] <= 0, "pe"] = np.nan
    out["source_file"] = source_file
    return out[
        [
            "date",
            "ticker",
            "name",
            "roe",
            "pe",
            "market_value_thousand_tl",
            "net_profit_ttm_thousand_tl",
            "net_cash_dividend_thousand_tl",
            "equity_thousand_tl",
            "dividend_yield_pct",
            "pbv",
            "source_file",
        ]
    ]


def parse_ratio_file(path: Path, stock_tickers: set[str]) -> list[pd.DataFrame]:
    frames: list[pd.DataFrame] = []
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as zf:
            for member in zf.namelist():
                if member.endswith("/") or Path(member).suffix.lower() not in {".xls", ".xlsx", ".csv", ".txt"}:
                    continue
                period = parse_period_from_name(member) or parse_period_from_name(path.name)
                if period is None:
                    continue
                payload = zf.read(member)
                raw = read_excel_or_delimited(member, payload)
                frame = normalize_ratio_frame(raw, period, f"{path.name}:{member}", stock_tickers)
                if not frame.empty:
                    frames.append(frame)
    else:
        period = parse_period_from_name(path.name)
        if period is None:
            return frames
        raw = read_excel_or_delimited(path.name, path.read_bytes())
        frame = normalize_ratio_frame(raw, period, path.name, stock_tickers)
        if not frame.empty:
            frames.append(frame)
    return frames


def input_files(input_dir: Path) -> list[Path]:
    suffixes = {".zip", ".xls", ".xlsx", ".csv", ".txt"}
    return sorted(path for path in input_dir.rglob("*") if path.is_file() and path.suffix.lower() in suffixes)


def write_coverage(ratios: pd.DataFrame, output_path: Path) -> None:
    coverage = (
        ratios.groupby("ticker")
        .agg(
            first_date=("date", "min"),
            last_date=("date", "max"),
            ratio_months=("date", "nunique"),
            pe_months=("pe", lambda s: int(s.notna().sum())),
            roe_months=("roe", lambda s: int(s.notna().sum())),
        )
        .reset_index()
        .sort_values("ticker")
    )
    coverage.to_csv(output_path.with_name("bist_monthly_ratio_coverage.csv"), index=False)


def main() -> None:
    args = parse_args()
    config = load_config()
    stock_tickers = load_ratio_filter_tickers(config, args.filter_config_universe)

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    write_input_readme(args.input_dir, args.manifest, args.output)

    if not args.skip_manifest:
        try:
            manifest = fetch_monthly_ratio_manifest()
            manifest.to_csv(args.manifest, index=False)
            print(f"Saved DataStore product manifest to {args.manifest.relative_to(ROOT)}.")
        except Exception as exc:  # noqa: BLE001 - metadata is useful but not required to parse local files.
            print(f"Could not refresh DataStore product manifest: {exc!r}")

    if args.manifest_only:
        return

    files = input_files(args.input_dir)
    if not files:
        raise SystemExit(
            f"No monthly ratio files found in {args.input_dir.relative_to(ROOT)}. "
            "Download BIST DataStore Basic Ratios monthly files named degoran_M_YYYYMM.zip, "
            "place them in that folder, then rerun this script."
        )

    frames: list[pd.DataFrame] = []
    for path in files:
        frames.extend(parse_ratio_file(path, stock_tickers))

    if not frames:
        raise SystemExit(
            "Monthly ratio files were found, but no rows matched config/project_config.yaml stock_tickers. "
            "Check that the files are BIST DataStore degoran_M_YYYYMM.zip / ORANYYYYMM.xls files."
        )

    ratios = pd.concat(frames, ignore_index=True)
    ratios = ratios.sort_values(["date", "ticker", "source_file"]).drop_duplicates(["date", "ticker"], keep="last")
    ratios.to_csv(args.output, index=False)
    write_coverage(ratios, args.output)

    print(f"Saved {len(ratios):,} BIST monthly ratio rows to {args.output.relative_to(ROOT)}.")
    print(f"Tickers covered: {ratios['ticker'].nunique():,}")
    print(f"Date range: {ratios['date'].min().date()} to {ratios['date'].max().date()}")


if __name__ == "__main__":
    main()
