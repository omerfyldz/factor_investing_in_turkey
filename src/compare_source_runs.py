"""Compare the original frozen run with the separate BIST-native run."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]


def read_optional_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


def selected_score(results_dir: Path) -> str:
    path = results_dir / "selected_strategy_score.csv"
    if not path.exists():
        return "N/A"
    return pd.read_csv(path, header=None, index_col=0).iloc[0, 0]


def summarize_run(source: str, results_dir: Path) -> dict:
    bt = read_optional_csv(results_dir / "strategy_base_vs_final_comparison.csv")
    mc = read_optional_csv(results_dir / "monte_carlo_summary.csv")
    improvements = read_optional_csv(results_dir / "strategy_improvement_tests.csv")
    wf = read_optional_csv(results_dir / "walk_forward_summary.csv")

    row = {"source": source, "selected_score": selected_score(results_dir)}

    if not bt.empty:
        for run_name, prefix in [("base", "base"), ("improved_regime_stop", "improved")]:
            match = bt[bt["run_name"] == run_name]
            if not match.empty:
                rec = match.iloc[0]
                row.update(
                    {
                        f"{prefix}_final_value": rec.get("final_value"),
                        f"{prefix}_simple_return": rec.get("simple_total_return"),
                        f"{prefix}_sharpe_analyzer": rec.get("sharpe_analyzer"),
                        f"{prefix}_max_drawdown_pct": rec.get("max_drawdown_pct"),
                    }
                )

    if not mc.empty:
        row.update(
            {
                "monte_carlo_actual_sharpe": mc.iloc[0].get("actual_sharpe"),
                "monte_carlo_p_value": mc.iloc[0].get("p_value"),
            }
        )

    if not improvements.empty and improvements["sharpe"].notna().any():
        best = improvements.sort_values("sharpe", ascending=False).iloc[0]
        row.update(
            {
                "best_vectorized_trial": best.get("name"),
                "best_vectorized_sharpe": best.get("sharpe"),
                "best_vectorized_avg_monthly_return": best.get("avg_return"),
                "best_vectorized_max_drawdown": best.get("max_drawdown"),
            }
        )

    if not wf.empty:
        rec = wf.iloc[0]
        row.update(
            {
                "walk_forward_steps": rec.get("walk_forward_steps"),
                "walk_forward_compounded_test_return": rec.get("compounded_test_return"),
                "walk_forward_mean_test_sharpe": rec.get("mean_test_sharpe"),
                "walk_forward_positive_window_pct": rec.get("positive_test_window_pct"),
            }
        )

    return row


def main() -> None:
    results_bist = ROOT / "results_bist"
    results_bist.mkdir(parents=True, exist_ok=True)
    required_bist_summary = results_bist / "strategy_base_vs_final_comparison.csv"
    if not required_bist_summary.exists():
        raise SystemExit(
            "Missing results_bist/strategy_base_vs_final_comparison.csv. "
            "Generate the BIST-native run with src/run_project_bist.py before comparing sources."
        )

    rows = [
        summarize_run("Yahoo adjusted prices + Yahoo fundamentals", ROOT / "results"),
        summarize_run("BIST public prices/indexes + BIST DataStore monthly ratios", ROOT / "results_bist"),
    ]
    out = pd.DataFrame(rows)
    numeric_cols = out.select_dtypes(include="number").columns
    if len(out) == 2:
        delta = {"source": "BIST-native minus original", "selected_score": ""}
        for col in numeric_cols:
            delta[col] = out.loc[1, col] - out.loc[0, col]
        out = pd.concat([out, pd.DataFrame([delta])], ignore_index=True)
    out.to_csv(results_bist / "original_vs_bist_native_comparison.csv", index=False)

    yahoo = out.iloc[0]
    bist = out.iloc[1]
    lines = [
        "Original vs BIST-native comparison",
        "==================================",
        "The original output folders were left intact. The BIST-native run is stored separately under data_bist, results_bist, figures_bist, and presentation_bist.",
        "BIST-native means official Borsa Istanbul public stock bulletins and public index closes, with ROE/P/E read from BIST DataStore monthly valuation-ratio files.",
        "The BIST public stock bulletin prices are not adjusted for dividends/splits unless an adjusted-price file is supplied.",
        "",
        f"Base Backtrader final value: Yahoo {yahoo.get('base_final_value', float('nan')):.0f} TL; BIST-source {bist.get('base_final_value', float('nan')):.0f} TL.",
        f"Base Backtrader Sharpe analyzer: Yahoo {yahoo.get('base_sharpe_analyzer', float('nan')):.3f}; BIST-source {bist.get('base_sharpe_analyzer', float('nan')):.3f}.",
        f"Improved run final value: Yahoo {yahoo.get('improved_final_value', float('nan')):.0f} TL; BIST-source {bist.get('improved_final_value', float('nan')):.0f} TL.",
        f"Improved run Sharpe analyzer: Yahoo {yahoo.get('improved_sharpe_analyzer', float('nan')):.3f}; BIST-source {bist.get('improved_sharpe_analyzer', float('nan')):.3f}.",
        f"Monte Carlo p-value: Yahoo {yahoo.get('monte_carlo_p_value', float('nan')):.4f}; BIST-source {bist.get('monte_carlo_p_value', float('nan')):.4f}.",
        "",
        "Interpretation: compare these rows only after both runs have been regenerated from their frozen CSV inputs.",
    ]
    (results_bist / "original_vs_bist_native_comparison.txt").write_text("\n".join(lines), encoding="utf-8")
    print(out.to_string(index=False))


if __name__ == "__main__":
    main()
