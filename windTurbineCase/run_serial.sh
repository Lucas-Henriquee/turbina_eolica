#!/usr/bin/env bash
# run_serial.sh — pipeline completo: malha + simulação serial.
# Uso: ./run_serial.sh

set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib_foam.sh"

check_env

echo "  windTurbineCase  —  serial"
echo ""

run_step blockMesh
run_step surfaceFeatureExtract
run_step snappyHexMesh -overwrite
run_step createBaffles -overwrite
run_step checkMesh

run_solver_serial

archive_logs

touch windTurbineCase.foam