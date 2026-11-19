"""Modelo DC quase estacionário com carga resistiva."""

import math


def resolve_generator(config):
    generator = config.get("generator")
    if not generator or not generator.get("enabled", False):
        return {"enabled": False, "electrical_damping_N_m_s_rad": 0.0}

    values = {}
    for key in ["nominal_voltage_V", "no_load_speed_rpm", "no_load_current_A",
                "stall_current_A", "load_resistance_ohm", "shunt_resistance_ohm"]:
        value = generator[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"generator.{key} must be a finite number.")
        values[key] = value
    for key in ["nominal_voltage_V", "no_load_speed_rpm", "stall_current_A", "load_resistance_ohm"]:
        if values[key] <= 0:
            raise ValueError(f"generator.{key} must be positive.")
    if not 0 <= values["no_load_current_A"] < values["stall_current_A"]:
        raise ValueError("Generator no-load current must be non-negative and below stall current.")
    if values["shunt_resistance_ohm"] < 0:
        raise ValueError("Generator shunt resistance must be non-negative.")

    resistance = values["nominal_voltage_V"] / values["stall_current_A"]
    omega = values["no_load_speed_rpm"] * 2 * math.pi / 60
    ke = (values["nominal_voltage_V"] - resistance * values["no_load_current_A"]) / omega
    total_resistance = resistance + values["load_resistance_ohm"] + values["shunt_resistance_ohm"]
    # Modelo ideal em SI: kt = ke; perdas mecânicas tratadas separadamente.
    damping = ke * ke / total_resistance
    if not all(math.isfinite(x) and x > 0 for x in [resistance, ke, total_resistance, damping]):
        raise ValueError("Derived generator parameters must be finite and positive.")
    return {
        "enabled": True,
        "reference_model": generator["reference_model"],
        "source_url": generator["source_url"],
        "internal_resistance_ohm": resistance,
        "total_resistance_ohm": total_resistance,
        "back_emf_constant_V_s_rad": ke,
        "torque_constant_N_m_A": ke,
        "electrical_damping_N_m_s_rad": damping,
        "load_resistance_ohm": values["load_resistance_ohm"],
        "shunt_resistance_ohm": values["shunt_resistance_ohm"],
        "assumptions": [
            "surrogate_motor_not_measured_RS775SF",
            "quasi_steady_resistive_load",
            "kt_equals_ke_in_SI",
            "no_inductance_or_non_linear_brush_voltage_drop",
            "no_generator_rotor_inertia",
            "no_mechanical_losses_inferred_from_catalog_no_load_current",
        ],
    }
