"""Lê forças e calcula resultados estacionários."""

import json
import math
from pathlib import Path
import re

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
NUMBER = r"[-+]?(?:\d*\.\d+|\d+\.?\d*)(?:[eE][-+]?\d+)?"


def read_forces(path):
    """2512: total/pressure/viscous. Formato antigo: pressure/viscous/porous."""
    header = []
    rows = []
    for line in path.read_text().splitlines():
        if line.lstrip().startswith("#"):
            header.append(line.lower())
            continue
        if not line.strip():
            continue
        row = [float(x) for x in re.findall(NUMBER, line)]
        if len(row) < 7 or (len(row) - 1) % 3:
            raise ValueError(f"Invalid row in {path}: {line}")
        rows.append(row)
    if not rows:
        raise ValueError(f"No data: {path}")
    description = " ".join(header)
    data = np.array(rows)
    if "total" in description:
        total = data[:, 1:4]
    elif "pressure" in description and "viscous" in description:
        total = data[:, 1:].reshape(len(data), -1, 3).sum(axis=1)
    else:
        raise ValueError(
            f"Unknown force header: {path}; total torque cannot be inferred."
        )
    return np.column_stack([data[:, 0], total])


def read_force_series(case, name):
    files = list((case / "postProcessing/forcesRotor").glob("*/" + name))
    if not files:
        raise ValueError(f"{name} missing from {case}/postProcessing/forcesRotor")
    values = {}
    for file in sorted(files, key=lambda p: float(p.parent.name)):
        for row in read_forces(file):
            values[row[0]] = row
    return np.array([values[times] for times in sorted(values)])


def interpolate_series(iterations, data):
    tolerance = 1e-8 * max(1, float(iterations[-1]))
    if (
        iterations[0] < data[0, 0] - tolerance
        or iterations[-1] > data[-1, 0] + tolerance
    ):
        raise ValueError("Force and moment series do not cover the same iterations.")
    return np.column_stack(
        [np.interp(iterations, data[:, 0], data[:, i]) for i in range(1, data.shape[1])]
    )


def analyze(case):
    case = Path(case).resolve()
    resolved = json.loads((case / "metadata/resolved_config.json").read_text())
    config, geometry = resolved["config"], resolved["body"]
    moments = read_force_series(case, "moment.dat")
    forces = read_force_series(case, "force.dat")
    iterations = moments[:, 0]
    if len(iterations) < 2 or np.any(np.diff(iterations) <= 0):
        raise ValueError("At least two increasing iteration samples are required.")
    axial_force = interpolate_series(iterations, forces)[:, 1]
    torque = moments[:, 2]
    angular_velocity = config["rotation"]["angular_velocity"]
    speed = float(np.linalg.norm(config["initial"]["velocity"]))
    available_power = (
        0.5 * config["fluid"]["density"] * geometry["swept_area"] * speed**3
    )
    # Preserva o sinal em relação ao eixo Y.
    power = torque * angular_velocity
    coefficient = (
        power / available_power
        if speed >= config["output"]["min_wind_speed"]
        else np.full(len(power), np.nan)
    )
    rpm = angular_velocity * 60 / (2 * math.pi)
    tip_speed_ratio = abs(angular_velocity) * geometry["radius"] / speed
    first = min(
        int(len(iterations) * config["output"]["average_start_fraction"]),
        len(iterations) - 1,
    )
    selected = slice(first, None)
    log = case / "logs/log.simpleFoam"
    if not log.exists():
        log = case / "log.simpleFoam"
    converged = False
    if log.exists():
        with log.open(errors="replace") as stream:
            converged = any("SIMPLE solution converged" in line for line in stream)
    data = np.column_stack(
        [
            iterations,
            np.full(len(iterations), rpm),
            torque,
            axial_force,
            power,
            np.full(len(iterations), available_power),
            coefficient,
            np.full(len(iterations), tip_speed_ratio),
        ]
    )
    columns = [
        "iteration",
        "rpm_y",
        "torque_y_N_m",
        "axial_force_y_N",
        "aerodynamic_power_W",
        "available_wind_power_W",
        "Cp",
        "TSR",
    ]
    summary = {
        "model": "steady_mrf",
        "converged": converged,
        "iteration_start": float(iterations[0]),
        "iteration_end": float(iterations[-1]),
        "samples": len(iterations),
        "averaged_samples": len(iterations[first:]),
        "average_start_iteration": float(iterations[first]),
        "rotor_radius_m": geometry["radius"],
        "swept_area_m2": geometry["swept_area"],
        "prescribed_omega_y_rad_s": angular_velocity,
        "prescribed_rpm_y": rpm,
        "inlet_speed_m_s": speed,
        "mean_torque_y_N_m": float(np.mean(torque[selected])),
        "mean_abs_torque_y_N_m": float(np.mean(np.abs(torque[selected]))),
        "mean_axial_force_y_N": float(np.mean(axial_force[selected])),
        "mean_aerodynamic_power_W": float(np.mean(power[selected])),
        "available_wind_power_W": available_power,
        "mean_Cp": (
            float(np.mean(coefficient[selected]))
            if np.isfinite(coefficient[selected]).all()
            else None
        ),
        "TSR": tip_speed_ratio,
        "notes": [
            "Iteration indices are not physical time.",
            "MRF angular velocity is prescribed; rotor acceleration is not solved.",
            "Signed aerodynamic power equals torque_y times omega_y.",
            "TSR uses the magnitude of prescribed rotation.",
            "No energy integral is computed from steady iteration indices.",
            "Reported averages use the configured trailing sample fraction.",
            "Solver convergence does not establish mesh independence or experimental agreement.",
        ],
    }
    return data, columns, summary


def save_analysis(case):
    data, columns, summary = analyze(case)
    output = Path(case) / "results"
    output.mkdir(exist_ok=True)
    np.savetxt(
        output / "iterations.csv",
        data,
        delimiter=",",
        header=",".join(columns),
        comments="",
        fmt="%.12g",
    )
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    (output / "summary.txt").write_text(
        "\n".join(f"{key}: {value}" for key, value in summary.items() if key != "notes")
        + "\n\n"
        + "\n".join(summary["notes"])
        + "\n"
    )
    return data, columns
