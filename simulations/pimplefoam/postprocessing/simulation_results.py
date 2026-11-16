"""Leitura das saídas OpenFOAM e cálculo dos resultados."""

import json
from pathlib import Path
import re

import numpy as np

NUMBER = r"[-+]?(?:\d*\.\d+|\d+\.?\d*)(?:[eE][-+]?\d+)?"
ROOT = Path(__file__).resolve().parents[1]


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


def read_motion_series(path):
    """Lê o último estado de cada passo PIMPLE."""
    states = {}
    time = None
    state = {}
    keys = {
        "Centre of rotation": "centre",
        "Centre of mass": "com",
        "Linear velocity": "velocity",
        "Angular velocity": "omega",
    }
    with path.open(errors="replace") as stream:
        for line in stream:
            match = re.match(r"^Time =\s*(" + NUMBER + r")\s*$", line)
            if match:
                time = float(match[1])
                state = {}
                continue
            for label, key in keys.items():
                match = re.search(re.escape(label) + r":\s*\(([^)]+)\)", line)
                if match:
                    values = [float(x) for x in re.findall(NUMBER, match[1])]
                    if len(values) != 3:
                        raise ValueError(f"Invalid state in log: {line}")
                    state[key] = values
                    if (
                        key == "omega"
                        and time is not None
                        and all(k in state for k in keys.values())
                    ):
                        states[time] = [
                            time,
                            *state["centre"],
                            *state["com"],
                            *state["velocity"],
                            *values,
                        ]
    if not states:
        raise ValueError(
            "No 6DoF states in log.pimpleFoam. Enable report and preserve the solver log."
        )
    result = np.array([states[times] for times in sorted(states)])
    if not np.isfinite(result).all():
        raise ValueError("Motion state contains NaN or Inf.")
    return result


def interpolate_series(times, data):
    tolerance = 1e-8 * max(1, float(times[-1]))
    if times[0] < data[0, 0] - tolerance or times[-1] > data[-1, 0] + tolerance:
        raise ValueError("Force and motion series do not cover the same times.")
    return np.column_stack(
        [np.interp(times, data[:, 0], data[:, i]) for i in range(1, data.shape[1])]
    )


def cumulative_trapezoid(times, power):
    return np.concatenate(
        [[0.0], np.cumsum(np.diff(times) * (power[1:] + power[:-1]) / 2)]
    )


def analyze(case):
    case = Path(case).resolve()
    metadata = json.loads((case / "metadata/resolved_config.json").read_text())
    config, body = metadata["config"], metadata["body"]
    log = case / "logs/log.pimpleFoam"
    if not log.exists():
        log = case / "log.pimpleFoam"
    motion = read_motion_series(log)
    moment = read_force_series(case, "moment.dat")
    force = read_force_series(case, "force.dat")
    times = moment[:, 0]
    if len(times) < 2:
        raise ValueError("At least two force samples are required to integrate energy.")
    states = interpolate_series(times, motion)
    forces = interpolate_series(times, force)
    angular = states[:, 9:12]
    omega = angular[:, 1]
    profile = np.array(config["wind"]["profile"])
    speed = np.interp(times, profile[:, 0], profile[:, 1])
    torque = moment[:, 2]
    # Preserva o sentido de rotação.
    power = torque * omega
    wind_power = 0.5 * config["fluid"]["density"] * body["swept_area"] * speed**3
    valid = speed >= config["output"]["min_wind_speed"]
    power_coefficient = np.full(len(times), np.nan)
    tip_speed_ratio = power_coefficient.copy()
    torque_coefficient = power_coefficient.copy()
    power_coefficient[valid] = power[valid] / wind_power[valid]
    tip_speed_ratio[valid] = omega[valid] * body["radius"] / speed[valid]
    torque_coefficient[valid] = torque[valid] / (
        0.5
        * config["fluid"]["density"]
        * body["swept_area"]
        * speed[valid] ** 2
        * body["radius"]
    )
    dissipated = config["motion"]["shaft_damping"] * omega**2
    orientation = np.array(body["orientation"]).reshape(3, 3)
    # Transfere a inércia para o eixo Y.
    tensor = orientation @ np.diag(body["momentOfInertia"]) @ orientation.T
    offset = np.array(body["centreOfMass"]) - config["geometry"]["rotation_centre"]
    inertia_y = tensor[1, 1] + body["mass"] * (offset[0] ** 2 + offset[2] ** 2)
    kinetic = 0.5 * inertia_y * omega**2
    energy = cumulative_trapezoid(times, power)
    loss_energy = cumulative_trapezoid(times, dissipated)
    data = np.column_stack(
        [
            times,
            speed,
            omega,
            omega * 60 / (2 * np.pi),
            torque,
            forces[:, 1],
            power,
            wind_power,
            power_coefficient,
            tip_speed_ratio,
            torque_coefficient,
            dissipated,
            kinetic,
            energy,
            loss_energy,
        ]
    )
    columns = [
        "time_s",
        "inlet_speed_m_s",
        "omega_y_rad_s",
        "rpm_y",
        "torque_y_N_m",
        "axial_force_y_N",
        "aerodynamic_power_W",
        "available_wind_power_W",
        "Cp",
        "TSR",
        "Cq",
        "shaft_dissipation_W",
        "rotor_kinetic_energy_J",
        "aerodynamic_energy_J",
        "shaft_dissipated_energy_J",
    ]
    summary = {
        "time_start_s": float(times[0]),
        "time_end_s": float(times[-1]),
        "samples": len(times),
        "rotor_radius_m": body["radius"],
        "mass_kg": body["mass"],
        "volume_m3": body["volume"],
        "inertia_about_shaft_kg_m2": float(inertia_y),
        "final_omega_y_rad_s": float(omega[-1]),
        "final_rpm_y": float(data[-1, 3]),
        "aerodynamic_energy_J": float(energy[-1]),
        "shaft_dissipated_energy_J": float(loss_energy[-1]),
        "kinetic_energy_change_J": float(kinetic[-1] - kinetic[0]),
        "energy_balance_residual_J": float(
            energy[-1] - loss_energy[-1] - (kinetic[-1] - kinetic[0])
        ),
        "mean_aerodynamic_power_W": float(energy[-1] / (times[-1] - times[0])),
        "notes": [
            "Potência aerodinâmica assinada = torque total Y × omega Y; não representa potência elétrica.",
            "Energia integrada apenas no intervalo de amostras informado, pela regra dos trapézios.",
            "Cp, Cq e TSR são NaN quando o vento é inferior ao limiar do YAML.",
            "Coeficientes instantâneos usam a velocidade prescrita no inlet, não a velocidade local no rotor.",
            "Resíduo de energia é diagnóstico; depende da discretização e do acoplamento fluido/corpo.",
        ],
    }
    if config.get("bench"):
        summary["coefficient_reference"] = "fan_disk_speed_and_rotor_swept_area"
        summary["notes"].append(
            "Disco finito: Cp é nominal e não mede a eficiência elétrica ou o fluxo de energia real que atravessa o rotor."
        )
    summary["mean_torque_y_N_m"] = float(
        cumulative_trapezoid(times, torque)[-1] / (times[-1] - times[0])
    )
    summary["mean_abs_torque_y_N_m"] = float(
        cumulative_trapezoid(times, np.abs(torque))[-1] / (times[-1] - times[0])
    )
    summary["notes"].append(
        "Torques médios são médias temporais trapezoidais no intervalo informado, incluindo a partida."
    )
    return data, columns, motion, summary


def save_analysis(case):
    data, columns, motion, summary = analyze(case)
    output = Path(case) / "results"
    output.mkdir(exist_ok=True)
    np.savetxt(
        output / "timeseries.csv",
        data,
        delimiter=",",
        header=",".join(columns),
        comments="",
        fmt="%.12g",
    )
    motion_columns = [
        "time_s",
        "centre_x_m",
        "centre_y_m",
        "centre_z_m",
        "com_x_m",
        "com_y_m",
        "com_z_m",
        "velocity_x_m_s",
        "velocity_y_m_s",
        "velocity_z_m_s",
        "omega_x_rad_s",
        "omega_y_rad_s",
        "omega_z_rad_s",
    ]
    np.savetxt(
        output / "motion.csv",
        motion,
        delimiter=",",
        header=",".join(motion_columns),
        comments="",
        fmt="%.12g",
    )
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n"
    )
    (output / "energy_summary.txt").write_text(
        "\n".join(f"{k}: {v}" for k, v in summary.items() if k != "notes")
        + "\n\n"
        + "\n".join(summary["notes"])
        + "\n"
    )
    return data, columns
