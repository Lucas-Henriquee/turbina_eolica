#!/usr/bin/env python3
"""Gera gráficos por iteração."""

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from simulation_results import ROOT, save_analysis


def plot_results(case):
    path = case / "results/iterations.csv"
    if not path.exists():
        save_analysis(case)
    data = np.genfromtxt(path, delimiter=",", names=True)
    graphs = [
        ("torque_y_N_m", "Torque Y (N.m)", "torque_vs_iteration.png"),
        ("axial_force_y_N", "Axial force Y (N)", "axial_force_vs_iteration.png"),
        (
            "aerodynamic_power_W",
            "Signed aerodynamic power (W)",
            "power_vs_iteration.png",
        ),
        ("Cp", "Power coefficient", "power_coefficient_vs_iteration.png"),
    ]
    for column, label, filename in graphs:
        figure, axes = plt.subplots(figsize=(8, 4.5))
        axes.plot(data["iteration"], data[column])
        axes.set(xlabel="Iteration", ylabel=label)
        axes.grid(True, alpha=0.3)
        figure.tight_layout()
        figure.savefig(path.parent / filename, dpi=180)
        plt.close(figure)
    print(f"[OK] Plots: {path.parent}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Plot steady MRF iteration results.")
    parser.add_argument("--case", type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        plot_results(args.case.resolve())
    except (OSError, ValueError, KeyError) as error:
        parser.exit(1, f"[FAIL] Plots: {error}\n")
