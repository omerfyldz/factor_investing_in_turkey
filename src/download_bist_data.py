"""Download a separate official-BIST price/index data set.

This script writes a BIST-focused source folder under ``data_bist/raw``.
ROE/P/E inputs are built separately from BIST DataStore monthly ratio files
with ``src/build_bist_datastore_ratios.py``.

Notes:
- Equity prices come from Borsa Istanbul public daily bulletin files.
- Index closes come from the Borsa Istanbul public index graphic endpoint.
- This script intentionally does not copy Yahoo Finance fundamentals.
"""

from __future__ import annotations

import argparse
import io
import json
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import pandas as pd
import yaml


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "project_config.yaml"
RAW_DIR = ROOT / "data_bist" / "raw"
PRICE_FILE = RAW_DIR / "bist_public_daily_prices.csv"


def load_config() -> dict:
    with CONFIG_PATH.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Freeze official BIST public data to data_bist/raw.")
    parser.add_argument(
        "--start-date",
        default="2016-01-01",
        help="First bulletin date to request. Default gives enough warm-up for 1000-day MA factors.",
    )
    parser.add_argument(
        "--end-date",
        default=None,
        help="Last bulletin date to request. Defaults to config end_date or today.",
    )
    parser.add_argument("--workers", type=int, default=8, help="Parallel download workers.")
    parser.add_argument(
        "--config-universe-only",
        action="store_true",
        help="Download only config/project_config.yaml stock_tickers. Default downloads all common-stock .E rows.",
    )
    return parser.parse_args()


def business_dates(start: str, end: str) -> list[pd.Timestamp]:
    return list(pd.date_range(start=start, end=end, freq="B"))


def http_get(url: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read()


def to_number(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series.replace({"": pd.NA, "-": pd.NA}), errors="coerce")


def parse_trade_dates(series: pd.Series) -> pd.Series:
    dates = pd.to_datetime(series, errors="coerce", format="%Y-%m-%d")
    missing = dates.isna()
    if missing.any():
        dates.loc[missing] = pd.to_datetime(series.loc[missing], errors="coerce", dayfirst=True)
    return dates


def parse_bulletin_csv(raw_zip: bytes, requested_tickers: Optional[set[str]]) -> pd.DataFrame:
    with zipfile.ZipFile(io.BytesIO(raw_zip)) as zf:
        csv_names = [name for name in zf.namelist() if name.lower().endswith(".csv")]
        if not csv_names:
            return pd.DataFrame()
        with zf.open(csv_names[0]) as fh:
            df = pd.read_csv(fh, sep=";", skiprows=[0], encoding="utf-8-sig", dtype=str)

    required = {
        "date": "TRADE DATE",
        "series": "INSTRUMENT SERIES CODE",
        "open": "OPENING PRICE",
        "high": "HIGHEST PRICE",
        "low": "LOWEST PRICE",
        "close": "CLOSING PRICE",
        "volume": "TOTAL TRADED VOLUME",
    }
    if not all(col in df.columns for col in required.values()):
        return pd.DataFrame()

    if requested_tickers:
        tickers_with_suffix = {f"{ticker}.E" for ticker in requested_tickers}
        df = df[df[required["series"]].isin(tickers_with_suffix)].copy()
    else:
        common_stock = df[required["series"]].str.endswith(".E", na=False)
        if "INSTRUMENT TYPE" in df.columns:
            common_stock &= df["INSTRUMENT TYPE"].eq("MSPOTEQT")
        if "MARKET" in df.columns:
            common_stock &= df["MARKET"].eq("MSPOT")
        df = df[common_stock].copy()
    if df.empty:
        return pd.DataFrame()

    out = pd.DataFrame(
        {
            "date": parse_trade_dates(df[required["date"]]),
            "ticker": df[required["series"]].str.replace(r"\.E$", "", regex=True),
            "open": to_number(df[required["open"]]),
            "high": to_number(df[required["high"]]),
            "low": to_number(df[required["low"]]),
            "close": to_number(df[required["close"]]),
            "volume": to_number(df[required["volume"]]),
        }
    )
    out = out.dropna(subset=["date", "ticker", "close"])
    out = out[out["close"] > 0].copy()
    for col in ["open", "high", "low"]:
        out.loc[out[col] <= 0, col] = pd.NA
    return out


def download_bulletin_for_date(dt: pd.Timestamp, requested_tickers: Optional[set[str]]) -> tuple[pd.DataFrame, dict]:
    ymd = dt.strftime("%Y%m%d")
    url = f"https://www.borsaistanbul.com/data/thb/{dt:%Y}/{dt:%m}/thb{ymd}1.zip"
    log = {"date": dt.date().isoformat(), "url": url, "status": "missing", "rows": 0, "error": None}
    try:
        content = http_get(url, timeout=20)
        rows = parse_bulletin_csv(content, requested_tickers)
        log.update({"status": "ok", "rows": int(len(rows))})
        return rows, log
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            log.update({"status": "error", "error": repr(exc)})
        return pd.DataFrame(), log
    except Exception as exc:  # noqa: BLE001 - data files can vary by date.
        log.update({"status": "error", "error": repr(exc)})
        return pd.DataFrame(), log


def download_stock_prices(
    start: str,
    end: str,
    tickers: Optional[list[str]],
    workers: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    requested_tickers = set(tickers) if tickers else None
    dates = business_dates(start, end)
    frames: list[pd.DataFrame] = []
    logs: list[dict] = []

    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        futures = [executor.submit(download_bulletin_for_date, dt, requested_tickers) for dt in dates]
        for i, future in enumerate(as_completed(futures), start=1):
            rows, log = future.result()
            logs.append(log)
            if not rows.empty:
                frames.append(rows)
            if i % 250 == 0:
                ok = sum(1 for row in logs if row["status"] == "ok")
                print(f"  processed {i:,}/{len(dates):,} candidate business days; found {ok:,} bulletins")

    prices = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if not prices.empty:
        prices = prices.sort_values(["ticker", "date"]).drop_duplicates(["ticker", "date"], keep="last")
    return prices, pd.DataFrame(logs).sort_values("date")


def download_index_closes(index_codes: list[str], start: str, end: str) -> pd.DataFrame:
    frames = []
    start_dt = pd.to_datetime(start)
    end_dt = pd.to_datetime(end)
    for code in index_codes:
        query = urllib.parse.urlencode({"veriTuru": "endeks-graphic", "indexCode": code})
        url = f"https://borsaistanbul.com/graphic.php?{query}"
        try:
            payload = json.loads(http_get(url, timeout=45).decode("utf-8"))
            data = pd.DataFrame(payload.get("data", []))
        except Exception as exc:  # noqa: BLE001
            print(f"Index download failed for {code}: {exc!r}")
            continue
        if data.empty or "hisTs" not in data.columns or "clval" not in data.columns:
            continue
        close = pd.to_numeric(data["clval"], errors="coerce")
        idx = pd.DataFrame(
            {
                "date": pd.to_datetime(data["hisTs"], errors="coerce"),
                "ticker": code,
                "open": close,
                "high": close,
                "low": close,
                "close": close,
                "volume": 0.0,
            }
        )
        idx = idx[(idx["date"] >= start_dt) & (idx["date"] <= end_dt)]
        frames.append(idx.dropna(subset=["date", "close"]))
    out = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    return out.sort_values(["ticker", "date"]) if not out.empty else out


def write_universe(config: dict, stock_tickers: list[str]) -> None:
    index_codes = list(config["index_tickers"].keys())
    rows = []
    for code in index_codes:
        rows.append(
            {
                "ticker": code,
                "source_symbol": code,
                "role": "index",
                "source": "BIST index graphic endpoint",
            }
        )
    for ticker in stock_tickers:
        rows.append(
            {
                "ticker": ticker,
                "source_symbol": f"{ticker}.E",
                "role": "stock",
                "source": "BIST public daily bulletin common-stock series",
            }
        )
    pd.DataFrame(rows).to_csv(RAW_DIR / "universe.csv", index=False)


def write_notes(start: str, end: str) -> None:
    lines = [
        "BIST-source data notes",
        "======================",
        f"Date range requested: {start} to {end}.",
        "Stock prices: Borsa Istanbul public daily bulletin files at https://www.borsaistanbul.com/data/thb/YYYY/MM/thbYYYYMMDD1.zip.",
        "Default universe: all MSPOTEQT common-stock .E rows found in the frozen BIST bulletin files.",
        "Index closes: Borsa Istanbul graphic endpoint at https://borsaistanbul.com/graphic.php?veriTuru=endeks-graphic&indexCode=XU100.",
        "Fundamentals/ratios: build data_bist/raw/bist_monthly_ratios.csv from BIST DataStore monthly valuation-ratio files with src/build_bist_datastore_ratios.py.",
        "Important limitation: public bulletin stock prices are official closing prices but are not adjusted for dividends/splits in this file.",
        "Data cleaning: rows with nonpositive closing prices are treated as non-trading placeholders and dropped.",
        "Adjusted daily closing price data is a separate BIST DataStore product; use it instead of bulletin closes if you obtain it.",
        "This folder is separate from data/raw, results, figures, and presentation.",
    ]
    (RAW_DIR / "bist_data_source_notes.txt").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    args = parse_args()
    config = load_config()
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    end_date = args.end_date or config["project"].get("end_date") or date.today().isoformat()
    start_date = args.start_date

    stock_tickers = list(config["stock_tickers"]) if args.config_universe_only else None
    index_codes = list(config["index_tickers"].keys())

    if stock_tickers:
        print(f"Downloading BIST public stock bulletins for {len(stock_tickers)} configured stocks...")
    else:
        print("Downloading BIST public stock bulletins for all common-stock .E rows...")
    stock_prices, log = download_stock_prices(start_date, end_date, stock_tickers, args.workers)
    print(f"Downloading BIST index closes for {', '.join(index_codes)}...")
    index_prices = download_index_closes(index_codes, start_date, end_date)

    prices = pd.concat([stock_prices, index_prices], ignore_index=True)
    if prices.empty:
        raise RuntimeError("No BIST price rows were downloaded.")
    prices = prices.sort_values(["ticker", "date"]).drop_duplicates(["ticker", "date"], keep="last")
    prices.to_csv(PRICE_FILE, index=False)
    log.to_csv(RAW_DIR / "bist_bulletin_download_log.csv", index=False)
    index_prices.to_csv(RAW_DIR / "bist_index_daily.csv", index=False)

    coverage = (
        prices.groupby("ticker")
        .agg(start=("date", "min"), end=("date", "max"), observations=("date", "size"))
        .reset_index()
        .sort_values("ticker")
    )
    coverage.to_csv(RAW_DIR / "price_coverage.csv", index=False)
    pd.DataFrame(
        [
            {
                "clean_price_rows": int(len(prices)),
                "stock_price_rows": int(len(stock_prices)),
                "index_price_rows": int(len(index_prices)),
                "tickers": int(prices["ticker"].nunique()),
                "stock_tickers": int(stock_prices["ticker"].nunique()) if not stock_prices.empty else 0,
                "index_tickers": int(index_prices["ticker"].nunique()) if not index_prices.empty else 0,
                "note": "Nonpositive closing-price placeholders are dropped while parsing each bulletin.",
            }
        ]
    ).to_csv(RAW_DIR / "bist_price_quality_report.csv", index=False)

    downloaded_stock_tickers = sorted(stock_prices["ticker"].dropna().unique()) if not stock_prices.empty else []
    write_universe(config, downloaded_stock_tickers)
    write_notes(start_date, end_date)

    ok_days = int((log["status"] == "ok").sum()) if not log.empty else 0
    print(f"Saved {len(prices):,} BIST-source price rows to {PRICE_FILE.relative_to(ROOT)}.")
    print(f"Found {ok_days:,} public bulletin files in requested business-date range.")
    print("Next: build BIST monthly ROE/P/E inputs with src/build_bist_datastore_ratios.py.")


if __name__ == "__main__":
    main()
