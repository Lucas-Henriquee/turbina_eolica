#!/usr/bin/env python3
"""Monitora iterações SIMPLE sem alterar arquivos."""

import argparse
from collections import deque
from dataclasses import dataclass
import json
import math
from pathlib import Path
import re
import time

ROOT = Path(__file__).resolve().parents[1]
NUMBER = r"[-+]?(?:\d*\.\d+|\d+\.?\d*)(?:[eE][-+]?\d+)?"
TAIL_BYTES = 2 * 1024 * 1024
STAGES = {
    "log.prepareCase": "Preparing case",
    "log.blockMesh": "Base mesh",
    "log.surfaceFeatureExtract": "Surface features",
    "log.snappyHexMesh": "Mesh refinement",
    "log.checkMesh": "Mesh check",
    "log.decomposePar": "MPI decomposition",
    "log.simpleFoam": "Solver",
    "log.reconstructPar": "Field reconstruction",
    "log.analyze_results": "Analysis",
    "log.plot_results": "Plots",
}


@dataclass
class Step:
    time: float
    wall: float
    residuals: dict


def read_json(path):
    try:
        value = json.loads(path.read_text())
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def modified(path):
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def log_path(case, name):
    archived = case / "logs" / name
    return archived if archived.is_file() else case / name


def select_case(root):
    if log_path(root, "log.simpleFoam").is_file():
        return root
    archives = [
        folder
        for folder in (root / "runs").glob("*")
        if folder.is_dir() and log_path(folder, "log.simpleFoam").is_file()
    ]
    latest = max(archives, key=lambda p: modified(p / "run_status.json"), default=None)
    recent_root = max((modified(root / name) for name in STAGES), default=0)
    if latest and modified(latest / "run_status.json") > recent_root:
        return latest
    return root


def read_tail(path):
    # Limita a leitura mesmo quando o log ocupa vários GB.
    try:
        with path.open("rb") as stream:
            stream.seek(0, 2)
            offset = max(0, stream.tell() - TAIL_BYTES)
            stream.seek(offset)
            data = stream.read(TAIL_BYTES)
        if offset:
            data = data.partition(b"\n")[2]
        # Ignora a última linha enquanto ela estiver sendo escrita.
        data = data.rpartition(b"\n")[0]
        return data.decode(errors="replace")
    except OSError:
        return ""


def estimate_remaining(steps, target):
    if target is None or len(steps) < 3:
        return None
    first, last = steps[0], steps[-1]
    elapsed = last.wall - first.wall
    simulated = last.time - first.time
    if elapsed < 5 or simulated <= 0 or target <= last.time:
        return None
    return (target - last.time) * elapsed / simulated


def duration(seconds):
    if seconds is None or not math.isfinite(seconds):
        return "--"
    seconds = max(0, round(seconds))
    return f"{seconds // 3600:02d}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"


def number(value, digits=5):
    return f"{value:.{digits}g}" if value is not None and math.isfinite(value) else "--"


def progress_bar(fraction, width=28):
    if fraction is None:
        return "[" + "." * width + "]   --"
    filled = round(max(0, min(1, fraction)) * width)
    return "[" + "=" * filled + "." * (width - filled) + f"] {100 * fraction:5.1f}%"


def positive_seconds(value):
    seconds = float(value)
    if not math.isfinite(seconds) or seconds <= 0:
        raise argparse.ArgumentTypeError("Expected a positive number of seconds.")
    return seconds


def parse_solver(text):
    steps = deque(maxlen=80)
    current = None
    residuals = {}
    converged = ended = failed = False
    for line in text.splitlines():
        if re.search(r"FOAM FATAL|MPI_ABORT|exited on signal|Segmentation fault", line):
            failed = True
        converged |= "SIMPLE solution converged" in line
        ended |= line.strip() == "End"
        match = re.match(r"Time =\s*(" + NUMBER + r")\s*$", line)
        if match:
            current = float(match[1])
            residuals = {}
        match = re.search(
            r"Solving for (p|Ux|Uy|Uz|k|omega), Initial residual =\s*(" + NUMBER + r")",
            line,
        )
        if match:
            field = "U" if match[1].startswith("U") else match[1]
            residuals[field] = max(residuals.get(field, 0), float(match[2]))
        match = re.match(r"ExecutionTime.*?ClockTime\s*=\s*(" + NUMBER + r")\s*s", line)
        if match and current is not None:
            wall = float(match[1])
            if steps and (current <= steps[-1].time or wall < steps[-1].wall):
                steps.clear()
            steps.append(Step(current, wall, residuals.copy()))
    return list(steps), converged, ended, failed


def read_controls(case):
    resolved = read_json(case / "metadata/resolved_config.json")
    config = resolved.get("config", {})
    target = config.get("iterations", {}).get("limit")
    omega = config.get("rotation", {}).get("angular_velocity")
    thresholds = config.get("numerics", {}).get("residual_control", {})
    for name, field in [
        ("system/controlDict", "endTime"),
        ("constant/MRFProperties", "omega"),
    ]:
        try:
            text = (case / name).read_text()
        except OSError:
            continue
        text = re.sub(r"/\*.*?\*/|//[^\n]*", "", text, flags=re.S)
        match = re.search(r"\b" + field + r"\s+(" + NUMBER + r")\s*;", text)
        if match:
            if field == "endTime":
                target = float(match[1])
            else:
                omega = float(match[1])
    return target, omega, thresholds


def render(root, stale_seconds=120, now=None):
    now = time.time() if now is None else now
    case = select_case(root)
    log = log_path(case, "log.simpleFoam")
    steps, converged, ended, failed = parse_solver(read_tail(log))
    state = read_json(case / "run_status.json")
    target, omega, thresholds = read_controls(case)
    last = steps[-1] if steps else None
    age = now - modified(log) if log.exists() else None
    if state.get("simulation") == "interrupted":
        status = "INTERRUPTED"
    elif (
        failed
        or state.get("simulation") == "failed"
        or state.get("postprocessing") == "failed"
    ):
        status = "FAILED"
    elif converged:
        status = "CONVERGED"
    elif state.get("simulation") == state.get("postprocessing") == "completed":
        status = "COMPLETED"
    elif ended:
        status = "SOLVER FINISHED"
    elif not steps:
        status = "WAITING"
    elif age is None or age > stale_seconds:
        status = "NO RECENT OUTPUT"
    else:
        status = "ACTIVE"
    fraction = (
        min(1, max(0, last.time / target)) if last and target and target > 0 else None
    )
    estimate = estimate_remaining(steps, target) if status == "ACTIVE" else None
    eta = "~" + duration(estimate) if estimate is not None else "--"
    if converged or (ended and fraction == 1):
        eta = "00:00:00"
    lines = [
        f"SIMPLEFOAM | {status}",
        f"Case      {case}",
        "",
        f"Budget    {progress_bar(fraction)}",
        f"Iteration {number(last.time if last else None)} / {number(target)}",
    ]
    if last:
        lines += [
            f"Wall log  {duration(last.wall)}   | ETA to limit {eta}",
            f"MRF speed {number(omega * 60 / (2 * math.pi) if omega is not None else None)} RPM (Y)",
            "Initial residuals / targets",
        ]
        for field in ["p", "U", "k", "omega"]:
            lines.append(
                f"  {field:<7} {number(last.residuals.get(field), 3):>9} / {number(thresholds.get(field), 3)}"
            )
    else:
        latest = max((log_path(case, name) for name in STAGES), key=modified)
        lines.append(
            f"Stage     {STAGES[latest.name] if latest.is_file() else 'Waiting for solver output'}"
        )
    lines += [
        f"Log       {log.relative_to(case)}   | Last output {duration(age)} ago",
        "",
        "Budget tracks iterations, not convergence. SIMPLE may converge earlier.",
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Read-only simpleFoam iteration monitor for watch."
    )
    parser.add_argument("--case", type=Path, default=ROOT)
    parser.add_argument("--stale-seconds", type=positive_seconds, default=120)
    args = parser.parse_args()
    case = args.case.expanduser().resolve()
    if not case.is_dir():
        parser.exit(1, f"[FAIL] Case directory not found: {case}\n")
    try:
        print(render(case, args.stale_seconds))
    except OSError as error:
        parser.exit(1, f"[FAIL] Monitor: {error}\n")


if __name__ == "__main__":
    main()
