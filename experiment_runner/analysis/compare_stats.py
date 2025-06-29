"""
experiment_runner.analysis.compare_stats
----------------------------------------

Compares two completed Diplomacy experiments.  Console output now
shows *all* metrics whose 95 % CI excludes 0 (α = 0.05 by default).

CSV files remain:

    <expA>/analysis/comparison/
        comparison_aggregated_vs_<expB>.csv
        comparison_by_power_vs_<expB>.csv
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd
from scipy import stats

# ───────────────────────── helpers ──────────────────────────
_EXCLUDE: set[str] = {
    "game_id",
    "llm_model",
    "power_name",
    "game_phase",
    "analyzed_response_type",
}


def _numeric_columns(df: pd.DataFrame) -> List[str]:
    return [c for c in df.select_dtypes("number").columns if c not in _EXCLUDE]


def _load_games(exp: Path) -> pd.DataFrame:
    indiv = exp / "analysis" / "statistical_game_analysis" / "individual"
    csvs = list(indiv.glob("*_game_analysis.csv"))
    if not csvs:
        raise FileNotFoundError(f"no *_game_analysis.csv under {indiv}")
    return pd.concat((pd.read_csv(p) for p in csvs), ignore_index=True)


def _welch(a: np.ndarray, b: np.ndarray, alpha: float) -> Dict:
    _t, p_val = stats.ttest_ind(a, b, equal_var=False)
    mean_a, mean_b = a.mean(), b.mean()
    diff = mean_b - mean_a
    pooled_sd = np.sqrt((a.var(ddof=1) + b.var(ddof=1)) / 2)
    cohen_d = diff / pooled_sd if pooled_sd else np.nan
    se = np.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b))
    df = len(a) + len(b) - 2
    ci = stats.t.ppf(1 - alpha / 2, df=df) * se
    return {
        "Mean_A": mean_a,
        "Mean_B": mean_b,
        "Diff": diff,
        "CI_low": diff - ci,
        "CI_high": diff + ci,
        "p_value": p_val,
        "Cohen_d": cohen_d,
        "n_A": len(a),
        "n_B": len(b),
    }


# ───────────────────────── console formatting ─────────────────────────
def _fmt_row(label: str, r: Dict, width: int) -> str:
    ci = f"[{r['CI_low']:+.2f}, {r['CI_high']:+.2f}]"
    return (
        f"  {label:<{width}} "
        f"{r['Diff']:+6.2f}  "
        f"({r['Mean_A']:.2f} → {r['Mean_B']:.2f})   "
        f"95%CI {ci:<17}  "
        f"p={r['p_value']:.4g}   "
        f"d={r['Cohen_d']:+.2f}"
    )


def _print_hdr(title: str) -> None:
    print(f"\n{title}")
    print("─" * len(title))


def _significant(df: pd.DataFrame, alpha: float) -> pd.DataFrame:
    """Return rows whose CI excludes 0 (equivalently p < alpha)."""
    sig = df[
        ((df["CI_low"] > 0) & (df["CI_high"] > 0))
        | ((df["CI_low"] < 0) & (df["CI_high"] < 0))
        | (df["p_value"] < alpha)  # fallback, same criterion
    ].copy()
    return sig.sort_values("p_value").reset_index(drop=True)


# ───────────────────────── public API ─────────────────────────
def run(exp_a: Path, exp_b: Path, alpha: float = 0.05) -> None:
    df_a = _load_games(exp_a)
    df_b = _load_games(exp_b)

    metrics = sorted(set(_numeric_columns(df_a)) & set(_numeric_columns(df_b)))
    if not metrics:
        print("No overlapping numeric metrics to compare.")
        return

    out_dir = exp_a / "analysis" / "comparison"
    out_dir.mkdir(parents=True, exist_ok=True)

    # ── section 1: aggregated across powers ───────────────────────────
    rows_agg: List[Dict] = []
    for col in metrics:
        a_vals = df_a.groupby("game_id")[col].mean().dropna().to_numpy()
        b_vals = df_b.groupby("game_id")[col].mean().dropna().to_numpy()
        if len(a_vals) < 2 or len(b_vals) < 2:
            continue
        rows_agg.append({"Metric": col, **_welch(a_vals, b_vals, alpha)})

    agg_df = pd.DataFrame(rows_agg)
    agg_csv = out_dir / f"comparison_aggregated_vs_{exp_b.name}.csv"
    agg_df.to_csv(agg_csv, index=False)

    sig_agg = _significant(agg_df, alpha)
    if not sig_agg.empty:
        n_a, n_b = int(sig_agg.iloc[0]["n_A"]), int(sig_agg.iloc[0]["n_B"])
        _print_hdr(f"Aggregated Across Powers – significant at 95 % CI (nA={n_a}, nB={n_b})")
        label_w = max(len(m) for m in sig_agg["Metric"]) + 2
        for _, r in sig_agg.iterrows():
            print(_fmt_row(r["Metric"], r, label_w))
    else:
        _print_hdr("Aggregated Across Powers – no metric significant at 95 % CI")

    # ── section 2: per-power breakdown ───────────────────────────────
    rows_pow: List[Dict] = []
    powers = sorted(set(df_a["power_name"]) & set(df_b["power_name"]))
    for power in powers:
        sub_a = df_a[df_a["power_name"] == power]
        sub_b = df_b[df_b["power_name"] == power]
        for col in metrics:
            a_vals = sub_a[col].dropna().to_numpy()
            b_vals = sub_b[col].dropna().to_numpy()
            if len(a_vals) < 2 or len(b_vals) < 2:
                continue
            rows_pow.append(
                {"Power": power, "Metric": col, **_welch(a_vals, b_vals, alpha)}
            )

    pow_df = pd.DataFrame(rows_pow)
    pow_csv = out_dir / f"comparison_by_power_vs_{exp_b.name}.csv"
    pow_df.to_csv(pow_csv, index=False)

    sig_pow = _significant(pow_df, alpha)
    if not sig_pow.empty:
        _print_hdr(f"Per-Power Breakdown – metrics significant at 95 % CI (α={alpha})")
        label_w = max(len(m) for m in sig_pow["Metric"]) + 2
        for power in powers:
            sub = sig_pow[sig_pow["Power"] == power]
            if sub.empty:
                continue
            n_a, n_b = int(sub.iloc[0]["n_A"]), int(sub.iloc[0]["n_B"])
            print(f"{power} (nA={n_a}, nB={n_b})")
            for _, r in sub.iterrows():
                print(_fmt_row(r["Metric"], r, label_w))
    else:
        _print_hdr("Per-Power Breakdown – no metric significant at 95 % CI")

    # ── summary of file outputs ───────────────────────────────────────
    print("\nCSV outputs:")
    print(f"  • {agg_csv}")
    print(f"  • {pow_csv}")
