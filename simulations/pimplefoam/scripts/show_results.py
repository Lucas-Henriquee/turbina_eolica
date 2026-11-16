#!/usr/bin/env python3
"""Exibe o resumo da execução."""

import argparse
import json
import math
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def latest_completed(root):
    for case in sorted((root / "runs").glob("test[0-9]*"), reverse=True):
        status = case / "run_status.json"
        if status.exists():
            state = json.loads(status.read_text())
            if state.get("simulation") == state.get("postprocessing") == "completed":
                return case
    raise ValueError("No completed run found. Use --case to select a run.")


def number(value, unit="", digits=6):
    if value is None:
        return "n/a"
    value = float(value)
    return (
        f'{value:.{digits}g}{" " + unit if unit else ""}'
        if math.isfinite(value)
        else "n/a"
    )


def show(case):
    case = Path(case).resolve()
    summary = json.loads((case / "results/summary.json").read_text())
    state = json.loads((case / "run_status.json").read_text())
    if (
        state.get("simulation") != "completed"
        or state.get("postprocessing") != "completed"
    ):
        raise ValueError(f"Run is incomplete: {case}")
    mesh = case / "logs/log.checkMesh"
    match = (
        re.search(r"^\s*cells:\s*(\d+)", mesh.read_text(errors="replace"), re.M)
        if mesh.exists()
        else None
    )
    try:
        display_case = case.relative_to(Path.cwd())
    except ValueError:
        display_case = case
    return "\n".join(
        [
            f"Run:         {case.name}",
            f'Time:        {number(summary["time_end_s"], "s")}',
            f'Cells:       {match[1] if match else "n/a"}',
            f'Final RPM:   {number(summary["final_rpm_y"])}',
            f'Mean torque: {number(summary.get("mean_torque_y_N_m"), "N.m")}',
            f'Aero energy: {number(summary["aerodynamic_energy_J"], "J")}',
            f"Results:     {display_case}/results/",
            f"Report:      {display_case}/config.txt",
        ]
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Show a completed run summary.")
    parser.add_argument(
        "--case", type=Path, help="Run directory; defaults to the latest completed run."
    )
    args = parser.parse_args()
    try:
        print(show(args.case or latest_completed(ROOT)))
    except (OSError, ValueError, KeyError) as error:
        parser.exit(1, f"[FAIL] Run summary: {error}\n")
