#!/usr/bin/env python3
"""Exibe o resumo estacionário."""

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def latest_completed(root):
    for case in sorted((root / "runs").glob("test*"), reverse=True):
        path = case / "run_status.json"
        if path.exists():
            status = json.loads(path.read_text())
            if status.get("simulation") == status.get("postprocessing") == "completed":
                return case
    raise ValueError("No completed run found. Use --case to select a run.")


def show(case):
    case = Path(case).resolve()
    summary = json.loads((case / "results/summary.json").read_text())
    value = summary["mean_Cp"]
    return "\n".join(
        [
            f"Run:         {case.name}",
            f"Converged:   {summary['converged']}",
            f"Iteration:   {summary['iteration_end']:g}",
            f"MRF speed:   {summary['prescribed_rpm_y']:.6g} RPM (Y)",
            f"Mean torque: {summary['mean_torque_y_N_m']:.6g} N.m",
            f"Mean power:  {summary['mean_aerodynamic_power_W']:.6g} W",
            f"Mean Cp:     {value:.6g}" if value is not None else "Mean Cp:     n/a",
            f"Results:     {case / 'results'}",
        ]
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Show steady MRF run results.")
    parser.add_argument("--case", type=Path)
    args = parser.parse_args()
    try:
        print(show(args.case or latest_completed(ROOT)))
    except (OSError, ValueError, KeyError) as error:
        parser.exit(1, f"[FAIL] Results: {error}\n")
