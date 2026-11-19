#!/usr/bin/env python3
"""Verifica uma volta da malha nos dois sentidos, sem resolver o fluido."""

import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
NUMBER = r"[-+]?(?:\d*\.\d+|\d+\.?\d*)(?:[eE][-+]?\d+)?"


def inspect_motion_log(text, minimum_weight):
    if "FOAM FATAL" in text or re.search(r"Failed\s+\d+\s+mesh", text):
        raise ValueError("Rotating mesh failed geometry or topology checks.")
    if not re.search(r"(?m)^End\s*$", text) or "Mesh OK." not in text:
        raise ValueError("Mesh motion check did not complete.")
    weights = re.findall(r"sum\(weights\) min:(" + NUMBER + r") max:(" + NUMBER + r")", text)
    if not weights:
        raise ValueError("No AMI weights found in mesh motion check.")
    minimum = min(float(a) for a, _ in weights)
    maximum = max(float(b) for _, b in weights)
    if not np.isfinite([minimum, maximum]).all() or minimum <= minimum_weight:
        raise ValueError(f"AMI coverage is below the configured limit: {minimum:.6g}.")
    return minimum, maximum


def replace_entry(text, name, value):
    result, count = re.subn(r"(?m)^" + re.escape(name) + r"\s+[^;]+;", f"{name} {value};", text)
    if count != 1:
        raise ValueError(f"Expected one {name} entry in controlDict.")
    return result


def check_mesh_motion(case, processes=None):
    case = Path(case).resolve()
    if not any((case / f"constant/polyMesh/{name}").exists() for name in ["points", "points.gz"]):
        raise ValueError("Generate the mesh before checking its motion.")
    if not shutil.which("moveDynamicMesh"):
        raise ValueError("moveDynamicMesh not found. Load the OpenFOAM environment.")
    metadata = json.loads((case / "metadata/resolved_config.json").read_text())
    parallel = processes is not None
    mode = "parallel" if parallel else "serial"
    suffix = "Parallel" if parallel else ""
    body = metadata["body"]
    orientation = np.array(body["orientation"]).reshape(3, 3)
    minimum_weight = max(0.0, metadata["config"]["motion"]["ami_low_weight_correction"])
    results = []
    for direction in [1, -1]:
        label = "Positive" if direction > 0 else "Negative"
        log = case / f"log.meshMotion{label}{suffix}"
        with tempfile.TemporaryDirectory(prefix="rotor-motion-") as temp:
            target = Path(temp)
            shutil.copytree(case / "system", target / "system")
            shutil.copytree(case / "0", target / "0", ignore=shutil.ignore_patterns("uniform"))
            shutil.copytree(case / "constant/polyMesh", target / "constant/polyMesh")
            shutil.copy2(case / "constant/inletVelocityProfile.dat", target / "constant")
            command = ["moveDynamicMesh", "-case", str(target), "-checkAMI", "-noFunctionObjects"]
            if parallel:
                for rank in range(processes):
                    partition = f"processor{rank}"
                    shutil.copytree(case / partition / "constant", target / partition / "constant")
                    shutil.copytree(case / partition / "0", target / partition / "0")
                command = ["mpirun", "-np", str(processes), *command, "-parallel"]
            angular_momentum = np.diag(body["momentOfInertia"]) @ (orientation.T @ np.array([0., direction * 16., 0.]))
            text = (case / "constant/dynamicMeshDict").read_text()
            marker = "sixDoFRigidBodyMotionCoeffs"
            start = text.index("{", text.index(marker)) + 1
            text = text[:start] + "\n            test true;\n            angularMomentum (" + " ".join(f"{v:.15g}" for v in angular_momentum) + ");\n" + text[start:]
            (target / "constant/dynamicMeshDict").write_text(text)
            control = (case / "system/controlDict").read_text()
            for key, value in {"startFrom": "startTime", "startTime": "0", "endTime": "0.4",
                               "deltaT": "0.01", "adjustTimeStep": "false", "writeControl": "timeStep",
                               "writeInterval": "40", "purgeWrite": "1"}.items():
                control = replace_entry(control, key, value)
            (target / "system/controlDict").write_text(control)
            with log.open("w") as output:
                completed = subprocess.run(
                    command,
                    stdout=output, stderr=subprocess.STDOUT, timeout=180,
                )
            if completed.returncode:
                raise ValueError(f"Mesh motion utility failed. Log: {log}")
            try:
                minimum, maximum = inspect_motion_log(log.read_text(errors="replace"), minimum_weight)
            except ValueError as error:
                raise ValueError(f"{error} Log: {log}") from error
            results.append({"direction": direction, "min_weight_sum": minimum, "max_weight_sum": maximum})
            print(f"[OK] Mesh rotation {label.lower()}: min AMI weight {minimum:.6g}; max {maximum:.6g}")
    report_name = "mesh_motion_check_parallel.json" if parallel else "mesh_motion_check.json"
    (case / "metadata" / report_name).write_text(json.dumps({
        "angular_speed_rad_s": 16.0, "duration_s": 0.4, "step_s": 0.01,
        "mode": mode, "processes": processes or 1,
        "flow_solved": False, "directions": results,
        "limitations": "Geometry preflight only; AMI weight sums are not a convergence or conservation certificate.",
    }, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Check rotating mesh before the flow solver.")
    parser.add_argument("--case", type=Path, default=ROOT)
    parser.add_argument("--processes", type=int, help="Check the existing MPI decomposition.")
    args = parser.parse_args()
    if args.processes is not None and args.processes < 1:
        parser.error("--processes must be positive")
    try:
        check_mesh_motion(args.case, args.processes)
    except (OSError, ValueError, KeyError, subprocess.TimeoutExpired) as error:
        parser.exit(1, f"[FAIL] Mesh motion check: {error}\n")
