#!/usr/bin/env python3
"""Calcula energia e exporta os resultados."""
import argparse
from pathlib import Path
from simulation_results import ROOT, save_analysis

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Calculate aerodynamic power and energy."
    )
    parser.add_argument("--case", type=Path, default=ROOT)
    parser.add_argument(
        "--bench-voltage-calibration",
        type=float,
        nargs=4,
        metavar=("V_PER_RPM", "MIN_RPM", "MAX_RPM", "OHMS"),
        help="Estimate electrical output from measured load voltage within an RPM range.",
    )
    args = parser.parse_args()
    try:
        save_analysis(args.case, args.bench_voltage_calibration)
        print(f"[OK] Analysis: {args.case.resolve()}/results")
    except (OSError, ValueError, KeyError) as error:
        parser.exit(1, f"[FAIL] Analysis: {error}\n")
