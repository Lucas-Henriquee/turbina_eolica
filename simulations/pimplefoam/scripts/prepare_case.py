#!/usr/bin/env python3
"""Prepara o caso OpenFOAM."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tempfile

import numpy as np
import yaml

from config_validation import validate_controls
from body_corrections import apply_body_corrections
from generator_model import resolve_generator

ROOT = Path(__file__).resolve().parents[1]
NUMBER = r"[-+]?(?:\d*\.\d+|\d+\.?\d*)(?:[eE][-+]?\d+)?"


def format_foam_value(value):
    if isinstance(value, (list, tuple, np.ndarray)):
        return "(" + " ".join(format_foam_value(v) for v in value) + ")"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float, np.number)):
        return f"{value:.12g}"
    return str(value)


def read_stl_vertices(path):
    data = path.read_bytes()
    if len(data) >= 84 and len(data) == 84 + 50 * struct.unpack_from("<I", data, 80)[0]:
        count = struct.unpack_from("<I", data, 80)[0]
        dtype = np.dtype(
            [("normal", "<f4", 3), ("vertices", "<f4", (3, 3)), ("attribute", "<u2")]
        )
        return (
            np.frombuffer(data, dtype=dtype, offset=84, count=count)["vertices"]
            .reshape(-1, 3)
            .astype(float)
        )
    values = re.findall(
        r"\bvertex\s+(" + NUMBER + r")\s+(" + NUMBER + r")\s+(" + NUMBER + r")",
        data.decode("ascii"),
    )
    if not values:
        raise ValueError(f"STL has no vertices: {path}")
    return np.array(values, dtype=float)


def run_foam_utility(args, work, log_path):
    result = subprocess.run(
        args, cwd=work, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
    )
    log_path.write_text(result.stdout)
    if result.returncode:
        raise ValueError(f"{args[0]} failed. Log: {log_path}")
    return result.stdout


def parse_inertia_entry(log, name, size):
    match = re.search(r"^" + re.escape(name) + r"\s+([^;]+);", log, re.M)
    if not match:
        raise ValueError(f"surfaceInertia did not report {name}; 6DoF setup aborted.")
    values = [float(x) for x in re.findall(NUMBER, match[1])]
    if len(values) != size or not np.isfinite(values).all():
        raise ValueError(f"{name} invalid: {values}")
    return values[0] if size == 1 else values


def build_cylinder_mesh(radius, ymin, ymax, centre, segments):
    triangles = []
    angles = np.linspace(0, 2 * np.pi, segments + 1)
    bottom = np.array(
        [
            [centre[0] + radius * np.cos(a), ymin, centre[2] + radius * np.sin(a)]
            for a in angles
        ]
    )
    top = bottom.copy()
    top[:, 1] = ymax
    b = np.array([centre[0], ymin, centre[2]])
    t = np.array([centre[0], ymax, centre[2]])
    for i in range(segments):
        triangles.extend(
            [
                [bottom[i], top[i], top[i + 1]],
                [bottom[i], top[i + 1], bottom[i + 1]],
                [b, bottom[i], bottom[i + 1]],
                [t, top[i + 1], top[i]],
            ]
        )
    data = bytearray(
        b"Generated cylinder".ljust(80, b"\0") + struct.pack("<I", len(triangles))
    )
    for triangle in np.array(triangles):
        normal = np.cross(triangle[1] - triangle[0], triangle[2] - triangle[0])
        normal /= np.linalg.norm(normal)
        data.extend(struct.pack("<12fH", *normal, *triangle.flatten(), 0))
    return bytes(data)


def compute_body_properties(rotor, density):
    """Valida o STL e calcula a inércia."""
    for tool in ["surfaceInertia", "surfaceCheck"]:
        if not shutil.which(tool):
            raise ValueError(f"{tool} not found. Load the OpenFOAM environment.")
    with tempfile.TemporaryDirectory() as temp:
        check_log = rotor.parents[2] / "log.surfaceCheck"
        check = run_foam_utility(["surfaceCheck", str(rotor)], temp, check_log)
        if (
            "Surface is closed." not in check
            or "Surface has no illegal triangles." not in check
        ):
            raise ValueError(f"Invalid STL. Log: {check_log}")
        log = run_foam_utility(
            [
                "surfaceInertia",
                "-density",
                str(density),
                str(rotor),
            ],
            temp,
            rotor.parents[2] / "log.surfaceInertia",
        )
        body = {
            k: parse_inertia_entry(log, k, n)
            for k, n in [
                ("mass", 1),
                ("centreOfMass", 3),
                ("momentOfInertia", 3),
                ("orientation", 9),
            ]
        }
        if body["mass"] <= 0 or min(body["momentOfInertia"]) <= 0:
            raise ValueError(
                "Mass and inertia must be positive. Check STL orientation and integrity."
            )
        orientation = np.array(body["orientation"]).reshape(3, 3)
        if (
            not np.allclose(orientation.T @ orientation, np.eye(3), atol=1e-6)
            or np.linalg.det(orientation) < 0
        ):
            raise ValueError("Invalid principal-axis orientation.")
        axes = (Path(temp) / "axes.obj").read_bytes()
    return body, log, check, axes


def render_case_templates(root, values, profile):
    """Gera os dicionários."""
    rendered = {}
    for template in (root / "config/templates").rglob("*.template"):
        text = template.read_text()
        text = re.sub(r"\{\{(\w+)\}\}", lambda m: format_foam_value(values[m[1]]), text)
        text = "\n".join(line.rstrip() for line in text.splitlines()).rstrip() + "\n"
        if "{{" in text:
            raise ValueError(f"Unresolved template: {template}")
        rendered[
            root
            / str(template.relative_to(root / "config/templates")).removesuffix(
                ".template"
            )
        ] = text
    rendered[root / "constant/inletVelocityProfile.dat"] = (
        "(\n"
        + "\n".join(
            f"    ({format_foam_value(t)} (0 {format_foam_value(u)} 0))"
            for t, u in profile
        )
        + "\n);\n"
    )
    return rendered


def render_solver_dictionaries(solvers):
    """Gera os blocos de solver."""
    solver_blocks = []
    for name, options in solvers.items():
        entries = "\n".join(
            f"        {key} {format_foam_value(value)};"
            for key, value in options.items()
            if key != "final_relTol"
        )
        final = format_foam_value(options["final_relTol"])
        solver_blocks.append(
            f"    {name}\n    {{\n{entries}\n    }}\n    {name}Final\n    {{\n        ${name};\n        relTol {final};\n    }}"
        )
    return "\n\n".join(solver_blocks)


def prepare_case(root=ROOT, processes=None):
    config = yaml.safe_load((root / "config.yaml").read_text())
    validate_controls(config, root / "config/templates")
    geometry, mesh = config["geometry"], config["mesh"]
    # Valida os nomes usados nos dicionários.
    for key in ["rotor_stl", "cylinder_stl"]:
        if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]*\.stl", geometry[key]):
            raise ValueError(
                f"{key}: use a simple STL filename in constant/triSurface."
            )
    if geometry["rotor_stl"] == geometry["cylinder_stl"]:
        raise ValueError("Rotor and cylinder must use different files.")
    centre = np.array(geometry["rotation_centre"], dtype=float)
    if centre.shape != (3,) or not np.isfinite(centre).all():
        raise ValueError("rotation_centre requires three finite components.")
    for section, keys in [
        ("geometry", ["material_density"]),
        ("fluid", ["density", "nu"]),
        ("turbulence", ["k", "omega"]),
        ("time", ["endTime", "deltaT", "maxDeltaT", "maxCo", "writeInterval"]),
        ("wind", ["reference_speed"]),
        ("output", ["min_wind_speed", "yplus_interval"]),
    ]:
        for key in keys:
            value = float(config[section][key])
            if not np.isfinite(value) or value <= 0:
                raise ValueError(f"{section}.{key} must be positive and finite.")
            config[section][key] = value
    for section, keys, minimum in [
        ("mesh", ["rotor_level", "cylinder_level"], 0),
        ("output", ["sample_steps"], 1),
        ("numerics", ["nOuterCorrectors", "nCorrectors"], 1),
        ("numerics", ["nNonOrthogonalCorrectors"], 0),
        ("time", ["writePrecision"], 6),
    ]:
        for key in keys:
            value = config[section][key]
            if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
                raise ValueError(f"{section}.{key} must be an integer >= {minimum}.")
    for key in ["acceleration_relaxation", "acceleration_damping"]:
        if not 0 < config["motion"][key] <= 1:
            raise ValueError(f"motion.{key} must be in (0, 1].")
    if config["motion"]["shaft_damping"] < 0:
        raise ValueError("shaft_damping must be nonnegative.")
    profile = np.array(config["wind"]["profile"], dtype=float)
    if (
        profile.ndim != 2
        or profile.shape[1] != 2
        or len(profile) < 2
        or not np.isfinite(profile).all()
        or np.any(np.diff(profile[:, 0]) <= 0)
        or profile[0, 0] > 0
        or profile[-1, 0] < config["time"]["endTime"]
        or np.any(profile[:, 1] < 0)
    ):
        raise ValueError(
            "wind.profile requires increasing times covering 0 to endTime and nonnegative speeds."
        )
    # Relaciona o domínio com a bancada.
    bounds = np.array(mesh["bounds"], dtype=float)
    if (
        bounds.shape != (2, 3)
        or not np.isfinite(bounds).all()
        or np.any(bounds[1] <= bounds[0])
    ):
        raise ValueError("Invalid mesh.bounds.")
    bench = config["bench"]
    if not np.isclose(bounds[0, 1], centre[1] - bench["fan_distance"]):
        raise ValueError("mesh.bounds.ymin must match the fan inlet plane.")
    if not np.isclose(bounds[0, 2], centre[2] - bench["axis_height"]):
        raise ValueError("mesh.bounds.zmin must match the ground plane.")
    fan_radius = bench["fan_diameter"] / 2
    if (
        centre[0] - fan_radius <= bounds[0, 0]
        or centre[0] + fan_radius >= bounds[1, 0]
        or centre[2] - fan_radius <= bounds[0, 2]
        or centre[2] + fan_radius >= bounds[1, 2]
    ):
        raise ValueError(
            "The fan disk must fit inside the inlet without touching the ground."
        )
    if bench["fan_refinement_depth"] >= bounds[1, 1] - bounds[0, 1]:
        raise ValueError(
            "fan_refinement_depth must be smaller than the domain length in Y."
        )
    cells = np.array(mesh["cells"])
    if cells.shape != (3,) or np.any(cells < 1) or np.any(cells != cells.astype(int)):
        raise ValueError("mesh.cells requires three positive integers.")
    location = np.array(mesh["location_in_mesh"], dtype=float)
    if (
        location.shape != (3,)
        or np.any(location <= bounds[0])
        or np.any(location >= bounds[1])
    ):
        raise ValueError("location_in_mesh must be inside the domain.")
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9]*", config["turbulence"]["model"]):
        raise ValueError("Invalid turbulence model name.")
    process_count = (
        processes if processes is not None else config["parallel"]["processes"]
    )
    if process_count is None:
        process_count = max(1, (os.cpu_count() or 1) // 2)
    if (
        isinstance(process_count, bool)
        or not isinstance(process_count, int)
        or process_count < 1
    ):
        raise ValueError("Process count must be a positive integer.")
    if (
        config["parallel"]["method"] != "scotch"
        and int(np.prod(config["parallel"]["divisions"])) != process_count
    ):
        raise ValueError("parallel.divisions must multiply to the process count.")
    rotor = root / "constant/triSurface" / geometry["rotor_stl"]
    points = read_stl_vertices(rotor)
    radius = float(np.linalg.norm((points - centre)[:, [0, 2]], axis=1).max())
    if not np.isfinite(points).all() or radius <= 0:
        raise ValueError("Invalid geometry.")
    generated = None
    cylinder = root / "constant/triSurface" / geometry["cylinder_stl"]
    if geometry["cylinder_mode"] == "auto":
        if (
            min(
                geometry["cylinder_radial_clearance"],
                geometry["cylinder_axial_clearance"],
            )
            <= 0
            or not isinstance(geometry["cylinder_segments"], int)
            or geometry["cylinder_segments"] < 16
        ):
            raise ValueError(
                "Clearances must be positive; cylinder_segments must be an integer >= 16."
            )
        # Compensa a aproximação poligonal do cilindro.
        cylinder_radius_with_clearance = (
            radius + geometry["cylinder_radial_clearance"]
        ) / np.cos(np.pi / geometry["cylinder_segments"])
        generated = build_cylinder_mesh(
            cylinder_radius_with_clearance,
            points[:, 1].min() - geometry["cylinder_axial_clearance"],
            points[:, 1].max() + geometry["cylinder_axial_clearance"],
            centre,
            geometry["cylinder_segments"],
        )
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / "cylinder.stl"
            p.write_bytes(generated)
            cylinder_points = read_stl_vertices(p)
    elif geometry["cylinder_mode"] == "existing":
        cylinder_points = read_stl_vertices(cylinder)
    else:
        raise ValueError("cylinder_mode must be existing or auto.")
    # Desconsidera vértices internos das tampas.
    cylinder_radius = min(
        np.max(np.abs(cylinder_points[:, 0] - centre[0])),
        np.max(np.abs(cylinder_points[:, 2] - centre[2])),
    )
    if (
        radius >= cylinder_radius
        or points[:, 1].min() <= cylinder_points[:, 1].min()
        or points[:, 1].max() >= cylinder_points[:, 1].max()
    ):
        raise ValueError(
            "Rotor does not fit inside the cylinder. Adjust the STL or use cylinder_mode: auto."
        )
    if np.any(cylinder_points.min(axis=0) <= bounds[0]) or np.any(
        cylinder_points.max(axis=0) >= bounds[1]
    ):
        raise ValueError("Cylinder does not fit inside the domain. Adjust mesh.bounds.")
    if (
        np.linalg.norm((location - centre)[[0, 2]]) < cylinder_radius
        and cylinder_points[:, 1].min() < location[1] < cylinder_points[:, 1].max()
    ):
        raise ValueError("location_in_mesh must be outside the cylinder.")
    # Mantém a região rotativa sem deformação.
    farthest = float(np.linalg.norm(cylinder_points - centre, axis=1).max())
    if config["motion"]["inner_distance"] is None:
        config["motion"]["inner_distance"] = float(
            np.ceil((farthest + 0.02) * 100) / 100
        )
    if config["motion"]["outer_distance"] is None:
        config["motion"]["outer_distance"] = config["motion"]["inner_distance"] + 0.10
    if (
        config["motion"]["inner_distance"] <= farthest
        or config["motion"]["outer_distance"] <= config["motion"]["inner_distance"]
    ):
        raise ValueError(
            f"inner_distance must exceed {farthest:.6g} m; outer_distance must exceed inner_distance."
        )
    body, log, check, axes = compute_body_properties(
        rotor, geometry["material_density"]
    )
    body = apply_body_corrections(body, geometry)
    generator = resolve_generator(config)
    values = {
        "rotor_file": geometry["rotor_stl"],
        "rotor_feature": Path(geometry["rotor_stl"]).with_suffix(".eMesh").name,
        "cylinder_file": geometry["cylinder_stl"],
        "cylinder_feature": Path(geometry["cylinder_stl"]).with_suffix(".eMesh").name,
        "rotation_centre": centre,
        "body_mass": body["mass"],
        "body_com": body["centreOfMass"],
        "body_inertia": body["momentOfInertia"],
        "body_orientation": body["orientation"],
        "fan_point1": [centre[0], bounds[0, 1] - 0.01, centre[2]],
        "fan_point2": [
            centre[0],
            bounds[0, 1] + bench["fan_refinement_depth"],
            centre[2],
        ],
        "fan_radius": fan_radius,
        "fan_refinement": bench["fan_refinement"],
        "rotor_radius": radius,
        "rotor_area": np.pi * radius**2,
        "fluid_density": config["fluid"]["density"],
        "fluid_nu": config["fluid"]["nu"],
        "wind_reference": config["wind"]["reference_speed"],
        "parallel_processes": process_count,
        "turbulence_model": config["turbulence"]["model"],
        "turbulence_k": config["turbulence"]["k"],
        "turbulence_omega": config["turbulence"]["omega"],
        "ami_low_weight": config["motion"]["ami_low_weight_correction"],
        "motion_inner": config["motion"]["inner_distance"],
        "motion_outer": config["motion"]["outer_distance"],
        "motion_gravity": config["motion"]["gravity"],
        "motion_relaxation": config["motion"]["acceleration_relaxation"],
        "motion_damping": config["motion"]["acceleration_damping"],
        "shaft_damping": config["motion"]["shaft_damping"],
        "generator_damping": generator["electrical_damping_N_m_s_rad"],
        "generator_mechanical_damping": generator["mechanical_damping_N_m_s_rad"],
        "mesh_cells": mesh["cells"],
        "mesh_location": mesh["location_in_mesh"],
        "mesh_layers": mesh["add_layers"],
        "mesh_nlayers": mesh["surface_layers"],
        "mesh_rotor_level": mesh["rotor_level"],
        "mesh_cylinder_level": mesh["cylinder_level"],
        "mesh_distance_levels": "\n                ".join(
            format_foam_value(x) for x in mesh["distance_levels"]
        ),
    }
    for i, axis in enumerate("xyz"):
        values[axis + "min"] = bounds[0, i]
        values[axis + "max"] = bounds[1, i]
    for section in ["time", "output", "numerics"]:
        values.update({section + "_" + k: v for k, v in config[section].items()})
    for key in ["maxLocalCells", "maxGlobalCells"]:
        values["mesh_" + key] = mesh[key]
    values.update(
        initial_velocity=config["initial"]["velocity"],
        initial_pressure=config["initial"]["pressure"],
        parallel_method=config["parallel"]["method"],
        parallel_coefficients="",
    )
    values["time_writeCompression"] = (
        "on" if config["time"]["writeCompression"] else "off"
    )
    if config["parallel"]["method"] != "scotch":
        method = config["parallel"]["method"]
        order = (
            f"    order {config['parallel']['order']};\n"
            if method == "hierarchical"
            else ""
        )
        values["parallel_coefficients"] = (
            f"{method}Coeffs\n{{\n    n {format_foam_value(config['parallel']['divisions'])};\n    delta 0.001;\n{order}}}"
        )
    values["solver_dictionaries"] = render_solver_dictionaries(
        config["numerics"]["solvers"]
    )
    values.update(
        {
            "relaxation_" + key: value
            for key, value in config["numerics"]["relaxation"].items()
        }
    )
    values.update({"schemes_" + key: value for key, value in config["schemes"].items()})
    for group in [
        "castellated_controls",
        "snap_controls",
        "layer_controls",
        "quality_controls",
    ]:
        values.update(
            {"mesh_" + group + "_" + key: value for key, value in mesh[group].items()}
        )
    values.update(
        mesh_merge_tolerance=mesh["merge_tolerance"],
        mesh_feature_included_angle=mesh["feature_included_angle"],
    )
    integration = config["motion"]["integration"]
    integration_keys = (
        ["gamma", "beta"] if integration["type"] == "Newmark" else ["aoc", "voc"]
    )
    values["motion_integration"] = (
        "type "
        + integration["type"]
        + ";\n"
        + "\n".join(
            f"                {key} {format_foam_value(integration[key])};"
            for key in integration_keys
        )
    )
    rendered = render_case_templates(root, values, profile)
    metadata = root / "metadata"
    metadata.mkdir(exist_ok=True)
    body.update(
        volume=body["geometry_mass"] / geometry["material_density"],
        surface_area=float(re.search(r"Surface area:\s*(" + NUMBER + ")", log)[1]),
        radius=radius,
        swept_area=np.pi * radius**2,
        rotor_sha256=hashlib.sha256(rotor.read_bytes()).hexdigest(),
        density=geometry["material_density"],
    )
    body["geometry_bounds"] = [points.min(axis=0).tolist(), points.max(axis=0).tolist()]
    body["cylinder_bounds"] = [
        cylinder_points.min(axis=0).tolist(),
        cylinder_points.max(axis=0).tolist(),
    ]
    # Grava após validar.
    for path, text in rendered.items():
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(text)
        tmp.replace(path)
    if generated is not None:
        cylinder.write_bytes(generated)
    (metadata / "surfaceInertia.log").write_text(log)
    (metadata / "surfaceCheck.log").write_text(check)
    (metadata / "axes.obj").write_bytes(axes)
    (metadata / "body_properties.json").write_text(json.dumps(body, indent=2) + "\n")
    (metadata / "resolved_config.json").write_text(
        json.dumps(
            {
                "config": config,
                "body": body,
                "generator": generator,
                "processes": process_count,
                "openfoam_version": os.environ.get("WM_PROJECT_VERSION"),
                "config_sha256": hashlib.sha256(
                    (root / "config.yaml").read_bytes()
                ).hexdigest(),
            },
            indent=2,
        )
        + "\n"
    )
    print(f"[OK] Case prepared. Metadata: {metadata}")
    return process_count


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Validate geometry and generate case dictionaries."
    )
    parser.add_argument("--processes", type=int)
    args = parser.parse_args()
    try:
        prepare_case(processes=args.processes)
    except (ValueError, KeyError, TypeError, OSError) as error:
        parser.exit(1, f"[FAIL] Prepare case: {error}\n")
