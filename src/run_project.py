"""Run the BIST factor investing project from frozen CSV data."""

from __future__ import annotations

import math
import os
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import backtrader as bt
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
import statsmodels.api as sm
import yaml
from matplotlib.backends.backend_pdf import PdfPages
from scipy import stats


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "project_config.yaml"


def project_path(env_name: str, default: str) -> Path:
    return ROOT / os.environ.get(env_name, default)


DATA_SOURCE_LABEL = os.environ.get("PROJECT_DATA_SOURCE_LABEL", "Yahoo Finance frozen CSV")
RAW_DIR = project_path("PROJECT_RAW_DIR", "data/raw")
PROCESSED_DIR = project_path("PROJECT_PROCESSED_DIR", "data/processed")
RESULTS_DIR = project_path("PROJECT_RESULTS_DIR", "results")
FIGURES_DIR = project_path("PROJECT_FIGURES_DIR", "figures")
PRESENTATION_DIR = project_path("PROJECT_PRESENTATION_DIR", "presentation")
PRICE_FILE_NAME = os.environ.get("PROJECT_PRICE_FILE", "yahoo_daily_prices.csv")
FUNDAMENTALS_FILE_NAME = os.environ.get("PROJECT_FUNDAMENTALS_FILE", "yahoo_fundamentals_long.csv")
RATIO_FILE_NAME = os.environ.get("PROJECT_RATIO_FILE", "")

FACTOR_COLS = ["roe", "pe", "momentum", "trend"]
INDEX_TICKERS = {"XU100", "XU030", "XBANK", "XUSIN"}


def fundamental_input_path() -> Path:
    return RAW_DIR / (RATIO_FILE_NAME or FUNDAMENTALS_FILE_NAME)


def fundamental_input_label() -> str:
    return "BIST monthly ratio CSV" if RATIO_FILE_NAME else "financial-statement CSV"


def ensure_dirs() -> None:
    for path in [PROCESSED_DIR, RESULTS_DIR, FIGURES_DIR, PRESENTATION_DIR]:
        path.mkdir(parents=True, exist_ok=True)


def load_config() -> dict:
    with CONFIG_PATH.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def read_csv_dates(path: Path, date_cols: Iterable[str]) -> pd.DataFrame:
    df = pd.read_csv(path)
    for col in date_cols:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
    return df


def month_end_panel(daily_close: pd.DataFrame) -> pd.DataFrame:
    return daily_close.sort_index().resample("ME").last()


def winsorize_cross_section(s: pd.Series, lower_q: float = 0.01, upper_q: float = 0.99) -> pd.Series:
    s = s.astype(float)
    valid = s.dropna()
    if len(valid) < 3:
        return s
    lower = valid.quantile(lower_q)
    upper = valid.quantile(upper_q)
    return s.clip(lower=lower, upper=upper)


def zscore_cross_section(s: pd.Series) -> pd.Series:
    s = winsorize_cross_section(s)
    valid = s.dropna()
    if len(valid) < 3 or valid.std(ddof=1) == 0:
        return pd.Series(np.nan, index=s.index)
    return (s - valid.mean()) / valid.std(ddof=1)


def max_drawdown(returns: pd.Series) -> float:
    returns = returns.dropna()
    if returns.empty:
        return np.nan
    cum = (1 + returns).cumprod()
    return float((cum / cum.cummax() - 1).min())


def perf_metrics(returns: pd.Series, name: str, periods_per_year: int = 12) -> dict:
    r = returns.dropna().astype(float)
    if r.empty:
        return {
            "name": name,
            "observations": 0,
            "avg_return": np.nan,
            "ann_return": np.nan,
            "ann_vol": np.nan,
            "sharpe": np.nan,
            "max_drawdown": np.nan,
            "t_stat": np.nan,
            "p_value": np.nan,
            "skew": np.nan,
            "excess_kurtosis": np.nan,
            "positive_pct": np.nan,
    }

    vol = r.std(ddof=1)
    if len(r) >= 2 and vol > 0:
        t_stat, p_value = stats.ttest_1samp(r, 0.0, nan_policy="omit")
    else:
        t_stat, p_value = np.nan, np.nan
    return {
        "name": name,
        "observations": int(len(r)),
        "avg_return": float(r.mean()),
        "ann_return": float(r.mean() * periods_per_year),
        "ann_vol": float(vol * np.sqrt(periods_per_year)),
        "sharpe": float((r.mean() / vol) * np.sqrt(periods_per_year)) if vol > 0 else np.nan,
        "max_drawdown": max_drawdown(r),
        "t_stat": float(t_stat) if pd.notna(t_stat) else np.nan,
        "p_value": float(p_value) if pd.notna(p_value) else np.nan,
        "skew": float(r.skew()),
        "excess_kurtosis": float(r.kurtosis()),
        "positive_pct": float((r > 0).mean()),
    }


def fmt_pct(value: float | int | None, digits: int = 2) -> str:
    if value is None or pd.isna(value):
        return "N/A"
    return f"{float(value) * 100:.{digits}f}%"


def fmt_num(value: float | int | None, digits: int = 2) -> str:
    if value is None or pd.isna(value):
        return "N/A"
    return f"{float(value):.{digits}f}"


def load_price_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    prices_path = RAW_DIR / PRICE_FILE_NAME
    if not prices_path.exists():
        raise FileNotFoundError(f"Missing {prices_path.relative_to(ROOT)}.")

    daily = read_csv_dates(prices_path, ["date"])
    daily = daily.dropna(subset=["date", "ticker", "close"])
    daily["ticker"] = daily["ticker"].astype(str)
    for col in ["open", "high", "low", "close", "volume"]:
        if col in daily.columns:
            daily[col] = pd.to_numeric(daily[col], errors="coerce")

    daily_close = daily.pivot_table(index="date", columns="ticker", values="close", aggfunc="last")
    daily_close = daily_close.sort_index()
    monthly_close = month_end_panel(daily_close)
    monthly_returns = monthly_close.pct_change(fill_method=None)

    universe_path = RAW_DIR / "universe.csv"
    if universe_path.exists():
        universe = pd.read_csv(universe_path)
        price_tickers = set(daily_close.columns)
        audit = universe.copy()
        audit["has_price_data"] = audit["ticker"].isin(price_tickers)
        audit["included_in_stock_portfolio"] = (audit["role"] == "stock") & audit["has_price_data"]
        audit.to_csv(RESULTS_DIR / "universe_price_audit.csv", index=False)

    daily.to_csv(PROCESSED_DIR / "daily_prices_clean.csv", index=False)
    monthly_close.to_csv(PROCESSED_DIR / "monthly_close.csv", index_label="date")
    monthly_returns.to_csv(PROCESSED_DIR / "monthly_returns.csv", index_label="date")
    return daily, monthly_close, monthly_returns


def find_statement_series(
    fundamentals: pd.DataFrame,
    ticker: str,
    frequency: str,
    statement: str | None,
    candidates: list[str],
) -> pd.Series:
    subset = fundamentals[
        (fundamentals["ticker"] == ticker)
        & (fundamentals["frequency"] == frequency)
    ].copy()
    if statement is not None:
        subset = subset[subset["statement"] == statement]
    if subset.empty:
        return pd.Series(dtype=float)

    subset["item_norm"] = subset["item"].str.lower().str.replace(r"[^a-z0-9]+", " ", regex=True).str.strip()
    candidate_norm = [
        c.lower().replace("_", " ").replace("-", " ").strip()
        for c in candidates
    ]
    for candidate in candidate_norm:
        exact = subset[subset["item_norm"] == candidate]
        if exact.empty:
            exact = subset[subset["item_norm"].str.contains(candidate, regex=False, na=False)]
        if not exact.empty:
            out = exact.sort_values("period_end").groupby("period_end")["value"].last()
            out.index = pd.to_datetime(out.index)
            return out.astype(float).sort_index()
    return pd.Series(dtype=float)


def event_to_monthly(series: pd.Series, monthly_index: pd.DatetimeIndex, lag_days: int) -> pd.Series:
    if series.empty:
        return pd.Series(np.nan, index=monthly_index)
    s = series.copy().dropna()
    s.index = pd.to_datetime(s.index) + pd.to_timedelta(lag_days, unit="D")
    s = s[~s.index.duplicated(keep="last")].sort_index()
    expanded_index = monthly_index.union(s.index)
    return s.reindex(expanded_index).sort_index().ffill().reindex(monthly_index)


def build_ratio_panels_from_file(ratio_path: Path, monthly_close: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    ratios = read_csv_dates(ratio_path, ["date"])
    required = {"date", "ticker", "roe", "pe"}
    missing = sorted(required.difference(ratios.columns))
    if missing:
        raise ValueError(
            f"{ratio_path.relative_to(ROOT)} is missing required columns: {', '.join(missing)}. "
            "Build it with src/build_bist_datastore_ratios.py from BIST DataStore monthly ratio files."
        )

    monthly_index = monthly_close.index
    stock_cols = [c for c in monthly_close.columns if c not in INDEX_TICKERS]
    ratios = ratios.dropna(subset=["date", "ticker"]).copy()
    ratios["ticker"] = ratios["ticker"].astype(str).str.upper().str.replace(r"\.E$", "", regex=True)
    ratios["date"] = ratios["date"].dt.to_period("M").dt.to_timestamp("M")
    ratios["roe"] = pd.to_numeric(ratios["roe"], errors="coerce").replace([np.inf, -np.inf], np.nan)
    ratios["pe"] = pd.to_numeric(ratios["pe"], errors="coerce").replace([np.inf, -np.inf], np.nan)
    ratios.loc[ratios["pe"] <= 0, "pe"] = np.nan
    ratios = ratios[ratios["ticker"].isin(stock_cols)]

    if ratios.empty:
        raise ValueError(
            f"{ratio_path.relative_to(ROOT)} contains no rows matching the configured BIST stock universe."
        )

    roe_panel = ratios.pivot_table(index="date", columns="ticker", values="roe", aggfunc="last")
    pe_panel = ratios.pivot_table(index="date", columns="ticker", values="pe", aggfunc="last")
    roe_panel = roe_panel.reindex(index=monthly_index, columns=stock_cols)
    pe_panel = pe_panel.reindex(index=monthly_index, columns=stock_cols)
    eps_panel = pd.DataFrame(np.nan, index=monthly_index, columns=stock_cols)

    coverage_rows = []
    for ticker in stock_cols:
        ticker_rows = ratios[ratios["ticker"] == ticker]
        coverage_rows.append(
            {
                "ticker": ticker,
                "roe_months": int(roe_panel[ticker].notna().sum()),
                "pe_months": int(pe_panel[ticker].notna().sum()),
                "ratio_rows": int(len(ticker_rows)),
                "first_ratio_date": ticker_rows["date"].min() if not ticker_rows.empty else pd.NaT,
                "last_ratio_date": ticker_rows["date"].max() if not ticker_rows.empty else pd.NaT,
                "source": ratio_path.name,
            }
        )

    roe_panel.to_csv(PROCESSED_DIR / "roe_panel.csv", index_label="date")
    pe_panel.to_csv(PROCESSED_DIR / "pe_panel.csv", index_label="date")
    eps_panel.to_csv(PROCESSED_DIR / "eps_panel.csv", index_label="date")
    pd.DataFrame(coverage_rows).to_csv(RESULTS_DIR / "fundamental_coverage.csv", index=False)
    (RESULTS_DIR / "fundamental_data_source.txt").write_text(
        "\n".join(
            [
                "Fundamental Data Source",
                "=======================",
                f"Input: {ratio_path.relative_to(ROOT)}",
                "ROE is net_profit_ttm / equity from BIST monthly valuation-ratio data.",
                "P/E is the positive F/K field from the same BIST monthly valuation-ratio data.",
                "No Yahoo Finance fundamental data is used when PROJECT_RATIO_FILE is set.",
            ]
        ),
        encoding="utf-8",
    )
    return roe_panel, pe_panel, eps_panel


def build_fundamental_panels(config: dict, monthly_close: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if RATIO_FILE_NAME:
        ratio_path = RAW_DIR / RATIO_FILE_NAME
        if not ratio_path.exists():
            raise FileNotFoundError(
                f"Missing {ratio_path.relative_to(ROOT)}. "
                "For a BIST-native run, place monthly DataStore degoran_M_YYYYMM.zip/ORANYYYYMM.xls files under "
                "data_bist/raw/datastore_basic_ratios and run src/build_bist_datastore_ratios.py first."
            )
        return build_ratio_panels_from_file(ratio_path, monthly_close)

    fundamentals_path = RAW_DIR / FUNDAMENTALS_FILE_NAME
    if not fundamentals_path.exists():
        raise FileNotFoundError(f"Missing {fundamentals_path.relative_to(ROOT)}.")

    fundamentals = read_csv_dates(fundamentals_path, ["period_end"])
    fundamentals["ticker"] = fundamentals["ticker"].astype(str)
    monthly_index = monthly_close.index
    stock_cols = [c for c in monthly_close.columns if c not in INDEX_TICKERS]

    ni_candidates = [
        "Net Income",
        "Net Income Common Stockholders",
        "Net Income From Continuing Operation Net Minority Interest",
        "Normalized Income",
    ]
    equity_candidates = [
        "Stockholders Equity",
        "Common Stock Equity",
        "Total Equity Gross Minority Interest",
    ]
    shares_candidates = [
        "Ordinary Shares Number",
        "Share Issued",
        "Diluted Average Shares",
        "Basic Average Shares",
    ]

    annual_lag = int(config["project"]["fundamental_lag_days_annual"])
    quarterly_lag = int(config["project"]["fundamental_lag_days_quarterly"])
    roe_panel = pd.DataFrame(index=monthly_index, columns=stock_cols, dtype=float)
    pe_panel = pd.DataFrame(index=monthly_index, columns=stock_cols, dtype=float)
    eps_panel = pd.DataFrame(index=monthly_index, columns=stock_cols, dtype=float)
    coverage_rows = []

    for ticker in stock_cols:
        # Annual values extend history; quarterly TTM values improve recency.
        ni_a = find_statement_series(fundamentals, ticker, "annual", "income_statement", ni_candidates)
        eq_a = find_statement_series(fundamentals, ticker, "annual", "balance_sheet", equity_candidates)
        sh_a = find_statement_series(fundamentals, ticker, "annual", None, shares_candidates)
        roe_a = ni_a / eq_a.reindex(ni_a.index, method="nearest") if not ni_a.empty and not eq_a.empty else pd.Series(dtype=float)
        eps_a = ni_a / sh_a.reindex(ni_a.index, method="nearest") if not ni_a.empty and not sh_a.empty else pd.Series(dtype=float)

        ni_q = find_statement_series(fundamentals, ticker, "quarterly", "income_statement", ni_candidates)
        eq_q = find_statement_series(fundamentals, ticker, "quarterly", "balance_sheet", equity_candidates)
        sh_q = find_statement_series(fundamentals, ticker, "quarterly", None, shares_candidates)
        ni_ttm = ni_q.rolling(4, min_periods=4).sum() if not ni_q.empty else pd.Series(dtype=float)
        roe_q = (
            ni_ttm / eq_q.reindex(ni_ttm.index, method="nearest")
            if not ni_ttm.empty and not eq_q.empty
            else pd.Series(dtype=float)
        )
        eps_q = (
            ni_ttm / sh_q.reindex(ni_ttm.index, method="nearest")
            if not ni_ttm.empty and not sh_q.empty
            else pd.Series(dtype=float)
        )

        roe_m = event_to_monthly(roe_a, monthly_index, annual_lag)
        eps_m = event_to_monthly(eps_a, monthly_index, annual_lag)
        roe_q_m = event_to_monthly(roe_q, monthly_index, quarterly_lag)
        eps_q_m = event_to_monthly(eps_q, monthly_index, quarterly_lag)

        roe = roe_q_m.combine_first(roe_m)
        eps = eps_q_m.combine_first(eps_m)
        close = monthly_close[ticker]
        pe = close / eps
        pe[(eps <= 0) | (pe <= 0)] = np.nan

        roe_panel[ticker] = roe.replace([np.inf, -np.inf], np.nan)
        eps_panel[ticker] = eps.replace([np.inf, -np.inf], np.nan)
        pe_panel[ticker] = pe.replace([np.inf, -np.inf], np.nan)
        coverage_rows.append(
            {
                "ticker": ticker,
                "roe_months": int(roe_panel[ticker].notna().sum()),
                "pe_months": int(pe_panel[ticker].notna().sum()),
                "annual_income_points": int(ni_a.notna().sum()),
                "quarterly_income_points": int(ni_q.notna().sum()),
            }
        )

    roe_panel.to_csv(PROCESSED_DIR / "roe_panel.csv", index_label="date")
    pe_panel.to_csv(PROCESSED_DIR / "pe_panel.csv", index_label="date")
    eps_panel.to_csv(PROCESSED_DIR / "eps_panel.csv", index_label="date")
    pd.DataFrame(coverage_rows).to_csv(RESULTS_DIR / "fundamental_coverage.csv", index=False)
    return roe_panel, pe_panel, eps_panel


def compute_momentum(monthly_close: pd.DataFrame, stock_cols: list[str]) -> pd.DataFrame:
    # Project formula: P_t / P_{t-12} - 1.
    return monthly_close[stock_cols] / monthly_close[stock_cols].shift(12) - 1


def compute_month_end_mads(daily_close: pd.Series, lags: list[int]) -> pd.DataFrame:
    out = pd.DataFrame(index=daily_close.index)
    for lag in lags:
        ma = daily_close.rolling(lag, min_periods=lag).mean()
        out[f"mad_{lag}"] = daily_close / ma - 1
    return out.resample("ME").last()


def fit_trend_regression(
    daily_close: pd.DataFrame,
    monthly_returns: pd.DataFrame,
    lags: list[int],
    alpha: float = 0.05,
    include_intercept: bool = False,
) -> tuple[pd.Series, pd.DataFrame, pd.DataFrame]:
    if "XU100" not in daily_close.columns or "XU100" not in monthly_returns.columns:
        raise ValueError("XU100 index data is required for the trend-factor regression.")

    xu_mads = compute_month_end_mads(daily_close["XU100"].dropna(), lags)
    target = monthly_returns["XU100"].shift(-1).rename("next_ret")
    reg_df = xu_mads.join(target).dropna()
    feature_cols = list(xu_mads.columns)

    if len(reg_df) < len(feature_cols) + 12:
        raise ValueError("Not enough XU100 observations for the trend-factor regression.")

    def fit_model(cols: list[str], with_intercept: bool) -> sm.regression.linear_model.RegressionResultsWrapper:
        x = reg_df[cols]
        if with_intercept:
            x = sm.add_constant(x, has_constant="add")
        return sm.OLS(reg_df["next_ret"], x).fit()

    # Diagnostic only: a conventional intercept absorbs the average BIST100 drift.
    # We save this so the presentation can disclose the sensitivity of the trend factor.
    diagnostic_model = fit_model(feature_cols, True)
    pd.DataFrame(
        {
            "term": diagnostic_model.params.index,
            "coef": diagnostic_model.params.values,
            "p_value": diagnostic_model.pvalues.reindex(diagnostic_model.params.index).values,
            "t_stat": diagnostic_model.tvalues.reindex(diagnostic_model.params.index).values,
            "r_squared": diagnostic_model.rsquared,
            "observations": int(diagnostic_model.nobs),
        }
    ).to_csv(RESULTS_DIR / "trend_regression_with_intercept_diagnostic.csv", index=False)

    # Primary project specification: the intercept is not used because it is common to
    # all stocks and disappears after cross-sectional z-scoring/ranking. This follows
    # the article's forecast equation, which ranks stocks using only MA-signal terms.
    selected = feature_cols.copy()
    dropped_rows = []
    while len(selected) > 1:
        model = fit_model(selected, include_intercept)
        pvalues = model.pvalues.drop("const", errors="ignore")
        worst = pvalues.idxmax()
        if pvalues.loc[worst] <= alpha:
            break
        dropped_rows.append(
            {
                "dropped_variable": worst,
                "p_value": float(pvalues.loc[worst]),
                "remaining_before_drop": len(selected),
            }
        )
        selected.remove(worst)

    model = fit_model(selected, include_intercept)
    selected_pvalues = model.pvalues.drop("const", errors="ignore")
    if selected_pvalues.empty or selected_pvalues.max() > alpha:
        raise ValueError(
            "No BIST100 moving-average deviation survived the trend regression significance filter. "
            "Check results/trend_regression_with_intercept_diagnostic.csv and consider disclosing "
            "that the trend factor is not supported by the frozen data."
        )

    coef = model.params
    summary = pd.DataFrame(
        {
            "term": coef.index,
            "coef": coef.values,
            "p_value": model.pvalues.reindex(coef.index).values,
            "t_stat": model.tvalues.reindex(coef.index).values,
            "r_squared": model.rsquared,
            "observations": int(model.nobs),
            "selection_alpha": float(alpha),
            "include_intercept": bool(include_intercept),
        }
    )
    summary.to_csv(RESULTS_DIR / "trend_regression_coefficients.csv", index=False)
    pd.DataFrame(dropped_rows).to_csv(RESULTS_DIR / "trend_regression_dropped_variables.csv", index=False)
    note = [
        "Trend Regression Selection Note",
        "=" * 31,
        "The project requires a BIST100 predictive regression and dropping non-significant MA-deviation variables.",
        f"Primary selection uses alpha={alpha:.2f} and include_intercept={include_intercept}.",
        "The intercept is excluded because it is common to all stocks and is removed by cross-sectional z-scoring/ranking.",
        "A with-intercept diagnostic is saved separately; in the frozen data, the intercept absorbs much of the average index drift.",
        f"Selected MA variables: {', '.join(selected)}.",
    ]
    (RESULTS_DIR / "trend_regression_selection_note.txt").write_text("\n".join(note), encoding="utf-8")
    xu_mads.to_csv(PROCESSED_DIR / "xu100_monthly_ma_deviations.csv", index_label="date")
    return coef, xu_mads, reg_df


def compute_trend_factor(daily_close: pd.DataFrame, stock_cols: list[str], lags: list[int], coef: pd.Series) -> pd.DataFrame:
    trend = pd.DataFrame(index=month_end_panel(daily_close).index, columns=stock_cols, dtype=float)
    selected_mads = [c for c in coef.index if c != "const"]
    intercept = float(coef.get("const", 0.0))

    for ticker in stock_cols:
        if ticker not in daily_close.columns:
            continue
        mads = compute_month_end_mads(daily_close[ticker].dropna(), lags)
        missing = [c for c in selected_mads if c not in mads.columns]
        if missing:
            continue
        trend[ticker] = intercept + mads[selected_mads].mul(coef[selected_mads], axis=1).sum(axis=1)
    return trend


def build_factor_panels(
    config: dict,
    daily: pd.DataFrame,
    monthly_close: pd.DataFrame,
    monthly_returns: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.Series]:
    daily_close = daily.pivot_table(index="date", columns="ticker", values="close", aggfunc="last").sort_index()
    stock_cols = [
        c
        for c in monthly_close.columns
        if c not in INDEX_TICKERS and monthly_close[c].notna().sum() >= int(config["project"]["min_months_for_stock"])
    ]

    roe_panel, pe_panel, _ = build_fundamental_panels(config, monthly_close)
    momentum_panel = compute_momentum(monthly_close, stock_cols)
    coef, _, _ = fit_trend_regression(
        daily_close,
        monthly_returns,
        config["moving_average_lags"],
        alpha=float(config["project"].get("trend_significance_level", 0.05)),
        include_intercept=bool(config["project"].get("trend_regression_include_intercept", False)),
    )
    trend_panel = compute_trend_factor(daily_close, stock_cols, config["moving_average_lags"], coef)

    raw = []
    for date in monthly_close.index:
        for ticker in stock_cols:
            raw.append(
                {
                    "date": date,
                    "ticker": ticker,
                    "roe": roe_panel.get(ticker, pd.Series(index=monthly_close.index, dtype=float)).get(date, np.nan),
                    "pe_ratio": pe_panel.get(ticker, pd.Series(index=monthly_close.index, dtype=float)).get(date, np.nan),
                    "pe": -pe_panel.get(ticker, pd.Series(index=monthly_close.index, dtype=float)).get(date, np.nan),
                    "momentum": momentum_panel.get(ticker, pd.Series(index=monthly_close.index, dtype=float)).get(date, np.nan),
                    "trend": trend_panel.get(ticker, pd.Series(index=monthly_close.index, dtype=float)).get(date, np.nan),
                }
            )
    factor_raw = pd.DataFrame(raw)
    factor_raw.to_csv(PROCESSED_DIR / "factor_raw_long.csv", index=False)

    z_rows = []
    for date, group in factor_raw.groupby("date"):
        out = group[["date", "ticker", "pe_ratio"]].copy()
        for factor in FACTOR_COLS:
            out[factor] = zscore_cross_section(group.set_index("ticker")[factor]).reindex(group["ticker"]).values
        out["available_factor_count"] = out[FACTOR_COLS].notna().sum(axis=1)
        out["composite_all4"] = out[FACTOR_COLS].mean(axis=1).where(out["available_factor_count"] == 4)
        out["composite_min2"] = out[FACTOR_COLS].mean(axis=1).where(out["available_factor_count"] >= 2)
        z_rows.append(out)
    factor_z = pd.concat(z_rows, ignore_index=True)
    factor_z.to_csv(PROCESSED_DIR / "factor_zscores_long.csv", index=False)

    coverage = (
        factor_z.groupby("date")
        .agg(
            stocks_with_roe=("roe", lambda s: int(s.notna().sum())),
            stocks_with_pe=("pe", lambda s: int(s.notna().sum())),
            stocks_with_momentum=("momentum", lambda s: int(s.notna().sum())),
            stocks_with_trend=("trend", lambda s: int(s.notna().sum())),
            stocks_all4=("composite_all4", lambda s: int(s.notna().sum())),
            stocks_min2=("composite_min2", lambda s: int(s.notna().sum())),
        )
        .reset_index()
    )
    coverage.to_csv(RESULTS_DIR / "monthly_factor_coverage.csv", index=False)

    all4_months = coverage["stocks_all4"].ge(config["project"]["min_stocks_for_quintiles"]).sum()
    selected_score = "composite_all4" if all4_months >= 12 else "composite_min2"
    pd.Series({"selected_composite_score": selected_score, "all4_usable_months": int(all4_months)}).to_csv(
        RESULTS_DIR / "selected_strategy_score.csv", header=False
    )
    return factor_raw, factor_z, monthly_returns[stock_cols], daily_close, coef


def factor_wide(factor_z: pd.DataFrame, column: str) -> pd.DataFrame:
    out = factor_z.pivot(index="date", columns="ticker", values=column)
    out.index = pd.to_datetime(out.index)
    return out.sort_index()


def next_date(index: pd.DatetimeIndex, date: pd.Timestamp) -> pd.Timestamp | None:
    loc = index.searchsorted(date)
    while loc < len(index) and index[loc] <= date:
        loc += 1
    if loc >= len(index):
        return None
    return index[loc]


def build_portfolio_sort_fmp(
    signal_wide: pd.DataFrame,
    returns_wide: pd.DataFrame,
    factor_name: str,
    n_quintiles: int = 5,
    min_stocks: int = 10,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows = []
    weight_rows = []
    return_index = returns_wide.index
    for signal_date, signal in signal_wide.iterrows():
        ret_date = next_date(return_index, signal_date)
        if ret_date is None:
            continue
        ret = returns_wide.loc[ret_date]
        common = signal.dropna().index.intersection(ret.dropna().index)
        if len(common) < min_stocks:
            continue
        sig = signal.loc[common]
        realized = ret.loc[common]
        try:
            q = pd.qcut(sig, n_quintiles, labels=range(1, n_quintiles + 1), duplicates="drop")
        except ValueError:
            continue
        if len(pd.unique(q.dropna())) < n_quintiles:
            continue
        df = pd.DataFrame({"signal": sig, "return": realized, "q": q})
        q_ret = df.groupby("q", observed=False)["return"].mean()
        row = {
            "factor": factor_name,
            "signal_date": signal_date,
            "date": ret_date,
            "n_stocks": int(len(common)),
            "Q1": float(q_ret.loc[1]),
            "Q2": float(q_ret.loc[2]),
            "Q3": float(q_ret.loc[3]),
            "Q4": float(q_ret.loc[4]),
            "Q5": float(q_ret.loc[5]),
            "long_short": float(q_ret.loc[5] - q_ret.loc[1]),
        }
        rows.append(row)

        long_names = df.index[df["q"] == 5]
        short_names = df.index[df["q"] == 1]
        for ticker in long_names:
            weight_rows.append({"factor": factor_name, "signal_date": signal_date, "ticker": ticker, "method": "portfolio_sort", "weight": 1 / len(long_names)})
        for ticker in short_names:
            weight_rows.append({"factor": factor_name, "signal_date": signal_date, "ticker": ticker, "method": "portfolio_sort", "weight": -1 / len(short_names)})
    return pd.DataFrame(rows), pd.DataFrame(weight_rows)


def build_regression_fmp(
    signal_wide: pd.DataFrame,
    returns_wide: pd.DataFrame,
    factor_name: str,
    min_stocks: int = 10,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows = []
    weights = []
    return_index = returns_wide.index
    for signal_date, signal in signal_wide.iterrows():
        ret_date = next_date(return_index, signal_date)
        if ret_date is None:
            continue
        ret = returns_wide.loc[ret_date]
        common = signal.dropna().index.intersection(ret.dropna().index)
        if len(common) < min_stocks:
            continue
        x = signal.loc[common].astype(float)
        y = ret.loc[common].astype(float)
        if x.std(ddof=1) == 0:
            continue
        design = pd.DataFrame({"const": 1.0, "signal": x}, index=x.index)
        model = sm.OLS(y, design).fit()
        if "signal" not in model.params:
            continue
        slope = model.params["signal"]
        x_demeaned = x - x.mean()
        denom = float((x_demeaned**2).sum())
        if denom == 0:
            continue
        h = x_demeaned / denom
        rows.append(
            {
                "factor": factor_name,
                "signal_date": signal_date,
                "date": ret_date,
                "n_stocks": int(len(common)),
                "long_short": float(slope),
                "t_stat_cross_section": float(model.tvalues.get("signal", np.nan)),
                "r_squared": float(model.rsquared),
            }
        )
        for ticker, weight in h.items():
            weights.append(
                {
                    "factor": factor_name,
                    "signal_date": signal_date,
                    "ticker": ticker,
                    "method": "cross_sectional_regression",
                    "weight": float(weight),
                }
            )
    return pd.DataFrame(rows), pd.DataFrame(weights)


def compute_ic(signal_wide: pd.DataFrame, returns_wide: pd.DataFrame, factor_name: str, min_stocks: int) -> pd.DataFrame:
    rows = []
    for signal_date, signal in signal_wide.iterrows():
        ret_date = next_date(returns_wide.index, signal_date)
        if ret_date is None:
            continue
        ret = returns_wide.loc[ret_date]
        common = signal.dropna().index.intersection(ret.dropna().index)
        if len(common) < min_stocks:
            continue
        x = signal.loc[common]
        y = ret.loc[common]
        raw_ic = x.corr(y)
        rank_ic = x.rank().corr(y.rank())
        rows.append(
            {
                "factor": factor_name,
                "signal_date": signal_date,
                "date": ret_date,
                "n_stocks": int(len(common)),
                "raw_ic": float(raw_ic) if pd.notna(raw_ic) else np.nan,
                "rank_ic": float(rank_ic) if pd.notna(rank_ic) else np.nan,
            }
        )
    return pd.DataFrame(rows)


def write_fmp_common_start_metrics(sort_returns: pd.DataFrame, reg_returns: pd.DataFrame) -> None:
    rows = []
    for method, df in [
        ("portfolio_sort", sort_returns),
        ("cross_sectional_regression", reg_returns),
    ]:
        if df.empty:
            continue
        work = df.copy()
        work["date"] = pd.to_datetime(work["date"])
        first_dates = work.groupby("factor")["date"].min()
        if first_dates.empty:
            continue
        common_start = first_dates.max()
        for factor in FACTOR_COLS:
            series = (
                work.loc[work["factor"] == factor]
                .set_index("date")["long_short"]
                .sort_index()
            )
            common_series = series[series.index >= common_start]
            row = perf_metrics(common_series, f"{factor}_{method}_common_start")
            row.update(
                {
                    "factor": factor,
                    "method": method,
                    "common_start_date": common_start,
                    "original_start_date": series.index.min() if not series.empty else pd.NaT,
                }
            )
            rows.append(row)
    pd.DataFrame(rows).to_csv(RESULTS_DIR / "fmp_common_start_metrics.csv", index=False)


def write_fmp_method_comparison(sort_returns: pd.DataFrame, reg_returns: pd.DataFrame) -> None:
    rows = []
    if sort_returns.empty or reg_returns.empty:
        pd.DataFrame(rows).to_csv(RESULTS_DIR / "fmp_method_comparison.csv", index=False)
        return

    sort_work = sort_returns.copy()
    reg_work = reg_returns.copy()
    sort_work["date"] = pd.to_datetime(sort_work["date"])
    reg_work["date"] = pd.to_datetime(reg_work["date"])

    for factor in FACTOR_COLS:
        s = sort_work.loc[sort_work["factor"] == factor].set_index("date")["long_short"].sort_index()
        r = reg_work.loc[reg_work["factor"] == factor].set_index("date")["long_short"].sort_index()
        both = pd.concat({"portfolio_sort": s, "cross_sectional_regression": r}, axis=1).dropna()
        if both.empty:
            rows.append({"factor": factor, "common_observations": 0})
            continue
        corr = both["portfolio_sort"].corr(both["cross_sectional_regression"])
        same_sign = np.sign(both["portfolio_sort"]) == np.sign(both["cross_sectional_regression"])
        rows.append(
            {
                "factor": factor,
                "common_start_date": both.index.min(),
                "common_end_date": both.index.max(),
                "common_observations": int(len(both)),
                "method_return_correlation": float(corr) if pd.notna(corr) else np.nan,
                "same_sign_pct": float(same_sign.mean()),
                "portfolio_sort_avg_monthly_return": float(both["portfolio_sort"].mean()),
                "regression_avg_monthly_return": float(both["cross_sectional_regression"].mean()),
                "portfolio_sort_sharpe": perf_metrics(both["portfolio_sort"], "sort")["sharpe"],
                "regression_sharpe": perf_metrics(both["cross_sectional_regression"], "reg")["sharpe"],
                "qualitatively_similar": bool(pd.notna(corr) and corr > 0 and same_sign.mean() >= 0.5),
            }
        )
    pd.DataFrame(rows).to_csv(RESULTS_DIR / "fmp_method_comparison.csv", index=False)


def analyze_factors(config: dict, factor_z: pd.DataFrame, returns_wide: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    min_stocks = int(config["project"]["min_stocks_for_quintiles"])
    all_sort = []
    all_reg = []
    all_weights = []
    all_ic = []

    for factor in FACTOR_COLS:
        signal = factor_wide(factor_z, factor)
        sort_df, sort_weights = build_portfolio_sort_fmp(signal, returns_wide, factor, min_stocks=min_stocks)
        reg_df, reg_weights = build_regression_fmp(signal, returns_wide, factor, min_stocks=min_stocks)
        ic_df = compute_ic(signal, returns_wide, factor, min_stocks=min_stocks)
        all_sort.append(sort_df)
        all_reg.append(reg_df)
        all_weights.append(sort_weights)
        all_weights.append(reg_weights)
        all_ic.append(ic_df)

    sort_returns = pd.concat(all_sort, ignore_index=True) if all_sort else pd.DataFrame()
    reg_returns = pd.concat(all_reg, ignore_index=True) if all_reg else pd.DataFrame()
    weights = pd.concat(all_weights, ignore_index=True) if all_weights else pd.DataFrame()
    ic = pd.concat(all_ic, ignore_index=True) if all_ic else pd.DataFrame()

    sort_returns.to_csv(RESULTS_DIR / "fmp_portfolio_sort_returns.csv", index=False)
    reg_returns.to_csv(RESULTS_DIR / "fmp_regression_returns.csv", index=False)
    weights.to_csv(RESULTS_DIR / "fmp_weights_all_dates.csv", index=False)
    ic.to_csv(RESULTS_DIR / "information_coefficients.csv", index=False)

    metrics = []
    for factor in FACTOR_COLS:
        s = sort_returns.loc[sort_returns["factor"] == factor].set_index("date")["long_short"] if not sort_returns.empty else pd.Series(dtype=float)
        r = reg_returns.loc[reg_returns["factor"] == factor].set_index("date")["long_short"] if not reg_returns.empty else pd.Series(dtype=float)
        metrics.append(perf_metrics(s, f"{factor}_portfolio_sort"))
        metrics.append(perf_metrics(r, f"{factor}_cross_sectional_regression"))
    metrics_df = pd.DataFrame(metrics)
    metrics_df.to_csv(RESULTS_DIR / "factor_performance_metrics.csv", index=False)
    write_fmp_common_start_metrics(sort_returns, reg_returns)
    write_fmp_method_comparison(sort_returns, reg_returns)

    ic_summary = (
        ic.groupby("factor")
        .agg(
            observations=("raw_ic", "count"),
            mean_raw_ic=("raw_ic", "mean"),
            mean_rank_ic=("rank_ic", "mean"),
            raw_ic_positive_pct=("raw_ic", lambda s: float((s > 0).mean())),
            rank_ic_positive_pct=("rank_ic", lambda s: float((s > 0).mean())),
        )
        .reset_index()
        if not ic.empty
        else pd.DataFrame()
    )
    ic_summary.to_csv(RESULTS_DIR / "information_coefficient_summary.csv", index=False)

    if not weights.empty:
        common_dates = sorted(set(sort_returns["signal_date"]).intersection(set(reg_returns["signal_date"]))) if not sort_returns.empty and not reg_returns.empty else []
        selected_date = common_dates[-1] if common_dates else weights["signal_date"].max()
        weights[weights["signal_date"] == selected_date].to_csv(RESULTS_DIR / "fmp_weights_selected_date.csv", index=False)

    return sort_returns, reg_returns, ic


def weighted_composite(factor_z: pd.DataFrame, weights: dict[str, float], min_count: int = 2) -> pd.DataFrame:
    out = factor_z[["date", "ticker"]].copy()
    weighted = pd.Series(0.0, index=factor_z.index)
    weight_sum = pd.Series(0.0, index=factor_z.index)
    count = pd.Series(0, index=factor_z.index)
    for factor, weight in weights.items():
        if factor not in factor_z.columns:
            continue
        valid = factor_z[factor].notna()
        weighted.loc[valid] += factor_z.loc[valid, factor] * float(weight)
        weight_sum.loc[valid] += abs(float(weight))
        count.loc[valid] += 1
    out["score"] = (weighted / weight_sum).where((weight_sum > 0) & (count >= min_count))
    return out.pivot(index="date", columns="ticker", values="score").sort_index()


def vectorized_top_n_strategy(
    score_wide: pd.DataFrame,
    returns_wide: pd.DataFrame,
    top_n: int,
    regime: pd.Series | None = None,
) -> tuple[pd.Series, pd.DataFrame]:
    rows = []
    pos_rows = []
    for signal_date, score in score_wide.iterrows():
        ret_date = next_date(returns_wide.index, pd.Timestamp(signal_date))
        if ret_date is None:
            continue
        if regime is not None:
            reg_value = regime.reindex([signal_date], method="ffill").iloc[0]
            if pd.isna(reg_value) or reg_value <= 0:
                rows.append({"signal_date": signal_date, "date": ret_date, "return": 0.0, "n_positions": 0})
                continue
        ret = returns_wide.loc[ret_date]
        common = score.dropna().index.intersection(ret.dropna().index)
        if len(common) == 0:
            continue
        selected = score.loc[common].sort_values(ascending=False).head(top_n)
        if selected.empty:
            continue
        selected_ret = ret.loc[selected.index]
        rows.append(
            {
                "signal_date": signal_date,
                "date": ret_date,
                "return": float(selected_ret.mean()),
                "n_positions": int(len(selected_ret)),
            }
        )
        for ticker, score_value in selected.items():
            pos_rows.append(
                {
                    "signal_date": signal_date,
                    "date": ret_date,
                    "ticker": ticker,
                    "score": float(score_value),
                    "weight": float(1 / len(selected_ret)),
                }
            )
    result = pd.DataFrame(rows)
    if result.empty:
        return pd.Series(dtype=float), pd.DataFrame()
    result["date"] = pd.to_datetime(result["date"])
    returns = result.set_index("date")["return"].sort_index()
    positions = pd.DataFrame(pos_rows)
    return returns, positions


def run_improvement_tests(
    config: dict,
    factor_z: pd.DataFrame,
    returns_wide: pd.DataFrame,
    monthly_close: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series]:
    xu = monthly_close["XU100"].dropna()
    regime = (xu > xu.rolling(10, min_periods=10).mean()).astype(float)
    regime.name = "xu100_above_10m_ma"
    regime.to_csv(PROCESSED_DIR / "xu100_regime_filter.csv", index_label="date")

    rows = []
    position_frames = []
    return_frames = []
    for score_name, weights in config["factor_weights"].items():
        min_count = 4 if score_name == "equal_all" else 2
        score = weighted_composite(factor_z, weights, min_count=min_count)
        score.to_csv(PROCESSED_DIR / f"score_{score_name}.csv", index_label="date")
        for top_n in [5, 10, 15]:
            for use_regime in [False, True]:
                rets, positions = vectorized_top_n_strategy(
                    score,
                    returns_wide,
                    top_n=top_n,
                    regime=regime if use_regime else None,
                )
                name = f"{score_name}_top{top_n}_{'regime' if use_regime else 'no_regime'}"
                row = perf_metrics(rets, name)
                row.update({"score_name": score_name, "top_n": top_n, "use_regime_filter": use_regime})
                rows.append(row)
                if not rets.empty:
                    return_frames.append(rets.rename(name))
                if not positions.empty:
                    positions["strategy"] = name
                    position_frames.append(positions)

    improvement = pd.DataFrame(rows).sort_values("sharpe", ascending=False)
    improvement.to_csv(RESULTS_DIR / "strategy_improvement_tests.csv", index=False)
    if position_frames:
        pd.concat(position_frames, ignore_index=True).to_csv(RESULTS_DIR / "vectorized_strategy_positions.csv", index=False)
    if return_frames:
        pd.concat(return_frames, axis=1).to_csv(RESULTS_DIR / "vectorized_strategy_returns.csv", index_label="date")

    # Base score selection mirrors factor coverage constraints.
    selected_path = RESULTS_DIR / "selected_strategy_score.csv"
    selected_score = "composite_min2"
    if selected_path.exists():
        selected_score = pd.read_csv(selected_path, header=None, index_col=0).iloc[0, 0]
    base_score = factor_wide(factor_z, selected_score)
    base_returns, base_positions = vectorized_top_n_strategy(base_score, returns_wide, top_n=10, regime=None)
    base_returns.to_csv(RESULTS_DIR / "base_monthly_top10_returns.csv", index_label="date")
    base_positions.to_csv(RESULTS_DIR / "base_monthly_top10_positions.csv", index=False)
    return improvement, base_positions, regime


def walk_forward_test(
    factor_z: pd.DataFrame,
    returns_wide: pd.DataFrame,
    config: dict,
    regime: pd.Series,
) -> pd.DataFrame:
    candidates = []
    for score_name, weights in config["factor_weights"].items():
        min_count = 4 if score_name == "equal_all" else 2
        score = weighted_composite(factor_z, weights, min_count=min_count)
        for top_n in [5, 10, 15]:
            for use_regime in [False, True]:
                rets, _ = vectorized_top_n_strategy(score, returns_wide, top_n, regime if use_regime else None)
                candidates.append((score_name, top_n, use_regime, rets))

    all_dates = sorted(set().union(*[set(r.index) for _, _, _, r in candidates if not r.empty]))
    all_dates = pd.DatetimeIndex(all_dates)
    rows = []
    train_window = 24
    test_window = 6
    start = 0
    step = 0
    while start + train_window + test_window <= len(all_dates):
        step += 1
        train_dates = all_dates[start : start + train_window]
        test_dates = all_dates[start + train_window : start + train_window + test_window]
        best = None
        best_sr = -np.inf
        for score_name, top_n, use_regime, rets in candidates:
            train = rets.reindex(train_dates).dropna()
            sr = perf_metrics(train, "tmp")["sharpe"]
            if pd.notna(sr) and sr > best_sr:
                best_sr = sr
                best = (score_name, top_n, use_regime, rets)
        if best is None:
            start += test_window
            continue
        score_name, top_n, use_regime, rets = best
        test = rets.reindex(test_dates).fillna(0.0)
        rows.append(
            {
                "step": step,
                "train_start": train_dates[0],
                "train_end": train_dates[-1],
                "test_start": test_dates[0],
                "test_end": test_dates[-1],
                "best_score_name": score_name,
                "best_top_n": top_n,
                "best_use_regime_filter": use_regime,
                "train_sharpe": best_sr,
                "test_return": float((1 + test).prod() - 1),
                "test_sharpe": perf_metrics(test, "test")["sharpe"],
            }
        )
        start += test_window

    wfa = pd.DataFrame(rows)
    wfa.to_csv(RESULTS_DIR / "walk_forward_results.csv", index=False)
    return wfa


class FactorPandasData(bt.feeds.PandasData):
    lines = ("score", "regime")
    params = (
        ("datetime", None),
        ("open", "open"),
        ("high", "high"),
        ("low", "low"),
        ("close", "close"),
        ("volume", "volume"),
        ("openinterest", -1),
        ("score", "score"),
        ("regime", "regime"),
    )


class FixedCashSizer(bt.Sizer):
    params = (("cash_per_trade", 100_000),)

    def _getsizing(self, comminfo, cash, data, isbuy):
        price = data.close[0]
        if price <= 0 or not math.isfinite(price):
            return 0
        size = int(self.p.cash_per_trade / price)
        if isbuy:
            return max(0, min(size, int(cash / price)))
        return size


class MonthlyFactorStrategy(bt.Strategy):
    params = dict(
        top_n=10,
        use_regime_filter=False,
        stop_loss_pct=None,
        take_profit_pct=None,
        printlog=False,
    )

    def __init__(self):
        self.index_data = self.datas[0]
        self.stocks = self.datas[1:]
        self.last_rebalance_month = None
        self.entry_prices = {}
        self.order_log = []
        self.trade_log = []
        self.position_log = []
        self.equity_curve = []

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return
        dt = bt.num2date(order.data.datetime[0]).date()
        self.order_log.append(
            {
                "date": dt,
                "ticker": order.data._name,
                "status": order.getstatusname(),
                "is_buy": bool(order.isbuy()),
                "size": float(order.executed.size),
                "price": float(order.executed.price),
                "value": float(order.executed.value),
                "commission": float(order.executed.comm),
            }
        )
        if order.status == order.Completed and order.isbuy():
            self.entry_prices[order.data._name] = float(order.executed.price)

    def notify_trade(self, trade):
        if trade.isclosed:
            self.trade_log.append(
                {
                    "entry_date": bt.num2date(trade.dtopen).date(),
                    "exit_date": bt.num2date(trade.dtclose).date(),
                    "ticker": trade.data._name,
                    "bars": int(trade.barlen),
                    "pnl": float(trade.pnl),
                    "pnl_net": float(trade.pnlcomm),
                }
            )

    def next(self):
        dt = self.index_data.datetime.date(0)
        self.equity_curve.append(
            {
                "date": dt,
                "cash": float(self.broker.getcash()),
                "value": float(self.broker.getvalue()),
            }
        )

        self._check_stops()
        month_key = (dt.year, dt.month)
        if self.last_rebalance_month == month_key:
            return
        self.last_rebalance_month = month_key
        self._rebalance(dt)

    def _check_stops(self):
        stop = self.p.stop_loss_pct
        take = self.p.take_profit_pct
        if stop is None and take is None:
            return
        for data in self.stocks:
            pos = self.getposition(data)
            if pos.size <= 0:
                continue
            entry = self.entry_prices.get(data._name)
            if entry is None or entry <= 0:
                continue
            close = float(data.close[0])
            if stop is not None and close <= entry * (1 - float(stop)):
                self.close(data=data, exectype=bt.Order.Market)
            elif take is not None and close >= entry * (1 + float(take)):
                self.close(data=data, exectype=bt.Order.Market)

    def _rebalance(self, dt):
        if self.p.use_regime_filter and float(self.index_data.regime[0]) <= 0:
            for data in self.stocks:
                if self.getposition(data).size != 0:
                    self.close(data=data, exectype=bt.Order.Market)
            return

        candidates = []
        for data in self.stocks:
            score = float(data.score[0])
            close = float(data.close[0])
            if math.isfinite(score) and math.isfinite(close) and close > 0:
                candidates.append((score, data))
        candidates.sort(key=lambda x: x[0], reverse=True)
        targets = {data._name: (score, data) for score, data in candidates[: int(self.p.top_n)]}

        for data in self.stocks:
            pos = self.getposition(data)
            if pos.size > 0 and data._name not in targets:
                self.close(data=data, exectype=bt.Order.Market)

        for ticker, (score, data) in targets.items():
            pos = self.getposition(data)
            self.position_log.append(
                {
                    "date": dt,
                    "ticker": ticker,
                    "score": float(score),
                    "size_before_order": float(pos.size),
                    "close": float(data.close[0]),
                }
            )
            if pos.size == 0:
                self.buy(data=data, exectype=bt.Order.Market)


def make_bt_feed_df(
    daily: pd.DataFrame,
    ticker: str,
    score_daily: pd.DataFrame,
    regime_daily: pd.Series,
) -> pd.DataFrame:
    df = daily[daily["ticker"] == ticker].copy()
    df = df[["date", "open", "high", "low", "close", "volume"]].dropna(subset=["date", "close"])
    if df.empty:
        return df
    df = df.sort_values("date").set_index("date")
    for col in ["open", "high", "low"]:
        df[col] = df[col].fillna(df["close"])
    df["volume"] = df["volume"].fillna(0)
    df["score"] = score_daily[ticker].reindex(df.index, method="ffill") if ticker in score_daily.columns else np.nan
    df["regime"] = regime_daily.reindex(df.index, method="ffill").fillna(0.0)
    return df


def run_backtrader(
    config: dict,
    daily: pd.DataFrame,
    factor_z: pd.DataFrame,
    regime: pd.Series,
    run_name: str,
    params: dict,
) -> pd.Series:
    selected_score_path = RESULTS_DIR / "selected_strategy_score.csv"
    selected_score = "composite_min2"
    if selected_score_path.exists():
        selected_score = pd.read_csv(selected_score_path, header=None, index_col=0).iloc[0, 0]
    score_monthly = factor_wide(factor_z, selected_score)
    all_daily_dates = pd.DatetimeIndex(sorted(daily["date"].unique()))
    score_daily = score_monthly.reindex(all_daily_dates, method="ffill")
    regime_daily = regime.reindex(all_daily_dates, method="ffill").fillna(0.0)

    stock_tickers = [
        c
        for c in score_daily.columns
        if c not in INDEX_TICKERS and score_daily[c].notna().sum() > 0
    ]
    cerebro = bt.Cerebro()

    index_df = make_bt_feed_df(daily, "XU100", score_daily, regime_daily)
    if index_df.empty:
        raise ValueError("XU100 feed is empty; cannot run Backtrader.")
    cerebro.adddata(FactorPandasData(dataname=index_df, name="XU100"))

    added = 0
    for ticker in stock_tickers:
        df = make_bt_feed_df(daily, ticker, score_daily, regime_daily)
        if len(df) < 60:
            continue
        cerebro.adddata(FactorPandasData(dataname=df, name=ticker))
        added += 1

    if added < 5:
        raise ValueError("Not enough stock feeds with scores for Backtrader.")

    cerebro.addstrategy(
        MonthlyFactorStrategy,
        top_n=int(params["top_n"]),
        use_regime_filter=bool(params.get("use_regime_filter", False)),
        stop_loss_pct=params.get("stop_loss_pct"),
        take_profit_pct=params.get("take_profit_pct"),
    )
    cerebro.broker.setcash(float(config["project"]["initial_cash"]))
    cerebro.broker.setcommission(commission=float(config["project"]["commission"]))
    cerebro.addsizer(FixedCashSizer, cash_per_trade=float(config["project"]["cash_per_trade"]))
    cerebro.addanalyzer(bt.analyzers.TimeReturn, _name="timereturn")
    cerebro.addanalyzer(bt.analyzers.Returns, _name="returns")
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe", riskfreerate=0.0)
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")

    result = cerebro.run()
    strat: MonthlyFactorStrategy = result[0]

    equity = pd.DataFrame(strat.equity_curve)
    orders = pd.DataFrame(strat.order_log)
    trades = pd.DataFrame(strat.trade_log)
    positions = pd.DataFrame(strat.position_log)
    for df, name in [
        (equity, "equity_curve"),
        (orders, "orders"),
        (trades, "trades"),
        (positions, "positions"),
    ]:
        df.to_csv(RESULTS_DIR / f"backtrader_{run_name}_{name}.csv", index=False)

    time_returns = pd.Series(strat.analyzers.timereturn.get_analysis(), name=run_name)
    time_returns.index = pd.to_datetime(time_returns.index)
    time_returns.to_csv(RESULTS_DIR / f"backtrader_{run_name}_daily_returns.csv", index_label="date")

    analysis = {
        "run_name": run_name,
        "final_value": float(cerebro.broker.getvalue()),
        "initial_cash": float(config["project"]["initial_cash"]),
        "total_return_analyzer": strat.analyzers.returns.get_analysis().get("rtot", np.nan),
        "annual_return_analyzer": strat.analyzers.returns.get_analysis().get("rnorm", np.nan),
        "sharpe_analyzer": strat.analyzers.sharpe.get_analysis().get("sharperatio", np.nan),
        "max_drawdown_pct": strat.analyzers.drawdown.get_analysis().max.drawdown,
        "total_orders": int(len(orders)),
        "closed_trades": int(len(trades)),
        "stock_feeds": int(added),
        "selected_score": selected_score,
    }
    pd.DataFrame([analysis]).to_csv(RESULTS_DIR / f"backtrader_{run_name}_summary.csv", index=False)
    return time_returns


def monte_carlo_test(
    base_returns: pd.Series,
    base_positions: pd.DataFrame,
    returns_wide: pd.DataFrame,
    simulations: int,
    seed: int,
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    base_returns = base_returns.dropna()
    actual_sharpe = perf_metrics(base_returns, "actual")["sharpe"]
    sim_sharpes = []

    pos_by_date = base_positions.groupby("date")["ticker"].count().to_dict() if not base_positions.empty else {}
    for _ in range(simulations):
        sim_rets = []
        for dt, actual_ret in base_returns.items():
            n = int(pos_by_date.get(dt, 10))
            row = returns_wide.reindex([dt]).iloc[0].dropna()
            if row.empty or n <= 0:
                sim_rets.append(0.0)
                continue
            n = min(n, len(row))
            picks = rng.choice(row.index.to_numpy(), size=n, replace=False)
            sim_rets.append(float(row.loc[picks].mean()))
        sim_sharpes.append(perf_metrics(pd.Series(sim_rets), "sim")["sharpe"])

    sim = pd.DataFrame({"simulation": np.arange(1, simulations + 1), "sharpe": sim_sharpes})
    p_value = float((sim["sharpe"] >= actual_sharpe).mean()) if pd.notna(actual_sharpe) else np.nan
    sim["actual_sharpe"] = actual_sharpe
    sim["p_value"] = p_value
    sim.to_csv(RESULTS_DIR / "monte_carlo_random_portfolio_sharpes.csv", index=False)
    pd.DataFrame(
        [{"actual_sharpe": actual_sharpe, "p_value": p_value, "simulations": simulations}]
    ).to_csv(RESULTS_DIR / "monte_carlo_summary.csv", index=False)
    return sim


def bootstrap_summary(returns: pd.Series, seed: int, simulations: int = 2000) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    r = returns.dropna().to_numpy(dtype=float)
    sharpes = []
    dds = []
    if len(r) == 0:
        out = pd.DataFrame()
    else:
        for _ in range(simulations):
            sample = rng.choice(r, size=len(r), replace=True)
            sr = perf_metrics(pd.Series(sample), "sample")["sharpe"]
            dd = max_drawdown(pd.Series(sample))
            sharpes.append(sr)
            dds.append(dd)
        out = pd.DataFrame({"simulation": np.arange(1, simulations + 1), "sharpe": sharpes, "max_drawdown": dds})
    out.to_csv(RESULTS_DIR / "bootstrap_base_strategy.csv", index=False)
    if not out.empty:
        pd.DataFrame(
            [
                {
                    "sharpe_ci_2_5": out["sharpe"].quantile(0.025),
                    "sharpe_ci_97_5": out["sharpe"].quantile(0.975),
                    "maxdd_ci_5": out["max_drawdown"].quantile(0.05),
                    "maxdd_ci_95": out["max_drawdown"].quantile(0.95),
                }
            ]
        ).to_csv(RESULTS_DIR / "bootstrap_summary.csv", index=False)
    return out


def make_figures(
    sort_returns: pd.DataFrame,
    reg_returns: pd.DataFrame,
    ic: pd.DataFrame,
    improvement: pd.DataFrame,
    monte_carlo: pd.DataFrame,
    bt_returns: dict[str, pd.Series],
) -> None:
    sns.set_theme(style="whitegrid")

    if not sort_returns.empty:
        fig, ax = plt.subplots(figsize=(10, 6))
        for factor, group in sort_returns.groupby("factor"):
            series = group.set_index(pd.to_datetime(group["date"]))["long_short"].sort_index()
            (1 + series).cumprod().plot(ax=ax, label=factor)
        ax.set_title("Portfolio-Sort FMP Cumulative Returns")
        ax.set_ylabel("Growth of 1 TL")
        ax.legend()
        fig.tight_layout()
        fig.savefig(FIGURES_DIR / "fmp_portfolio_sort_cumulative.png", dpi=160)
        plt.close(fig)

    if not reg_returns.empty:
        fig, ax = plt.subplots(figsize=(10, 6))
        for factor, group in reg_returns.groupby("factor"):
            series = group.set_index(pd.to_datetime(group["date"]))["long_short"].sort_index()
            (1 + series).cumprod().plot(ax=ax, label=factor)
        ax.set_title("Cross-Sectional Regression FMP Cumulative Returns")
        ax.set_ylabel("Growth of 1 TL")
        ax.legend()
        fig.tight_layout()
        fig.savefig(FIGURES_DIR / "fmp_regression_cumulative.png", dpi=160)
        plt.close(fig)

    if not ic.empty:
        fig, axes = plt.subplots(2, 1, figsize=(11, 7), sharex=True)
        for factor, group in ic.groupby("factor"):
            group = group.sort_values("date")
            axes[0].plot(pd.to_datetime(group["date"]), group["raw_ic"], label=factor, alpha=0.8)
            axes[1].plot(pd.to_datetime(group["date"]), group["rank_ic"], label=factor, alpha=0.8)
        axes[0].set_title("Raw Information Coefficients")
        axes[1].set_title("Rank Information Coefficients")
        axes[0].axhline(0, color="black", linewidth=0.8)
        axes[1].axhline(0, color="black", linewidth=0.8)
        axes[0].legend(ncol=4, fontsize=8)
        fig.tight_layout()
        fig.savefig(FIGURES_DIR / "information_coefficients.png", dpi=160)
        plt.close(fig)

    if not improvement.empty:
        pivot = improvement.pivot_table(index="score_name", columns="top_n", values="sharpe", aggfunc="max")
        fig, ax = plt.subplots(figsize=(8, 5))
        sns.heatmap(pivot, annot=True, fmt=".2f", cmap="RdYlGn", ax=ax)
        ax.set_title("Best Sharpe by Composite Score and Top-N")
        fig.tight_layout()
        fig.savefig(FIGURES_DIR / "strategy_parameter_heatmap.png", dpi=160)
        plt.close(fig)

    if bt_returns:
        fig, ax = plt.subplots(figsize=(10, 6))
        for name, rets in bt_returns.items():
            (1 + rets.dropna()).cumprod().plot(ax=ax, label=name)
        ax.set_title("Backtrader Strategy Equity Curves")
        ax.set_ylabel("Growth of 1 TL")
        ax.legend()
        fig.tight_layout()
        fig.savefig(FIGURES_DIR / "backtrader_equity_curves.png", dpi=160)
        plt.close(fig)

        fig, ax = plt.subplots(figsize=(10, 5))
        for name, rets in bt_returns.items():
            cum = (1 + rets.dropna()).cumprod()
            dd = cum / cum.cummax() - 1
            dd.plot(ax=ax, label=name)
        ax.set_title("Backtrader Drawdowns")
        ax.set_ylabel("Drawdown")
        ax.legend()
        fig.tight_layout()
        fig.savefig(FIGURES_DIR / "backtrader_drawdowns.png", dpi=160)
        plt.close(fig)

    if not monte_carlo.empty:
        fig, ax = plt.subplots(figsize=(9, 5))
        ax.hist(monte_carlo["sharpe"].dropna(), bins=50, color="0.65", edgecolor="white")
        actual = monte_carlo["actual_sharpe"].iloc[0]
        pval = monte_carlo["p_value"].iloc[0]
        ax.axvline(actual, color="red", linewidth=2, label=f"Strategy Sharpe={actual:.2f}")
        ax.set_title(f"Monte Carlo Random Portfolio Test (p={pval:.3f})")
        ax.set_xlabel("Sharpe Ratio")
        ax.legend()
        fig.tight_layout()
        fig.savefig(FIGURES_DIR / "monte_carlo_sharpe_histogram.png", dpi=160)
        plt.close(fig)


def add_text_slide(pdf: PdfPages, title: str, bullets: list[str], image: Path | None = None) -> None:
    fig = plt.figure(figsize=(11, 8.5))
    fig.patch.set_facecolor("white")
    fig.text(0.06, 0.93, title, fontsize=22, weight="bold", ha="left", va="top")
    y = 0.84
    for bullet in bullets:
        wrapped = textwrap.wrap(bullet, width=95)
        fig.text(0.08, y, "- " + wrapped[0], fontsize=12.5, ha="left", va="top")
        y -= 0.035
        for line in wrapped[1:]:
            fig.text(0.105, y, line, fontsize=12.5, ha="left", va="top")
            y -= 0.035
        y -= 0.015
    if image is not None and image.exists():
        ax = fig.add_axes([0.08, 0.08, 0.84, 0.35])
        ax.imshow(plt.imread(image))
        ax.axis("off")
    pdf.savefig(fig)
    plt.close(fig)


def add_code_slide(pdf: PdfPages, title: str, code: str, bullets: list[str] | None = None) -> None:
    fig = plt.figure(figsize=(11, 8.5))
    fig.patch.set_facecolor("white")
    fig.text(0.06, 0.93, title, fontsize=22, weight="bold", ha="left", va="top")
    y = 0.84
    if bullets:
        for bullet in bullets:
            wrapped = textwrap.wrap(bullet, width=95)
            fig.text(0.08, y, "- " + wrapped[0], fontsize=12.5, ha="left", va="top")
            y -= 0.035
            for line in wrapped[1:]:
                fig.text(0.105, y, line, fontsize=12.5, ha="left", va="top")
                y -= 0.035
            y -= 0.01
    code_box = fig.add_axes([0.07, 0.08, 0.86, max(0.25, y - 0.10)])
    code_box.set_facecolor("#f5f5f5")
    code_box.set_xticks([])
    code_box.set_yticks([])
    for spine in code_box.spines.values():
        spine.set_edgecolor("#cccccc")
    code_box.text(
        0.02,
        0.96,
        code.strip(),
        family="monospace",
        fontsize=9.2,
        ha="left",
        va="top",
        transform=code_box.transAxes,
    )
    pdf.savefig(fig)
    plt.close(fig)


def write_strategy_development_outputs(improvement: pd.DataFrame, wfa: pd.DataFrame) -> None:
    if not wfa.empty:
        test_return = pd.to_numeric(wfa["test_return"], errors="coerce").dropna()
        test_sharpe = pd.to_numeric(wfa["test_sharpe"], errors="coerce").dropna()
        pd.DataFrame(
            [
                {
                    "walk_forward_steps": int(len(wfa)),
                    "compounded_test_return": float((1 + test_return).prod() - 1) if not test_return.empty else np.nan,
                    "mean_test_return_per_window": float(test_return.mean()) if not test_return.empty else np.nan,
                    "mean_test_sharpe": float(test_sharpe.mean()) if not test_sharpe.empty else np.nan,
                    "positive_test_window_pct": float((test_return > 0).mean()) if not test_return.empty else np.nan,
                }
            ]
        ).to_csv(RESULTS_DIR / "walk_forward_summary.csv", index=False)

    bt_summary_files = sorted(RESULTS_DIR.glob("backtrader_*_summary.csv"))
    if bt_summary_files:
        bt = pd.concat([pd.read_csv(p) for p in bt_summary_files], ignore_index=True)
        bt["simple_total_return"] = bt["final_value"] / bt["initial_cash"] - 1
        bt["role"] = np.where(bt["run_name"].eq("base"), "base", "risk_control_experiment")
        bt.to_csv(RESULTS_DIR / "strategy_base_vs_final_comparison.csv", index=False)

    lines = [
        "Strategy Development Narrative",
        "=" * 30,
        "Goal: build a Turkey/BIST long-only factor strategy that follows the factor-investing project rules.",
        "",
    ]
    if not improvement.empty:
        imp = improvement.copy()
        for col in ["sharpe", "avg_return", "ann_return", "max_drawdown"]:
            imp[col] = pd.to_numeric(imp[col], errors="coerce")
        best = imp.sort_values("sharpe", ascending=False).iloc[0]
        base = imp[
            (imp["score_name"] == "equal_all")
            & (imp["top_n"].astype(str) == "10")
            & (imp["use_regime_filter"].astype(str).str.lower().isin(["false", "0"]))
        ]
        lines.append(
            f"Best vectorized trial: {best['name']} with Sharpe {fmt_num(best['sharpe'])}, "
            f"annualized return {fmt_pct(best['ann_return'])}, max drawdown {fmt_pct(best['max_drawdown'])}."
        )
        if not base.empty:
            b = base.iloc[0]
            lines.append(
                f"Base monthly trial: {b['name']} with Sharpe {fmt_num(b['sharpe'])}, "
                f"annualized return {fmt_pct(b['ann_return'])}, max drawdown {fmt_pct(b['max_drawdown'])}."
            )
        regime_summary = imp.groupby("use_regime_filter")["sharpe"].mean()
        if len(regime_summary) == 2:
            lines.append(
                "Regime filter test: average Sharpe was "
                f"{fmt_num(regime_summary.get(False))} without the filter and "
                f"{fmt_num(regime_summary.get(True))} with the BIST100 filter."
            )
    trend_path = RESULTS_DIR / "trend_regression_coefficients.csv"
    if trend_path.exists():
        trend = pd.read_csv(trend_path)
        selected_terms = trend.loc[trend["term"] != "const", "term"].tolist()
        min_p = pd.to_numeric(trend.loc[trend["term"] != "const", "p_value"], errors="coerce").min()
        lines.append(
            f"Trend regression selected {', '.join(selected_terms) if selected_terms else 'no MA term'} "
            f"at the configured significance level; minimum MA p-value was {fmt_num(min_p, 4)}."
        )
    if bt_summary_files:
        bt = pd.read_csv(RESULTS_DIR / "strategy_base_vs_final_comparison.csv")
        for _, row in bt.iterrows():
            lines.append(
                f"Backtrader {row['run_name']}: final value {fmt_num(row['final_value'], 0)} TL, "
                f"simple return {fmt_pct(row['simple_total_return'])}, Sharpe {fmt_num(row['sharpe_analyzer'])}, "
                f"max drawdown {fmt_num(row['max_drawdown_pct'])}%."
            )
    mc_path = RESULTS_DIR / "monte_carlo_summary.csv"
    if mc_path.exists():
        mc = pd.read_csv(mc_path).iloc[0]
        lines.append(
            f"Monte Carlo test: strategy Sharpe {fmt_num(mc['actual_sharpe'])}; "
            f"p-value {fmt_num(mc['p_value'], 4)} against random portfolios."
        )
    wfa_path = RESULTS_DIR / "walk_forward_summary.csv"
    if wfa_path.exists():
        wf = pd.read_csv(wfa_path).iloc[0]
        lines.append(
            f"Walk-forward validation: {int(wf['walk_forward_steps'])} windows, "
            f"compounded test return {fmt_pct(wf['compounded_test_return'])}, "
            f"positive-window rate {fmt_pct(wf['positive_test_window_pct'])}."
        )
    lines.extend(
        [
            "",
            "Conclusion logic:",
            "The best-looking in-sample/vectorized result is not accepted blindly.",
            "The Backtrader base run is the return leader, while the regime/stop experiment is treated as a risk-control test.",
            "Because the Monte Carlo p-value is not below 5%, the final investment judgment should be cautious.",
            "The main improvement path was testing factor weights, top-N thresholds, regime filtering, stop/take-profit rules, and walk-forward selection.",
        ]
    )
    (RESULTS_DIR / "strategy_development_narrative.txt").write_text("\n".join(lines), encoding="utf-8")


def write_project_audit_checklist(selected_score: str) -> None:
    def rel(path: Path) -> str:
        return str(path.relative_to(ROOT))

    config = load_config()
    participants = [str(name).strip() for name in config["project"].get("group_participants", []) if str(name).strip()]
    has_participants = bool(participants)
    checks = [
        ("Pinned Python requirements", (ROOT / "requirements.txt").exists(), "requirements.txt", "Versions are pinned."),
        ("Frozen raw price CSV", (RAW_DIR / PRICE_FILE_NAME).exists(), rel(RAW_DIR / PRICE_FILE_NAME), "Final analysis reads this file."),
        ("Frozen raw fundamental/ratio CSV", fundamental_input_path().exists(), rel(fundamental_input_path()), f"Final analysis reads this {fundamental_input_label()}."),
        ("Turkish stock universe", (RESULTS_DIR / "universe_price_audit.csv").exists(), rel(RESULTS_DIR / "universe_price_audit.csv"), "Index columns are marked separately and excluded."),
        ("BIST100 trend regression", (RESULTS_DIR / "trend_regression_coefficients.csv").exists(), rel(RESULTS_DIR / "trend_regression_coefficients.csv"), "Uses XU100 moving-average deviations."),
        ("Four required factor panels", (PROCESSED_DIR / "factor_zscores_long.csv").exists(), rel(PROCESSED_DIR / "factor_zscores_long.csv"), "ROE, P/E, momentum, trend plus composites."),
        ("Portfolio-sort FMPs", (RESULTS_DIR / "fmp_portfolio_sort_returns.csv").exists(), rel(RESULTS_DIR / "fmp_portfolio_sort_returns.csv"), "Top quintile minus bottom quintile."),
        ("Regression FMPs", (RESULTS_DIR / "fmp_regression_returns.csv").exists(), rel(RESULTS_DIR / "fmp_regression_returns.csv"), "Monthly cross-sectional slopes."),
        ("IC and rank IC", (RESULTS_DIR / "information_coefficients.csv").exists(), rel(RESULTS_DIR / "information_coefficients.csv"), "Signal at t versus return at t+1."),
        ("Common-start FMP comparison", (RESULTS_DIR / "fmp_common_start_metrics.csv").exists(), rel(RESULTS_DIR / "fmp_common_start_metrics.csv"), "Required when factor starts differ."),
        ("Selected-date FMP weights", (RESULTS_DIR / "fmp_weights_selected_date.csv").exists(), rel(RESULTS_DIR / "fmp_weights_selected_date.csv"), "Portfolio and regression weights."),
        ("Backtrader base run", (RESULTS_DIR / "backtrader_base_summary.csv").exists(), rel(RESULTS_DIR / "backtrader_base_summary.csv"), "1,000,000 TL, 100,000 TL sizer, zero commission."),
        ("Backtrader improvement run", (RESULTS_DIR / "backtrader_improved_regime_stop_summary.csv").exists(), rel(RESULTS_DIR / "backtrader_improved_regime_stop_summary.csv"), "Regime plus stop/take-profit test."),
        ("Saved Backtrader details", (RESULTS_DIR / "backtrader_base_trades.csv").exists() and (RESULTS_DIR / "backtrader_base_positions.csv").exists(), rel(RESULTS_DIR / "backtrader_base_*.csv"), "Trades, positions, orders, returns, equity."),
        ("Monte Carlo Sharpe test", (RESULTS_DIR / "monte_carlo_summary.csv").exists() and (FIGURES_DIR / "monte_carlo_sharpe_histogram.png").exists(), rel(RESULTS_DIR / "monte_carlo_summary.csv"), "Random same-position-count portfolios."),
        ("Walk-forward validation", (RESULTS_DIR / "walk_forward_results.csv").exists(), rel(RESULTS_DIR / "walk_forward_results.csv"), "Parameter selection on train window, test out of sample."),
        ("PDF presentation", (PRESENTATION_DIR / "bist_factor_project_presentation.pdf").exists(), rel(PRESENTATION_DIR / "bist_factor_project_presentation.pdf"), "Contains project summary, paper summary, results, and conclusion."),
        (
            "Group names in PDF",
            has_participants,
            rel(PRESENTATION_DIR / "bist_factor_project_presentation.pdf"),
            "Set project.group_participants in config/project_config.yaml and rerun the project." if not has_participants else "Participant names are configured.",
        ),
    ]
    rows = []
    for requirement, ok, evidence, notes in checks:
        rows.append(
            {
                "requirement": requirement,
                "status": "OK" if ok else "NEEDS_INPUT" if requirement == "Group names in PDF" else "MISSING",
                "evidence": evidence,
                "notes": notes,
                "selected_score": selected_score,
            }
        )
    pd.DataFrame(rows).to_csv(RESULTS_DIR / "project_audit_checklist.csv", index=False)


def make_presentation() -> None:
    config = load_config()
    participants = [str(name).strip() for name in config["project"].get("group_participants", []) if str(name).strip()]
    participant_text = ", ".join(participants) if participants else "[set project.group_participants in config/project_config.yaml]"
    metrics_path = RESULTS_DIR / "factor_performance_metrics.csv"
    bt_summary_files = sorted(RESULTS_DIR.glob("backtrader_*_summary.csv"))
    factor_metrics = pd.read_csv(metrics_path) if metrics_path.exists() else pd.DataFrame()
    improvement = pd.read_csv(RESULTS_DIR / "strategy_improvement_tests.csv") if (RESULTS_DIR / "strategy_improvement_tests.csv").exists() else pd.DataFrame()
    method_comparison = pd.read_csv(RESULTS_DIR / "fmp_method_comparison.csv") if (RESULTS_DIR / "fmp_method_comparison.csv").exists() else pd.DataFrame()
    common_start = pd.read_csv(RESULTS_DIR / "fmp_common_start_metrics.csv") if (RESULTS_DIR / "fmp_common_start_metrics.csv").exists() else pd.DataFrame()
    trend_coeff = pd.read_csv(RESULTS_DIR / "trend_regression_coefficients.csv") if (RESULTS_DIR / "trend_regression_coefficients.csv").exists() else pd.DataFrame()
    monte_summary = pd.read_csv(RESULTS_DIR / "monte_carlo_summary.csv") if (RESULTS_DIR / "monte_carlo_summary.csv").exists() else pd.DataFrame()
    wfa_summary = pd.read_csv(RESULTS_DIR / "walk_forward_summary.csv") if (RESULTS_DIR / "walk_forward_summary.csv").exists() else pd.DataFrame()
    best_factor = "N/A"
    if not factor_metrics.empty and factor_metrics["sharpe"].notna().any():
        best_factor = factor_metrics.sort_values("sharpe", ascending=False).iloc[0]["name"]
    best_trial = None
    if not improvement.empty and improvement["sharpe"].notna().any():
        best_trial = improvement.sort_values("sharpe", ascending=False).iloc[0]

    out = PRESENTATION_DIR / "bist_factor_project_presentation.pdf"
    with PdfPages(out) as pdf:
        add_text_slide(
            pdf,
            "BIST Factor Investing Project",
            [
                f"Group participants: {participant_text}.",
                "Project focus: Turkish equities, BIST100 benchmark, ROE, P/E, momentum, and trend factors.",
                f"Data-source run: {DATA_SOURCE_LABEL}.",
                "All data and results are frozen to CSV for reproducibility.",
            ],
        )
        add_text_slide(
            pdf,
            "Paper Summary",
            [
                "Han, Zhou, and Zhu ask whether combining price information across short, intermediate, and long horizons improves factor returns.",
                "Their trend factor uses moving averages from 3 to 1,000 trading days, predicts expected returns, buys the highest predicted-return quintile, and shorts the lowest.",
                "They report stronger Sharpe ratios than separate reversal, momentum, and long-term reversal factors, including resilience during the financial crisis.",
                "Our course adaptation keeps the moving-average logic but estimates the predictive regression on BIST100 Index data as required by the project PDF.",
            ],
        )
        add_text_slide(
            pdf,
            "Data and Factor Construction",
            [
                "Use XU100 only for benchmark and trend regression; stock portfolios exclude index columns.",
                "ROE and P/E come from the frozen fundamental or BIST ratio file and are lagged by using month t signals for month t+1.",
                "Momentum is P_t / P_{t-12} - 1 using month-end closes from the frozen price file.",
                "All factor signals are winsorized and cross-sectionally z-scored before portfolio formation.",
            ],
        )
        trend_lines = [
            "Trend uses only XU100/BIST100 for coefficient estimation; index columns are excluded from stock portfolios.",
            "The configured primary regression excludes the common intercept because z-scoring/ranking removes any stock-common constant.",
        ]
        if not trend_coeff.empty:
            terms = trend_coeff.loc[trend_coeff["term"] != "const"]
            for _, row in terms.iterrows():
                trend_lines.append(
                    f"Selected {row['term']}: coef {fmt_num(row['coef'], 4)}, p-value {fmt_num(row['p_value'], 4)}."
                )
        trend_lines.append("With-intercept diagnostics are saved separately to disclose specification sensitivity.")
        add_text_slide(pdf, "Trend Regression", trend_lines)
        add_code_slide(
            pdf,
            "Code Example: Factors",
            """
def compute_momentum(monthly_close, stock_cols):
    return monthly_close[stock_cols] / monthly_close[stock_cols].shift(12) - 1

def zscore_cross_section(s):
    s = winsorize_cross_section(s, lower_q=0.01, upper_q=0.99)
    valid = s.dropna()
    if len(valid) < 3 or valid.std(ddof=1) == 0:
        return pd.Series(np.nan, index=s.index)
    return (s - valid.mean()) / valid.std(ddof=1)

target = monthly_returns["XU100"].shift(-1)
model = sm.OLS(target, xu100_ma_deviations[selected_terms]).fit()
            """,
            [
                "All factors are constructed at month end.",
                "Signals at month t are matched to returns/trades at month t+1.",
            ],
        )
        add_text_slide(
            pdf,
            "Factor-Mimicking Portfolios",
            [
                "Each factor is analyzed with both portfolio-sort FMPs and cross-sectional-regression FMPs.",
                f"Best factor by Sharpe in the saved metrics: {best_factor}.",
                "Saved outputs include separate-start metrics, common-start metrics, and selected-date portfolio/regression weights.",
                "Method comparison reports return correlations and same-sign frequencies between portfolio and regression FMPs.",
            ],
            FIGURES_DIR / "fmp_portfolio_sort_cumulative.png",
        )
        fmp_lines = []
        if not common_start.empty and "sharpe" in common_start:
            top_common = common_start.sort_values("sharpe", ascending=False).head(3)
            for _, row in top_common.iterrows():
                fmp_lines.append(
                    f"{row['factor']} / {row['method']}: common-start Sharpe {fmt_num(row['sharpe'])}, avg monthly return {fmt_pct(row['avg_return'])}."
                )
        if not method_comparison.empty:
            similar = int(pd.Series(method_comparison.get("qualitatively_similar", [])).fillna(False).astype(bool).sum())
            fmp_lines.append(f"Portfolio-sort and regression methods were qualitatively similar for {similar} of {len(method_comparison)} factors by the saved rule.")
        if not fmp_lines:
            fmp_lines = ["Common-start and method-comparison files are generated in the results folder."]
        add_text_slide(pdf, "FMP Comparison Results", fmp_lines, FIGURES_DIR / "fmp_regression_cumulative.png")
        add_text_slide(
            pdf,
            "Information Coefficients",
            [
                "Raw IC measures cross-sectional correlation between factor signal at month t and stock returns at month t+1.",
                "Rank IC repeats the test on ranks and is more robust to outliers.",
                "Positive average IC suggests the factor ranks stocks in the correct direction.",
            ],
            FIGURES_DIR / "information_coefficients.png",
        )
        add_code_slide(
            pdf,
            "Code Example: Backtrader",
            """
class FixedCashSizer(bt.Sizer):
    params = (("cash_per_trade", 100_000),)
    def _getsizing(self, comminfo, cash, data, isbuy):
        price = data.close[0]
        return int(self.p.cash_per_trade / price) if price > 0 else 0

cerebro.broker.setcash(1_000_000)
cerebro.broker.setcommission(commission=0)
cerebro.addsizer(FixedCashSizer, cash_per_trade=100_000)
self.buy(data=data, exectype=bt.Order.Market)
            """,
            [
                "This matches the instructor's capital, sizing, commission, and market-order rules.",
                "Trades, orders, positions, daily returns, and equity curves are saved to CSV.",
            ],
        )
        add_text_slide(
            pdf,
            "Backtrader Strategy",
            [
                "Monthly strategy buys the top-ranked composite-factor stocks.",
                "Initial capital is 1,000,000 TL; each trade uses the FixedCashSizer with 100,000 TL per trade.",
                "Commission is set to zero and base orders are market orders, matching the instructor instructions.",
                "Trades, positions, daily returns, equity curves, and summary metrics are saved as CSV files.",
            ],
            FIGURES_DIR / "backtrader_equity_curves.png",
        )
        improvement_lines = [
            "Test grid: equal all four factors, price/trend, trend-heavy, and quality/value composites.",
            "For each composite, top 5 / top 10 / top 15 and BIST100 regime filter on/off were tested.",
            "Backtrader then tested the base strategy and a regime plus stop-loss/take-profit risk-control variant.",
        ]
        if best_trial is not None:
            improvement_lines.append(
                f"Best vectorized trial: {best_trial['name']} with Sharpe {fmt_num(best_trial['sharpe'])} and annualized return {fmt_pct(best_trial['ann_return'])}."
            )
        if not wfa_summary.empty:
            wf = wfa_summary.iloc[0]
            improvement_lines.append(
                f"Walk-forward: {int(wf['walk_forward_steps'])} windows, compounded test return {fmt_pct(wf['compounded_test_return'])}."
            )
        add_text_slide(
            pdf,
            "What We Tried",
            improvement_lines,
            FIGURES_DIR / "strategy_parameter_heatmap.png",
        )
        add_text_slide(
            pdf,
            "What Failed or Weakened",
            [
                "The trend signal is specification-sensitive, so we disclose both the primary no-intercept selection and with-intercept diagnostic.",
                "Regime filtering and stop/take-profit rules reduced final wealth in the Backtrader run, even if they slightly changed risk metrics.",
                "Pure price/trend variants did not dominate the equal-weight composite in the final Backtrader comparison.",
                "ROE/P/E coverage depends on the frozen fundamental or BIST ratio file, so these factors can have shorter samples than momentum/trend.",
            ],
            FIGURES_DIR / "backtrader_drawdowns.png",
        )
        add_text_slide(
            pdf,
            "Monte Carlo Significance",
            [
                "The null model randomly selects stocks each month while preserving the number of positions.",
                "The p-value is the fraction of random portfolios with Sharpe at least as high as the strategy Sharpe.",
                (
                    f"Saved p-value: {fmt_num(monte_summary.iloc[0]['p_value'], 4)}; this does not reject the random-strategy null at 5%."
                    if not monte_summary.empty
                    else "The Monte Carlo summary is saved in results/monte_carlo_summary.csv."
                ),
            ],
            FIGURES_DIR / "monte_carlo_sharpe_histogram.png",
        )
        if RATIO_FILE_NAME:
            limitation = "BIST monthly ratios keep ROE/P/E source-consistent, but raw public bulletin prices remain unadjusted unless an adjusted-price file is supplied."
        else:
            limitation = "Public financial-statement fundamentals have limited history for some BIST stocks; results should be interpreted with that limitation."
        if bt_summary_files:
            bt_summary = pd.concat([pd.read_csv(p) for p in bt_summary_files], ignore_index=True)
            best_bt = bt_summary.sort_values("final_value", ascending=False).iloc[0]
            judgment = f"Best Backtrader run by final value: {best_bt['run_name']} with final value {best_bt['final_value']:.0f} TL."
        else:
            judgment = "Backtrader results were not available when the presentation was generated."
        add_text_slide(
            pdf,
            "Conclusion",
            [
                judgment,
                limitation,
                "The final conclusion is cautious: the base Backtrader result is strong, but the Monte Carlo p-value and data limitations argue against real-money investment without better data and cost assumptions.",
            ],
        )


def write_validation_report(files_created: list[Path], selected_score: str) -> None:
    lines = [
        "BIST Factor Investing Validation Report",
        "=" * 44,
        f"Data source: {DATA_SOURCE_LABEL}.",
        f"Raw data folder: {RAW_DIR.relative_to(ROOT)}.",
        f"Raw price file: {(RAW_DIR / PRICE_FILE_NAME).relative_to(ROOT)}.",
        f"Raw fundamental/ratio file: {fundamental_input_path().relative_to(ROOT)}.",
        "Universe: Turkish equities from config/project_config.yaml; index columns are excluded from stock portfolios.",
        "Benchmark and trend regression index: XU100 / BIST100.",
        f"Selected strategy score: {selected_score}.",
        "Trend regression: non-significant MA terms are dropped at the configured alpha; the stock-common intercept is excluded from the primary ranking specification and saved as a diagnostic separately.",
        "Look-ahead handling: factor values at month t are paired with returns at month t+1; Backtrader market orders execute after signal calculation.",
        "Costs: commission is set to zero as required by the project.",
        "FMP outputs include portfolio-sort, cross-sectional-regression, common-start comparison, method comparison, IC/rank IC, and selected-date weights.",
        "Known limitations: fundamental/ratio coverage can be incomplete for some BIST stocks; exact financial statement release dates are proxied by fixed lags or monthly ratio availability; set project.group_participants in config/project_config.yaml before final submission.",
        "",
        "Generated files:",
    ]
    for path in sorted(files_created):
        lines.append(f"- {path.relative_to(ROOT)}")
    (RESULTS_DIR / "validation_report.txt").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    ensure_dirs()
    config = load_config()
    np.random.seed(int(config["project"]["random_seed"]))

    daily, monthly_close, monthly_returns = load_price_data()
    factor_raw, factor_z, stock_returns, daily_close, _ = build_factor_panels(
        config, daily, monthly_close, monthly_returns
    )
    sort_returns, reg_returns, ic = analyze_factors(config, factor_z, stock_returns)
    improvement, base_positions, regime = run_improvement_tests(config, factor_z, stock_returns, monthly_close)
    wfa = walk_forward_test(factor_z, stock_returns, config, regime)

    selected_score = pd.read_csv(RESULTS_DIR / "selected_strategy_score.csv", header=None, index_col=0).iloc[0, 0]
    base_returns = pd.read_csv(RESULTS_DIR / "base_monthly_top10_returns.csv", index_col="date", parse_dates=True).iloc[:, 0]
    monte_carlo = monte_carlo_test(
        base_returns,
        base_positions,
        stock_returns,
        simulations=int(config["project"]["monte_carlo_simulations"]),
        seed=int(config["project"]["random_seed"]),
    )
    bootstrap_summary(base_returns, seed=int(config["project"]["random_seed"]))

    bt_returns = {}
    for run_name, params in config["backtrader_runs"].items():
        try:
            bt_returns[run_name] = run_backtrader(config, daily, factor_z, regime, run_name, params)
        except Exception as exc:  # noqa: BLE001 - save failure details without stopping whole report.
            pd.DataFrame([{"run_name": run_name, "error": repr(exc)}]).to_csv(
                RESULTS_DIR / f"backtrader_{run_name}_error.csv", index=False
            )

    write_strategy_development_outputs(improvement, wfa)
    make_figures(sort_returns, reg_returns, ic, improvement, monte_carlo, bt_returns)
    make_presentation()
    write_project_audit_checklist(selected_score)

    files_created = (
        list(PROCESSED_DIR.glob("*.csv"))
        + list(RESULTS_DIR.glob("*.csv"))
        + list(RESULTS_DIR.glob("*.txt"))
        + list(FIGURES_DIR.glob("*.png"))
        + list(PRESENTATION_DIR.glob("*.pdf"))
    )
    write_validation_report(files_created, selected_score)
    print("Project run complete.")
    print(f"Selected score: {selected_score}")
    print(f"Results: {RESULTS_DIR}")
    print(f"Figures: {FIGURES_DIR}")
    print(f"Presentation: {PRESENTATION_DIR / 'bist_factor_project_presentation.pdf'}")


if __name__ == "__main__":
    main()
