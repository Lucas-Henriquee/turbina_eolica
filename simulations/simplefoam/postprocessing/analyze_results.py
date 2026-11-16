#!/usr/bin/env python3
"""Exporta os resultados estacionários."""

import argparse
from pathlib import Path
from simulation_results import ROOT, save_analysis


def main():
    parser = argparse.ArgumentParser(
        description="Analyze steady MRF force and power results."
    )
    parser.add_argument("--case", type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        save_analysis(args.case)
        print(f"[OK] Analysis: {args.case.resolve() / 'results'}")
    except (OSError, ValueError, KeyError) as error:
        parser.exit(1, f"[FAIL] Analysis: {error}\n")


if __name__ == "__main__":
    main()
