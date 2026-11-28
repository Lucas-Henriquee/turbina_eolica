#!/usr/bin/env python3
"""Gera os gráficos da execução."""
import argparse
from pathlib import Path
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from simulation_results import ROOT, save_analysis


def plot_results(case):
    output = case / "results"
    csv = output / "timeseries.csv"
    if not csv.exists():
        save_analysis(case)
    data = np.genfromtxt(csv, delimiter=",", names=True)
    graphs = [
        ("rpm_y", "Rotação no eixo Y (RPM)", "rpm_vs_time.png"),
        ("torque_y_N_m", "Torque no eixo Y (N.m)", "torque_vs_time.png"),
        ("aerodynamic_power_W", "Potência aerodinâmica (W)", "power_vs_time.png"),
        (
            "Cp",
            "Cp nominal (velocidade no inlet, área do rotor)",
            "power_coefficient_vs_time.png",
        ),
        ("axial_force_y_N", "Força axial (N)", "axial_force_vs_time.png"),
        ("inlet_speed_m_s", "Velocidade de entrada (m/s)", "inlet_speed_vs_time.png"),
        (
            "aerodynamic_energy_J",
            "Energia aerodinâmica acumulada (J)",
            "energy_vs_time.png",
        ),
    ]
    if "generator_load_power_W" in data.dtype.names and np.isfinite(data["generator_load_power_W"]).any():
        graphs.extend([
            ("generator_load_power_W", "Potência elétrica estimada na carga (W)", "generator_load_power_vs_time.png"),
            ("generator_current_A", "Corrente estimada no eixo Y (A)", "generator_current_vs_time.png"),
            ("generator_load_voltage_V", "Tensão estimada no eixo Y (V)", "generator_load_voltage_vs_time.png"),
            ("generator_load_energy_J", "Energia estimada na carga (J)", "generator_load_energy_vs_time.png"),
        ])
    bench_graphs = [
        ("bench_load_voltage_V", "Tensão estimada na carga (V)", "bench_load_voltage_vs_time.png"),
        ("bench_current_A", "Corrente estimada por V/R (A)", "bench_current_vs_time.png"),
        ("bench_load_power_W", "Potência estimada por V²/R (W)", "bench_load_power_vs_time.png"),
        ("bench_load_energy_J", "Energia estimada na faixa calibrada (J)", "bench_load_energy_vs_time.png"),
    ]
    for column, label, name in bench_graphs:
        if column in data.dtype.names and np.isfinite(data[column]).any():
            graphs.append((column, label, name))
        else:
            (output / name).unlink(missing_ok=True)
    for column, label, name in graphs:
        fig, ax = plt.subplots(figsize=(8, 4.5))
        ax.plot(data["time_s"], data[column])
        ax.set(xlabel="Tempo (s)", ylabel=label)
        ax.grid(True, alpha=0.3)
        fig.tight_layout()
        fig.savefig(output / name, dpi=180)
        plt.close(fig)
    print(f"[OK] Plots: {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Plot simulation results.")
    parser.add_argument("--case", type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        plot_results(args.case.resolve())
    except (OSError, ValueError, KeyError) as error:
        parser.exit(1, f"[FAIL] Plots: {error}\n")
