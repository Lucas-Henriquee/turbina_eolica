"""Valida os parâmetros do caso."""

import math
import re
from generator_model import resolve_generator


def validate_controls(config, templates):
    for key in ["mass_correction_kg", "shaft_inertia_correction_kg_m2"]:
        config["geometry"].setdefault(key, 0.0)
    def finite(value, name, lower=None, integer=False):
        if isinstance(value, bool):
            raise ValueError(f"{name}: expected a number, not a boolean.")
        number = float(value)
        if (
            not math.isfinite(number)
            or (lower is not None and number < lower)
            or (integer and (not isinstance(value, int)))
        ):
            raise ValueError(f"{name}: invalid numeric value ({value}).")
        return number

    def text(value, name):
        if (
            not isinstance(value, str)
            or not value.strip()
            or any(c in value for c in ';{}\n\r#$"')
        ):
            raise ValueError(f"{name}: invalid OpenFOAM text.")

    def keys(mapping, allowed, name):
        if not isinstance(mapping, dict):
            raise ValueError(f"{name}: expected a YAML mapping.")
        missing = set(allowed) - set(mapping)
        unknown = set(mapping) - set(allowed)
        if missing or unknown:
            raise ValueError(
                f"{name}: missing {sorted(missing)}, unknown {sorted(unknown)}."
            )

    schema = {
        "geometry": [
            "rotor_stl",
            "rotation_centre",
            "material_density",
            "mass_correction_kg",
            "shaft_inertia_correction_kg_m2",
            "cylinder_stl",
            "cylinder_mode",
            "cylinder_radial_clearance",
            "cylinder_axial_clearance",
            "cylinder_segments",
        ],
        "bench": [
            "fan_diameter",
            "fan_distance",
            "axis_height",
            "fan_refinement",
            "fan_refinement_depth",
        ],
        "initial": ["velocity", "pressure"],
        "fluid": ["density", "nu"],
        "turbulence": ["model", "k", "omega"],
        "wind": ["profile", "reference_speed"],
        "motion": [
            "ami_low_weight_correction",
            "inner_distance",
            "outer_distance",
            "gravity",
            "acceleration_relaxation",
            "acceleration_damping",
            "shaft_damping",
            "integration",
        ],
        "time": [
            "endTime",
            "deltaT",
            "maxDeltaT",
            "maxCo",
            "writeInterval",
            "writePrecision",
            "adjustTimeStep",
            "writeFormat",
            "writeCompression",
            "timePrecision",
        ],
        "output": ["sample_steps", "yplus_interval", "min_wind_speed", "plots"],
        "parallel": ["processes", "method", "divisions", "order", "mpi_test_timeout"],
        "mesh": [
            "bounds",
            "cells",
            "location_in_mesh",
            "maxLocalCells",
            "maxGlobalCells",
            "rotor_level",
            "cylinder_level",
            "distance_levels",
            "add_layers",
            "surface_layers",
            "castellated_controls",
            "snap_controls",
            "layer_controls",
            "quality_controls",
            "merge_tolerance",
            "feature_included_angle",
        ],
        "numerics": [
            "nOuterCorrectors",
            "nCorrectors",
            "nNonOrthogonalCorrectors",
            "momentumPredictor",
            "solvers",
            "relaxation",
        ],
        "schemes": [
            "time",
            "gradient",
            "velocity_gradient",
            "velocity_divergence",
            "k_divergence",
            "omega_divergence",
            "viscous_divergence",
            "laplacian",
            "interpolation",
            "normal_gradient",
            "wall_distance",
        ],
    }
    if "generator" in config:
        config["generator"].setdefault("mechanical_loss_model", "none")
        schema["generator"] = [
            "enabled", "mechanical_loss_model", "reference_model", "source_url", "nominal_voltage_V",
            "no_load_speed_rpm", "no_load_current_A", "stall_current_A",
            "load_resistance_ohm", "shunt_resistance_ohm",
        ]
    keys(config, schema, "config")
    for section, allowed in schema.items():
        keys(config[section], allowed, section)
    if "generator" in config:
        if not isinstance(config["generator"]["enabled"], bool):
            raise ValueError("generator.enabled must be true or false.")
        text(config["generator"]["reference_model"], "generator.reference_model")
        url = config["generator"]["source_url"]
        if not isinstance(url, str) or not url.startswith("https://") or any(c.isspace() for c in url):
            raise ValueError("generator.source_url must be an HTTPS URL.")
        resolve_generator(config)
    threshold = finite(
        config["motion"]["ami_low_weight_correction"],
        "motion.ami_low_weight_correction",
        0,
    )
    if threshold > 1:
        raise ValueError("ami_low_weight_correction must be between 0 and 1.")
    for key in ["fan_diameter", "fan_distance", "axis_height", "fan_refinement_depth"]:
        finite(config["bench"][key], "bench." + key, 1e-12)
    finite(config["bench"]["fan_refinement"], "bench.fan_refinement", 0, True)
    for section, key in [
        ("time", "adjustTimeStep"),
        ("time", "writeCompression"),
        ("output", "plots"),
        ("mesh", "add_layers"),
        ("numerics", "momentumPredictor"),
    ]:
        if not isinstance(config[section][key], bool):
            raise ValueError(f"{section}.{key} must be true or false.")
    if config["time"]["writeFormat"] not in ["ascii", "binary"]:
        raise ValueError("writeFormat must be ascii or binary.")
    finite(config["time"]["timePrecision"], "time.timePrecision", 6, True)
    for section, key in [("initial", "velocity"), ("motion", "gravity")]:
        values = config[section][key]
        if not isinstance(values, list) or len(values) != 3:
            raise ValueError(f"{section}.{key}: expected three components.")
        for value in values:
            finite(value, f"{section}.{key}")
    finite(config["initial"]["pressure"], "initial.pressure")
    for key in ["mass_correction_kg", "shaft_inertia_correction_kg_m2"]:
        finite(config["geometry"][key], "geometry." + key)
    finite(config["motion"]["shaft_damping"], "motion.shaft_damping", 0)
    for key in ["inner_distance", "outer_distance"]:
        if config["motion"][key] is not None:
            finite(config["motion"][key], f"motion.{key}", 0)
    # Campos compatíveis com kOmegaSST.
    if config["turbulence"]["model"] != "kOmegaSST":
        raise ValueError(
            "Only kOmegaSST is supported by the current fields and boundary conditions."
        )
    integration = config["motion"]["integration"]
    keys(integration, ["type", "gamma", "beta", "aoc", "voc"], "motion.integration")
    if integration["type"] not in ["Newmark", "CrankNicolson"]:
        raise ValueError("motion.integration.type must be Newmark or CrankNicolson.")
    for key in ["gamma", "beta", "aoc", "voc"]:
        finite(integration[key], f"motion.integration.{key}", 0)
    if (
        integration["type"] == "Newmark"
        and integration["beta"] < 0.25 * (integration["gamma"] + 0.5) ** 2
    ):
        raise ValueError("Newmark requires beta >= 0.25*(gamma+0.5)^2.")
    for key in ["aoc", "voc"]:
        if integration[key] > 1:
            raise ValueError(f"motion.integration.{key} must be <= 1.")
    if config["parallel"]["method"] not in ["scotch", "simple", "hierarchical"]:
        raise ValueError("parallel.method must be scotch, simple or hierarchical.")
    finite(config["parallel"]["mpi_test_timeout"], "parallel.mpi_test_timeout", 1, True)
    divisions = config["parallel"]["divisions"]
    if not isinstance(divisions, list) or len(divisions) != 3:
        raise ValueError("parallel.divisions requires three integers.")
    for value in divisions:
        finite(value, "parallel.divisions", 1, True)
    if config["parallel"]["order"] not in ["xyz", "xzy", "yxz", "yzx", "zxy", "zyx"]:
        raise ValueError("Invalid parallel.order.")
    finite(config["mesh"]["surface_layers"], "mesh.surface_layers", 0, True)
    for key in ["maxLocalCells", "maxGlobalCells"]:
        finite(config["mesh"][key], f"mesh.{key}", 1, True)
    if config["mesh"]["maxLocalCells"] > config["mesh"]["maxGlobalCells"]:
        raise ValueError("maxLocalCells must not exceed maxGlobalCells.")
    finite(config["mesh"]["merge_tolerance"], "mesh.merge_tolerance", 1e-15)
    angle = finite(
        config["mesh"]["feature_included_angle"], "mesh.feature_included_angle", 0
    )
    if angle > 180:
        raise ValueError("feature_included_angle must be <= 180.")
    levels = config["mesh"]["distance_levels"]
    if not isinstance(levels, list) or not levels:
        raise ValueError("mesh.distance_levels must not be empty.")
    previous = 0
    for pair in levels:
        if not isinstance(pair, list) or len(pair) != 2:
            raise ValueError("distance_levels requires [distance, level] pairs.")
        distance = finite(pair[0], "distance_levels.distance", 0)
        if distance <= previous:
            raise ValueError("Refinement distances must be positive and increasing.")
        previous = distance
        finite(pair[1], "distance_levels.level", 0, True)
    template = (templates / "system/snappyHexMeshDict.template").read_text()
    for group in [
        "castellated_controls",
        "snap_controls",
        "layer_controls",
        "quality_controls",
    ]:
        allowed = set(re.findall(r"\{\{mesh_" + group + r"_(\w+)\}\}", template))
        keys(config["mesh"][group], allowed, "mesh." + group)
        for name, value in config["mesh"][group].items():
            label = "mesh." + group + "." + name
            if name in [
                "allowFreeStandingZoneFaces",
                "implicitFeatureSnap",
                "explicitFeatureSnap",
                "multiRegionFeatureSnap",
                "relativeSizes",
            ]:
                if not isinstance(value, bool):
                    raise ValueError(label + " must be true or false.")
            else:
                finite(
                    value,
                    label,
                    integer=name.startswith("n")
                    and name
                    not in [
                        "minVol",
                        "minTetQuality",
                        "minArea",
                        "minTwist",
                        "minDeterminant",
                        "minFaceWeight",
                        "minVolRatio",
                        "minTriangleTwist",
                    ],
                )
    keys(
        config["numerics"]["relaxation"],
        ["p", "U", "k", "omega"],
        "numerics.relaxation",
    )
    for name, value in config["numerics"]["relaxation"].items():
        number = finite(value, "relaxation." + name, 1e-15)
        if number > 1:
            raise ValueError("Relaxation factors must be <= 1.")
    keys(
        config["numerics"]["solvers"],
        ["p", "pcorr", "U", "k", "omega"],
        "numerics.solvers",
    )
    for name, solver in config["numerics"]["solvers"].items():
        if (
            not isinstance(solver, dict)
            or not {"solver", "tolerance", "relTol", "final_relTol"} <= solver.keys()
        ):
            raise ValueError(f"Solver {name}: missing required entries.")
        for key, value in solver.items():
            if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", key):
                raise ValueError("Invalid solver option name.")
            if isinstance(value, str):
                text(value, f"solvers.{name}.{key}")
            elif not isinstance(value, bool):
                finite(value, f"solvers.{name}.{key}")
        for key in ["tolerance", "relTol", "final_relTol"]:
            finite(solver[key], f"solvers.{name}.{key}", 0)
        if float(solver["tolerance"]) == 0:
            raise ValueError("Absolute tolerance must be positive.")
        if (
            not 0 <= float(solver["relTol"]) <= 1
            or not 0 <= float(solver["final_relTol"]) <= 1
        ):
            raise ValueError("relTol must be between 0 and 1.")
    for name, value in config["schemes"].items():
        text(value, "schemes." + name)
