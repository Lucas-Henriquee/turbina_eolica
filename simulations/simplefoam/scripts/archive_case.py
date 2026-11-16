#!/usr/bin/env python3
"""Arquiva o caso e os resultados."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import re
import shutil

from config_report import write_report

ROOT = Path(__file__).resolve().parents[1]


def archive(root, status):
    runs = root / "runs"
    runs.mkdir(exist_ok=True)
    prefix = "test" if status == "completed" else "failed"
    ids = [
        int(m[1]) for p in runs.iterdir() if (m := re.match(prefix + r"(\d+)_", p.name))
    ]
    target = (
        runs / f"{prefix}{max(ids,default=0)+1:03d}_{datetime.now():%Y%m%d_%H%M%S_%f}"
    )
    target.mkdir()
    (target / "logs").mkdir()
    # Preserva as entradas.
    for name in ["system", "0", "config", "scripts", "postprocessing"]:
        shutil.copytree(
            root / name, target / name, ignore=shutil.ignore_patterns("__pycache__")
        )
    shutil.copytree(
        root / "constant",
        target / "constant",
        ignore=shutil.ignore_patterns("polyMesh", "extendedFeatureEdgeMesh", "*.eMesh"),
    )
    shutil.copy2(root / "config.yaml", target / "config.yaml")
    for name in [
        "run_mpi.sh",
        "run_serial.sh",
        "create_mesh.sh",
        "clean_runs.sh",
        "README.md",
    ]:
        if (root / name).exists():
            shutil.copy2(root / name, target / name)
    # Inclui as dependências para manter o arquivo exportado independente.
    for parent in (root, *root.parents):
        requirements = parent / "requirements.txt"
        if requirements.is_file():
            shutil.copy2(requirements, target / "requirements.txt")
            break
    processors = []
    for path in list(root.iterdir()):
        if (
            status == "completed"
            and re.fullmatch(r"processor\d+", path.name)
            and path.is_dir()
        ):
            processors.append(path)
            continue
        if path.is_dir() and (
            re.fullmatch(r"\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", path.name)
            and path.name != "0"
            or path.name in ["postProcessing", "results", "metadata", "VTK"]
            or re.fullmatch(r"processor\d+", path.name)
        ):
            shutil.move(str(path), target / path.name)
        elif path.is_file() and path.name.startswith("log."):
            shutil.move(str(path), target / "logs" / path.name)
    if (root / "constant/polyMesh").exists():
        shutil.move(str(root / "constant/polyMesh"), target / "constant/polyMesh")
    if (root / "constant/extendedFeatureEdgeMesh").exists():
        shutil.move(
            str(root / "constant/extendedFeatureEdgeMesh"),
            target / "constant/extendedFeatureEdgeMesh",
        )
    # Remove partições já reconstruídas.
    for path in processors:
        shutil.rmtree(path)
    # Remove arestas regeneráveis.
    for path in (root / "constant/triSurface").glob("*.eMesh"):
        path.unlink()
    for name in [
        "cellLevel",
        "pointLevel",
        "cellToRegion",
        "nSurfaceLayers",
        "thickness",
        "thicknessFraction",
    ]:
        (root / "0" / name).unlink(missing_ok=True)
    (target / (target.name + ".foam")).touch()
    (target / "run_status.json").write_text(
        json.dumps(
            {
                "simulation": status,
                "postprocessing": "pending" if status == "completed" else "not_run",
            },
            indent=2,
        )
        + "\n"
    )
    write_report(target)
    return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Archive case inputs and results.")
    parser.add_argument(
        "--status", choices=["completed", "failed", "interrupted"], required=True
    )
    args = parser.parse_args()
    print(archive(ROOT, args.status))
