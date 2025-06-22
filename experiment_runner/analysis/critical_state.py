"""
Extracts the board state *before* and *after* a critical phase
for every critical-analysis run produced by experiment_runner.

Each run must have:
• lmvsgame.json   – containing a phase named ctx["resume_from_phase"]

Outputs live in  analysis/critical_state/<run_name>_{before|after}.json
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List

log = logging.getLogger(__name__)


def _phase_by_name(phases: List[dict], name: str) -> dict | None:
    for ph in phases:
        if ph["state"]["name"] == name:
            return ph
    return None


def run(exp_dir: Path, ctx: Dict) -> None:
    resume_phase = ctx.get("resume_from_phase")
    if not resume_phase:
        log.info("critical_state: --resume_from_phase not supplied – skipping")
        return

    out_dir = exp_dir / "analysis" / "critical_state"
    out_dir.mkdir(parents=True, exist_ok=True)

    for run_dir in (exp_dir / "runs").iterdir():
        game_json = run_dir / "lmvsgame.json"
        if not game_json.exists():
            continue

        with game_json.open("r") as fh:
            game = json.load(fh)
        phases = game.get("phases", [])
        if not phases:
            continue

        before = _phase_by_name(phases, resume_phase)
        after = phases[-1] if phases else None
        if before is None or after is None:
            log.warning("Run %s missing expected phases – skipped", run_dir.name)
            continue

        (out_dir / f"{run_dir.name}_before.json").write_text(
            json.dumps(before, indent=2)
        )
        (out_dir / f"{run_dir.name}_after.json").write_text(
            json.dumps(after, indent=2)
        )

    log.info("critical_state: snapshots written to %s", out_dir)
