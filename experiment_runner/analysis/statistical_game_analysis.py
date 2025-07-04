"""
experiment_runner.analysis.statistical_game_analysis
----------------------------------------------------

Runs the Statistical Game Analyzer to create per-run / combined CSVs,
then produces a suite of PNG plots:

analysis/
└── statistical_game_analysis/
    ├── individual/
    │   ├── run_00000_game_analysis.csv
    │   └── …
    └── plots/
        ├── game/
        │   ├── final_supply_centers_owned.png
        │   └── …
        ├── game_summary_heatmap.png
        └── phase/
            ├── supply_centers_owned_count.png
            └── …

Complies with experiment-runner’s plug-in contract:
    run(experiment_dir: pathlib.Path, ctx: dict) -> None
"""
from __future__ import annotations

import logging
import re
import json
from pathlib import Path
from typing import List

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

# third-party analyser that creates the CSVs
from analysis.statistical_game_analysis import StatisticalGameAnalyzer  # type: ignore

log = logging.getLogger(__name__)

# ───────────────────────── helpers ──────────────────────────
_SEASON_ORDER = {"S": 0, "F": 1, "W": 2, "A": 3}


def _sanitize(name: str) -> str:
    return re.sub(r"[^\w\-\.]", "_", name)


def _discover_csvs(individual_dir: Path, pattern: str) -> List[Path]:
    return sorted(individual_dir.glob(pattern))


def _numeric_columns(df: pd.DataFrame, extra_exclude: set[str] | None = None) -> List[str]:
    exclude = {
        "game_id",
        "llm_model",
        "power_name",
        "game_phase",
        "analyzed_response_type",
    }
    if extra_exclude:
        exclude |= extra_exclude
    return [c for c in df.select_dtypes("number").columns if c not in exclude]


def _phase_sort_key(ph: str) -> tuple[int, int]:
    """
    Sort key that keeps normal phases chronological and forces the literal
    string 'COMPLETED' to the very end.

    • 'S1901M' → (1901, 0)
    • 'COMPLETED' → (9999, 9)
    """
    if ph.upper() == "COMPLETED":
        return (9999, 9)               # always last

    year = int(ph[1:5]) if len(ph) >= 5 and ph[1:5].isdigit() else 0
    season = _SEASON_ORDER.get(ph[0], 9)
    return year, season


def _phase_index(series: pd.Series) -> pd.Series:
    uniq = sorted(series.unique(), key=_phase_sort_key)
    mapping = {ph: i for i, ph in enumerate(uniq)}
    return series.map(mapping)

def _map_game_id_to_run_dir(exp_dir: Path) -> dict[str, str]:
    """
    Reads each runs/run_xxxxx/lmvsgame.json file and returns
    {game_id_string: 'run_xxxxx'}.
    """
    mapping: dict[str, str] = {}
    runs_root = exp_dir / "runs"
    for run_dir in runs_root.glob("run_*"):
        json_path = run_dir / "lmvsgame.json"
        if not json_path.exists():
            continue
        try:
            with json_path.open(encoding="utf-8") as fh:
                data = json.load(fh)
            gid = str(data.get("id", ""))          # use top-level "id"
            if gid:
                mapping[gid] = run_dir.name
        except Exception:                          # corrupt / unreadable → skip
            continue
    return mapping


# ───────────────────────── plots ────────────────────────────
def _plot_game_level(all_games: pd.DataFrame, plot_dir: Path) -> None:
    """
    • Box-plots per metric (hue = power, legend removed).
    • Z-score heat-map: powers × metrics, colour-coded by relative standing.
    """
    plot_dir.mkdir(parents=True, exist_ok=True)
    num_cols = _numeric_columns(all_games)

    # ── per-metric box-plots ──────────────────────────────────────────
    for col in num_cols:
        fig, ax = plt.subplots(figsize=(8, 6))
        sns.boxplot(
            data=all_games,
            x="power_name",
            y=col,
            hue="power_name",
            palette="pastel",
            dodge=False,
            ax=ax,
        )
        leg = ax.get_legend()
        if leg is not None:
            leg.remove()
        ax.set_title(col.replace("_", " ").title())
        fig.tight_layout()
        fig.savefig(plot_dir / f"{_sanitize(col)}.png", dpi=140)
        plt.close(fig)

    # ── summary heat-map (column-wise z-scores) ───────────────────────
    #   1) mean across runs  2) z-score each column
    summary = all_games.groupby("power_name")[num_cols].mean().sort_index()
    zscores = summary.apply(lambda col: (col - col.mean()) / col.std(ddof=0), axis=0)

    fig_w = max(6, len(num_cols) * 0.45 + 2)
    fig, ax = plt.subplots(figsize=(fig_w, 6))
    sns.heatmap(
        zscores,
        cmap="coolwarm",
        center=0,
        linewidths=0.4,
        annot=True,
        fmt=".2f",
        ax=ax,
    )
    ax.set_title("Relative Standing (column-wise z-score)")
    ax.set_ylabel("Power")
    fig.tight_layout()
    fig.savefig(plot_dir.parent / "game_summary_zscore_heatmap.png", dpi=160)
    plt.close(fig)




def _plot_phase_level(
    all_phase: pd.DataFrame,
    plot_dir: Path,
    title_suffix: str = "",
) -> None:
    """
    Plots aggregated phase metrics.  If *title_suffix* is supplied it is
    appended to each chart title — handy for per-run plots.
    """
    if all_phase.empty:
        return
    plot_dir.mkdir(parents=True, exist_ok=True)

    if "phase_index" not in all_phase.columns:
        all_phase["phase_index"] = _phase_index(all_phase["game_phase"])

    num_cols = _numeric_columns(all_phase)

    agg = (
        all_phase
        .groupby(["phase_index", "game_phase", "power_name"], as_index=False)[num_cols]
        .mean()
    )

    n_phases = agg["phase_index"].nunique()
    fig_w = max(8, n_phases * 0.1 + 4)

    for col in num_cols:
        plt.figure(figsize=(fig_w, 6))
        sns.lineplot(
            data=agg,
            x="phase_index",
            y=col,
            hue="power_name",
            marker="o",
        )

        phases_sorted = (
            agg.drop_duplicates("phase_index")
            .sort_values("phase_index")[["phase_index", "game_phase"]]
        )
        plt.xticks(
            phases_sorted["phase_index"],
            phases_sorted["game_phase"],
            rotation=90,
            fontsize=8,
        )
        title = col.replace("_", " ").title()
        if title_suffix:
            title = f"{title} – {title_suffix}"
        plt.title(title)
        plt.xlabel("Game Phase")
        plt.tight_layout()
        plt.savefig(plot_dir / f"{_sanitize(col)}.png", dpi=140)
        plt.close()


def _plot_phase_level_per_game(
    all_phase: pd.DataFrame,
    root_dir: Path,
    gameid_to_rundir: dict[str, str],
) -> None:
    """
    Writes one folder of phase-plots per iteration.
    Folder name and chart titles use the run directory (e.g. run_00003).
    """
    if all_phase.empty or "game_id" not in all_phase.columns:
        return

    for game_id, sub in all_phase.groupby("game_id"):
        run_label = gameid_to_rundir.get(str(game_id), f"game_{_sanitize(str(game_id))}")
        target = root_dir / run_label

        # ── critical change: drop global phase_index so we rebuild a dense one ──
        sub = sub.copy().drop(columns=["phase_index"], errors="ignore")

        _plot_phase_level(sub, target, title_suffix=run_label)




# ───────────────────────── entry-point ─────────────────────────
def run(experiment_dir: Path, ctx: dict) -> None:  # pylint: disable=unused-argument
    root = experiment_dir / "analysis" / "statistical_game_analysis"
    indiv_dir = root / "individual"
    plots_root = root / "plots"

    # 1. (re)generate CSVs
    try:
        StatisticalGameAnalyzer().analyze_multiple_folders(
            str(experiment_dir / "runs"), str(root)
        )
        log.info("statistical_game_analysis: CSV generation complete")
    except Exception as exc:  # noqa: broad-except
        log.exception("statistical_game_analysis: CSV generation failed – %s", exc)
        return

    # 2. load CSVs
    game_csvs = _discover_csvs(indiv_dir, "*_game_analysis.csv")
    phase_csvs = _discover_csvs(indiv_dir, "*_phase_analysis.csv")

    if not game_csvs:
        log.warning("statistical_game_analysis: no *_game_analysis.csv found")
        return

    all_game_df = pd.concat((pd.read_csv(p) for p in game_csvs), ignore_index=True)
    all_phase_df = (
        pd.concat((pd.read_csv(p) for p in phase_csvs), ignore_index=True)
        if phase_csvs else pd.DataFrame()
    )

    # 3. plots
    sns.set_theme(style="whitegrid")
    _plot_game_level(all_game_df, plots_root / "game")
    _plot_phase_level(all_phase_df, plots_root / "phase")
    game_map = _map_game_id_to_run_dir(experiment_dir)
    _plot_phase_level_per_game(
        all_phase_df,
        plots_root / "phase_by_game",
        game_map,
    )


    log.info("statistical_game_analysis: plots written → %s", plots_root)
