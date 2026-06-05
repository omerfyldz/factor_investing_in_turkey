"""Download and freeze public BIST data to CSV.

Run this script once before running ``src/run_project.py``. The analysis script
uses the CSV files written here, so final results are reproducible without
network access.
"""

from __future__ import annotations

import collections
import collections.abc
from datetime import datetime
from pathlib import Path
from typing import Iterable

import pandas as pd
import yaml


# Compatibility for the old requests/urllib3 stack in the course environment.
for _name in ["Mapping", "MutableMapping", "Sequence", "MutableSet", "Callable"]:
    if not hasattr(collections, _name):
        setattr(collections, _name, getattr(collections.abc, _name))

import yfinance as yf  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "project_config.yaml"
RAW_DIR = ROOT / "data" / "raw"


def load_config() -> dict:
    with CONFIG_PATH.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def yahoo_symbol(ticker: str) -> str:
    if ticker.endswith(".IS"):
        return ticker
    return f"{ticker}.IS"


def flatten_price_download(raw: pd.DataFrame, symbols: Iterable[str]) -> pd.DataFrame:
    rows = []
    if raw.empty:
        return pd.DataFrame()

    raw = raw.copy()
    raw.index = pd.to_datetime(raw.index).tz_localize(None)

    if isinstance(raw.columns, pd.MultiIndex):
        first_level = set(raw.columns.get_level_values(0))
        for symbol in symbols:
            if symbol not in first_level:
                continue
            df = raw[symbol].copy()
            if df.dropna(how="all").empty:
                continue
            df.columns = [str(c).lower().replace(" ", "_") for c in df.columns]
            df["ticker"] = symbol.replace(".IS", "")
            df["date"] = df.index
            rows.append(df.reset_index(drop=True))
    else:
        df = raw.copy()
        df.columns = [str(c).lower().replace(" ", "_") for c in df.columns]
        df["ticker"] = list(symbols)[0].replace(".IS", "")
        df["date"] = df.index
        rows.append(df.reset_index(drop=True))

    if not rows:
        return pd.DataFrame()

    out = pd.concat(rows, ignore_index=True)
    keep = ["date", "ticker", "open", "high", "low", "close", "volume"]
    for col in keep:
        if col not in out.columns:
            out[col] = pd.NA
    out = out[keep]
    out = out.dropna(subset=["date", "ticker", "close"])
    out = out.sort_values(["ticker", "date"])
    return out


def statement_to_long(df: pd.DataFrame, ticker: str, statement: str, frequency: str) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(
            columns=["ticker", "frequency", "statement", "item", "period_end", "value"]
        )

    out = df.copy()
    out.index = out.index.astype(str)
    out = out.reset_index(names="item")
    out = out.melt(id_vars="item", var_name="period_end", value_name="value")
    out["ticker"] = ticker.replace(".IS", "")
    out["frequency"] = frequency
    out["statement"] = statement
    out["period_end"] = pd.to_datetime(out["period_end"], errors="coerce").dt.tz_localize(None)
    out["value"] = pd.to_numeric(out["value"], errors="coerce")
    out = out.dropna(subset=["period_end", "value"])
    return out[["ticker", "frequency", "statement", "item", "period_end", "value"]]


def download_prices(config: dict) -> pd.DataFrame:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    start = config["project"]["start_date"]
    end = config["project"].get("end_date") or datetime.today().strftime("%Y-%m-%d")

    index_symbols = list(config["index_tickers"].values())
    stock_symbols = [yahoo_symbol(t) for t in config["stock_tickers"]]
    symbols = list(dict.fromkeys(index_symbols + stock_symbols))

    print(f"Downloading adjusted daily OHLCV for {len(symbols)} BIST symbols...")
    raw = yf.download(
        symbols,
        start=start,
        end=end,
        group_by="ticker",
        auto_adjust=True,
        progress=False,
        threads=True,
    )
    prices = flatten_price_download(raw, symbols)
    prices.to_csv(RAW_DIR / "yahoo_daily_prices.csv", index=False)

    coverage = (
        prices.groupby("ticker")
        .agg(start=("date", "min"), end=("date", "max"), observations=("date", "size"))
        .reset_index()
        .sort_values("ticker")
    )
    coverage.to_csv(RAW_DIR / "price_coverage.csv", index=False)

    universe = pd.DataFrame(
        {
            "ticker": [s.replace(".IS", "") for s in symbols],
            "yahoo_symbol": symbols,
            "role": [
                "index" if s in index_symbols else "stock"
                for s in symbols
            ],
        }
    )
    universe.to_csv(RAW_DIR / "universe.csv", index=False)

    print(f"Saved {len(prices):,} daily price rows.")
    return prices


def download_fundamentals(config: dict) -> None:
    stock_symbols = [yahoo_symbol(t) for t in config["stock_tickers"]]
    all_rows = []
    info_rows = []
    errors = []

    print(f"Downloading public financial statements for {len(stock_symbols)} stocks...")
    for i, symbol in enumerate(stock_symbols, start=1):
        ticker = symbol.replace(".IS", "")
        print(f"  [{i:02d}/{len(stock_symbols)}] {symbol}")
        tk = yf.Ticker(symbol)

        try:
            info = tk.info or {}
            info_rows.append(
                {
                    "ticker": ticker,
                    "yahoo_symbol": symbol,
                    "long_name": info.get("longName"),
                    "currency": info.get("currency"),
                    "quote_type": info.get("quoteType"),
                    "trailing_pe_snapshot": info.get("trailingPE"),
                    "forward_pe_snapshot": info.get("forwardPE"),
                    "roe_snapshot": info.get("returnOnEquity"),
                    "market_cap_snapshot": info.get("marketCap"),
                    "snapshot_downloaded_at": datetime.now().isoformat(timespec="seconds"),
                }
            )
        except Exception as exc:  # noqa: BLE001 - data availability varies by ticker.
            errors.append({"ticker": ticker, "stage": "info", "error": repr(exc)})

        for frequency, getter_pairs in [
            (
                "annual",
                [
                    ("income_statement", "income_stmt"),
                    ("balance_sheet", "balance_sheet"),
                ],
            ),
            (
                "quarterly",
                [
                    ("income_statement", "quarterly_income_stmt"),
                    ("balance_sheet", "quarterly_balance_sheet"),
                ],
            ),
        ]:
            for statement, attr in getter_pairs:
                try:
                    df = getattr(tk, attr)
                    all_rows.append(statement_to_long(df, ticker, statement, frequency))
                except Exception as exc:  # noqa: BLE001
                    errors.append(
                        {
                            "ticker": ticker,
                            "stage": f"{frequency}_{statement}",
                            "error": repr(exc),
                        }
                    )

    fundamentals = (
        pd.concat(all_rows, ignore_index=True)
        if all_rows
        else pd.DataFrame(columns=["ticker", "frequency", "statement", "item", "period_end", "value"])
    )
    fundamentals.to_csv(RAW_DIR / "yahoo_fundamentals_long.csv", index=False)
    pd.DataFrame(info_rows).to_csv(RAW_DIR / "yahoo_info_snapshot.csv", index=False)
    pd.DataFrame(errors).to_csv(RAW_DIR / "download_errors.csv", index=False)
    print(f"Saved {len(fundamentals):,} fundamental rows.")


def main() -> None:
    config = load_config()
    download_prices(config)
    download_fundamentals(config)
    print("Data freeze complete. Run: py src/run_project.py")


if __name__ == "__main__":
    main()
