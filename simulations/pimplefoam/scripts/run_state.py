#!/usr/bin/env python3
"""Consulta e atualiza o estado da execução."""

import argparse
import json
from pathlib import Path


def read_json(path):
    return json.loads(Path(path).read_text())


def parallel_settings():
    resolved = read_json("metadata/resolved_config.json")
    return resolved["processes"], resolved["config"]["parallel"]["mpi_test_timeout"]


def set_analysis_status(path, exit_code):
    state = read_json(path)
    state["postprocessing"] = "completed" if exit_code == 0 else "failed"
    Path(path).write_text(json.dumps(state, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description="Read or update run state.")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("parallel", help="Print MPI process count and timeout.")
    plots = commands.add_parser("plots", help="Check whether plots are enabled.")
    plots.add_argument("metadata", type=Path)
    analysis = commands.add_parser("analysis-status", help="Record the analysis exit code.")
    analysis.add_argument("status_file", type=Path)
    analysis.add_argument("exit_code", type=int)
    args = parser.parse_args()

    try:
        if args.command == "parallel":
            print(*parallel_settings())
        elif args.command == "plots":
            return 0 if read_json(args.metadata)["config"]["output"]["plots"] else 1
        else:
            set_analysis_status(args.status_file, args.exit_code)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(2, f"[FAIL] Run state: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
