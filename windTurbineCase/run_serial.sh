#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/scripts/lib_foam.sh"

check_env

echo "  windTurbineCase  —  serial"
echo ""

run_step blockMesh
run_step surfaceFeatureExtract
run_step snappyHexMesh -overwrite
run_step createBaffles -overwrite
run_step checkMesh

rm -f 0/cellLevel 0/pointLevel 0/cellToRegion

run_solver_serial

archive_run