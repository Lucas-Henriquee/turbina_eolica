"""Leitura das saídas OpenFOAM e cálculo dos resultados."""

import json
from pathlib import Path
import re
import sys

import numpy as np

NUMBER = r"[-+]?(?:\d*\.\d+|\d+\.?\d*)(?:[eE][-+]?\d+)?"
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from generator_model import resolve_generator


def read_forces(path, components=False):
    """Lê o total e, se solicitado, as parcelas de pressão e viscosidade."""
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
    groups = data[:, 1:].reshape(len(data), -1, 3)
    has_total = "total" in description
    if not has_total and not ("pressure" in description and "viscous" in description):
        raise ValueError(
            f"Unknown force header: {path}; total torque cannot be inferred."
        )
    total = groups[:, 0] if has_total else groups.sum(axis=1)
    if components:
        offset = int(has_total)
        if groups.shape[1] < offset + 2:
            raise ValueError(f"Pressure and viscous components missing: {path}")
        return np.column_stack([data[:, 0], total, groups[:, offset], groups[:, offset + 1]])
    return np.column_stack([data[:, 0], total])


def read_force_series(case, name, components=False):
    files = list((case / "postProcessing/forcesRotor").glob("*/" + name))
    if not files:
        raise ValueError(f"{name} missing from {case}/postProcessing/forcesRotor")
    values = {}
    for file in sorted(files, key=lambda p: float(p.parent.name)):
        for row in read_forces(file, components):
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


def prescribed_torque_balance(moment, rpm, shaft_damping, generator):
    # Usa até três voltas completas no fim da execução.
    times = moment[:, 0]
    period = 60 / abs(rpm)
    turns = min(3, int((times[-1] - times[0]) / period))
    result = {"complete_revolutions": turns}
    if turns == 0:
        return result

    start = times[-1] - turns * period
    window = np.r_[start, times[times > start]]
    torques = interpolate_series(window, moment)[:, [1, 4, 7]] * np.sign(rpm)
    mean_total, mean_pressure, mean_viscous = (
        cumulative_trapezoid(window, component)[-1] / (window[-1] - start)
        for component in torques.T
    )
    speed = abs(rpm) * np.pi / 30
    electric = generator["electrical_damping_N_m_s_rad"] * speed
    mechanical = (shaft_damping + generator["mechanical_damping_N_m_s_rad"]) * speed
    result.update(
        window_start_s=float(start),
        window_end_s=float(times[-1]),
        mean_aero_drive_torque_N_m=float(mean_total),
        mean_pressure_drive_torque_N_m=float(mean_pressure),
        mean_viscous_drive_torque_N_m=float(mean_viscous),
        model_electrical_brake_N_m=float(electric),
        model_mechanical_brake_N_m=float(mechanical),
        model_total_brake_N_m=float(electric + mechanical),
        net_drive_torque_N_m=float(mean_total - electric - mechanical),
    )
    return result


def free_torque_balance(times, torque, omega, inertia, damping):
    # Compara o saldo de torque com a aceleração no último segundo.
    start = max(times[0], times[-1] - 1)
    window = np.r_[start, times[times > start]]
    duration = window[-1] - start
    direction = np.sign(omega[-1])
    if direction == 0:
        return None
    speed = np.interp(window, times, omega) * direction
    aero = np.interp(window, times, torque) * direction
    mean_aero = cumulative_trapezoid(window, aero)[-1] / duration
    mean_brake = damping * cumulative_trapezoid(window, speed)[-1] / duration
    acceleration_torque = inertia * (speed[-1] - speed[0]) / duration
    return {
        "window_start_s": float(start),
        "window_end_s": float(window[-1]),
        "mean_aero_drive_torque_N_m": float(mean_aero),
        "model_total_brake_N_m": float(mean_brake),
        "net_drive_torque_N_m": float(mean_aero - mean_brake),
        "inertial_torque_N_m": float(acceleration_torque),
        "balance_residual_N_m": float(mean_aero - mean_brake - acceleration_torque),
    }


def analyze(case):
    case = Path(case).resolve()
    metadata = json.loads((case / "metadata/resolved_config.json").read_text())
    config, body = metadata["config"], metadata["body"]
    rpm = config["motion"].get("prescribed_rpm")
    moment = read_force_series(case, "moment.dat", components=rpm is not None)
    force = read_force_series(case, "force.dat")
    times = moment[:, 0]
    if len(times) < 2:
        raise ValueError("At least two force samples are required to integrate energy.")
    if rpm is None:
        log = case / "logs/log.pimpleFoam"
        if not log.exists():
            log = case / "log.pimpleFoam"
        motion = read_motion_series(log)
        states = interpolate_series(times, motion)
    else:
        motion = np.zeros((len(times), 13))
        motion[:, 0] = times
        centre = np.array(config["geometry"]["rotation_centre"])
        motion[:, 1:4] = centre
        offset = np.array(body["centreOfMass"]) - centre
        omega_y = rpm * np.pi / 30
        angle = times * omega_y
        motion[:, 4] = centre[0] + offset[0] * np.cos(angle) + offset[2] * np.sin(angle)
        motion[:, 5] = centre[1] + offset[1]
        motion[:, 6] = centre[2] - offset[0] * np.sin(angle) + offset[2] * np.cos(angle)
        motion[:, 11] = omega_y
        states = motion[:, 1:]
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
    generator = resolve_generator(config)
    electrical_loss = generator["electrical_damping_N_m_s_rad"] * omega**2
    generator_mechanical_loss = generator["mechanical_damping_N_m_s_rad"] * omega**2
    mechanical_loss = config["motion"]["shaft_damping"] * omega**2 + generator_mechanical_loss
    dissipated = mechanical_loss + electrical_loss
    current = voltage = load_power = internal_loss = shunt_loss = np.full_like(omega, np.nan)
    generator_torque = np.full_like(omega, np.nan)
    load_energy = np.full_like(omega, np.nan)
    if generator["enabled"]:
        current = generator["back_emf_constant_V_s_rad"] * omega / generator["total_resistance_ohm"]
        voltage = current * generator["load_resistance_ohm"]
        load_power = current**2 * generator["load_resistance_ohm"]
        internal_loss = current**2 * generator["internal_resistance_ohm"]
        shunt_loss = current**2 * generator["shunt_resistance_ohm"]
        generator_torque = -generator["torque_constant_N_m_A"] * current
        load_energy = cumulative_trapezoid(times, load_power)
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
            mechanical_loss,
            generator_torque,
            current,
            voltage,
            load_power,
            internal_loss,
            shunt_loss,
            load_energy,
            generator_mechanical_loss,
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
        "mechanical_loss_W",
        "generator_torque_y_N_m",
        "generator_current_A",
        "generator_load_voltage_V",
        "generator_load_power_W",
        "generator_internal_loss_W",
        "generator_shunt_loss_W",
        "generator_load_energy_J",
        "generator_no_load_loss_W",
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
        "energy_balance_residual_J": None if rpm is not None else float(
            energy[-1] - loss_energy[-1] - (kinetic[-1] - kinetic[0])
        ),
        "mean_aerodynamic_power_W": float(energy[-1] / (times[-1] - times[0])),
        "generator_model": generator,
        "generator_load_energy_J": float(load_energy[-1]) if generator["enabled"] else None,
        "mean_generator_load_power_W": float(load_energy[-1] / (times[-1] - times[0])) if generator["enabled"] else None,
        "mechanical_loss_energy_J": float(cumulative_trapezoid(times, mechanical_loss)[-1]),
        "generator_no_load_loss_energy_J": float(cumulative_trapezoid(times, generator_mechanical_loss)[-1]),
        "generator_extracted_energy_J": float(cumulative_trapezoid(times, electrical_loss)[-1]),
        "notes": [
            "Potência aerodinâmica assinada = torque total Y × omega Y; não representa potência elétrica.",
            "Energia integrada apenas no intervalo de amostras informado, pela regra dos trapézios.",
            "Cp, Cq e TSR são NaN quando o vento é inferior ao limiar do YAML.",
            "Coeficientes instantâneos usam a velocidade prescrita no inlet, não a velocidade local no rotor.",
            "Resíduo de energia é diagnóstico; depende da discretização e do acoplamento fluido/corpo.",
        ],
    }
    if rpm is not None:
        summary["prescribed_rpm_y"] = rpm
        summary["prescribed_torque_balance"] = prescribed_torque_balance(
            moment, rpm, config["motion"]["shaft_damping"], generator
        )
        summary["notes"].append(
            "Rotação imposta. Freio e geração elétrica são referências do modelo; "
            "a diferença de torque é compensada pela imposição de velocidade."
        )
    else:
        damping = (
            config["motion"]["shaft_damping"]
            + generator["electrical_damping_N_m_s_rad"]
            + generator["mechanical_damping_N_m_s_rad"]
        )
        summary["free_torque_balance"] = free_torque_balance(
            times, torque, omega, inertia_y, damping
        )
    if config.get("bench"):
        summary["coefficient_reference"] = "fan_disk_speed_and_rotor_swept_area"
        summary["notes"].append(
            "Disco finito: Cp é nominal e não mede a eficiência elétrica ou o fluxo de energia real que atravessa o rotor."
        )
    if generator["enabled"]:
        summary["notes"].extend([
            "Potência elétrica estimada no resistor: I²R; modelo de motor semelhante, sem calibração do RS-775SF.",
            "Dissipação do eixo inclui carga elétrica, perdas internas, shunt e amortecimento mecânico separado.",
            "Corrente e tensão do modelo seguem a convenção de sinal do eixo Y; compare módulos com a bancada.",
            "Indutância, queda não linear nas escovas e inércia interna do gerador não incluídas.",
        ])
        if generator["mechanical_loss_model"] == "viscous_from_no_load":
            summary["notes"].append(
                "Perdas sem carga do catálogo extrapoladas como amortecimento viscoso; atrito em baixa rotação não calibrado."
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
