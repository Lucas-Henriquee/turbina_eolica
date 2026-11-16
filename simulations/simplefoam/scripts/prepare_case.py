#!/usr/bin/env python3
"""Prepara o caso SIMPLE com zona MRF."""

import argparse
import hashlib
import json
from pathlib import Path
import os
import re
import shutil
import subprocess

import numpy as np
import yaml

from config_validation import validate_config
from geometry import build_cylinder_mesh, format_foam_value, read_stl_vertices, NUMBER

ROOT = Path(__file__).resolve().parents[1]


def solver_dictionaries(solvers):
    blocks = []
    for field, options in solvers.items():
        entries = "\n".join(
            f"        {key} {format_foam_value(value)};"
            for key, value in options.items()
            if key != "final_relTol"
        )
        blocks.append(
            f"    {field}\n    {{\n{entries}\n    }}\n    {field}Final\n    {{\n        ${field};\n        relTol {format_foam_value(options['final_relTol'])};\n    }}"
        )
    return "\n\n".join(blocks)


def render_templates(root, values):
    rendered = {}
    for template in (root / "config/templates").rglob("*.template"):
        text = re.sub(
            r"\{\{(\w+)\}\}",
            lambda match: format_foam_value(values[match[1]]),
            template.read_text(),
        )
        if "{{" in text:
            raise ValueError(f"Unresolved template: {template}")
        target = root / str(
            template.relative_to(root / "config/templates")
        ).removesuffix(".template")
        rendered[target] = (
            "\n".join(line.rstrip() for line in text.splitlines()).rstrip() + "\n"
        )
    return rendered


def prepare(root=ROOT, processes=None):
    config = yaml.safe_load((root / "config.yaml").read_text())
    process_count = validate_config(config, root / "config/templates", processes)
    geometry, mesh = config["geometry"], config["mesh"]
    rotor = root / "constant/triSurface" / geometry["rotor_stl"]
    cylinder = root / "constant/triSurface" / geometry["cylinder_stl"]
    if not rotor.is_file():
        raise ValueError(f"Rotor STL not found: {rotor}")
    points = read_stl_vertices(rotor)
    centre = np.array(geometry["rotation_centre"], dtype=float)
    bounds = np.array(mesh["bounds"], dtype=float)
    location = np.array(mesh["location_in_mesh"], dtype=float)
    if (
        bounds.shape != (2, 3)
        or not np.isfinite(bounds).all()
        or np.any(bounds[1] <= bounds[0])
    ):
        raise ValueError("mesh.bounds requires finite minimum and maximum XYZ vectors.")
    if np.any(location <= bounds[0]) or np.any(location >= bounds[1]):
        raise ValueError("location_in_mesh must be inside the domain.")
    if not np.isfinite(points).all():
        raise ValueError("STL contains nonfinite vertices.")
    radius = float(np.linalg.norm((points - centre)[:, [0, 2]], axis=1).max())
    if radius <= 0:
        raise ValueError("Rotor radius must be positive.")
    generated = None
    if geometry["cylinder_mode"] == "auto":
        segments = geometry["cylinder_segments"]
        cylinder_radius = (radius + geometry["cylinder_radial_clearance"]) / np.cos(
            np.pi / segments
        )
        ymin = points[:, 1].min() - geometry["cylinder_axial_clearance"]
        ymax = points[:, 1].max() + geometry["cylinder_axial_clearance"]
        generated = build_cylinder_mesh(cylinder_radius, ymin, ymax, centre, segments)
        # Valida os extremos antes de gravar o cilindro.
        cylinder_bounds = np.array(
            [
                [centre[0] - cylinder_radius, ymin, centre[2] - cylinder_radius],
                [centre[0] + cylinder_radius, ymax, centre[2] + cylinder_radius],
            ]
        )
    else:
        cylinder_points = read_stl_vertices(cylinder)
        cylinder_bounds = np.array(
            [cylinder_points.min(axis=0), cylinder_points.max(axis=0)]
        )
        cylinder_radius = min(
            np.max(np.abs(cylinder_points[:, 0] - centre[0])),
            np.max(np.abs(cylinder_points[:, 2] - centre[2])),
        )
    if (
        radius >= cylinder_radius
        or points[:, 1].min() <= cylinder_bounds[0, 1]
        or points[:, 1].max() >= cylinder_bounds[1, 1]
    ):
        raise ValueError("Rotor must fit inside the MRF cylinder.")
    if np.any(cylinder_bounds[0] <= bounds[0]) or np.any(
        cylinder_bounds[1] >= bounds[1]
    ):
        raise ValueError("MRF cylinder must fit inside mesh.bounds.")
    if (
        np.linalg.norm((location - centre)[[0, 2]]) < cylinder_radius
        and cylinder_bounds[0, 1] < location[1] < cylinder_bounds[1, 1]
    ):
        raise ValueError("location_in_mesh must be outside the MRF cylinder.")
    if not shutil.which("surfaceCheck"):
        raise ValueError("surfaceCheck not found. Load the OpenFOAM environment.")
    result = subprocess.run(
        ["surfaceCheck", str(rotor)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    (root / "log.surfaceCheck").write_text(result.stdout)
    if (
        result.returncode
        or "Surface is closed." not in result.stdout
        or "Surface has no illegal triangles." not in result.stdout
    ):
        raise ValueError("Invalid rotor STL. Log: log.surfaceCheck")

    values = {
        "rotor_file": geometry["rotor_stl"],
        "rotor_feature": Path(geometry["rotor_stl"]).with_suffix(".eMesh").name,
        "cylinder_file": geometry["cylinder_stl"],
        "cylinder_feature": Path(geometry["cylinder_stl"]).with_suffix(".eMesh").name,
        "rotation_centre": centre,
        "angular_velocity": config["rotation"]["angular_velocity"],
        "initial_velocity": config["initial"]["velocity"],
        "initial_pressure": config["initial"]["pressure"],
        "fluid_density": config["fluid"]["density"],
        "fluid_nu": config["fluid"]["nu"],
        "turbulence_model": config["turbulence"]["model"],
        "turbulence_k": config["turbulence"]["k"],
        "turbulence_omega": config["turbulence"]["omega"],
        "wind_reference": float(np.linalg.norm(config["initial"]["velocity"])),
        "rotor_area": np.pi * radius**2,
        "rotor_diameter": 2 * radius,
        "parallel_processes": process_count,
        "parallel_method": config["parallel"]["method"],
        "parallel_coefficients": "",
        "iteration_limit": config["iterations"]["limit"],
        "iteration_write_interval": config["iterations"]["write_interval"],
        "iteration_runtime_modifiable": config["iterations"]["runtime_modifiable"],
        "write_compression": "on" if config["output"]["write_compression"] else "off",
        "non_orthogonal_correctors": config["numerics"]["nNonOrthogonalCorrectors"],
        "solver_dictionaries": solver_dictionaries(config["numerics"]["solvers"]),
        "mesh_cells": mesh["cells"],
        "mesh_location": mesh["location_in_mesh"],
        "mesh_layers": mesh["add_layers"],
        "mesh_nlayers": mesh["surface_layers"],
        "mesh_rotor_level": mesh["rotor_level"],
        "mesh_cylinder_level": mesh["cylinder_level"],
        "mesh_distance_levels": "\n                ".join(
            format_foam_value(pair) for pair in mesh["distance_levels"]
        ),
        "mesh_maxLocalCells": mesh["maxLocalCells"],
        "mesh_maxGlobalCells": mesh["maxGlobalCells"],
        "mesh_merge_tolerance": mesh["merge_tolerance"],
        "mesh_feature_included_angle": mesh["feature_included_angle"],
    }
    for index, axis in enumerate("xyz"):
        values[axis + "min"], values[axis + "max"] = bounds[:, index]
    for group in [
        "castellated_controls",
        "snap_controls",
        "layer_controls",
        "quality_controls",
    ]:
        values.update(
            {"mesh_" + group + "_" + key: value for key, value in mesh[group].items()}
        )
    for section in ["output", "schemes"]:
        values.update(
            {section + "_" + key: value for key, value in config[section].items()}
        )
    for prefix, section in [
        ("residual", "residual_control"),
        ("relaxation", "relaxation"),
    ]:
        values.update(
            {
                prefix + "_" + field: value
                for field, value in config["numerics"][section].items()
            }
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
    rendered = render_templates(root, values)
    for target, text in rendered.items():
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + ".tmp")
        temporary.write_text(text)
        temporary.replace(target)
    if generated is not None:
        cylinder.write_bytes(generated)
    metadata = root / "metadata"
    metadata.mkdir(exist_ok=True)
    body = {
        "radius": radius,
        "diameter": 2 * radius,
        "swept_area": np.pi * radius**2,
        "geometry_bounds": [points.min(axis=0).tolist(), points.max(axis=0).tolist()],
        "cylinder_bounds": cylinder_bounds.tolist(),
        "rotor_sha256": hashlib.sha256(rotor.read_bytes()).hexdigest(),
        "angular_velocity_rad_s": config["rotation"]["angular_velocity"],
        "rotation_axis": [0, 1, 0],
    }
    resolved = {
        "model": "steady_mrf",
        "config": config,
        "body": body,
        "processes": process_count,
        "openfoam_version": os.environ.get("WM_PROJECT_VERSION"),
        "config_sha256": hashlib.sha256(
            (root / "config.yaml").read_bytes()
        ).hexdigest(),
    }
    (metadata / "resolved_config.json").write_text(
        json.dumps(resolved, indent=2) + "\n"
    )
    (metadata / "geometry.json").write_text(json.dumps(body, indent=2) + "\n")
    (metadata / "surfaceCheck.log").write_text(result.stdout)
    print(f"[OK] Case prepared. Metadata: {metadata}")
    return process_count


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Prepare a steady MRF simpleFoam case."
    )
    parser.add_argument("--processes", type=int)
    args = parser.parse_args()
    try:
        prepare(processes=args.processes)
    except (OSError, ValueError, TypeError, KeyError) as error:
        parser.exit(1, f"[FAIL] Prepare case: {error}\n")
