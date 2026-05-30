#!/usr/bin/env bash
# run_mpi.sh — pipeline completo: malha + simulação paralela (MPI).
# Uso: ./run_mpi.sh [num_processos]   (padrão: 12)

set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib_foam.sh"

check_env

NP="${1:-12}"

echo "  windTurbineCase  —  paralelo  (${NP} processos MPI)"
echo ""

sed -i -E "s/(numberOfSubdomains[[:space:]]+)[0-9]+;/\1${NP};/" system/decomposeParDict

run_step blockMesh
run_step surfaceFeatureExtract
run_step snappyHexMesh -overwrite
run_step createBaffles -overwrite
run_step checkMesh

rm -f 0/cellLevel
rm -f 0/pointLevel

run_step decomposePar -force

run_solver_parallel "${NP}"

archive_logs

touch windTurbineCase.foam
echo "  Pronto. Abra windTurbineCase.foam no ParaView."