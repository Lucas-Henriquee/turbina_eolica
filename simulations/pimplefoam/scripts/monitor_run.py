#!/usr/bin/env python3
"""Monitora a execução sem alterar arquivos."""

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
    "log.createBaffles": "AMI interface",
    "log.topoSet": "Inlet selection",
    "log.createPatch": "Inlet patch",
    "log.prepareFields": "Initial fields",
    "log.checkMesh": "Mesh check",
    "log.decomposePar": "MPI decomposition",
    "log.pimpleFoam": "Solver",
    "log.reconstructPar": "Field reconstruction",
    "log.calculate_energy": "Analysis",
    "log.plot_results": "Plots",
}


@dataclass
class Step:
    time: float
    wall: float
    delta: float | None
    courant: float | None
    rpm: float | None
    pressure_residual: float | None
    velocity_residual: float | None


@dataclass
class SolverLog:
    steps: list[Step]
    ended: bool = False
    failed: bool = False
    modified: float | None = None


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
    if log_path(root, "log.pimpleFoam").is_file():
        return root
    archives = [
        folder
        for folder in (root / "runs").glob("*")
        if folder.is_dir() and log_path(folder, "log.pimpleFoam").is_file()
    ]
    latest = max(archives, key=lambda p: modified(p / "run_status.json"), default=None)
    recent_root = max((modified(root / name) for name in STAGES), default=0)
    if latest and modified(latest / "run_status.json") > recent_root:
        return latest
    return root


def read_controls(case):
    config = read_json(case / "metadata/resolved_config.json").get("config", {})
    controls = {
        name: config.get("time", {}).get(name)
        for name in ("startTime", "endTime", "maxCo")
    }
    try:
        text = (case / "system/controlDict").read_text()
    except OSError:
        text = ""
    text = re.sub(r"/\*.*?\*/|//[^\n]*", "", text, flags=re.S)
    for name in controls:
        match = re.search(r"\b" + name + r"\s+(" + NUMBER + r")\s*;", text)
        if match:
            controls[name] = float(match[1])
    controls["startTime"] = controls["startTime"] or 0.0
    controls["prescribed_rpm"] = config.get("motion", {}).get("prescribed_rpm")
    return controls


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


def parse_solver(text):
    steps = deque(maxlen=80)
    current = delta = courant = rpm = pressure = None
    velocity = {}
    ended = failed = False
    for line in text.splitlines():
        if re.search(r"FOAM FATAL|MPI_ABORT|exited on signal|Segmentation fault", line):
            failed = True
        if line.strip() == "End":
            ended = True
        match = re.match(r"Courant Number.*?max:\s*(" + NUMBER + r")", line)
        if match:
            courant = float(match[1])
        match = re.match(r"deltaT\s*=\s*(" + NUMBER + r")", line)
        if match:
            delta = float(match[1])
        match = re.match(r"Time =\s*(" + NUMBER + r")\s*$", line)
        if match:
            current = float(match[1])
            pressure = rpm = None
            velocity = {}
        match = re.search(r"Angular velocity:\s*\(([^)]+)\)", line)
        if match:
            values = re.findall(NUMBER, match[1])
            if len(values) == 3:
                rpm = float(values[1]) * 60 / (2 * math.pi)
        match = re.search(
            r"Solving for (p|Ux|Uy|Uz),.*?Final residual =\s*(" + NUMBER + r")", line
        )
        if match:
            if match[1] == "p":
                pressure = float(match[2])
            else:
                velocity[match[1]] = float(match[2])
        match = re.match(r"ExecutionTime.*?ClockTime\s*=\s*(" + NUMBER + r")\s*s", line)
        if match and current is not None:
            wall = float(match[1])
            # Reinícios não devem contaminar o ritmo estimado.
            if steps and (current <= steps[-1].time or wall < steps[-1].wall):
                steps.clear()
            steps.append(
                Step(
                    current,
                    wall,
                    delta,
                    courant,
                    rpm,
                    pressure,
                    max(velocity.values(), default=None),
                )
            )
    return SolverLog(list(steps), ended, failed)


def read_solver(path):
    result = parse_solver(read_tail(path))
    result.modified = modified(path) or None
    return result


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


def run_status(case, log, controls, now, stale_seconds):
    state = read_json(case / "run_status.json")
    if state.get("simulation") == "interrupted":
        return "INTERRUPTED"
    if (
        state.get("simulation") == "failed"
        or state.get("postprocessing") == "failed"
        or log.failed
    ):
        return "FAILED"
    if not log.steps:
        return "WAITING"
    target = controls["endTime"]
    if (
        log.ended
        and target is not None
        and log.steps[-1].time < target - max(1e-9, abs(target) * 1e-8)
    ):
        return "ENDED EARLY"
    if state.get("simulation") == state.get("postprocessing") == "completed":
        return "COMPLETED"
    if log.ended:
        return (
            "FINALIZING"
            if state.get("postprocessing") == "pending"
            else "SOLVER FINISHED"
        )
    if log.modified is None or now - log.modified > stale_seconds:
        return "NO RECENT OUTPUT"
    return "ACTIVE"


def status_line(status, label, detail):
    tag = f"[{status}]"
    return f"{tag:<6} {label:<24} {detail}"


def render(root, stale_seconds=120, now=None):
    now = time.time() if now is None else now
    case = select_case(root)
    path = log_path(case, "log.pimpleFoam")
    controls = read_controls(case)
    log = read_solver(path)
    status = run_status(case, log, controls, now, stale_seconds)
    last = log.steps[-1] if log.steps else None
    target, start = controls["endTime"], controls["startTime"]
    fraction = None
    if last and target is not None and target > start:
        fraction = max(0, min(1, (last.time - start) / (target - start)))
    remaining = estimate_remaining(log.steps, target) if status == "ACTIVE" else None
    eta = "~" + duration(remaining) if remaining is not None else "--"
    if status in ("COMPLETED", "FINALIZING", "SOLVER FINISHED") and fraction == 1:
        eta = duration(0)
    level = {
        "ACTIVE": "RUN",
        "FINALIZING": "RUN",
        "COMPLETED": "OK",
        "SOLVER FINISHED": "OK",
        "FAILED": "FAIL",
        "ENDED EARLY": "WARN",
        "INTERRUPTED": "WARN",
        "NO RECENT OUTPUT": "WARN",
    }.get(status, "INFO")
    current = number(last.time if last else None)
    lines = [
        status_line(level, "OpenFOAM", f"pimpleFoam | {status.title()}"),
        status_line("INFO", "Case", case),
        status_line("INFO", "Progress", progress_bar(fraction)),
        status_line("INFO", "Simulated time", f"{current} / {number(target)} s"),
    ]
    if last:
        rotor = f"{number(last.rpm)} RPM (Y)"
        if last.rpm is None and controls["prescribed_rpm"] is not None:
            rotor = f"{number(controls['prescribed_rpm'])} RPM (Y, prescribed)"
        courant = f"{number(last.courant)} / {number(controls['maxCo'])}"
        lines.extend(
            [
                status_line("INFO", "Solver time", f"{duration(last.wall)} | ETA {eta}"),
                status_line(
                    "INFO", "Time step", f"{number(last.delta)} s | Co max {courant}"
                ),
                status_line("INFO", "Rotor", rotor),
                status_line(
                    "INFO",
                    "Final residuals",
                    f"p {number(last.pressure_residual, 3)} | U max {number(last.velocity_residual, 3)}",
                ),
            ]
        )
    else:
        latest = max((log_path(case, name) for name in STAGES), key=modified)
        stage = STAGES[latest.name] if latest.is_file() else "Waiting for solver output"
        lines.append(status_line("INFO", "Stage", stage))
    log_detail = str(path.relative_to(case))
    if log.modified is not None:
        log_detail += f" | Updated {duration(now - log.modified)} ago"
    lines.append(status_line("INFO", "Log", log_detail))
    return "\n".join(lines)


def positive_seconds(value):
    seconds = float(value)
    if not math.isfinite(seconds) or seconds <= 0:
        raise argparse.ArgumentTypeError("Expected a positive number of seconds.")
    return seconds


def main():
    parser = argparse.ArgumentParser(
        description="Read-only OpenFOAM progress monitor for watch."
    )
    parser.add_argument(
        "--case", type=Path, default=ROOT, help="Case or archived run directory."
    )
    parser.add_argument(
        "--stale-seconds",
        type=positive_seconds,
        default=120,
        help="No-output threshold (default: 120).",
    )
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
