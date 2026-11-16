#!/usr/bin/env python3
"""Gera o relatório do caso MRF."""

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def write_report(case, output=None):
    case = Path(case).resolve()
    output = Path(output or "config.txt")
    if not output.is_absolute():
        output = case / output
    resolved = case / "metadata/resolved_config.json"
    status = case / "run_status.json"
    lines = [
        "STEADY MRF CASE",
        f"Generated: {datetime.now().astimezone().isoformat(timespec='seconds')}",
        f"Case: {case}",
    ]
    if status.exists():
        lines += ["", "RUN STATUS", status.read_text().strip()]
    if resolved.exists():
        lines += ["", "RESOLVED CONFIGURATION", resolved.read_text().strip()]
        saved = json.loads(resolved.read_text())
        if (case / "config.yaml").exists() and hashlib.sha256(
            (case / "config.yaml").read_bytes()
        ).hexdigest() != saved["config_sha256"]:
            lines += ["WARNING: config.yaml differs from the prepared configuration."]
    elif (case / "config.yaml").exists():
        lines += ["", "UNPREPARED CONFIGURATION", (case / "config.yaml").read_text()]
    summary = case / "results/summary.json"
    if summary.exists():
        lines += ["", "RESULTS", summary.read_text().strip()]
    lines += ["", "OPENFOAM INPUTS"]
    files = list((case / "system").glob("*")) + list((case / "0").glob("*"))
    files += [
        case / "constant" / name
        for name in ["MRFProperties", "transportProperties", "turbulenceProperties"]
    ]
    for path in sorted(files):
        if path.is_file():
            lines += [
                f"{path.relative_to(case)} SHA256 {hashlib.sha256(path.read_bytes()).hexdigest()}",
                path.read_text(errors="replace").strip(),
                "",
            ]
    lines += [
        "Iteration indices are not physical time.",
        "MRF rotation is prescribed; rotor mass and free acceleration are not modeled.",
        "Power is signed aerodynamic torque times prescribed angular velocity.",
        "No transient energy integral is reported.",
    ]
    output.write_text("\n".join(lines) + "\n")
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Write the steady-case report.")
    parser.add_argument("output", nargs="?", default="config.txt")
    parser.add_argument("--case", type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        write_report(args.case, args.output)
    except (OSError, ValueError, KeyError) as error:
        parser.exit(1, f"[FAIL] Configuration report: {error}\n")
