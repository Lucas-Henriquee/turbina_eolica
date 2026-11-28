"""Valida o caso estacionário."""

import math
import re


def require_keys(mapping, keys, name):
    if not isinstance(mapping, dict):
        raise ValueError(f"{name}: expected a mapping.")
    missing, unknown = set(keys) - mapping.keys(), mapping.keys() - set(keys)
    if missing or unknown:
        raise ValueError(
            f"{name}: missing {sorted(missing)}, unknown {sorted(unknown)}."
        )


def finite(value, name, minimum=None, integer=False):
    if isinstance(value, bool) or (integer and not isinstance(value, int)):
        raise ValueError(f"{name}: invalid numeric type.")
    number = float(value)
    if not math.isfinite(number) or (minimum is not None and number < minimum):
        raise ValueError(f"{name}: invalid value {value}.")
    return number


def validate_config(config, templates, processes=None):
    sections = {
        "geometry": [
            "rotor_stl",
            "cylinder_stl",
            "cylinder_mode",
            "rotation_centre",
            "cylinder_radial_clearance",
            "cylinder_axial_clearance",
            "cylinder_segments",
        ],
        "bench": [
            "fan_diameter",
            "fan_distance",
            "axis_height",
            "fan_speed",
            "fan_refinement",
            "fan_refinement_depth",
        ],
        "fluid": ["density", "nu"],
        "initial": ["velocity", "pressure"],
        "turbulence": ["model", "k", "omega"],
        "rotation": ["angular_velocity"],
        "iterations": ["limit", "write_interval", "runtime_modifiable"],
        "output": [
            "sample_steps",
            "average_start_fraction",
            "min_wind_speed",
            "plots",
            "write_format",
            "write_precision",
            "write_compression",
            "time_precision",
        ],
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
            "nNonOrthogonalCorrectors",
            "residual_control",
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
    require_keys(config, sections, "config")
    if isinstance(config["mesh"], dict):
        sections["mesh"].extend(
            key for key in ("cylinder_surface_level", "y_grading") if key in config["mesh"]
        )
    if isinstance(config["schemes"], dict) and "omega_laplacian" in config["schemes"]:
        sections["schemes"].append("omega_laplacian")
    for section, keys in sections.items():
        require_keys(config[section], keys, section)
    for section, keys in {
        "fluid": ["density", "nu"],
        "bench": ["fan_diameter", "fan_distance", "axis_height", "fan_speed", "fan_refinement_depth"],
        "turbulence": ["k", "omega"],
        "geometry": ["cylinder_radial_clearance", "cylinder_axial_clearance"],
        "output": ["min_wind_speed"],
    }.items():
        for key in keys:
            finite(config[section][key], f"{section}.{key}", 1e-15)
    for section, keys in {
        "iterations": ["limit", "write_interval"],
        "output": ["sample_steps", "write_precision", "time_precision"],
        "parallel": ["processes", "mpi_test_timeout"],
    }.items():
        for key in keys:
            finite(config[section][key], f"{section}.{key}", 1, True)
    finite(config["bench"]["fan_refinement"], "bench.fan_refinement", 0, True)
    finite(
        config["geometry"]["cylinder_segments"], "geometry.cylinder_segments", 16, True
    )
    finite(config["initial"]["pressure"], "initial.pressure")
    finite(config["rotation"]["angular_velocity"], "rotation.angular_velocity")
    fraction = finite(
        config["output"]["average_start_fraction"], "output.average_start_fraction", 0
    )
    if fraction >= 1:
        raise ValueError("average_start_fraction must be below 1.")
    for section, key in [
        ("iterations", "runtime_modifiable"),
        ("output", "plots"),
        ("output", "write_compression"),
        ("mesh", "add_layers"),
    ]:
        if not isinstance(config[section][key], bool):
            raise ValueError(f"{section}.{key} must be true or false.")
    if config["output"]["write_format"] not in ["ascii", "binary"]:
        raise ValueError("write_format must be ascii or binary.")
    if config["turbulence"]["model"] != "kOmegaSST":
        raise ValueError("Only kOmegaSST is supported by the current boundary fields.")
    if config["schemes"]["time"] != "steadyState":
        raise ValueError("simpleFoam requires schemes.time: steadyState.")
    for value in config["schemes"].values():
        if not isinstance(value, str) or any(char in value for char in ';{}\n\r#$"'):
            raise ValueError("Invalid discretization scheme text.")
    geometry, mesh = config["geometry"], config["mesh"]
    for key in ["rotor_stl", "cylinder_stl"]:
        if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]*\.stl", geometry[key]):
            raise ValueError(f"Invalid {key} filename.")
    if geometry["rotor_stl"] == geometry["cylinder_stl"] or geometry[
        "cylinder_mode"
    ] not in ["auto", "existing"]:
        raise ValueError("Invalid cylinder geometry configuration.")
    for section, key in [
        ("geometry", "rotation_centre"),
        ("initial", "velocity"),
        ("mesh", "cells"),
        ("mesh", "location_in_mesh"),
    ]:
        vector = config[section][key]
        if not isinstance(vector, list) or len(vector) != 3:
            raise ValueError(f"{section}.{key} requires three components.")
        for value in vector:
            finite(
                value, f"{section}.{key}", 1 if key == "cells" else None, key == "cells"
            )
    for key in ["rotor_level", "cylinder_level", "surface_layers"]:
        finite(mesh[key], "mesh." + key, 0, True)
    if "cylinder_surface_level" in mesh:
        finite(mesh["cylinder_surface_level"], "mesh.cylinder_surface_level", 0, True)
    if "y_grading" in mesh:
        sections_y = mesh["y_grading"]
        if not isinstance(sections_y, list) or not sections_y:
            raise ValueError("mesh.y_grading requires at least one section.")
        for row in sections_y:
            if not isinstance(row, list) or len(row) != 3:
                raise ValueError("mesh.y_grading entries require [length, cells, expansion].")
            finite(row[0], "mesh.y_grading length", 1e-12)
            finite(row[1], "mesh.y_grading cells", 1, True)
            finite(row[2], "mesh.y_grading expansion", 1e-12)
        if sum(row[1] for row in sections_y) != mesh["cells"][1]:
            raise ValueError("mesh.y_grading cells must sum to mesh.cells[1].")
    for key in ["maxLocalCells", "maxGlobalCells"]:
        finite(mesh[key], "mesh." + key, 1, True)
    if mesh["maxLocalCells"] > mesh["maxGlobalCells"]:
        raise ValueError("maxLocalCells must not exceed maxGlobalCells.")
    finite(mesh["merge_tolerance"], "mesh.merge_tolerance", 1e-15)
    angle = finite(mesh["feature_included_angle"], "mesh.feature_included_angle", 0)
    if angle > 180:
        raise ValueError("feature_included_angle must not exceed 180 degrees.")
    previous = 0
    if not mesh["distance_levels"]:
        raise ValueError("distance_levels must not be empty.")
    for distance, level in mesh["distance_levels"]:
        if finite(distance, "refinement distance", 0) <= previous:
            raise ValueError("Refinement distances must be positive and increasing.")
        previous = distance
        finite(level, "refinement level", 0, True)
    template = (templates / "system/snappyHexMeshDict.template").read_text()
    for group in [
        "castellated_controls",
        "snap_controls",
        "layer_controls",
        "quality_controls",
    ]:
        allowed = re.findall(r"\{\{mesh_" + group + r"_(\w+)\}\}", template)
        require_keys(mesh[group], allowed, "mesh." + group)
        for key, value in mesh[group].items():
            if key in [
                "allowFreeStandingZoneFaces",
                "implicitFeatureSnap",
                "explicitFeatureSnap",
                "multiRegionFeatureSnap",
                "relativeSizes",
            ]:
                if not isinstance(value, bool):
                    raise ValueError(f"mesh.{group}.{key} must be boolean.")
            else:
                finite(value, f"mesh.{group}.{key}", integer=key.startswith("n"))
    numerics = config["numerics"]
    finite(numerics["nNonOrthogonalCorrectors"], "nNonOrthogonalCorrectors", 0, True)
    require_keys(
        numerics["residual_control"], ["p", "U", "k", "omega"], "residual_control"
    )
    require_keys(numerics["relaxation"], ["p", "U", "k", "omega"], "relaxation")
    require_keys(numerics["solvers"], ["p", "pcorr", "U", "k", "omega"], "solvers")
    for field, value in numerics["residual_control"].items():
        finite(value, "residual_control." + field, 1e-15)
    for field, value in numerics["relaxation"].items():
        if finite(value, "relaxation." + field, 1e-15) > 1:
            raise ValueError("Relaxation factors must not exceed 1.")
    for field, solver in numerics["solvers"].items():
        require_keys(
            solver,
            ["solver", "smoother", "tolerance", "relTol", "final_relTol"],
            "solvers." + field,
        )
        for key in ["solver", "smoother"]:
            if not isinstance(solver[key], str) or not re.fullmatch(
                r"[A-Za-z][A-Za-z0-9]*", solver[key]
            ):
                raise ValueError(f"Invalid solver option: {field}.{key}")
        finite(solver["tolerance"], "solver tolerance", 1e-15)
        for key in ["relTol", "final_relTol"]:
            if finite(solver[key], key, 0) > 1:
                raise ValueError("Relative tolerances must not exceed 1.")
    parallel = config["parallel"]
    process_count = parallel["processes"] if processes is None else processes
    finite(process_count, "process count", 1, True)
    if parallel["method"] not in ["scotch", "simple", "hierarchical"] or parallel[
        "order"
    ] not in ["xyz", "xzy", "yxz", "yzx", "zxy", "zyx"]:
        raise ValueError("Invalid parallel method or order.")
    if not isinstance(parallel["divisions"], list) or len(parallel["divisions"]) != 3:
        raise ValueError("parallel.divisions requires three components.")
    product = 1
    for value in parallel["divisions"]:
        product *= finite(value, "parallel.divisions", 1, True)
    if parallel["method"] != "scotch" and product != process_count:
        raise ValueError("parallel.divisions must multiply to the process count.")
    return process_count
